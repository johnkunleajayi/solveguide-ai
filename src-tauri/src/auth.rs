use serde::{Deserialize, Serialize};
use std::{
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex as StdMutex,
    },
    time::Duration,
};
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
    epoch: AtomicU64,
    pending_ai: StdMutex<Option<(String, tokio::sync::watch::Sender<bool>)>>,
}

impl Default for AuthState {
    fn default() -> Self {
        Self {
            credentials: Mutex::new(Credentials::default()),
            epoch: AtomicU64::new(0),
            pending_ai: StdMutex::new(None),
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
pub(crate) fn error(code: &str) -> AuthError {
    AuthError {
        code: code.into(),
        message: "Sign-in could not be completed. Check backend configuration or try again.",
    }
}
pub(crate) fn authorize(window: &tauri::WebviewWindow) -> Result<()> {
    if window.label() != "main" {
        return Err(error("auth_forbidden"));
    }
    Ok(())
}

impl AuthState {
    pub(crate) fn session_epoch(&self) -> u64 {
        self.epoch.load(Ordering::SeqCst)
    }

    pub(crate) async fn library_credential_present(&self, epoch: u64) -> Result<()> {
        if self.credentials.lock().await.token.is_none() || epoch != self.session_epoch() {
            return Err(error("sign_in_required"));
        }
        Ok(())
    }

    // Only the typed native library adapter calls this. Credentials never cross IPC.
    pub(crate) async fn library_request(
        &self,
        epoch: u64,
        request: crate::context_library::Request,
    ) -> Result<serde_json::Value> {
        self.library_credential_present(epoch).await?;
        let token = self
            .credentials
            .lock()
            .await
            .token
            .clone()
            .ok_or_else(|| error("sign_in_required"))?;
        let mut builder = self
            .client
            .request(
                request.method,
                format!(
                    "http://127.0.0.1:8000/api/v1/context/documents{}",
                    request.suffix
                ),
            )
            .header("Origin", ORIGIN)
            .bearer_auth(&token)
            .timeout(Duration::from_secs(if request.suffix.ends_with("/index") {
                150
            } else {
                60
            }));
        if let Some((content_type, filename, bytes)) = request.body {
            builder = builder.header("Content-Type", content_type).body(bytes);
            if let Some(filename) = filename {
                builder = builder.header("X-Document-Filename", filename);
            }
        }
        if epoch != self.session_epoch() {
            return Err(error("sign_in_required"));
        }
        let mut response = builder
            .send()
            .await
            .map_err(|_| error("backend_unavailable"))?;
        let status = response.status().as_u16();
        if status == 401 {
            let mut credentials = self.credentials.lock().await;
            if credentials.token.as_deref() == Some(&token) {
                credentials.token = None;
            }
        }
        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| error("backend_unavailable"))?
        {
            if bytes.len() + chunk.len() > 8 * 1024 * 1024 {
                return Err(error("invalid_response"));
            }
            bytes.extend_from_slice(&chunk);
        }
        if epoch != self.session_epoch() {
            return Err(error("sign_in_required"));
        }
        let raw: serde_json::Value = if status == 204 {
            serde_json::Value::Null
        } else {
            serde_json::from_slice(&bytes).map_err(|_| error("invalid_response"))?
        };
        if status >= 400 {
            return Ok(
                serde_json::json!({"ok":false,"status":status,"error":{"code":if status == 401 { "sign_in_required" } else {raw["error"]["code"].as_str().unwrap_or("library_unavailable")}}}),
            );
        }
        Ok(serde_json::json!({"ok":true,"status":status,"data":raw}))
    }
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
                        | "sign_in_required"
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

async fn user(state: &AuthState, token: Option<&str>) -> Result<Option<PublicUser>> {
    let mut request = state.client.get(format!("{BASE}/me"));
    if let Some(token) = token {
        request = request.bearer_auth(token);
    }
    checked(request.send().await)
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
    let result = user(&state, credentials.token.as_deref()).await;
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
    user(&state, Some(&token)).await
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
    state.epoch.fetch_add(1, Ordering::SeqCst);
    cancel_ai(&state, None);
    let mut credentials = state.credentials.lock().await;
    let token = credentials.token.take();
    credentials.exchange = None;
    drop(credentials);
    if let Some(token) = token {
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
    Ok(())
}

fn cancel_ai(state: &AuthState, request_id: Option<&str>) {
    let pending = state.pending_ai.lock().unwrap_or_else(|p| p.into_inner());
    if let Some((id, sender)) = pending.as_ref() {
        if request_id.is_none_or(|requested| requested == id) {
            let _ = sender.send(true);
        }
    }
}

#[derive(Deserialize, Clone, Copy)]
#[serde(rename_all = "snake_case")]
pub enum AiKind {
    Vision,
    Answer,
}
impl AiKind {
    fn path(self) -> &'static str {
        match self {
            Self::Vision => "/api/v1/vision/question",
            Self::Answer => "/api/v1/answer",
        }
    }
    fn limit(self) -> usize {
        match self {
            Self::Vision => 14 * 1024 * 1024,
            Self::Answer => 256 * 1024,
        }
    }
}
fn validate_ai(kind: AiKind, id: &str, payload: &serde_json::Value) -> Result<()> {
    if id.is_empty()
        || id.len() > 64
        || !id.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
        || !payload.is_object()
        || serde_json::to_vec(payload)
            .map_err(|_| error("invalid_request"))?
            .len()
            > kind.limit()
    {
        return Err(error("invalid_request"));
    }
    // Backend Pydantic remains authoritative. Reject images at the answer transport too.
    if matches!(kind, AiKind::Answer)
        && payload
            .as_object()
            .is_some_and(|p| p.contains_key("image_base64") || p.contains_key("imageBase64"))
    {
        return Err(error("invalid_request"));
    }
    Ok(())
}
struct AiGuard<'a> {
    state: &'a AuthState,
    id: String,
}
impl Drop for AiGuard<'_> {
    fn drop(&mut self) {
        let mut pending = self
            .state
            .pending_ai
            .lock()
            .unwrap_or_else(|p| p.into_inner());
        if pending.as_ref().is_some_and(|(id, _)| id == &self.id) {
            *pending = None;
        }
    }
}
#[tauri::command]
pub async fn ai_cancel(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
    request_id: String,
) -> Result<()> {
    authorize(&window)?;
    cancel_ai(&state, Some(&request_id));
    Ok(())
}
#[tauri::command]
pub async fn ai_request(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
    kind: AiKind,
    request_id: String,
    payload: serde_json::Value,
) -> Result<serde_json::Value> {
    authorize(&window)?;
    request_authenticated(&state, kind, request_id, payload).await
}
async fn request_authenticated(
    state: &AuthState,
    kind: AiKind,
    request_id: String,
    payload: serde_json::Value,
) -> Result<serde_json::Value> {
    validate_ai(kind, &request_id, &payload)?;
    let epoch = state.epoch.load(Ordering::SeqCst);
    let (sender, mut cancelled) = tokio::sync::watch::channel(false);
    {
        let mut pending = state.pending_ai.lock().unwrap_or_else(|p| p.into_inner());
        if pending.is_some() {
            return Err(error("ai_busy"));
        }
        *pending = Some((request_id.clone(), sender));
    }
    let _guard = AiGuard {
        state,
        id: request_id,
    };
    if epoch != state.epoch.load(Ordering::SeqCst) {
        return Err(error("sign_in_required"));
    }
    let operation = async {
        let token = state
            .credentials
            .lock()
            .await
            .token
            .clone()
            .ok_or_else(|| error("sign_in_required"))?;
        if epoch != state.epoch.load(Ordering::SeqCst) {
            return Err(error("sign_in_required"));
        }
        let response = state
            .client
            .post(format!("http://127.0.0.1:8000{}", kind.path()))
            .header("Origin", ORIGIN)
            .bearer_auth(&token)
            .timeout(Duration::from_secs(105))
            .json(&payload)
            .send()
            .await
            .map_err(|_| error("backend_unavailable"))?;
        let status = response.status();
        let raw: serde_json::Value = response
            .json()
            .await
            .map_err(|_| error("backend_unavailable"))?;
        if status.as_u16() == 401 {
            let mut credentials = state.credentials.lock().await;
            if credentials.token.as_deref() == Some(&token) {
                credentials.token = None;
            }
        }
        // Preserve safe backend error codes; React maps messages rather than displaying raw errors.
        if !status.is_success() {
            return Ok(
                serde_json::json!({"ok":false,"status":status.as_u16(),"error": {"code":raw["error"]["code"].as_str().unwrap_or("provider_unavailable")}}),
            );
        }
        Ok(serde_json::json!({"ok":true,"status":status.as_u16(),"data":raw}))
    };
    let result = tokio::select! {
        biased;
        _ = cancelled.changed() => Err(error("request_cancelled")),
        result = operation => result,
    };
    if epoch != state.epoch.load(Ordering::SeqCst) {
        return Err(error("sign_in_required"));
    }
    result
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
    #[test]
    fn library_rejects_credentials_from_an_old_login_epoch() {
        let state = AuthState::default();
        tauri::async_runtime::block_on(async {
            state.credentials.lock().await.token = Some("a".repeat(43));
            let old = state.session_epoch();
            state.epoch.fetch_add(1, Ordering::SeqCst);
            assert!(state.library_credential_present(old).await.is_err());
            assert!(state
                .library_credential_present(state.session_epoch())
                .await
                .is_ok());
        });
    }
    #[test]
    fn ai_request_requires_native_credential_without_network() {
        let state = AuthState::default();
        let result = tauri::async_runtime::block_on(request_authenticated(
            &state,
            AiKind::Answer,
            "test-request".into(),
            serde_json::json!({"status":"detected"}),
        ));
        assert_eq!(result.unwrap_err().code, "sign_in_required");
        assert!(state.pending_ai.lock().unwrap().is_none());
    }
    #[test]
    fn ai_transport_limits_and_image_boundary_are_fixed() {
        assert_eq!(AiKind::Vision.path(), "/api/v1/vision/question");
        assert_eq!(AiKind::Answer.path(), "/api/v1/answer");
        assert!(validate_ai(
            AiKind::Answer,
            "id",
            &serde_json::json!({"image_base64":"no"})
        )
        .is_err());
        assert!(validate_ai(
            AiKind::Answer,
            "id",
            &serde_json::json!({"text":"x".repeat(256*1024)})
        )
        .is_err());
        assert!(validate_ai(AiKind::Answer, "bad/id", &serde_json::json!({})).is_err());
    }
    #[test]
    fn cancellation_is_scoped_and_guard_releases_slot() {
        let state = AuthState::default();
        let (sender, receiver) = tokio::sync::watch::channel(false);
        *state.pending_ai.lock().unwrap() = Some(("current".into(), sender));
        let guard = AiGuard {
            state: &state,
            id: "current".into(),
        };
        cancel_ai(&state, Some("old"));
        assert!(!*receiver.borrow());
        cancel_ai(&state, None);
        assert!(*receiver.borrow());
        drop(guard);
        assert!(state.pending_ai.lock().unwrap().is_none());
    }
}
