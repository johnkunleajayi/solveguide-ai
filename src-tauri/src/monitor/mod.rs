//! Explicit, ephemeral native monitor. No database, credential IPC or capture history.
mod filter;
mod panel;
mod pipeline;
mod validation;
use crate::{
    auth::{self, AiKind, AuthState},
    capture::{self, Source},
    context_library::Request,
    diagnostics::{self as diag, Trace},
};
use filter::{Gate, Signature};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc, Mutex,
};
use std::time::{Duration, Instant};
use tauri::Manager;

type Result<T> = std::result::Result<T, String>;
const SESSION_CHECK_TIMEOUT: Duration = validation::DEADLINE;
#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Config {
    interval_ms: u64,
    stabilize_ms: u64,
    request_interval_seconds: u64,
    max_questions: u32,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            interval_ms: 1500,
            stabilize_ms: 3000,
            request_interval_seconds: 30,
            max_questions: 60,
        }
    }
}
impl Config {
    fn validate(&self) -> Result<()> {
        if !(1000..=5000).contains(&self.interval_ms)
            || !(2000..=10000).contains(&self.stabilize_ms)
            || !(30..=120).contains(&self.request_interval_seconds)
            || !(1..=60).contains(&self.max_questions)
        {
            return Err("invalid_monitor_configuration".into());
        }
        Ok(())
    }
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    phase: String,
    generation: u64,
    question_number: u32,
    source: Option<Source>,
    mode: String,
    document_ids: Vec<String>,
    observation: Option<Value>,
    answer: Option<Value>,
    message: String,
    panel_visible: bool,
    privacy_available: bool,
}
impl Default for Snapshot {
    fn default() -> Self {
        Self {
            phase: "stopped".into(),
            generation: 0,
            question_number: 0,
            source: None,
            mode: "general".into(),
            document_ids: vec![],
            observation: None,
            answer: None,
            message: "Monitoring starts only when you explicitly activate it.".into(),
            panel_visible: false,
            privacy_available: true,
        }
    }
}
struct Cancellation {
    flag: AtomicBool,
    wake: tokio::sync::Notify,
}
impl Cancellation {
    fn new() -> Self {
        Self {
            flag: AtomicBool::new(false),
            wake: tokio::sync::Notify::new(),
        }
    }
    fn cancel(&self) {
        self.flag.store(true, Ordering::Release);
        self.wake.notify_waiters();
    }
    fn stopped(&self) -> bool {
        self.flag.load(Ordering::Acquire)
    }
}
#[derive(Clone)]
struct Selection {
    source: Source,
    session_id: String,
    revision: u32,
    epoch: u64,
    config: Config,
    context_signature: Option<String>,
    target: Option<Arc<capture::MonitorTarget>>,
    trace_id: String,
    checks: Arc<validation::Checks>,
}
#[derive(Default)]
struct Inner {
    run: u64,
    snapshot: Snapshot,
    selection: Option<Selection>,
    cancel: Option<Arc<Cancellation>>,
    worker: Option<tokio::task::AbortHandle>,
}
pub struct MonitorState(
    Mutex<Inner>,
    AtomicU64,
    Arc<tokio::sync::Semaphore>,
    tokio::sync::Notify,
);
impl Default for MonitorState {
    fn default() -> Self {
        Self(
            Mutex::new(Inner::default()),
            AtomicU64::new(0),
            Arc::new(tokio::sync::Semaphore::new(1)),
            tokio::sync::Notify::new(),
        )
    }
}
impl MonitorState {
    pub(crate) fn log_action(&self, action: &str, reason: &str) {
        let inner = self.0.lock().unwrap_or_else(|p| p.into_inner());
        if let Some(selection) = &inner.selection {
            let trace = Trace::session(&selection.trace_id, None);
            diag::emit(
                "monitor_action",
                "INFO",
                Some(&trace),
                json!({"action":action,"reason":reason,"run":inner.run}),
            );
        }
    }

    pub(crate) fn set_privacy_available(&self, value: bool) {
        self.0
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .snapshot
            .privacy_available = value;
    }
    pub(crate) fn stop(&self, app: &tauri::AppHandle, keep: bool, phase: &str, message: &str) {
        self.finish(app, None, keep, phase, message);
    }
    fn stop_run(&self, app: &tauri::AppHandle, run: u64, keep: bool, phase: &str, message: &str) {
        self.finish(app, Some(run), keep, phase, message);
    }
    fn finish(
        &self,
        app: &tauri::AppHandle,
        expected: Option<u64>,
        keep: bool,
        phase: &str,
        message: &str,
    ) {
        // Never hold monitor state while dispatching native window events.
        let panel = if keep {
            None
        } else {
            app.get_webview_window("answer-panel")
        };
        if self.reset(expected, keep, phase, message) {
            if let Some(panel) = panel {
                let _ = panel.destroy();
            }
        }
    }
    fn reset(&self, expected: Option<u64>, keep: bool, phase: &str, message: &str) -> bool {
        let mut inner = self.0.lock().unwrap_or_else(|p| p.into_inner());
        if expected.is_some_and(|run| run != inner.run) {
            return false;
        }
        if let Some(selection) = &inner.selection {
            let trace = Trace::session(&selection.trace_id, None);
            diag::emit(
                "monitor_transition",
                "INFO",
                Some(&trace),
                json!({"outcome":phase,"reason":"state_transition","run":inner.run}),
            );
        }
        self.1.fetch_add(1, Ordering::SeqCst);
        self.3.notify_waiters();
        inner.run += 1;
        if let Some(cancel) = inner.cancel.take() {
            cancel.cancel();
        }
        if let Some(worker) = inner.worker.take() {
            worker.abort();
        }
        inner.snapshot.phase = phase.into();
        inner.snapshot.message = message.into();
        inner.snapshot.generation += 1;
        inner.snapshot.observation = None;
        inner.snapshot.answer = None;
        if !keep {
            inner.selection = None;
            inner.snapshot = Snapshot {
                message: message.into(),
                generation: inner.snapshot.generation,
                ..Snapshot::default()
            };
        }
        true
    }
    fn current(&self, run: u64, generation: u64) -> bool {
        let inner = self.0.lock().unwrap_or_else(|p| p.into_inner());
        inner.run == run
            && inner.snapshot.generation == (run << 32) + generation
            && inner.cancel.as_ref().is_some_and(|c| !c.stopped())
    }
    fn publish(&self, run: u64, generation: u64, action: impl FnOnce(&mut Snapshot)) -> bool {
        let mut inner = self.0.lock().unwrap_or_else(|p| p.into_inner());
        if inner.run != run
            || inner.snapshot.generation != (run << 32) + generation
            || inner.cancel.as_ref().is_none_or(|c| c.stopped())
        {
            if let Some(selection) = &inner.selection {
                let trace = Trace::session(&selection.trace_id, None);
                diag::emit(
                    "stale_result_suppressed",
                    "DEBUG",
                    Some(&trace),
                    json!({"run":run,"generation":generation,"reason":"run_or_generation_changed"}),
                );
            }
            return false;
        }
        action(&mut inner.snapshot);
        true
    }
    fn change(&self, run: u64, action: impl FnOnce(&mut Snapshot)) -> bool {
        let mut inner = self.0.lock().unwrap_or_else(|p| p.into_inner());
        if inner.run != run || inner.cancel.as_ref().is_none_or(|c| c.stopped()) {
            return false;
        }
        action(&mut inner.snapshot);
        true
    }
}
#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    Snapshot {},
    Start {
        source_id: String,
        source_kind: capture::SourceKind,
        session_id: String,
        revision: u32,
        config: Option<Config>,
    },
    Pause {},
    Resume {},
    Stop {
        reason: Option<StopReason>,
    },
    ShowPanel {},
    HidePanel {},
    FocusPanel {},
    Expand {
        expanded: bool,
    },
}
#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StopReason {
    UserRequested,
    SourceChanged,
    WorkspaceDisposed,
}
impl StopReason {
    fn code(&self) -> &'static str {
        match self {
            Self::UserRequested => "user_requested",
            Self::SourceChanged => "source_changed",
            Self::WorkspaceDisposed => "workspace_disposed",
        }
    }
}
fn allowed(window: &tauri::WebviewWindow) -> Result<()> {
    if ["main", "answer-panel"].contains(&window.label()) {
        Ok(())
    } else {
        Err("not_allowed".into())
    }
}
async fn active(app: &tauri::AppHandle, selection: &Selection) -> Result<Value> {
    active_for(app, selection, None).await
}
async fn active_for(
    app: &tauri::AppHandle,
    selection: &Selection,
    candidate: Option<(u64, u64)>,
) -> Result<Value> {
    let trace = Trace::session(&selection.trace_id, candidate);
    let started = Instant::now();
    diag::emit(
        "session_check_started",
        "DEBUG",
        Some(&trace),
        json!({"deadline_ms":SESSION_CHECK_TIMEOUT.as_millis() as u64}),
    );
    let state = app.state::<MonitorState>();
    let invalidated = state.3.notified();
    tokio::pin!(invalidated);
    invalidated.as_mut().enable();
    let result = validation::cancellable(async {
        let auth = app.state::<AuthState>();
        let auth_started=Instant::now();
        let credential=auth.library_credential_present(selection.epoch).await;
        diag::emit("native_authentication_validation",if credential.is_ok(){"DEBUG"}else{"WARNING"},Some(&trace),json!({"duration_ms":auth_started.elapsed().as_millis() as u64,"outcome":if credential.is_ok(){"validated"}else{"rejected"},"error_code":credential.as_ref().err().map(|e|e.code.as_str())}));
        credential.map_err(|e|e.code)?;
        let (response, coalesced) = selection.checks.run(|| async {
            auth.learning_request_traced(selection.epoch, Request {
                method: reqwest::Method::POST,
                suffix: format!("/sessions/{}/validate", selection.session_id),
                body: Some(("application/json", None, serde_json::to_vec(&json!({"revision":selection.revision})).map_err(|_| "invalid_request".to_owned())?)),
            }, &trace).await.map_err(|e| e.code)
        }).await?;
        if coalesced { diag::emit("session_check_coalesced", "DEBUG", Some(&trace), json!({"reason":"overlapping_validation"})); }
        if response["ok"] != true {
            return Err(response["error"]["code"]
                .as_str()
                .unwrap_or("backend_http_error")
                .to_owned());
        }
        let data = &response["data"];
        if data.is_null() {
            return Err("session_missing".into());
        }
        if data["id"].as_str() != Some(&selection.session_id) {
            return Err("session_replaced".into());
        }
        if data["revision"].as_u64() != Some(u64::from(selection.revision)) {
            return Err("session_revision_mismatch".into());
        }
        if data["status"] != "active" {
            return Err("session_not_active".into());
        }
        if data["ready"] != true {
            return Err("session_materials_not_ready".into());
        }
        if data["mode"] != "general"
            && data["documents"].as_array().is_none_or(|docs| {
                docs.is_empty()
                    || docs
                        .iter()
                        .any(|d| d["index_generation"].as_str().is_none())
            })
        {
            return Err("session_metadata_outdated".into());
        }
        if selection
            .context_signature
            .as_ref()
            .is_some_and(|expected| *expected != context_signature(data))
        {
            return Err("session_materials_changed".into());
        }
        Ok(data.clone())
    }, invalidated).await;
    let code = result.as_ref().err().map(String::as_str);
    diag::emit(
        "session_check_finished",
        if code.is_some_and(|c| c != "request_cancelled") {
            "WARNING"
        } else {
            "DEBUG"
        },
        Some(&trace),
        json!({"duration_ms":started.elapsed().as_millis() as u64,"deadline_ms":SESSION_CHECK_TIMEOUT.as_millis() as u64,"outcome":if code.is_some(){"failed"}else{"active"},"error_code":code,"error_category":code.map(diag::category)}),
    );
    result
}
fn session_message(code: &str) -> &'static str {
    match code {
        "session_check_timeout"=>"Session validation exceeded its 12-second deadline. Monitoring stopped. Check diagnostics and start explicitly.",
        "backend_timeout"=>"The backend request timed out. Monitoring stopped; check diagnostics and retry explicitly.",
        "backend_connection_failed"|"backend_unavailable"=>"The backend connection failed. Monitoring stopped; check the backend terminal.",
        "session_expired"|"session_revoked"|"invalid_session"|"sign_in_required"=>"Authentication expired, was revoked, or is unavailable. Sign in again before monitoring.",
        "session_revision_mismatch"|"preparation_changed"=>"The session revision changed. Recover its current configuration before monitoring.",
        "session_missing"|"session_replaced"|"session_not_active"=>"The selected learning session ended or was replaced. Recover an active session before monitoring.",
        "database_unavailable"|"database_schema"|"database_not_configured"=>"The account/session database check failed. Review backend diagnostics before restarting monitoring.",
        "session_materials_changed"|"session_materials_not_ready"=>"Session materials changed or are not ready. Review the preparation before monitoring.",
        _=>"Session validation failed. Monitoring stopped; use the diagnostic trace to identify the cause.",
    }
}
#[tauri::command]
pub async fn monitor_control(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    operation: Operation,
) -> Result<Snapshot> {
    allowed(&window)?;
    let state = app.state::<MonitorState>();
    match operation {
        Operation::Start {
            source_id,
            source_kind,
            session_id,
            revision,
            config,
        } => {
            if window.label() != "main" {
                return Err("not_allowed".into());
            }
            crate::context_library::identifier(&session_id).map_err(|_| "invalid_session")?;
            let config = config.unwrap_or_default();
            config.validate()?;
            let source = capture::monitor_source(
                &app.state::<Arc<capture::CaptureState>>(),
                &capture::Request {
                    source_id,
                    kind: source_kind,
                },
            )
            .map_err(|e| e.code.to_string())?;
            begin(
                &app,
                Selection {
                    source,
                    session_id,
                    revision,
                    epoch: app.state::<AuthState>().session_epoch(),
                    config,
                    context_signature: None,
                    target: None,
                    trace_id: String::new(),
                    checks: Arc::new(validation::Checks::default()),
                },
            )
            .await?;
        }
        Operation::Resume {} => {
            let selection = {
                let inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
                if !["paused", "error"].contains(&inner.snapshot.phase.as_str()) {
                    return Err("not_paused".into());
                }
                inner.selection.clone().ok_or("source_required")?
            };
            state.log_action("resume", "user_requested");
            // A newly validated run may accept new index generations, but never a new source/session.
            begin(
                &app,
                Selection {
                    context_signature: None,
                    ..selection
                },
            )
            .await?;
        }
        Operation::Pause {} => {
            state.log_action("pause", "user_requested");
            state.stop(
                &app,
                true,
                "paused",
                "Paused. No new capture or provider requests. Resume explicitly when ready.",
            )
        }
        Operation::Stop { reason } => {
            state.log_action("stop", reason.unwrap_or(StopReason::UserRequested).code());
            state.stop(
                &app,
                false,
                "stopped",
                "Monitoring stopped. Live content cleared.",
            )
        }
        Operation::ShowPanel {} | Operation::FocusPanel {} => {
            if window.label() != "main" {
                return Err("not_allowed".into());
            }
            let (run, selection) = {
                let inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
                (inner.run, inner.selection.clone().ok_or("source_required")?)
            };
            active(&app, &selection).await?;
            if state.0.lock().unwrap_or_else(|p| p.into_inner()).run != run {
                return Err("request_cancelled".into());
            }
            panel::show(&app, matches!(operation, Operation::FocusPanel {}))?;
            let current = {
                let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
                if inner.run == run {
                    inner.snapshot.panel_visible = true;
                    true
                } else {
                    false
                }
            };
            if !current {
                let stopped = state
                    .0
                    .lock()
                    .unwrap_or_else(|p| p.into_inner())
                    .selection
                    .is_none();
                if stopped {
                    if let Some(panel) = app.get_webview_window("answer-panel") {
                        let _ = panel.destroy();
                    }
                }
                return Err("request_cancelled".into());
            }
        }
        Operation::HidePanel {} => {
            if let Some(panel) = app.get_webview_window("answer-panel") {
                let _ = panel.destroy();
            }
            state
                .0
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .snapshot
                .panel_visible = false;
        }
        Operation::Expand { expanded } => panel::resize(&app, expanded)?,
        Operation::Snapshot {} => {}
    }
    let (run, selection) = {
        let inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
        (inner.run, inner.selection.clone())
    };
    if let Some(selection) = selection {
        let auth = app.state::<AuthState>();
        let credential = auth.library_credential_present(selection.epoch).await;
        if credential.is_err() {
            diag::emit(
                "monitor_authentication_failed",
                "WARNING",
                Some(&Trace::session(&selection.trace_id, None)),
                json!({"error_code":"sign_in_required","error_category":"authentication","run":run}),
            );
            state.stop_run(
                &app,
                run,
                false,
                "stopped",
                "Sign in again before monitoring.",
            );
        }
    }
    let snapshot = state
        .0
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .snapshot
        .clone();
    Ok(snapshot)
}

async fn begin(app: &tauri::AppHandle, mut selection: Selection) -> Result<()> {
    selection.trace_id = diag::activation_id();
    selection.checks = Arc::new(validation::Checks::default());
    let trace = Trace::session(&selection.trace_id, None);
    diag::emit(
        "monitor_start",
        "INFO",
        Some(&trace),
        json!({"outcome":"requested"}),
    );
    let result = begin_inner(app, selection).await;
    if let Err(code) = &result {
        diag::emit(
            "monitor_start_failed",
            "WARNING",
            Some(&trace),
            json!({"error_code":code,"error_category":diag::category(code)}),
        );
    }
    result
}
async fn begin_inner(app: &tauri::AppHandle, mut selection: Selection) -> Result<()> {
    let state = app.state::<MonitorState>();
    let intent = state.1.fetch_add(1, Ordering::SeqCst) + 1;
    let invalidated = state.3.notified();
    tokio::pin!(invalidated);
    invalidated.as_mut().enable();
    if state.1.load(Ordering::SeqCst) != intent {
        return Err("request_cancelled".into());
    }
    let trace = Trace::session(&selection.trace_id, None);
    let config = tokio::select! { biased;
        _ = &mut invalidated => return Err("request_cancelled".into()),
        config = active(app, &selection) => config?,
    };
    if state.1.load(Ordering::SeqCst) != intent {
        return Err("request_cancelled".into());
    }
    if selection.target.is_none() {
        let source = selection.source.clone();
        selection.target = Some(Arc::new(
            tauri::async_runtime::spawn_blocking(move || capture::monitor_target(&source))
                .await
                .map_err(|_| "source_unavailable")?
                .map_err(|e| e.code.to_owned())?,
        ));
    }
    if selection
        .target
        .as_ref()
        .is_none_or(|target| target.closed())
    {
        return Err("source_unavailable".into());
    }
    selection.context_signature = Some(context_signature(&config));
    let (run, cancel) = {
        let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
        if state.1.load(Ordering::SeqCst) != intent {
            return Err("request_cancelled".into());
        }
        if inner.cancel.as_ref().is_some_and(|c| !c.stopped()) {
            return Err("already_monitoring".into());
        }
        inner.run += 1;
        let cancel = Arc::new(Cancellation::new());
        inner.cancel = Some(cancel.clone());
        inner.selection = Some(selection.clone());
        inner.snapshot = Snapshot {
            phase: "monitoring".into(),
            source: Some(selection.source.clone()),
            mode: config["mode"].as_str().unwrap_or("general").into(),
            document_ids: config["document_ids"]
                .as_array()
                .map(|v| {
                    v.iter()
                        .filter_map(|v| v.as_str().map(str::to_owned))
                        .collect()
                })
                .unwrap_or_default(),
            message: "Monitoring selected source. Waiting for stable content.".into(),
            ..Snapshot::default()
        };
        (inner.run, cancel)
    };
    if let Err(e) = panel::show(app, false) {
        state.stop_run(
            app,
            run,
            true,
            "error",
            "The answer panel could not open. Retry explicitly.",
        );
        return Err(e);
    }
    let current = {
        let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
        if inner.run == run && !cancel.stopped() {
            inner.snapshot.panel_visible = true;
            true
        } else {
            false
        }
    };
    if !current {
        if state
            .0
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .selection
            .is_none()
        {
            if let Some(panel) = app.get_webview_window("answer-panel") {
                let _ = panel.destroy();
            }
        }
        return Err("request_cancelled".into());
    }
    diag::emit(
        "monitor_start",
        "INFO",
        Some(&trace),
        json!({"run":run,"outcome":"active","mode":selection_mode(&config)}),
    );
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        run_loop(handle, run, selection, cancel).await;
    });
    Ok(())
}
fn selection_mode(config: &Value) -> &str {
    config["mode"].as_str().unwrap_or("general")
}
fn context_signature(config: &Value) -> String {
    if config["mode"] == "general" {
        return String::new();
    }
    config["documents"]
        .as_array()
        .map(|docs| {
            docs.iter()
                .map(|d| {
                    json!([
                        d["id"],
                        d["index_generation"],
                        d["index_status"],
                        d["extraction_status"]
                    ])
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
        .iter()
        .map(Value::to_string)
        .collect::<Vec<_>>()
        .join("|")
}
fn fingerprint(observation: &Value) -> String {
    let fields = [
        "question_type",
        "question_text",
        "options",
        "instructions",
        "required_selection_count",
        "visible_context",
        "visual_elements",
    ];
    let data: serde_json::Map<String, Value> = fields
        .into_iter()
        .map(|key| (key.into(), observation[key].clone()))
        .collect();
    fn normalize(value: Value, preserve: bool) -> Value {
        match value {
            Value::String(text) => Value::String(if preserve {
                text.trim().into()
            } else {
                text.split_whitespace().collect::<Vec<_>>().join(" ")
            }),
            Value::Array(values) => {
                Value::Array(values.into_iter().map(|v| normalize(v, preserve)).collect())
            }
            Value::Object(values) => Value::Object(
                values
                    .into_iter()
                    .map(|(k, v)| (k, normalize(v, preserve)))
                    .collect(),
            ),
            other => other,
        }
    }
    normalize(Value::Object(data), observation["question_type"] == "code").to_string()
}
use pipeline::{Outcome, Services};
struct NativeServices {
    app: tauri::AppHandle,
    selection: Selection,
    run: u64,
    generation: u64,
}
impl Services for NativeServices {
    async fn session(&self) -> Result<()> {
        if !self
            .app
            .state::<MonitorState>()
            .current(self.run, self.generation)
        {
            return Err("request_cancelled".into());
        }
        active_for(
            &self.app,
            &self.selection,
            Some((self.run, self.generation)),
        )
        .await?;
        if !self
            .app
            .state::<MonitorState>()
            .current(self.run, self.generation)
        {
            return Err("request_cancelled".into());
        }
        Ok(())
    }
    async fn vision(&self, payload: Value) -> Result<Value> {
        if !self
            .app
            .state::<MonitorState>()
            .current(self.run, self.generation)
        {
            return Err("request_cancelled".into());
        }
        let auth = self.app.state::<AuthState>();
        let trace = Trace::candidate(
            &self.selection.trace_id,
            self.run,
            self.generation,
            "vision",
        );
        unwrap_response(
            auth::request_authenticated_traced(
                &auth,
                AiKind::Vision,
                trace.request_id.clone(),
                payload,
                &trace,
            )
            .await
            .map_err(|e| e.code)?,
        )
    }
    async fn answer(&self, observation: Value) -> Result<Value> {
        if !self
            .app
            .state::<MonitorState>()
            .current(self.run, self.generation)
        {
            return Err("request_cancelled".into());
        }
        let auth = self.app.state::<AuthState>();
        let trace = Trace::candidate(
            &self.selection.trace_id,
            self.run,
            self.generation,
            "answer",
        );
        unwrap_response(auth::request_authenticated_traced(&auth,AiKind::Answer,trace.request_id.clone(),json!({"observation":observation,"session_id":self.selection.session_id,"session_revision":self.selection.revision}),&trace).await.map_err(|e|e.code)?)
    }
}
async fn pipeline(
    app: tauri::AppHandle,
    selection: Selection,
    frame: capture::Frame,
    last: Option<String>,
    run: u64,
    generation: u64,
) -> Result<Outcome> {
    let services = NativeServices {
        app,
        selection,
        run,
        generation,
    };
    services.session().await?;
    let encoder = services.app.state::<MonitorState>().2.clone();
    let permit = encoder
        .acquire_owned()
        .await
        .map_err(|_| "capture_cancelled")?;
    let image = tauri::async_runtime::spawn_blocking(move || {
        let _permit = permit;
        frame.encode()
    })
    .await
    .map_err(|_| "capture_failed")?
    .map_err(|e| e.code.to_owned())?;
    pipeline::execute(
        &services,
        json!({"media_type":"image/png","image_base64":image.image_base64}),
        last,
    )
    .await
}
fn unwrap_response(response: Value) -> Result<Value> {
    if response["ok"] == true {
        Ok(response["data"].clone())
    } else {
        Err(response["error"]["code"]
            .as_str()
            .unwrap_or("provider_unavailable")
            .into())
    }
}
fn terminal(code: &str) -> bool {
    matches!(
        code,
        "sign_in_required"
            | "session_expired"
            | "session_revoked"
            | "invalid_session"
            | "session_changed"
            | "session_missing"
            | "session_replaced"
            | "session_not_active"
            | "session_revision_mismatch"
            | "session_materials_not_ready"
            | "session_materials_changed"
            | "source_unavailable"
            | "capture_timeout"
            | "source_changed"
    )
}
fn backoff(failures: u32) -> u64 {
    30u64.saturating_mul(1u64 << failures.min(2))
}
struct Termination {
    run: u64,
    cancel: Arc<Cancellation>,
    trace: Trace,
}
impl Drop for Termination {
    fn drop(&mut self) {
        if !self.cancel.stopped() {
            diag::emit(
                "monitor_unexpected_termination",
                "WARNING",
                Some(&self.trace),
                json!({"run":self.run,"reason":if std::thread::panicking(){"panic"}else{"unexpected_return"}}),
            );
        }
    }
}
async fn run_loop(
    app: tauri::AppHandle,
    run: u64,
    selection: Selection,
    cancel: Arc<Cancellation>,
) {
    let _termination = Termination {
        run,
        cancel: cancel.clone(),
        trace: Trace::session(&selection.trace_id, None),
    };
    let mut gate = Gate::new();
    let started = Instant::now();
    let mut next_request = 0;
    let mut attempts = 0;
    let mut failures = 0;
    let mut last = None;
    let mut generation = 0;
    let mut next_session_check = 5000; // Startup just validated; do not immediately repeat.
    let mut worker: Option<tauri::async_runtime::JoinHandle<Result<Outcome>>> = None;
    loop {
        tokio::select! {_ = cancel.wake.notified()=>break,_=tokio::time::sleep(Duration::from_millis(selection.config.interval_ms))=>{}}
        if cancel.stopped() {
            break;
        }
        let state = app.state::<MonitorState>();
        let now = started.elapsed().as_millis() as u64;
        let auth = app.state::<AuthState>();
        let credential = tokio::select! {_ = cancel.wake.notified()=>break,result=auth.library_credential_present(selection.epoch)=>result};
        if credential.is_err() {
            state.stop_run(
                &app,
                run,
                false,
                "stopped",
                "Sign-in ended. Monitoring stopped.",
            );
            break;
        }
        if now >= next_session_check {
            let checked = tokio::select! {_ = cancel.wake.notified()=>break,result=active(&app,&selection)=>result};
            if let Err(code) = checked {
                diag::emit(
                    "monitor_session_failure",
                    "WARNING",
                    Some(&Trace::session(&selection.trace_id, None)),
                    json!({"error_code":code,"error_category":diag::category(&code),"run":run}),
                );
                state.stop_run(&app, run, false, "stopped", session_message(&code));
                break;
            }
            next_session_check = started.elapsed().as_millis() as u64 + 5000;
        }
        let source = selection.source.clone();
        let target = selection.target.clone().expect("validated source identity");
        if target.closed() {
            diag::emit(
                "monitor_source_failure",
                "WARNING",
                Some(&Trace::session(&selection.trace_id, None)),
                json!({"error_code":"source_unavailable","run":run}),
            );
            state.stop_run(
                &app,
                run,
                true,
                "error",
                "The selected source closed. Stop and explicitly choose another source.",
            );
            break;
        }
        let token = cancel.clone();
        let capture = app.state::<Arc<capture::CaptureState>>().inner().clone();
        let frame = tauri::async_runtime::spawn_blocking(move || {
            capture::sample(&capture, source, &token.flag, &target)
        })
        .await;
        if cancel.stopped() {
            break;
        }
        let frame = match frame {
            Ok(Ok(frame)) => frame,
            Ok(Err(e)) if e.code == "busy" => continue,
            failed => {
                let code = match failed {
                    Ok(Err(e)) => e.code,
                    _ => "capture_worker_failed",
                };
                diag::emit(
                    "monitor_source_failure",
                    "WARNING",
                    Some(&Trace::session(&selection.trace_id, None)),
                    json!({"error_code":code,"run":run}),
                );
                state.stop_run(&app,run,true,"error","Source unavailable or capture failed. Restore the selected source and Resume, or Stop and select another.");
                break;
            }
        };
        let now = started.elapsed().as_millis() as u64;
        let (changed, stable) =
            gate.observe(Signature::of(&frame), now, selection.config.stabilize_ms);
        if changed {
            generation += 1;
            diag::emit(
                "monitor_candidate_changed",
                "DEBUG",
                Some(&Trace::session(
                    &selection.trace_id,
                    Some((run, generation)),
                )),
                json!({"run":run,"generation":generation,"reason":"source_changed"}),
            );
            if let Some(old) = worker.take() {
                old.abort();
                let _ = old.await;
            }
            if !state.change(run, |s| {
                s.generation = (run << 32) + generation;
                s.observation = None;
                s.answer = None;
                s.phase = "monitoring".into();
                s.message = "Source changed. Waiting for stable content.".into();
            }) {
                break;
            }
        }
        if worker.as_ref().is_some_and(|w| w.inner().is_finished()) {
            let result = worker.take().expect("finished worker").await;
            match result {
                Ok(Ok(outcome)) => {
                    failures = 0;
                    diag::emit(
                        "monitor_candidate_finished",
                        "INFO",
                        Some(&Trace::session(
                            &selection.trace_id,
                            Some((run, generation)),
                        )),
                        json!({"run":run,"generation":generation,"outcome":if outcome.answer.is_some(){"answer_ready"}else{"no_new_answer"},"answer_outcome":outcome.answer.as_ref().and_then(|a|a["status"].as_str())}),
                    );
                    if outcome.answer.is_some() {
                        last = Some(outcome.fingerprint);
                    }
                    if !state.publish(run, generation, |s| {
                        s.phase = if outcome.answer.is_some() {
                            "answer_ready"
                        } else {
                            "monitoring"
                        }
                        .into();
                        s.observation = Some(outcome.observation);
                        s.answer = outcome.answer;
                        s.message = outcome.message.into();
                    }) {
                        break;
                    }
                }
                Ok(Err(code)) => {
                    failures += 1;
                    diag::emit(
                        "monitor_pipeline_failed",
                        "WARNING",
                        Some(&Trace::session(
                            &selection.trace_id,
                            Some((run, generation)),
                        )),
                        json!({"run":run,"generation":generation,"error_code":code,"error_category":diag::category(&code),"attempt":attempts}),
                    );
                    if terminal(&code) {
                        state.stop_run(
                            &app,
                            run,
                            false,
                            "stopped",
                            "Session or authorization changed. Monitoring stopped.",
                        );
                        break;
                    }
                    if failures >= 3 {
                        state.stop_run(&app,run,true,"error","Repeated provider failures. Check configuration or connection, then Resume explicitly.");
                        break;
                    }
                    next_request = next_request.max(now + backoff(failures - 1) * 1000);
                    gate.retry();
                    state.change(run,|s|{s.phase="monitoring".into();s.message="Provider unavailable. Backing off before a bounded retry. Pause or Stop at any time.".into();s.observation=None;s.answer=None;});
                }
                Err(_) => {
                    diag::emit(
                        "monitor_worker_terminated",
                        "WARNING",
                        Some(&Trace::session(
                            &selection.trace_id,
                            Some((run, generation)),
                        )),
                        json!({"error_code":"worker_terminated","run":run,"generation":generation}),
                    );
                    state.stop_run(
                        &app,
                        run,
                        true,
                        "error",
                        "Monitoring work ended unexpectedly. Resume explicitly.",
                    );
                    break;
                }
            }
        }
        if stable && worker.is_none() && now >= next_request {
            if attempts >= selection.config.max_questions {
                state.stop_run(
                    &app,
                    run,
                    true,
                    "paused",
                    "Automatic request limit reached. Review costs before explicitly resuming.",
                );
                break;
            }
            attempts += 1;
            diag::emit(
                "monitor_candidate_started",
                "INFO",
                Some(&Trace::session(
                    &selection.trace_id,
                    Some((run, generation)),
                )),
                json!({"run":run,"generation":generation,"attempt":attempts}),
            );
            gate.sent();
            next_request = now + selection.config.request_interval_seconds * 1000;
            state.change(run, |s| {
                s.phase = "processing".into();
                s.question_number = attempts;
                s.message =
                    "Reading stable content and preparing a session-aware recommendation…".into();
            });
            // The worker cannot enter a provider boundary until its abort handle
            // is registered under the same run lock used by Pause/Stop.
            let (permit, ready) = tokio::sync::oneshot::channel();
            let app_for_task = app.clone();
            let selected = selection.clone();
            let previous = last.clone();
            let task = tauri::async_runtime::spawn(async move {
                ready.await.map_err(|_| "request_cancelled".to_owned())?;
                pipeline(app_for_task, selected, frame, previous, run, generation).await
            });
            {
                let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
                if inner.run == run && !cancel.stopped() {
                    inner.worker = Some(task.inner().abort_handle());
                    let _ = permit.send(());
                } else {
                    task.abort();
                }
            }
            worker = Some(task);
        }
    }
    if let Some(task) = worker {
        task.abort();
        let _ = task.await;
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn starts_stopped_and_config_is_bounded() {
        assert_eq!(Snapshot::default().phase, "stopped");
        assert!(Config::default().validate().is_ok());
        assert!(Config {
            interval_ms: 10,
            ..Config::default()
        }
        .validate()
        .is_err());
        assert!(Config {
            request_interval_seconds: 1,
            ..Config::default()
        }
        .validate()
        .is_err());
    }
    #[test]
    fn ipc_is_narrow_and_no_history_is_serialized() {
        assert!(
            serde_json::from_value::<Operation>(json!({"kind":"snapshot","url":"evil"})).is_err()
        );
        assert!(
            serde_json::from_value::<Operation>(json!({"kind":"start","source_id":"x"})).is_err()
        );
        let raw = serde_json::to_string(&Snapshot::default()).unwrap();
        assert!(!raw.contains("credential"));
        assert!(!raw.contains("imageBase64"));
    }
    #[test]
    fn question_dedup_ignores_confidence_but_preserves_options() {
        let a = json!({"question_text":"Question?","options":[{"label":"A","text":"One"}],"extraction_confidence":0.8});
        let mut b = a.clone();
        b["extraction_confidence"] = json!(0.9);
        assert_eq!(fingerprint(&a), fingerprint(&b));
        b["options"][0]["text"] = json!("Two");
        assert_ne!(fingerprint(&a), fingerprint(&b));
    }
    #[test]
    fn bounded_error_backoff_and_terminal_failures() {
        assert_eq!(backoff(0), 30);
        assert_eq!(backoff(1), 60);
        assert_eq!(backoff(100), 120);
        assert!(terminal("session_revoked"));
        assert!(terminal("source_unavailable"));
        assert!(!terminal("provider_timeout"));
    }
    #[test]
    fn pause_stop_and_stale_loop_cannot_affect_a_new_run() {
        let state = MonitorState::default();
        let old = Arc::new(Cancellation::new());
        {
            let mut inner = state.0.lock().unwrap();
            inner.run = 1;
            inner.cancel = Some(old.clone());
            inner.snapshot.phase = "processing".into();
            inner.snapshot.answer = Some(json!({"private":"ephemeral"}));
            inner.snapshot.observation = Some(json!({"question":"ephemeral"}));
        }
        assert!(state.reset(Some(1), true, "paused", "Paused"));
        assert!(old.stopped());
        assert!(state.0.lock().unwrap().snapshot.answer.is_none());
        assert!(!state.change(1, |s| s.answer = Some(json!({}))));
        let fresh = Arc::new(Cancellation::new());
        {
            let mut inner = state.0.lock().unwrap();
            inner.run = 3;
            inner.cancel = Some(fresh.clone());
            inner.snapshot.phase = "monitoring".into();
            inner.snapshot.generation = (3 << 32) + 2;
        }
        assert!(!state.reset(Some(1), false, "stopped", "Old failure"));
        assert!(!fresh.stopped());
        state.publish(3, 1, |s| s.answer = Some(json!({"obsolete":true})));
        assert!(state.0.lock().unwrap().snapshot.answer.is_none());
        state.publish(3, 2, |s| s.answer = Some(json!({"current":true})));
        assert!(state.0.lock().unwrap().snapshot.answer.is_some());
        assert!(state.reset(None, false, "stopped", "Stopped"));
        assert!(fresh.stopped());
        assert!(state.0.lock().unwrap().snapshot.answer.is_none());
    }
    #[test]
    fn stop_invalidates_a_start_that_is_waiting_for_validation() {
        let state = MonitorState::default();
        let ticket = state.1.fetch_add(1, Ordering::SeqCst) + 1;
        state.reset(None, false, "stopped", "Stop while starting");
        assert_ne!(state.1.load(Ordering::SeqCst), ticket);
    }
    #[test]
    fn pause_aborts_native_provider_work_without_a_webview_timer() {
        tauri::async_runtime::block_on(async {
            let state = MonitorState::default();
            let task = tokio::spawn(async { std::future::pending::<()>().await });
            {
                let mut inner = state.0.lock().unwrap();
                inner.run = 9;
                inner.worker = Some(task.abort_handle());
                inner.cancel = Some(Arc::new(Cancellation::new()));
            }
            state.reset(Some(9), true, "paused", "Pause");
            assert!(task.await.unwrap_err().is_cancelled());
        });
    }
    #[test]
    fn index_generation_changes_invalidate_grounding_but_general_ignores_it() {
        let mut config = json!({"mode":"materials_only","documents":[{"id":"owned","index_generation":"one","index_status":"ready","extraction_status":"ready"}]});
        let before = context_signature(&config);
        config["documents"][0]["index_generation"] = json!("two");
        assert_ne!(before, context_signature(&config));
        config["mode"] = json!("general");
        assert_eq!(context_signature(&config), "");
    }
    #[test]
    fn session_failure_diagnostics_do_not_conflate_healthy_backend_timeout_and_expiry() {
        assert_eq!(SESSION_CHECK_TIMEOUT, Duration::from_secs(12));
        assert!(session_message("session_check_timeout").contains("12-second"));
        assert!(session_message("session_revoked").contains("Authentication"));
        assert!(session_message("session_revision_mismatch").contains("revision"));
        assert_ne!(
            session_message("backend_connection_failed"),
            session_message("database_unavailable")
        );
        assert!(terminal("session_revision_mismatch"));
        assert!(terminal("session_missing"));
    }
    #[test]
    fn stop_or_pause_interrupts_pending_startup_session_validation() {
        tauri::async_runtime::block_on(async {
            let state = Arc::new(MonitorState::default());
            let waiting = state.clone();
            let (ready, started) = tokio::sync::oneshot::channel();
            let task = tauri::async_runtime::spawn(async move {
                let invalidated = waiting.3.notified();
                tokio::pin!(invalidated);
                invalidated.as_mut().enable();
                ready.send(()).unwrap();
                validation::cancellable(std::future::pending::<Result<Value>>(), invalidated).await
            });
            started.await.unwrap();
            let before = Instant::now();
            assert!(state.reset(None, false, "stopped", "Stopped"));
            assert_eq!(task.await.unwrap().unwrap_err(), "request_cancelled");
            assert!(before.elapsed() < Duration::from_secs(1));
        });
    }
}
