//! All privacy Win32 FFI is isolated here. Never accepts a frontend HWND.
use super::{Issue, Platform};
use windows::{
    System::Profile::AnalyticsInfo,
    Win32::{
        Foundation::HWND,
        UI::WindowsAndMessaging::{
            GetAncestor, GetWindowDisplayAffinity, GetWindowThreadProcessId, IsWindow,
            SetWindowDisplayAffinity, GA_ROOT, WDA_EXCLUDEFROMCAPTURE, WDA_NONE,
        },
    },
};

pub(super) struct WindowPrivacy<'a>(pub &'a tauri::WebviewWindow);

fn classify(error: windows::core::Error, fallback: Issue) -> Issue {
    // Numeric API classification only; never log HWNDs, titles or captured content.
    eprintln!(
        "screen_share_privacy: {fallback:?} win32_code={:#x}",
        error.code().0 as u32
    );
    match error.code().0 as u32 {
        0x80070005 => Issue::AccessDenied,
        0x80070578 => Issue::InvalidWindow,
        _ => fallback,
    }
}

fn exclusion_version(version: u64) -> bool {
    let major = version >> 48;
    let build = (version >> 16) & 0xffff;
    major > 10 || (major == 10 && build >= 19041)
}

impl WindowPrivacy<'_> {
    fn hwnd(&self) -> Result<HWND, Issue> {
        let handle = self.0.hwnd().map_err(|_| Issue::InvalidWindow)?;
        let hwnd = HWND(handle.0);
        // SAFETY: Tauri supplies this live window handle. Win32 validates it and its
        // root/process ownership before any setter; all output pointers are local.
        unsafe {
            let mut process_id = 0;
            if !IsWindow(Some(hwnd)).as_bool()
                || GetAncestor(hwnd, GA_ROOT) != hwnd
                || GetWindowThreadProcessId(hwnd, Some(&mut process_id)) == 0
                || process_id != std::process::id()
            {
                return Err(Issue::InvalidWindow);
            }
        }
        Ok(hwnd)
    }
}
impl Platform for WindowPrivacy<'_> {
    fn supported(&self) -> Result<bool, Issue> {
        // Documented, manifest-independent local OS version query; no telemetry/network.
        let value = AnalyticsInfo::VersionInfo()
            .and_then(|info| info.DeviceFamilyVersion())
            .map_err(|_| Issue::CapabilityUnavailable)?
            .to_string();
        let version = value
            .parse::<u64>()
            .map_err(|_| Issue::CapabilityUnavailable)?;
        Ok(exclusion_version(version))
    }
    fn set(&self, enabled: bool) -> Result<(), Issue> {
        let hwnd = self.hwnd()?;
        // SAFETY: validated Tauri-owned top-level HWND, same process, documented flags.
        unsafe {
            SetWindowDisplayAffinity(
                hwnd,
                if enabled {
                    WDA_EXCLUDEFROMCAPTURE
                } else {
                    WDA_NONE
                },
            )
        }
        .map_err(|error| classify(error, Issue::ApplyFailed))
    }
    fn read(&self) -> Result<bool, Issue> {
        let hwnd = self.hwnd()?;
        let mut affinity = 0;
        // SAFETY: validated HWND and a valid mutable DWORD output for this call only.
        unsafe { GetWindowDisplayAffinity(hwnd, &mut affinity) }
            .map_err(|error| classify(error, Issue::ReadFailed))?;
        match affinity {
            value if value == WDA_EXCLUDEFROMCAPTURE.0 => Ok(true),
            value if value == WDA_NONE.0 => Ok(false),
            _ => Err(Issue::VerificationFailed),
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exclusion_requires_windows_2004_or_later() {
        let version = |build: u64| (10u64 << 48) | (build << 16);
        assert!(!exclusion_version(version(18362)));
        assert!(exclusion_version(version(19041)));
        assert!(exclusion_version(version(26100)));
    }
}
