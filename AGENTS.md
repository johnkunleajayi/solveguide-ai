# SolveGuide AI agent instructions

## Canonical workspace and publication

Work ONLY inside `D:\solveguide-ai`. No project files, Python/Rust environments,
caches, screenshots, WebView profiles or build/temp artifacts on C:, Desktop,
OneDrive or elsewhere. Never commit or push without explicit authorization.

## Current scope: Milestone 5

SolveGuide CAPTURES, UNDERSTANDS, RECOMMENDS and EXPLAINS for learning and authorized
practice. Preserve working native capture and separate vision extraction. Answers
require an explicit Get Suggested Answer action on a validated QuestionObservation;
never combine capture/vision/recommendation into an uncontrolled paid prompt.
Region remains unavailable. Do not add authentication, databases, history, Context
Library, uploads, RAG, embeddings, vector search, Session Preparation, payments,
analytics, automatic/continuous capture or capture exclusion.

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
- service: vision orchestration, semantic output revalidation and sanitized failures;
- answer/: separate AnswerProvider protocol, OpenAIAnswerProvider, centralized prompt,
  strict AnswerRecommendation, deterministic AnswerService and POST /api/v1/answer;
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
QuestionObservation remains neutral and rejects answer/reasoning/correctness fields.
Recommendations belong only to the separate AnswerRecommendation contract and UI.

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

## Milestone 5 answer invariants

`AnswerProvider.recommend(QuestionObservation)` receives validated structured text,
never CaptureResult/screenshots/paths/URLs. Keep OpenAI SDK calls in its adapter;
Responses structured output, Pydantic revalidation, store=False, explicit timeouts
and max_retries=0 are mandatory. Vision and answer models are independently configured.
Current answer defaults: OPENAI_ANSWER_MODEL=gpt-5.4, ANSWER_REASONING_EFFORT=medium,
ANSWER_MAX_OUTPUT_TOKENS=6000, ANSWER_TIMEOUT_SECONDS=60; see config.py bounds.
Do not change the working vision model/settings as part of reasoning changes.

AnswerRecommendation is strict and rejects extra/private reasoning fields. Preserve
statuses answered/uncertain/insufficient_information/unsupported, matching question
type, unique valid selected labels, nullable answer/boolean/code, concise explanation,
up to eight key points, separate answer confidence and warnings. MCQ requires exactly
one label; multiple-select requires the known count. Never silently repair invalid
labels/counts/duplicates. True/false can use a boolean without artificial options.
Essay/short answer/maths/code/mixed tasks use suitable plain-text/public educational
explanation and typed escaped code, not fake option labels or executable HTML.
Do not request, return, log or store private chain-of-thought or raw reasoning items.

Incomplete/unclear/no-question observations, contradictory selection instructions,
missing options and unknown types must fail closed with deterministic abstentions
where supported. Insufficient/unsupported responses contain no answer/selections/code,
key points or confidence beyond zero and must explain the limitation. Uncertain
recommendations need warnings and still obey any selection constraints.

Reading confidence describes extraction; answer confidence describes recommendation
correctness. Never copy one to the other or imply calibrated certainty. Observation
options stay neutral. Recommended labels and emphasis belong in AnswerRecommendationView.

`src/answer` owns typed text-only HTTP, runtime checks and cancellable request state.
No automatic request after reading, effect-triggered paid call or automatic retry.
Block double submission during loading. Try Again is an explicit paid attempt.
Retake/Change Source/Clear/new observation synchronously invalidate answers, abort
client transport and ignore stale replies. Changing source invalidates even if
selection is subsequently cancelled. Preserve cleanup of subscriptions/abort handles.
A request already accepted by the provider may finish and incur charges after cancel.

The answer endpoint accepts only QuestionObservation JSON; enforce its 256 KiB
streamed-body limit and existing exact Origin/host rules. Share one in-flight slot
with vision to limit concurrent paid requests. Do not weaken image validation, CORS,
CSP or native permissions. Never persist screenshots/answers, add history/database,
or log sensitive question/answer/provider payloads. Only allowlisted request metadata
may be logged. All secrets stay in the ignored backend .env.

Rerun existing/new frontend, Ruff/pytest and Rust fmt/check/Clippy/tests. Automated
provider tests remain mocked. One controlled live reasoning attempt is allowed only
with configured credentials and a confirmed harmless practice observation. Do not
repeat paid calls just for testing. Prior successful vision testing is not proof of
answer quality. If a browser URL cannot be verified by Computer Use, stop browser
control and hand off exact native/live steps; never bypass the limitation.

README contains the contract, supported types, privacy, cost controls and future
selected-context boundary. Keep future Context Library/RAG/materials modes/session
preparation documented only. Do not proceed beyond Milestone 5 or commit/push.
