# Milestone 17 Phase 2A.1 — Focused diagnostics and terminal noise

## Scope and checkpoint

Baseline HEAD remains `609cdd1`. All uncommitted Phase 2A work was preserved. This pass changes diagnostic collection/presentation/configuration and tests only. It does not optimize capture, scheduling, authentication, database access, provider configuration, prompts or answers. No OpenAI request, Neon connection, migration, deployment, commit or push was performed.

The previous DEBUG switch coupled useful timing instrumentation with routine auth/session/database/polling output. The new mode selects whether to suppress, aggregate or print that instrumentation. Existing detailed events remain available in DEBUG.

## Terminal-source inventory

| Source | Ownership / observed configuration | Treatment |
|---|---|---|
| `backend/app/diagnostics.py` | Application JSON logger, ContextVar correlation, logging configuration | NORMAL/PERFORMANCE filter routine successes before JSON formatting. PERFORMANCE consumes timing metadata into a request-local aggregate. |
| FastAPI diagnostic middleware | HTTP start/completion and safe failure categorization | Polling and successful HTTP chatter hidden outside DEBUG; actionable failures retained. Vision/Answer requests get one backend report each in PERFORMANCE. |
| Auth/session services and SQLAlchemy event hooks | Existing application spans and safe transaction/query measurements | Checks/queries unchanged. Timings collected silently in PERFORMANCE; detailed spans only DEBUG. |
| Uvicorn | `app.runtime` already sets `access_log=False`; startup/shutdown/error logger is third-party | Access logger also disabled in diagnostic configuration. Uvicorn lifecycle/error output remains; no global suppression. |
| SQLAlchemy / Psycopg / OpenAI / HTTPX / HTTPCore / Authlib | Library loggers | WARNING minimum, no DEBUG propagation. One owned sanitized warning/error handler per configured logger; no raw message/traceback, payload, SQL or URL. Component and severity identify the dependency; application errors retain safe error codes. |
| Parser logging | Existing pypdf NullHandler/no propagation | Existing privacy boundary preserved. |
| Direct Python prints | Search of runtime `backend/app` found none | No new prints in production. Synthetic probe output is test tooling only. |
| `src-tauri/src/diagnostics.rs` | Application-owned native JSON stderr emitter | Filters routine success/sampling/HTTP events outside DEBUG; bounded collector emits native reports in PERFORMANCE. |
| Tauri/Rust app | No log/tracing plugin or blanket Rust logger found | No plugin added. Explicit startup/shutdown diagnostics added; runtime failures remain visible. |
| Native privacy module | Existing direct `eprintln!` for verified state and safe issues; Win32 error classification | Retained: meaningful startup/affinity failures, no per-frame messages. Protection is never disabled. |
| React/TypeScript | Runtime console-log search found no recurring application console diagnostics | No console interception or client feature changes. Existing asynchronous panel readiness IPC reused. |
| Vite / Tauri CLI / Cargo / npm | Third-party build/watch/startup/HMR/compiler output | Left intact. No stdout/stderr-to-null redirection, dependency patches or compiler-error suppression. |
| PowerShell launchers | `scripts/backend.ps1`, `scripts/desktop.ps1`, npm scripts | Already inherit parent environment. No new launcher process, pipeline call or config override added. |

## Modes and precedence

Use uppercase `SOLVEGUIDE_DIAGNOSTIC_MODE=NORMAL|PERFORMANCE|DEBUG`.

1. An explicitly supplied diagnostic mode takes precedence over `SOLVEGUIDE_LOG_LEVEL`, including explicit NORMAL with legacy DEBUG.
2. If no mode is supplied, legacy `SOLVEGUIDE_LOG_LEVEL=DEBUG` retains DEBUG behavior; absent/INFO resolves NORMAL.
3. PERFORMANCE uses application logger level INFO and a separate instrumentation-enabled predicate. It does **not** enable application/global/library DEBUG.
4. Backend Pydantic configuration rejects an invalid mode. Native startup warns with a safe `invalid_diagnostic_mode` code and uses NORMAL for an invalid explicit value.
5. The backend accepts its environment or ignored `backend/.env`, with the existing environment-over-file precedence. Native reads its inherited environment, not the backend file. Set the mode in both terminals to avoid mismatched output. `.env.example` now explicitly recommends NORMAL; no real `.env` was edited.

| Mode | Backend terminal | Desktop terminal |
|---|---|---|
| NORMAL | App/Uvicorn startup/shutdown, warnings/errors/security failures. No successful auth/polling/query/provider-span chatter. | Startup/privacy status, meaningful monitor start/pause/resume/stop transitions, warnings/errors. No sampling/candidate-success/HTTP chatter. Build-tool output remains. |
| PERFORMANCE | NORMAL plus one correlated `performance_report` for each Vision or Answer HTTP request, including failed/cancelled requests. Routine polling never gets a success report. | NORMAL plus one report for each admitted native attempt reaching a terminal diagnostic boundary. Retries are separate attempt numbers; no duplicate report for that attempt. |
| DEBUG | Existing detailed spans/decisions/HTTP/query timings, still allowlisted and payload-free. | Detailed native timing/lifecycle/HTTP events, no summaries duplicated alongside spans. |

Warnings and errors are never filtered by routine-success rules. Dependency warnings/errors are sanitized rather than forwarding possibly sensitive SDK/SQL messages. A failure may legitimately have both an actionable error event and a final performance report; these serve different purposes.

## Aggregation and report format

Both terminals emit one-line structured JSON with `event=performance_report`. This is deliberately a diagnostic presentation, not another application API. There is no new synchronous cross-process call to combine clocks.

### Backend ownership

`boundary=backend_request` reports exactly one existing `/api/v1/vision/question` or `/api/v1/answer` request. It includes trace/request/candidate IDs, safe question type where available, request outcome/result, request total, SDK invocation count, auth/liveness/transaction/query counts and measured stage rows. The two requests for a question are separate correlated partial reports, not duplicate end-to-end reports. Polling/liveness costs outside these requests belong to native liveness timers; their detailed backend request events remain DEBUG-only.

SDK rows distinguish vision, answer, grounded draft, support verification, general supplementation and embedding roles. This measures SDK/network/parsing round-trip wall time, not OpenAI internal inference. The fake provider does not increment the SDK counter; reports do not invent a paid call just because a provider abstraction was invoked.

### Native ownership

`boundary=native_attempt` includes activation/candidate IDs, the dispatch attempt number, up to 16 actual backend request IDs, question type/result where available, native stage rows, panel readiness and observed-generation total where a terminal candidate measurement exists. `backend_ai_requests` counts distinct observed native Vision/Answer HTTP requests. `provider_calls` is null because native cannot observe backend verification/embedding SDK invocations.

The stage rows cover stability, dispatch capture, scheduling, frame fingerprint, encoder admission, PNG preparation, native credential validation, session validation, HTTP operation/headers/body-decode, post-vision gate, worker container/collection and panel acknowledgement. A failure/cancellation can finalize at worker termination before candidate/UI total is available; its total remains null rather than inferred. UI-ready is the existing React commit/IPC acknowledgement proxy, not physical paint.

### Duration integrity

- All durations use milliseconds. `stages_ms.<stage>={count,max_single_span_ms}` means the largest individual measured span and number of observations. It is **not a sum** or exclusive-stage total. Parallel/nested/repeated operations are never added to infer elapsed time.
- Backend `request_total_ms` is measured within Python. Native `observed_generation_total_ms` is measured within Rust from the first observed candidate change, including earlier failed attempts in that generation when applicable. The attempt number and request IDs identify which subset a report describes.
- Missing stages are JSON `null` (N/A), not zero. A measured zero can occur at millisecond resolution.
- Browser `panel_receipt_to_ready_ms` and `panel_validation_ms` remain local browser durations; native panel acknowledgement also includes IPC delivery. No absolute monotonic values are subtracted across processes.
- No exact physical first-appearance time, SDK-internal parsing split, pure network transit, pure pool wait or compositor paint measurement is claimed.
- Existing database setup includes checkout/connect/pre-ping when incurred and the unchanged transaction-local timeout statement. Query execution excludes some fetching/ORM/commit work.

## Correlation, bounds and cleanup

Backend aggregation is owned by the existing request ContextVar: a fixed vocabulary of 25 stage/role keys, counters, maxima and one question-type enum. No raw event history is stored. It is discarded with request context cleanup, including failure/cancellation.

Native aggregation is a process-local mutex-protected store of at most 32 candidate entries, 15 fixed stage keys and 16 request IDs per entry. It retains only safe IDs, enum metadata, counters, maxima and timestamps. Terminal summaries mark an attempt finished; later events cannot emit a duplicate. A new dispatch attempt resets attempt-specific measurements. Expiry after 600 seconds is lazy on the next relevant diagnostic event; eviction/expiry can report `diagnostic_evicted` / `diagnostic_expired` for unfinished admitted attempts. These mean measurement lifecycle, not a claimed application timeout. Finished tombstones are bounded and removed by expiry/eviction; shutdown drops the store. No background cleanup task or event-history accumulation is added.

The collection mutex protects only diagnostics, never monitoring state. Formatting/output happens after collection releases it. Native/React panel acknowledgements reuse the existing non-blocking diagnostic IPC and return no learning content. No diagnostic path sends HTTP, SQL or provider calls or changes monitor cancellation/state.

## Synthetic terminal verification

Separate local Python processes exercised the production diagnostic emitter and middleware with an in-process ASGI fake, fake auth and a local timed delay. There was no application server, account login, database or real provider.

Observed event sequences:

```text
NORMAL:      application_started, synthetic_warning, application_stopped
PERFORMANCE: application_started, performance_report, synthetic_warning, application_stopped
DEBUG:       application_started, http_request_started, stage_started,
             stage_finished, question_metadata, performance_stage, http_request,
             synthetic_warning, application_stopped
```

Sanitized projection from that actual synthetic PERFORMANCE output (irrelevant null rows omitted here only):

```json
{"event":"performance_report","boundary":"backend_request","request_id":"monitor-1-99-vision-aa","trace_id":"live-a-b-999","candidate_id":"question-1-99","outcome":"completed","question_type":"multiple_choice","request_total_ms":17,"observed_total_ms":null,"panel_ready_ms":null,"provider_calls":1,"database_transactions":0,"stages_ms":{"authentication":{"count":1,"max_single_span_ms":0},"provider_vision":{"count":1,"max_single_span_ms":17}}}
```

The `provider_vision` span above encloses a local delay, not OpenAI. These numbers are synthetic test observations, not product benchmark claims.

The native `diagnostics::reports::tests::synthetic_terminal_probe` also ran in three separate processes through the real production emitter (`--exact --nocapture`). NORMAL produced startup/warning/shutdown; PERFORMANCE added exactly one native report; DEBUG instead exposed the session event, three stage events and candidate-terminal event. The native fixture injects durations (including a 5,000 ms observed total) to verify presentation; these are not observed product latency. The probe invokes no Tauri window, capture, auth service, database or provider. Both probe families deliberately set legacy DEBUG while choosing explicit modes to exercise precedence. Sanitized temporary probe logs are under ignored `.cache/phase2a1-*`.

This does **not** establish live `npm.cmd run desktop` monitoring terminal behavior. That requires the authorized manual account/source/provider session. We did not sign in, start live monitoring, call OpenAI, connect to Neon or disable capture protection. The source audit establishes that no application console loop/logger bypass was found; third-party development output is not intercepted.

## Privacy safeguards

Reports contain only safe correlation IDs, enums, counts and durations. No account identity, owner ID, session credential, cookie, API key, URL query, database connection string, exception text, provider payload, image, question, answer or document passage is added. Explicit source authorization, mandatory auth, session revision/ownership/consent, cancellation, rate limits, provider behavior and ephemeral content boundaries are unchanged.

## Changed-file inventory for Phase 2A.1

Existing Phase 2A files not listed here retain their previous changes.

```text
backend/.env.example
backend/app/answer/api.py
backend/app/api.py
backend/app/config.py
backend/app/database.py
backend/app/diagnostics.py
backend/app/diagnostic_reports.py                 (new)
backend/app/main.py
backend/app/performance.py
backend/tests/test_answer.py
backend/tests/test_diagnostic_modes.py           (new)
src-tauri/src/diagnostics.rs
src-tauri/src/diagnostics/reports.rs              (new)
src-tauri/src/lib.rs
src-tauri/src/monitor/mod.rs
docs/DIAGNOSTICS.md
docs/MILESTONE_17_PHASE_2A.md
docs/MILESTONE_17_PHASE_2A_1.md                    (new)
```

No frontend component or website change is required for this refinement. Vite exclusions remain `['**/src-tauri/**', '**/.tools/**', '**/.cache/**']`.

## Validation results

Final regression results on 2026-11-04:

| Check | Result |
|---|---|
| Backend full pytest | **327 passed, 2 skipped**, 2 existing dependency warnings; final run 11.46 s. |
| Ruff lint / format check | Passed; 82 Python files formatted. |
| Frontend full suite | **158 passed**, 0 failures/skips. |
| ESLint / TypeScript / production build | Passed; 1,632 modules transformed. |
| Rust full tests | **60 passed**, 0 failed/ignored; binary/doc targets contain zero tests. |
| Cargo format check / offline check | Passed. |
| Project-standard `cargo clippy --offline -- -D warnings` | Passed. |
| Additional `clippy --all-targets -- -D warnings` | Fails on two pre-existing `items_after_test_module` lints in untouched `src-tauri/src/capture/mod.rs:235` and `src-tauri/src/privacy.rs:250`. No logging-module lint failed. Left unchanged to preserve scope. |
| `git diff --check` | Passed. |

Tests cover precedence/default modes, routine suppression, warning/error visibility, exact summary counts, correlation, request cleanup, missing stages, overlaps, retry/failure/cancellation, bounded expiry/eviction, redaction, unchanged provider/database call counts, and existing monitor state/cancellation safeguards. The old successful-INFO redaction test now explicitly captures DEBUG, matching the revised noise policy while testing more detailed output. Fourteen new backend cases and five native cases extend the Phase 2A checkpoint. No frontend logic was changed in this refinement.

Skipped tests require explicit disposable-PostgreSQL/reset or live PostgreSQL/RAG opt-in; neither was enabled. Existing Starlette/Authlib HTTPX deprecations, the Windows selector-policy harness deprecation and Cargo incremental-cache hard-link fallback remain. The standard commands exit zero; the separately broadened all-target lint limitation above is disclosed, not suppressed. No dependency installation, schema action, external provider call or remote connection was needed.

## Exact manual verification and next MCQ benchmark

Live OpenAI requests and Neon connections remain approval-gated. After approval, stop the previous processes with Ctrl+C and open two PowerShell terminals.

Backend:

```powershell
cd D:\solveguide-ai
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = "PERFORMANCE"
npm.cmd run backend
```

Desktop:

```powershell
cd D:\solveguide-ai
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = "PERFORMANCE"
npm.cmd run desktop
```

The environment travels PowerShell → npm → launcher → Python / Tauri CLI / native process. Vite inherits the variable, but it is not a `VITE_*` value and is not exposed to React. No source credentials are passed to the WebView. Changing the terminal variable requires restarting the running process; setting it in only one terminal does not change the other process. No `.env` edit is needed.

1. Sign in manually, start/recover a ready owned General session, explicitly select an authorized practice-question source and activate monitoring with the existing notice. Keep screen-share protection enabled.
2. Leave the page unchanged briefly. Routine success polling/query/capture logs should remain absent in both terminals. Compiler/HMR/startup messages and actionable errors remain visible.
3. Present one disposable MCQ and wait for a recommendation or honest abstention. Expect correlated backend Vision and Answer request reports and one terminal native attempt report after panel acknowledgement. Vision-only rejection, failure, cancellation or a retry can produce a different request count; do not treat attempt number alone as billing.
4. Match native request IDs to backend request reports. Read SDK counts there; never equate native HTTP count with OpenAI billing. Compare stage maxima individually and retain the measured total boundary. Do not sum nested spans or native/backend totals.
5. Pause/Stop during another candidate, then resume explicitly. Check cancelled/failed reports where timing exists, no obsolete answer, and unchanged immediate controls. Verify source closure/logout/session replacement using the existing manual procedure.
6. If output is focused, collect an approved initial 3–5 MCQs with cold/warm labels, correctness/abstention/error flags and safe correlation IDs. Count every SDK call against the approved budget. Extend to other categories and sufficient samples for p50/p90/p95 using the Phase 2A procedure only with approval. Do not record content or claim a latency improvement from this logging change.

Return both terminals to everyday operation and restart:

```powershell
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = "NORMAL"
# In the backend terminal:
npm.cmd run backend
# In the separate desktop terminal:
npm.cmd run desktop
```

For a specific detailed troubleshooting run, set this in both terminals before restarting their respective command:

```powershell
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = "DEBUG"
```

To use legacy behavior, remove the explicit mode from both the process environment and backend `.env` if present, then set `SOLVEGUIDE_LOG_LEVEL=INFO|DEBUG`. Explicit modes are recommended. Do not enable SQL echo, SDK/body traces or blanket `RUST_LOG=debug` to investigate performance.

## Limitations and approval checkpoint

No real MCQ latency, provider inference, Neon pool timing, physical paint, native focus, or live terminal-noise claim follows from the synthetic checks. Missing or bounded/expired diagnostics must be reported as unknown. A hidden panel or a stopped process may not send readiness; later expiry/eviction can close its diagnostic attempt. Warnings and third-party npm/Cargo/Tauri/Vite development output intentionally remain visible.

Phase 2A.1 stops after offline validation and review. No Phase 2B optimization, model/prompt/scheduler/rate/auth/database change, external benchmark, migration or publication is authorized by this implementation.
