//! Bounded process-local diagnostic aggregation. Never participates in monitor decisions.
use super::{record, Trace};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, VecDeque},
    sync::{Mutex, OnceLock},
    time::{Duration, Instant},
};

#[derive(Clone, Copy, Debug, PartialEq)]
pub(super) enum Mode {
    Normal,
    Performance,
    Debug,
}
pub(super) fn resolve(explicit: Option<&str>, legacy: Option<&str>) -> Mode {
    match explicit {
        Some("PERFORMANCE") => Mode::Performance,
        Some("DEBUG") => Mode::Debug,
        Some(_) => Mode::Normal,
        None if legacy == Some("DEBUG") => Mode::Debug,
        None => Mode::Normal,
    }
}
pub(super) fn mode() -> Mode {
    resolve(
        std::env::var("SOLVEGUIDE_DIAGNOSTIC_MODE").ok().as_deref(),
        std::env::var("SOLVEGUIDE_LOG_LEVEL").ok().as_deref(),
    )
}
pub(super) fn visible(mode: Mode, event: &str, level: &str) -> bool {
    mode == Mode::Debug
        || matches!(level, "WARNING" | "ERROR")
        || matches!(
            event,
            "application_started"
                | "application_stopped"
                | "monitor_start"
                | "monitor_action"
                | "monitor_transition"
        )
}
const STAGES: &[&str] = &[
    "detection_stability",
    "candidate_capture",
    "candidate_scheduling",
    "frame_fingerprint",
    "encoder_slot_wait",
    "image_preparation",
    "session_validation",
    "native_authentication_validation",
    "backend_http",
    "backend_response_headers",
    "backend_response_body_decode",
    "observation_gate_dedup",
    "candidate_pipeline",
    "worker_collection",
    "panel_ready_ack",
];
#[derive(Default)]
struct Entry {
    trace: String,
    candidate: String,
    attempt: Option<u64>,
    touched: Option<Instant>,
    stages: BTreeMap<String, (u64, u64)>,
    requests: Vec<String>,
    ai_requests: u64,
    finished: bool,
    question_type: Option<String>,
    answer_outcome: Option<String>,
    panel_receipt_to_ready_ms: Option<u64>,
    panel_validation_ms: Option<u64>,
}
impl Entry {
    fn summary(&mut self, outcome: &str, observed: Option<u64>) -> Option<Value> {
        if self.finished || self.attempt.is_none() {
            return None;
        }
        self.finished = true;
        let stages: BTreeMap<_, _> = STAGES
            .iter()
            .map(|s| {
                (
                    *s,
                    self.stages
                        .get(*s)
                        .map(|(count, max)| json!({"count":count,"max_single_span_ms":max})),
                )
            })
            .collect();
        Some(
            json!({"event":"performance_report","boundary":"native_attempt",
            "trace_id":self.trace,"candidate_id":self.candidate,"attempt":self.attempt,
            "request_ids":self.requests,"outcome":outcome,"question_type":self.question_type,
            "answer_outcome":self.answer_outcome,
            "panel_receipt_to_ready_ms":self.panel_receipt_to_ready_ms,"panel_validation_ms":self.panel_validation_ms,
            "observed_generation_total_ms":observed,"provider_calls":null,
            "backend_ai_requests":self.ai_requests,"stages_ms":stages,
            "backend_authentication_ms":null,"database_ms":null,"provider_ms":null}),
        )
    }
}
#[derive(Default)]
pub(super) struct Reports {
    entries: VecDeque<Entry>,
}
impl Reports {
    pub(super) fn observe(
        &mut self,
        event: &str,
        trace: &Trace,
        fields: Value,
        now: Instant,
    ) -> Vec<Value> {
        let mut output = Vec::new();
        // Expiry is lazy/event-driven: no timer, task, file or IPC is introduced.
        let mut i = 0;
        while i < self.entries.len() {
            if self.entries[i]
                .touched
                .is_some_and(|t| now.saturating_duration_since(t) > Duration::from_secs(600))
            {
                if let Some(value) = self.entries[i].summary("diagnostic_expired", None) {
                    output.push(value);
                }
                self.entries.remove(i);
            } else {
                i += 1;
            }
        }
        let safe = record(event, "DEBUG", Some(trace), fields);
        let (Some(t), Some(c)) = (safe["trace_id"].as_str(), safe["candidate_id"].as_str()) else {
            return output;
        };
        let index = self
            .entries
            .iter()
            .position(|e| e.trace == t && e.candidate == c);
        let index = if let Some(index) = index {
            index
        } else {
            if self.entries.len() == 32 {
                if let Some(mut old) = self.entries.pop_front() {
                    if let Some(value) = old.summary("diagnostic_evicted", None) {
                        output.push(value);
                    }
                }
            }
            self.entries.push_back(Entry {
                trace: t.into(),
                candidate: c.into(),
                ..Entry::default()
            });
            self.entries.len() - 1
        };
        let entry = &mut self.entries[index];
        entry.touched = Some(now);
        let stage = match event {
            "backend_http" => "backend_http",
            "native_authentication_validation" => "native_authentication_validation",
            _ => safe["stage"].as_str().unwrap_or(""),
        };
        // These events precede dispatch, including a retry after a failed attempt.
        if matches!(stage, "candidate_capture" | "frame_fingerprint") {
            if let Some(ms) = safe["duration_ms"].as_u64() {
                entry.stages.insert(stage.into(), (1, ms));
            }
            return output;
        }
        if stage == "candidate_scheduling" {
            let attempt = safe["attempt"].as_u64();
            if attempt != entry.attempt {
                // Retry is a distinct attempt; initial detection remains generation-relative.
                let detection = entry.stages.get("detection_stability").copied();
                let capture = entry.stages.get("candidate_capture").copied();
                let fingerprint = entry.stages.get("frame_fingerprint").copied();
                entry.stages.clear();
                if let Some(row) = detection {
                    entry.stages.insert("detection_stability".into(), row);
                }
                if let Some(row) = capture {
                    entry.stages.insert("candidate_capture".into(), row);
                }
                if let Some(row) = fingerprint {
                    entry.stages.insert("frame_fingerprint".into(), row);
                }
                entry.requests.clear();
                entry.ai_requests = 0;
                entry.answer_outcome = None;
                entry.panel_receipt_to_ready_ms = None;
                entry.panel_validation_ms = None;
                entry.finished = false;
                entry.attempt = attempt;
            }
        }
        if entry.finished {
            return output;
        }
        if let Some(kind) = safe["question_type"].as_str() {
            entry.question_type = Some(kind.into());
        }
        if let Some(
            result @ ("answered" | "uncertain" | "insufficient_information" | "unsupported"),
        ) = safe["answer_outcome"].as_str()
        {
            entry.answer_outcome = Some(result.into());
        }
        if stage == "panel_ready_ack" {
            entry.panel_receipt_to_ready_ms = safe["receipt_to_ready_ms"].as_u64();
            entry.panel_validation_ms = safe["validation_ms"].as_u64();
        }
        if STAGES.contains(&stage) {
            if let Some(ms) = safe["duration_ms"].as_u64() {
                let row = entry.stages.entry(stage.into()).or_default();
                row.0 += 1;
                row.1 = row.1.max(ms);
            }
        }
        if event == "backend_http" {
            if let Some(id) = safe["request_id"].as_str() {
                if entry.requests.len() < 16 && !entry.requests.iter().any(|v| v == id) {
                    entry.requests.push(id.into());
                    if matches!(
                        safe["endpoint"].as_str(),
                        Some("/api/v1/vision/question" | "/api/v1/answer")
                    ) {
                        entry.ai_requests += 1;
                    }
                }
            }
        }
        let terminal = if event == "performance_candidate" {
            Some((
                safe["outcome"].as_str().unwrap_or("unknown"),
                safe["duration_ms"].as_u64(),
            ))
        } else if stage == "candidate_pipeline"
            && matches!(safe["outcome"].as_str(), Some("failed" | "cancelled"))
        {
            Some((safe["outcome"].as_str().unwrap(), None))
        } else {
            None
        };
        if let Some((outcome, total)) = terminal {
            if let Some(value) = entry.summary(outcome, total) {
                output.push(value);
            }
        }
        output
    }
}
pub(super) fn collect(event: &str, trace: Option<&Trace>, fields: &Value) -> Vec<Value> {
    if !matches!(
        event,
        "performance_stage"
            | "performance_candidate"
            | "backend_http"
            | "monitor_candidate_finished"
            | "native_authentication_validation"
    ) {
        return vec![];
    }
    let Some(trace) = trace.filter(|t| t.candidate_id.is_some()) else {
        return vec![];
    };
    static STORE: OnceLock<Mutex<Reports>> = OnceLock::new();
    STORE
        .get_or_init(|| Mutex::new(Reports::default()))
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .observe(event, trace, fields.clone(), Instant::now())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn trace(n: u64) -> Trace {
        Trace::candidate("live-a-b-1", 1, n, "answer")
    }
    fn event(
        store: &mut Reports,
        t: &Trace,
        event: &str,
        fields: Value,
        at: Instant,
    ) -> Vec<Value> {
        store.observe(event, t, fields, at)
    }
    fn dispatch(store: &mut Reports, t: &Trace, attempt: u64, at: Instant) {
        event(
            store,
            t,
            "performance_stage",
            json!({"stage":"candidate_scheduling","duration_ms":200,"attempt":attempt}),
            at,
        );
    }
    #[test]
    fn modes_are_explicit_legacy_compatible_and_quiet() {
        assert_eq!(resolve(None, None), Mode::Normal);
        assert_eq!(resolve(None, Some("DEBUG")), Mode::Debug);
        assert_eq!(resolve(Some("NORMAL"), Some("DEBUG")), Mode::Normal);
        assert_eq!(
            resolve(Some("PERFORMANCE"), Some("DEBUG")),
            Mode::Performance
        );
        assert_eq!(resolve(Some("DEBUG"), Some("INFO")), Mode::Debug);
        for mode in [Mode::Normal, Mode::Performance] {
            for event in [
                "backend_http",
                "session_check_finished",
                "monitor_candidate_changed",
                "performance_stage",
            ] {
                assert!(!visible(mode, event, "DEBUG"));
                assert!(!visible(mode, event, "INFO"));
                assert!(visible(mode, event, "WARNING"));
            }
            assert!(visible(mode, "monitor_transition", "INFO"));
        }
        assert!(visible(Mode::Debug, "performance_stage", "DEBUG"));
    }
    #[test]
    fn one_report_per_attempt_missing_clocks_and_overlapping_stages_are_honest() {
        let mut store = Reports::default();
        let t = trace(1);
        let now = Instant::now();
        dispatch(&mut store, &t, 1, now);
        for ms in [100, 300] {
            event(
                &mut store,
                &t,
                "performance_stage",
                json!({"stage":"session_validation","duration_ms":ms}),
                now,
            );
        }
        event(
            &mut store,
            &t,
            "backend_http",
            json!({"endpoint":"/api/v1/answer?token=secret","duration_ms":1000}),
            now,
        );
        let result = event(
            &mut store,
            &t,
            "performance_candidate",
            json!({"duration_ms":2000,"outcome":"ui_ready_acknowledged","question_text":"secret"}),
            now,
        );
        assert_eq!(result.len(), 1);
        let row = &result[0];
        assert_eq!(row["observed_generation_total_ms"], 2000);
        assert_eq!(
            row["stages_ms"]["session_validation"],
            json!({"count":2,"max_single_span_ms":300})
        );
        assert!(row["stages_ms"]["panel_ready_ack"].is_null());
        assert!(row["provider_calls"].is_null() && row["database_ms"].is_null());
        assert_eq!(row["backend_ai_requests"], 1);
        assert_eq!(row["candidate_id"], "question-1-1");
        assert!(!row.to_string().contains("secret"));
        assert!(event(
            &mut store,
            &t,
            "performance_candidate",
            json!({"duration_ms":2001}),
            now
        )
        .is_empty());
        assert!(event(
            &mut store,
            &t,
            "performance_stage",
            json!({"stage":"candidate_pipeline","outcome":"cancelled"}),
            now
        )
        .is_empty());
    }
    #[test]
    fn retry_is_distinct_failure_and_cancel_are_terminal_once() {
        let mut store = Reports::default();
        let t = trace(2);
        let now = Instant::now();
        for (attempt, outcome) in [(1, "failed"), (2, "cancelled")] {
            event(
                &mut store,
                &t,
                "performance_stage",
                json!({"stage":"candidate_capture","duration_ms":attempt*100}),
                now,
            );
            dispatch(&mut store, &t, attempt, now);
            let rows = event(
                &mut store,
                &t,
                "performance_stage",
                json!({"stage":"candidate_pipeline","duration_ms":500,"outcome":outcome}),
                now,
            );
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0]["attempt"], attempt);
            assert_eq!(rows[0]["outcome"], outcome);
            assert_eq!(
                rows[0]["stages_ms"]["candidate_capture"]["max_single_span_ms"],
                attempt * 100
            );
            assert!(rows[0]["observed_generation_total_ms"].is_null());
        }
    }
    #[test]
    fn store_is_bounded_expiry_and_eviction_are_diagnostic_only() {
        let mut store = Reports::default();
        let now = Instant::now();
        for n in 0..40 {
            dispatch(&mut store, &trace(n), 1, now);
        }
        assert_eq!(store.entries.len(), 32);
        let rows = event(
            &mut store,
            &trace(50),
            "performance_stage",
            json!({"stage":"image_preparation","duration_ms":1}),
            now + Duration::from_secs(601),
        );
        assert_eq!(store.entries.len(), 1);
        assert_eq!(rows.len(), 32);
        assert!(rows.iter().all(|r| r["outcome"] == "diagnostic_expired"));
        // Only fixed stage keys are retained, never arbitrary content or learning state.
        for n in 0..500 {
            event(
                &mut store,
                &trace(50),
                "performance_stage",
                json!({"stage":format!("private_{n}"),"duration_ms":n,"answer":"secret"}),
                now + Duration::from_secs(601),
            );
        }
        assert_eq!(store.entries[0].stages.len(), 1);
        assert!(store.entries[0].summary("cancelled", None).is_none());
    }

    #[test]
    fn synthetic_terminal_probe() {
        // Used with --exact --nocapture in three separate processes. Synthetic only.
        let t = trace(99);
        super::super::emit("application_started", "INFO", None, json!({}));
        super::super::emit(
            "session_check_finished",
            "DEBUG",
            Some(&t),
            json!({"outcome":"active"}),
        );
        for (stage, ms) in [
            ("detection_stability", 3000),
            ("candidate_capture", 40),
            ("candidate_scheduling", 200),
        ] {
            super::super::emit(
                "performance_stage",
                "DEBUG",
                Some(&t),
                json!({"stage":stage,"duration_ms":ms,"attempt":1}),
            );
        }
        super::super::emit(
            "performance_candidate",
            "DEBUG",
            Some(&t),
            json!({"duration_ms":5000,"outcome":"ui_ready_acknowledged"}),
        );
        super::super::emit(
            "synthetic_warning",
            "WARNING",
            Some(&t),
            json!({"error_code":"provider_timeout"}),
        );
        super::super::emit("application_stopped", "INFO", None, json!({}));
    }
}
