# Milestone 14: purpose and reasoning policy

## Preparation and compatibility

The three visible choices are:

- Interview Preparation: interviews, technical discussions, role-specific preparation.
- Research & Study: studying, certification practice, research and learning.
- General / Custom: unrestricted learning and mixed-format practice.

Purpose is untrusted educational intent, never a filter on question type. Every
purpose supports multiple-choice, multiple-select, true/false, short/theoretical
answers, essays, mathematics, code and mixed observations. Objective remains a
separate step for all three. Blank General / Custom input uses:

> Help me understand questions and explore useful answers across learning topics and formats.

Other purposes require a nonblank objective. Explicit input is limited to 2,000
characters and rejects invalid controls. New writes reuse three existing database
values; there is no migration. See SESSION_PREPARATION.md for the six-value legacy
mapping. Saved/active records remain unchanged on read. Mapping on an explicit save
still requires the current revision; active configuration is never edited implicitly.
The former custom label field remains compatibility metadata, not another UI step.

## Reasoning correction

The former shared grounded prompt, empty-retrieval branch, citation requirement and
desktop parser all treated absent document support as mandatory abstention, including
Context Guided. This incorrectly applied the Materials Only policy to both modes.

- General keeps the existing AnswerService path and never retrieves documents.
- Context Guided prefers relevant selected evidence. Relevant supported results keep
  real citations and distinguish supplements. Empty retrieval, insufficient support,
  missing support targets or contradictory passages can invoke the same existing
  AnswerService without document content. The public mode stays `context_guided`;
  `grounding_status=general_reasoning` explicitly identifies a general-knowledge
  recommendation with no citations and a visible attribution notice.
- Materials Only is unchanged: evidence sufficiency, real citation membership,
  answer/explanation/key-point coverage and independent provider verification are
  required; lack of support or conflict abstains. General knowledge never fills gaps.

A Context Guided question/provider that cannot recommend reliably still abstains.
The supplement is not an automatic retry on malformed output, network failure,
authorization failure or fabricated citation IDs. At most one general supplement
call follows a grounded attempt; no relevant retrieval skips the grounded provider
call entirely. Grounded retrieval and any supplement share the existing configured
answer deadline. General's original path/timeouts remain unchanged. Supplementation
may consume another answer-provider request; no live or paid calls run in tests.

General supplements send the original structured observation and optional learning
intent through the existing provider; no retrieved passage, fabricated source or
screenshot is added. Option labels/counts, code, mathematics, instructions and
confidence validation remain in the existing AnswerService. Reading confidence and
answer confidence remain separate. Relevant citations reference only real retrieved
chunks; uncited parts are labelled as general reasoning. Model-based attribution is
not a guarantee of correctness or perfect semantic entailment.

## Security, privacy and lifecycle

Authentication, selected ownership and passage consent precede grounded work.
Owner/index generations are checked around supplementation and before publication;
active sessions still resolve mode/selection/consent server-side and check revision
and configuration after providers. No missing/foreign selection broadens retrieval.
Materials Only cannot accept general-only attribution in backend or desktop parsing.
Existing monitor generations, cancellation and floating-panel behavior are preserved.
The floating panel uses the same public answer parser/presentation as manual answers.
No capture, question, answer, provider payload or additional history is persisted.
No schema, website, brand, authentication or capture-privacy changes are involved.

## Manual review

Restart backend and desktop from D:\solveguide-ai using `npm.cmd run backend` and
`npm.cmd run desktop` in separate PowerShell terminals. Optional diagnostic logging
uses SOLVEGUIDE_LOG_LEVEL=DEBUG in both terminals; see DIAGNOSTICS.md. No migration
command is required. Do not disable screen-share privacy.

1. Sign in yourself. Recover an old saved draft/active session. Check mapped display,
   unchanged objective and usable recovery. Explicit save of an old draft should map
   the category and advance its revision; active sessions require normal replacement.
2. Start General / Custom with blank objective; review must show the default. Verify
   Interview and Research reject blank objectives. Check exactly three choices,
   keyboard focus, both themes, and the compact 640x560 window.
3. Across purposes, try disposable MCQ, multiple-select, code, essay/math and mixed
   questions. Preserve selection counts and question-specific instructions.
4. Recheck the Salesforce Pub/Sub API example in General as the existing baseline.
5. With a ready selected but unrelated document and explicit consent, use Context
   Guided. Expect a recommendation when general knowledge is sufficient, clearly
   labelled general reasoning with no citations; uncertainty may still abstain.
6. Repeat with a relevant document: inspect actual passages and citations. If support
   is mixed, general supplements must remain distinguishable.
7. Use Materials Only with the unrelated document: expect abstention and no answer
   confidence. With supporting material, inspect the real citations.
8. Repeat through explicitly activated Live Monitor and its floating panel. Pause,
   Stop, source change, session end/replacement and logout must invalidate old results.
   Screen-share privacy must remain enabled; no historical learning content appears.

Automated tests use fakes/mocks, not live Neon or paid providers. Real answer quality,
retrieval relevance, native focus behavior and live window layout need manual review.
