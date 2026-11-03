# Milestone 15, Phase A — Live Monitor intelligence and reliability audit

Date: 2026-10-30. Canonical repository: `D:\solveguide-ai`.
Audited HEAD: `8ed1d555ba4b9fce3d70ff1f2086b0e0140e6091` (`8ed1d55`). Initial working tree: clean.

## 1. Scope and evidence

This is an audit, not an implementation. Only this document was created. Application code, environment variables, credentials, dependencies, schemas, migrations, website, brand and privacy settings were not changed. No Neon connection, Google login, live provider request or native capture was performed.

Evidence includes actual source inspection, existing frontend monitor tests, deterministic source-derived calculations, and an in-memory probe of the real ASGI request boundary with a fake handler. Python used `-B`, avoiding bytecode writes; no application bootstrap or configured provider was initialized. The ASGI probe used a process-local selector event loop and no HTTP server. The user's previous manual verification is context, not a new hardware test.

References identify functions and line numbers at the audited commit. Repository-relative links use GitHub-style line anchors. Full builds/backend/Rust suites were not rerun for this documentation-only phase; previous milestone results are not fresh audit evidence. No actual p50/p95 latency, GPU/memory, upstream billing or focus measurements are claimed.

**Priorities:** P1 = high-impact identity/progress/stale-content issue; P2 = material latency/recovery/usability improvement; P3 = measurement or defense in depth. **Confirmed** means source-established behavior or a stated executed probe, not necessarily an observed production incident. **Risk** means impact/frequency still needs verification. No P0 exploit or demonstrated cross-account exposure was established; this is not a penetration test.

## 2. Current architecture and lifecycle

```text
Authenticated preparation + explicit source + transmission notice
 -> typed Tauri Start; token/epoch/session/revision/readiness validation
 -> identity-bound Windows target + privacy-protected non-activating panel
 -> wait / credential check / periodic server check / bounded frame capture
 -> local signature / changed generation / stability / cooldown / attempt cap
 -> session check / PNG encoding / session check / authenticated Vision
 -> validated observation / confidence and type gate / semantic deduplication
 -> session check / session-authoritative AnswerService or RAG / session check
 -> current run/generation publication / main and panel snapshot rendering
```

### Activation and capture

1. `LiveMonitor` requires a selected source, explicit automatic-transmission consent and a ready preparation. Its effect only refreshes snapshots; neither polling nor recovery starts monitoring. [LiveMonitor.tsx:9–21](../src/components/LiveMonitor.tsx#L9), [controller.ts:1](../src/monitor/controller.ts#L1).
2. `monitor_control(Start)` is main-window-only, resolves an enumerated token/type, captures the native auth epoch and validates bounded configuration. `begin_inner` rejects racing startup using an intent revision, validates the server session and retains a native `GraphicsCaptureItem` identity/Closed flag. [monitor/mod.rs:409–475](../src-tauri/src/monitor/mod.rs#L409), [595–640](../src-tauri/src/monitor/mod.rs#L595), [capture/windows.rs:209–252](../src-tauri/src/capture/windows.rs#L209).
3. Every sample rediscovers the selected source, rejects unavailable/replaced identities and monitor-layout changes, validates dimensions, creates D3D11/device/frame-pool/session/staging resources, obtains one frame and copies CPU RGBA. RAII closes the capture session/pool. The retained target is an identity reference, not a running recorder. Own-process, invisible, minimized, tool and cloaked windows are filtered. [windows.rs:79–162](../src-tauri/src/capture/windows.rs#L79), [175](../src-tauri/src/capture/windows.rs#L175), [271–443](../src-tauri/src/capture/windows.rs#L271).
4. Live sampling does not use the manual capture path's `HiddenWindow` guard, so sampling does not restore/focus the main window. Source closure/unavailability stops or enters recoverable error; it never switches targets silently. Restoring a minimized, still-live source permits explicit Resume; a closed identity requires a new selection. [capture/mod.rs:326–413](../src-tauri/src/capture/mod.rs#L326), [monitor/mod.rs:978–1020](../src-tauri/src/monitor/mod.rs#L978).

### Detection, providers and publication

5. A 128×72 point-luminance signature feeds `Gate`, which tracks anchor/previous frames, stabilization and submission state. A detected change increments generation, aborts obsolete work and clears visible content. [filter.rs:10–80](../src-tauri/src/monitor/filter.rs#L10), [monitor/mod.rs:1024–1048](../src-tauri/src/monitor/mod.rs#L1024).
6. A stable candidate outside cooldown and below the attempt cap gets one worker. Its abort handle is registered under the same state lock used by Stop before a oneshot permits provider work. Attempts count failed/no-question/duplicate candidates, not only successfully answered unique questions. [monitor/mod.rs:1131–1184](../src-tauri/src/monitor/mod.rs#L1131).
7. The outer `pipeline()` remotely validates before encoding. Inner `execute()` validates before Vision, before Answer and after Answer: **four logical checks per successful candidate**, plus heartbeats. Only overlapping checks coalesce; sequential successes are not cached. [monitor/mod.rs:841–872](../src-tauri/src/monitor/mod.rs#L841), [pipeline.rs:16–58](../src-tauri/src/monitor/pipeline.rs#L16), [validation.rs:9–41](../src-tauri/src/monitor/validation.rs#L9).
8. Vision receives a bounded PNG through required authentication. Its structured observation is independently validated. Native processing requires detected, nonempty, known-type content and extraction confidence ≥0.65. Confidence is a model estimate, not calibrated certainty. [api.py:40](../backend/app/api.py#L40), [service.py:15](../backend/app/service.py#L15), [providers/openai.py:19–90](../backend/app/providers/openai.py#L19), [pipeline.rs:24–40](../src-tauri/src/monitor/pipeline.rs#L24).
9. Deduplication includes prompt, type, options, instructions, required selection count, context and visual elements, excluding reading confidence. Only the last observation with an answer result is retained as a fingerprint, not persistent history. [monitor/mod.rs:730–763](../src-tauri/src/monitor/mod.rs#L730).
10. Answer input is observation plus session ID/revision. Backend configuration resolves mode, purpose/objective, selected owned documents and consent; it rechecks configuration after providers. General bypasses retrieval. Context Guided may use labelled general reasoning without citations. Materials Only retains evidence coverage, verification and abstention. Selected index generations/citation membership are checked. [answer/api.py:24](../backend/app/answer/api.py#L24), [learning/service.py:261–315](../backend/app/learning/service.py#L261), [rag/service.py:199–357](../backend/app/rag/service.py#L199), [rag/repository.py:156–191](../backend/app/rag/repository.py#L156).
11. The loop checks the latest sampled frame before harvesting a completed worker; run/generation/cancellation must match before publication. The main/panel poll and validate the same answer contracts. [monitor/mod.rs:226–253](../src-tauri/src/monitor/mod.rs#L226), [1024–1078](../src-tauri/src/monitor/mod.rs#L1024), [src/monitor/types.ts:12](../src/monitor/types.ts#L12).
12. Pause/Stop increment identity, clear live snapshots, notify validation waiters, flag capture cancellation and abort workers. Logout, session transitions, main Close and application Exit also stop native monitoring. Resume is explicit and begins a new activation; panel dismissal alone does not stop monitoring. [monitor/mod.rs:188–225](../src-tauri/src/monitor/mod.rs#L188), [auth.rs:432–469](../src-tauri/src/auth.rs#L432), [learning.rs:141](../src-tauri/src/learning.rs#L141), [lib.rs:34–45](../src-tauri/src/lib.rs#L34), [lib.rs:78–90](../src-tauri/src/lib.rs#L78).

### Existing default limits

These are code defaults, not values read from private `.env`.

| Control | Default/bound | Source |
| --- | --- | --- |
| Sampling | 1,500 ms wait **plus** capture/check work; configurable 1,000–5,000 ms | `monitor/mod.rs:33–53` |
| Stabilization | 3,000 ms; configurable 2,000–10,000 ms | `monitor/mod.rs:33–53` |
| Candidate rate/cap | 30-second minimum start separation, configurable 30–120 s; at most 60 attempts/run | `monitor/mod.rs:43–53, 1131–1153` |
| Error backoff | 30 s then 60 s; third consecutive failure enters recoverable error | `monitor/mod.rs:904, 1083–1117` |
| Session validation | 12-second total bound, overlap-only coalescing; heartbeat five seconds after completion | `validation.rs:9–41`; `mod.rs:942–975` |
| Frame wait | Five seconds; cancel checks every 50 ms during the wait | `capture/windows.rs:372–390` |
| Images | 40 MP raw; 10 MiB PNG; 14 MiB inbound vision JSON | `capture/mod.rs:178, 334–364`; `config.py:8–10` |
| Native AI transport | One request slot; 105-second per-HTTP deadline | `auth.rs:567–649` |
| Backend admission | One shared vision/answer HTTP slot **per app process**, busy→503 | `middleware.py:13–18, 72–79` |
| Providers | Vision 45 s; answer 60 s; embedding 25 s; SDK retries zero | `config.py:21–35`; provider implementations |
| Rendering | Main polls 700 ms; panel polls 500 ms, with non-overlapping refresh | `LiveMonitor.tsx:16`; `MonitorPanel.tsx:9`; `monitor/controller.ts` |

Candidate limits are not hosted SDK-call limits. General normally makes Vision + Answer. Context Guided may additionally embed the query and/or supplement a grounded attempt. Materials Only may additionally embed and verify support. Current paths can initiate up to four hosted calls per candidate, excluding separately requested document indexing. Retries/cancellations can still incur costs. No billing/quota system exists or is proposed here.

## 3. Existing safeguards to preserve

- **Authorization:** opaque credentials stay in native memory; auth epoch prevents cross-login reuse; backend required-user validation checks expiry/revocation. [auth/dependencies.py:26–61](../backend/app/auth/dependencies.py#L26), [auth/service.py:84–103](../backend/app/auth/service.py#L84). Compact liveness is owner/revision/state/readiness/consent scoped and avoids full preparation loading: [learning/repository.py:17–79](../backend/app/learning/repository.py#L17), [learning/service.py:86](../backend/app/learning/service.py#L86).
- **Bounds:** atomic capture-busy guard, one WGC pool buffer and channel entry, one encoder permit, one native AI slot and process-wide backend AI admission. No unbounded frame queue. [capture/mod.rs:71–92](../src-tauri/src/capture/mod.rs#L71), [windows.rs:337–360](../src-tauri/src/capture/windows.rs#L337), [monitor/mod.rs:853–866](../src-tauri/src/monitor/mod.rs#L853), [auth.rs:581–595](../src-tauri/src/auth.rs#L581).
- **Answer integrity:** strict observation/recommendation contracts, label/count/type checks, separate reading/answer confidence, real selected citations, bounded top-K/context budget, index-generation validation and Materials Only verification. [schemas.py:23–68](../backend/app/schemas.py#L23), [answer/service.py:38–96](../backend/app/answer/service.py#L38), [rag/retrieval.py:22–135](../backend/app/rag/retrieval.py#L22). No image is resent to AnswerProvider.
- **Privacy:** main and panel use owned HWNDs, supported `WDA_EXCLUDEFROMCAPTURE` and readback; panel applies current preference before show. This is supported capture privacy, not guaranteed invisibility. [privacy/windows.rs:39–98](../src-tauri/src/privacy/windows.rs#L39), [privacy.rs:374–383](../src-tauri/src/privacy.rs#L374), [monitor/panel.rs:51–81](../src-tauri/src/monitor/panel.rs#L51). No monitor history model/writer was found; live images/questions/answers remain in request/current-state memory. Library/preparation persistence is separate. Responses use no-store.
- **Focus:** automatic show uses `.focused(false)` and `SW_SHOWNOACTIVATE`; explicit Focus Panel alone calls `set_focus`. Automatic results do not restore/maximize the main window. DPI/work-area layout exists. [monitor/panel.rs:4–81](../src-tauri/src/monitor/panel.rs#L4), [127–202](../src-tauri/src/monitor/panel.rs#L127). Hardware permutations were not retested here.
- **Diagnostics:** allowlisted trace/request/candidate IDs, safe codes/counts/durations, ContextVar isolation, quiet successful heartbeats at INFO, sanitized failures. No image/question/answer/passage/token logging added. [diagnostics.py:35–52](../backend/app/diagnostics.py#L35), [124–175](../backend/app/diagnostics.py#L124), [221](../backend/app/diagnostics.py#L221), [native diagnostics](../src-tauri/src/diagnostics.rs).

## 4. Confirmed findings with reproducible evidence

### D1 — P1: small or color-sensitive changes can be invisible to detection

**Evidence:** `Signature::of` [filter.rs:10–29](../src-tauri/src/monitor/filter.rs#L10) samples one pixel per grid position, not an area average. `differs` [31–44](../src-tauri/src/monitor/filter.rs#L31) requires a luminance change greater than 20 at **at least 37 of 9,216 sampled points**. There is no alternative local tile/text-sensitive comparison.

**Executed source-derived calculation:** at 1920×1080, sample coordinates are multiples of 15. Changing the 196 pixels at `x=1..14, y=1..14` from white to black changes **zero** sampled points. RGB `(100,0,0)` and `(0,30,0)` both reduce to integer luminance 21, so a purely color-coded change can also collide. These calculations reproduce Rust arithmetic; they are not Windows capture tests.

**Impact/likelihood:** high impact, medium-to-high likelihood for small negation/option/numeric changes on large/scaled displays; actual frequency needs fixtures. A question transition can be missed and an old answer remain visible. Vision cannot correct a change that never reaches it.

**Minimal fix:** evaluate a bounded tile-sensitive/multi-scale score for localized text and relevant color changes. Increasing resolution alone while retaining only a global percentage threshold is insufficient. Preserve cursor/caret tolerance.

**Regression:** one changed NOT/option/digit, Python indentation, equal-luminance chart/legend changes, cursor-only motion, and 100/150/200% scaling. Require all curated critical transitions to be detected; quantify noise separately.

### D2 — P1: mixed-format code can be falsely deduplicated

**Evidence:** `fingerprint` [monitor/mod.rs:730–763](../src-tauri/src/monitor/mod.rs#L730) recursively collapses whitespace unless the top-level type is exactly `code`. Code inside `visual_elements` of a `mixed` observation is therefore collapsed. Dedup occurs after Vision at [pipeline.rs:43–51](../src-tauri/src/monitor/pipeline.rs#L43).

**Executed ASCII normalization/AST probe:** these programs have different Python syntax trees but identical whitespace-collapsed strings:

```python
# A: returns 2 even when flag is false
def result(flag):
    if flag:
        value = 1
    return 2

# B: returns None when flag is false
def result(flag):
    if flag:
        value = 1
        return 2
```

With other fields equal and `question_type="mixed"`, the fingerprint cannot distinguish them. Whitespace inside string literals is another semantic collision. Code-only normalization is better but still trims edges; code-field preservation should not depend solely on top-level classification.

**Impact/likelihood:** high impact, medium likelihood for mixed coding/theory questions: a genuinely new program can skip answer generation.

**Minimal fix:** conservative field-aware prose normalization; preserve program/literal whitespace in code-bearing fields across formats. Preserve instructions/options/count in identity as now. Prefer a safe extra analysis over a false semantic match; no historical cache is needed.

**Regression:** Python nesting, string-literal spaces, mixed code elements, significant initial indentation, identical code and intentional prose-reflow policy. Existing option/count-change tests must remain green.

### D3 — P1: heartbeat latency blocks observation of source changes

**Evidence:** `run_loop` awaits `active()` inline at [monitor/mod.rs:963–975](../src-tauri/src/monitor/mod.rs#L963), before source-closure inspection, capture, detection and worker-result handling at 978–1078. The bound is 12 seconds. Sampling is not independent of session I/O even though provider work is on a separate task.

**Deterministic timeline:** A's answer is visible; a heartbeat begins; the user switches to B; the heartbeat takes four valid seconds. This loop cannot sample B or invalidate A during that wait. A hung check can consume the 12-second bound before stopping. Generation guards only act after a change is observed. This is confirmed sequencing, not a new live latency measurement.

**Impact/likelihood:** high impact, medium likelihood with material authenticated/DB latency: delayed clearing, missed transitions and delayed completed-answer delivery. Stop/Pause cancellation remains responsive during the await; this is not a claim that those controls block.

**Minimal fix:** separate the bounded periodic validation future from sampling; retain fail-closed handling and fresh authenticated validation at provider boundaries. Continue generation invalidation while the check is pending. Do not extend deadlines or turn cached success into authorization.

**Regression:** inject a ten-second valid heartbeat while A→B and source closure occur. Detection/clearing must not wait. Independently test expiry, revision failure and immediate Stop cancellation.

### D4 — P2: consecutive remote preflights add unnecessary candidate latency

**Evidence:** outer `pipeline()` checks the session before PNG encoding [monitor/mod.rs:855](../src-tauri/src/monitor/mod.rs#L855); `execute()` checks again immediately before Vision [pipeline.rs:22](../src-tauri/src/monitor/pipeline.rs#L22), then twice around Answer. The overlap-only coalescer [validation.rs:13–28](../src-tauri/src/monitor/validation.rs#L13) does not reuse sequential successes.

**Reproducer:** trace `session -> encode -> session -> vision -> session -> answer -> session`. Existing inner-pipeline tests count only its three checks. At actual check cost S, four non-coalesced validations contribute approximately `4*S`; the short encoding-adjacent duplicate adds approximately S. This is a budget calculation, not a current measurement that S is four seconds.

**Impact/likelihood:** medium impact, high likelihood on normal candidates; substantial under remote DB latency. The current compact liveness projection is already an improvement and must not revert to full preparation loading.

**Minimal fix:** keep cheap native run/epoch checks before encoding and fresh server checks before Vision, before Answer and before publication; remove only the redundant remote pre-encoding lookup or prove an equivalent narrow optimization. Do not drop post-answer revision/material checks.

**Regression:** test the outer pipeline with a counting fake, ensuring no provider precedes retained authorization. Measure encode-adjacent overhead without adding a TTL auth cache.

### D5 — P1: backend cancellation is not propagated after upload

**Evidence:** native cancellation/abort drops the HTTP operation and releases `AiGuard` [auth.rs:519–534](../src-tauri/src/auth.rs#L519), [643](../src-tauri/src/auth.rs#L643). `VisionRequestBoundary` recognizes `http.disconnect` only while receiving the initial body [middleware.py:79–110](../backend/app/middleware.py#L79); afterward it awaits the handler without a disconnect watcher. Vision/answer/provider paths add no watcher. A shared backend AI slot does protect that process against parallel vision/answer handlers.

**Executed real-boundary/fake-handler probe:** after complete JSON upload, a disconnect was available from `receive`. Results:

```json
{"disconnect_polled_after_body":false,"task_still_pending":true,"second_request_status":503,"fake_completion_count":1}
```

The fake handler completed after release despite the queued disconnect. This proves the boundary's behavior, not real OpenAI billing or every Uvicorn disconnect behavior.

**Impact/likelihood:** high impact, medium likelihood when navigating/Stopping during slow providers. Superseded work can occupy admission until completion/timeout; the next candidate can receive busy/backoff. Native cancellation alone does not prove upstream work/charging stopped. The process-wide slot prevents unbounded parallel handlers; do not remove it as a workaround.

**Minimal fix:** request-scoped post-upload disconnect cancellation, sanitized diagnostics and finally-based admission release. Affect only the exact request, not another account's work; preserve provider timeouts. Already accepted external charges may remain irreversible even with prompt coroutine cancellation.

**Regression:** actual ASGI messages and fake Vision/Answer/verification/supplement providers: observe cancellation, release admission, prevent later provider stages, admit the next request and reject mismatched cross-request/account cancellation. No paid calls.

### D6 — P2: duplicate recognition can remove the still-relevant answer

**Evidence:** detected visual change clears observation/answer [monitor/mod.rs:1025–1048](../src-tauri/src/monitor/mod.rs#L1025). Fresh Vision returning the same question yields `answer=None` [pipeline.rs:43–51](../src-tauri/src/monitor/pipeline.rs#L43); publication writes that None [monitor/mod.rs:1064–1076](../src-tauri/src/monitor/mod.rs#L1064). `gate.sent()` prevents another attempt on the unchanged anchor.

**Reproducer:** answer A; change a large unrelated sidebar/toolbar; stabilize; fake Vision returns exact A. No second answer call occurs (good), but A's answer is absent and does not return while that frame stays unchanged. Another change, Resume or manual fallback is needed. This is a state-transition proof, not a new Windows UI reproduction.

**Impact/likelihood:** medium impact, medium-to-high likelihood with surrounding UI changes or same-question scrolling. Cost-saving dedup unexpectedly removes useful output.

**Minimal fix:** consider one bounded ephemeral last-answer slot keyed by semantic identity plus account/session/revision/mode/material generations. Clear visible output on an unconfirmed change; redisplay only after fresh matching observation and session validation. Erase it on Stop/logout/context change. This is not persistent history. Alternatively provide deliberate recovery rather than silent answer loss.

**Regression:** matching nuisance change restores only its confirmed result without another answer call; changed code/option/count/context never reuses it; Stop/logout erase it; no file/record is written.

### D7 — P2, conditional error path: unexpected loop exit leaves active state

**Evidence:** `Termination::drop` only logs [monitor/mod.rs:907–923](../src-tauri/src/monitor/mod.rs#L907). It does not cancel/clear state or abort the registered worker. `begin_inner` spawns the loop without supervising its handle [697–700](../src-tauri/src/monitor/mod.rs#L697). Explicit abort elsewhere demonstrates that dropping a local handle is not the intended cleanup mechanism.

**Reproducer:** fault-inject a loop panic after a worker registers. Unwind bypasses the trailing worker-abort block; the guard logs while snapshot/cancel state remain active. An orphan worker can still satisfy `current()` until another action resets state. This is a confirmed conditional cleanup omission; no normal user action causing a panic was demonstrated.

**Impact/likelihood:** high impact if reached, low/unknown likelihood. A false active indicator undermines user control. Ordinary source/provider errors already use handled stop paths and are not this failure.

**Minimal fix:** idempotent run-scoped supervisor/finalizer that cancels, clears, aborts and sets recoverable error only for the failed run. Avoid panicking or manipulating windows while holding the state lock.

**Regression:** panic/early return with/without worker; no later provider stage; inactive/error snapshot; old cleanup cannot stop a newer activation; user Stop is not logged as an unexpected failure.

## 5. Potential risks and how to verify them

| ID / priority | Source mechanism and current protection | Verification and narrowly scoped response |
| --- | --- | --- |
| R1 / P1 | **Incomplete/off-screen content:** only the visible selected surface is captured. Vision is instructed to mark truncation/ambiguity unclear, but the native gate has no typed completeness field and ignores warnings. High-confidence partial detected content can pass; option-count checks cannot prove every choice or coding requirement was visible. `pipeline.rs:24–40`; `providers/openai.py:19–39`; `schemas.py:37–67`. | Disposable long code/theory/diagram fixtures at 25/50/75% visibility, obscured options and multiple visible questions. Known incomplete content must not be confidently auto-answered. Prefer typed completeness/conservative review over language-specific warning-string matching. Do not promise off-screen understanding or add OCR/autoscroll here. |
| R2 / P2 | **Animation/scroll starvation and nuisance costs:** whole-source motion resets stability and can abort work; a pause mid-scroll can analyze a fragment. Same-question dedup happens after paid Vision. `filter.rs:60–80`; `monitor/mod.rs:1025–1050`; `pipeline.rs:23–51`. | Replay scrolling, caret/cursor, skeletons, video/sidebar motion and real transitions. Count eligible/canceled/Vision candidates. Distinguish conservative stability waiting from missed settled questions; do not ignore animation that is itself question evidence. |
| R3 / P2 | **CPU/GPU/memory:** each sample enumerates sources and creates capture/staging resources. A 40 MP RGBA buffer is 160 MB, not a process-memory bound. GPU textures, staging, concurrent current frames, PNG/base64/JSON copies and WebViews add overhead. `windows.rs:277–443`; `capture/mod.rs:334–364`. | Measure 1080p/4K/max-size capture and encode timings, CPU, working set, GPU memory and handles. Aborting an async task does not instantly preempt blocking PNG/GPU work; measure drain after Stop. Reuse a device only if profiling justifies a narrow lifecycle-bound change, not a recorder rewrite. |
| R4 / P2 | **Rate-limit scope:** Resume starts a new run; cooldown, attempts, failures and last fingerprint reset. The 30-second separation and 60-attempt cap are not cross-activation/account quotas. `monitor/mod.rs:454–475, 574–577, 934–942`; consent text `LiveMonitor.tsx:20`. | Fake-provider rapid Pause/Resume and Stop/Start within one minute. Decide whether promises apply per activation or across resumptions, then align copy/tests. Count hosted calls separately from candidates, including Context Guided supplementation. Do not introduce billing/DB quotas. |
| R5 / P2 | **Long-question retrieval recall:** query construction includes prompt/options/visual elements/context, omits the separate `instructions` array, and truncates at 6,000 UTF-8 bytes. Tail code or instruction-only constraints can be omitted even though the answer provider receives the full observation. `rag/retrieval.py:111–119`. | Corpus where the only matching condition occurs in instructions or beyond that byte boundary. Measure passage recall and false Materials Only abstentions. If confirmed, include instructions and use a bounded field-aware query budget. Never broaden selected ownership or relax final constraints. |
| R6 / P2 | **DPI/placement/focus:** supported non-activating show/work-area layout exists. Selection coordinates used for placement are captured initially; updated per-sample source geometry does not refresh Selection. Reopening after moving the source may use its old display. `panel.rs:95–125`; `windows.rs:302–305`; `monitor/mod.rs:110–116`. | Move the source between displays, change scaling, disconnect a display, dismiss/reopen/expand, close/minimize during capture. Foreground HWND must remain the monitored app except deliberate focus. Prior manual success does not establish every hardware permutation. |
| R7 / P2 | **Total latency:** bounded stages exist, but a candidate can wait through several validations, encoding/admission, Vision, Answer and result harvesting. The 105-second native deadline resets per HTTP request. Grounded retrieval/supplementation share an answer deadline; auth/config DB work is outside provider timeouts. `auth.rs:614`; `pipeline.rs:22–55`; `rag/service.py:250–263`; `learning/service.py:296–315`. | Inject stage delays and establish an end-to-end budget from measured stages. Preserve authorization/evidence checks. Never hide failures by blindly increasing timeouts. |
| R8 / P3 | **Response-size hardening:** AI transport calls `response.json()` without the streamed byte cap used by owned session/document requests. Backend schemas/output-token caps constrain normal responses, but a broken/local replacement backend could allocate more before validation. `auth.rs:625–628` versus `auth.rs:174–194`. | Fake oversized/chunked responses. Add a bounded decoder if warranted; this audit did not demonstrate an exploit or treat localhost compromise as normal model behavior. |
| R9 / P3 | **Measurement gaps:** HTTP/service spans exist; capture, encode, eligibility and panel receipt lack dedicated durations. `captured_at` is assigned after encoding rather than exactly at frame acquisition. `capture/mod.rs:357–363`; `monitor/mod.rs:998–1024, 1152–1178`. | Add only safe ephemeral monotonic stage timestamps under existing correlation IDs. Separate slot-busy/cancellation-tail time from provider latency. Never record payloads, titles, captured content or credentials. |

The local gate detects image change/stability, not questions semantically. Cloud Vision performs actual question recognition; a stable non-question source can therefore incur a Vision request. A selected monitor includes other visible applications within that explicitly authorized surface. Existing transmission consent must remain accurate about this boundary.

## 6. Prioritized improvement plan and proposed test coverage

| Order | Minimal implementation slice | Required regression evidence |
| --- | --- | --- |
| 1 | D1/D2: fix existing signature/fingerprint helpers, starting with semantic-change fixtures. | Critical small-token/color/indent transitions versus cursor/caret noise; MCQ, multiple-select, mixed/code and diagram fixtures. No competing recognition engine. |
| 2 | D3/D4: independent bounded periodic validation and removal of the duplicate remote pre-encoding check. | Slow valid checks, 12-second timeout, expiry/revocation, revision/material changes, startup cancellation, rapid A→B→C, outer-pipeline check counts and fresh authorization before providers. |
| 3 | D5: request-scoped disconnect cancellation and backend admission cleanup. | Actual ASGI messages with fake providers for Vision, Answer, verification and supplementation; subsequent requests admitted; no cross-request/account cancellation or post-cancel provider stage. Keep the single-slot guard and zero SDK retries. |
| 4 | D7: abnormal-exit supervision/finalization scoped to the failed run. | Fault injection, worker/resource cleanup, honest state and stale-run protection. |
| 5 | D6: explicit same-question recovery policy, at most one ephemeral last result if approved. | Fresh identity/context validation before redisplay, no extra answer request, no reuse on changed code/options/count/account/session/material generations, no persistence. |
| 6 | Profile R3/R4/R5/R6/R7/R9; implement only fixture/measurement-supported changes. | Retrieval recall, Resume cap semantics, source movement/DPI, stage timing, resource plateaus and cost accounting. |

All slices must preserve required user authorization, session revision, selected ownership, transmission consent, reasoning modes, real citations and Materials Only abstention. Faster execution that skips those checks is not an acceptable fix.

### Existing coverage and its limits

- `tests/monitor.test.mjs`: explicit startup, polling backpressure, Stop over pending startup, Pause/Resume/source changes, logout disposal, safe snapshot/citation contracts, native IPC, panel dismissal and Context Guided general attribution.
- `monitor/filter.rs:85–126`: coarse noise/stability/retry cases; no real-image small-text/color fixtures.
- `monitor/pipeline.rs:60–146`: inner sequencing and unclear/duplicate outcomes; not the outer redundant preflight or restoration of an existing answer.
- `monitor/mod.rs:1238–1341` and `validation.rs:44–148`: native lifecycle/stale-run guards, abort, startup interruption, slow-valid checks, timeout, coalescing and cancellation release.
- `backend/tests/test_learning.py`, `test_diagnostics.py`, `test_rag.py`: authority/ownership/revisions, redaction/correlation, format support and three-mode policy. Retain them.

New coverage should use deterministic event-driven fakes and frame/observation fixtures, not paid automated calls, live Google/Neon, long sleeps or assertions that merely mirror function text.

## 7. Measurable latency and reliability benchmarks

These are **proposed Phase B targets**, not results achieved by this audit. Record baselines first; calibrate hardware-dependent resource budgets explicitly.

### Measurement boundaries

Record safe monotonic timestamps for frame acquisition, change detection, stability eligibility, authorization, encoding, Vision send/receive, Answer send/receive, native publication and panel receipt. Keep activation/candidate/request correlation. Count actual hosted calls separately from candidate attempts. Never retain learning content or provider bodies in benchmark logs.

```text
candidate latency ≈ sampling/stability + cooldown debt + session checks
                 + encode/admission + vision HTTP + answer HTTP
                 + completion harvesting + panel polling
```

Provider HTTP durations include backend/auth work: do not double-count nested spans. The four native session checks are outside those provider HTTP calls, and may coalesce with a heartbeat. Blocking OS/GPU work and encoder admission lack a complete candidate deadline, so this is decomposition, not a guaranteed upper bound.

| Measure | Proposed acceptance gate |
| --- | --- |
| Semantic recall | 100% on curated must-detect negation/digit/option/Python nesting/relevant-color fixtures; report held-out replay recall separately. |
| Noise | After initial analysis, zero extra candidates over ten deterministic minutes of stationary content plus cursor/caret motion; measure larger animation/scroll cases separately. |
| Invalidation | At default 1.5 s sampling and mocked capture ≤150 ms, p95 old-answer clearing ≤2 s after source change, even with a concurrent ten-second heartbeat. Zero obsolete publications across ≥10,000 seeded interleavings. |
| Stability | With the same fast mocks and no cooldown debt, eligibility p95 ≤6 s after settling. Eligibility is separate from dispatch, which must await valid server authorization. |
| Authorization | Fresh server checks remain at actual provider boundaries. Expiry/revocation/revision and the 12-second timeout fail closed. Measure liveness p50/p95/p99; investigate p95 >2 s or p99 >5 s before changing limits. These are operating targets, not current Neon claims. |
| Cancellation | Native publish eligibility invalidated immediately; mocked control ack p95 ≤100 ms and panel clearing ≤1 s. Fake backend provider cancellation/admission release within 500 ms of disconnect. No new stage after cancellation ack. Accepted external charges are not promised reversible. |
| Dedup | No second answer call for exact identity. Chosen recovery behavior explicit; changed code/options/count/context cannot reuse. |
| Cost | Assert cap/cooldown/retry and actual SDK-call counts by mode; explicitly test chosen Resume semantics. No unlimited candidate queue or claim of account-wide quotas. |
| Resources | Controlled 1080p/4K 30-minute soak and 100 Pause/Resume cycles with fake providers: bounded active captures/encoders/requests and plateauing CPU/GPU/handle/memory use. Investigate warm-state growth >1 MiB/min or failure to return within 10% of measured quiescent memory after Stop; calibrate against WebView/driver variance. |
| Complex content | Preserve exact selectable labels/counts and code formatting on complete fixtures. Known incomplete/off-screen content is not confidently auto-answered. Citations use selected current chunks only; general-only attribution has no citations; Materials Only abstains without support. |
| Privacy/access | No automatic start/recovery, requests after logout/end, cross-account reuse/cancel, learning-content files/DB rows/log text. Preserve affinity/preference on both windows. |
| Native UX | Approved hardware tests at 100/150/200% scaling and mixed-DPI/source movement/closure: no automatic foreground change; explicit focus, dismiss/reopen, compact/expand and honest privacy state work. Never disable capture exclusion for screenshots. |

Run deterministic/offline performance tests first. Only after separate user approval, conduct a small controlled live-provider sample and report capture-to-answer p50/p95 by mode, separating SolveGuide overhead from dependencies. This audit authorizes no paid benchmark, remote DB test or configuration change.

## 8. Recommended Phase B scope

Approve small, independently tested corrections for the first five slices in section 6, starting with D1/D2 identity safety, plus safe timing needed to measure them. Cap scope, completeness handling, capture-device reuse, retrieval query changes and hardware placement should be explicit follow-up decisions backed by fixtures, not silently added features.

Keep the Windows capture engine, FastAPI modular monolith, existing providers, native credential boundary, session/RAG contracts and floating-panel architecture. Core fixes require no OCR, automatic scrolling/off-screen assembly, recorder, new DB table/migration, persistent question/answer cache, billing/quota product, website/brand redesign or evasion behavior.

Phase B should run full relevant frontend/backend/Rust suites, lint/type/build/Clippy, targeted regression/soak checks and approved native tests. Mocked focus/privacy adapters and source review are not Windows integration proof.

## 9. Audit execution record and reproduction

- Read-only status/diff confirmed clean baseline `8ed1d55`. No fetch/push.
- `node --test tests/monitor.test.mjs`: **12 passed, 0 failed**, approximately 0.62 s. Controller/contract/render evidence, not native capture/focus proof.
- Source-derived probes: sparse rectangle produced `changed_pixels=196`, `changed_sample_cells=0`; equivalent luminance was 21; mixed-code normalized strings matched while ASTs differed.
- Actual `VisionRequestBoundary` with an in-memory fake handler: disconnect after upload was not consumed; task remained pending; next request got 503; fake handler then completed. No production provider/app was initialized.
- No full pytest/build/Rust rebuild, live-provider/Neon or native hardware tests were performed in this documentation-only phase. Prior milestone totals were not substituted for current results.

### Compact independent D1/D2 reproduction

Use the existing interpreter with `-B` through stdin (no new test file or environment setting):

```python
import ast
samples = {(x*1920//128, y*1080//72) for y in range(72) for x in range(128)}
changed = {(x, y) for y in range(1, 15) for x in range(1, 15)}
assert len(changed) == 196 and not (changed & samples)
assert 100*54//256 == 30*183//256 == 21
a = 'def result(flag):\n    if flag:\n        value = 1\n    return 2'
b = 'def result(flag):\n    if flag:\n        value = 1\n        return 2'
assert ' '.join(a.split()) == ' '.join(b.split())
assert ast.dump(ast.parse(a)) != ast.dump(ast.parse(b))
```

This demonstrates source arithmetic/ASCII normalization, not an actual Rust/Windows frame test. Phase B must add actual Rust fixtures. For D5, wrap the real boundary with a fake handler that reads the replayed body and awaits an event; offer `http.disconnect` after that body, then issue a second request before releasing the event. Valid local-origin and `application/json` headers are essential; otherwise the boundary correctly rejects the fixture before handler entry. The present boundary holds admission and does not poll the post-upload disconnect.

**Stop condition:** Phase A ends with this document. Wait for user approval before any Phase B application change.
