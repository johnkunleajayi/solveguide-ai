use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::Mutex;

const BASE: &str = "http://127.0.0.1:8000/api/v1/auth";
const ORIGIN: &str = "http://tauri.localhost";

#[derive(Default)]
struct Credentials {
    token: Option<String>,
    exchange: Option<String>,
}

pub struct AuthState {
    credentials: Mutex<Credentials>,
    client: reqwest::Client,
}

impl Default for AuthState {
    fn default() -> Self {
        Self {
            credentials: Mutex::new(Credentials::default()),
            client: reqwest::Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .connect_timeout(Duration::from_secs(3))
                .timeout(Duration::from_secs(12))
                .build()
                .expect("local authentication HTTP client"),
        }
    }
}

#[derive(Serialize, Debug)]
pub struct AuthError {
    code: String,
    message: &'static str,
}
type Result<T> = std::result::Result<T, AuthError>;
fn error(code: &str) -> AuthError {
    AuthError {
        code: code.into(),
        message: "Sign-in could not be completed. Check backend configuration or try again.",
    }
}
fn authorize(window: &tauri::WebviewWindow) -> Result<()> {
    if window.label() != "main" {
        return Err(error("auth_forbidden"));
    }
    Ok(())
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PublicUser {
    id: String,
    email: String,
    email_verified: bool,
    display_name: String,
    avatar_url: Option<String>,
}
#[derive(Deserialize)]
struct Start {
    authorization_url: String,
    exchange_secret: String,
}
#[derive(Deserialize)]
struct Exchange {
    status: String,
    session_token: Option<String>,
}

async fn checked(
    response: std::result::Result<reqwest::Response, reqwest::Error>,
) -> Result<reqwest::Response> {
    let response = response.map_err(|_| error("backend_unavailable"))?;
    if !response.status().is_success() {
        let code = response
            .json::<serde_json::Value>()
            .await
            .ok()
            .and_then(|v| v["error"]["code"].as_str().map(str::to_owned))
            .filter(|s| {
                matches!(
                    s.as_str(),
                    "database_not_configured"
                        | "database_schema"
                        | "database_unavailable"
                        | "auth_not_configured"
                        | "session_expired"
                        | "session_revoked"
                        | "invalid_session"
                        | "invalid_exchange"
                        | "google_sign_in_failed"
                )
            })
            .unwrap_or_else(|| "auth_unavailable".into());
        return Err(error(&code));
    }
    Ok(response)
}
fn valid_secret(value: &str) -> bool {
    value.len() == 43
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
}
fn valid_google_url(value: &str) -> bool {
    reqwest::Url::parse(value).is_ok_and(|url| {
        url.scheme() == "https"
            && url.host_str() == Some("accounts.google.com")
            && url.path() == "/o/oauth2/v2/auth"
            && url.username().is_empty()
            && url.password().is_none()
            && url.port().is_none()
    })
}

#[cfg(windows)]
fn open_browser(url: &str) -> Result<()> {
    use windows::core::PCWSTR;
    use windows::Win32::UI::Shell::ShellExecuteW;
    use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    let wide: Vec<u16> = url.encode_utf16().chain(Some(0)).collect();
    let operation: Vec<u16> = "open".encode_utf16().chain(Some(0)).collect();
    let result = unsafe {
        ShellExecuteW(
            None,
            PCWSTR(operation.as_ptr()),
            PCWSTR(wide.as_ptr()),
            None,
            None,
            SW_SHOWNORMAL,
        )
    };
    if result.0 as isize <= 32 {
        return Err(error("browser_unavailable"));
    }
    Ok(())
}
#[cfg(not(windows))]
fn open_browser(_: &str) -> Result<()> {
    Err(error("browser_unavailable"))
}

#[tauri::command]
pub async fn auth_start(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
) -> Result<()> {
    authorize(&window)?;
    let mut credentials = state.credentials.lock().await;
    let response = checked(
        state
            .client
            .post(format!("{BASE}/desktop/start"))
            .header("Origin", ORIGIN)
            .json(&serde_json::json!({}))
            .send()
            .await,
    )
    .await?;
    let start: Start = response
        .json()
        .await
        .map_err(|_| error("invalid_auth_response"))?;
    if !valid_google_url(&start.authorization_url) || !valid_secret(&start.exchange_secret) {
        return Err(error("invalid_auth_response"));
    }
    open_browser(&start.authorization_url)?;
    credentials.exchange = Some(start.exchange_secret);
    Ok(())
}

async fn user(state: &AuthState, token: &str) -> Result<Option<PublicUser>> {
    checked(
        state
            .client
            .get(format!("{BASE}/me"))
            .bearer_auth(token)
            .send()
            .await,
    )
    .await?
    .json()
    .await
    .map_err(|_| error("invalid_auth_response"))
}

#[tauri::command]
pub async fn auth_me(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
) -> Result<Option<PublicUser>> {
    authorize(&window)?;
    let mut credentials = state.credentials.lock().await;
    let Some(token) = credentials.token.as_deref() else {
        return Ok(None);
    };
    let result = user(&state, token).await;
    if result.as_ref().is_err_and(|e| {
        matches!(
            e.code.as_str(),
            "session_expired" | "session_revoked" | "invalid_session"
        )
    }) {
        credentials.token = None;
    }
    result
}

#[tauri::command]
pub async fn auth_poll(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
) -> Result<Option<PublicUser>> {
    authorize(&window)?;
    let mut credentials = state.credentials.lock().await;
    let Some(secret) = credentials.exchange.as_deref() else {
        return Ok(None);
    };
    let response = checked(
        state
            .client
            .post(format!("{BASE}/desktop/exchange"))
            .header("Origin", ORIGIN)
            .json(&serde_json::json!({"secret":secret}))
            .send()
            .await,
    )
    .await?;
    let exchange: Exchange = response
        .json()
        .await
        .map_err(|_| error("invalid_auth_response"))?;
    if exchange.status == "pending" {
        return Ok(None);
    }
    let token = exchange
        .session_token
        .filter(|s| valid_secret(s))
        .ok_or_else(|| error("invalid_auth_response"))?;
    credentials.token = Some(token.clone());
    credentials.exchange = None;
    user(&state, &token).await
}

#[tauri::command]
pub async fn auth_cancel(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
) -> Result<()> {
    authorize(&window)?;
    let mut credentials = state.credentials.lock().await;
    if let Some(secret) = credentials.exchange.take() {
        let _ = state
            .client
            .post(format!("{BASE}/desktop/cancel"))
            .header("Origin", ORIGIN)
            .json(&serde_json::json!({"secret": secret}))
            .send()
            .await;
    }
    // A poll may have completed just before cancellation. Revoke that local login too.
    if let Some(token) = credentials.token.take() {
        let _ = state
            .client
            .post(format!("{BASE}/logout"))
            .header("Origin", ORIGIN)
            .bearer_auth(token)
            .json(&serde_json::json!({}))
            .send()
            .await;
    }
    Ok(())
}

#[tauri::command]
pub async fn auth_logout(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
) -> Result<()> {
    authorize(&window)?;
    let mut credentials = state.credentials.lock().await;
    if let Some(token) = credentials.token.as_deref() {
        checked(
            state
                .client
                .post(format!("{BASE}/logout"))
                .header("Origin", ORIGIN)
                .bearer_auth(token)
                .json(&serde_json::json!({}))
                .send()
                .await,
        )
        .await?;
    }
    *credentials = Credentials::default();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn browser_destination_is_restricted() {
        assert!(valid_google_url(
            "https://accounts.google.com/o/oauth2/v2/auth?state=test"
        ));
        for url in [
            "https://accounts.google.com.evil.test/o/oauth2/v2/auth",
            "file:///test",
            "http://accounts.google.com/o/oauth2/v2/auth",
            "https://user@accounts.google.com/o/oauth2/v2/auth",
            "https://accounts.google.com/other",
        ] {
            assert!(!valid_google_url(url));
        }
    }
    #[test]
    fn secrets_are_bounded_and_opaque() {
        assert!(valid_secret(&"a".repeat(43)));
        assert!(!valid_secret(&"a".repeat(44)));
        assert!(!valid_secret(&"/".repeat(43)));
    }
}
