//! Allowlisted terminal JSON only. Never stringify HTTP/OS/provider exceptions.
use serde_json::{json, Map, Value};
use std::{
    io::Write,
    sync::atomic::{AtomicU64, Ordering},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
static SEQUENCE: AtomicU64 = AtomicU64::new(0);
fn stamp() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
}
pub fn activation_id() -> String {
    format!(
        "live-{:x}-{:x}-{}",
        std::process::id(),
        stamp(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    )
}
#[derive(Clone)]
pub struct Trace {
    pub trace_id: String,
    pub request_id: String,
    pub candidate_id: Option<String>,
}
impl Trace {
    pub fn session(trace_id: &str, candidate: Option<(u64, u64)>) -> Self {
        Self {
            trace_id: trace_id.into(),
            request_id: format!("session-{:x}", stamp()),
            candidate_id: candidate.map(|(r, g)| format!("question-{r}-{g}")),
        }
    }
    pub fn candidate(trace_id: &str, run: u64, generation: u64, kind: &str) -> Self {
        Self {
            trace_id: trace_id.into(),
            request_id: format!("monitor-{run}-{generation}-{kind}-{:x}", stamp()),
            candidate_id: Some(format!("question-{run}-{generation}")),
        }
    }
    pub fn local(request_id: &str) -> Self {
        Self {
            trace_id: request_id.into(),
            request_id: request_id.into(),
            candidate_id: None,
        }
    }
}
pub fn category(code: &str) -> &'static str {
    match code {
        "sign_in_required" | "invalid_session" | "session_expired" | "session_revoked" => {
            "authentication"
        }
        "session_check_timeout" | "backend_timeout" => "network_timeout",
        "backend_connection_failed" => "network_connect",
        "backend_unavailable" => "network",
        "backend_http_error" => "backend_http",
        "backend_invalid_response" | "backend_response_too_large" => "invalid_response",
        "session_revision_mismatch" | "preparation_changed" => "session_revision",
        "session_ownership_mismatch" | "preparation_not_found" | "document_not_found" => {
            "ownership_or_missing"
        }
        "request_cancelled" => "cancellation",
        "source_unavailable" | "capture_timeout" | "source_changed" => "source",
        c if c.starts_with("database_") => "database",
        c if c.starts_with("session_") => "session",
        c if c.starts_with("provider_")
            || c.starts_with("answer_")
            || c.starts_with("embedding_")
            || c.starts_with("vision_")
            || c.starts_with("invalid_provider_") =>
        {
            if c.contains("timeout") {
                "provider_timeout"
            } else {
                "provider"
            }
        }
        _ => "validation_or_internal",
    }
}
pub fn endpoint(value: &str) -> String {
    let path = value.split('?').next().unwrap_or("");
    if matches!(
        path,
        "/api/v1/vision/question"
            | "/api/v1/answer"
            | "/api/v1/learning/sessions/active"
            | "/api/v1/learning/preparation"
            | "/api/v1/learning/sessions/start"
    ) {
        return path.into();
    }
    if path.starts_with("/api/v1/context/documents") {
        return "/api/v1/context/documents/{operation}".into();
    }
    if path.starts_with("/api/v1/learning/") {
        return "/api/v1/learning/{operation}".into();
    }
    "/unclassified".into()
}
fn word(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
}
fn id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-')
}
fn record(event: &str, level: &str, trace: Option<&Trace>, fields: Value) -> Value {
    let mut data = Map::new();
    data.insert("timestamp_ms".into(), json!((stamp() / 1_000_000) as u64));
    data.insert(
        "event".into(),
        json!(if word(event) {
            event
        } else {
            "diagnostic_event"
        }),
    );
    data.insert("level".into(), json!(level));
    if let Some(t) = trace {
        for (key, value) in [
            ("trace_id", Some(&t.trace_id)),
            ("request_id", Some(&t.request_id)),
            ("candidate_id", t.candidate_id.as_ref()),
        ] {
            if let Some(v) = value.filter(|v| id(v)) {
                data.insert(key.into(), json!(v));
            }
        }
    }
    if let Some(fields) = fields.as_object() {
        for (key, value) in fields {
            let safe = match key.as_str() {
                "status" | "duration_ms" | "run" | "generation" | "attempt" | "deadline_ms"
                | "retry_ms" => value.is_u64(),
                "endpoint" => false,
                "stage" | "outcome" | "reason" | "error_code" | "error_category" | "mode"
                | "action" | "answer_outcome" => value.as_str().is_some_and(word),
                _ => false,
            };
            if safe {
                data.insert(key.clone(), value.clone());
            } else if key == "endpoint" {
                if let Some(v) = value.as_str() {
                    data.insert(key.clone(), json!(endpoint(v)));
                }
            }
        }
    }
    Value::Object(data)
}
fn enabled(level: &str, configured: &str) -> bool {
    level != "DEBUG" || configured == "DEBUG"
}
pub fn emit(event: &str, level: &str, trace: Option<&Trace>, fields: Value) {
    if !enabled(
        level,
        &std::env::var("SOLVEGUIDE_LOG_LEVEL").unwrap_or_else(|_| "INFO".into()),
    ) {
        return;
    }
    let mut line = record(event, level, trace, fields).to_string();
    line.push('\n');
    let _ = std::io::stderr().lock().write_all(line.as_bytes());
}
pub fn http_error(error: &reqwest::Error) -> &'static str {
    if error.is_timeout() {
        "backend_timeout"
    } else if error.is_connect() {
        "backend_connection_failed"
    } else if error.is_decode() {
        "backend_invalid_response"
    } else {
        "backend_unavailable"
    }
}
fn http_level(ai: bool, code: Option<&str>) -> &'static str {
    if code == Some("request_cancelled") {
        "DEBUG"
    } else if code.is_some() {
        "WARNING"
    } else if ai {
        "INFO"
    } else {
        "DEBUG"
    }
}
pub struct Http {
    trace: Trace,
    endpoint: String,
    started: Instant,
    done: bool,
    ai: bool,
}
impl Http {
    pub fn new(trace: Trace, path: &str, ai: bool) -> Self {
        emit(
            "backend_http_started",
            "DEBUG",
            Some(&trace),
            json!({"endpoint":path}),
        );
        Self {
            trace,
            endpoint: endpoint(path),
            started: Instant::now(),
            done: false,
            ai,
        }
    }
    pub fn finish(&mut self, status: Option<u16>, code: Option<&str>) {
        self.done = true;
        emit(
            "backend_http",
            http_level(self.ai, code),
            Some(&self.trace),
            json!({"endpoint":self.endpoint,"status":status,"duration_ms":self.started.elapsed().as_millis() as u64,"outcome":if code==Some("request_cancelled"){"cancelled"}else if code.is_some(){"failed"}else{"completed"},"error_code":code,"error_category":code.map(category)}),
        );
    }
}
impl Drop for Http {
    fn drop(&mut self) {
        if !self.done {
            emit(
                "backend_http",
                "DEBUG",
                Some(&self.trace),
                json!({"endpoint":self.endpoint,"duration_ms":self.started.elapsed().as_millis() as u64,"outcome":"cancelled","error_code":"request_cancelled","error_category":"cancellation"}),
            );
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn structured_diagnostics_redact_payloads_urls_and_credentials() {
        let trace = Trace::session(&activation_id(), Some((1, 2)));
        let value = record(
            "backend_http",
            "INFO",
            Some(&trace),
            json!({"endpoint":"/api/v1/learning/sessions/active?token=secret","status":503,"duration_ms":200,"question_text":"private question","answer":"private answer","authorization":"Bearer secret","error":"postgresql://user:password@host/db"}),
        );
        let text = value.to_string();
        assert!(!text.contains("secret"));
        assert!(!text.contains("private"));
        assert!(!text.contains("password"));
        assert_eq!(value["candidate_id"], "question-1-2");
    }
    #[test]
    fn failures_are_distinct_and_activations_do_not_collide() {
        assert_ne!(activation_id(), activation_id());
        assert_ne!(category("session_expired"), category("backend_timeout"));
        assert_eq!(category("session_revision_mismatch"), "session_revision");
        assert_ne!(category("provider_timeout"), category("session_missing"));
    }
    #[test]
    fn correlation_connects_session_vision_answer_and_default_level_is_info() {
        let id = activation_id();
        let session = Trace::session(&id, Some((4, 2)));
        let vision = Trace::candidate(&id, 4, 2, "vision");
        let answer = Trace::candidate(&id, 4, 2, "answer");
        assert_eq!(session.trace_id, vision.trace_id);
        assert_eq!(vision.trace_id, answer.trace_id);
        assert_eq!(vision.candidate_id, answer.candidate_id);
        assert_ne!(vision.request_id, answer.request_id);
        assert!(!enabled("DEBUG", "INFO"));
        assert!(enabled("INFO", "INFO"));
        assert!(enabled("DEBUG", "DEBUG"));
    }
    #[test]
    fn successful_heartbeats_are_quiet_at_info_and_failures_are_visible() {
        assert!(!enabled(http_level(false, None), "INFO"));
        assert!(enabled(http_level(false, Some("session_expired")), "INFO"));
        assert_eq!(http_level(true, Some("request_cancelled")), "DEBUG");
    }
}
