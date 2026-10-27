mod auth;
mod capture;
pub fn run() {
    tauri::Builder::default()
        .manage(auth::AuthState::default())
        .manage(std::sync::Arc::new(capture::CaptureState::default()))
        .invoke_handler(tauri::generate_handler![
            capture::list_capture_sources,
            capture::capture_source,
            auth::auth_start,
            auth::auth_me,
            auth::auth_poll,
            auth::auth_cancel,
            auth::auth_logout
        ])
        .setup(|app| {
            // Keep the WebView profile and local appearance storage in the official workspace.
            let workspace = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .expect("the native shell must live inside the workspace");
            tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .data_directory(workspace.join(".cache").join("webview"))
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run SolveGuide AI");
}
