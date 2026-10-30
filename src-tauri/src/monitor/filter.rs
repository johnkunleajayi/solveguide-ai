//! Local, bounded luminance comparison. It never calls a provider.
use crate::capture::Frame;
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
