mod auth;
mod backend;
mod capture;
mod context_library;
mod diagnostics;
mod learning;
mod monitor;
mod privacy;
use tauri::Manager;
pub fn run() {
    tauri::Builder::default()
        .manage(monitor::MonitorState::default())
        .manage(std::sync::Arc::new(capture::CaptureState::default()))
        .invoke_handler(tauri::generate_handler![
            capture::list_capture_sources,
            capture::capture_source,
            auth::auth_start,
            auth::auth_me,
            auth::auth_poll,
            auth::auth_cancel,
            auth::auth_logout,
            auth::ai_request,
            auth::ai_cancel,
            context_library::library_request,
            learning::session_request,
            monitor::monitor_control,
            privacy::privacy_get_state,
            privacy::privacy_set_enabled
        ])
        .on_window_event(|window, event| {
            if window.label() == "main"
                && matches!(event, tauri::WindowEvent::CloseRequested { .. })
            {
                window.state::<monitor::MonitorState>().stop(
                    window.app_handle(),
                    false,
                    "stopped",
                    "Application closed.",
                );
                window.state::<backend::BackendState>().stop();
                if let Some(panel) = window.app_handle().get_webview_window("answer-panel") {
                    let _ = panel.destroy();
                }
            }
        })
        .setup(|app| {
            let backend =
                backend::BackendState::launch(app.handle()).map_err(std::io::Error::other)?;
            let auth =
                auth::AuthState::with_backend(backend.endpoint()).map_err(std::io::Error::other)?;
            app.manage(backend);
            app.manage(auth);
            let runtime = backend::runtime_dir(app.handle()).map_err(std::io::Error::other)?;
            // Keep the WebView profile and local appearance storage in the official workspace.
            let privacy = privacy::PrivacyState::new(
                runtime
                    .join("preferences")
                    .join("screen-share-privacy.json"),
            );
            let window =
                tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                    .data_directory(runtime.join("webview"))
                    .visible(false)
                    .build()?;
            // Apply/verify before first show. Failure never prevents the window opening.
            privacy.initialize(&window);
            app.manage(privacy);
            window.show()?;
            diagnostics::startup();
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build SolveGuide AI")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                diagnostics::emit("application_stopped", "INFO", None, serde_json::json!({}));
            }
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                app.state::<monitor::MonitorState>().stop(
                    app,
                    false,
                    "stopped",
                    "Application closed.",
                );
                app.state::<backend::BackendState>().stop();
            }
        });
}
