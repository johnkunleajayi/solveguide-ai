//! DEBUG-only metadata, one ephemeral clock per observed source generation. No content.
use crate::diagnostics::{self as diag, Trace};
use serde::Serialize;
use serde_json::json;
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::{Duration, Instant},
};

#[derive(Default, Debug)]
pub(super) struct Marks {
    pub stable: Option<u64>,
    pub dispatch: Option<u64>,
    pub worker: Option<u64>,
    pub publish: Option<u64>,
    capture_count: u64,
    capture_sum: u64,
    capture_max: u64,
    gap_max: u64,
}
pub(super) fn interval(start: Option<u64>, end: Option<u64>) -> Option<u64> {
    end?.checked_sub(start?)
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(super) struct Descriptor {
    trace_id: String,
    candidate_id: String,
    generation: u64,
    observed_to_snapshot_ms: u64,
}
pub(super) struct Candidate {
    pub trace: Trace,
    pub started: Instant,
    pub generation: u64,
    marks: Mutex<Marks>,
    finished: AtomicBool,
}
impl Candidate {
    pub fn new(trace: Trace, generation: u64) -> Self {
        Self {
            trace,
            started: Instant::now(),
            generation,
            marks: Mutex::new(Marks::default()),
            finished: AtomicBool::new(false),
        }
    }
    pub fn elapsed(&self) -> u64 {
        self.started.elapsed().as_millis() as u64
    }
    pub fn stage(&self, stage: &'static str) -> diag::StageTimer {
        diag::StageTimer::new(self.trace.clone(), stage, "candidate").origin(self.started)
    }
    pub fn capture(&self, duration: Duration, gap: Option<Duration>) {
        let mut m = self.marks.lock().unwrap_or_else(|p| p.into_inner());
        let ms = duration.as_millis() as u64;
        m.capture_count += 1;
        m.capture_sum += ms;
        m.capture_max = m.capture_max.max(ms);
        m.gap_max = m
            .gap_max
            .max(gap.map(|d| d.as_millis() as u64).unwrap_or(0));
    }
    pub fn candidate_capture(&self, started: Instant, finished: Instant) {
        diag::emit(
            "performance_stage",
            "DEBUG",
            Some(&self.trace),
            json!({"stage":"candidate_capture","latency_category":"application","duration_ms":finished.saturating_duration_since(started).as_millis() as u64,"start_offset_ms":started.saturating_duration_since(self.started).as_millis() as u64,"end_offset_ms":finished.saturating_duration_since(self.started).as_millis() as u64,"outcome":"completed"}),
        );
    }
    pub fn stable(&self) {
        let mut m = self.marks.lock().unwrap_or_else(|p| p.into_inner());
        if m.stable.is_none() {
            let now = self.elapsed();
            m.stable = Some(now);
            diag::emit(
                "performance_stage",
                "DEBUG",
                Some(&self.trace),
                json!({"stage":"detection_stability","duration_ms":now,"start_offset_ms":0,"end_offset_ms":now,"outcome":"accepted"}),
            );
        }
    }
    pub fn dispatch(&self, attempt: u32, retry: bool) {
        let mut m = self.marks.lock().unwrap_or_else(|p| p.into_inner());
        let now = self.elapsed();
        m.dispatch.get_or_insert(now);
        diag::emit(
            "performance_stage",
            "DEBUG",
            Some(&self.trace),
            json!({"stage":"candidate_scheduling","duration_ms":interval(m.stable,Some(now)),"start_offset_ms":m.stable,"end_offset_ms":now,"attempt":attempt,"reason":if retry{"candidate_retry"}else{"initial_dispatch"},"outcome":"dispatched"}),
        );
    }
    pub fn worker_done(&self) {
        self.marks.lock().unwrap_or_else(|p| p.into_inner()).worker = Some(self.elapsed());
    }
    pub fn published(&self) {
        let mut m = self.marks.lock().unwrap_or_else(|p| p.into_inner());
        let now = self.elapsed();
        m.publish = Some(now);
        diag::emit(
            "performance_stage",
            "DEBUG",
            Some(&self.trace),
            json!({"stage":"worker_collection","duration_ms":interval(m.worker,Some(now)),"start_offset_ms":m.worker,"end_offset_ms":now,"outcome":"published"}),
        );
    }
    pub fn descriptor(&self) -> Descriptor {
        Descriptor {
            trace_id: self.trace.trace_id.clone(),
            candidate_id: self.trace.candidate_id.clone().unwrap_or_default(),
            generation: self.generation,
            observed_to_snapshot_ms: self.elapsed(),
        }
    }
    pub fn ready(&self, receipt_to_ready: u64, validation: u64) {
        if self.finished.load(Ordering::Acquire) {
            return;
        }
        let now = self.elapsed();
        let m = self.marks.lock().unwrap_or_else(|p| p.into_inner());
        diag::emit(
            "performance_stage",
            "DEBUG",
            Some(&self.trace),
            json!({"stage":"panel_ready_ack","duration_ms":interval(m.publish,Some(now)),"receipt_to_ready_ms":receipt_to_ready,"validation_ms":validation,"outcome":"ui_ready"}),
        );
        drop(m);
        self.finish("ui_ready_acknowledged");
    }
    pub fn finish(&self, outcome: &'static str) {
        if self.finished.swap(true, Ordering::AcqRel) {
            return;
        }
        let m = self.marks.lock().unwrap_or_else(|p| p.into_inner());
        // No continuous summaries for candidates never admitted to a pipeline.
        if m.dispatch.is_none() {
            return;
        }
        diag::emit(
            "performance_candidate",
            "DEBUG",
            Some(&self.trace),
            json!({"stage":"observed_to_terminal","duration_ms":self.elapsed(),"outcome":outcome,"capture_count":m.capture_count,"capture_sum_ms":m.capture_sum,"capture_max_ms":m.capture_max,"sample_gap_max_ms":m.gap_max}),
        );
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn intervals_are_not_sums_and_missing_or_backwards_clocks_remain_unknown() {
        assert_eq!(interval(Some(100), Some(1100)), Some(1000));
        assert_eq!(interval(None, Some(1100)), None);
        assert_eq!(interval(Some(1100), Some(100)), None);
        // Two overlapping child intervals do not define a 2-second parent.
        assert_eq!(interval(Some(0), Some(1000)), Some(1000));
    }
    #[test]
    fn serialized_metadata_has_no_content_and_current_generation_is_explicit() {
        let c = Candidate::new(
            Trace::candidate("live-a-b-1", 1, 2, "timing"),
            (1 << 32) + 2,
        );
        let descriptor = serde_json::to_value(c.descriptor()).unwrap();
        assert_eq!(descriptor["candidateId"], "question-1-2");
        assert_eq!(descriptor["generation"], (1u64 << 32) + 2);
        assert_eq!(descriptor.as_object().unwrap().len(), 4);
        assert!(interval(None, Some(c.elapsed())).is_none());
    }
}
