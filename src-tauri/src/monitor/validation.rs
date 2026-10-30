//! One bounded server check; only overlapping callers share a result. No TTL auth cache.
use super::Result;
use serde_json::Value;
use std::{
    future::Future,
    time::{Duration, Instant},
};

pub(super) const DEADLINE: Duration = Duration::from_secs(12);
#[derive(Default)]
pub(super) struct Checks(tokio::sync::Mutex<Option<(Instant, Result<Value>)>>);
impl Checks {
    pub async fn run<F, Fut>(&self, request: F) -> Result<(Value, bool)>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<Value>>,
    {
        let requested = Instant::now();
        let mut slot = self.0.lock().await;
        if let Some((finished, result)) = slot.as_ref() {
            if *finished >= requested {
                return result.clone().map(|v| (v, true));
            }
        }
        let result = request().await;
        *slot = Some((Instant::now(), result.clone()));
        result.map(|v| (v, false))
    }
}
pub(super) async fn bounded<T>(operation: impl Future<Output = Result<T>>) -> Result<T> {
    tokio::time::timeout(DEADLINE, operation)
        .await
        .map_err(|_| "session_check_timeout".to_owned())?
}
pub(super) async fn cancellable<T>(
    operation: impl Future<Output = Result<T>>,
    cancelled: impl Future<Output = ()>,
) -> Result<T> {
    tokio::select! { biased; _ = cancelled => Err("request_cancelled".into()), result = bounded(operation) => result }
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    #[test]
    fn valid_response_slower_than_old_deadline_succeeds() {
        tauri::async_runtime::block_on(async {
            assert_eq!(DEADLINE, Duration::from_secs(12));
            assert_eq!(
                bounded(async {
                    tokio::time::sleep(Duration::from_millis(5100)).await;
                    Ok(7)
                })
                .await
                .unwrap(),
                7
            );
        });
    }
    #[test]
    fn actual_timeout_remains_specific_and_cancellation_is_immediate() {
        tauri::async_runtime::block_on(async {
            let started = Instant::now();
            let result = cancellable(std::future::pending::<Result<()>>(), async {}).await;
            assert_eq!(result.unwrap_err(), "request_cancelled");
            assert!(started.elapsed() < Duration::from_secs(1));
            assert_eq!(
                bounded(std::future::pending::<Result<()>>())
                    .await
                    .unwrap_err(),
                "session_check_timeout"
            );
        });
    }
    #[test]
    fn overlapping_requests_coalesce_but_sequential_checks_are_fresh() {
        tauri::async_runtime::block_on(async {
            let checks = Arc::new(Checks::default());
            let calls = Arc::new(AtomicUsize::new(0));
            let a = checks.clone();
            let count = calls.clone();
            let (ready, wait) = tokio::sync::oneshot::channel();
            let first = tauri::async_runtime::spawn(async move {
                a.run(|| async {
                    count.fetch_add(1, Ordering::SeqCst);
                    ready.send(()).unwrap();
                    tokio::time::sleep(Duration::from_millis(50)).await;
                    Ok(json!({"revision":1}))
                })
                .await
            });
            wait.await.unwrap();
            let second = checks
                .run(|| async {
                    calls.fetch_add(1, Ordering::SeqCst);
                    Ok(json!({}))
                })
                .await
                .unwrap();
            assert!(second.1);
            assert_eq!(second.0["revision"], 1);
            first.await.unwrap().unwrap();
            assert_eq!(calls.load(Ordering::SeqCst), 1);
            assert_eq!(
                checks
                    .run(|| async { Err("session_revoked".into()) })
                    .await
                    .unwrap_err(),
                "session_revoked"
            );
            assert_eq!(
                checks
                    .run(|| async { Err("session_revision_mismatch".into()) })
                    .await
                    .unwrap_err(),
                "session_revision_mismatch"
            );
        });
    }
    #[test]
    fn cancellation_drops_inflight_work_and_releases_validation_slot() {
        struct Guard(Arc<AtomicUsize>);
        impl Drop for Guard {
            fn drop(&mut self) {
                self.0.fetch_add(1, Ordering::SeqCst);
            }
        }
        tauri::async_runtime::block_on(async {
            let checks = Checks::default();
            let dropped = Arc::new(AtomicUsize::new(0));
            let result = cancellable(
                checks.run(|| async {
                    let _guard = Guard(dropped.clone());
                    std::future::pending::<Result<Value>>().await
                }),
                async { tokio::time::sleep(Duration::from_millis(10)).await },
            )
            .await;
            assert_eq!(result.unwrap_err(), "request_cancelled");
            assert_eq!(dropped.load(Ordering::SeqCst), 1);
            assert!(
                !checks
                    .run(|| async { Ok(json!({"revision":2})) })
                    .await
                    .unwrap()
                    .1
            );
        });
    }
}
