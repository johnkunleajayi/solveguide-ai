//! Application-owned window only. Automatic show never requests foreground focus.
use super::*;
use tauri::{LogicalSize, PhysicalPosition, WebviewUrl, WebviewWindowBuilder};
pub(super) fn show(app: &tauri::AppHandle, focus: bool) -> Result<()> {
    let window = if let Some(window) = app.get_webview_window("answer-panel") {
        window
    } else {
        let workspace = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or("panel_unavailable")?;
        let window = WebviewWindowBuilder::new(
            app,
            "answer-panel",
            WebviewUrl::App("index.html?panel=monitor".into()),
        )
        .title("SolveGuide AI · Live Monitor")
        .inner_size(420.0, 440.0)
        .min_inner_size(320.0, 240.0)
        .focused(false)
        .visible(false)
        .always_on_top(true)
        .skip_taskbar(false)
        .maximizable(false)
        .data_directory(workspace.join(".cache").join("webview"))
        .on_navigation(|url| {
            matches!(url.path(), "/" | "/index.html")
                && (url.scheme() == "tauri" && url.host_str() == Some("localhost")
                    || url.scheme() == "http"
                        && (url.host_str() == Some("127.0.0.1") && url.port() == Some(1420)
                            || url.host_str() == Some("tauri.localhost") && url.port().is_none()))
        })
        .build()
        .map_err(|_| "panel_unavailable")?;
        let handle = app.clone();
        window.on_window_event(move |event| {
            if matches!(
                event,
                tauri::WindowEvent::CloseRequested { .. } | tauri::WindowEvent::Destroyed
            ) {
                handle
                    .state::<MonitorState>()
                    .0
                    .lock()
                    .unwrap_or_else(|p| p.into_inner())
                    .snapshot
                    .panel_visible = false;
            }
        });
        place(app, &window)?;
        window
    };
    // Apply and verify the current device preference on every reopen, before show.
    let status = app
        .state::<crate::privacy::PrivacyState>()
        .update(&window, None, true);
    app.state::<MonitorState>()
        .0
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .snapshot
        .privacy_available = matches!(
        status.effective_state,
        crate::privacy::EffectiveState::Enabled | crate::privacy::EffectiveState::Disabled
    );
    #[cfg(windows)]
    {
        use windows::Win32::UI::WindowsAndMessaging::{ShowWindow, SW_SHOWNOACTIVATE};
        let hwnd = window.hwnd().map_err(|_| "panel_unavailable")?;
        // SAFETY: HWND comes solely from this owned Tauri window. Documented show flag;
        // no other process/window is changed, no style hooks or input interception.
        unsafe {
            let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
        }
    }
    #[cfg(not(windows))]
    {
        window.show().map_err(|_| "panel_unavailable")?;
    }
    if focus {
        window.set_focus().map_err(|_| "panel_unavailable")?;
    }
    Ok(())
}
fn overlap(source: &Source, monitor: &tauri::Monitor) -> i64 {
    let p = monitor.position();
    let size = monitor.size();
    let width = (i64::from(source.x) + i64::from(source.width))
        .min(i64::from(p.x) + i64::from(size.width))
        - i64::from(source.x.max(p.x));
    let height = (i64::from(source.y) + i64::from(source.height))
        .min(i64::from(p.y) + i64::from(size.height))
        - i64::from(source.y.max(p.y));
    width.max(0) * height.max(0)
}
fn place(app: &tauri::AppHandle, window: &tauri::WebviewWindow) -> Result<()> {
    let source = app
        .state::<MonitorState>()
        .0
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .selection
        .as_ref()
        .map(|s| s.source.clone());
    let monitors = window
        .available_monitors()
        .map_err(|_| "panel_unavailable")?;
    let selected = source
        .and_then(|s| {
            monitors
                .iter()
                .max_by_key(|m| overlap(&s, m))
                .filter(|m| overlap(&s, m) > 0)
        })
        .or(monitors.first());
    if let Some(monitor) = selected {
        layout(window, monitor, (420.0, 440.0))?;
    }
    Ok(())
}
fn edge(x: i32, y: i32, width: u32, panel_width: u32, gap: i32) -> (i32, i32) {
    (
        (i64::from(x) + i64::from(width) - i64::from(panel_width) - i64::from(gap))
            .max(i64::from(x)) as i32,
        y.saturating_add(gap),
    )
}
fn layout(
    window: &tauri::WebviewWindow,
    monitor: &tauri::Monitor,
    desired: (f64, f64),
) -> Result<()> {
    let area = monitor.work_area();
    let scale = monitor.scale_factor();
    let gap = (16.0 * scale) as i32;
    // Move while unshown (or after an explicit size action) to the target monitor
    // before measuring the native frame at that monitor's DPI.
    window
        .set_position(PhysicalPosition::new(
            area.position.x.saturating_add(gap),
            area.position.y.saturating_add(gap),
        ))
        .map_err(|_| "panel_unavailable")?;
    let outer = window.outer_size().map_err(|_| "panel_unavailable")?;
    let inner = window.inner_size().map_err(|_| "panel_unavailable")?;
    let horizontal_frame = outer.width.saturating_sub(inner.width);
    let vertical_frame = outer.height.saturating_sub(inner.height);
    let width = f64::from(
        area.size
            .width
            .saturating_sub((gap as u32) * 2 + horizontal_frame),
    ) / scale;
    let height = f64::from(
        area.size
            .height
            .saturating_sub((gap as u32) * 2 + vertical_frame),
    ) / scale;
    window
        .set_min_size(Some(LogicalSize::new(
            width.clamp(1.0, 320.0),
            height.clamp(1.0, 240.0),
        )))
        .map_err(|_| "panel_unavailable")?;
    window
        .set_size(LogicalSize::new(
            desired.0.min(width).max(1.0),
            desired.1.min(height).max(1.0),
        ))
        .map_err(|_| "panel_unavailable")?;
    let size = window.outer_size().map_err(|_| "panel_unavailable")?;
    let (x, y) = edge(
        area.position.x,
        area.position.y,
        area.size.width,
        size.width,
        gap,
    );
    window
        .set_position(PhysicalPosition::new(x, y))
        .map_err(|_| "panel_unavailable")?;
    Ok(())
}
pub(super) fn resize(app: &tauri::AppHandle, expanded: bool) -> Result<()> {
    let window = app
        .get_webview_window("answer-panel")
        .ok_or("panel_unavailable")?;
    let monitor = window
        .current_monitor()
        .map_err(|_| "panel_unavailable")?
        .ok_or("panel_unavailable")?;
    layout(
        &window,
        &monitor,
        if expanded {
            (520.0, 680.0)
        } else {
            (420.0, 440.0)
        },
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn panel_edge_handles_negative_monitor_origins_and_scaled_gaps() {
        assert_eq!(edge(-1920, 0, 1920, 630, 24), (-654, 24));
        assert_eq!(edge(0, -1080, 1920, 420, 16), (1484, -1064));
    }
    #[test]
    fn oversized_panel_is_clamped_to_the_monitor_origin() {
        assert_eq!(edge(-800, 0, 800, 1000, 16), (-800, 16));
    }
}
