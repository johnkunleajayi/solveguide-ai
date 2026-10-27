# SolveGuide AI agent instructions

## Canonical workspace and publication

Work ONLY inside `D:\solveguide-ai`. No project files, Python/Rust environments,
caches, screenshots, WebView profiles or build/temp artifacts on C:, Desktop,
OneDrive or elsewhere. Never commit or push without explicit authorization.

## Current scope: Milestone 4

SolveGuide captures and understands visible questions. It does NOT determine or
recommend correct answers. Native Screen/Window capture and explicit Read Question
are implemented. Region capture remains unavailable. The only intelligence stage
is QuestionObservation via an explicit user-requested backend/provider call.
Do not add answer generation/reasoning, local OCR, authentication, databases,
Context Library, uploads, RAG, embeddings, vector search, payments, analytics,
continuous capture or native capture exclusion in this milestone.

Preserve the exact tagline: "Understand the question. Find the answer. Learn why."
Preserve existing working capture, settings, keyboard and responsive behavior.

## Architecture and boundaries

Tauri 2/Rust hosts React/strict TypeScript/Vite/Tailwind. `src/capture` owns the
existing native contract/controller; `src-tauri/src/capture` owns Windows APIs.
`src/vision` owns HTTP transport, typed/runtime-validated observations and cancellable
UI state. `QuestionObservationView` renders plain escaped text with math/code
whitespace, options, context and uncertainty; never correctness highlights.

`backend/app` is a modular FastAPI monolith:
- config: pydantic-settings, backend-only masked credentials and bounded timeouts;
- schemas/images: strict observation/request contracts and in-memory PNG validation;
- providers/base: provider-independent VisionProvider protocol;
- providers/openai: only implemented provider, official SDK Responses structured output;
- service: orchestration, semantic output revalidation and sanitized failures;
- api/main/middleware: application factory, DI, health, bounded request stream,
  exact browser origins/hosts, concurrency bound and safe JSON errors/logging.

Do not spread OpenAI SDK calls/model names through other layers. No frontend or
Rust key access. `backend/.env` is ignored; `.env.example` contains safe placeholders.
Never print/read a real key into tool output. Use SecretStr and never log exceptions
or validation inputs that could include images, provider text or credentials.

## Capture and vision privacy invariants

Capture alone stays local and ephemeral. Read Question explicitly discloses that
OpenAI receives the current image. No automatic reading/retry/provider request.
Backend accepts only bounded PNG base64 JSON, never paths or remote URLs. Keep
14 MiB streamed-body, 10 MiB PNG and 40 MP bounds, decoder checks, and one in-flight
vision request. No UploadFile/temp-file spooling, permanent image files or history.
Do not log base64, screenshots, extracted prompts, complete provider responses or
raw SDK exceptions. Logs contain only allowlisted event metadata. Keep store=False;
this is not a provider zero-retention guarantee. No Files API upload is needed.

Retake/Clear reset observations and abort requests; discard stale responses.
Cancellation cannot promise a remote request already sent will stop or avoid costs.
Only theme/pointer preferences persist. Keep capture-result and observation types
separate for future stages. Pydantic remains authoritative; client guard fails closed.
No schema answer/reasoning/correctness fields or UI recommendations are permitted.

## Native and development invariants

Preserve Vite exclusions `**/src-tauri/**`, `**/.tools/**`, `**/.cache/**` and avoid
EBUSY recurrence. Preserve .cache/webview, create:false native setup, local Rust,
Windows capture resource/DPI/COM cleanup, frame timeout and main-window restoration.
Keep two capture commands restricted to the main WebView and validate native-issued
source tokens/types. Do not fall back from window capture to desktop cropping.
Preserve Windows' capture indicator. Region is typed but deliberately unsupported.

The only CSP extension is the exact loopback backend http://127.0.0.1:8000.
No new native permissions. Backend binds only 127.0.0.1. Exact POST origins are
http://127.0.0.1:1420 and http://tauri.localhost; no wildcard credentials. These
checks are not authentication. Public deployment/access controls remain future work.

Use npm.cmd on Windows. See README for exact environment/install/start commands.
`setup:backend` uses Python 3.12+ in .tools/python, pinned backend dependencies,
.cache/pip/.cache/tmp/.cache/pycache. `backend` starts FastAPI; `desktop` starts Tauri.
Use scripts rather than creating global Python or Rust state outside the workspace.

## Design and interaction system

Preserve the black/white Neutral Light identity and semantic CSS tokens. Dark is
signature, light intentional, System persisted. Keep typography readable, luminous
motion restrained, and source/observation layouts usable at the 640 x 560 client
minimum with natural vertical scrolling and no horizontal overflow.
Pointer Light remains browser-only, fine-hover-only, preference-controlled, bounded
rAF/DOM refs/transforms with no React state per move. Preserve native cursor,
selection, touch/coarse, reduced-motion, forced-colors, keyboard and modal fallbacks.
Semantic controls, visible focus and live status/error messages are mandatory.

## Validation and honest reporting

Run lint, typecheck, test:interaction, build, backend:lint, backend:test and native
Cargo fmt/check/Clippy (-D warnings)/tests. Preserve all capture/pointer/Rust tests.
Automated provider tests use fakes/HTTP transport mocks and never real credits.
Perform one real-provider test only if a real key is configured and using a harmless
captured practice question. Never report mocked UI/SDK tests as live extraction proof.
Verify actual native capture, explicit Read Question, rendering/errors, theme/pointer,
keyboard and compact windows. Report untested physical multi-monitor/DPI/HDR cases.

## Future architecture (documentation only)

README records a reusable PDF/DOCX/TXT/notes Context Library across sessions, separate
Session Preparation (work description, material selection/review, reasoning mode,
begin), GENERAL / CONTEXT GUIDED / MATERIALS ONLY modes. Context Guided should be
the default with selected materials while broader knowledge remains available;
Materials Only must communicate insufficient support. Do not implement these yet.
Future region capture and supported native screen-share privacy belong behind
Tauri/Rust boundaries, not CSS. No anti-proctoring, monitoring/detection evasion or
security circumvention. Keep tokens and browser primitives reusable for a future
web application without creating a separate web app now.
