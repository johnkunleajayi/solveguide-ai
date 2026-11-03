# Milestone 16 — Visual Reasoning Intelligence

## Scope and architecture

Baseline: `8ed1d55`. This is an additive extension of the existing capture → vision
observation → session-authoritative answer/RAG → floating panel pipeline. It does
not rebuild the monitor, introduce a provider, alter the website, or apply a migration.
Milestone 15 reliability work remains deferred; the audit is preserved separately.

The authorized single PNG still goes only to the existing VisionProvider. Its
structured QuestionObservation now supports `question_type=visual_reasoning` and
a nullable `visual_task`. Existing text, code, mathematics, mixed and choice types
continue to work; mixed tasks may also include this visual metadata. Old observations
without the new field remain valid. No manual task-mode switch is needed.

The observer records neutral facts, never a correct selection or a hidden solution.
The existing AnswerProvider reasons from that observation; it does **not** receive
a second screenshot. This preserves the two-stage boundary and request count, but
means details missed by vision cannot be recovered by the answer model.

## Observation contract

`backend/app/schemas.py` adds VisualImage and VisualTask:

- Kinds: `editing_prompt`, `odd_one_out`, `sequence`, `spot_difference`, `mixed_visual`.
- Up to 20 task images, including sequence stimuli and options. Each has a unique
  identifier (printed label or explicit spatial name), relative position, role and
  bounded description (4,000 characters). Count must equal described image count.
- Roles: original, edited, option, sequence, comparison or unknown. Labels/positions
  never imply correctness. Choice-image identifiers must match actual option labels;
  odd-one-out needs at least two choices. A sequence may have no selectable choices.
- `complete` indicates legibility/completeness. `direction` is established,
  ambiguous or not applicable. An established edit requires exactly one original
  and one edited image. Visible labels/instructions establish direction; left/right
  order alone does not. Missing labels do not authorize guessing direction.
- Up to 30 neutral observed changes, each at most 1,200 characters. These preserve
  legible text, colors, sizes, shapes, positioning, typography and unchanged elements.
  They are observations, not document evidence or a recommended answer.

Instructions require an unclear observation for missing/ambiguous details, preserve
image count/labels/task instructions, and reject treating compression artifacts as
definite edits. An image-only question may use a neutral task description only when
the task is visibly established. Offscreen images and unreadable text are not invented.

`backend/app/answer/visual.py` rejects incomplete tasks, missing visual descriptions,
missing comparison images and ambiguous edit direction before answer-provider work.
The native pipeline also suppresses automatic answering of incomplete/ambiguous edit
observations. The frontend runtime guard validates the same field bounds and label
relationships and continues rejecting extra answer/credential fields.

## Reasoning and presentation

The AnswerRecommendation schema is reused:

- Editing tasks put the entire copyable transformation prompt in `answer_text`;
  explanations remain separate. Instructions require all supported changes and
  preservation of unchanged content, without inferred/unverifiable edits.
- Odd-one-out/pattern answers select real option labels and provide concise public
  explanations. Odd-one-out is deterministically limited to one selection; pattern
  tasks preserve any explicit selection count. Unsupported rules/details abstain.
- Spot-the-difference and mixed tasks use the existing answer/explanation/key-points
  fields. No hidden chain-of-thought, executable output or third-party interaction.

The shared answer view (manual and floating) shows Suggested Editing Prompt,
Suggested Selection or Visual Explanation, plus existing confidence, citations and
warnings. The panel exposes visual uncertainty even when no answer is requested.
Copy Response writes **only the generated prompt**, only on a user click, with
accessible success/failure status and a selectable-text fallback. It uses the WebView
Clipboard API, with no new capture/filesystem permission. Deliberately copying moves
text to the OS clipboard; clipboard history/sync, if enabled by the user, is outside
SolveGuide's ephemeral in-app storage. Copy is never automatic.

Existing compact/expanded layout, focus behavior, Pause/Resume/Stop, window privacy,
themes, keyboard focus and reduced-motion styles are reused, not redesigned.

## Reasoning modes and authorization

- General bypasses retrieval and uses the observed visual facts plus general reasoning.
- Context Guided retrieves only selected owned documents. The bounded ephemeral
  retrieval query now includes image descriptions and observed changes. Unsupported
  document grounding can use the established clearly labelled, uncited general
  fallback; irrelevant documents are never presented as supporting evidence.
- Materials Only keeps selected-document support and independent support verification.
  Visible image facts describe the task; they are **not** citations. Substantive
  conclusions/transformations still require material support. Missing evidence abstains,
  even when a general visual answer would appear possible. No general-mode fallback.

Required authentication, ownership, index readiness, transmission consent, session
revision checks and before/after-provider validation remain unchanged. Purpose does
not restrict formats. No frontend state overrides server-authoritative configuration.

## Identity, cancellation, limits and privacy

Native candidate fingerprints include the complete new visual metadata and preserve
its whitespace so label/text/layout changes are not normalized away. Existing
run/generation/auth-epoch cancellation, single pending request slot, bounded worker
and post-provider session checks still control publication. Stop, Pause, logout,
source changes and session replacement clear the same ephemeral state.

No new endpoint, table, upload, history, log payload, provider retry or automatic
third-party click/type/submit operation was added. No screenshot/question/answer is
persisted. No test sends images to a live provider. Native credentials remain outside
React. Screen-share privacy and Windows capture indicators remain enabled.

Existing limits are unchanged: 40 MP / 10 MiB PNG, 14 MiB vision request body,
bounded provider structured output, configured provider deadlines, one candidate
worker, default 1.5-second sampling / 3-second stability / 30-second request-start
interval, maximum 60 candidates per activation. These are activation safeguards,
not account-wide billing quotas. New descriptions also remain subject to existing
answer-request byte limits; unusually dense tasks can be rejected rather than grow
unbounded. Restarting/resuming monitoring has the existing activation-cap semantics.

## Validation and limitations

Tests use generated in-memory two-slide PNG data, synthetic visual observations,
local SDK HTTP transport doubles, deterministic providers and existing controller
fixtures. They validate contracts, transport, orchestration, direction/label integrity,
abstention, three modes, real citation membership, clipboard success/failure and stale
result rejection. They do **not** establish real model perception or visual accuracy.

Known limitations requiring manual review:

1. The unchanged Milestone 15 detector is sparse/luminance-based; a subtle isolated
   text/color/position change can fail to create a new candidate. A complete page
   transition is more reliable. This milestone preserves that deferred reliability work.
2. Vision descriptions are lossy. Tiny fonts, similar colors, dense diagrams, subtle
   artifacts, more than 20 task images or clipped content may be incomplete or wrong.
   The model's completeness/confidence is an estimate, not a guarantee. No OCR,
   offscreen stitching or extra image requests are introduced.
3. Prompt completeness, visual-rule correctness and citation entailment require human
   review; schema and support checks are not mathematical proof. A provider may omit
   a change despite correct prompt instructions.
4. Actual Windows clipboard permission, non-focus-stealing behavior, external capture
   exclusion, mixed-DPI layout and provider accuracy require native manual testing.
   Protection must never be disabled to obtain test screenshots.
5. No live AI, Google login, Neon connection or migration was used during validation.

## Manual review procedure

From two PowerShell terminals:

```powershell
Set-Location D:\solveguide-ai
npm.cmd run backend
```

```powershell
Set-Location D:\solveguide-ai
npm.cmd run desktop
```

1. Sign in yourself. Confirm Screen-share privacy stays ON; prepare a General session.
2. In an authorized practice window, display two clearly labelled slides. Put Original
   on the **right** and Edited on the left. Change text, title color, one object's
   position, and one added/removed element. Keep both slides legible and fully visible.
3. Select that window and explicitly activate Live Monitor, accepting the existing
   cost/transmission notice. Verify the transformation direction, every actual edit,
   preservation of unchanged elements, and copyable prompt. Click Copy Response and
   paste into a disposable local editor yourself; copied content must match the prompt.
4. Show five labelled images with one distinct rule, then a rotation/count sequence.
   Verify the selected label/position and explanation match the visible task.
5. Show a spot-the-difference task, ambiguous original/edited labels, cropped choices
   and low-resolution details. Verify uncertainty/abstention instead of invented edits.
6. Transition visual → MCQ → Python code → visual. Verify new content replaces old
   answers. Pause/Stop mid-request, switch source, end/replace the session and sign out;
   no late answer may reappear. Reopen/expand/dismiss the panel as before.
7. Repeat with Context Guided: test relevant and irrelevant selected documents, real
   citations and clearly labelled general fallback. In Materials Only, test both
   supported and unsupported visual conclusions; unsupported conclusions must abstain.
8. Verify compact/expanded panel, main window at 640×560, both themes, keyboard focus,
   clipboard failure fallback if denied, and continued typing in the monitored app.
9. Verify no history is created, no automatic webpage input occurs, and the existing
   manual Capture → Read Question → Get Suggested Answer workflow still works.

Real provider testing incurs API charges and is deliberately left for this review.

## Changed files

- Observation/provider: `backend/app/schemas.py`, `backend/app/providers/openai.py`.
- Answer: `backend/app/answer/visual.py`, `service.py`, `prompt.py`.
- Grounding/retrieval: `backend/app/rag/service.py`, `retrieval.py`, `prompt.py`.
- Native: `src-tauri/src/monitor/mod.rs`, `pipeline.rs`.
- Desktop contracts: `src/vision/types.ts`, `src/answer/types.ts`.
- Desktop views: `src/components/AnswerRecommendationView.tsx`,
  `MonitorResult.tsx`, `QuestionObservationView.tsx`.
- Tests: `backend/tests/conftest.py`, `test_rag.py`, `test_visual_tasks.py`,
  `tests/visual.test.mjs`. The shared observation fixture now includes null visual
  metadata; a separate regression covers old observations without the field.
- This document. The existing untracked Milestone 15 audit was preserved unchanged.

## Initial implementation validation record (before corrective pass)

Final checks on the implementation:

| Check | Result |
| --- | --- |
| Complete backend pytest | 297 passed, 2 opt-in PostgreSQL tests skipped |
| Ruff lint / format check | Passed; 77 Python files formatted |
| Complete desktop frontend suite | 151 passed |
| ESLint / TypeScript / Vite production build | Passed |
| Cargo formatting / offline check | Passed |
| Cargo tests | 51 passed |
| Offline Clippy with `-D warnings` | Passed |
| Git whitespace check | Passed; HEAD remains `8ed1d55` |

On this machine's Python 3.14, pytest used a process-local Windows selector-policy
harness, matching the established Windows/Psycopg development approach. Initial
restricted test attempts were interrupted before completion; the completed runs had
local asyncio socket access. No runtime policy, dependency or environment file was
changed. Warnings remain for the deprecated Python selector-policy API and existing
Starlette/Authlib httpx adapters. Cargo emitted filesystem hard-link-cache warnings
and copied incremental files instead; no Clippy lint failure occurred. Git reports
normal LF/CRLF normalization notices on several edited files.

Auth, capture, learning-session, privacy, manual workflow, RAG, diagnostics, pointer
and brand regression tests remain passing. The Vite watcher exclusions are unchanged:
`**/src-tauri/**`, `**/.tools/**`, `**/.cache/**`. Website, brand tokens, database
models/migrations, session/auth implementation and native window protection were
not modified. A fresh native launch, actual EBUSY behavior and external focus/capture
behavior were not re-tested in this implementation session. These remain manual checks,
not automated validation claims. Nothing was committed, pushed or deployed.

## Corrective pass — visual accuracy, copying and repeated processing

### Findings and evidence boundary

The user reported a real five-change slide comparison: title blue→green, increased
gap below the title, revenue callout blue→green, a taller second bar, and removed
confidentiality footer. The original live image/observation/provider payload was not
recorded (intentionally); therefore **the exact stage that lost those earlier facts
cannot be determined retrospectively**. No private content was recovered or logged.

Inspection and offline probes establish:

1. Native capture supplies RGBA pixels to a lossless PNG encoder; the current vision
   provider sends that bounded PNG with high image detail. No intentional thumbnail or
   lossy conversion was found. The corrective synthetic fixture's PNG bytes survive
   backend validation unchanged. This is not proof that the earlier native capture
   contained every intended pixel or that the live model read it correctly.
2. Initial visual extraction used broad per-image prose plus free-text changes; it
   had no separate per-property record for title spacing, bar height and bar color.
   The second model receives only the description, so it cannot recover a missed fact
   from pixels. It could also reinterpret or omit correct prose during prompt writing.
3. Pydantic serialization and `answer_input` preserve the new structured facts in
   round-trip tests; no field-dropping transformation was found in that path.
4. **Confirmed Copy defect:** the button required `kind=editing_prompt`. A valid
   editing instruction classified `mixed_visual` was therefore not copyable from
   either compact or expanded rendering. Expansion does not change this condition.
5. **Confirmed counter semantics:** `question_number` increments before a candidate
   pipeline starts, including bounded retries. The old Candidate label did not mean
   a unique question or a billed request. A pipeline may stop at session validation,
   perform Vision but suppress a duplicate Answer, or include Materials Only support
   verification. Candidate 1→5 alone cannot establish duplicate billing.
6. The existing gate suppresses an unchanged stable anchor. However, source noise
   can move the anchor away and back; deduplication later compares model-generated
   observation strings, which can vary. These are source-confirmed repeat paths,
   **not proof of which path occurred during the reported run**.

### Targeted corrections

**Property-aware observation.** VisualTask adds backward-compatible `requested_output`
and `comparisons` fields. Each comparison names an element, property (text, color,
spacing, size, position, presence or style), original/edited values and changed,
unchanged or uncertain status. Maximum 40 rows, element 160 characters and values
500 characters. Duplicate element/property pairs and contradictory unchanged values
are rejected. Old observations remain readable without these fields.

Vision instructions explicitly inspect the gap **below** the title, each bar height
against its baseline, callout styling and footer visibility. Colors and geometry
are compared independently within each slide's coordinates. A green title/callout
is not evidence that the chart bars were recolored. Cropping cannot establish removal;
approximate relations are preferred to invented pixel measurements. These instructions
do not prescribe a fixed number of changes to the model.

**Faithful editing-response formatting.** For explicit prompt-writing tasks with a
structured comparison, the existing provider result is formatted from changed rows
and explicit preservation constraints. Uncertain rows are excluded and the result is
marked uncertain with a warning; abstentions and answerless uncertain results remain
unanswered. An 8,000-character output bound is retained. Unsupported free-form model
recoloring cannot replace an unchanged color row in this formatted prompt, explanation
or key points. Old observations without comparison rows retain the earlier path.

This is deterministic formatting of observed facts, not another AI engine or a claim
that those facts are independently verified. **If vision itself records an incorrect
color/height/change, formatting cannot correct it.** Inspectable comparison facts in
the observation and floating panel make this distinction visible without sensitive logs.

Formatting occurs before the existing Materials Only independent support verification;
it is not performed after verification to bypass evidence checks. Grounded validation
rejects a differently rewritten comparison response. Unsupported materials still abstain,
and Context Guided still labels general-only reasoning without fabricated citations.

**Copy and task identity.** Prompt-writing instructions set `requested_output=editing_prompt`
even for mixed slides/charts/text. An explicit editing output normalizes `mixed_visual`
to `editing_prompt` at both contract boundaries; old mixed observations without that intent
remain unchanged. Selecting an existing prompt option remains a selection
task. Copy Response is also defensively available on any successful visual direct response
so an older mixed classification cannot hide it. The actual button handler copies only
`answer_text`, never the panel, explanation, sources or image. Failure remains accessible
and text stays selectable. No native clipboard/capture permission was broadened.

**Narrow full-frame repeat guard.** After local stability/cooldown and before starting
another pipeline, native code compares full-pixel fingerprints against the last completed
frame. Only dimensions and two domain-separated noncryptographic hash values remain in
memory; no extra pixel buffer, disk history or logged image hash is retained. Hash collision
is theoretically possible; this is an efficiency filter, never an authorization mechanism.
Hashing is performed only on dispatch-eligible frames, not every sample.

The guard is local to one run/source/session and resets on Pause/Resume/Stop/replacement.
Successful completion marks a frame; failed or aborted work is not marked complete.
Existing retry limits remain. A→unsettled noise→identical A can skip a repeat request. A→completed B→A
remains eligible. It does not fuzzy-match near-identical images, suppress arbitrary
animations, or replace server authorization. An obsolete answer is never restored from
this fingerprint cache. If it was cleared during source change, suppression leaves it
cleared with an explanatory status, preserving stale-result protection.

The visible counter now says **Processing attempt**. Diagnostics add only safe reasons:
`monitor_candidate_started.reason=stable_source_candidate|candidate_retry` and DEBUG-only
`monitor_frame_suppressed.reason=same_completed_pixels`. Existing trace/request/candidate
IDs correlate these with backend HTTP Vision/Answer outcomes. No image, fact, prompt,
answer or fingerprint is logged. Actual billing must be checked with provider usage,
not inferred from the displayed attempt number or HTTP count.

### Corrective regression evidence

`backend/tests/test_visual_corrective.py` generates a two-slide PNG in memory with
the five intentional changes and unchanged blue chart bars. A local SDK transport
double returns the corresponding structured observation. Tests verify lossless bytes,
all rows through schema/JSON/prompt construction, all five edits in the formatted answer,
and rejection of a deliberately fabricated free-form chart recolor. These tests prove
transport/formatting behavior, **not live model extraction accuracy**.

Additional tests cover mixed editing intent, uncertainty, duplicate properties, grounded
formatting before verification, and preserving answerless uncertainty. The frontend
test invokes the actual rendered Copy button callback against a mocked Clipboard API and
asserts exact prompt-only content. Rust tests exercise identical pixels, unsettled returns,
tiny genuine pixel differences, completed A→B→A transitions and fresh-run isolation.
Existing cancellation, session replacement, auth, provider and manual workflow suites remain
part of full regression validation. Windows clipboard/focus and live perception remain manual.

### Exact corrective manual retest

Start two PowerShell terminals:

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

1. Sign in yourself and retain screen-share privacy ON. Start a General session and
   explicitly authorize the practice window. Use the original five-change fixture with
   both full slides, labels, chart baseline and footer region legible. Avoid clocks,
   blinking carets and hover effects in the fixture for the static-frame test.
2. Start Monitoring. Inspect **Observed comparison facts** first. Confirm title color,
   title-to-content gap, callout styling, second bar size and footer removal are changed;
   chart bar color must be unchanged blue. Check direction from labels, not screen order.
3. Compare the generated prompt with those facts. All five changes must appear; there
   must be no instruction to recolor the chart bars. If facts are wrong, the error is
   upstream extraction; if facts are right but formatting is wrong, report the specific
   discrepancy. Do not copy sensitive content into logs.
4. In both compact and expanded views click Copy Response and paste yourself into a
   disposable editor. Clipboard text must equal the prompt alone. Confirm the button
   also appears if the task still reads mixed visual. Confirm monitored typing remains
   unaffected unless you deliberately focus/click the panel.
5. Leave the static fixture unchanged for at least 90 seconds. The anchor should not
   dispatch another pipeline. If Processing attempt increases, correlate DEBUG source
   changes, safe start reasons, request IDs and Vision/Answer HTTP outcomes; distinguish
   retries, duplicate-Answer suppression and real provider requests. The counter is not
   a billing meter. Returning to identical completed pixels may emit a suppression event.
6. Navigate to a clearly different visual question, then MCQ and code questions. Each
   genuine transition must remain eligible. Return after a successfully processed next
   page to check A→B→A. Pause/Stop mid-request and replace/end the session; no stale prompt
   may reappear. Resume must be explicit; there is no saved per-account frame history.
7. Repeat supported/unsupported cases in Context Guided and Materials Only. Verify real
   citations or labelled general fallback in Guided, and strict abstention for unsupported
   Materials Only conclusions. Do not disable window privacy for any test capture.

No live AI request, Google login, Neon connection or migration was performed for this pass.
Provider perception, visual accuracy on the real fixture, OS clipboard permission and
native focus/DPI behavior require the above manual review.

### Corrective file inventory

In addition to preserving the initial Milestone 16 changes:

- `backend/app/schemas.py`: requested-output identity and property comparison contract.
- `backend/app/providers/openai.py`: systematic comparison and classification instructions.
- `backend/app/answer/visual.py`: bounded fact-preserving editing-response formatting.
- `backend/app/answer/openai.py`: formatting before grounded support verification.
- `backend/app/answer/service.py`: canonical response validation and common-path formatting.
- `backend/app/answer/prompt.py`: property-aware answer instructions and mode boundaries.
- `src/vision/types.ts`, `src/answer/types.ts`: compatible validation and editing intent.
- `src/components/AnswerRecommendationView.tsx`: classification-independent visual copying.
- `src/components/QuestionObservationView.tsx`, `MonitorResult.tsx`: inspectable comparison
  facts and truthful processing-attempt terminology.
- `src-tauri/src/monitor/filter.rs`, `mod.rs`: last-completed-frame guard and retry diagnostics.
- `src-tauri/src/monitor/pipeline.rs`: direction checks include explicit editing output.
- `backend/tests/test_visual_corrective.py`, `tests/visual.test.mjs`: new regression coverage;
  Rust filter regressions reside beside the guarded logic. This document records the handoff.

No dependency, account/auth implementation, schema/migration, website, brand, capture API,
window-affinity or native clipboard-permission change was introduced by this correction.

### Corrective final validation

| Check | Result |
| --- | --- |
| Full backend pytest | **305 passed, 2 opt-in PostgreSQL tests skipped** |
| Ruff lint / formatting | Passed; 78 Python files formatted |
| Full desktop frontend suite | **153 passed** |
| ESLint / TypeScript / production build | Passed |
| Cargo formatting / offline check | Passed |
| Rust tests | **52 passed** |
| Offline Clippy `-D warnings` | Passed |
| Git whitespace check | Passed; HEAD remains `8ed1d55` |

Existing authentication, mode/ownership/consent, citations, session replacement,
cancellation, manual capture, code/MCQ answering, privacy and brand regressions pass.
The prior Python selector-policy, Starlette/Authlib deprecation, Rust incremental
hard-link fallback and Git line-ending notices remain; no new dependency was installed
to hide them. Native startup, real clipboard permission, focus behavior and real
provider perception were deliberately left for manual verification. The Vite watcher
exclusions remain unchanged. No migration, live provider call, Neon connection, commit,
push or deployment was performed. The pre-existing uncommitted implementation and
Milestone 15 audit remain preserved.
