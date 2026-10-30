//! Reuses the existing providers through a testable, sequential native boundary.
use super::{fingerprint, Result};
use serde_json::Value;
use std::future::Future;
pub(super) trait Services: Sync {
    fn session(&self) -> impl Future<Output = Result<()>> + Send;
    fn vision(&self, payload: Value) -> impl Future<Output = Result<Value>> + Send;
    fn answer(&self, observation: Value) -> impl Future<Output = Result<Value>> + Send;
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
    services.session().await?;
    let observation = services.vision(image).await?;
    let signature = fingerprint(&observation);
    if observation["status"] != "detected"
        || observation["question_text"]
            .as_str()
            .is_none_or(|s| s.trim().is_empty())
        || observation["extraction_confidence"].as_f64().unwrap_or(0.0) < 0.65
        || observation["question_type"] == "unknown"
    {
        return Ok(Outcome {
            observation,
            answer: None,
            fingerprint: signature,
            message: "No clear question detected. Waiting for a meaningful page change.",
        });
    }
    if last.as_ref() == Some(&signature) {
        return Ok(Outcome {
            observation,
            answer: None,
            fingerprint: signature,
            message: "Same question recognized. No additional answer request was sent.",
        });
    }
    services.session().await?;
    let answer = services.answer(observation.clone()).await?;
    services.session().await?;
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
        async fn session(&self) -> Result<()> {
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
            } else {
                Ok(json!({"status":"answered"}))
            }
        }
    }
    #[test]
    fn auto_pipeline_is_sequential_and_session_checked() {
        tauri::async_runtime::block_on(async {
            let f = Fake::new();
            assert!(execute(&f, json!({}), None).await.unwrap().answer.is_some());
            assert_eq!(
                *f.events.lock().unwrap(),
                vec!["session", "vision", "session", "answer", "session"]
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
