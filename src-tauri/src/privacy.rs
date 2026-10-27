//! Device-local preference and verified, application-owned window capture protection.
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::Mutex,
};

#[cfg(windows)]
mod windows;

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EffectiveState {
    Enabled,
    Disabled,
    Unsupported,
    Failed,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Issue {
    // Constructed by the non-Windows adapter and portability tests.
    #[cfg_attr(windows, allow(dead_code))]
    UnsupportedPlatform,
    UnsupportedVersion,
    #[cfg_attr(not(windows), allow(dead_code))]
    CapabilityUnavailable,
    #[cfg_attr(not(windows), allow(dead_code))]
    InvalidWindow,
    #[cfg_attr(not(windows), allow(dead_code))]
    AccessDenied,
    #[cfg_attr(not(windows), allow(dead_code))]
    ApplyFailed,
    #[cfg_attr(not(windows), allow(dead_code))]
    ReadFailed,
    VerificationFailed,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrivacyStatus {
    pub supported: Option<bool>,
    pub preference_enabled: bool,
    pub effective_state: EffectiveState,
    pub preference_persisted: bool,
    pub issue: Option<Issue>,
}

trait Platform {
    fn supported(&self) -> Result<bool, Issue>;
    fn set(&self, enabled: bool) -> Result<(), Issue>;
    fn read(&self) -> Result<bool, Issue>;
}

fn evaluate(
    platform: &impl Platform,
    preference: bool,
    persisted: bool,
    apply: bool,
) -> PrivacyStatus {
    let mut status = PrivacyStatus {
        supported: None,
        preference_enabled: preference,
        effective_state: EffectiveState::Failed,
        preference_persisted: persisted,
        issue: None,
    };
    match platform.supported() {
        Ok(false) => {
            status.supported = Some(false);
            status.effective_state = EffectiveState::Unsupported;
            status.issue = Some(Issue::UnsupportedVersion);
            return status;
        }
        Err(Issue::UnsupportedPlatform) => {
            status.supported = Some(false);
            status.effective_state = EffectiveState::Unsupported;
            status.issue = Some(Issue::UnsupportedPlatform);
            return status;
        }
        Err(issue) => {
            status.issue = Some(issue);
            return status;
        }
        Ok(true) => status.supported = Some(true),
    }
    if apply {
        if let Err(issue) = platform.set(preference) {
            status.issue = Some(issue);
            return status;
        }
    }
    match platform.read() {
        Ok(actual) if actual == preference => {
            status.effective_state = if actual {
                EffectiveState::Enabled
            } else {
                EffectiveState::Disabled
            }
        }
        Ok(_) => status.issue = Some(Issue::VerificationFailed),
        Err(issue) => status.issue = Some(issue),
    }
    status
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Preference {
    enabled: bool,
}

fn load(path: &Path) -> (bool, bool) {
    let read = fs::File::open(path).and_then(|file| {
        let mut bytes = Vec::new();
        file.take(129).read_to_end(&mut bytes)?;
        Ok(bytes)
    });
    match read {
        Ok(bytes) if bytes.len() <= 128 => serde_json::from_slice::<Preference>(&bytes)
            .map(|p| (p.enabled, true))
            .unwrap_or((true, false)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (true, true),
        _ => (true, false),
    }
}

fn save(path: &Path, enabled: bool) -> std::io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| std::io::Error::other("Preference directory unavailable"))?;
    fs::create_dir_all(parent)?;
    let pending = path.with_extension(format!("{}.pending", std::process::id()));
    let result = (|| {
        let mut file = fs::File::create(&pending)?;
        file.write_all(if enabled {
            b"{\"enabled\":true}"
        } else {
            b"{\"enabled\":false}"
        })?;
        file.sync_all()?;
        drop(file);
        fs::rename(&pending, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(pending);
    }
    result
}

struct Controller {
    path: PathBuf,
    preference: bool,
    persisted: bool,
}
pub struct PrivacyState(Mutex<Controller>);
impl PrivacyState {
    pub fn new(path: PathBuf) -> Self {
        let (preference, persisted) = load(&path);
        Self(Mutex::new(Controller {
            path,
            preference,
            persisted,
        }))
    }
    pub fn initialize(&self, window: &tauri::WebviewWindow) {
        let status = self.update(window, None, true);
        eprintln!(
            "screen_share_privacy: effective_state={:?}",
            status.effective_state
        );
        // Allowlisted classifications only: no HWND, source content, or user data.
        if let Some(issue) = status.issue {
            eprintln!("screen_share_privacy: {issue:?}");
        }
        if !status.preference_persisted {
            eprintln!("screen_share_privacy: preference_storage_unavailable");
        }
    }
    fn update(
        &self,
        window: &tauri::WebviewWindow,
        preference: Option<bool>,
        apply: bool,
    ) -> PrivacyStatus {
        let mut controller = self.0.lock().unwrap_or_else(|poison| poison.into_inner());
        if let Some(enabled) = preference {
            controller.preference = enabled;
            controller.persisted = save(&controller.path, enabled).is_ok();
        }
        #[cfg(windows)]
        let platform = windows::WindowPrivacy(window);
        #[cfg(not(windows))]
        let platform = {
            let _ = window;
            Unsupported
        };
        evaluate(
            &platform,
            controller.preference,
            controller.persisted,
            apply,
        )
    }
}

#[cfg(not(windows))]
struct Unsupported;
#[cfg(not(windows))]
impl Platform for Unsupported {
    fn supported(&self) -> Result<bool, Issue> {
        Err(Issue::UnsupportedPlatform)
    }
    fn set(&self, _: bool) -> Result<(), Issue> {
        Err(Issue::UnsupportedPlatform)
    }
    fn read(&self) -> Result<bool, Issue> {
        Err(Issue::UnsupportedPlatform)
    }
}

fn authorize(window: &tauri::WebviewWindow) -> Result<(), &'static str> {
    if window.label() != "main" {
        return Err("Privacy controls are available only in the main window.");
    }
    Ok(())
}
#[tauri::command]
pub fn privacy_get_state(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, PrivacyState>,
) -> Result<PrivacyStatus, &'static str> {
    authorize(&window)?;
    Ok(state.update(&window, None, false))
}
#[tauri::command]
pub fn privacy_set_enabled(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, PrivacyState>,
    enabled: bool,
) -> Result<PrivacyStatus, &'static str> {
    authorize(&window)?;
    Ok(state.update(&window, Some(enabled), true))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    struct Fake {
        supported: Result<bool, Issue>,
        actual: Cell<bool>,
        failure: Option<Issue>,
        read_failure: Option<Issue>,
        ignore_set: bool,
    }
    impl Platform for Fake {
        fn supported(&self) -> Result<bool, Issue> {
            self.supported
        }
        fn set(&self, enabled: bool) -> Result<(), Issue> {
            if let Some(issue) = self.failure {
                return Err(issue);
            }
            if !self.ignore_set {
                self.actual.set(enabled);
            }
            Ok(())
        }
        fn read(&self) -> Result<bool, Issue> {
            if let Some(issue) = self.read_failure {
                return Err(issue);
            }
            Ok(self.actual.get())
        }
    }
    fn fake() -> Fake {
        Fake {
            supported: Ok(true),
            actual: Cell::new(false),
            failure: None,
            read_failure: None,
            ignore_set: false,
        }
    }
    #[test]
    fn enabled_and_disabled_are_verified_and_serialized() {
        let platform = fake();
        let enabled = evaluate(&platform, true, true, true);
        assert_eq!(enabled.effective_state, EffectiveState::Enabled);
        let value = serde_json::to_value(&enabled).unwrap();
        assert_eq!(value["preferenceEnabled"], true);
        assert_eq!(value["effectiveState"], "enabled");
        assert_eq!(value["supported"], true);
        assert_eq!(
            evaluate(&platform, false, true, true).effective_state,
            EffectiveState::Disabled
        );
    }
    #[test]
    fn failure_and_mismatched_readback_never_claim_success() {
        let mut platform = fake();
        platform.failure = Some(Issue::AccessDenied);
        assert_eq!(
            evaluate(&platform, true, true, true).issue,
            Some(Issue::AccessDenied)
        );
        platform.failure = None;
        platform.ignore_set = true;
        assert_eq!(
            evaluate(&platform, true, true, true).effective_state,
            EffectiveState::Failed
        );
        platform.supported = Err(Issue::CapabilityUnavailable);
        assert_eq!(evaluate(&platform, true, true, true).supported, None);
        platform.supported = Ok(true);
        platform.read_failure = Some(Issue::ReadFailed);
        assert_eq!(
            evaluate(&platform, true, true, true).issue,
            Some(Issue::ReadFailed)
        );
    }
    #[test]
    fn unsupported_platform_and_old_windows_are_honest() {
        let mut platform = fake();
        for supported in [Ok(false), Err(Issue::UnsupportedPlatform)] {
            platform.supported = supported;
            assert_eq!(
                evaluate(&platform, true, true, true).effective_state,
                EffectiveState::Unsupported
            );
            assert!(!platform.actual.get());
        }
    }
    #[test]
    fn fresh_and_persisted_preferences_survive_reopen() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join(".cache")
            .join(format!("privacy-test-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("preference.json");
        let _ = fs::remove_file(&path);
        assert_eq!(load(&path), (true, true));
        for enabled in [false, true] {
            save(&path, enabled).unwrap();
            assert_eq!(load(&path), (enabled, true));
        }
        fs::write(&path, b"invalid").unwrap();
        assert_eq!(load(&path), (true, false));
        let blocked = root.join("not-a-directory");
        fs::write(&blocked, b"blocked").unwrap();
        assert!(save(&blocked.join("privacy.json"), false).is_err());
        let status = evaluate(&fake(), true, false, true);
        assert_eq!(status.effective_state, EffectiveState::Enabled);
        assert!(!status.preference_persisted);
        fs::remove_file(blocked).unwrap();
        fs::remove_file(path).unwrap();
        fs::remove_dir(root).unwrap();
    }
}
