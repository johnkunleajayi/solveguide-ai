//! Bounded ephemeral captures. No paths, persistence, credential IPC or new provider boundary.
use super::*;

const MAX_ENCODED_BYTES: usize = 13_981_016; // Base64 of the existing 10 MiB combined image limit.
#[derive(Clone, Serialize)]
pub(super) struct Status {
    count: usize,
    adding: bool,
    solving: bool,
}
#[derive(Default)]
pub(super) struct Collection {
    images: Vec<String>,
    adding: bool,
    solving: bool,
}
impl Collection {
    fn push(&mut self, image: String) -> Result<()> {
        if self.images.len() >= 5 {
            return Err("capture_limit".into());
        }
        if self.images.iter().map(String::len).sum::<usize>() + image.len() > MAX_ENCODED_BYTES {
            return Err("image_too_large".into());
        }
        self.images.push(image);
        Ok(())
    }
    fn payload(&mut self) -> Result<Value> {
        if !(2..=5).contains(&self.images.len()) || self.adding || self.solving {
            return Err("multi_not_ready".into());
        }
        self.solving = true;
        let mut images = std::mem::take(&mut self.images).into_iter();
        Ok(
            json!({"media_type":"image/png", "image_base64":images.next().unwrap(),
            "additional_images":images.map(|image| json!({"media_type":"image/png","image_base64":image})).collect::<Vec<_>>() }),
        )
    }
}
fn sync(inner: &mut Inner) {
    inner.snapshot.multi_capture = inner.multi.as_ref().map(|c| Status {
        count: if c.solving {
            inner.snapshot.multi_capture.as_ref().map_or(0, |s| s.count)
        } else {
            c.images.len()
        },
        adding: c.adding,
        solving: c.solving,
    });
}
fn invalidate(inner: &mut Inner) {
    inner.snapshot.generation = (inner.run << 32) + (inner.snapshot.generation & 0xffff_ffff) + 1;
    if let Some(worker) = inner.worker.take() {
        worker.abort();
    }
    if let Some(clock) = inner.snapshot.clock.take() {
        clock.finish("cancelled");
    }
    inner.snapshot.performance = None;
    inner.answer_action = Some(false);
}
pub(super) fn start(state: &MonitorState) -> Result<()> {
    let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
    if inner.cancel.as_ref().is_none_or(|c| c.stopped())
        || inner.selection.is_none()
        || inner.multi.is_some()
    {
        return Err("not_monitoring".into());
    }
    invalidate(&mut inner);
    inner.multi = Some(Collection::default());
    inner.snapshot.message =
        "Multi-Capture: add 2-5 views of one question, in reading order.".into();
    sync(&mut inner);
    state.4.notify_one();
    Ok(())
}
pub(super) fn cancel(state: &MonitorState) -> Result<()> {
    let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
    if inner.multi.is_none() {
        return Err("multi_not_active".into());
    }
    invalidate(&mut inner);
    inner.multi = None;
    inner.snapshot.multi_capture = None;
    inner.resume_detection = inner.snapshot.answer.is_none();
    inner.snapshot.phase = if inner.snapshot.answer.is_some() {
        "answer_ready"
    } else {
        "monitoring"
    }
    .into();
    inner.snapshot.message = "Multi-Capture cancelled. Existing answer retained; otherwise waiting for a new page change.".into();
    state.4.notify_one();
    Ok(())
}
pub(super) fn remove(state: &MonitorState, index: usize) -> Result<()> {
    let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
    let collection = inner.multi.as_mut().ok_or("multi_not_active")?;
    if collection.adding || collection.solving || index >= collection.images.len() {
        return Err("multi_not_ready".into());
    }
    collection.images.remove(index);
    sync(&mut inner);
    Ok(())
}
pub(super) async fn add(app: &tauri::AppHandle) -> Result<()> {
    let state = app.state::<MonitorState>();
    let (run, generation, selection, cancel) = {
        let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
        let selection = inner.selection.clone().ok_or("source_required")?;
        let cancel = inner
            .cancel
            .clone()
            .filter(|c| !c.stopped())
            .ok_or("not_monitoring")?;
        let collection = inner.multi.as_mut().ok_or("multi_not_active")?;
        if collection.adding || collection.solving || collection.images.len() >= 5 {
            return Err("capture_limit".into());
        }
        collection.adding = true;
        sync(&mut inner);
        (inner.run, inner.snapshot.generation, selection, cancel)
    };
    let result: Result<String> = async {
        tokio::select! { _ = cancel.cancelled() => return Err("request_cancelled".into()), result = active(app, &selection) => { result?; } }
        let permit = state.2.clone().acquire_owned().await.map_err(|_| "request_cancelled")?;
        let capture = app.state::<Arc<capture::CaptureState>>().inner().clone();
        tauri::async_runtime::spawn_blocking(move || {
            let _permit = permit;
            let target = selection.target.ok_or("source_unavailable")?;
            let frame = capture::sample(&capture, selection.source, &cancel.flag, &target).map_err(|e|e.code.to_owned())?;
            frame.encode().map(|image|image.image_base64).map_err(|e|e.code.to_owned())
        }).await.map_err(|_| "capture_failed")?
    }.await;
    let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
    if inner.run != run || inner.snapshot.generation != generation {
        return Err("request_cancelled".into());
    }
    let collection = inner.multi.as_mut().ok_or("request_cancelled")?;
    collection.adding = false;
    let result = result.and_then(|image| collection.push(image));
    sync(&mut inner);
    result
}
pub(super) async fn solve(app: &tauri::AppHandle) -> Result<()> {
    let state = app.state::<MonitorState>();
    let (run, generation, selection, payload) = {
        let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
        let selection = inner.selection.clone().ok_or("source_required")?;
        if inner.cancel.as_ref().is_none_or(|c| c.stopped()) {
            return Err("not_monitoring".into());
        }
        let payload = inner.multi.as_mut().ok_or("multi_not_active")?.payload()?;
        invalidate(&mut inner);
        inner.answer_action = None; // This explicit worker owns the new generation.
        inner.snapshot.answer = None;
        inner.snapshot.observation = None;
        if let Some((mode, docs)) = inner.next_answer_context.take() {
            inner.snapshot.mode = mode;
            inner.snapshot.document_ids = docs;
        }
        inner.snapshot.phase = "processing".into();
        inner.snapshot.message = "Reading the collected captures as one question...".into();
        sync(&mut inner);
        (inner.run, inner.snapshot.generation, selection, payload)
    };
    let app_worker = app.clone();
    let (permit, ready) = tokio::sync::oneshot::channel();
    let task = tauri::async_runtime::spawn(async move {
        ready.await.map_err(|_| "request_cancelled".to_owned())?;
        let services = NativeServices {
            app: app_worker.clone(),
            selection,
            run,
            generation: generation & 0xffff_ffff,
        };
        let result = pipeline::execute(&services, payload, None).await;
        finish(&app_worker.state::<MonitorState>(), run, generation, result)
    });
    {
        let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
        if inner.run == run
            && inner.snapshot.generation == generation
            && inner.multi.as_ref().is_some_and(|c| c.solving)
        {
            inner.worker = Some(task.inner().abort_handle());
            let _ = permit.send(());
        } else {
            task.abort();
        }
    }
    match task.await {
        Ok(result) => result,
        Err(_) => finish(&state, run, generation, Err("request_cancelled".into())),
    }
}
fn finish(state: &MonitorState, run: u64, generation: u64, result: Result<Outcome>) -> Result<()> {
    let mut inner = state.0.lock().unwrap_or_else(|p| p.into_inner());
    if inner.run != run || inner.snapshot.generation != generation || inner.multi.is_none() {
        return Err("request_cancelled".into());
    }
    inner.worker = None;
    inner.multi = None; // Release every image on success, no-question, error or cancellation.
    inner.snapshot.multi_capture = None;
    inner.answer_action = Some(false);
    inner.resume_detection = true;
    inner.snapshot.phase = "monitoring".into();
    match &result {
        Ok(outcome) => {
            inner.snapshot.observation = Some(outcome.observation.clone());
            inner.snapshot.answer = outcome.answer.clone();
            inner.snapshot.phase = if outcome.answer.is_some() {
                "answer_ready"
            } else {
                "monitoring"
            }
            .into();
            inner.snapshot.message = outcome.message.into();
        }
        Err(_) => {
            inner.snapshot.message =
                "Multi-Capture could not complete. Collect again or use New Capture.".into()
        }
    }
    state.4.notify_one();
    result.map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bounded_ordered_payload_moves_images_out_of_collection() {
        let mut c = Collection::default();
        assert!(c.payload().is_err());
        for index in 0..5 {
            c.push(format!("image-{index}")).unwrap();
        }
        assert!(c.push("extra".into()).is_err());
        c.images.remove(1);
        let payload = c.payload().unwrap();
        assert_eq!(payload["image_base64"], "image-0");
        assert_eq!(payload["additional_images"][0]["image_base64"], "image-2");
        assert!(c.images.is_empty());
        assert!(c.payload().is_err());
        let mut huge = Collection::default();
        assert!(huge.push("x".repeat(MAX_ENCODED_BYTES + 1)).is_err());
        assert!(huge.images.is_empty());
    }
    #[test]
    fn collection_blocks_automatic_updates_even_after_wake_is_consumed() {
        let state = MonitorState::default();
        {
            let mut inner = state.0.lock().unwrap();
            inner.run = 1;
            inner.cancel = Some(Arc::new(Cancellation::new()));
            inner.snapshot.generation = (1 << 32) + 1;
            inner.multi = Some(Collection::default());
        }
        assert!(!state.change(1, |s| s.generation = 0));
        assert!(!state.publish(1, 1, |s| s.answer = Some(json!({"old":true}))));
        let mut inner = state.0.lock().unwrap();
        invalidate(&mut inner);
        assert_eq!(inner.snapshot.generation, (1 << 32) + 2);
    }
    #[test]
    fn solve_finalization_retains_one_answer_and_cleans_up_failures() {
        for success in [false, true] {
            let state = MonitorState::default();
            {
                let mut inner = state.0.lock().unwrap();
                inner.run = 1;
                inner.cancel = Some(Arc::new(Cancellation::new()));
                inner.snapshot.generation = (1 << 32) + 2;
                inner.multi = Some(Collection {
                    solving: true,
                    ..Collection::default()
                });
            }
            let result = if success {
                Ok(Outcome {
                    observation: json!({"question":"combined"}),
                    answer: Some(json!({"solution":true})),
                    fingerprint: String::new(),
                    message: "Ready",
                })
            } else {
                Err("provider_timeout".into())
            };
            assert_eq!(finish(&state, 1, (1 << 32) + 2, result).is_ok(), success);
            let inner = state.0.lock().unwrap();
            assert!(inner.multi.is_none());
            assert!(inner.snapshot.multi_capture.is_none());
            assert_eq!(inner.snapshot.answer.is_some(), success);
            assert!(inner.resume_detection);
        }
    }
    #[test]
    fn cancel_and_shutdown_drop_images_and_reject_old_results() {
        for stop in [false, true] {
            let state = MonitorState::default();
            {
                let mut inner = state.0.lock().unwrap();
                inner.run = 1;
                inner.cancel = Some(Arc::new(Cancellation::new()));
                inner.snapshot.generation = (1 << 32) + 1;
                inner.multi = Some(Collection {
                    images: vec!["private-pixels".into()],
                    ..Collection::default()
                });
                sync(&mut inner);
            }
            if stop {
                state.reset(None, true, "paused", "Paused");
            } else {
                cancel(&state).unwrap();
            }
            assert!(state.0.lock().unwrap().multi.is_none());
            assert!(state.0.lock().unwrap().snapshot.multi_capture.is_none());
            assert!(!state.publish(1, 1, |s| s.answer = Some(json!({"stale":true}))));
            assert!(!serde_json::to_string(&state.0.lock().unwrap().snapshot)
                .unwrap()
                .contains("private-pixels"));
        }
    }
}
