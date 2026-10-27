//! Windows Graphics Capture, single-frame only. No desktop cropping fallback for windows.
use super::*;
use ::windows::{
    core::{factory, Interface, Ref, BOOL},
    Foundation::TypedEventHandler,
    Graphics::{
        Capture::{Direct3D11CaptureFramePool, GraphicsCaptureItem, GraphicsCaptureSession},
        DirectX::{Direct3D11::IDirect3DDevice, DirectXPixelFormat},
    },
    Win32::{
        Foundation::{HMODULE, HWND, LPARAM, RECT},
        Graphics::{
            Direct3D::D3D_DRIVER_TYPE_HARDWARE,
            Direct3D11::*,
            Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED},
            Dxgi::IDXGIDevice,
            Gdi::*,
        },
        System::WinRT::{
            Direct3D11::{CreateDirect3D11DeviceFromDXGIDevice, IDirect3DDxgiInterfaceAccess},
            Graphics::Capture::IGraphicsCaptureItemInterop,
            RoInitialize, RoUninitialize, RO_INIT_MULTITHREADED,
        },
        UI::{
            HiDpi::{SetThreadDpiAwarenessContext, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2},
            WindowsAndMessaging::*,
        },
    },
};
use base64::Engine;
use std::{
    sync::mpsc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
fn native_error(_: ::windows::core::Error) -> CaptureError {
    error("capture_failed", "Windows could not capture this source. It may be protected, unavailable, or unsupported by the display driver.")
}
struct Dpi(::windows::Win32::UI::HiDpi::DPI_AWARENESS_CONTEXT);
impl Dpi {
    fn enter() -> Self {
        Self(unsafe { SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) })
    }
}
impl Drop for Dpi {
    fn drop(&mut self) {
        if !self.0 .0.is_null() {
            unsafe {
                SetThreadDpiAwarenessContext(self.0);
            }
        }
    }
}

unsafe extern "system" fn monitor_callback(
    monitor: HMONITOR,
    _: HDC,
    _: *mut RECT,
    data: LPARAM,
) -> BOOL {
    let sources = &mut *(data.0 as *mut Vec<Source>);
    let mut info = MONITORINFOEXW::default();
    info.monitorInfo.cbSize = std::mem::size_of::<MONITORINFOEXW>() as u32;
    if GetMonitorInfoW(monitor, &mut info as *mut _ as *mut MONITORINFO).as_bool() {
        let rect = info.monitorInfo.rcMonitor;
        let name = String::from_utf16_lossy(&info.szDevice)
            .trim_end_matches('\0')
            .to_string();
        sources.push(Source {
            id: String::new(),
            kind: SourceKind::Screen,
            title: format!("Display {} · {}", sources.len() + 1, name),
            width: (rect.right - rect.left).max(0) as u32,
            height: (rect.bottom - rect.top).max(0) as u32,
            x: rect.left,
            y: rect.top,
            primary: info.monitorInfo.dwFlags & 1 != 0,
            native_id: monitor.0 as usize,
            process_id: 0,
        });
    }
    BOOL(1)
}
fn external_window_process(process_id: u32, own_process_id: u32) -> bool {
    process_id != 0 && process_id != own_process_id
}
unsafe fn window_source(hwnd: HWND) -> Option<Source> {
    let mut pid = 0;
    GetWindowThreadProcessId(hwnd, Some(&mut pid));
    if !external_window_process(pid, std::process::id())
        || !IsWindowVisible(hwnd).as_bool()
        || IsIconic(hwnd).as_bool()
    {
        return None;
    }
    let style = GetWindowLongPtrW(hwnd, GWL_EXSTYLE) as u32;
    if style & WS_EX_TOOLWINDOW.0 != 0 {
        return None;
    }
    let mut cloaked = 0u32;
    if DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, &mut cloaked as *mut _ as _, 4).is_ok()
        && cloaked != 0
    {
        return None;
    }
    let length = GetWindowTextLengthW(hwnd);
    if length <= 0 {
        return None;
    }
    let mut title = vec![0u16; (length + 1).min(4096) as usize];
    let count = GetWindowTextW(hwnd, &mut title);
    let title = String::from_utf16_lossy(&title[..count.max(0) as usize]);
    if title.trim().is_empty() || title == "Program Manager" {
        return None;
    }
    let mut rect = RECT::default();
    GetWindowRect(hwnd, &mut rect).ok()?;
    if rect.right <= rect.left || rect.bottom <= rect.top {
        return None;
    }
    Some(Source {
        id: String::new(),
        kind: SourceKind::Window,
        title,
        width: (rect.right - rect.left) as u32,
        height: (rect.bottom - rect.top) as u32,
        x: rect.left,
        y: rect.top,
        primary: false,
        native_id: hwnd.0 as usize,
        process_id: pid,
    })
}

unsafe extern "system" fn window_callback(hwnd: HWND, data: LPARAM) -> BOOL {
    if let Some(source) = window_source(hwnd) {
        (*(data.0 as *mut Vec<Source>)).push(source);
    }
    BOOL(1)
}
pub fn discover() -> Result<Vec<Source>> {
    let _dpi = Dpi::enter();
    let mut sources = Vec::<Source>::new();
    unsafe {
        if !EnumDisplayMonitors(
            None,
            None,
            Some(monitor_callback),
            LPARAM(&mut sources as *mut _ as isize),
        )
        .as_bool()
        {
            return Err(error(
                "discovery_failed",
                "Windows displays could not be listed.",
            ));
        }
        EnumWindows(
            Some(window_callback),
            LPARAM(&mut sources as *mut _ as isize),
        )
        .map_err(native_error)?;
    }
    Ok(sources)
}

struct Apartment;
impl Drop for Apartment {
    fn drop(&mut self) {
        unsafe {
            RoUninitialize();
        }
    }
}
struct Session {
    pool: Direct3D11CaptureFramePool,
    session: GraphicsCaptureSession,
}
impl Drop for Session {
    fn drop(&mut self) {
        let _ = self.session.Close();
        let _ = self.pool.Close();
    }
}

pub fn capture(mut source: Source) -> Result<CaptureResult> {
    let _dpi = Dpi::enter();
    // Re-discover immediately; stale tokens never select a replacement window or monitor.
    let live = discover()?
        .into_iter()
        .find(|s| {
            s.kind == source.kind
                && s.native_id == source.native_id
                && s.process_id == source.process_id
                && s.title == source.title
        })
        .ok_or_else(unavailable)?;
    if source.kind == SourceKind::Screen
        && (live.x, live.y, live.width, live.height)
            != (source.x, source.y, source.width, source.height)
    {
        return Err(unavailable());
    }
    source.width = live.width;
    source.height = live.height;
    source.x = live.x;
    source.y = live.y;
    validate_size(source.width, source.height)?;
    unsafe {
        RoInitialize(RO_INIT_MULTITHREADED).map_err(native_error)?;
    }
    let _apartment = Apartment;
    if !GraphicsCaptureSession::IsSupported().map_err(native_error)? {
        return Err(error("unsupported_platform", "Windows Graphics Capture requires a supported Windows 10 version 1903 or newer display."));
    }
    let interop: IGraphicsCaptureItemInterop =
        factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>().map_err(native_error)?;
    let item: GraphicsCaptureItem = unsafe {
        match source.kind {
            SourceKind::Screen => interop.CreateForMonitor(HMONITOR(source.native_id as _)),
            SourceKind::Window => interop.CreateForWindow(HWND(source.native_id as _)),
            SourceKind::Region => {
                return Err(error(
                    "unsupported_source",
                    "Region selection is not available yet.",
                ))
            }
        }
    }
    .map_err(native_error)?;
    let size = item.Size().map_err(native_error)?;
    validate_size(size.Width.max(0) as u32, size.Height.max(0) as u32)?;
    let (mut device, mut context) = (None, None);
    unsafe {
        D3D11CreateDevice(
            None,
            D3D_DRIVER_TYPE_HARDWARE,
            HMODULE::default(),
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            None,
            D3D11_SDK_VERSION,
            Some(&mut device),
            None,
            Some(&mut context),
        )
        .map_err(native_error)?;
    }
    let device = device.ok_or_else(unavailable)?;
    let context = context.ok_or_else(unavailable)?;
    let dxgi: IDXGIDevice = device.cast().map_err(native_error)?;
    let direct: IDirect3DDevice = unsafe { CreateDirect3D11DeviceFromDXGIDevice(&dxgi) }
        .map_err(native_error)?
        .cast()
        .map_err(native_error)?;
    let pool = Direct3D11CaptureFramePool::CreateFreeThreaded(
        &direct,
        DirectXPixelFormat::B8G8R8A8UIntNormalized,
        1,
        size,
    )
    .map_err(native_error)?;
    let session = pool.CreateCaptureSession(&item).map_err(native_error)?;
    let guard = Session { pool, session };
    // Keep Windows' capture border; do not request capture-exclusion or borderless privileges.
    let (tx, rx) = mpsc::sync_channel(1);
    guard
        .pool
        .FrameArrived(&TypedEventHandler::new(
            move |sender: Ref<'_, Direct3D11CaptureFramePool>, _| {
                if let Some(pool) = sender.as_ref() {
                    if let Ok(frame) = pool.TryGetNextFrame() {
                        let _ = tx.try_send(frame);
                    }
                }
                Ok(())
            },
        ))
        .map_err(native_error)?;
    guard.session.StartCapture().map_err(native_error)?;
    let frame = rx.recv_timeout(Duration::from_secs(5)).map_err(|_| {
        error(
            "capture_timeout",
            "The source did not provide a frame. Restore the window or choose another source.",
        )
    })?;
    let frame_size = frame.ContentSize().map_err(native_error)?;
    if frame_size.Width != size.Width || frame_size.Height != size.Height {
        return Err(error(
            "source_changed",
            "The source was resized during capture. Please retake it.",
        ));
    }
    let access: IDirect3DDxgiInterfaceAccess = frame
        .Surface()
        .map_err(native_error)?
        .cast()
        .map_err(native_error)?;
    let texture: ID3D11Texture2D = unsafe { access.GetInterface() }.map_err(native_error)?;
    let mut desc = D3D11_TEXTURE2D_DESC::default();
    unsafe {
        texture.GetDesc(&mut desc);
    }
    if desc.Width < size.Width as u32 || desc.Height < size.Height as u32 {
        return Err(error(
            "source_changed",
            "The source changed size. Please retake it.",
        ));
    }
    desc.Usage = D3D11_USAGE_STAGING;
    desc.BindFlags = 0;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ.0 as u32;
    desc.MiscFlags = 0;
    let mut staging = None;
    unsafe {
        device
            .CreateTexture2D(&desc, None, Some(&mut staging))
            .map_err(native_error)?;
    }
    let staging = staging.ok_or_else(unavailable)?;
    let (width, height) = (size.Width as u32, size.Height as u32);
    let mut pixels = vec![0u8; width as usize * height as usize * 4];
    unsafe {
        context.CopyResource(&staging, &texture);
        let mut mapped = D3D11_MAPPED_SUBRESOURCE::default();
        context
            .Map(&staging, 0, D3D11_MAP_READ, 0, Some(&mut mapped))
            .map_err(native_error)?;
        if mapped.pData.is_null() || mapped.RowPitch < width * 4 {
            context.Unmap(&staging, 0);
            return Err(error(
                "invalid_frame",
                "Windows returned an incomplete frame. Please retake it.",
            ));
        }
        for y in 0..height as usize {
            let row = std::slice::from_raw_parts(
                (mapped.pData as *const u8).add(y * mapped.RowPitch as usize),
                width as usize * 4,
            );
            for (dst, src) in pixels[y * width as usize * 4..(y + 1) * width as usize * 4]
                .as_chunks_mut::<4>()
                .0
                .iter_mut()
                .zip(row.as_chunks::<4>().0.iter())
            {
                dst.copy_from_slice(&[src[2], src[1], src[0], 255]);
            }
        }
        context.Unmap(&staging, 0);
    }
    frame.Close().map_err(native_error)?;
    drop(guard); // End native capture before encoding; no recording loop survives this call.
    let mut png_bytes = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png_bytes, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|_| {
            error(
                "encoding_failed",
                "The captured image could not be prepared.",
            )
        })?;
        writer.write_image_data(&pixels).map_err(|_| {
            error(
                "encoding_failed",
                "The captured image could not be prepared.",
            )
        })?;
    }
    Ok(CaptureResult {
        source,
        width,
        height,
        format: "image/png",
        captured_at: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64,
        image_base64: base64::engine::general_purpose::STANDARD.encode(png_bytes),
    })
}

#[cfg(test)]
mod source_filter_tests {
    use super::external_window_process;
    #[test]
    fn self_and_unknown_processes_are_excluded_other_apps_remain() {
        assert!(!external_window_process(42, 42));
        assert!(!external_window_process(0, 42));
        assert!(external_window_process(100, 42));
    }
}
