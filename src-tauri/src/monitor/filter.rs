//! Local, bounded luminance comparison. It never calls a provider.
use crate::capture::Frame;
use std::hash::{DefaultHasher, Hash, Hasher};

/// Ephemeral exact-pixel fingerprint, not an authorization or security identifier.
/// Two domain-separated hashes avoid keeping another full-size screenshot buffer.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct FrameIdentity(u32, u32, u64, u64);
impl FrameIdentity {
    pub fn of(frame: &Frame) -> Self {
        let digest = |domain: u8| {
            let mut hasher = DefaultHasher::new();
            domain.hash(&mut hasher);
            frame.pixels.hash(&mut hasher);
            hasher.finish()
        };
        Self(frame.width, frame.height, digest(0), digest(1))
    }
}
#[derive(Default)]
pub struct CompletedFrame(Option<FrameIdentity>);
impl CompletedFrame {
    pub fn contains(&self, frame: FrameIdentity) -> bool {
        self.0 == Some(frame)
    }
    pub fn finish(&mut self, frame: FrameIdentity) {
        self.0 = Some(frame);
    }
}
#[derive(Clone)]
pub struct Signature {
    pub width: u32,
    pub height: u32,
    pub cells: Vec<u8>,
}
impl Signature {
    pub fn of(frame: &Frame) -> Self {
        let mut cells = Vec::with_capacity(128 * 72);
        for y in 0..72 {
            for x in 0..128 {
                let px = (x * frame.width as usize / 128).min(frame.width as usize - 1);
                let py = (y * frame.height as usize / 72).min(frame.height as usize - 1);
                let i = (py * frame.width as usize + px) * 4;
                cells.push(
                    ((u32::from(frame.pixels[i]) * 54
                        + u32::from(frame.pixels[i + 1]) * 183
                        + u32::from(frame.pixels[i + 2]) * 19)
                        / 256) as u8,
                );
            }
        }
        Self {
            width: frame.width,
            height: frame.height,
            cells,
        }
    }
    pub fn differs(&self, other: &Self) -> bool {
        self.width != other.width
            || self.height != other.height
            || self.cells.len() != other.cells.len()
            || self
                .cells
                .iter()
                .zip(&other.cells)
                .filter(|(a, b)| a.abs_diff(**b) > 20)
                .count()
                * 1000
                > self.cells.len() * 4
    }
}
pub struct Gate {
    anchor: Option<Signature>,
    previous: Option<Signature>,
    stable_since: u64,
    sent: bool,
}
impl Gate {
    pub fn new() -> Self {
        Self {
            anchor: None,
            previous: None,
            stable_since: 0,
            sent: false,
        }
    }
    pub fn observe(&mut self, signature: Signature, now: u64, stabilize: u64) -> (bool, bool) {
        let changed = self.anchor.as_ref().is_none_or(|a| a.differs(&signature));
        if changed {
            self.anchor = Some(signature.clone());
            self.sent = false;
            self.stable_since = now;
        }
        if self.previous.as_ref().is_none_or(|p| p.differs(&signature)) {
            self.stable_since = now;
        }
        self.previous = Some(signature);
        (
            changed,
            !self.sent && now.saturating_sub(self.stable_since) >= stabilize,
        )
    }
    pub fn sent(&mut self) {
        self.sent = true;
    }
    pub fn retry(&mut self) {
        self.sent = false;
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn frame(value: u8) -> Frame {
        Frame {
            source: crate::capture::Source {
                id: "synthetic".into(),
                kind: crate::capture::SourceKind::Window,
                title: "Synthetic".into(),
                width: 128,
                height: 72,
                x: 0,
                y: 0,
                primary: false,
                native_id: 0,
                process_id: 0,
            },
            width: 128,
            height: 72,
            pixels: vec![value; 128 * 72 * 4],
        }
    }
    #[test]
    fn completed_pixels_suppress_repeat_after_unprocessed_noise_but_not_new_questions() {
        let a = FrameIdentity::of(&frame(20));
        let b = FrameIdentity::of(&frame(40));
        let mut completed = CompletedFrame::default();
        assert!(!completed.contains(a)); // Activation has no history.
        completed.finish(a);
        for _ in 0..10 {
            assert!(completed.contains(FrameIdentity::of(&frame(20))));
        }
        assert!(!completed.contains(b)); // New page, or a retry after failure, remains eligible.
        assert!(completed.contains(a)); // Aborted/unprocessed noise B did not retire A.
        completed.finish(b);
        assert!(!completed.contains(a)); // A -> completed B -> A is a legitimate transition.
        assert!(completed.contains(b));
        assert!(!CompletedFrame::default().contains(b)); // Stop/new session/source has no cache.
        let mut tiny = frame(40);
        tiny.pixels[1] += 1;
        assert_ne!(b, FrameIdentity::of(&tiny)); // Full pixels, not the sparse gate signature.
        tiny.width += 1;
        assert_ne!(b, FrameIdentity::of(&tiny));
    }
    fn s(n: usize) -> Signature {
        let mut cells = vec![0; 9216];
        cells[..n].fill(255);
        Signature {
            width: 1920,
            height: 1080,
            cells,
        }
    }
    #[test]
    fn cursor_noise_is_ignored_but_text_changes_are_detected() {
        assert!(!s(0).differs(&s(8)));
        assert!(s(0).differs(&s(100)));
    }
    #[test]
    fn stability_dedup_and_changed_page() {
        let mut g = Gate::new();
        assert_eq!(g.observe(s(0), 0, 2000), (true, false));
        assert_eq!(g.observe(s(8), 2000, 2000), (false, true));
        g.sent();
        assert_eq!(g.observe(s(0), 5000, 2000), (false, false));
        assert_eq!(g.observe(s(100), 6000, 2000), (true, false));
        assert_eq!(g.observe(s(100), 8000, 2000), (false, true));
    }
    #[test]
    fn moving_content_defers_processing_and_retry_is_explicit() {
        let mut g = Gate::new();
        g.observe(s(0), 0, 2000);
        assert!(!g.observe(s(100), 1500, 2000).1);
        assert!(!g.observe(s(200), 2500, 2000).1);
        assert!(g.observe(s(200), 5000, 2000).1);
        g.sent();
        g.retry();
        assert!(g.observe(s(200), 6000, 2000).1);
    }
}
