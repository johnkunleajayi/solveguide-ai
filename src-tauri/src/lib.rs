mod auth;
mod capture;
mod context_library;
mod privacy;
use tauri::Manager;
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
            auth::auth_logout,
            auth::ai_request,
            auth::ai_cancel,
            context_library::library_request,
            privacy::privacy_get_state,
            privacy::privacy_set_enabled
        ])
        .setup(|app| {
            // Keep the WebView profile and local appearance storage in the official workspace.
            let workspace = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .expect("the native shell must live inside the workspace");
            let privacy = privacy::PrivacyState::new(
                workspace
                    .join(".cache")
                    .join("preferences")
                    .join("screen-share-privacy.json"),
            );
            let window =
                tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                    .data_directory(workspace.join(".cache").join("webview"))
                    .visible(false)
                    .build()?;
            // Apply/verify before first show. Failure never prevents the window opening.
            privacy.initialize(&window);
            app.manage(privacy);
            window.show()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run SolveGuide AI");
}
