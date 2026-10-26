# SolveGuide AI

Understand the question. Find the answer. Learn why.

SolveGuide AI is a desktop-first learning assistant built with Tauri 2, Rust,
React, strict TypeScript, Vite and Tailwind CSS. This milestone provides the
permanent visual and interaction foundation plus deliberate Windows single-frame capture. AI analysis is deliberately not connected.

## Canonical workspace

The ONLY project folder is D:\solveguide-ai. Keep sources, dependencies, tooling,
temporary files, screenshots, WebView profiles and build output here.
Do not create project copies on C:, Desktop, OneDrive or elsewhere.
Do not commit or push without explicit authorization.

## Development

Run these commands in PowerShell from D:\solveguide-ai:

    npm.cmd install --cache .cache/npm
    npm.cmd run desktop

Frontend only: npm.cmd run dev

Validation:

    npm.cmd run lint
    npm.cmd run typecheck
    npm.cmd run build
    npm.cmd run desktop:check

The desktop script selects the project-local Rust toolchain and redirects npm
cache and temporary files into this workspace. If Rust setup needs repair,
run npm.cmd run setup:rust. MSVC C++ Build Tools and WebView2 are required.
See https://v2.tauri.app/start/prerequisites/ for native prerequisites.

Keep the Vite watch exclusions for **/src-tauri/**, **/.tools/** and **/.cache/**.
Tauri watches native sources separately. These exclusions prevent Vite from
traversing locked Rust artifacts and reintroducing the EBUSY/beforeDevCommand failure.
Native WebView data stays in .cache/webview. No installer is configured.

## Visual system: Neutral Light

The SolveGuide identity is black and white: intelligence emerging from darkness.
The signature dark palette uses near-black canvas, charcoal surfaces, white type
and silver secondary text. Light mode uses a warm off-white canvas, white work
surfaces, dark ink and independent neutral shadows. Neither palette depends on
purple or blue. System mode follows OS appearance changes; existing preferences
remain compatible and persist locally. Theme resolution occurs before React
renders to avoid a theme flash.

src/styles/tokens.css owns semantic palettes, typography, spacing, radii, borders,
shadows, selection/focus colors, luminous gradients, motion durations and easing.
The other style files compose these tokens into the shell, connected workbench,
settings and interaction system. Fonts are local system fonts; no remote font
service or runtime dependency is required.

A restrained metallic light pass accents the headline. Content arrival, button
response and theme transitions reinforce hierarchy. There are no fake analysis
animations. prefers-reduced-motion disables ambient motion, reveals, transitions,
light sweeps and enhanced pointer effects. Forced-colors retains readable type,
native controls/focus and native cursor behavior.

## Frontend architecture

- src/App.tsx: shell composition, modal visibility and preference wiring.
- src/components/Sidebar.tsx and Brand.tsx: reusable navigation and brand.
- src/components/AnswerWorkspace.tsx: question, suggested answer, explanation and
  explicitly planned context status; Analyze Question opens native capture preparation.
- src/components/SettingsDialog.tsx: semantic native dialog, theme radios and
  persisted Pointer light switch. Escape/backdrop dismissal and focus return remain.
- src/components/PointerLight.tsx: browser-only pointer enhancement.
- src/hooks/useTheme.ts and usePointerPreference.ts: small local preference hooks.
- src/styles/: tokens plus focused shell/workspace/settings/interaction styles.
- public/cursors/: crisp theme-aware SVG pointers with CSS native fallbacks.
- src/capture/: typed contract, native adapter and independently testable capture state machine.
- src-tauri/src/capture/: native source discovery, validation and Windows capture.
- scripts/: project-local launch, Rust setup and validation environment.
- eslint.config.js: TypeScript, React Hooks and JSX accessibility checks.

UI state stays local to React. Only appearance and Pointer light preferences are
stored. No router, global state library or component framework is introduced.
Browser-only tokens and pointer primitives can be reused by a future web app
without importing Tauri APIs. Do not create a separate web application yet.

## Pointer interaction

Enhancement requires a fine hover pointer, an enabled preference, no reduced-motion
request and no forced-colors mode. It affects only SolveGuide content; it never
changes the OS cursor. SVG cursor rendering keeps the tip precise; CSS falls back
to the native cursor if unsupported. Text retains an I-beam and normal selection.

The halo uses passive pointer listeners, DOM refs and requestAnimationFrame with
time-based easing. Movement causes no React state updates. Transforms handle
positioning; geometry is read only on surface entry. The animation loop settles
when motion stops and is cancelled on blur, scroll, resize, leave and cleanup.
A single selected work surface receives restrained light response. Hover and
press feedback stay small. All effect layers are pointer-events:none and hidden
from accessibility APIs. Native dialogs suspend enhancement to preserve top-layer
focus and normal modal interaction. The preference survives reloads.

## Responsive and accessible behavior

The shell moves from full navigation to an icon rail, then a compact header.
The question/answer surface adapts and stacks at narrow widths. Short windows
scroll naturally; settings remain scrollable. The current native minimum is
640 x 560. Keyboard controls, visible focus, skip navigation, native radio/switch
semantics, semantic headings, selection and honest live announcements are required.
Verify actual WebView behavior as well as frontend builds.

## Future architecture — documentation only

Context Library, Session Preparation, reasoning modes and capture exclusion remain future work. Native capture status is described explicitly below.

### Reusable Context Library

Users will eventually supply PDF, DOCX, TXT, pasted notes and other supported
learning/reference materials. Materials belong to a reusable library across
sessions, not temporary session-only uploads. Users should not repeatedly upload
the same material. A future session will reference selected library material IDs
and revisions so its context can be reviewed consistently.

Selected materials guide reasoning; they do not automatically become its only
knowledge source. Prepare for three explicit reasoning modes:

| Mode | Intended contract |
| --- | --- |
| GENERAL | Normal AI knowledge and reasoning, without selected-material guidance. |
| CONTEXT GUIDED | Selected materials provide important guidance while broader model knowledge and reasoning remain available. Default when materials are selected. |
| MATERIALS ONLY | Answer only when selected materials provide sufficient support; clearly communicate insufficient support. |

Future library storage, import/parsing, retrieval, grounding and provider policy
must remain separate responsibilities. No uploads, parsing, RAG, embeddings,
vector database, retrieval pipeline or answer generation are included now.

### Session Preparation

A future preparation step may let users describe their work, select reusable
materials, review the selection, choose a reasoning mode and begin a session.
Keep the reusable library separate from each session's selected material references.
No preparation forms or session execution are implemented now.

### User-selected native capture

Capture supports a screen or application window; the typed model reserves a user-selected region.
Supported OS/system work belongs behind appropriate Tauri/Rust boundaries, with
an explicit user selection and a typed frontend contract. Capture must remain
separate from OCR, context preparation, reasoning and result presentation.
Monitor and window capture are implemented below. Region selection, OCR, automatic detection and provider integration remain deferred.

### Ordinary screen-sharing privacy

The future desktop companion should support native OS capture exclusion where
the operating system and supported Tauri/native capabilities allow it, for
legitimate screen-sharing privacy. Document support and limitations per platform.
CSS tricks cannot provide this guarantee. Do not implement anti-proctoring,
monitoring evasion, detection evasion or security-tool circumvention.
Capture exclusion is not implemented in this milestone.

## Current scope and boundaries

No screen capture, OCR, AI provider, answer generation, backend/FastAPI,
authentication, database, uploads, RAG, embeddings, vector search, payments,
subscriptions, analytics or capture exclusion is implemented. Analyze Question
never accesses screen content. Empty states are not generated answers.

## Milestone 3: Windows native capture

Analyze Question opens the SolveGuide source picker. Choose Screen or Window,
select one source explicitly, then Capture. No source is selected automatically.
The native host hides itself briefly for monitor capture and restores itself on
success or failure. Window capture uses the selected window's surface, not a crop
of whatever overlaps it. Preview shows source, physical pixel dimensions and time.
Retake requests one new frame; Change Source reopens discovery. Clear capture
releases the displayed result. AI answer/explanation remain empty and honest.
Region is a typed, explicitly unavailable option: a reliable DPI-aware selection
overlay with Escape cancellation is the next incremental capture capability.

### Boundary and native implementation

React -> src/capture/native.ts -> two Tauri commands -> src-tauri/src/capture/.
list_capture_sources returns typed metadata and opaque native-issued IDs (unchanged sources retain IDs across refresh).
capture_source accepts only a source kind and ID from the native registry;
no frontend filesystem path or raw HWND is accepted. The main WebView alone may
invoke these commands. No filesystem/shell/network plugin permission was added;
existing CSP and capability settings are unchanged.

Windows enumerates monitors with EnumDisplayMonitors/GetMonitorInfoW and top-level
windows with EnumWindows. Hidden, minimized, cloaked, tool, untitled, desktop shell
and SolveGuide-owned windows are excluded. Titles, dimensions, primary-display
status and physical desktop position help identify sources. The source is checked
again immediately before capture; vanished, replaced or changed monitors fail
closed rather than silently selecting another source. Window identity includes
its process and title; a title change requires a refresh.

Windows Graphics Capture (IGraphicsCaptureItemInterop) and Direct3D11 acquire a
single frame with a free-threaded frame pool and a five-second frame wait. Work
and PNG encoding run off the UI thread. The capture session/frame pool are closed
on every exit path; nothing records continuously. One operation runs at a time.
The OS capture indicator is retained; capture-exclusion is not requested.
A 40-megapixel input limit bounds frame allocation. Size changes during frame
acquisition are rejected for a retake. Errors cross IPC as { code, message } with
safe user-facing messages, not native paths or image contents.

CaptureResult contains source metadata, actual width/height, image/png MIME type,
Unix capture timestamp in milliseconds and a base64 PNG. This is the future vision
provider input boundary; no provider, OCR or extraction stage exists.

### Privacy and lifetime

Pixels, PNG and IPC payloads live only in process memory; no screenshot files,
history, upload, database storage, image logging or provider calls are implemented.
React retains only the current result; retake replaces it, Clear releases it and
reload/exit loses it. Cancel invalidates pending replies. If cancelled during native
work, the bounded one-frame operation may finish, but its response is discarded;
it never becomes a preview or history. Native metadata remains until the next
discovery or process exit. There is no secure-memory-wipe guarantee: normal OS
memory management, crash dumps or pagefile policies are outside this mechanism.
Only theme and pointer preferences are written to browser storage.

### Dependencies and platform limits

Direct dependencies windows 0.62, png 0.18 and base64 0.23 are MIT OR Apache-2.0.
The Microsoft bindings and PNG/base64 encoders were reviewed from project-local
crate manifests/source. No capture service or recording dependency was added.
XCap was evaluated but is NOT a project dependency. References:
https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture
https://learn.microsoft.com/en-us/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow

Requires Windows 10 1903+ with supported Graphics Capture/D3D11 hardware and a
normal interactive desktop. Protected, elevated, minimized or special windows
may fail, appear blank or be unavailable. There is no desktop-crop fallback that
could accidentally substitute overlapping content. SDR BGRA8 is used: HDR color
accuracy/tone mapping is not provided. Cursor inclusion follows Windows defaults.
A temporary per-thread per-monitor-v2 DPI context keeps discovery in physical
pixels, including negative monitor origins; it is restored after each operation.
Physical multi-monitor, mixed-DPI, rotation, HDR and protected-content coverage
must be tested on representative hardware; do not infer that coverage from a
single-display machine. The future capture exclusion feature remains independent
from this capture adapter and is not implemented.

### Focused validation

    npm.cmd run test:interaction

This includes capture state-machine tests (discovery/selection, success, source
loss, retake/change source, cancel/stale replies, unsupported region and sanitized
errors) plus the existing pointer regression suite. Native unit tests cover input
bounds, stale/unsupported source requests and operation concurrency. Use the
project-local Rust environment from scripts/desktop.ps1 when running cargo fmt,
cargo test --lib or cargo clippy. Real Windows capture still requires native manual
verification; mock state tests are not proof of display-driver compatibility.


### Verification on the available Windows machine

Native Tauri launched and rendered. Manual checks confirmed monitor discovery
(single 1366 x 768 display), monitor capture with companion hide/restore, eligible
window discovery, occluded Notepad window capture (619 x 697 actual image), Retake,
Change Source, Escape cancellation, Region unavailable messaging, and a structured
source-unavailable error after the test window closed. Light/dark presentation,
visible keyboard focus, radio/button keyboard operation, Pointer Light return
outside dialogs and persisted light theme after reload were checked. Wide
1322 x 768 and compact 654 x 768 / 654 x 592 outer window sizes were inspected;
controls remain reachable through normal vertical scrolling with no observed
horizontal overflow. The minimum client size remains 640 x 560. WebView console
showed the React development-tools hint and no application errors. Vite's actual
watch inventory excluded src-tauri, .tools and .cache, and no EBUSY appeared.

These checks do not establish physical multi-monitor, mixed-DPI, HDR or all-application
compatibility. Window discovery bounds can include invisible OS borders; preview
reports the actual captured content size. Capture data was not written or uploaded
by the application; privacy confirmation is based on the capture code paths, not
a packet-capture audit of Windows or developer tools.
