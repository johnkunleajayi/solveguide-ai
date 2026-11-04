//! One owner thread for a monitoring session and its D3D immediate context.
use super::*;
use std::{sync::Arc, thread};
type Reply = mpsc::SyncSender<Result<Frame>>;
pub(super) struct Live {
    requests: mpsc::SyncSender<Reply>,
    pub stop: Arc<AtomicBool>,
    pub run_cancel: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}
impl Live {
    pub fn spawn<F, G, S>(
        run_cancel: Arc<AtomicBool>,
        initialize: F,
    ) -> Result<(Self, mpsc::Receiver<Result<()>>)>
    where
        F: FnOnce(Arc<AtomicBool>) -> Result<(G, S)> + Send + 'static,
        S: FnMut(&AtomicBool) -> Result<Frame> + 'static,
    {
        let (tx, rx) = mpsc::sync_channel::<Reply>(1);
        let (ready, wait) = mpsc::sync_channel(1);
        let stop = Arc::new(AtomicBool::new(false));
        let flag = stop.clone();
        let run = run_cancel.clone();
        let thread = thread::Builder::new()
            .name("solveguide-capture".into())
            .spawn(move || {
                let (apartment, mut sample) = match initialize(flag.clone()) {
                    Ok(value) => value,
                    Err(error) => {
                        let _ = ready.send(Err(error));
                        return;
                    }
                };
                if !flag.load(Ordering::Acquire) && !run.load(Ordering::Acquire) {
                    let _ = ready.send(Ok(()));
                    while !flag.load(Ordering::Acquire) && !run.load(Ordering::Acquire) {
                        match rx.recv_timeout(Duration::from_millis(50)) {
                            Ok(reply) => {
                                let result = sample(&flag);
                                let failed = result.is_err();
                                let _ = reply.try_send(result);
                                if failed {
                                    break;
                                }
                            }
                            Err(mpsc::RecvTimeoutError::Timeout) => {}
                            Err(_) => break,
                        }
                    }
                }
                drop(sample); // Close session/pool/frames before leaving the MTA.
                drop(apartment);
            })
            .map_err(|_| error("capture_failed", "Could not start capture."))?;
        Ok((
            Self {
                requests: tx,
                stop,
                run_cancel,
                thread: Some(thread),
            },
            wait,
        ))
    }
    pub fn request(&self) -> mpsc::SyncSender<Reply> {
        self.requests.clone()
    }
}
impl Drop for Live {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;
    struct Resource(Arc<AtomicUsize>);
    impl Drop for Resource {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }
    fn frame() -> Frame {
        Frame {
            source: Source {
                id: "test".into(),
                title: "Synthetic".into(),
                kind: SourceKind::Window,
                width: 1,
                height: 1,
                x: 0,
                y: 0,
                primary: false,
                native_id: 0,
                process_id: 0,
            },
            width: 1,
            height: 1,
            pixels: vec![0; 4],
        }
    }
    pub fn fake(run: Arc<AtomicBool>, closed: Arc<AtomicUsize>, failed: bool) -> Live {
        let (live, ready) = Live::spawn(run, move |_| {
            Ok((Resource(closed), move |_: &AtomicBool| {
                if failed {
                    Err(error("capture_timeout", "Synthetic timeout"))
                } else {
                    Ok(frame())
                }
            }))
        })
        .unwrap();
        ready.recv_timeout(Duration::from_secs(1)).unwrap().unwrap();
        live
    }
    #[test]
    fn samples_reuse_one_resource_and_pause_resume_close_each_run() {
        let closed = Arc::new(AtomicUsize::new(0));
        let first = Arc::new(AtomicBool::new(false));
        let live = fake(first.clone(), closed.clone(), false);
        for _ in 0..3 {
            let (tx, rx) = mpsc::sync_channel(1);
            live.request().try_send(tx).unwrap();
            assert_eq!(
                rx.recv_timeout(Duration::from_secs(1))
                    .unwrap()
                    .unwrap()
                    .pixels
                    .len(),
                4
            );
            assert_eq!(closed.load(Ordering::SeqCst), 0);
        }
        first.store(true, Ordering::Release);
        drop(live);
        assert_eq!(closed.load(Ordering::SeqCst), 1);
        let resumed = fake(Arc::new(AtomicBool::new(false)), closed.clone(), false);
        drop(resumed);
        assert_eq!(closed.load(Ordering::SeqCst), 2);
    }
    #[test]
    fn capture_error_releases_resource_before_shutdown_finishes() {
        let closed = Arc::new(AtomicUsize::new(0));
        let live = fake(Arc::new(AtomicBool::new(false)), closed.clone(), true);
        let (tx, rx) = mpsc::sync_channel(1);
        live.request().try_send(tx).unwrap();
        assert_eq!(
            rx.recv_timeout(Duration::from_secs(1))
                .unwrap()
                .err()
                .unwrap()
                .code,
            "capture_timeout"
        );
        drop(live);
        assert_eq!(closed.load(Ordering::SeqCst), 1);
    }
}
