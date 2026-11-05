# Windows backend packaging — Phase 1

From `D:\solveguide-ai`, using the existing backend build environment:

```powershell
.\scripts\build-backend.ps1 -InstallBuildTools -SmokeTest
```

Output: `dist/backend/solveguide-backend/solveguide-backend.exe`. Ship **the entire
folder**, including `_internal`; this is a standalone one-folder distribution, not
an exe-only distribution. Python and native DLLs are included. No venv, VS Code or
shell is needed to execute it. Double-click starts a console backend on
`127.0.0.1:8000`. Optional `--port` supports isolated checks. No external bind-address
option exists. The existing HTTP routes, Windows selector loop, timeout defaults,
models, prompts and answer policies are reused. This build does not start Tauri.

Build tools are separately pinned. `build-info.json` records installed package/Python
versions without environment values or URLs. Reproducible rebuilds require matching
source and runtime versions: existing runtime requirements remain ranged. This is
not a byte-for-byte deterministic-build guarantee. Caches/logs are in ignored `.cache`;
output is in ignored `dist`. No migrations are applied or automated by the executable.

The spec collects application code and required package resources/DLLs, never private
`.env`, keys, uploaded originals, user data or captured content. Frozen settings disable
dotenv loading entirely. Runtime configuration must come from process environment;
do not put Google/OpenAI/database secrets into the distributable. Frozen Context Library
storage defaults to `%LOCALAPPDATA%/SolveGuide AI/backend/context-library`, overridable
via `CONTEXT_STORAGE_DIRECTORY`. Development startup/configuration is unchanged.

Smoke check uses an empty credential environment, a temporary loopback port and
project-local scratch storage. It checks `/api/health` and terminates only its own
child. It makes no OpenAI/Google/Neon calls. Log: `.cache/backend-package/smoke/startup.log`.
This verifies local frozen startup, not clean-machine compatibility or live provider,
authentication and database operation. Test the complete folder on a clean supported
Windows installation before release. Console output is intentional for Phase 1 diagnostics.

Phase 2: Tauri-owned backend startup/readiness/shutdown, delivery of the complete bundle,
port-conflict handling, safe runtime configuration and installer signing/clean-machine
tests. Desktop binaries cannot conceal hosted service secrets: decide the production
service/credential boundary before public release. Tauri and monitoring are untouched.


## Phase 2 — desktop ownership

The desktop executable defaults to managed startup. Python binds/reserves port zero
on IPv4 loopback itself and announces that selected port through a private stdout pipe.
The parent supplies separate random instance identity/request credentials through stdin.
Readiness requires the matching identity header and health response before creating the
main window. Rust holds the URL and credentials; React continues to use typed native IPC.
Every native API response is identity-checked. There are no new frontend network origins.
Other applications/ports are never adopted or terminated.

Windows uses an unnamed KILL_ON_JOB_CLOSE job, assigned before the child receives its
bootstrap. EOF before bootstrap exits without listening. Normal shutdown requests a
bounded graceful exit; job closure is the forced fallback and also covers owner crashes.
An exited child fails native requests closed. There is no automatic backend restart.
The child is hidden and writes startup diagnostics to the native runtime directory.
Debug data/logs remain in the workspace `.cache`; release logs/WebView/privacy preferences
use Tauri's per-user application data directory, outside the installation resources.

Preserved development workflow: `npm.cmd run desktop` sets external mode unless
`SOLVEGUIDE_BACKEND_MODE` is already set; it continues to use the separately launched
`npm.cmd run backend`. External mode is available only in debug builds.

Test managed startup locally (no installer):

```powershell
.\scripts\build-backend.ps1
.\scripts\stage-backend.ps1
$env:SOLVEGUIDE_BACKEND_MODE = "managed"
npm.cmd run desktop
```

A production desktop build must include the managed resource overlay:

```powershell
.\scripts\build-backend.ps1
npm.cmd run tauri -- build --no-bundle --config src-tauri/tauri.managed.conf.json
```

The overlay stages the entire backend folder in `.cache/desktop-backend` BEFORE Vite
clears `dist`, and maps it to the desktop's `backend/` resource directory with `_internal`
intact. No installer is enabled or produced. Stage/build fail clearly if the backend
bundle is missing. Base development config has no mandatory packaged-resource dependency.

Runtime secrets are not bundled or loaded from private `.env` files in managed mode.
The packaged child inherits explicitly provisioned process environment configuration.
Existing Google web OAuth redirect registration is NOT rewritten to a random port:
`AUTH_PUBLIC_BASE_URL` and Google's authorized callback must agree. Local fixed-port web
OAuth configuration from development therefore needs a deliberate production callback
strategy before managed sign-in can be verified. Use external development mode for the
existing configured flow. Phase 3 must resolve this callback/credential/service boundary,
then validate sign-in/providers on a clean machine, code-sign and build the installer.

## Personal Windows installer

The personal Tauri configuration uses the existing registered Google callback at
`http://127.0.0.1:8000/api/v1/auth/google/callback`. The desktop owns this listener
exclusively on IPv4 loopback. Close the separately started **SolveGuide development
backend** before launching the installed app. If another application owns port 8000,
startup fails closed. The managed instance header, OAuth and account sessions still apply.

One-time setup in Explorer: open `%LOCALAPPDATA%`, create the folder
`SolveGuide AI Personal`, and privately copy your working
`D:\solveguide-ai\backend\.env` into it as `settings.env` (show file extensions).
Use your Windows user's private local profile. Keep this plaintext configuration out
of shared folders and installer resources. It supplies the existing database, Google
OAuth, state-encryption and OpenAI settings. Keep `AUTH_PUBLIC_BASE_URL=http://127.0.0.1:8000`.
Restart the desktop after editing settings. Personal credentials and this configuration
file are never inputs to the installer. No temporary login bypass is used.

Build from the repository with the existing local Rust toolchain available:
run `scripts/build-backend.ps1`, then `scripts/stage-backend.ps1 -Personal`, then
`npm.cmd run tauri -- build --config src-tauri/tauri.personal.conf.json`.
Double-click the generated x64 NSIS setup in `src-tauri/target/release/bundle/nsis`.
Launch SolveGuide AI Personal from Start, then use Sign in with Google.

Installer validation: personal x64 NSIS built and installed into
`D:\solveguide-ai\.cache\installed-personal` using /S /NS. Installation returned
0. Installed main window, managed backend readiness, normal main-window close and
port release passed with an empty isolated configuration. Nine targeted Python
packaging tests passed, and the TypeScript/Vite production build passed.
Google sign-in, remote database access and paid AI calls require manual verification
with the external personal settings file. No credentials were included.
The installer is unsigned. Tauri emitted a bundle-type marker warning during a
bundle-only retry; this product has no updater. Public distribution requires separate
OAuth/configuration and signing work.
