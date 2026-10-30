//! Preparation metadata only. Credentials remain inside AuthState.
use crate::auth::{authorize, error, AuthError, AuthState};
use crate::context_library::{identifier, Request};
use reqwest::Method;
use serde::{Deserialize, Serialize};
use tauri::Manager;
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Draft {
    revision: Option<u32>,
    purpose: String,
    custom_purpose: Option<String>,
    objective: String,
    document_ids: Vec<String>,
    mode: String,
    allow_context_transmission: bool,
}
#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    Current {},
    Active {},
    Save {
        draft: Draft,
    },
    Ready {
        id: String,
        revision: u32,
    },
    Start {
        preparation_id: String,
        revision: u32,
        replace_active_id: Option<String>,
    },
    End {
        id: String,
        revision: u32,
    },
}
fn valid_revision(value: u32) -> Result<(), AuthError> {
    if value == 0 || value >= i32::MAX as u32 {
        Err(error("invalid_request"))
    } else {
        Ok(())
    }
}
fn prepare(operation: Operation) -> Result<Request, AuthError> {
    let (method, suffix, body) = match operation {
        Operation::Current {} => (Method::GET, "/preparation".into(), None),
        Operation::Active {} => (Method::GET, "/sessions/active".into(), None),
        Operation::Save { draft } => {
            if let Some(revision) = draft.revision {
                valid_revision(revision)?;
            }
            if ![
                "general_learning",
                "certification_practice",
                "interview_preparation",
                "technical_assessment_practice",
                "research_study",
                "custom",
            ]
            .contains(&draft.purpose.as_str())
                || !["general", "context_guided", "materials_only"].contains(&draft.mode.as_str())
                || draft.objective.trim().is_empty()
                || draft.objective.chars().count() > 2000
                || draft
                    .custom_purpose
                    .as_ref()
                    .is_some_and(|v| v.chars().count() > 100)
                || draft.document_ids.len() > 5
            {
                return Err(error("invalid_request"));
            }
            for id in &draft.document_ids {
                identifier(id)?;
            }
            (
                Method::PUT,
                "/preparation".into(),
                Some(serde_json::to_value(draft).map_err(|_| error("invalid_request"))?),
            )
        }
        Operation::Ready { id, revision } => {
            identifier(&id)?;
            valid_revision(revision)?;
            (
                Method::POST,
                format!("/preparation/{id}/ready"),
                Some(serde_json::json!({"revision":revision})),
            )
        }
        Operation::End { id, revision } => {
            identifier(&id)?;
            valid_revision(revision)?;
            (
                Method::POST,
                format!("/sessions/{id}/end"),
                Some(serde_json::json!({"revision":revision})),
            )
        }
        Operation::Start {
            preparation_id,
            revision,
            replace_active_id,
        } => {
            identifier(&preparation_id)?;
            valid_revision(revision)?;
            if let Some(id) = &replace_active_id {
                identifier(id)?;
            }
            (
                Method::POST,
                "/sessions/start".into(),
                Some(
                    serde_json::json!({"preparation_id":preparation_id,"revision":revision,"replace_active_id":replace_active_id}),
                ),
            )
        }
    };
    let body = body
        .map(|v| serde_json::to_vec(&v).map(|b| ("application/json", None, b)))
        .transpose()
        .map_err(|_| error("invalid_request"))?;
    Ok(Request {
        method,
        suffix,
        body,
    })
}
#[tauri::command]
pub async fn session_request(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
    operation: Operation,
) -> Result<serde_json::Value, AuthError> {
    authorize(&window)?;
    if matches!(&operation, Operation::End { .. } | Operation::Start { .. }) {
        app.state::<crate::monitor::MonitorState>()
            .log_action("stop", "session_transition");
        app.state::<crate::monitor::MonitorState>().stop(
            &app,
            false,
            "stopped",
            "Learning session transition. Monitoring stopped.",
        );
    }
    state
        .learning_request(state.session_epoch(), prepare(operation)?)
        .await
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn narrow_operations() {
        assert!(prepare(Operation::End {
            id: "../auth".into(),
            revision: 1
        })
        .is_err());
        assert!(serde_json::from_value::<Operation>(
            serde_json::json!({"kind":"current","url":"https://example.com"})
        )
        .is_err());
        let r = prepare(Operation::Start {
            preparation_id: "00000000-0000-0000-0000-000000000001".into(),
            revision: 1,
            replace_active_id: None,
        })
        .unwrap();
        assert_eq!(r.suffix, "/sessions/start");
        assert_eq!(r.method, Method::POST);
    }
}
