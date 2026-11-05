//! Desktop-owned backend. Private pipe bootstrap; no credentials or URLs cross React IPC.
use serde::Deserialize;
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex, Weak},
    time::{Duration, Instant},
};
use tauri::Manager;
type Result<T> = std::result::Result<T, String>;
const DEADLINE: Duration = Duration::from_secs(60);

#[derive(Clone)]
pub(crate) struct Endpoint {
    base: String,
    instance: Option<String>,
    token: Option<String>,
    owner: Option<Weak<Mutex<Option<Owned>>>>,
}
impl Endpoint {
    pub fn external() -> Self {
        Self {
            base: "http://127.0.0.1:8000".into(),
            instance: None,
            token: None,
            owner: None,
        }
    }
    pub fn url(&self, suffix: &str) -> Result<String> {
        if let Some(owner) = &self.owner {
            let owner = owner.upgrade().ok_or("backend_unavailable")?;
            let mut lock = owner.lock().unwrap_or_else(|p| p.into_inner());
            let child = lock.as_mut().ok_or("backend_unavailable")?;
            if child
                .child
                .try_wait()
                .map_err(|_| "backend_unavailable")?
                .is_some()
            {
                return Err("backend_unavailable".into());
            }
        }
        Ok(format!("{}{}", self.base, suffix))
    }
    pub fn headers(&self) -> Result<reqwest::header::HeaderMap> {
        let mut headers = reqwest::header::HeaderMap::new();
        if let Some(token) = &self.token {
            let mut value =
                reqwest::header::HeaderValue::from_str(token).map_err(|_| "backend_unavailable")?;
            value.set_sensitive(true);
            headers.insert("x-solveguide-instance", value);
        }
        Ok(headers)
    }
    pub fn accepts(&self, response: &reqwest::Response) -> bool {
        self.instance.as_ref().is_none_or(|id| {
            response
                .headers()
                .get("x-solveguide-instance-id")
                .is_some_and(|v| v.as_bytes() == id.as_bytes())
        })
    }
}
pub(crate) struct BackendState {
    owner: Arc<Mutex<Option<Owned>>>,
    endpoint: Endpoint,
}
impl BackendState {
    pub fn endpoint(&self) -> Endpoint {
        self.endpoint.clone()
    }
    pub fn stop(&self) {
        let child = self.owner.lock().unwrap_or_else(|p| p.into_inner()).take();
        drop(child); // Only the process/job we created is stopped; never kill by port/name.
    }
    pub fn launch(app: &tauri::AppHandle) -> Result<Self> {
        let mode = std::env::var("SOLVEGUIDE_BACKEND_MODE").unwrap_or_else(|_| "managed".into());
        if mode == "external" && cfg!(debug_assertions) {
            return Ok(Self {
                owner: Arc::new(Mutex::new(None)),
                endpoint: Endpoint::external(),
            });
        }
        if mode != "managed" {
            return Err("backend_mode_invalid".into());
        }
        let resources = app
            .path()
            .resource_dir()
            .map_err(|_| "backend_resources_unavailable")?;
        let installed = resources.join("backend").join("solveguide-backend.exe");
        let executable = if cfg!(debug_assertions) {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap()
                .join(".cache/desktop-backend/solveguide-backend.exe")
        } else if installed.is_file() {
            installed
        } else {
            return Err("backend_bundle_missing".into());
        };
        let log = runtime_dir(app)?.join("backend");
        std::fs::create_dir_all(&log).map_err(|_| "backend_log_unavailable")?;
        let mut command = Command::new(&executable);
        command.current_dir(executable.parent().ok_or("backend_bundle_missing")?);
        if app.config().identifier == "com.solveguide.desktop.personal" {
            command.arg("--personal-desktop");
        }
        Self::spawn(command, log.join("startup.log"))
    }
    #[cfg(windows)]
    fn spawn(mut command: Command, log: PathBuf) -> Result<Self> {
        use std::os::windows::process::CommandExt;
        use windows::Win32::System::Threading::CREATE_NO_WINDOW;
        let (instance, token) = identity()?;
        let started = Instant::now();
        let stderr = std::fs::File::create(log).map_err(|_| "backend_log_unavailable")?;
        command
            .arg("--managed")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(stderr)
            .env_remove("PYTHONHOME")
            .env_remove("PYTHONPATH")
            .env_remove("VIRTUAL_ENV")
            .creation_flags(CREATE_NO_WINDOW.0);
        let job = Job::new()?;
        let child = command.spawn().map_err(|_| "backend_spawn_failed")?;
        let mut owned = Owned {
            child,
            job: Some(job),
            reader: None,
        };
        owned.job.as_ref().unwrap().assign(&owned.child)?;
        let stdout = owned.child.stdout.take().ok_or("backend_pipe_failed")?;
        let (sender, ready) = std::sync::mpsc::sync_channel(1);
        owned.reader = Some(std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut line = String::new();
            let result = reader
                .by_ref()
                .take(8192)
                .read_line(&mut line)
                .ok()
                .and_then(|n| {
                    if n > 0 && n < 8192 {
                        serde_json::from_str::<Ready>(&line).ok()
                    } else {
                        None
                    }
                });
            let _ = sender.send(result);
            let _ = std::io::copy(&mut reader, &mut std::io::sink());
        }));
        let bootstrap = serde_json::json!({"protocol":1,"instance_id":instance,"token":token});
        writeln!(
            owned.child.stdin.as_mut().ok_or("backend_pipe_failed")?,
            "{bootstrap}"
        )
        .map_err(|_| "backend_pipe_failed")?;
        let announced = ready
            .recv_timeout(DEADLINE.saturating_sub(started.elapsed()))
            .map_err(|_| "backend_startup_timeout")?
            .ok_or("backend_protocol_invalid")?;
        if announced.protocol != 1 || announced.port == 0 || announced.instance_id != instance {
            return Err("backend_protocol_invalid".into());
        }
        let owner = Arc::new(Mutex::new(Some(owned)));
        let state = Self {
            endpoint: Endpoint {
                base: format!("http://127.0.0.1:{}", announced.port),
                instance: Some(instance),
                token: Some(token),
                owner: Some(Arc::downgrade(&owner)),
            },
            owner,
        };
        let client = reqwest::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|_| "backend_unavailable")?;
        let readiness: Result<()> = tauri::async_runtime::block_on(async {
            while started.elapsed() < DEADLINE {
                let url = state.endpoint.url("/api/health")?;
                if let Ok(response) = client.get(url).timeout(Duration::from_secs(2)).send().await {
                    if !state.endpoint.accepts(&response) {
                        return Err("backend_instance_mismatch".into());
                    }
                    if response.status().is_success()
                        && response
                            .json::<serde_json::Value>()
                            .await
                            .ok()
                            .is_some_and(|v| v["status"] == "ok")
                    {
                        return Ok(());
                    }
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
            Err("backend_startup_timeout".into())
        });
        readiness?;
        Ok(state)
    }
    #[cfg(not(windows))]
    fn spawn(_command: Command, _log: PathBuf) -> Result<Self> {
        Err("backend_platform_unsupported".into())
    }
}
impl Drop for BackendState {
    fn drop(&mut self) {
        self.stop();
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Ready {
    protocol: u32,
    port: u16,
    instance_id: String,
}
struct Owned {
    child: Child,
    #[cfg(windows)]
    job: Option<Job>,
    reader: Option<std::thread::JoinHandle<()>>,
}
impl Drop for Owned {
    fn drop(&mut self) {
        if let Some(mut control) = self.child.stdin.take() {
            let _ = writeln!(control, "stop");
        }
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            if self.child.try_wait().ok().flatten().is_some() {
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }
        #[cfg(windows)]
        drop(self.job.take()); // KILL_ON_JOB_CLOSE covers crashes and descendants.
        let _ = self.child.kill();
        let _ = self.child.wait();
        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
        }
    }
}
pub(crate) fn runtime_dir(app: &tauri::AppHandle) -> Result<PathBuf> {
    if cfg!(debug_assertions) {
        Ok(Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .join(".cache"))
    } else {
        app.path()
            .app_local_data_dir()
            .map_err(|_| "runtime_directory_unavailable".into())
    }
}
#[cfg(windows)]
fn identity() -> Result<(String, String)> {
    use base64::Engine;
    use windows::Win32::Security::Cryptography::{
        BCryptGenRandom, BCRYPT_USE_SYSTEM_PREFERRED_RNG,
    };
    let mut bytes = [0u8; 64];
    // SAFETY: OS-generated randomness into this owned, correctly sized byte buffer.
    unsafe { BCryptGenRandom(None, &mut bytes, BCRYPT_USE_SYSTEM_PREFERRED_RNG).ok() }
        .map_err(|_| "backend_identity_failed")?;
    Ok((
        base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(&bytes[..32]),
        base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(&bytes[32..]),
    ))
}
#[cfg(windows)]
struct Job(isize); // Sole owner of the kernel handle; integer representation is Send/Sync.
#[cfg(windows)]
impl Job {
    fn new() -> Result<Self> {
        use windows::Win32::System::JobObjects::*;
        // SAFETY: unnamed owned job, valid information buffer; handle closed exactly once.
        unsafe {
            let handle = CreateJobObjectW(None, None).map_err(|_| "backend_job_failed")?;
            let job = Self(handle.0 as isize);
            let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of_val(&info) as u32,
            )
            .map_err(|_| "backend_job_failed")?;
            Ok(job)
        }
    }
    fn assign(&self, child: &Child) -> Result<()> {
        use std::os::windows::io::AsRawHandle;
        use windows::Win32::{Foundation::HANDLE, System::JobObjects::AssignProcessToJobObject};
        // SAFETY: handles belong to our job and newly created child; bootstrap is still blocked.
        unsafe { AssignProcessToJobObject(HANDLE(self.0 as *mut _), HANDLE(child.as_raw_handle())) }
            .map_err(|_| "backend_job_assignment_failed".into())
    }
}
#[cfg(windows)]
impl Drop for Job {
    fn drop(&mut self) {
        unsafe {
            let _ = windows::Win32::Foundation::CloseHandle(windows::Win32::Foundation::HANDLE(
                self.0 as *mut _,
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn malformed_identity_cannot_select_an_external_address() {
        assert!(serde_json::from_str::<Ready>(
            r#"{"protocol":1,"port":8000,"instance_id":"x","url":"https://other"}"#
        )
        .is_err());
        assert!(
            serde_json::from_str::<Ready>(r#"{"protocol":1,"port":70000,"instance_id":"x"}"#)
                .is_err()
        );
    }
    #[cfg(windows)]
    #[test]
    fn missing_executable_fails_without_adopting_an_external_server() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
        let scratch = root.join(".cache/backend-missing-test");
        std::fs::create_dir_all(&scratch).unwrap();
        let result = BackendState::spawn(
            Command::new(scratch.join("missing.exe")),
            scratch.join("startup.log"),
        );
        assert!(matches!(result,Err(code) if code=="backend_spawn_failed"));
    }
    #[cfg(windows)]
    #[test]
    #[ignore = "requires the staged packaged backend; run explicitly with --include-ignored"]
    fn packaged_backend_start_health_and_owned_shutdown() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
        let executable = root.join(".cache/desktop-backend/solveguide-backend.exe");
        assert!(
            executable.is_file(),
            "stage the Phase 2 backend bundle before this explicit integration test"
        );
        let scratch = root.join(".cache/backend-lifecycle-test");
        std::fs::create_dir_all(&scratch).unwrap();
        let occupied = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let mut command = Command::new(executable);
        command.env_clear();
        for name in ["SYSTEMROOT", "WINDIR", "COMSPEC"] {
            if let Some(value) = std::env::var_os(name) {
                command.env(name, value);
            }
        }
        command
            .env("TEMP", &scratch)
            .env("TMP", &scratch)
            .env("LOCALAPPDATA", &scratch)
            .env("CONTEXT_STORAGE_DIRECTORY", scratch.join("documents"));
        let owner = BackendState::spawn(command, scratch.join("startup.log"))
            .unwrap_or_else(|code| panic!("managed startup failed: {code}"));
        let url = owner.endpoint.url("/api/health").unwrap();
        let port = reqwest::Url::parse(&url).unwrap().port().unwrap();
        assert_ne!(port, occupied.local_addr().unwrap().port());
        tauri::async_runtime::block_on(async {
            let response = reqwest::Client::new().get(&url).send().await.unwrap();
            assert!(owner.endpoint.accepts(&response));
            let mut wrong = owner.endpoint.clone();
            wrong.instance = Some("wrong-instance".into());
            assert!(!wrong.accepts(&response));
            let health = response.json::<serde_json::Value>().await.unwrap();
            assert_eq!(health["authentication"]["configured"], false);
            assert_eq!(health["vision"]["configured"], false);
            let denied = reqwest::Client::new()
                .get(owner.endpoint.url("/api/v1/auth/me").unwrap())
                .send()
                .await
                .unwrap();
            assert_eq!(denied.status().as_u16(), 403);
            let own = reqwest::Client::builder()
                .default_headers(owner.endpoint.headers().unwrap())
                .build()
                .unwrap()
                .get(owner.endpoint.url("/api/v1/auth/me").unwrap())
                .send()
                .await
                .unwrap();
            assert_ne!(own.status().as_u16(), 403);
            assert!(owner.endpoint.accepts(&own));
        });
        owner.stop();
        owner.stop();
        assert!(owner.endpoint.url("/api/health").is_err());
        assert!(std::net::TcpStream::connect_timeout(
            &format!("127.0.0.1:{port}").parse().unwrap(),
            Duration::from_millis(200)
        )
        .is_err());
        assert!(occupied.local_addr().is_ok()); // Never terminated the unrelated listener.
                                                // Closing the job handle is the same kernel cleanup used when the owner crashes.
        let mut command = Command::new(root.join(".cache/desktop-backend/solveguide-backend.exe"));
        command.env_clear();
        for name in ["SYSTEMROOT", "WINDIR", "COMSPEC"] {
            if let Some(value) = std::env::var_os(name) {
                command.env(name, value);
            }
        }
        command
            .env("TEMP", &scratch)
            .env("TMP", &scratch)
            .env("LOCALAPPDATA", &scratch);
        let crash = BackendState::spawn(command, scratch.join("job-close.log"))
            .unwrap_or_else(|code| panic!("job-close startup failed: {code}"));
        let job = crash.owner.lock().unwrap().as_mut().unwrap().job.take();
        drop(job);
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline
            && crash
                .owner
                .lock()
                .unwrap()
                .as_mut()
                .unwrap()
                .child
                .try_wait()
                .unwrap()
                .is_none()
        {
            std::thread::sleep(Duration::from_millis(25));
        }
        assert!(crash
            .owner
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .child
            .try_wait()
            .unwrap()
            .is_some());
        crash.stop();
    }
}
