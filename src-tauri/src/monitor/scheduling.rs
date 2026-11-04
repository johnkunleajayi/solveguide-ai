//! Await completion directly; sampling and a slow heartbeat must not gate ready answers.
use super::Result;
use serde_json::Value;
use std::{future::Future, pin::Pin, time::Duration};
pub(super) type Heartbeat = Pin<Box<dyn Future<Output = Result<Value>> + Send>>;
pub(super) enum Wake<T> {
    Cancel,
    Sample,
    Worker(tauri::Result<T>),
    Heartbeat(Result<Value>),
}
pub(super) async fn wake<T>(
    worker: &mut Option<tauri::async_runtime::JoinHandle<T>>,
    heartbeat: &mut Option<Heartbeat>,
    cancelled: impl Future<Output = ()>,
    interval: Duration,
) -> Wake<T> {
    tokio::select! { biased;
        _=cancelled=>Wake::Cancel,
        value=async {match heartbeat.as_mut() {Some(h)=>h.await,None=>std::future::pending().await}}=>Wake::Heartbeat(value),
        value=async {match worker.as_mut() {Some(w)=>w.await,None=>std::future::pending().await}}=>Wake::Worker(value),
        _=tokio::time::sleep(interval)=>Wake::Sample,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn worker_completion_does_not_wait_for_sampling_or_heartbeat() {
        tauri::async_runtime::block_on(async {
            let mut worker = Some(tauri::async_runtime::spawn(async { 7 }));
            let mut heartbeat: Option<Heartbeat> = Some(Box::pin(std::future::pending()));
            let result = tokio::time::timeout(
                Duration::from_secs(1),
                wake(
                    &mut worker,
                    &mut heartbeat,
                    std::future::pending(),
                    Duration::from_secs(30),
                ),
            )
            .await
            .unwrap();
            assert!(matches!(result, Wake::Worker(Ok(7))));
        });
    }
    #[test]
    fn cancellation_and_failed_validation_win_over_a_ready_worker() {
        tauri::async_runtime::block_on(async {
            let mut worker = Some(tauri::async_runtime::spawn(async { 7 }));
            let mut heartbeat: Option<Heartbeat> =
                Some(Box::pin(async { Err("session_revoked".into()) }));
            assert!(matches!(
                wake(
                    &mut worker,
                    &mut heartbeat,
                    async {},
                    Duration::from_secs(2)
                )
                .await,
                Wake::Cancel
            ));
            assert!(matches!(
                wake(
                    &mut worker,
                    &mut heartbeat,
                    std::future::pending(),
                    Duration::from_secs(2)
                )
                .await,
                Wake::Heartbeat(Err(_))
            ));
            worker.take().unwrap().abort();
        });
    }
}
