# SolveGuide AI agent instructions

## Mandatory workspace rule
The official and ONLY project directory is D:\solveguide-ai.
Work exclusively inside it. Do not create or modify SolveGuide AI project files
on C:, Desktop, OneDrive or another location. Keep caches, tooling, screenshots,
temporary files and build artifacts inside this directory too.
Never commit or push unless the user explicitly authorizes it.

## Product and current scope
SolveGuide AI is a desktop-first learning assistant. This milestone adds deliberate native monitor/window capture to the
desktop application foundation. Preserve the branding and exact tagline:
"Understand the question. Find the answer. Learn why."

Monitor/window capture is explicitly authorized. Do not add OCR, AI providers, backend services, authentication,
database, automatic detection, payments or analytics without a future explicit
task. Analyze Question opens capture preparation; do not fabricate
answers or simulate analysis.

## Architecture
Tauri 2 hosts a React + TypeScript UI served by Vite. Tailwind CSS 4 is integrated
through its Vite plugin. Semantic CSS variables define light/dark palettes.
App.tsx owns layout and modal visibility; components contain focused UI sections.
useTheme owns appearance preference and OS-theme subscription.
src-tauri contains the native shell and a focused Windows capture module.
Only two custom capture commands are exposed. Keep native Windows work out of
React; no service layer, global state library or router is needed.

## Development
Use npm.cmd on Windows to avoid npm.ps1 execution-policy issues.
Install: npm.cmd install --cache .cache/npm
Launch desktop: npm.cmd run desktop
Frontend: npm.cmd run dev
Type check: npm.cmd run typecheck
Production frontend: npm.cmd run build
Rust validation: npm.cmd run desktop:check
The desktop script uses project-local Rust when available and redirects temporary
files into .cache. .tools, .cache, node_modules, dist and Rust target are ignored.

## Verification
Run type checking and frontend production build after relevant changes. Run
native checks when tooling is available. Check light/dark/system appearance,
keyboard access, modal Escape/focus return, resize behavior and the minimum
native window size. Report blocked checks honestly. Do not introduce test
frameworks or extra infrastructure for trivial presentational changes.
## Permanent visual and interaction foundation
Preserve the black/white Neutral Light identity and semantic tokens in
src/styles/tokens.css. Dark mode is the signature, with an intentional light
palette and persisted System option. Keep body text readable and luminous/motion
effects restrained. Use the existing focused components and browser-only pointer
primitive; do not rebuild the app or add a heavy component framework.
Never update React state for each pointer move. Preserve native cursor fallback,
selection, keyboard focus, coarse/touch behavior, reduced motion and forced colors.
Pause pointer enhancement in native settings dialogs. Pointer light is a persisted
user preference. Keep its animation loop bounded and listeners/frames cleaned up.

## Required development invariants
Preserve Vite watch.ignored entries for **/src-tauri/**, **/.tools/** and
**/.cache/**. Keep the existing Tauri host and .cache/webview data directory,
create:false window setup, project-local Rust configuration and desktop scripts.
Run npm.cmd run lint, typecheck, build and desktop:check; verify the actual native
window and check that EBUSY/beforeDevCommand failures do not return.

## Future architecture: documentation only
README.md records the intended reusable Context Library (PDF, DOCX, TXT, notes
and other learning materials), separate session preparation, explicit material
selection/review and GENERAL / CONTEXT GUIDED / MATERIALS ONLY reasoning modes.
CONTEXT GUIDED should be the future default with selected materials; broader model
reasoning remains available. MATERIALS ONLY must communicate insufficient support.
Library materials are reusable across sessions and must not require repeated uploads.
Do not implement uploads, parsing, retrieval, RAG, embeddings or vector search now.

Future user-selected screen/window/region capture belongs behind appropriate
Tauri/Rust native boundaries. Ordinary screen-sharing privacy may use supported
native OS/Tauri capture exclusion where available; never CSS tricks. Only explicit monitor/window capture is implemented. Exclusion, anti-proctoring,
monitoring/detection evasion and security circumvention remain out of scope. Keep visual tokens and browser interactions
reusable for an eventual web experience without creating a second app.

## Native capture invariants (Milestone 3)

Screen and window are implemented; Region exists only in the typed source model
and honest unavailable UI. Do not add a fragile selection overlay. Rust Windows
Graphics Capture owns source enumeration, source revalidation, one-frame capture,
D3D staging and PNG encoding. React owns preparation, preview and ephemeral state.
Do not pass frontend HWNDs, paths or arbitrary native targets across commands.
Use native-issued snapshot tokens and validate source kind/identity before capture.
Keep commands restricted to the main WebView; retain existing CSP/capabilities.
Never add background capture, automatic analysis or capture history.

Capture pixels stay in memory: never log them, upload them, persist them or create
screenshot fixtures from user content. Clear/reload must release the preview;
cancelled asynchronous results must be ignored. Capture cancellation does not
forcibly kill a native worker: the one-frame five-second wait finishes and cleans
up. Preserve session/pool/DPI/COM cleanup and main-window restoration on failures.
Native source loss, changed dimensions, unsupported sources, bounds, busy and
capture/API errors must remain structured and fail closed. Do not fall back from
window capture to desktop cropping. Preserve Windows' own capture indicator.

Run lint, typecheck, test:interaction, build, project-local cargo fmt --check,
cargo check, cargo test --lib and appropriate native manual checks. Use only D:
for Cargo/Rustup/temp/cache/build files (same environment as desktop.ps1). Validate
actual monitor/window capture, preview, retake, source change, Escape/cancel, error
handling, theme/pointer/keyboard behavior and smaller native windows. Document
physical multi-monitor/mixed-DPI/HDR/protected-window limits honestly.
Future OCR/vision/reasoning consumes CaptureResult through a separate adapter;
no provider calls, backend or context retrieval are authorized by this milestone.
