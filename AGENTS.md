# SolveGuide AI agent instructions

## Canonical workspace and publication

Work ONLY inside `D:\solveguide-ai`. No project files, Python/Rust environments,
caches, screenshots, WebView profiles or build/temp artifacts on C:, Desktop,
OneDrive or elsewhere. Never commit or push without explicit authorization.

## Current scope: Milestone 10

SolveGuide CAPTURES, UNDERSTANDS, RECOMMENDS and EXPLAINS for learning and authorized
practice. Preserve working native capture and separate vision extraction. Answers
require an explicit Get Suggested Answer action on a validated QuestionObservation;
never combine capture/vision/recommendation into an uncontrolled paid prompt.
Google OIDC and PostgreSQL/SQLAlchemy/Alembic now wrap the stable AI pipeline.
SolveGuide is desktop-only; Google authentication is mandatory for all core learning
actions. Local privacy/appearance Settings remain available without authentication.
Region remains unavailable. Milestone 9 adds only authenticated PDF/DOCX/TXT and
pasted-text Context Library management. Do not add learning history,
Session Preparation, payments,
analytics or automatic/continuous capture. Milestone 7 adds only supported native
capture protection for SolveGuide's own main window.

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
Appearance preferences, authentication identity/session metadata and explicitly
added Context Library materials persist. Live learning content does not persist.
Keep capture-result and observation types
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

Keep the exact loopback backend http://127.0.0.1:8000 and only the Google avatar
host lh3.googleusercontent.com in CSP; no broad native opener permissions.
Backend binds only 127.0.0.1. Exact POST origins are
http://127.0.0.1:1420 and http://tauri.localhost; no wildcard credentials. These
checks alone are not authentication. Only auth routes enable exact-origin cookie CORS;
vision/answer require current authenticated user and native-held session credentials.
Browser cookie CORS remains separate. Public deployment/access
controls remain future work.

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

Milestone 9 implements reusable PDF/DOCX/TXT/notes library management, separate from future
Session Preparation (work description, material selection/review, reasoning mode,
begin), GENERAL / CONTEXT GUIDED / MATERIALS ONLY modes. Context Guided should be
the default with selected materials while broader knowledge remains available;
Materials Only must communicate insufficient support. Reasoning modes and Session
Preparation remains documentation-only. Milestone 10 implements explicit selected-document
reasoning modes and retrieval after consent; never use materials in General mode.
Future region capture stays native. Screen-share privacy now lives behind the
Tauri/Rust boundary, not CSS. No anti-proctoring, monitoring/detection evasion or
security circumvention. A future website is public presence/download/support,
not a planned duplicate browser learning application. Do not build it in this task.

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
CSP or native permissions unnecessarily. Never persist screenshots/answers or add history,
or log sensitive question/answer/provider payloads. Only allowlisted request metadata
may be logged. All secrets stay in the ignored backend .env.

Rerun existing/new frontend, Ruff/pytest and Rust fmt/check/Clippy/tests. Automated
provider tests remain mocked. One controlled live reasoning attempt is allowed only
with configured credentials and a confirmed harmless practice observation. Do not
repeat paid calls just for testing. Prior successful vision testing is not proof of
answer quality. If a browser URL cannot be verified by Computer Use, stop browser
control and hand off exact native/live steps; never bypass the limitation.

README contains the contract, supported types, privacy, cost controls and future
selected-context boundary. Context Library management is now implemented separately; implement RAG/materials modes only within Milestone 10; keep session preparation
documented only. Do not proceed beyond Milestone 10 or commit/push.

## Milestone 6 platform invariants

`app/database.py` centrally owns PostgreSQL/Psycopg async SQLAlchemy 2 engine,
session factory, transaction context/dependency and cleanup. No create_all(), SQLite
fallback, schema creation at startup or engine/session construction in business APIs.
Alembic alone owns schema evolution. Preserve metadata/initial migration names,
UUIDs, timezone-aware timestamps, indexes, unique subject/session hashes and FKs.
`app/runtime.py` and Alembic use a selector event loop for Windows/Psycopg compatibility.

Only users, auth_sessions and short-lived oauth_attempts are implemented. Google
subject is the durable identity key; normalized indexed email is not an account-link
key. Concurrent sign-in uses PostgreSQL upsert by subject. Sessions use 32 random
bytes; store only SHA-256 hashes, bounded expiry, last-seen and revocation metadata.
Never persist Google ID/access/refresh tokens. Do not save captures, questions or answers.

`app/auth` separates provider, service, models, public DTOs, current-user dependencies
and routes. Google Authorization Code + S256 PKCE + nonce/state is backend-owned.
Validate signed RS256 tokens against Google's fixed JWKS and issuer/audience/expiry/
nonce/OIDC requirements. Require verified email. State is claimed/committed under
a row lock before provider I/O; callbacks/exchanges are one-use and ten-minute bounded.
Encrypt temporary verifier with backend AUTH_STATE_ENCRYPTION_KEY; hash state/binding.

Desktop opens only the exact Google authorization endpoint in the system browser.
`src-tauri/src/auth.rs` exposes main-window-only start/poll/me/cancel/logout commands,
fixed loopback HTTP with no redirects/proxies, and volatile session/exchange storage.
Never return session/exchange secrets to React, accept arbitrary URLs, register
custom URI handlers or place credentials in callback URLs. App restart signs out;
durable native credential storage is deliberately absent. Do not alter capture module.

Existing cookie compatibility shares the same service and user/session tables; it
does not imply a browser product requirement. Browser start/callback
requires a browser-binding HttpOnly cookie. Session cookie is HttpOnly, SameSite=Lax,
Path=/api and Secure for configured HTTPS. Exact Origin checks protect auth POSTs;
4 KiB request bounds and explicit timeouts are mandatory. CORS is not authorization.
Future owned resources must use required_current_user and server-derived user.id
ownership queries; optional_current_user is for optional identity only. Existing
vision/answer endpoints now require sign-in before any provider work.

DATABASE_URL, GOOGLE_CLIENT_ID/SECRET, AUTH_STATE_ENCRYPTION_KEY and auth settings are
backend-only. URL/keys use masked settings; never print real .env, raw SQL exceptions,
provider tokens, session/exchange secrets or callback query strings. Logs stay
allowlisted; SQL echo stays disabled. Missing config prevents core access while local
privacy/appearance Settings remain usable.
Health flags mean configured, not database connectivity or migrated schema readiness.

Frontend `src/auth` has backend-derived checking/signed_out/signing_in/signed_in/error
states; no localStorage/sessionStorage credentials or trusted login flag. Sign-in is
explicit; polling is bounded/non-overlapping; cancellation rejects stale replies.
Settings owns restrained account controls, avatar/name/email and sign-out. Preserve
themes/pointer, semantic controls, keyboard focus, modal scrolling and compact layout.

Tests use fakes at DB boundaries, locally signed test identity tokens and mocked
Google only. PostgreSQL-dialect migration rendering is not a live upgrade proof.
Opt-in destructive integration requires a dedicated TEST_DATABASE_URL and explicit
ALLOW_TEST_DATABASE_RESET=1; never point it at a database with needed accounts.
Real Google login is manual with the user, never automate credentials or consent.
README contains exact Neon/Google setup, env variables, migration and manual steps.
No external infrastructure, later features, commits or pushes without authorization.

## Milestone 7 screen-share privacy

`src-tauri/src/privacy.rs` owns a device-local preference and typed effective state;
`privacy/windows.rs` alone owns the Win32 privacy calls. Use the Tauri-provided HWND,
validate current-process/top-level ownership, call SetWindowDisplayAffinity with
WDA_EXCLUDEFROMCAPTURE (ON) or WDA_NONE (OFF), and verify GetWindowDisplayAffinity.
Never accept a frontend HWND/URL/path. Commands are main-window-only. No broad new
Tauri permissions or backend/auth/AI changes are needed.

Fresh preference is ON. Rust reads `.cache/preferences/screen-share-privacy.json`
before first show and applies/verifies protection on the initially unshown window.
Normal first show always proceeds even on protection failure; initial visibility
ordering is not the protection mechanism. Explicit ON/OFF saves atomically. Corrupt
or unreadable preferences default ON; persistence errors are separately reported.
Only a boolean is stored, with no account/server dependency or image/history data.

Windows exclusion requires 10 version 2004/build 19041 or newer; use the documented
local WinRT OS-version query, not manifest-sensitive assumptions. Older Windows and
non-Windows report unsupported; failed capability/API/readback reports failed, never
false enabled. State includes preference, capability, effective result, persistence
and sanitized issue. Logs may include enum/numeric error classifications, never HWNDs,
window titles, image bytes, questions or answers. No telemetry is sent.

Capture keeps its existing self-process filter; unknown PID is excluded too. Other
applications and monitor sources remain available. Never disable affinity during
SolveGuide capture. Actual monitor/external capture behavior needs visual manual
verification; API readback and adapter tests do not prove universal capture exclusion.
Keep exact Vite exclusions. No hooks/injection, process hiding, third-party control,
anti-proctoring, monitoring evasion, DRM or guaranteed invisibility claims.

## Milestone 8 mandatory access invariants

The application has one AuthProvider/controller and central AuthGate. No authenticated
workspace mounts until backend-derived signed_in state has a user. Settings and native
privacy are independent of the gate. Distinguish checking, signed_out, signing_in,
signing_out, signed_in, unavailable and error. No local login flags or browser storage
credentials. Full desktop process restart intentionally requires sign-in again.

Both provider routes use existing required_current_user; never bypass auth or execute
a provider before it succeeds. Keep auth-start/callback/exchange and health usable for
sign-in. Tests of provider contracts must opt into authenticated dependency overrides;
access-enforcement tests must exercise actual session validation with no overrides.
Test missing/invalid/expired/revoked sessions, outage and logout; assert zero provider calls.

Native ai_request exposes only two fixed routes, bounded JSON and a request ID. Rust
attaches its credential in memory; never return it to React or accept arbitrary URLs.
Request cancellation and logout epoch guards discard stale replies. Native /me must
check backend availability even with no stored token. Logout clears local credentials
before network revocation; failure must keep UI locked and not claim remote success.

Core capture preflight lives in the TypeScript client/gate; do not couple the Windows
capture engine to PostgreSQL/Google. Unmount clears capture/observation/answer state
and aborts provider transport; abandoned preflights cannot begin new capture. A fresh
login gets a new workspace. Preserve all existing neutral observations, answer schemas,
confidence semantics, privacy protections and explicit paid actions.

No migration, history, telemetry, browser app, website or commercial features are added.
Future entitlement policy may sit after authenticated-user validation and before
provider services; documentation only, no speculative entitlement abstraction now.


## Milestone 9 Context Library invariants

`backend/app/context_library` owns API/service/model/schemas/extraction/storage.
All document queries include authenticated owner identity; never fetch by UUID
then trust React to filter. Unknown and cross-owner resources both return 404.
`context_documents` is the only new table, via Alembic `0002_context_library`.
Never modify applied `0001_auth` or call create_all(). Preserve PostgreSQL JSONB,
UUID/timezone timestamps, owner FK and named constraints/index. Milestone 10 adds only derived index/chunk tables. No session preparation, histories or billing tables.

DocumentStorage is replaceable. Development LocalDocumentStorage defaults to
D:\solveguide-ai\.cache\context-library, generated 32-hex keys only, ignored by Git
and Vite, no static mount. Keep OS directory permissions private. No arbitrary paths
or storage keys in public DTOs. Originals and extracted text intentionally persist;
live capture/question/answer content stays ephemeral and account-independent.

Raw-body uploads avoid multipart temp spooling. Enforce authentication before body
parsing, exact mutation origins, configurable byte/text/page/block/expanded-content
limits, MIME/extension/signature/encoding checks. Blocking PDF/DOCX parsing runs in
bounded worker threads. No OCR, XML entity expansion, macro/action execution,
external decoder or provider call during ordinary library CRUD. Milestone 10
indexing/retrieval is separate and requires explicit transmission consent.
No titles, notes, binary bytes or parser exceptions in operational logs.

Native `context_library::library_request` accepts typed operations only. File
selection/read/upload is native, filtered and parented to the main window; no
React paths or filesystem privileges. AuthState applies native-memory credentials
and epoch validation. Never expose those credentials through IPC or browser storage.
Use shared auth invalidation and discard stale responses/follow-up requests.

Deletion durably marks pending, clears text, removes binary, then removes metadata.
Partial storage/DB failure remains retryable; no false success. Upload DB failures
compensate stored files. Cross-resource crash atomicity is not guaranteed: disclose
operator reconciliation limits and do not add a background service speculatively.

Frontend `src/library` and ContextLibrary reuse current tokens/themes/accessibility;
keep learning state mounted when navigating. Test ownership on every operation,
parser/storage/commit failure paths, stale responses, auth expiry, CRUD and all
existing pipeline/privacy/pointer regressions. Generate disposable fixtures under
.cache; never add user documents or large binary fixtures to Git. Never destructively
downgrade the user's real Neon database; offline SQL or explicit disposable DB only.


## Milestone 10 RAG invariants

`app/rag` separates versioned owned indexing, chunking, embedding abstraction,
repository, bounded retrieval and grounded service/DTOs. Preserve General's original
AnswerService/AnswerProvider path and zero document lookup/embedding behavior.
Context Guided separates general supplements from document support; Materials Only
requires sufficient selected evidence and per-answer/explanation/key-point support,
plus the implemented independent structured verification call. Failed verification,
contradictions, missing indexes or no relevant evidence abstain; never auto-fallback
to General or broaden a document selection.

Authorization precedes retrieval/embeddings/reasoning. Every query is owner-scoped;
composite FKs bind chunk/index ownership. Only explicitly selected IDs (max five)
are eligible. Never accept client excerpts, vectors, titles, pages or citations as
trusted source metadata. Resolve citations from retrieved rows and validate reference
membership and source support. Never expose hidden reasoning.

Index explicitly; no startup/upload/rename backfill. Lexical is local; semantic
indexing requires boolean user consent before OpenAI document transmission. Grounded
answers require separate passage-transmission consent. SDK keys remain backend-only,
max_retries=0; batches/inputs/deadlines bounded. Query embeddings are ephemeral and
must never be stored. Document vectors may persist with library data only.

`0003_context_rag` is additive; do not modify older migrations or use create_all.
pgvector capability is checked. JSONB stores dimension-flexible document vectors;
pgvector performs scoped exact cosine ranking. Lexical fallback uses PostgreSQL GIN
full-text ranking and must be labelled honestly. No ANN performance claim. Index
claims/generation publication are transactional; retirement prevents stale chunks,
failures are retryable, unchanged non-forced requests are idempotent. Renames do not
re-embed. Deletion cascades derived rows; pending deletions are excluded immediately.

Treat all source text as untrusted data, never system instructions/tools/auth policy.
Fixed prompts, strict support contracts and a separate Materials Only check reduce
risk; do not claim perfect semantic grounding or prompt-injection immunity. Source
support is model-verified, not mathematical proof. Never log document/query/answer
content, vectors, provider payloads or credentials. Keep native credentials in Rust.

`src/rag` owns ephemeral mode/selection/consent/readiness; invalidation cancels answers
on changes/logout/expiry. Keep late index/answer/catalog results from restoring stale
state. Selected documents beyond the first page must remain correctly represented.
Keep library source links, themes, keyboard/focus, compact layout, Pointer Light and
screen-share privacy. All live learning content stays ephemeral; no session/history,
telemetry, monetization, OCR or account-wide auto-retrieval. Stop at Milestone 10.
