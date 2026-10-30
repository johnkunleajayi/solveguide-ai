use serde::{Deserialize, Serialize};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Mutex,
};

#[cfg(windows)]
mod windows;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    Screen,
    Window,
    Region,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Source {
    pub id: String,
    pub kind: SourceKind,
    pub title: String,
    pub width: u32,
    pub height: u32,
    pub x: i32,
    pub y: i32,
    pub primary: bool,
    #[serde(skip)]
    pub native_id: usize,
    #[serde(skip)]
    pub process_id: u32,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Request {
    pub source_id: String,
    pub kind: SourceKind,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureResult {
    pub source: Source,
    pub width: u32,
    pub height: u32,
    pub format: &'static str,
    pub captured_at: u64,
    pub image_base64: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaptureError {
    pub code: &'static str,
    pub message: &'static str,
}
pub type Result<T> = std::result::Result<T, CaptureError>;
pub fn error(code: &'static str, message: &'static str) -> CaptureError {
    CaptureError { code, message }
}
pub fn unavailable() -> CaptureError {
    error(
        "source_unavailable",
        "This source changed or is no longer available. Choose it again.",
    )
}

#[derive(Default)]
pub struct CaptureState {
    sources: Mutex<Vec<Source>>,
    busy: AtomicBool,
}
struct Busy<'a>(&'a AtomicBool);
impl Drop for Busy<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}
impl CaptureState {
    fn enter(&self) -> Result<Busy<'_>> {
        self.busy
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| {
                error(
                    "busy",
                    "Another capture operation is still finishing. Please try again.",
                )
            })?;
        Ok(Busy(&self.busy))
    }
}
fn authorize(window: &tauri::WebviewWindow) -> Result<()> {
    if window.label() != "main" {
        return Err(error(
            "not_allowed",
            "Capture is only available in the desktop workspace.",
        ));
    }
    Ok(())
}

#[tauri::command]
pub async fn list_capture_sources(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, std::sync::Arc<CaptureState>>,
) -> Result<Vec<Source>> {
    authorize(&window)?;
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let _busy = state.enter()?;
        #[cfg(windows)]
        let mut sources = windows::discover()?;
        #[cfg(not(windows))]
        let mut sources: Vec<Source> = Vec::new();
        // Opaque snapshot-scoped tokens: frontend never supplies HWNDs or paths.
        let generation = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let mut previous = state
            .sources
            .lock()
            .map_err(|_| error("native_error", "Capture sources could not be refreshed."))?;
        assign_tokens(&mut sources, &previous, generation);
        *previous = sources.clone();
        Ok(sources)
    })
    .await
    .map_err(|_| error("native_error", "Source discovery could not finish."))?
}

// Retain an unchanged source token across refresh so cancel -> retake remains valid.
fn assign_tokens(sources: &mut [Source], previous: &[Source], generation: u128) {
    for (i, source) in sources.iter_mut().enumerate() {
        source.id = previous
            .iter()
            .find(|old| {
                old.kind == source.kind
                    && old.native_id == source.native_id
                    && old.process_id == source.process_id
                    && old.title == source.title
                    && (source.kind != SourceKind::Screen
                        || (old.x, old.y, old.width, old.height)
                            == (source.x, source.y, source.width, source.height))
            })
            .map(|old| old.id.clone())
            .unwrap_or_else(|| format!("{generation}-{i}"));
    }
}

// Keep the companion out of monitor captures; restore visibility on every exit path.
struct HiddenWindow(tauri::WebviewWindow);
impl Drop for HiddenWindow {
    fn drop(&mut self) {
        let _ = self.0.show();
        let _ = self.0.set_focus();
    }
}

fn resolve(sources: &[Source], request: &Request) -> Result<Source> {
    if request.kind == SourceKind::Region {
        return Err(error(
            "unsupported_source",
            "Region selection is not available yet. Choose a screen or window.",
        ));
    }
    if request.source_id.len() > 100 {
        return Err(unavailable());
    }
    sources
        .iter()
        .find(|s| s.id == request.source_id && s.kind == request.kind)
        .cloned()
        .ok_or_else(unavailable)
}
fn validate_size(width: u32, height: u32) -> Result<()> {
    if width == 0 || height == 0 || u64::from(width) * u64::from(height) > 40_000_000 {
        return Err(error(
            "invalid_dimensions",
            "This source is empty or exceeds the 40 megapixel capture limit.",
        ));
    }
    Ok(())
}

#[tauri::command]
pub async fn capture_source(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, std::sync::Arc<CaptureState>>,
    request: Request,
) -> Result<CaptureResult> {
    authorize(&window)?;
    let state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let _busy = state.enter()?;
        let source = resolve(&state.sources.lock().map_err(|_| unavailable())?, &request)?;
        validate_size(source.width, source.height)?;
        #[cfg(windows)]
        {
            let _hidden = if source.kind == SourceKind::Screen {
                window.hide().map_err(|_| {
                    error(
                        "window_error",
                        "SolveGuide could not prepare the display for capture.",
                    )
                })?;
                let guard = HiddenWindow(window);
                std::thread::sleep(std::time::Duration::from_millis(180));
                Some(guard)
            } else {
                None
            };
            windows::capture(source)
        }
        #[cfg(not(windows))]
        {
            Err(error(
                "unsupported_platform",
                "Native capture currently requires Windows 10 version 1903 or later.",
            ))
        }
    })
    .await
    .map_err(|_| {
        error(
            "native_error",
            "Capture could not finish. Please try again.",
        )
    })?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dimensions_are_bounded() {
        assert!(validate_size(0, 2).is_err());
        assert!(validate_size(10000, 10000).is_err());
        assert!(validate_size(3840, 2160).is_ok());
    }
    #[test]
    fn missing_and_region_fail_closed() {
        assert_eq!(
            resolve(
                &[],
                &Request {
                    source_id: "stale".into(),
                    kind: SourceKind::Screen
                }
            )
            .unwrap_err()
            .code,
            "source_unavailable"
        );
        assert_eq!(
            resolve(
                &[],
                &Request {
                    source_id: "".into(),
                    kind: SourceKind::Region
                }
            )
            .unwrap_err()
            .code,
            "unsupported_source"
        );
    }
    fn fixture() -> Source {
        Source {
            id: "existing-token".into(),
            kind: SourceKind::Screen,
            title: "Display".into(),
            width: 1920,
            height: 1080,
            x: -1920,
            y: 0,
            primary: false,
            native_id: 42,
            process_id: 0,
        }
    }
    #[test]
    fn refresh_retains_only_unchanged_source_tokens() {
        let old = fixture();
        let mut fresh = vec![fixture()];
        fresh[0].id.clear();
        assign_tokens(&mut fresh, std::slice::from_ref(&old), 1);
        assert_eq!(fresh[0].id, old.id);
        fresh[0].x = 0;
        assign_tokens(&mut fresh, &[old], 2);
        assert_eq!(fresh[0].id, "2-0");
    }
    #[test]
    fn request_requires_matching_type_and_native_token() {
        let source = fixture();
        assert!(resolve(
            std::slice::from_ref(&source),
            &Request {
                source_id: source.id.clone(),
                kind: SourceKind::Screen
            }
        )
        .is_ok());
        assert!(resolve(
            std::slice::from_ref(&source),
            &Request {
                source_id: source.id.clone(),
                kind: SourceKind::Window
            }
        )
        .is_err());
    }
    #[test]
    fn busy_guard_releases() {
        let s = CaptureState::default();
        let guard = s.enter().unwrap();
        assert!(s.enter().is_err());
        drop(guard);
        assert!(s.enter().is_ok());
    }
}

// One bounded frame; no image or source handles are persisted. Live sampling never
// uses HiddenWindow, so it cannot restore or focus the main application.
pub(crate) struct Frame {
    pub source: Source,
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
}
impl Frame {
    pub(crate) fn encode(self) -> Result<CaptureResult> {
        use base64::Engine;
        let mut bytes = Vec::new();
        {
            let mut encoder = png::Encoder::new(&mut bytes, self.width, self.height);
            encoder.set_color(png::ColorType::Rgba);
            encoder.set_depth(png::BitDepth::Eight);
            let mut writer = encoder
                .write_header()
                .map_err(|_| error("encoding_failed", "Could not prepare the image."))?;
            writer
                .write_image_data(&self.pixels)
                .map_err(|_| error("encoding_failed", "Could not prepare the image."))?;
        }
        if bytes.len() > 10 * 1024 * 1024 {
            return Err(error(
                "image_too_large",
                "Choose a smaller source (10 MiB PNG limit).",
            ));
        }
        Ok(CaptureResult {
            source: self.source,
            width: self.width,
            height: self.height,
            format: "image/png",
            captured_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            image_base64: base64::engine::general_purpose::STANDARD.encode(bytes),
        })
    }
}
pub(crate) fn monitor_source(state: &CaptureState, request: &Request) -> Result<Source> {
    resolve(&state.sources.lock().map_err(|_| unavailable())?, request)
}
pub(crate) fn sample(
    state: &CaptureState,
    source: Source,
    cancelled: &AtomicBool,
    target: &MonitorTarget,
) -> Result<Frame> {
    let _busy = state.enter()?;
    #[cfg(windows)]
    {
        windows::capture_frame(source, Some(cancelled), Some(&target.target))
    }
    #[cfg(not(windows))]
    {
        let _ = (source, cancelled, target);
        Err(error(
            "unsupported_platform",
            "Live Monitor requires Windows.",
        ))
    }
}

// An identity reference, not a running capture session or frame buffer.
pub(crate) struct MonitorTarget {
    #[cfg(windows)]
    target: windows::Target,
}
impl MonitorTarget {
    pub(crate) fn closed(&self) -> bool {
        #[cfg(windows)]
        {
            self.target.is_closed()
        }
        #[cfg(not(windows))]
        {
            true
        }
    }
}
pub(crate) fn monitor_target(source: &Source) -> Result<MonitorTarget> {
    #[cfg(windows)]
    {
        Ok(MonitorTarget {
            target: windows::Target::new(source)?,
        })
    }
    #[cfg(not(windows))]
    {
        let _ = source;
        Err(error(
            "unsupported_platform",
            "Live Monitor requires Windows.",
        ))
    }
}
