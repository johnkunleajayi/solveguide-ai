//! Explicit, typed library operations. No frontend paths, credentials or arbitrary URLs.
use crate::auth::{authorize, error, AuthError, AuthState};
use reqwest::Method;
use serde::Deserialize;

#[cfg(windows)]
const MAX_FILE: u64 = 20 * 1024 * 1024; // Hard ceiling; backend configuration may be lower.

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    List { cursor: Option<String> },
    Limits,
    Detail { id: String },
    Rename { id: String, title: String },
    Delete { id: String },
    Paste { title: String, text: String },
    Upload,
}
pub(crate) type RequestBody = (&'static str, Option<String>, Vec<u8>);
pub(crate) struct Request {
    pub method: Method,
    pub suffix: String,
    pub body: Option<RequestBody>,
}
fn encode(value: &str) -> String {
    value
        .bytes()
        .map(|c| {
            if c.is_ascii_alphanumeric() || b"-_.~".contains(&c) {
                (c as char).to_string()
            } else {
                format!("%{c:02X}")
            }
        })
        .collect()
}
fn identifier(value: &str) -> Result<(), AuthError> {
    if value.len() != 36
        || !value.bytes().enumerate().all(|(i, c)| {
            if [8, 13, 18, 23].contains(&i) {
                c == b'-'
            } else {
                c.is_ascii_hexdigit()
            }
        })
    {
        return Err(error("invalid_request"));
    }
    Ok(())
}
fn title(value: &str) -> Result<(), AuthError> {
    if value.trim().is_empty() || value.chars().count() > 200 || value.chars().any(char::is_control)
    {
        return Err(error("invalid_request"));
    }
    Ok(())
}
fn json_body(value: serde_json::Value) -> Result<Option<RequestBody>, AuthError> {
    Ok(Some((
        "application/json",
        None,
        serde_json::to_vec(&value).map_err(|_| error("invalid_request"))?,
    )))
}
fn request(operation: Operation) -> Result<Request, AuthError> {
    let (method, suffix, body) = match operation {
        Operation::List { cursor } => {
            if cursor.as_ref().is_some_and(|v| v.len() > 150) {
                return Err(error("invalid_request"));
            }
            (
                Method::GET,
                cursor
                    .map(|v| format!("?cursor={}", encode(&v)))
                    .unwrap_or_default(),
                None,
            )
        }
        Operation::Limits => (Method::GET, "/limits".into(), None),
        Operation::Detail { id } => {
            identifier(&id)?;
            (Method::GET, format!("/{id}"), None)
        }
        Operation::Delete { id } => {
            identifier(&id)?;
            (Method::DELETE, format!("/{id}"), None)
        }
        Operation::Rename { id, title: value } => {
            identifier(&id)?;
            title(&value)?;
            (
                Method::PATCH,
                format!("/{id}"),
                json_body(serde_json::json!({"title":value}))?,
            )
        }
        Operation::Paste { title: value, text } => {
            title(&value)?;
            if text.is_empty() || text.len() > 4_000_000 || text.chars().count() > 1_000_000 {
                return Err(error("document_too_large"));
            }
            (
                Method::POST,
                "/text".into(),
                json_body(serde_json::json!({"title":value,"text":text}))?,
            )
        }
        Operation::Upload => return Err(error("invalid_request")),
    };
    Ok(Request {
        method,
        suffix,
        body,
    })
}

#[cfg(any(windows, test))]
fn file_type(filename: &str) -> Result<&'static str, AuthError> {
    match filename
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "pdf" => Ok("application/pdf"),
        "docx" => Ok("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "txt" => Ok("text/plain"),
        _ => Err(error("unsupported_document")),
    }
}

#[cfg(windows)]
async fn pick(window: &tauri::WebviewWindow) -> Result<Option<Request>, AuthError> {
    let Some(file) = rfd::AsyncFileDialog::new()
        .set_parent(window)
        .set_title("Add a Context Library document")
        .add_filter("Learning documents", &["pdf", "docx", "txt"])
        .pick_file()
        .await
    else {
        return Ok(None);
    };
    let path = file.path().to_owned();
    // Bound the actual opened file (not just a raced path stat). Never expose the path to JS.
    tauri::async_runtime::spawn_blocking(move || {
        use std::io::Read;
        let filename = path
            .file_name()
            .and_then(|v| v.to_str())
            .filter(|v| v.chars().count() <= 255)
            .ok_or_else(|| error("invalid_document"))?
            .to_owned();
        let content_type = file_type(&filename)?;
        let file = std::fs::File::open(&path).map_err(|_| error("document_unavailable"))?;
        if !file
            .metadata()
            .map_err(|_| error("document_unavailable"))?
            .is_file()
        {
            return Err(error("invalid_document"));
        }
        let mut bytes = Vec::new();
        file.take(MAX_FILE + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| error("document_unavailable"))?;
        if bytes.is_empty() || bytes.len() as u64 > MAX_FILE {
            return Err(error("document_too_large"));
        }
        Ok(Some(Request {
            method: Method::POST,
            suffix: "/upload".into(),
            body: Some((content_type, Some(encode(&filename)), bytes)),
        }))
    })
    .await
    .map_err(|_| error("document_unavailable"))?
}
#[cfg(not(windows))]
async fn pick(_: &tauri::WebviewWindow) -> Result<Option<Request>, AuthError> {
    Err(error("unsupported_platform"))
}

#[tauri::command]
pub async fn library_request(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AuthState>,
    operation: Operation,
) -> Result<serde_json::Value, AuthError> {
    authorize(&window)?;
    let epoch = state.session_epoch();
    state.library_credential_present(epoch).await?;
    let request = if matches!(operation, Operation::Upload) {
        // Validate the backend session before opening a dialog, not just a local flag.
        let access = state
            .library_request(epoch, request(Operation::Limits)?)
            .await?;
        if access["ok"] != true {
            return Ok(access);
        }
        let Some(request) = pick(&window).await? else {
            return Ok(serde_json::json!({"ok":true,"status":204,"data":null}));
        };
        request
    } else {
        request(operation)?
    };
    state.library_request(epoch, request).await
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn routes_and_inputs_are_narrow() {
        assert!(request(Operation::Detail {
            id: "../../auth".into()
        })
        .is_err());
        assert!(request(Operation::Paste {
            title: " ".into(),
            text: "notes".into()
        })
        .is_err());
        assert!(file_type("notes.exe").is_err());
        assert_eq!(file_type("notes.PDF").unwrap(), "application/pdf");
        let req = request(Operation::Rename {
            id: "00000000-0000-0000-0000-000000000001".into(),
            title: "Notes".into(),
        })
        .unwrap();
        assert_eq!(req.method, Method::PATCH);
        assert!(!req.suffix.contains("Notes"));
        assert_eq!(encode("a b.txt"), "a%20b.txt");
    }
    #[test]
    fn credential_and_old_epoch_fail_closed() {
        let state = AuthState::default();
        let result =
            tauri::async_runtime::block_on(state.library_credential_present(state.session_epoch()));
        assert!(result.is_err());
    }
}
