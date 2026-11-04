# Milestone 17 Phase 2B — Latency and session reliability corrections

## Status and evidence boundary

Implemented in `D:\solveguide-ai` on baseline `609cdd1`, preserving all uncommitted Phase 2A/2A.1 instrumentation. No external service was contacted, no schema/migration was changed or applied, and nothing was committed/pushed/deployed. This is an implementation handoff, not another audit-only proposal.

The owner's live MCQ baseline is 34,122 ms observed generation, 30,815 ms worker pipeline, 3,161 ms detection, 16 ms scheduling, 71 ms capture and 125 ms image preparation. Vision and answer HTTP requests were 8,929/8,903 ms; their SDK wall times were 7,232/4,042 ms. These are supplied live measurements, not measurements produced by this pass. They overlap/nest; they must not be added indiscriminately.

The supplied failure had two native checks exceeding 12 seconds and backend HTTP 500 durations of 17,604/9,858 ms, with zero AI calls. It proves validation failed without provider work. The original exception and a complete matching trace are unavailable, so its exact exception/Neon cause is **not confirmed**. Source-confirmed contention, extra round trips, missing disconnect cancellation and inadequate classification were corrected; the next controlled live test must establish which caused that incident.

## Confirmed causes and implemented fixes

| Confirmed source behavior | Implemented correction / evidence |
|---|---|
| `auth/service.py:current_session` locked the credential row (`FOR UPDATE`) and updated activity on every ordinary authentication; `optional_current_user` then loaded User separately. Polling/parallel checks could contend on the same credential. | New `read_identity` joins AuthSession/User in one fresh SELECT, validates token hash/revocation/expiry every time, and does not lock ordinary reads. Advisory `last_seen_at` updates at most once per minute using an atomic predicate. This is metadata throttling, **not cached authorization**. Logout retains its locking mutation path. Invalid-length credentials fail before checkout. |
| `SessionRepository.transaction` took the User lifecycle lock even for preparation reads and answer configuration. General configuration additionally read links it never used. | New owned `reading` transaction for read/active/configuration, without the lifecycle mutation lock. General skips link/document/index reads. Read-only document inspection no longer locks documents; mutation transactions still lock account/documents and enforce existing unique/FK constraints. |
| Normal native pipeline made four separate validation operations around authenticated Vision and session-aware Answer. | One native pre-Vision validation remains. Native Vision now includes paired session ID/revision; backend checks owned active readiness before Vision. The session-bound Answer endpoint performs fresh pre/post configuration, plus fresh post-provider credential validation inside the post-configuration transaction. Removed native pre-encode, pre-answer and post-answer HTTP checks are replaced by these server-side boundaries, not cached trust. Incomplete/duplicate observations keep a final native validation before their observation-only result. |
| Heartbeat awaited inline before sampling and completed-worker collection; worker completion was only noticed after sleep/capture. | A loop-owned heartbeat future is polled alongside worker completion, cancellation and the unchanged sampling interval. Worker completion wakes the loop directly. A fresh source sample still precedes publication: if it detects a new generation, the completed old result is discarded. No detached heartbeat task, image queue or additional provider concurrency was introduced. |
| A stop notification could precede waiter registration. | Register the waiter and check the durable atomic cancellation flag; pre-existing Stop/Pause cannot be lost until a later sampling wake. |
| VisionRequestBoundary monitored disconnects only during upload; provider work/admission could remain active after a client left. Session-validation requests had no whole-request budget. | `run_connected` owns the application task and the sole post-upload disconnect watcher, cancels/awaits both on disconnect/cancellation/timeout, and releases the existing AI admission slot. Validation gets a 10-second whole-request budget (upload included), below the unchanged 12-second native deadline. Hot auth/config/liveness transactions have an 8-second cooperative budget. Finished-response disconnects are not mislabeled as cancelled work. |
| Database translation only caught SQLAlchemyError. Direct driver/connect/socket/timeouts could emerge as generic 500. | Classify SQLAlchemy, Psycopg, socket and transaction-budget errors without exception strings. Keep schema errors distinct, connection/pool/statement/transaction reasons, 503 availability and 504 timeout semantics. Existing pre-ping/pool limits/connect timeout/TLS URL handling remain. No silent transaction retry or pool expansion. |
| Every provider method constructed/closed another SDK/HTTP transport. | Application-owned lazy `ClientPool` shares the official SDK HTTP transport across Vision/Answer/Embedding and grounded verification/supplementation. Per-call SDK copies preserve distinct timeouts. Zero retries, models, prompts, structured schemas, image detail, reasoning effort, output limits and `store=False` remain unchanged. Shutdown closes transport and database even on exceptional lifespan exit. Standalone/test provider construction still owns its own client. |
| PERFORMANCE could expose only generic layered session 500 warnings. | One `session_validation_failure` report identifies correlation, HTTP status, elapsed time, error category/code, first failed stage and safe reason. Unexpected bugs add a fixed exception-kind label and application module/function/line where available; no exception text, source line or payload. NORMAL/PERFORMANCE/DEBUG policies remain. |

## Security and correctness boundaries

- Mandatory authentication, hashed credentials, token revocation/expiry, owner scope, active status, revision, selected-document readiness and explicit transmission consent remain authoritative on the backend.
- No authorization TTL/cache was introduced. A recent activity timestamp never proves identity. Fresh ORM reads explicitly repopulate existing identity-map state.
- Session Answer rechecks credentials after the provider and reads the owned session in the same short postflight transaction. A revoked credential, ended/replaced session or changed revision rejects the result before return. No transaction/row lock/connection is held across OpenAI reasoning.
- The native Live Monitor injects its selected session metadata into Vision. Optional paired fields preserve existing manual Vision compatibility; their presence is validated strictly. An invalid/foreign/unready/revised session executes no Vision provider call.
- General still bypasses retrieval. Context Guided still distinguishes supplementation. Materials Only still validates evidence/citations and abstains; no extra provider calls or changed evidence policies were introduced.
- Source selection, run/generation checks, FrameIdentity/question dedup, stability/admission/backoff limits, request caps and the single provider slot remain. Completed work is checked against a fresh observed source generation before publication. Sampling intervals/stability thresholds and the 30-second start-spacing safeguard were not reduced.
- Pause/Stop/logout/source replacement still cancel native provider work. The server now reacts to ASGI disconnects after upload. Captures/observations/answers remain ephemeral; no tables, history, capture permissions, website, branding, floating-panel focus policy or capture exclusion changed.

## Structural before/after comparison

These are source/contract-derived counts for a normal successful **General** candidate, not a new live latency benchmark. They exclude background/UI traffic, pool pre-ping, transaction protocol messages and occasional coarse activity updates. Actual diagnostics are authoritative.

| Work | Before | After |
|---|---:|---:|
| Independent native candidate liveness HTTP calls | 4 | 1 |
| Candidate HTTP operations including Vision/Answer | 6 | 3 |
| General answer transaction contexts | 3 | 3 (fresh security checks retained) |
| General answer SQL executions including SET LOCAL | 12 (also observed live) | normally 7 |
| Whole candidate transaction contexts | normally 12 | normally 7 |
| Whole candidate SQL executions including SET LOCAL | normally 40 | normally 15 |
| Vision/Answer SDK calls for General | 2 | 2 |

New Vision authorization accounts for an extra lightweight backend session transaction inside the existing Vision HTTP request. The post-answer credential read is inside the existing post-configuration transaction. The counts above include both; they do not pretend three checks simply disappeared. Grounded modes perform additional existing ownership/index/retrieval/verification work; use their measured counts separately.

Expected benefits: three fewer high-latency candidate HTTP round trips, fewer SQL executions/commits, less credential/account lock contention, reusable HTTP connections, and no sampling/heartbeat delay in noticing worker completion. These are justified structural improvements; no precise number of seconds saved has been measured against Neon/OpenAI.

The owner's two SDK awaits alone occupied about 11.27 seconds in that run. Local overhead improvements do not demonstrate a 3–5 second total. Provider time still varies. Combining Vision/Answer or changing models/prompts/effort could affect neutral extraction, visual accuracy, RAG evidence and the screenshot boundary; those are separate comparative-quality/approval proposals, not changes made here.

## Timeouts, errors and cleanup

| Boundary | Policy |
|---|---|
| Native validation | Unchanged 12-second deadline; cancellation wins; overlap-only coalescing remains, no TTL result reuse. |
| Server validation | 10 seconds for body + auth + liveness + transaction completion; `session_validation_timeout` / HTTP 504. |
| Hot auth/read transactions | 8 seconds including setup/body/commit; `database_timeout` / 504 when exhausted. General database mutation transactions retain existing policy. |
| Pool/connect/statement | Existing pool timeout 5 s, connect timeout 5 s, transaction-local statement timeout 10 s; pre-ping/TLS parameters unchanged. |
| Provider requests | Existing per-provider timeouts, SDK zero retries, native backoff/caps unchanged. |
| Database failure during candidate | Fail closed and stop explicitly with database-specific action; do not label it expired authentication or silently run paid retries. |

The server timeout has a distinct code from native `session_check_timeout`, so a server budget failure is not described as an exceeded native 12-second deadline. Availability failures never count as successful authentication. Native messages distinguish connection, database timeout, configuration/schema and real credential/session failures.

Cancellation is cooperative. The middleware cancels and awaits its owned async tasks; no application task is detached. Driver cancellation/rollback/close can itself take time during an external outage. A provider request already received remotely cannot be recalled or guaranteed unbilled. Proxy buffering/OS socket behavior must be verified live. Blocking image-validation work is bounded but cannot be forcibly killed mid-thread; cancellation prevents its subsequent provider step. These limits are not hidden by a longer desktop timeout.

## Diagnostics

Use the existing `SOLVEGUIDE_DIAGNOSTIC_MODE=NORMAL|PERFORMANCE|DEBUG` precedence and both-terminal setup from Phase 2A.1. Routine successes remain quiet. A validation failure in PERFORMANCE now produces one safe summary, for example the following **schema illustration, not a benchmark**:

```json
{"event":"session_validation_failure","error_code":"database_timeout","error_category":"database","stage":"database_transaction","reason":"database_transaction_timeout","exception_kind":null,"site":null}
```

Real output also supplies measured duration/status and existing safe correlation IDs. Unexpected application bugs retain `internal_error` but disclose a safe kind such as `type_error`, stage and `site={component,function,line}` when resolvable. No raw traceback, SQL, credentials, URLs, account data, image/question/answer/passage content is logged. First failure stage/reason is retained rather than overwritten by outer wrappers.

## Offline validation and synthetic evidence

Final offline validation on 2026-11-04:

| Check | Result |
|---|---|
| Backend complete pytest | **345 passed, 2 skipped**, 2 existing dependency warnings; final run 7.38 s. |
| Ruff lint / formatting check | Passed, 85 Python files formatted. |
| Frontend complete tests | **158 passed**, zero failed/skipped. |
| ESLint / TypeScript / production build | Passed; 1,632 modules transformed. |
| Rust complete tests | **63 passed**, zero failed/ignored; binary/doc targets have zero tests. |
| Cargo formatting / offline check | Passed. |
| Standard Clippy `-- -D warnings` | Passed. |
| `git diff --check` | Passed. |

The two skipped tests require explicit disposable PostgreSQL/reset or live PostgreSQL/RAG opt-in; neither was enabled. Existing Starlette/Authlib HTTPX deprecations, the Windows selector-policy test-harness deprecation and Cargo incremental-cache hard-link fallback remain. The prior additional all-target Clippy findings are not silently treated as fixed: capture/privacy module ordering remains out of scope, with no source changes or lint suppressions in those files. Local Cargo lock waits were build-tool contention, not runtime measurements.

Eighteen new backend cases and three native cases extend the Phase 2A.1 checkpoint. New regression coverage includes fresh joined reads, repeated/revoked/expired identity, coarse metadata writes, direct driver/socket/SQLAlchemy failures, subsequent connection-boundary recovery, transaction timeout/cleanup, request disconnect releasing admission, server deadline cancellation and no-store response headers, unexpected-500 diagnostic safety, shared SDK options/concurrency/cancellation recovery, session-bound Vision rejection and fresh post-answer revocation/end/revision rejection. Test doubles were updated for the new joined SELECT, read transaction boundary and optional timeout argument. Old native sequence assertions were updated to the server-enforced pipeline. Initial outdated-double/assertion failures were corrected; no required final check remains failing.

The request-boundary synthetic test blocks a fake first provider, confirms a second is rejected without another provider call, injects disconnect, observes cleanup/slot release and successfully admits the next request. This confirms local task/admission cleanup; it does not prove a real server/provider's billing behavior.

The native scheduling test uses a pending heartbeat and a 30-second sampling sleep; a ready worker is selected within the independent 1-second test bound. Cancellation and a failed ready heartbeat win over ready worker output. Another test checks cancellation set before waiter registration. Existing stale-generation, source-close/identity, visual/editing-prompt, dedup and pause/session tests continue to run.

Mock SDK requests reuse one real SDK/HTTPX MockTransport client across distinct timeout options; no extra request is sent by pooling. Concurrent use and recovery after a cancelled mock request are tested. No live speed distribution, TCP/TLS/Neon pool behavior or physical paint/focus improvement was measured. No synthetic before/after time is presented as a product benchmark.

## Phase 2B changed-file inventory

Prior Phase 2A/2A.1 changes in other files remain preserved.

```text
backend/app/auth/dependencies.py
backend/app/auth/service.py
backend/app/database.py
backend/app/learning/repository.py
backend/app/learning/service.py
backend/app/api.py
backend/app/answer/api.py
backend/app/schemas.py
backend/app/providers/client.py                   new
backend/app/providers/openai.py
backend/app/answer/openai.py
backend/app/rag/embedding.py
backend/app/main.py
backend/app/middleware.py
backend/app/request_lifetime.py                   new
backend/app/diagnostics.py
backend/tests/test_auth.py
backend/tests/test_access.py
backend/tests/test_learning.py
backend/tests/test_phase2b.py                     new
src-tauri/src/diagnostics.rs
src-tauri/src/monitor/mod.rs
src-tauri/src/monitor/pipeline.rs
src-tauri/src/monitor/scheduling.rs                new
docs/MILESTONE_17_PHASE_2B.md                      new
```

Important code entry points: `auth/service.py:read_identity`, `learning/repository.py:reading`, `learning/service.py:configuration/recommend`, `providers/client.py:lease/ClientPool`, `request_lifetime.py:run_connected/SessionRequestBoundary`, and native `monitor/scheduling.rs:wake` / `monitor/mod.rs:run_loop`. All library calls remain in the existing modular monolith.

## Remaining risks and known limitations

- The actual incident's original HTTP 500 exception remains unconfirmed. The corrections address confirmed source defects/overhead and expose the next failure safely. Do not claim Neon itself was proven faulty.
- Actual PostgreSQL isolation/constraints, remote revocation timing, stale-socket recovery, provider transport reuse, latency and disconnect behavior require an approved live retest. Optional integration tests remain disabled; no migration is required.
- Faster answers can expose the unchanged 30-second candidate-start cap as a larger share of next-question latency. The supplied first successful candidate had only 16 ms scheduling delay, so the cap was not its measured bottleneck. Do not silently increase spending by lowering it; report cooldown cohorts separately.
- Detection still measures first observed change, not physical appearance. Panel readiness remains React/IPC, not compositor paint. Native and backend totals do not share a clock and must not be summed.
- Existing additional `--all-targets` Clippy ordering lints in untouched capture/privacy test modules remain documented from Phase 2A.1; standard Clippy with warnings denied is the required project check. No lint suppression/reordering of those unrelated modules was introduced.
- Models, prompts and quality parameters were deliberately unchanged; no claim of improved AI accuracy or guaranteed correctness follows from passing mocked regressions.

## Controlled live retest — explicit external approval required

This engineering pass did not perform external requests. After the owner approves/executes live benchmarking, restart **both updated backend and desktop** (the revised native/backend contract is intended to ship together). No installer, deployment or migration step is needed.

Backend terminal:

```powershell
cd D:\solveguide-ai
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = "PERFORMANCE"
npm.cmd run backend
```

Desktop terminal:

```powershell
cd D:\solveguide-ai
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = "PERFORMANCE"
npm.cmd run desktop
```

1. Sign in manually; recover/start a ready General session. Keep screen-share privacy ON. Choose the authorized practice source and explicitly start monitoring. Never auto-start or silently switch sources.
2. Present a disposable straightforward MCQ; hold it stable through the result. Collect correlated native/backend reports. Expect normally one native candidate validation, a session-bound Vision request and a session Answer request, with two SDK invocations in General. Heartbeats and advisory activity writes are separate from these expectations.
3. Confirm correct option labels/instructions, explanation, no duplicate processing and normal floating-panel focus behavior. Record SDK wall time, auth/config/read transaction counts, worker collection and observed total. Compare to 34,122 ms only with the same category/mode and cold/warm labels. Never sum overlapping spans.
4. Test Pause/Stop while reading and answering, resume explicitly, rapidly navigate to a new question, close the selected source, end/replace the session and log out. Old replies must not reappear. Restore the source and start explicitly after recoverable failure.
5. Using a disposable second session/client, revoke/end/revise the active session during a delayed request. Confirm the final recommendation is rejected. Do not use personal documents to test this.
6. If validation fails, capture only the safe `session_validation_failure`, matching native request ID, code/reason/stage/kind/site and durations. A database timeout/availability failure must stop safely, not masquerade as expired auth. Check whether server cleanup completes after desktop cancellation.
7. With approval and an SDK-call budget, collect at least 3–5 cold/warm pilot MCQs, then enough comparable warm samples for p50/p90/p95. Count vision/answer/embedding/verification/supplementation separately. Follow Phase 2A's sample-size rules; no unapproved repeated paid requests.
8. Retest Context Guided with relevant and irrelevant selected evidence, Materials Only support and abstention, multiple-select counts, code/math, diagrams, odd-one-out, patterns and the controlled editing comparison/Copy Response. Preserve citation integrity and all five supported visual changes without fabricated colors.

Retain only safe benchmark metadata, not screenshots/questions/answers/material passages. If detailed troubleshooting is needed, explicitly set DEBUG in both terminals and restart; return NORMAL after collection. Any further model/prompt/combined-provider experiment needs comparative quality/privacy review and separate approval. Stop after this implementation and review; no publication has been performed.
