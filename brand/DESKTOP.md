# Stage 11B — desktop presentation

This stage builds on the uncommitted 11A foundation. `brand/tokens.css` remains the
only shared brand-token source. No website, functional milestone, dependency,
backend, schema or native security changes are introduced.

## Audit and changes

The previous desktop used 9–11px metadata, a large always-expanded materials panel,
weak separation between reading/recommendations/evidence, and a nested library
gutter that wasted compact-window space. The refinement:

- Raises application metadata to the shared 12px label role and control/body text
  to 14px, with prominent question and recommended-answer typography.
- Uses charcoal/white surfaces with mint for intent and darker green accents in
  light mode. Secondary buttons stay neutral; warning/error colours retain their
  semantic meaning and do not imply calibrated AI correctness.
- Clarifies navigation/current state, the signed-out brand composition and account
  card, and the explicit Capture → Read → Recommend → Review workflow.
- Keeps General/Context Guided/Materials Only visible. A keyboard-native details
  disclosure groups document selection, readiness and transmission consent.
  Opening it does not select documents, grant consent or issue provider requests.
  Existing readiness/status/error behavior stays intact.
- Separates recommendations, explanation, confidence and inspectable citations;
  insufficient/uncertain states receive warning emphasis rather than answer styling.
- Removes duplicate library gutters and improves document selection, preview,
  rename/form boundaries and extraction-failure presentation.
- Makes privacy status prominent in Settings, while preserving native effective
  state, persistence and failure semantics. Appearance and Pointer Light logic are
  unchanged. Selected theme miniatures use the approved palette.
- Uses short hover/press/reveal transitions. Continuous headline/background loops
  were removed. Reduced-motion disables animation/transitions; forced-colour rules
  preserve selected-control boundaries and focus. No new blur effects are added.

## Responsive and accessibility design

The existing 640×560 native minimum remains unchanged. Wide layouts use connected
capture/result columns; at 950px and below the workbench stacks, headings become
more compact and actions wrap. The existing intermediate icon rail and narrow
top navigation remain. Three reasoning modes stay side by side at native minimum
width; below 620px they stack. Library detail stacks below its list below 900px.

Main content scrolls naturally. Dialogs retain viewport-bounded vertical scrolling;
long source/document lists and extracted text retain bounded independent scrolling.
Focus rings have room inside scrollable source/material lists. Input/textarea/summary
focus, semantic radio/checkbox controls, native details keyboard behavior, text
selection, disabled controls and Pointer Light fallbacks are preserved.

These are implemented CSS behaviors, not measured browser/native results for this
continuation. Required visual review sizes: 640×560, 800×600, 1280×800, 1440×900.
Check all in dark/light; also confirm System follows the OS without losing preference.

## Automated and manual evidence

`tests/desktop.test.mjs` adds presentation coverage for the workflow, accessible
material disclosure/consent, citations, abstention, auth gate, library/capture/settings
controls, and empty/reading/retry states. `tests/helpers/desktop.mjs` renders synthetic
offline states with actual components; it never contacts providers or accounts.
These complement the existing controller, auth, capture, library, RAG and privacy
regressions. They are not real Google, native capture or answer-quality tests.

Final automated results: 120 frontend tests pass, including 10 brand and six desktop
presentation tests; ESLint, TypeScript and production build pass. Backend Ruff lint
and format checks pass; pytest reports 186 passed and two optional PostgreSQL tests
skipped. Existing Starlette/Authlib HTTPX deprecation warnings remain. Cargo fmt,
check, Clippy with warnings denied and 21 Rust tests pass. Protected controllers,
transports, backend/native sources, dependencies and Vite configuration have no diff.
Production assets exclude the showcase and offline review fixtures. The native
process is running with a window handle; its visual state was not verified here.

Local browser use was disabled in Work settings during final visual validation.
No alternate automation route was used to bypass that restriction. Native
screen-share protection stays enabled; it must not be disabled for screenshots.
Ignored static review pages under `.cache` are test artifacts, not a browser
application, authentication bypass or production navigation. They contain only
synthetic data and disconnected actions.

## Open and review

From `D:\solveguide-ai`, start the backend with `npm.cmd run backend` and desktop
with `npm.cmd run desktop` in separate terminals. If a development desktop/Vite
instance is already running, use it instead of starting a duplicate on port 1420.
The independent 11A showcase remains at `http://127.0.0.1:1420/brand.html`.

Manual acceptance checklist:

1. Review signed-out/checking/error/signing-in states, Settings access and keyboard
   focus. Complete Google sign-in manually; verify the learning gate and sign-out.
2. At each of the four sizes, inspect both themes: navigation, headings, wrapped
   controls, long document/source names, vertical scrolling and horizontal overflow.
3. Select a disposable window and capture. Verify preview, Retake, Change Source,
   Read Question, cancellation, loading and retry. Keep privacy enabled throughout.
4. Generate one authorized practice recommendation. Inspect neutral observed
   options, the suggested answer, explanation and separate reading/answer confidence.
5. Open Reference documents & permissions with keyboard Enter/Space. Check all
   three modes, disabled Materials Only, readiness and explicit consent. Verify no
   request occurs merely by opening the disclosure.
6. Review grounded citations/source navigation and Materials Only abstention.
   Changing mode/materials/capture must still invalidate stale answers.
7. Review library empty/list/detail/extraction failure, paste/rename/delete
   confirmation using disposable documents. Do not transmit personal materials
   without explicit consent.
8. Verify Light/Dark/System, Pointer Light and effective screen-share privacy status.
   Check Tab focus, text selection, reduced-motion and Windows high-contrast modes.

Stage 11C is not started. Shared tokens are available for a future public website,
but desktop visual acceptance should happen before its implementation is authorized.
