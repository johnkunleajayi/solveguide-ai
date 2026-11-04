//! Reuses the existing providers through a testable, sequential native boundary.
use super::{fingerprint, Result};
use serde_json::Value;
use std::future::Future;
pub(super) trait Services: Sync {
    fn session(&self, role: &'static str) -> impl Future<Output = Result<()>> + Send;
    fn vision(&self, payload: Value) -> impl Future<Output = Result<Value>> + Send;
    fn answer(&self, observation: Value) -> impl Future<Output = Result<Value>> + Send;
    fn trace(&self) -> crate::diagnostics::Trace {
        crate::diagnostics::Trace::local("synthetic-pipeline")
    }
}
pub(super) struct Outcome {
    pub observation: Value,
    pub answer: Option<Value>,
    pub fingerprint: String,
    pub message: &'static str,
}
pub(super) async fn execute(
    services: &impl Services,
    image: Value,
    last: Option<String>,
) -> Result<Outcome> {
    services.session("pre_vision").await?;
    let observation = services.vision(image).await?;
    let mut classification = crate::diagnostics::StageTimer::new(
        services.trace(),
        "observation_gate_dedup",
        "neutral_validation",
    );
    let signature = fingerprint(&observation);
    if observation["status"] != "detected"
        || observation["question_text"]
            .as_str()
            .is_none_or(|s| s.trim().is_empty())
        || observation["extraction_confidence"].as_f64().unwrap_or(0.0) < 0.65
        || observation["question_type"] == "unknown"
        || observation["visual_task"]["complete"] == false
        || ((observation["visual_task"]["kind"] == "editing_prompt"
            || observation["visual_task"]["requested_output"] == "editing_prompt")
            && observation["visual_task"]["direction"] != "established")
    {
        classification.finish("incomplete");
        services.session("post_observation").await?;
        return Ok(Outcome {
            observation,
            answer: None,
            fingerprint: signature,
            message: "No clear question detected. Waiting for a meaningful page change.",
        });
    }
    if last.as_ref() == Some(&signature) {
        classification.finish("duplicate");
        services.session("post_observation").await?;
        return Ok(Outcome {
            observation,
            answer: None,
            fingerprint: signature,
            message: "Same question recognized. No additional answer request was sent.",
        });
    }
    classification.finish("accepted");
    // The session-bound backend answer performs fresh pre/post configuration and
    // post-provider credential checks. Do not repeat them as separate HTTP calls.
    let answer = services.answer(observation.clone()).await?;
    Ok(Outcome {
        observation,
        answer: Some(answer),
        fingerprint: signature,
        message: "Suggested answer ready. Review the question and supporting evidence.",
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::Mutex;
    struct Fake {
        events: Mutex<Vec<&'static str>>,
        observation: Value,
        failure: Option<&'static str>,
    }
    impl Fake {
        fn new() -> Self {
            Self {
                events: Mutex::new(vec![]),
                observation: json!({"status":"detected","question_type":"short_answer","question_text":"A practice question","options":[],"extraction_confidence":0.9}),
                failure: None,
            }
        }
    }
    impl Services for Fake {
        async fn session(&self, _role: &'static str) -> Result<()> {
            let mut events = self.events.lock().unwrap();
            events.push("session");
            if self.failure == Some("initial")
                || self.failure == Some("ended")
                    && events.iter().filter(|e| **e == "session").count() == 3
            {
                Err("session_changed".into())
            } else {
                Ok(())
            }
        }
        async fn vision(&self, _image: Value) -> Result<Value> {
            self.events.lock().unwrap().push("vision");
            if self.failure == Some("vision") {
                Err("provider_timeout".into())
            } else {
                Ok(self.observation.clone())
            }
        }
        async fn answer(&self, observation: Value) -> Result<Value> {
            assert_eq!(observation, self.observation);
            self.events.lock().unwrap().push("answer");
            if self.failure == Some("answer") {
                Err("provider_timeout".into())
            } else if self.failure == Some("ended") {
                // Models the server's fresh post-provider session/revocation check.
                Err("session_changed".into())
            } else {
                Ok(json!({"status":"answered"}))
            }
        }
    }
    #[test]
    fn visual_tasks_preserve_detail_identity_and_use_the_same_authorized_pipeline() {
        tauri::async_runtime::block_on(async {
            let mut f = Fake::new();
            f.observation["question_type"] = json!("visual_reasoning");
            f.observation["visual_task"] = json!({"kind":"editing_prompt","complete":true,"direction":"established","observed_changes":["title becomes mint"]});
            let before = fingerprint(&f.observation);
            f.observation["visual_task"]["observed_changes"] = json!(["title moves right"]);
            assert_ne!(before, fingerprint(&f.observation));
            let single_space = fingerprint(&f.observation);
            f.observation["visual_task"]["observed_changes"] = json!(["title  moves right"]);
            assert_ne!(single_space, fingerprint(&f.observation));
            assert!(execute(&f, json!({}), Some(before))
                .await
                .unwrap()
                .answer
                .is_some());
            assert_eq!(
                *f.events.lock().unwrap(),
                vec!["session", "vision", "answer"]
            );
            for incomplete in [true, false] {
                f.events.lock().unwrap().clear();
                f.observation["visual_task"]["complete"] = json!(!incomplete);
                f.observation["visual_task"]["direction"] = json!("ambiguous");
                assert!(execute(&f, json!({}), None).await.unwrap().answer.is_none());
                assert!(!f.events.lock().unwrap().contains(&"answer"));
            }
        });
    }
    #[test]
    fn auto_pipeline_is_sequential_and_session_checked() {
        tauri::async_runtime::block_on(async {
            let f = Fake::new();
            assert!(execute(&f, json!({}), None).await.unwrap().answer.is_some());
            assert_eq!(
                *f.events.lock().unwrap(),
                vec!["session", "vision", "answer"]
            );
        });
    }
    #[test]
    fn duplicate_or_unclear_question_does_not_trigger_answer() {
        tauri::async_runtime::block_on(async {
            for unclear in [false, true] {
                let mut f = Fake::new();
                let previous = Some(fingerprint(&f.observation));
                if unclear {
                    f.observation["status"] = json!("no_question");
                }
                assert!(execute(&f, json!({}), previous)
                    .await
                    .unwrap()
                    .answer
                    .is_none());
                assert!(!f.events.lock().unwrap().contains(&"answer"));
            }
        });
    }
    #[test]
    fn no_provider_before_authorization_and_no_late_result_after_end() {
        tauri::async_runtime::block_on(async {
            for failure in ["initial", "ended", "vision", "answer"] {
                let mut f = Fake::new();
                f.failure = Some(failure);
                assert!(execute(&f, json!({}), None).await.is_err());
                if failure == "initial" {
                    assert_eq!(*f.events.lock().unwrap(), vec!["session"]);
                }
            }
        });
    }
}
