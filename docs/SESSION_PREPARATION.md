# Session Preparation — Milestone 12

## Boundary and architecture

The authenticated desktop now prepares Purpose → Objective → Reference Materials →
Reasoning Mode → Review → Start Session before opening the existing manual workspace.
There is no Live Question Monitor, automatic capture, automatic provider request or
persistent question/answer history. No website changes or new dependencies are required.

`src/learning` owns typed native transport, runtime DTO checks and recovery/lifecycle
state. `LearningWorkspace` presents preparation and a compact active summary.
`src-tauri/src/learning.rs` exposes fixed, main-window-only operations through the
existing native-memory AuthState credential and epoch boundary. React receives no
session credential, URL or filesystem capability.

`backend/app/learning` separates strict schemas, SQLAlchemy metadata, owner-scoped
repository, lifecycle service and authenticated API. Existing Context Library and RAG
remain the only document/index/retrieval systems. No document is selected automatically.
At most five explicit references are allowed. Objectives are required, trimmed and
bounded to 2,000 characters; custom purposes are required only for Custom Purpose
and bounded to 100 characters. Saved drafts must satisfy these basic field constraints;
incomplete editing remains local until Save Draft. A readiness review additionally
validates grounded material readiness and passage-transmission consent.

## Database and lifecycle

Additive Alembic revision `0004_session_preparation` follows `0003_context_rag`:

- `learning_sessions`: UUID, owner, purpose/custom purpose, objective, reasoning mode,
  passage-transmission consent, selected-reference count, revision, lifecycle state
  and timezone-aware timestamps.
- `learning_session_documents`: ordered explicit document references with composite
  owner foreign keys to both the preparation and Context Library document.
- PostgreSQL partial unique indexes allow one active and one draft/ready preparation
  per owner. Every lifecycle transaction locks the account row, including first draft
  creation. Revisions reject stale changes. No production `create_all()` is used.

Draft → Ready → Active → Ended are explicit transitions. Editing Ready returns it to
Draft. Start revalidates readiness transactionally. A repeated accepted start is
idempotent. Starting another session requires the exact active session ID confirmed
by the user; it ends the old session and activates the new one in the same transaction.
End requires the current ID and revision. Only the latest ended metadata is retained;
this is recovery metadata, not a session-history product.

Deleting a document cascades its association rows, avoiding dangling references. The
saved selection count detects removed references; a grounded session then fails closed
and requires new preparation. Pending deletion, failed extraction and unavailable indexes
also prevent grounded answers. General ignores reference readiness/content for reasoning.
Renaming does not create a duplicate document or regenerate embeddings.

## Authenticated API

All routes require the existing authenticated user; POST/PUT also retain exact-origin
and bounded JSON validation. No request accepts a client owner identity.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/v1/learning/preparation` | Current draft and active session |
| PUT | `/api/v1/learning/preparation` | Create/update draft using expected revision |
| POST | `/api/v1/learning/preparation/{id}/ready` | Validate and mark reviewed |
| POST | `/api/v1/learning/sessions/start` | Start reviewed preparation; explicit replacement ID if needed |
| GET | `/api/v1/learning/sessions/active` | Active session metadata or null |
| POST | `/api/v1/learning/sessions/{id}/end` | Explicit revision-checked end |

`POST /api/v1/answer` accepts an additional strict envelope:
`{observation, session_id, session_revision}`. Backend loads purpose, objective, mode,
references and consent from the active owned session. Client mode/document overrides
are rejected. Legacy observation/reasoning requests remain compatible only when no
active preparation exists; they cannot bypass an active session's configuration.

General routes directly to the existing AnswerService without document retrieval.
Context Guided and Materials Only use the existing RagService with the authoritative
selection and consent; existing citations, independent support verification and
Materials Only abstention remain unchanged. The backend checks the session again after
provider completion and rejects late results after end/replacement/material deletion.
RAG retains its index-generation checks. No database transaction spans provider I/O.
Purpose/objective are untrusted educational intent, not instructions overriding mode,
evidence or security rules.

## Desktop recovery, accessibility and stale requests

The authenticated host recovers draft/active metadata at mount, on window focus, after
library changes and periodically (60 seconds). App restart requires existing native
reauthentication; after sign-in, active metadata recovers from the account. Refresh
failure pauses core workspace access. End/replacement/logout unmounts the old manual
workspace and clears its ephemeral UI/controllers. A reviewed revision is required to
start; replacement and end confirmations identify the exact session being confirmed.
Development Strict Mode effect replay is supported without accepting older refreshes.

Steps use semantic headings, radio buttons, labels, fieldsets, visible focus and
status/error announcements. Existing theme, Pointer Light, reduced-motion, forced-colors
and native screen-share privacy stay intact. Step controls wrap; narrow layouts collapse
to one column and use the existing page scroll. No native privacy protection is disabled
for visual testing.

## Privacy and consent

Only preparation metadata and explicit reference associations persist. Screenshots,
QuestionObservation, AnswerRecommendation, explanations and provider payloads remain
ephemeral. No screenshots are resent to AnswerProvider. Starting/recovering/saving/ending
alone never captures, indexes or calls AI. Existing explicit Read Question and Get
Suggested Answer controls remain.

On an explicit answer request, purpose/objective join the structured observation sent
to OpenAI. Grounded answers additionally transmit relevant selected passages only with
existing explicit passage consent. Hosted document embedding consent remains separate;
indexing is explicit. General transmits no document passages. No sensitive content or
credentials is added to logs.

## Local validation and migration approval

From `D:\solveguide-ai`:

```powershell
npm.cmd run backend:lint
npm.cmd run backend:test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test:interaction
npm.cmd run build
npm.cmd run desktop:check
```

Normal backend tests use transactional service doubles and offline PostgreSQL-dialect
DDL rendering. These validate transitions, lock contention at the fake boundary,
ownership, explicit selection, mode routing, consent, deletion, late results and privacy
schema. They are not proof of live PostgreSQL concurrency. Optional destructive database
tests require a dedicated disposable TEST_DATABASE_URL plus ALLOW_TEST_DATABASE_RESET=1;
never use the real application database for downgrade tests.

**The new migration is prepared, not approved for live Neon application.** After user
approval, run (no secrets in commands/output):

```powershell
& .tools/python/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
& .tools/python/Scripts/python.exe -m alembic -c backend/alembic.ini current
& .tools/python/Scripts/python.exe -m alembic -c backend/alembic.ini check
```

Expected head: `0004_session_preparation`. Never downgrade the live Neon database to
test reversibility. Existing configured schema remains unchanged until approval.
Start backend with `npm.cmd run backend` and desktop in another terminal with
`npm.cmd run desktop`. No new environment variables are required.

## Manual acceptance after approved migration

1. Sign in manually. Confirm appearance/Pointer Light and Screen-share privacy remain ON.
2. Choose each suggested purpose and Custom; confirm blank/whitespace objective cannot
   continue, and useful multiline objectives save. Save Draft; restart/reauthenticate
   and reload the saved preparation without losing explicit document selections.
3. General: use no documents, review and start. Confirm summary and manual Capture →
   Read Question → Get Suggested Answer. Starting alone must send no provider request.
4. Prepare another session while one is active; verify replacement requires confirmation.
   Cancel replacement, then confirm. Verify old captures/questions/answers are cleared.
5. Select one owned ready indexed disposable reference, choose Context Guided, explicitly
   consent to passage transmission, review/start and inspect existing grounded citations.
   Test Materials Only support and abstention with an unrelated question. Paid/provider
   checks are manual, explicit and subject to consent.
6. Test missing/unready materials and consent OFF. Do not start grounded preparation
   until ready. Delete a selected reference; verify grounded requests fail closed,
   new preparation shows accurate readiness and no dangling source is reused.
7. End explicitly, including while a request is pending; late results must not appear.
   Sign out/in and restart to recover the active session (or no active after ending).
8. Use two desktop instances: concurrent starts must leave one active; a stale draft,
   replacement or end confirmation must fail and require refresh/review.
9. Review dark/light/system themes at 640×560, 800×600 and larger sizes; keyboard-only
   progression, visible focus, status messages, wrapping, scrolling, Settings and Library.
   Keep Windows capture protection enabled; verify capture of another selected app.

Milestone 13 may consume the typed active-session endpoint. No monitor, background
capture, floating UI or automatic AI behavior is implemented here.
