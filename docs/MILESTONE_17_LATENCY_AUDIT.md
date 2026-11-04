# Milestone 17 — Real-Time Response Performance

Current follow-up: Phase 2A instrumentation is implemented and validated in the
uncommitted working tree. See `MILESTONE_17_PHASE_2A.md` and the addendum below.
The Phase 1 audit that follows is preserved as the original inspection record;
its proposed bottlenecks have not yet been established by live timing benchmarks.

## 1. Executive summary

**Phase 1: diagnostic audit only.** Audited on 2026-11-03 at
`609cdd192a9cfc6e025e10c0e1082cd0df088f60` in `D:\solveguide-ai`.
The working tree was clean before this document. No optimization, instrumentation,
application/configuration change, dependency installation, live provider request,
database connection, migration, native launch or deployment was performed.

The reported ~20-second MCQ and ~35-second visual responses are **user observations,
not instrumented category benchmarks**. There is insufficient current run evidence
to assign those totals to OpenAI, Neon or any single component.

Three findings deserve priority:

1. **Confirmed application scheduling costs:** defaults require 3 seconds of observed
   stability with a nominal 1.5-second sampling sleep, and enforce 30 seconds between
   candidate starts. A new question can wait for cooldown even after becoming stable.
   Inline session heartbeats also precede capture and collection of completed work.
2. **Confirmed repeated remote security work:** a normal answered candidate has four
   logical native liveness checks plus authenticated Vision and Answer HTTP requests.
   General still needs database-backed identity and session checks; without overlapping
   coalescing this path enters 12 backend database transaction contexts, before heartbeats
   or other UI traffic. Cost is unmeasured; earlier latency reports make this material.
3. **Confirmed serial provider/delivery path:** Vision, Answer and final validation all
   complete before publication. Grounded paths can add more serial calls. There is no
   streaming, no persistent OpenAI SDK client pool, and no event-driven result publication.
   Existing timings cannot isolate provider computation from network/SDK time or measure
   question-visible-to-panel-paint latency.

**Recommended next step:** approve a narrowly scoped instrumentation/test phase first,
then evaluate targeted scheduling, transaction and client-lifecycle changes. Preserve
the successful Milestone 16 visual comparison corrections, authoritative sessions,
ownership, consent, abstention, duplicate suppression and stale-result safeguards.
Do not change models or relax validation based on these observations alone.

Evidence labels below: **confirmed** = inspected source or an explicitly described
local probe; **hypothesis** = plausible production impact not measured here;
**historical** = earlier user/repository reports, not a fresh measurement.
Links refer to source at this baseline; future edits can move line numbers.

## 2. Current end-to-end request architecture

```text
Explicit Start + owned source + active session + transmission consent
  -> startup liveness / target acquisition / protected non-activating panel
  -> loop: sleep -> native credential check -> periodic remote heartbeat
           -> source verification -> WGC frame -> local signature/stability
           -> clear/cancel obsolete generation -> collect finished worker
  -> if stable AND cooldown expired AND no worker:
       full-pixel fingerprint guard -> attempt limit -> register cancellable worker
  -> S1: remote session liveness
  -> encoder semaphore -> blocking PNG encode/base64
  -> S2: remote session liveness
  -> POST vision: backend auth transaction -> PNG validation -> Vision SDK -> observation
  -> neutral question classification/completeness/confidence + observation dedup
  -> S3: remote session liveness
  -> POST answer: backend auth -> authoritative configuration before
       -> General Answer OR selected-document RAG/Answer/verification
       -> authoritative configuration after -> validated JSON response
  -> S4: remote session liveness
  -> worker Outcome ready
  -> main native loop collects Outcome AFTER its next validation/capture
  -> guarded snapshot publication
  -> panel polls IPC -> runtime validation -> React render -> WebView paint
```

Primary sources: [native pipeline wrapper](../src-tauri/src/monitor/mod.rs#L846),
[sequential provider pipeline](../src-tauri/src/monitor/pipeline.rs#L16),
[sampling/result loop](../src-tauri/src/monitor/mod.rs#L929),
[Vision route](../backend/app/api.py#L33),
[Answer route](../backend/app/answer/api.py#L24),
[session-authoritative reasoning](../backend/app/learning/service.py#L296).

Question classification is part of Vision's structured observation, **not a third
classification API call**. The screenshot goes only to Vision; Answer receives the
structured observation and learning context, plus consented retrieved evidence where
applicable. The manual workflow remains separate and explicit.

An appropriate critical-path accounting model is:

```text
dispatch_time = next actual loop tick after max(stable_time, previous_start + cooldown,
                                              worker_available_time)
T_visible_to_final_paint = detection/eligibility wait + fingerprint
                        + S1 + encoder wait/encode + S2 + Vision HTTP
                        + S3 + Answer HTTP + S4 + collection wait + IPC/paint
```

The HTTP terms already include backend auth, relevant database work and provider
spans; do not add those nested durations again. Stability and cooldown overlap;
do not simply sum both full waits. Heartbeat and worker checks can overlap/coalesce,
so count actual requests by request ID, not just logical function invocations.

## 3. Stage-by-stage latency investigation

### 3.1 Detection, debounce and admission

| Stage | Confirmed behavior | Latency consequence / qualification |
| --- | --- | --- |
| Sampling | `interval_ms=1500`; allowed 1000–5000. Sleep happens before each iteration, not on a fixed wall-clock schedule. | Effective period includes capture, credential/heartbeat and loop work. It is not guaranteed 1.5-second capture frequency. |
| Stability | `stabilize_ms=3000`; allowed 2000–10000. Anchor/previous-frame differences reset stability. | Ideal zero-work steady-state visibility-to-eligibility is approximately 3–4.5 seconds; from a newly activated loop with a question already visible, first sample is nominally at 1.5 seconds and eligibility at 4.5 seconds. Real work increases/jitters this. |
| Meaningful change | Sparse 128×72 luminance signature; changed cells need intensity difference >20 and >0.4% of cells. | Cursor-scale changes are filtered; tiny/color-only edits can be missed, while persistent animation can delay stability. Missing a change is a reliability failure, not merely a slow answer. |
| Cooldown | Default/minimum 30 seconds between starts; configurable up to 120. No reset just because a new question appears. | Up to nearly 30 seconds of cooldown debt can apply to the next page. This is an intentional cost safeguard, but conflicts with rapid-question latency targets. |
| Full-frame guard | Two full-pixel hash passes on dispatch-eligible frames, synchronously in the async loop; only the last completed identity is retained. | Prevents some repeated calls without another image buffer. Cost scales with pixels and is uninstrumented. It does not fuzzy-match animated variants or cache authorization/answers. |
| Admission | One candidate worker and one encoder permit. Native AI slot rejects another pending AI operation. | No unbounded candidate queue; manual/other AI work may yield a busy error rather than wait in a queue. Encoder contention remains a possible wait after aborted blocking work. |
| Retry | SDK retries are off. Native pipeline errors can retry after 30 then 60 seconds; third consecutive failure stops; attempts capped at 60/run. | Retries can dominate time-to-useful-answer. A valid abstention is not a transport failure/retry. Stop/Resume starts a new activation; limits are not account-wide billing quotas. |

Sources: [defaults/bounds](../src-tauri/src/monitor/mod.rs#L33),
[signature and stability gate](../src-tauri/src/monitor/filter.rs#L39),
[full-frame identity](../src-tauri/src/monitor/filter.rs#L9),
[retry/backoff](../src-tauri/src/monitor/mod.rs#L909),
[admission/cooldown](../src-tauri/src/monitor/mod.rs#L1146),
[encoder semaphore](../src-tauri/src/monitor/mod.rs#L862).

**Executed source-equivalent schedule calculation**, not a native benchmark: with
zero capture/auth/provider work, fixed ticks every 1.5 seconds and stability 3 seconds:

| Question fully visible at | Previous candidate start | First eligible dispatch | Visibility-to-dispatch |
| --- | --- | --- | --- |
| 0.01 s | none | 4.5 s | 4.49 s |
| 7.6 s | none | 12 s | 4.4 s |
| 7.6 s | 0 s | 30 s | 22.4 s |
| 31.6 s | 30 s | 60 s | 28.4 s |

Thus a >20-second apparent delay can arise before a provider is called. This does
**not** establish that cooldown caused the user's observed 20-second MCQ response.

### 3.2 Capture and image preparation

Each live sample re-discovers sources, verifies the original process/target identity,
creates a D3D11 device/context, WGC frame pool/session and staging texture, waits for
one frame, maps GPU data and copies BGRA to RGBA on CPU. The retained MonitorTarget is
an identity reference, **not a retained running capture session**. These operations
run in a blocking worker, but the monitor loop awaits them. Frame-arrival wait is
bounded to 5 seconds with 50 ms cancellation checks; GPU mapping and all local work
do not thereby gain a complete 5-second end-to-end deadline.
[capture_frame](../src-tauri/src/capture/windows.rs#L271),
[device/frame pool](../src-tauri/src/capture/windows.rs#L316),
[frame wait](../src-tauri/src/capture/windows.rs#L371),
[GPU map/CPU copy](../src-tauri/src/capture/windows.rs#L421).

Only an admitted candidate is PNG/base64 encoded. Encoding is blocking-worker work
behind a semaphore, but native JSON serialization and the two hash passes also use
CPU/memory. PNG uses RGBA8 at captured resolution; no explicit crop, downscale,
JPEG conversion or quality reduction is present. `captured_at` is assigned **after
encoding**, and the monitor sends only media type/base64, so it is not a reliable
frame-acquisition clock for this pipeline.
[Frame::encode](../src-tauri/src/capture/mod.rs#L334).

Limits remain 40 MP, 10 MiB PNG and 14 MiB streamed Vision body; raw RGBA alone can
reach 160 MB at the pixel limit. GPU/staging buffers, encoded PNG, base64 (~4/3 PNG
bytes), JSON copies and backend decoder allocations add memory/CPU costs. Native
capture releases its session before encoding. High-resolution/image-rich fixtures
need measurement; there is no proof that capture currently contributes seconds.

Backend `validate_image` checks base64/PNG limits, verifies and loads the image,
then canonicalizes base64. It runs through `run_in_threadpool`; actual threadpool
queue delay is not separately measured. Do not remove decoder validation to save
the millisecond costs seen in simple local fixtures.
[image validation](../backend/app/images.py#L23), [route](../backend/app/api.py#L43).

### 3.3 Authentication and database work

`S1` precedes encoding; `S2` follows encoding and immediately precedes Vision;
`S3` precedes Answer; `S4` follows Answer before returning the worker result.
Each uses the compact owned `/learning/sessions/{id}/validate` projection. This is
already an improvement over full preparation/catalog loading: no document text,
titles, objectives or vectors are loaded. General's joins do not produce selected
document rows. Each logical check has a 12-second total bound, including native
credential mutex, coalescer wait, HTTP/auth/DB, decode and validation.
[active_for](../src-tauri/src/monitor/mod.rs#L310),
[overlap-only coalescer/deadline](../src-tauri/src/monitor/validation.rs#L9),
[owned projection](../backend/app/learning/repository.py#L17).

There is **no TTL authorization cache**. Sequential checks normally make separate
requests; only overlapping callers share a result. At each actual authenticated HTTP
request, `current_session` selects the hashed credential row **FOR UPDATE**, checks
expiry/revocation and updates `last_seen_at`; authentication also loads the user.
This is local backend/PostgreSQL session validation, not another Google OAuth call.
[authentication dependency](../backend/app/auth/dependencies.py#L25),
[current_session](../backend/app/auth/service.py#L93).

Normal General successful path, excluding startup, overlap sharing and heartbeats:

| Operation | HTTP requests | Database transaction contexts |
| --- | --- | --- |
| Four liveness checks | 4 | 8: auth transaction + compact session transaction per check |
| Vision | 1 | 1 auth transaction |
| Answer | 1 | 3: auth + configuration before + configuration after |
| **Total** | **6** | **12**, including 6 auth-row last-seen writes |

FastAPI's reused dependency is not a second auth execution merely because it appears
both on the route and user parameter. These counts are logical transaction contexts,
not exact wire round trips, connection creations or measured milliseconds. Each
transaction issues `SET LOCAL statement_timeout='10s'`; commit, SQL flush and warm
pool pre-ping can add work. The shared async engine already pools connections
(3 + 2 overflow, 5-second pool/connect limits); do not recommend a new pool as if
none existed. Auth/lifecycle transactions end before AI calls, so the inspected
code does **not** hold those row locks for the entire 20-second provider operation.
[Database](../backend/app/database.py#L40),
[configuration/recommend](../backend/app/learning/service.py#L261).

General avoids Context Library content/index readiness queries in authoritative
answer configuration, RAG retrieval and embeddings. It still reads session links
and identity/lifecycle metadata. Periodic main-window auth/preparation refreshes
(60 seconds when visible, plus focus/library changes) can perform additional work;
full preparation views may load selected metadata. They are not the 500 ms panel
poll and should be tagged separately in benchmarks.
[configuration](../backend/app/learning/service.py#L269),
[view/read](../backend/app/learning/service.py#L40),
[frontend refresh](../src/components/LearningWorkspace.tsx#L19),
[auth refresh](../src/auth/context.tsx#L11).

Grounded modes additionally repeat owned `selection`/generation validation around
retrieval/provider work. `selection` loads full ContextDocument ORM rows, including
extracted text, even where metadata checks suffice. Semantic retrieval checks
pgvector availability, embeds a bounded ephemeral query and performs exact scoped
cosine ranking using JSONB-to-vector casts, not an ANN index. Repeated selection,
large documents and ranking are plausible costs; no database plan or latency was
measured here. Preserve owner/index-generation checks before/after external work.
[selection/validate/rank](../backend/app/rag/repository.py#L156),
[retrieval](../backend/app/rag/retrieval.py#L69).

### 3.4 Response delivery and blocking boundaries

An inline heartbeat runs before every due sampling/collection cycle and sets its
next due time to completion + 5 seconds. While awaiting it, the sampling loop does
not inspect the source or harvest a completed provider worker. Pause/Stop remain
cancellable; this is a delivery/source-observation stall, not proof of a frozen UI.
[loop ordering](../src-tauri/src/monitor/mod.rs#L953).

Even without a heartbeat, a worker that finishes just after collection waits through
the next sleep, credential check and capture. With an otherwise idle loop this adds
up to roughly one effective loop period; a slow heartbeat/capture can add seconds.
After native publication, the panel polls every 500 ms (main view 700 ms), parses
the entire snapshot and sets React state even when content is unchanged. Actual
WebView paint, timer throttling and large-code/citation render costs are unmeasured;
there is no native per-answer event push or paint acknowledgement.
[collection](../src-tauri/src/monitor/mod.rs#L1060),
[publish guard](../src-tauri/src/monitor/mod.rs#L232),
[panel polling](../src/components/MonitorPanel.tsx#L9),
[main polling](../src/components/LiveMonitor.tsx#L18),
[controller](../src/monitor/controller.ts#L10),
[IPC parser](../src/monitor/client.ts#L4).

Snapshots perform a native credential/epoch check, **not remote DB validation** on
every poll. Panel show/protection/placement happens at start/reopen, not every answer.
The non-activating Windows behavior and affinity verification must remain unchanged.
[Snapshot](../src-tauri/src/monitor/mod.rs#L534),
[panel lifecycle](../src-tauri/src/monitor/panel.rs#L4).

Post-answer checks are security barriers, not cosmetic work to move after display:
server configuration and native S4 prevent publishing after end/replacement,
revocation or selected-material changes. Improve their implementation/coordination
only with equivalent enforcement and tests; do not display first and retract later.

## 4. Existing timing evidence and local probes

| Evidence | What is known | What is not established |
| --- | --- | --- |
| Current manual observations | MCQ ~20 s; some visuals ~35 s; variable speed. | Measurement endpoints, mode, cooldown debt, model overrides, cold/warm distribution and percentiles. |
| Historical user diagnostics | Preparation 4,301 ms; index requests ~3,865–4,071 ms; transactions ~1–2.5 s; earlier Answer requests ~19–21 s with abstention. | Those are not new measurements at this commit, not all the compact liveness route, and not model inference-only durations. Do not multiply index latency by every current check. |
| Repository history | [DIAGNOSTICS.md](./DIAGNOSTICS.md#L83) records old 3.9–4.3 s successful requests and the 5→12 s deadline change; [Milestone 15 audit](./MILESTONE_15_AUDIT.md#L119) identifies blocking heartbeat/preflights. | Neither document supplies fresh p50/p90/p95 for this baseline; Milestone 16 changed fingerprinting/visual paths, so old findings were re-inspected. |

Executed offline probes used project Python with `-B`, generated in-memory RGBA
diagram PNGs, no files/network/provider/database, one untimed warm-up and
`perf_counter_ns`. p90/p95 use nearest rank; small samples are exploratory.
These timings measure the synchronous `validate_image` worker body, **not native
capture/PNG encoding, threadpool queue time, ASGI auth or provider inference**.

| Probe | Samples | p50 ms | p90 ms | p95 ms |
| --- | --- | --- | --- | --- |
| PNG validation, 1280×720, 7,340-byte simple diagram | 30 | 1.923 | 2.690 | 3.517 |
| PNG validation, 3840×2160, 39,809-byte simple diagram | 12 | 18.823 | 22.775 | 24.783 |
| Small MCQ Pydantic observation validation | 1,000 | 0.005 | 0.005 | 0.005 |
| Small observation JSON serialization | 1,000 | 0.002 | 0.002 | 0.004 |
| Small AnswerRecommendation validation | 1,000 | 0.003 | 0.005 | 0.005 |

These low-entropy synthetic images are not photo-heavy screenshots, maximum-size
requests or complex visual observations. They argue against prioritizing removal
of small DTO validation, not that every local stage is necessarily cheap.

`node --test tests/monitor.test.mjs tests/visual.test.mjs`: **21 passed, 0 failed**,
~745 ms reported test duration. These exercise mocked controller/contract/rendering,
copy and stale-state behavior; they do not establish Windows focus, actual paint,
WGC latency, live perception or billing. No builds/full backend/Rust suites were
needed for this documentation-only audit, and previous suite totals are not fresh
audit evidence. Static schedule calculations are recorded in §3.1.

## 5. Existing diagnostics and missing instrumentation

| Existing event/span | Scope and useful correlation | Limitation |
| --- | --- | --- |
| `monitor_candidate_changed/started/finished` | Activation trace + native run/generation/candidate ID; timestamps and attempt reason. | Changed means first **observed** frame change, not when pixels first became visible. Started is after eligibility/hash, not first provider send. Finished is logged on loop collection, not worker completion. |
| `session_check_started/finished` | Native monotonic duration, 12-second deadline, candidate ID when called from worker. | Heartbeats have no candidate ID. Overlap coalescing gives no explicit shared leader request ID to the waiter. |
| `backend_http_started/backend_http` | Native request ID, activation trace, endpoint, status, duration and sanitized category. | Includes serialization/send/receive/decode/epoch checks; not provider compute-only timing. |
| Backend `http_request` | Same propagated request/trace/candidate IDs, route, status, total duration and outcome. | Broad ASGI span includes request/auth/service/response serialization, not actual WebView receipt. |
| `stage_started/finished` | Authentication, Vision service, Answer service/provider, retrieval, embeddings, grounded answer, session liveness. | Inclusive/nested spans. Vision has no separate SDK-only span. Repeated Answer provider spans lack an explicit draft/verify/supplement role/ordinal. |
| `database_transaction` | DEBUG duration under current request context; sanitized failure SQLSTATE/category. | Includes pool acquisition, pre-ping, SQL, locks, flush and commit; no operation label/query count or pool-vs-query breakdown. |
| Decisions/support verification | Counts and safe retrieval/abstention/grounding reasons. | No free-form content or upstream inference duration. `insufficient_information` with HTTP 200 is not an auth/network error. |

Sources: [native trace/HTTP diagnostics](../src-tauri/src/diagnostics.rs#L30),
[native HTTP timer](../src-tauri/src/diagnostics.rs#L199),
[backend allowlist/spans](../backend/app/diagnostics.py#L124),
[ASGI correlation/timing](../backend/app/diagnostics.py#L221),
[transaction timer](../backend/app/database.py#L105).

INFO shows lifecycle/candidate and provider-endpoint HTTP outcomes; successful
heartbeats, auth, transactions and stage details are DEBUG. Healthy native snapshot
polls do not create remote HTTP traffic. Backend context uses ContextVars with reset;
unrecognized correlation values/paths are sanitized. Do not enable SQL/SDK wire logs.

**Missing Phase 2 instrumentation, proposed only:**

- monotonic source-frame acquisition, signature/stability eligibility, cooldown debt,
  full hash, blocking-worker/semaphore queue time, PNG encode/base64 and byte counts;
- logical liveness-check role (pre-encode, pre-Vision, pre-Answer, post-Answer, heartbeat),
  and coalesced leader request ID; lifecycle configuration-before/after duration;
- database pool acquisition/pre-ping, transaction role, lock/query/commit aggregate
  timings and counts, without SQL parameters, SQL text or connection strings;
- SDK request start/end, first byte if exposed, local SDK parse time, call role,
  safe model identifier, actual numeric usage counts and optional upstream request ID;
- worker-complete **before** harvest, native publish, panel receipt, validated state
  commit and next-paint acknowledgement, joined by safe generation/trace identifiers;
- counters for suppressed frames/questions, failures, cancellations, retries and
  outcomes, without saving frame hashes, question identities or learning content.

There is currently no shared complete question lifecycle trace through paint. Use
monotonic clocks within each process; wall timestamps help correlate but should not
be treated as precision cross-process durations. Add validated operational IDs/fields
through existing allowlists only after approval. SDK round-trip minus local parsing
still includes network/provider queue time: it cannot be relabelled pure model
inference without reliable upstream timing evidence.

## 6. Confirmed bottlenecks versus hypotheses

| ID / priority | Finding | Confidence and impact |
| --- | --- | --- |
| L1 / high | 3-second stability gate, non-fixed 1.5-second loop sleep and 30-second start interval. | Confirmed lower/admission waits. Fast next-page goals conflict with cooldown irrespective of model speed; current incident attribution unproven. |
| L2 / high | Heartbeat and capture precede completed-worker harvest. | Confirmed scheduling bottleneck. Magnitude follows those stage costs; no live measurement supplied. |
| L3 / high | Four logical liveness calls and repeated auth/transactions; adjacent preflights bracket encoding. | Confirmed repeated work. Avoidable portion requires security design, not deletion of checks. Live DB/lock/pool share remains a hypothesis. |
| L4 / high | Vision → Answer serial dependency; mode-dependent embedding/verification/fallback calls; full responses awaited. | Confirmed critical path. Which call dominates ~20/~35 s is unknown without correlated stage traces. |
| L5 / medium | New SDK client for every Vision, Answer, embedding and verification call. | Confirmed lack of application-level provider connection reuse; handshake/network saving unmeasured. OS/DNS/TLS caches may still help. Native client and SQLAlchemy engine are already shared. |
| L6 / medium | Per-sample source enumeration/D3D/WGC resource setup; full pixel copy/hash; full-resolution PNG. | Confirmed work, unmeasured production bottleneck. Expensive on large sources or debug builds is a hypothesis to test. |
| L7 / medium | Repeated RAG selection reads full document content; exact JSONB-vector ranking. | Confirmed query/data shape; real account size/plan and cost unknown. General doesn't execute these retrieval calls. |
| L8 / medium | Structured visual output can repeat facts across descriptions, changes and comparison rows. Editing Answer text/explanation/key points can be generated then replaced by deterministic formatting. | Confirmed output work; actual tokens/time unknown. Preserve five-change fidelity and Materials Only verification before trimming. |
| L9 / lower | Panel polls every 500 ms, full snapshot reparsing/rerender; main polls every 700 ms. | Confirmed extra delivery delay/copy work, usually a fraction of a second under idle assumptions; actual WebView paint/throttling unmeasured. Not proof of 20-second rendering. |
| L10 / reliability | Shared backend AI slot; disconnect checked during upload, no explicit post-upload watcher in the boundary. | Confirmed code boundary. Aborted native requests may leave upstream/backend work occupying the slot, triggering busy/backoff. Current runtime propagation/billing consequences are unverified. |

L10 source: [request boundary](../backend/app/middleware.py#L72). The slot rejects
concurrent paid routes; it does not create a long server queue. Do not "fix" latency
by removing it or allowing overlapping obsolete provider jobs.

No single deadline covers visibility-to-final-paint. Timeouts are failure ceilings,
not intentional sleeps: increasing 45/60/105-second limits cannot make a successful
request faster. Conversely, shortening them without measurements can cause more
abstention/failure/retries and greater perceived latency.

## 7. Provider configuration and input/output analysis

### Configuration observed without secrets

| Role | Setting/default | Request settings |
| --- | --- | --- |
| Vision | `OPENAI_VISION_MODEL=gpt-4.1-mini` | `responses.parse`, high-detail PNG, QuestionObservation schema, `VISION_MAX_OUTPUT_TOKENS=4096`, `VISION_TIMEOUT_SECONDS=45` (allowed 1–90). |
| Answer, including grounded draft/check/supplement | `OPENAI_ANSWER_MODEL=gpt-5.4` | `responses.parse`, schema per call, `ANSWER_REASONING_EFFORT=medium`, `ANSWER_MAX_OUTPUT_TOKENS=6000`, `ANSWER_TIMEOUT_SECONDS=60` (allowed 1–90). |
| Semantic query embedding | `OPENAI_EMBEDDING_MODEL=text-embedding-3-small` | `embeddings.create`, dimensions 512, timeout 25 seconds (allowed 1–45), bounded batches/input. |
| Retrieval | `RAG_TOP_K=6`, `RAG_CONTEXT_TOKENS=6000`, semantic threshold 0.3 | Selected owned documents only. The budget implementation conservatively counts serialized evidence UTF-8 bytes + allowance, not a measured tokenizer count. |

All use the explicit official API base, backend-only key, `max_retries=0` and a
5-second connection timeout. Vision/Answer use `store=False`; that is not a claim
about provider retention guarantees. No streaming flag/stream consumer is used.
No temperature or alternate per-category routing is configured in these adapters.

Sources: [Settings/defaults](../backend/app/config.py#L15),
[safe example configuration](../backend/.env.example#L1),
[Vision SDK call](../backend/app/providers/openai.py#L87),
[Answer SDK call](../backend/app/answer/openai.py#L97),
[embedding SDK](../backend/app/rag/embedding.py#L40),
[evidence budget](../backend/app/rag/retrieval.py#L22).

A read-only **strict whitelist** inspection of the local `.env` found explicit
Vision model/timeout/output-cap entries matching the table. Other listed settings
were absent and therefore use repository defaults absent process overrides. No
allowlisted override was present in the audit process environment. **The running
backend's separate PowerShell environment and loaded Settings were not inspected**;
do not present this as a live runtime configuration dump. Settings load on backend
startup; document the safe effective values during an approved benchmark. No key,
OAuth value or database URL was printed or copied into this audit.

### Calls, clients and budgets

| Successful/relevant path | Serial external calls after candidate admission |
| --- | --- |
| General | Vision + Answer = 2 |
| Context Guided, lexical relevant support | Vision + grounded draft = 2 |
| Context Guided, semantic relevant support | Vision + query embedding + grounded draft = 3 |
| Context Guided, draft lacks usable support | Above path + general supplemental Answer: up to 3 lexical / 4 semantic |
| Materials Only, proposed supported answer | Vision + grounded draft + independent verification: 3 lexical / 4 semantic |

No-question/duplicate observations or deterministic abstention can stop earlier.
Empty retrieval can avoid a draft, and failed support verification can abstain.
General never invokes retrieval/embedding. These counts are calls, **not bills or
guaranteed successful answers**, and native retries can repeat a pipeline.
[RAG branching](../backend/app/rag/service.py#L250),
[fallback](../backend/app/rag/service.py#L199),
[independent support check](../backend/app/answer/openai.py#L51).

Grounded retrieval, supplementation and verification share an outer answer deadline;
do not budget two independent full 60-second Answer windows in a grounded request.
Auth/configuration work outside that outer provider budget, native HTTP (105 seconds
per AI route), local preparation and four liveness bounds still add latency. A
timeout is not a new-question response-time guarantee.

Provider adapters instantiate/close AsyncOpenAI inside each call, preventing an
explicit shared HTTP pool across those calls. Native AuthState owns one persistent
reqwest client with fixed loopback destination/no proxy/no redirects. It serializes
the payload once for a size check and again through `.json()`, then awaits whole
JSON responses; backend and client perform further semantic validation. Those local
copies are bounded but uninstrumented, and are lower-priority than multi-second waits.
[native client](../src-tauri/src/auth.rs#L31),
[native request validation](../src-tauri/src/auth.rs#L496),
[AI HTTP path](../src-tauri/src/auth.rs#L566).

### Prompt and schema sizes

Static in-memory sizes at this commit:

| Item | Characters / UTF-8 bytes |
| --- | --- |
| Vision instructions | 5,532 / 5,532 |
| General Answer instructions | 4,697 / 4,697 |
| Grounded instructions | 6,159 / 6,159 |
| Materials Only verification instructions | 1,136 / 1,136 |
| Pydantic observation JSON schema, compact serialized | 4,610 bytes |
| Pydantic answer JSON schema, compact serialized | 1,689 bytes |

These are **not token counts, exact SDK strict wire-schema sizes, provider cache-hit
measurements or complete request sizes**. User task text, image processing, actual
output and retrieved context vary. Observation can contain 20 images, 40 comparison
rows and substantial descriptions; code/visual tasks legitimately need more output
than a small MCQ. Structured parsing/schema checks remain necessary. Lowering an
output ceiling is not guaranteed to lower actual output and can truncate required
facts/code, cause invalid responses and incur retries.

For matrix-based editing tasks, Answer generation currently emits fields that
`compose_editing_response` can replace with factual deterministic text. A future
compact decision/support schema could avoid discarded prose, but must still assess
uncertainty and verify the **formatted final prompt** in Materials Only, as now.
[formatting](../backend/app/answer/visual.py#L59),
[pre-verification integration](../backend/app/answer/openai.py#L51).

## 8. Security, accuracy and target feasibility

Non-negotiable invariants for any later optimization:

- Explicit authorized source and monitoring consent; no source switching, automatic
  activation, wider capture permission, hidden monitoring or increased paid-call rate
  without an explicit cost-policy decision.
- Native-held credential/epoch, current server auth, active owned session/revision,
  selected-document ownership/readiness/generation and consent checks. No frontend
  cached state or old successful heartbeat becomes proof of authorization.
- Clear/ignore obsolete generations on source/question change, Pause/Stop, logout,
  expiry and end/replacement; no obsolete answer restored to make latency appear lower.
- General remains retrieval-free; Context Guided supplements honestly; Materials Only
  requires validated support/abstention. Keep label/count/code requirements, real
  citations, comparison direction, title spacing/bar-height facts and unchanged colors.
- Never disable window capture protection for benchmarking; keep non-focus-stealing
  display and keyboard controls. No learning-content persistence or raw diagnostic logs.

Do not parallelize dependent Vision and Answer speculatively. Only consider parallel
independent work after authorization and with final revision/ownership checks intact.
Do not publish partial unvalidated JSON, tentative option labels, hidden reasoning,
or unchecked citations to claim a faster answer. Streaming may improve feedback but
does not automatically improve validated completion time.

Proposed engineering targets, **not achieved results or guarantees**:

| Category | Target visible-to-useful-answer | Feasibility under current defaults |
| --- | --- | --- |
| Simple MCQ / True-False | 3–5 s | Very tight: the stability/sampling floor already consumes ~3–4.5 s in the ideal warm steady state, leaving little for security + two serial SDK calls + display. |
| Short theory | 3–7 s | Aggressive; needs low warm DB/provider latency and concise complete output. |
| Basic visual patterns | 4–8 s | Needs accurate extraction with bounded descriptions and low provider/DB time; no measurement proves it yet. |
| Complex image comparisons | 5–12 s | Plausible only after measurement; must retain subtle geometry, color/presence distinctions and uncertainty rather than trim accuracy-critical facts. |
| Coding/math | 5–15 s | Variable output/reasoning complexity; preserve complete code, indentation, math steps and reliable abstention. Larger tasks may require an explicitly different class/budget. |

All targets need separate reporting for modes and cold/warm requests. Rapid new-page
targets cannot hold while a previous start still creates substantial 30-second
cooldown debt. Adopt the upper bound as an initial **proposed warm p90 goal for approval**;
record p50/p90/p95, sample counts and confidence limitations. Establish p95 and cold-start
budgets from the baseline rather than inventing a universal model guarantee.

## 9. Prioritized optimization recommendations — not implemented

Every benefit below is an **unmeasured estimate/opportunity**, except observed local
probe values. Implement one change at a time and compare against the same baseline.

| Priority / bottleneck & evidence | Proposed correction | Estimated benefit | Risks / required regressions |
| --- | --- | --- | --- |
| P0: incomplete critical-path clocks (§5) | Add safe per-stage roles/timestamps, worker-complete/publish/paint and pool/SDK breakdown. | No direct speed promise; prevents optimizing the wrong stage and yields attributable tail latency. | Allowlist/privacy, correlation isolation, overlapping checks, no content/credential logging; known-delay tests must reconstruct the correct non-double-counted path. |
| P1: worker collection behind sleep/heartbeat/capture (L2) | Separate prompt result collection/publication from sampling and bounded heartbeat scheduling, keeping source-change invalidation and fresh final security barriers. | Recover up to one effective sample period and any avoidable capture/heartbeat collection stall; seconds possible under slow checks. Exact gain unknown. | Race tests: new page during heartbeat, complete worker during capture, concurrent Stop/logout/end/revision; no stale publication, no focus change or unbounded loops. |
| P1: redundant preflights/transactions (L3) | Review adjacent pre-encode/pre-Vision validations and coordinate server-aware security boundaries; use compact projections/shared request context where valid. Retain before-provider authorization and after-work invalidation. | Up to one removed check's measured critical-path time for the narrow duplicate; larger consolidation needs design proof. Historical seconds are not a projected guaranteed saving. | No TTL auth cache, no expired/revoked access, race/revision/material-generation tests, zero unauthorized provider calls; count actual HTTP/DB operations. |
| P1: per-request auth row lock/write + setup (L3) | Measure pool/lock/query/commit separately. Consider bounded conditional last-seen updates and reducing metadata round trips while still performing fresh credential validation. | Remove unnecessary writes/lock contention/setup round trips if they dominate; actual gain unknown. | Preserve fixed expiration/revocation semantics, concurrent logout/login/session starts and transaction cleanup; do not assume pool size is too small or disable pre-ping blindly. |
| P1 decision: 30-second rate gate (L1) | Explicitly agree a cost-aware policy for genuinely changed stable questions, preserving one pending pipeline, dedup, cooldown/backoff and bounded spend. | Can remove up to nearly 30 s of cooldown debt for a later page, **not** speed the first provider response. | Higher paid rate/animation noise and bill risk; regression count repeated/static/rapid pages, failures, Resume, cancellations. No silent cap removal. |
| P2: per-call provider client lifecycle (L5) | Own long-lived SDK clients via FastAPI lifespan with bounded pool/timeouts and orderly close. Preserve endpoint, keys, retries and no-persistence settings. | Avoid some repeated client/connection setup; measure warm handshake/round-trip change. No quantified saving yet. | Cross-request/account isolation, cancel/error cleanup, credential reload only via intended startup, no proxy/endpoint drift or new retries. |
| P2: redundant prompt/output and fixed model effort (L4/L8) | Measure actual usage/call role, remove duplicated prose, evaluate concise task-aware output/effort/model routing behind the existing provider contract. Compact editing-decision output is a specific candidate. | Reduce genuinely unnecessary input/output or reasoning work; gain depends on model/answer, not just cap values. | Approved offline/live accuracy suite: MCQ labels/counts, code/math, diagrams, all five slide edits, no fabricated bar color/citations; fallback overhead measured. No model changes without approval. |
| P2: repeated full RAG metadata/content loads (L7) | Separate owned metadata/generation projections from content-bearing reads; consolidate redundant selection checks without losing before/after validation. Profile exact vector ranking before considering storage/index changes. | Fewer transactions/bytes/materialization where large documents dominate; no measured production saving. | Cross-user IDs, reindex/delete during retrieval/answer, consent, selected-only scope, no General retrieval, semantic/lexical parity. No migration implied/authorized. |
| P2: capture/image preparation (L6) | Benchmark first; consider safe per-run native resource reuse and cancellation-friendly hashing/encoding. Evaluate explicit content-safe sizing only against legibility/visual fixtures. | Less setup/copy cost if substantial; simple backend validation probes suggest little benefit from weakening that validation. | WGC closure/resize/DPI/memory cleanup, capture indicator/affinity, tiny text/spacing/bar height/color/code quality; never silently crop out content or sample unrelated windows. |
| P2 reliability: cancellation/admission tail (L10) | Test and then implement request-scoped backend cancellation/disconnect cleanup where safe. Retain bounded shared admission. | Reduce busy errors and 30/60-second retry penalties for abandoned work if this path occurs. | Independent request/account cancellation, no slot leaks, upstream billing caveat, errors/timeouts/Stop; don't cancel another user's request. |
| P3: polling/streaming (L9) | Prefer generation-tagged native result events or change-aware snapshot delivery; evaluate streaming only with a safe validated-output strategy. | Event delivery may recover up to the nominal 0.5 s poll window and reduce reparsing. Streaming primarily improves first feedback; final-answer gain unproven. | Event loss/reopen/resync, keyboard/focus, compact/expanded panels, no partial invalid answer/citation leakage, late-generation rejection, reduced motion. |

No recommendation assumes a new provider, separate engine, database migration,
weaker image/schema validation, disabled evidence verification or cached authorization.

## 10. Proposed implementation phases and approval gates

1. **Phase 2A — instrumentation/offline harness only:** approve the minimal missing
   clocks/roles and reproducible synthetic source transitions; use existing logging,
   in-memory fakes and no external services. Report known-delay attribution accuracy.
2. **Phase 2B — controlled baseline pilot, separate approval:** safe effective config,
   cold/warm, modes and resolution cohorts; run the explicitly authorized request budget
   below. This audit does not grant approval to contact OpenAI or Neon.
3. **Phase 2C — scheduling/validation/client reuse:** prioritize measured critical-path
   delays, implement narrowly and independently, re-run security/cancellation regressions.
   Discuss the cost/rate-policy decision explicitly; do not silently change 30 seconds.
4. **Phase 2D — accuracy-gated provider/image/RAG work:** only if earlier stages leave
   a material bottleneck. Evaluate model/effort/prompt/size changes with correctness and
   visual fidelity controls, then consider event/stream presentation.

Keep a before/after table with p50/p90/p95, warm/cold, category/mode, input size,
provider call counts, cancellation/failure/abstention/accuracy rates and build profile.
No grouped rollout that hides which change improved or degraded performance.

## 11. Manual benchmarking procedure — proposal awaiting approval

**Do not run the following paid/database-connected experiment as part of Phase 1.**

1. Approve Phase 2 instrumentation, then separately approve service access, harmless
   fixtures and a finite request budget. An initial General-only pilot of two cases per
   category is 10 successful candidates / normally 20 SDK calls, before errors/retries.
   Stop on unexpected retries/failures and review counts; already-sent calls may still
   finish/be charged. Expand only with approval; 20–30+ warm cases per category/mode
   gives more useful tails, but even that has sample-size limits. Report small-n pilots
   without claiming a meaningful production p95.
2. Record baseline commit, Windows/hardware, dev/release build, source kind/resolution,
   DPI, mode, reference count/index method and safe model/timeout/effort/output settings.
   Separate `.env` from actual process overrides; never print full Settings/environment,
   keys, DB URLs or headers. Do not change models/configuration for the baseline.
3. After approval, start current backend and desktop in separate canonical PowerShell
   terminals; DEBUG is diagnostic-only. These commands were **not executed in this audit**:

   ```powershell
   Set-Location D:\solveguide-ai
   $env:SOLVEGUIDE_LOG_LEVEL='DEBUG'
   npm.cmd run backend
   ```

   ```powershell
   Set-Location D:\solveguide-ai
   $env:SOLVEGUIDE_LOG_LEVEL='DEBUG'
   npm.cmd run desktop
   ```

4. The user signs in and explicitly authorizes a disposable learning source/session.
   Keep screen-share privacy ON. Use anonymous synthetic MCQ/True-False, short theory,
   visual pattern, five-change comparison and code/math fixtures. No personal document
   transmission without separate consent. Do not disable protection to obtain assets.
5. Define clocks: `t_visible` = fully rendered target question in the authorized source;
   `t_observed` = first native observed change; `t_eligible`, `t_dispatch`, each provider
   start/end, final security checks, `t_worker_done`, `t_publish` and `t_paint`. Measure
   E2E as `t_paint - t_visible`, not candidate-start-to-HTTP-finish. Use an approved
   synthetic source marker/monotonic instrumentation; stopwatch readings alone are
   coarse. With current logs alone label results **partial traces**, not complete E2E.
6. Separate startup (sign-in/target/panel creation), first connection/schema/cache effects
   and warm steady-state. Run isolated questions after cooldown expiry, then a separate
   realistic rapid-navigation cohort including cooldown debt. Do not reset/Resume each
   page and call that steady-state performance. Do not forcibly suspend or reconfigure
   Neon to manufacture cold starts. A full desktop restart requires manual sign-in.
7. Under separately approved grounded testing, use ready selected disposable materials
   with explicit transmission consent. Separate General, Guided lexical/semantic relevant,
   Guided no-support/supplement, and Materials Only supported/abstention/verification.
   Record actual external call count, not just native processing-attempt number.
8. Exercise slow but valid session response, timeout, source closure, rapidly changed
   pages, Stop/Pause, logout and session replacement with **local fakes** first. Verify
   no stale publication or unauthorized work. Live failures are separate from success
   percentiles; include error/abstention rates and time-to-useful-answer rather than
   discarding slow/cancelled failures to improve the average.
9. Export only safe stage/count/category/config metadata into a reviewed local audit
   location, with no frames, text, answers, passages, image fingerprints or credentials.
   Join unique request IDs within activation/candidate traces; annotate coalesced checks
   and nested spans. Optional provider usage records require operator access/approval;
   HTTP and SDK elapsed time are not pure provider inference or billing evidence.
10. Review p50/p90/p95 and cold/warm distributions, outliers, accuracy and cost before
    approving any optimization. Establish an E2E residual for currently unmeasured
    waits; do not claim a single dominant component until traces actually support it.

## 12. Acceptance criteria for Milestone 17

**Phase 1 completion:** only this audit document is added; cited architecture and
configuration are verified against the baseline; observations and probe limits are
explicit; no runtime/application changes or external service calls. This criterion
does not mean response-time targets have been met.

Proposed acceptance criteria for an approved implementation:

- Every accepted benchmark candidate has a reconstructable stage trace through final
  paint or an explicit terminal outcome, with no sensitive content. Known-delay offline
  tests recover injected intervals within a stated harness tolerance (proposed ≤50 ms
  for 1-second fake stage delays), without nested-span double counting.
- Publish per-category/per-mode cold/warm n, p50/p90/p95, correctness/abstention/error
  and call-count tables. Initial warm p90 goals use §8 upper bounds; disclose cooldown
  and startup cohorts separately. Ratify cold/p95 budgets after the baseline pilot.
- In local fake tests, once provider work **and required final security checks** have
  completed for the current generation, proposed native publication ≤100 ms and visible
  panel update ≤500 ms under an idle foreground test environment; measure rather than
  assume these in Windows. No slow capture/heartbeat may unnecessarily gate that path.
- Zero obsolete answers in at least 1,000 scripted generation/Stop/logout/revision
  interleavings; no provider execution before required auth/ownership/consent; General
  makes zero retrieval/embedding calls; unsupported Materials Only cases abstain.
- Retain MCQ labels/counts, code/math structure, visual direction and all five controlled
  slide changes without fabricated bar recolors; citation membership/support stays valid.
  Any model/prompt/size/effort change must pass the approved accuracy benchmark and
  human review, not just return schema-valid JSON faster.
- Preserve bounded concurrency/retries and static-frame duplicate suppression. Record
  candidate and SDK call counts; no unexplained extra requests or silent higher spending
  rate. Long-run memory/resource use must plateau within an agreed hardware baseline.
- Native focus/keyboard, both themes/compact panels, affinity/capture indicator, manual
  capture fallback and no-persistence guarantees remain intact. Run full backend/frontend/
  Rust regression suites for implementation work; no database/schema change is implied.

**Mandatory stop:** Phase 1 ends here. No optimization or instrumentation is implemented.
Await explicit approval before Phase 2 and before live OpenAI/Neon benchmarking.

## Phase 2A instrumentation addendum (no optimization)

The Phase 1 conclusions above remain a historical audit, not measured live results.
Phase 2A adds DEBUG-only native candidate/worker/panel timing, backend SDK and
independent validation spans, SQL execution/setup timing and per-request counters.
See `MILESTONE_17_PHASE_2A.md` for the event reference, legacy intelligence audit,
clock/overlap limitations, offline validation and approval-gated benchmarking plan.
The Phase 1 stopping statement records that phase's state; instrumentation is now
implemented in the uncommitted Phase 2A work. No prompts, models, scheduling,
rate limits, authorization behavior or database architecture were optimized.
No live OpenAI/Neon benchmark was performed. Physical first appearance, pure pool
wait, internal model inference and actual compositor paint remain unmeasured.
