# Milestone 17 Phase 2A — Instrumentation and legacy intelligence verification

Follow-up: `MILESTONE_17_PHASE_2A_1.md` adds NORMAL/PERFORMANCE/DEBUG modes.
References below to DEBUG-only collection describe the original Phase 2A checkpoint;
the same timings are now collected silently in PERFORMANCE and printed in DEBUG.
The recommended benchmarking commands below use the focused PERFORMANCE mode.

## 1. Executive summary

Baseline: `609cdd192a9cfc6e025e10c0e1082cd0df088f60`. The pre-existing Phase 1 audit was preserved. This phase adds observational, DEBUG-only monotonic measurements; it does not optimize the pipeline. No live OpenAI request, Neon connection, migration, configuration change, deployment or Git publication was performed.

The tracked runtime contains no general-purpose legacy local question solver. OpenAI supplies observations and recommendations. Local visual editing-prompt composition, evidence/answer validation, retrieval ranking and question deduplication remain active; their distinct roles are described below. Their existence does not establish that they cause the observed 20–35 second latency.

No real latency distribution has been measured in this phase. Synthetic tests establish timing arithmetic, isolation and safety, not production response speed.

## 2. Files changed

- `backend/app/performance.py`: lightweight monotonic spans, parent identifiers and provider roles.
- `backend/app/diagnostics.py`: safe fields, per-request counters and context isolation.
- `backend/app/database.py`: query execution callbacks and existing transaction-setup timing.
- `backend/app/api.py`: existing image-validation worker boundary.
- `backend/app/providers/openai.py`: vision SDK wall time and independent validation.
- `backend/app/answer/openai.py`, `answer/service.py`: answer/draft/verification SDK time, formatting and validation.
- `backend/app/learning/service.py`: authoritative pre/post-answer configuration checks.
- `backend/app/rag/{embedding,repository,retrieval,service}.py`: embedding roles, selection/ranking and supplementation attribution.
- `src-tauri/src/diagnostics.rs`: native stage timer and allowlisted timing fields.
- `src-tauri/src/auth.rs`: existing AI HTTP headers and body/decode boundaries.
- `src-tauri/src/monitor/{mod,pipeline,performance}.rs`: candidate lifecycle clocks, capture aggregates, liveness roles, observation gate and readiness acknowledgement.
- `src/monitor/{types,client,performance}.ts`, `src/components/MonitorPanel.tsx`: strict metadata and one-shot UI-ready acknowledgement.
- `backend/tests/{test_performance,test_database}.py`, `tests/{performance,monitor}.test.mjs`: synthetic regressions and updated engine-listener fake.
- This document and the Phase 1 audit addendum.

Exact changed/new file inventory (all relative to `D:\solveguide-ai`):

```text
backend/app/answer/openai.py
backend/app/answer/service.py
backend/app/api.py
backend/app/database.py
backend/app/diagnostics.py
backend/app/learning/service.py
backend/app/performance.py
backend/app/providers/openai.py
backend/app/rag/embedding.py
backend/app/rag/repository.py
backend/app/rag/retrieval.py
backend/app/rag/service.py
backend/tests/test_database.py
backend/tests/test_performance.py
docs/MILESTONE_17_LATENCY_AUDIT.md
docs/MILESTONE_17_PHASE_2A.md
src-tauri/src/auth.rs
src-tauri/src/diagnostics.rs
src-tauri/src/monitor/mod.rs
src-tauri/src/monitor/performance.rs
src-tauri/src/monitor/pipeline.rs
src/components/MonitorPanel.tsx
src/monitor/client.ts
src/monitor/performance.ts
src/monitor/types.ts
tests/monitor.test.mjs
tests/performance.test.mjs
```

No dependency, schema, migration, website, capture permission, screen-share privacy, prompt, model or scheduler configuration was changed.

## 3. Instrumentation architecture

Rust uses `Instant`, Python uses `time.monotonic`, and the WebView uses `performance.now`. All duration calculations stay inside the originating process. Wall-clock diagnostic timestamps help humans order terminals but are not used for duration subtraction.

Backend `Timing` is inert at INFO: it does not read its injected clock or emit timing events. Existing INFO diagnostics remain. SQL listeners return immediately outside DEBUG. Native candidate bookkeeping and panel metadata are enabled only when `SOLVEGUIDE_LOG_LEVEL=DEBUG`; normal operation sends no diagnostic acknowledgement. Native timers still have a small construction/level-check overhead. No high-frequency frame log is added: capture timing is aggregated per admitted generation, with one dispatch-frame measurement.

A `performance_ready` IPC operation is restricted to the owned answer panel, current generation and existing answer. It accepts bounded durations and returns an empty snapshot. It does not access credentials, call a backend, mutate learning state or run ordinary monitoring-control authorization/stop logic. It is observational, not an authorization channel.

## 4. Available timing events and interpretation

`performance_stage` is the new detailed event. Existing `stage_started`, `stage_finished`, `http_request`, `database_transaction`, `backend_http`, session and monitor lifecycle events remain useful. Exact event names are preserved; stages are fields, not new routes.

| Stage / event | Boundary and interpretation |
|---|---|
| `detection_stability` | Native observed frame-change generation to first stability acceptance; excludes unobserved screen appearance and earlier capture. |
| `candidate_capture` | Native capture of the frame dispatched for an admitted candidate. Other captures are aggregated. |
| `performance_candidate` | `capture_count`, `capture_sum_ms`, `capture_max_ms`, `sample_gap_max_ms`; one admitted generation's aggregate sampling observations. Not additive to total. |
| `candidate_scheduling` | Stability acceptance to each dispatch; `attempt` and initial/retry reason identify cooldown/backoff/admission waiting collectively. Does not decompose every gate. |
| `frame_fingerprint` | Eligible full-frame identity hashing; no fingerprint or pixels logged. |
| `encoder_slot_wait`, `image_preparation` | Existing blocking-encoder admission and PNG preparation worker await; worker scheduling is included. No resizing is introduced. |
| `session_validation` | Existing native liveness call with roles `pre_encode`, `pre_vision`, `pre_answer`, `post_answer`, or generic `liveness` for other checks. |
| `backend_http` | Full existing native authenticated HTTP operation. Match endpoint, status and request ID. |
| `backend_response_headers` | Existing AI send-to-headers wall time; includes backend/provider processing, not just network. |
| `backend_response_body_decode` | AI response body acquisition plus JSON decode. Not pure wire transit. |
| `http_request` | Backend request lifetime with DEBUG counters for authentication, liveness, transactions, queries and SDK calls. Counts are per HTTP request, not deduplicated logical callers. |
| `authentication` (`stage_finished`) | Existing authentication span. Includes its existing database access. |
| `database_setup` | Existing `SET LOCAL` execution await, including lazy connection checkout/connect/pre-ping where incurred. Not pure pool wait. |
| `database_query` | SQLAlchemy before/after cursor execution (or error) duration. No SQL, parameters, table content or credentials. |
| `database_transaction` | Existing transaction context lifetime including commit/rollback/close; query count and summed cursor time are child measurements. |
| `session_liveness`, `active_session_lookup` | Existing backend session operations. Do not equate all full-configuration checks with lightweight liveness. |
| `session_configuration_before`, `session_configuration_after` | Existing authoritative answer-session checks; no checks removed or cached. |
| `image_validation_worker` | Existing backend PNG validation/threadpool await, including scheduling. |
| `provider_sdk`, role `vision` | Existing OpenAI vision `responses.parse` await. |
| `vision_validation` | Independent Pydantic observation revalidation after SDK parse. |
| `observation_gate_dedup` | Native quality, completeness, direction and duplicate gate; outcomes accepted/incomplete/duplicate. This does not classify or solve questions independently. |
| `reference_selection`, `reference_ranking`, `retrieval` | Existing selected-document ownership/readiness, ranking and retrieval containers. |
| `provider_sdk`, role `query_embedding` / `embedding` | Existing conditional query/document embedding call; no new embeddings are requested. |
| `provider_sdk`, role `answer` / `grounded_draft` / `verification` / `answer_supplement` | Existing answer, grounded draft, support verification and Context Guided general fallback calls distinguished. |
| `answer_validation`, `answer_formatting`, `answer_validation_formatting` | Existing independent schema/semantic validation and visual formatting; containers can overlap/nest. |
| `candidate_pipeline` | Existing native candidate worker container, not provider-only time. |
| `worker_collection` | Worker completion to native collection/publication, exposing capture/heartbeat gating if present. |
| `panel_ready_ack` | Native publication to receipt of panel acknowledgement; contains browser `receipt_to_ready_ms` and `validation_ms`. Upper bound, not physical paint. |
| `observed_to_terminal` | Native generation observation to acknowledgement, cancellation, supersession, failure or no-answer terminal outcome. Only a UI-ready outcome is a successful total proxy. |

Provider stages include a safe model identifier and provider category when allowlisted. Arbitrary model strings are omitted. `sdk_max_retries=0` records the unchanged current adapters; native candidate retries remain separate attempts. API wall time includes HTTP, SDK decoding and SDK structured parsing; it is **not OpenAI internal inference time**.

## 5. Correlation strategy

1. Group by native activation `trace_id` (`live-...`).
2. Within it group by `candidate_id` (`question-run-generation`), not the visible attempt counter alone.
3. Join each backend HTTP operation using `request_id`; vision, answer and session requests have different IDs. Backend sanitizes incoming IDs using the existing formats.
4. Backend detailed spans have request-local `span_id` / `parent_span_id`, request-relative start/end offsets, and operation roles for SQL. Existing decorator spans retain their event format and may not form a complete parent tree.
5. Native detailed candidate offsets use that candidate's origin. Other native HTTP/session timers have durations without candidate offsets. The IPC descriptor carries only trace/candidate/generation and elapsed metadata; no session credentials or content.
6. Browser duration uses only its own IPC receipt and React effect times. The acknowledgement matches the current native generation; late acknowledgements cannot mark another generation ready.

Do not subtract Rust, Python and browser monotonic origins. Do not sum HTTP, provider, transaction, query and pipeline containers: they overlap. A 1,000 ms parent containing a 300 ms child is still 1,000 ms. Retries/backoff belong inside one observed-generation elapsed total, not extra totals to be added again. An SDK request counter means an invocation, not verified billing.

## 6. Legacy Local Intelligence Audit

The current runtime was traced from `src/main.tsx` through the authenticated workspace, native monitor, FastAPI vision, session-aware answer/RAG and floating panel. These findings concern the tracked implementation at this baseline, not an unavailable external prototype.

| Component / exact entry | Active and callers | Classification / blocking implications |
|---|---|---|
| `src-tauri/src/monitor/filter.rs`: `Gate`, `Signature`, `CompletedFrame` | Native monitor run loop | Essential local detection, stabilization, duplicate/rate gates. Intentional waits, no answer selection. |
| `src-tauri/src/monitor/mod.rs`: `fingerprint`; `pipeline.rs`: `execute` | After remote vision, before remote answer | Useful preprocessing: quality/complete/direction validation and duplicate suppression. Synchronous bounded traversal, no local correct-option inference. |
| `backend/app/schemas.py`: visual consistency validators | SDK and independent Pydantic observation validation | Contract normalization, including explicit editing intent. No separate remote/local question-solving contest. |
| `backend/app/answer/service.py`: `abstain`, `validate_recommendation`, `AnswerService.recommend` | General and supplemented answer paths | Essential safety/format checks: labels, counts, question compatibility, incomplete visuals. May abstain; does not discover a correct MCQ option. |
| `backend/app/answer/visual.py`: `editing_response`, `compose_editing_response`, `visual_limitation` | `OpenAIAnswerProvider` and `AnswerService`; grounded formatting before support verification | Active deterministic visual composition: converts already extracted supported differences into an editing prompt, preserves unchanged properties, excludes uncertain edits. Can replace successful provider wording. Intelligence-like formatter with demonstrated visual-accuracy purpose; not a general solver. Synchronous; possible repeated formatting/validation is now timed, not removed. |
| `backend/app/rag/retrieval.py`: `lexical_query`, `bounded_evidence`, `Retriever.retrieve`; repository ranking | Context Guided / Materials Only only | Useful retrieval preprocessing, ranking, thresholds, dedup and evidence budget. Regex/stopwords do not generate an answer. General bypass remains. |
| `backend/app/rag/service.py`: `grounded_result`, `recommend_selected`, `general_fallback` | Session-aware selected-document answer path | Essential evidence/citation/consent policy. General fallback invokes the same OpenAI answer service; it is not a hardcoded local answer. Additional verification/supplementation calls can add latency and are separately attributed. |
| `backend/app/learning/service.py`: `guard_legacy` | Legacy-shaped answer request boundary | Essential authorization compatibility guard, not legacy intelligence. |
| `src-tauri/src/auth.rs`: `legacy_transport_error` | Native error mapping | Infrastructure compatibility, not reasoning. |
| `backend/app/__init__.py` old “local intelligence” docstring | Package import only | Inactive descriptive text; no solver implementation. Left untouched. |
| `tests/`, `tests/helpers/desktop.mjs`; `src/brand/BrandShowcase.tsx`, `src/brand/main.tsx` | Offline fakes / isolated development showcase | Hardcoded examples are not Live Monitor production answer generation. Production providers remain OpenAI. |

Tracked history evidence: the first commit `0ffb1bb92733350fcaf020196604b7659312df66` has native capture and no backend. Its `src/components/AnswerWorkspace.tsx` explicitly presents “Capture first. AI analysis comes later.” and empty answer sections. Subsequent `8ce2923` introduces vision and `cdc54ca` structured recommendations. No original general local solver was found in the inspected tracked runtime/history boundary. This is **not proof that an earlier untracked prototype never existed**.

## 7. Active versus inactive local processing

Active local work is capture/orchestration, frame filtering, PNG encoding, schema normalization, deterministic editing-prompt composition, retrieval, authorization and evidence validation. None was removed. Classification is primarily inside remote vision and its structured output; the native post-vision timer is deliberately named an observation gate, not an independent classifier. Development examples and the stale package docstring do not participate in monitored requests.

## 8. Potentially redundant intelligence

Visual composition/revalidation can occur at more than one boundary. This is a candidate for **measurement**, not a confirmed latency defect. It also enforces validated changes and citation support; removing it could regress the controlled slide tests. Lexical query preparation and evidence gates provide required selected-document constraints. No evidence supports blaming either for 20–35 second latency. No local logic was disabled/refactored in Phase 2A.

## 9. Known measurement limitations

- First observable candidate means the native post-capture change observation, not the exact moment a question appeared on screen. Initial capture can precede that clock. Sampling blind intervals remain unmeasured physical appearance time.
- Capture aggregates are bounded metadata, not a frame trace; `sample_gap_max_ms` also includes work between samples. Capture totals overlap other containers and may include the first pre-origin capture. Per-gate wait decomposition is unavailable.
- Panel readiness is a passive React committed-state effect plus acknowledgement IPC; it proves neither compositor paint nor native focus behavior. A hidden/dismissed panel or shutdown may produce no UI-ready total. Some abrupt terminal paths finish as cancelled; existing lifecycle failure events supply the cause.
- Native liveness coalescing remains unchanged. A coalesced waiter does not expose a separate leader request ID; count actual backend requests/counters, not every logical waiter as another query. Generic `liveness` covers start/heartbeat/reopen rather than separate role names.
- SQL cursor timings exclude some fetch/ORM hydration/commit/rollback work; setup combines connection acquisition and the existing timeout statement. Pure pool wait and connect/TLS breakdown are unavailable without deeper driver instrumentation.
- SDK `responses.parse` includes structured decoding; independent revalidation is separately timed, SDK-internal parsing is not. No server inference, token-arrival or hidden retry timeline is claimed. Existing adapters use retries zero and non-streaming responses.
- Serialization, network transit and SDK/client creation/close are not fully isolated. Native send-to-headers includes server work. HTTP versus backend duration differences are approximate residuals, not exact network latency.
- DEBUG logs have observer overhead. Existing request/candidate limits remain unchanged. Missing boundaries stay absent/unknown; do not impute zero.

## 10. Privacy and security safeguards

Only allowlisted stage/outcome/role/model tokens, safe IDs, counts and durations are added. No SQL text/parameters, exception strings, questions, answers, passages, images, headers, cookies, credentials, URLs with query strings or provider payloads are added to diagnostics. Third-party SDK/HTTP/SQL payload logging stays suppressed. No external telemetry or content history is introduced.

Authentication, server-authoritative session revisions, ownership, consent, cancellation, stale-generation checks, bounded provider slots and screen-share affinity are unchanged. General still bypasses retrieval; Context Guided may supplement honestly; Materials Only keeps evidence abstention. Instrumentation adds no network operation or provider call. The panel acknowledgement is local IPC only.

## 11. Automated validation

Synthetic timing tests use injected clocks, ASGI/mock providers, SQL execution-context fakes and local IPC snapshots. They do not establish real provider latency, Neon latency, billing, visual model accuracy or native compositor/focus behavior.

Final validation on 2026-11-04:

| Check | Result |
|---|---|
| Backend full pytest suite | **313 passed, 2 skipped**, 2 dependency warnings; final run 15.21 s. |
| Ruff lint / format | Passed; 80 Python files already formatted. |
| Frontend full interaction suite | **158 passed**, 0 failures/skips. |
| ESLint / TypeScript | Passed, zero lint warnings. |
| Production frontend build | Passed, 1,632 transformed modules. |
| `cargo fmt --check` | Passed. |
| `cargo check --offline` | Passed. |
| `cargo test --offline` | **55 passed**, 0 failed/ignored; binary/doc targets have zero tests. |
| `cargo clippy --offline -- -D warnings` | Passed; no Clippy code warnings. |
| `git diff --check` | Passed. |

Skipped tests are the explicit disposable-PostgreSQL migration roundtrip and opt-in live PostgreSQL/RAG rollback test. Neither was enabled. Backend tests used the existing Windows selector-loop harness; local asyncio socket restrictions required an approved test execution context. No external service was called. Existing Starlette/Authlib HTTPX deprecations and the harness's Windows loop-policy deprecation remain. Cargo emits a filesystem hard-link fallback warning for its incremental cache; copying succeeds and all commands exit zero. No cache/toolchain reconfiguration was introduced.

The database regression fake now supplies an engine listener boundary while retaining its assertions about PostgreSQL URL parameters, transaction-local timeout, commit/rollback and cleanup. An initial test-double failure was corrected; there are no remaining failing tests. Eight new Python timing cases, five new frontend cases and three native instrumentation cases cover timing/correlation/redaction, missing clocks, overlaps/retries, metadata validation and acknowledgement isolation alongside the existing reasoning/visual/auth/session regressions.

The diagnostic acknowledgement has a native regression that checks current/obsolete generations, bounded fields, caller restriction, a content-free reply, rejection of an injected control field, and unchanged run/phase/content/cancellation. The command returns this reply immediately, so acknowledgement cannot fall through to normal monitor controls or credential validation.

During final validation, a single existing status-message line was found with extreme repeated character-encoding corruption (approximately 283 MB). That line alone was restored verbatim from HEAD; instrumentation and all other working changes were preserved. This explained the stalled formatter. No toolchain reinstall or dependency change was needed. Normal source size and formatting/check speed were restored. This was a development-file correction, not a Live Monitor performance optimization.

## 12. Manual benchmarking instructions — approval required

Do not execute the following until the owner explicitly approves both live provider use and the configured Neon access required for authentication/session checks. Do not change `.env`, models, prompts, thresholds or retry settings for the baseline.

After approval, open two PowerShell terminals:

```powershell
# Backend terminal
Set-Location D:\solveguide-ai
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = 'PERFORMANCE'
npm run backend
```

```powershell
# Desktop terminal
Set-Location D:\solveguide-ai
$env:SOLVEGUIDE_DIAGNOSTIC_MODE = 'PERFORMANCE'
npm run desktop
```

Stop existing processes first using their terminal Ctrl+C. The environment setting is process-local; both processes need restarting. Keep screen-share protection enabled. Use disposable authorized practice content, not personal documents. Sign in manually, recover/start a session, explicitly select the source and activate monitoring with its cost notice. Do not automate account login or answer submission.

Benchmark these categories separately: simple MCQ, True/False, short theory, Odd One Out, Visual Sequence, Diagram Interpretation, complex image comparison and coding. Use General first to isolate retrieval, then separate Context Guided relevant/irrelevant and Materials Only supported/abstention cohorts with explicitly consented disposable references. Keep session mode authoritative.

For each sample record only category, mode, cold/warm label, run/candidate/request IDs, stage durations, outcome, call count, and a human correctness/support flag. Do not export question/answer/passages or full provider payloads into benchmark logs. Record question appearance with an independent human observation separately and label its uncertainty.

Collect an initial paid pilot of 3–5 per category only within an approved request budget. Budget SDK invocations, including vision, embedding, verification, supplementation and native retries, rather than counting a candidate as one paid call. Pause between samples when preparing a new page, then resume explicitly; record any resulting run change. Expand with approval to at least 20 warm samples/category for useful p90, and preferably 100 for a defensible p95; small-sample p95 must be labeled unstable. Report n, nearest-rank percentile method, p50/p90/p95, min/max, errors/cancellations/abstentions, SDK invocation counts, and cold versus warm results separately. First call after process start is a cold cohort; a new provider client is still created per current adapter call, so warm does not imply client reuse.

For each candidate: read observed-to-terminal UI-ready total; separate detection/stability, scheduling, native worker/transport, backend auth/DB/retrieval, SDK wall time and panel proxy. Keep nested/parallel spans on a timeline rather than summing them. Aggregate per-request auth/query/provider counters by candidate; distinguish native retries from extra grounded verification or supplementation. Compare publication gaps with capture and liveness intervals. Correlation gaps and missing UI acknowledgement must be reported, not filled with invented durations.

Also test Stop/Pause during vision and answer, rapid page changes, logout/session replacement, unchanged frames and source closure using the existing manual safety procedure. No obsolete answer should reappear. This phase did not execute any live procedure.

## 13. Recommended next steps

Approve the bounded baseline benchmark first. Use measured p50/p90/p95 and call counts to decide whether provider time, repeated security transactions, admission waiting or result collection dominates. The 3–5 second simple-MCQ goal remains a proposed target, not a result or guarantee. Any subsequent model/prompt/client/scheduling/auth change requires separate Phase 2B approval and accuracy/privacy regression review. Preserve visual editing facts, selected-document support and General/Context Guided/Materials Only policies.

## 14. Explicit approval checkpoint

Phase 2A ends after offline validation. No optimization has been implemented. Live OpenAI and Neon benchmarking, performance changes, legacy-code removal, migrations and publication remain unapproved. Review this instrumentation and approve a bounded live benchmark before proceeding.
