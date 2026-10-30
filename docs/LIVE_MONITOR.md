# Live Question Monitor — Milestone 13

## Explicit activation and product boundary

An authenticated user first starts or recovers a ready learning session, explicitly
chooses one window/monitor and accepts the automatic-transmission/cost notice, then
presses **Start Monitoring**. Launch, sign-in and session recovery never start capture.
Region remains unsupported. This is for authorized learning, practice and accessibility.
There are no monitoring-evasion, third-party process modification or hidden monitoring
features. No new database table, migration, provider, website or persistent history.

Live Monitor becomes the primary active-session workflow. The existing manual Capture →
Read Question → Get Suggested Answer flow remains in a disclosure; pause monitoring
before using its capture/provider controls. Pause/Stop remain available during startup.

## Native architecture

`src-tauri/src/monitor` separates lifecycle/orchestration, local filtering, sequential
pipeline and the owned answer window. `src/monitor` supplies strict status parsing,
typed IPC and UI cancellation/polling. Native credentials never cross this boundary.

A single native task samples only the selected source through the existing Windows
Graphics Capture/D3D11 implementation. It uses bounded single-frame capture sessions,
not a recording stream or a browser screenshot. The shared manual implementation is
retained; live sampling bypasses manual HiddenWindow/restoration entirely. Windows'
capture indicator remains enabled. Cursor capture is disabled where the API supports it.

A retained GraphicsCaptureItem with an agile reference and Closed flag pins source
identity across samples and pauses, without active capture. A closed item is never
reinterpreted through a reused HWND. Stop/logout drops this identity too.

Each sample closes its capture session/frame pool and releases COM/DPI/D3D resources
before PNG encoding/provider work. The loop retains small fingerprints, one current
sample and at most one pending candidate. Only stable candidates are PNG-encoded;
encoding is serialized so canceled blocking encodes cannot create an unbounded queue.
The existing 40 MP / 10 MiB PNG limits remain. No frames, screenshots or history files
are written. Sample sessions recreate D3D resources: GPU/power overhead and display-driver
behavior need hardware testing; this is deliberately low-frequency sampling, not video.

## Filtering, deduplication and budgets

Default native bounds:

| Setting | Default | Allowed range |
| --- | --- | --- |
| Sampling interval | 1,500 ms, plus capture/check time | 1,000–5,000 ms |
| Stable-content wait | 3,000 ms | 2,000–10,000 ms |
| Minimum candidate interval | 30 seconds | 30–120 seconds |
| Candidate attempts per activation/resume | 60 | 1–60 |

A 128×72 luminance signature compares sampled image pixels. A cell changes when its
luminance differs by more than 20; more than 0.4% changed cells signals a meaningful
change. Dimensions are also compared. Small pointer noise is ignored. A new candidate
must remain stable before processing. There is no backlog of pages: a newer page wins.

After vision, a structured fingerprint compares question type, text, options,
instructions, selection count, visible context and visual elements. Confidence/warnings
are excluded; prose whitespace is normalized while code layout is retained. Only a clear
detected question (confidence at least 0.65, known type and nonblank text) proceeds to
answers. The previous completed question is deduplicated; a duplicate candidate does
not issue another answer call or redisplay a potentially obsolete cached recommendation.

Local filtering and model extraction are heuristic: small text-only differences can be
missed; animations can delay stabilization or cause extra vision candidates. Whitespace
normalization does not make differently worded model observations semantically identical.
Use the manual fallback for ambiguous layouts. No claim of perfect question detection.

A candidate can incur a vision call, an answer call, an ephemeral query embedding and,
for Materials Only, a support-verification call. Two candidates/minute does **not** mean
two total provider calls/minute. Failed attempts count toward the activation budget.
Transient failures back off at least 30 then 60 seconds while preserving the configured
minimum interval. Three consecutive failures enter Recoverable Error; the budget limit
pauses. Resume is explicit, revalidates the session/source and begins a new budget.
There are no infinite retries or background startup requests. Provider SDK timeouts,
existing native HTTP deadlines and the shared single AI-request slot remain in force.

## Lifecycle, stale work and account isolation

Stopped → Monitoring → Processing → Answer ready; Pause → explicit Resume; Stop clears
selection/content; recoverable capture/provider errors require user action. The native
run/intent identifiers reject a Start that was waiting when Pause/Stop arrived. Scoped
shutdown means an old failed loop cannot stop a newly resumed run. Each meaningful page
change increments a generation, clears the old answer and aborts obsolete work. Only
matching run/generation results can publish.

Cancellation uses native atomic flags, Notify and task abort handles, not WebView timers.
The frame wait checks cancellation every 50 ms, with a five-second frame timeout. Already
running native/PNG operations finish cleanup; a provider request already accepted may
still finish remotely and incur charges. Ending/replacing a session and native logout
stop monitoring immediately on the local command path. Shutdown stops tasks and destroys
the child window. Credential epochs prevent old-account requests/results being reused.

The native loop checks server session ID/revision/readiness before processing, between
vision and answer, and before publication, plus periodically (about five seconds when
capture/backend are responsive). External session changes or access loss stop monitoring.
Remote change detection has capture/network latency; it is not instantaneous. Session
metadata includes existing index generations, so reindex/deletion invalidates old grounding.
Metadata reads select no extracted text. General does not compare/retrieve document
content or use RAG. Context Guided and Materials Only remain server-authoritative through
`POST /api/v1/answer` with observation + session ID/revision only. Existing ownership,
consent, citation validation and Materials Only support verification are unchanged.

## Floating answer window

`answer-panel` is a separate compact decorated, movable Tauri window: 420×440 logical
pixels, expandable to 520×680, clamped to the monitor work area including native frame
and scale. Initial placement uses the source's largest overlapping monitor. Native title
bar dragging and explicit keyboard focus remain available. It shows candidate/generation,
mode, observed question, recommendation, explanation, confidence, warnings, citations
and abstention. Citations expand to actual supporting passages; full library navigation
is available from the main workspace without automatically restoring it.

Creation uses `focused(false)` and automatic Windows showing uses documented
[SW_SHOWNOACTIVATE](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindow).
Updates never call focus, maximize or restore the main window. Only the explicit main
**Focus panel for keyboard use** action requests panel focus. This implementation is
not proof of focus behavior: typing continuity must be checked on the actual machine.
No third-party hooks or input interception. Non-Windows capture is unsupported.

Dismiss/close destroys the panel WebView while native monitoring can continue; reopen
creates a fresh view from the current snapshot, preventing old renderer content flashes.
Stop/logout/session changes destroy it and clear content. Pause leaves an accurately
paused panel with cleared answers. The main app close destroys its child window too.
Status updates poll bounded snapshots (500 ms panel / 700 ms main); native sampling and
cancellation continue independently when the main WebView is minimized or throttled.

The same device-local Screen-share privacy preference applies before first display and
on reopen. Settings applies/verifies affinity on both owned windows; failures are shown
accurately. No privacy weakening for screenshots/testing. WDA_EXCLUDEFROMCAPTURE is not DRM
or a guarantee against every capture method. With privacy OFF, a monitor capture can
include SolveGuide itself; prefer explicit external-window capture to avoid recursion.

## Validation and manual acceptance

Run from `D:\solveguide-ai`:

```powershell
npm.cmd run backend:lint
npm.cmd run backend:test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test:interaction
npm.cmd run build
npm.cmd run desktop:check
npm.cmd run desktop
```

Use the existing project-local Cargo environment for fmt/check/test/Clippy (-D warnings).
Automated tests use fakes and synthetic frames/observations, with no paid requests or
Google sign-in. No migration is required for this milestone. Offline existing migration
checks remain in the full suite; no live Neon migration or destructive tests are run.

Manual acceptance (user-operated, disposable practice material, explicit provider consent):

1. Start backend (`npm.cmd run backend`) and native app (`npm.cmd run desktop`). Sign in,
   recover/start a ready session. Confirm monitoring is Stopped; keep privacy ON.
2. Choose a disposable Chrome practice-question window, accept automatic costs/transmission
   and Start. Type continuously in Chrome as the panel opens and updates. Confirm focus
   stays in Chrome and the main window is never restored/maximized. This is the required
   native focus test; do not mark it passed from unit tests or API documentation.
3. Hold one question still for stabilization/request cooldown, then navigate through
   ten questions. Confirm automatic reading/recommendations, generation changes and no
   repeated answer calls for unchanged/duplicate questions. Rapid navigation should
   discard old results rather than queue all past pages.
4. Navigate while vision/answers are pending; only the newest question may publish.
   Pause during Start, vision and answer; verify no late answer appears. Resume explicitly;
   Stop and change source. Confirm no silent source switch or automatic restart.
5. Test General, Context Guided and Materials Only sessions. Inspect real citations,
   support and abstention; reindex/delete a selected document and confirm invalidation.
6. Minimize/close the monitored app; verify monitoring stops with a recoverable error.
   Restore and Resume only that source, or Stop/reselect. Disconnect the backend/provider
   and check bounded backoff/error controls. Do not repeatedly generate paid failures.
7. Dismiss/reopen the panel, expand/compact it, move it, deliberately focus it via the
   main keyboard action, then use keyboard Pause/Stop. Check that controls and source
   passages remain usable on 100/125/150/200% scaling, negative-origin/mixed-DPI displays
   and different taskbar positions. These hardware combinations are not yet verified.
8. End/replace the session and sign out while work is pending. Both content and panel
   must clear; a different account must never receive the previous answer. Restart and
   recover the session: monitoring must still be stopped.
9. Verify Screen-share privacy covers both windows using a supported external capture
   path, without disabling it for testing. Capture another selected app normally.
10. Pause Live Monitor and exercise the complete manual workflow. Review dark/light/system,
    keyboard focus, reduced motion, forced colours and 640×560 compact main-window layout.

Live multi-question quality, focus continuity, DPI/hardware behavior and actual external
capture exclusion require manual acceptance. Automated success does not establish those
claims. No Live Monitor history, recording, billing, analytics or website functionality
is introduced.

### Session-validation latency policy

See DIAGNOSTICS.md. Monitor validation uses a compact authenticated owner-scoped
projection with a bounded 12-second total deadline and no automatic retry. Overlapping
checks share one in-flight response; sequential checks always reach the backend.
Heartbeat spacing is five seconds after completion. Readiness/index generations are
still server-checked, and native invalidation interrupts pending validation including
startup. Full preparation remains the recovery UI contract; lifecycle writes keep
account serialization. No schema change or persistent authorization cache is added.
