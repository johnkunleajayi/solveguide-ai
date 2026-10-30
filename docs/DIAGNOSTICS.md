# Live Monitor diagnostics

## Enable diagnostics

The normal application level is **INFO**. Set **SOLVEGUIDE_LOG_LEVEL=DEBUG** in
both PowerShell terminals before starting their processes. This controls only
SolveGuide's allowlisted JSON diagnostics; it does not enable SDK, HTTP wire/body,
SQL statement or global Rust debug logging. No logging dependencies were added.

Stop the previous backend/desktop development commands with Ctrl+C first. From the
canonical workspace, start the backend:

```powershell
Set-Location D:\solveguide-ai
$env:SOLVEGUIDE_LOG_LEVEL = 'DEBUG'
npm.cmd run backend
```

In a separate PowerShell terminal, start the desktop:

```powershell
Set-Location D:\solveguide-ai
$env:SOLVEGUIDE_LOG_LEVEL = 'DEBUG'
npm.cmd run desktop
```

The backend also accepts SOLVEGUIDE_LOG_LEVEL=INFO or DEBUG in its ignored `.env`;
the native process reads its environment, not the backend's file. Setting the variable
in both terminals is the simplest troubleshooting workflow. To return to normal,
set the value to INFO and restart both commands. Do not enable SDK/body tracing,
SQL echo, Uvicorn access logs or blanket RUST_LOG=debug for this investigation.

Logs appear in the respective PowerShell terminals (stderr), alongside ordinary
Uvicorn/Cargo startup messages. No automatic log file, database table or telemetry
sink is created. If saving logs manually, use an ignored file inside D:\solveguide-ai\.cache.

## Correlation fields

- `trace_id`: one native activation. Explicit Resume creates a new activation trace.
- `candidate_id`: one local question generation, shared by its session checks, vision
  and answer requests. Retried HTTP calls have fresh request IDs.
- `request_id`: one native-to-backend HTTP request. X-Request-ID,
  X-Solveguide-Trace-ID and X-Solveguide-Candidate-ID carry only these diagnostic IDs.
- `timestamp_ms`: UTC Unix milliseconds for comparing both terminals.
- `duration_ms`: monotonic elapsed time, not provider token usage or billing.

Backend request context uses ContextVar isolation and is reset on completion/cancellation.
Supplied IDs must match bounded approved formats; arbitrary/token-like headers are
replaced or discarded. Manual AI requests retain UUID correlation. No credentials
are added to diagnostic headers. Response headers echo only validated IDs.

Find the native `monitor_start` record for the failing activation, then follow that
trace in both terminals. Locate the failing request ID and compare `backend_http`,
`session_check_finished` and backend `http_request`/stage records. A backend completion
means handler completion/status, not proof that the canceled client received the reply.

## Important events

| Event | Meaning |
| --- | --- |
| monitor_start / monitor_start_failed | Explicit activation requested, active or failed |
| monitor_action / monitor_transition | Pause/Resume/Stop intent and resulting state; reasons distinguish user_requested, source_changed, workspace_disposed, logout and session_transition |
| session_check_started / session_check_finished | Native session verification and its bounded 12,000 ms validation deadline |
| native_authentication_validation | Native credential/epoch validation timing, no credential value |
| backend_http_started / backend_http | Native HTTP endpoint template, status when known, duration, safe error category |
| http_request_started / http_request | Correlated backend receipt and completion |
| stage_started / stage_finished | Authentication, session lookup, retrieval, provider and service timing |
| database_transaction / database_failure | Transaction timing; allowlisted SQLSTATE/reason on failure, never SQL or connection details |
| session_lookup / session_revision_check | Owned lookup or stale revision; missing and foreign-owned IDs remain indistinguishable |
| monitor_candidate_changed / stale_result_suppressed | New source generation or obsolete result suppression |
| monitor_candidate_started / monitor_candidate_finished | Automatic candidate processing and safe result status |
| monitor_source_failure / monitor_pipeline_failed | Source loss or bounded pipeline failure |
| monitor_unexpected_termination / monitor_worker_terminated | Unexpected native loop/worker exit without exception text |
| retrieval_decision / answer_decision / support_verification | Retrieval counts and safe grounding/abstention reason codes |

Successful heartbeat, authentication, transaction and stage detail is DEBUG-only.
Failures are WARNING (visible at normal INFO). Candidate/lifecycle and AI HTTP outcomes
remain INFO. Polling the native status snapshot produces no repeated HTTP diagnostics.
Per-route legacy vision/answer summary logs were consolidated into one backend HTTP
completion record; stage/decision records serve different diagnostic purposes.
Expected cancellation is DEBUG rather than a provider/authentication failure.

## Interpret this incident

Native monitor checks use authenticated `POST /api/v1/learning/sessions/{id}/validate`
with the expected revision. A **12-second total deadline** covers the local native
credential check, single-flight wait, HTTP authentication, database work, transfer
and response validation. There are no automatic retries or grace authorization.
A timeout stops monitoring explicitly with `session_check_timeout`, not an expired
or revoked authentication label. Only a real HTTP 401 clears the native credential.
The previous five-second deadline had little margin over observed 3.9–4.3 second
successful requests. The exact original timed-out request remains uncorrelated;
these code-path findings explain the latency risk, not a proven Neon outage.

The dedicated backend projection reads only the owned session, revision, lifecycle,
consent, selected-reference readiness and index generations in one SQL statement.
It does not load draft preparation, titles, objectives, document text or vectors,
and takes no lifecycle account/document row locks. General does not join selected
references into results. Authentication still validates the server-side credential
on every actual request, and answer requests still enforce configuration before
and after provider execution. Database connection/statement limits remain unchanged.
Existing lifecycle writes keep their account serialization and uniqueness safeguards.
The full `/sessions/active` endpoint remains available for desktop recovery and now
loads only the active view, rather than unnecessarily loading a draft as well.

Only callers overlapping the same in-flight validation share its completed response;
there is no TTL cache or cached authorization between sequential checks. Each new
activation has its own coalescer, so no account/session/source reuse occurs. A DEBUG
`session_check_coalesced` event explains why a waiter has no separate backend request;
match the shared activation trace to the leader's HTTP request. Heartbeats wait five
seconds after completion, and do not immediately repeat the startup check. Candidate
pre/post-provider validation remains in place. Pause/Stop/logout/session transition
notify native validation waiters immediately, dropping pending futures, including
startup; cancellation does not rely on a WebView timer. Source-change Stop and worker
aborts retain their existing invalidation boundaries. Successful heartbeats remain
DEBUG-only. Privacy and capture behavior are unchanged.

A healthy `/api/health` reports process/configuration status, not successful authenticated
PostgreSQL session lookup. A 19â€“21 second answer completion does not establish why a
separate session request failed. The next manual trace should distinguish:

- `session_check_timeout` / `network_timeout`: the 12-second total deadline expired. Find the
  same request ID on the backend. A late backend completion can coexist with this timeout.
- `backend_connection_failed` / `network_connect`: connection establishment failed.
- `backend_timeout`: the underlying HTTP client timed out.
- `session_expired`, `session_revoked`, `invalid_session`, `sign_in_required`: authentication.
- `session_revision_mismatch`: the selected revision no longer matches.
- `session_missing`, `session_replaced`, `session_not_active`: lifecycle mismatch.
- `session_materials_changed`, `session_materials_not_ready`: index/readiness changed.
- `database_*`: review transaction timings and safe SQLSTATE/reason, including pool,
  statement or lock timeout. Do not expose a database URL to diagnose this.
- `answer_timeout`, `provider_timeout`, provider authentication/rate-limit codes: an
  AI provider failure, distinct from learning-session access.

HTTP 200 with `outcome=insufficient_information` is a valid abstention, not an
HTTP/authentication failure. `answer_decision.reason` distinguishes incomplete observation,
selection conflict, missing options, provider_abstention, unavailable/empty retrieval,
contradictory evidence and incomplete citation support. `support_verification` identifies
failed Materials Only support checks. Free-form model explanations are intentionally
not logged; inspect those in the application instead. General mode remains General;
no material retrieval is added by diagnostics.

## Privacy and validation

Only fixed event/stage names, validated IDs, endpoint templates, codes, counts, status
and timing fields are emitted. No screenshots/base64, question or answer text, passages,
objectives, titles, provider payloads, OAuth values, cookies, authorization headers,
API keys, database URLs or raw exception messages/tracebacks are logged. Query strings
are omitted; unknown paths become `/unclassified`. Internal account/session UUIDs may
appear in owned backend lookup diagnostics; treat diagnostic logs as operational data.

Automated tests cover redaction, forged header rejection, overlapping-request context
isolation, session failures while health stays OK, revision/ownership checks, abstention,
quiet heartbeats, cancellation cleanup, actual bounded expiry and native trace
relationships. Automated tests use fakes and do not call paid providers or migrate Neon.

After restarting both processes, sign in manually, explicitly start monitoring a disposable
practice source and reproduce once. Keep screen-share privacy ON. If it stops, retain the
native failure record plus backend records with the same trace/request IDs. We should use
that evidence before deciding whether the deadline, database runtime or workflow needs
any further change. The original live failure is not yet proven to have a specific cause.

## Latency-fix manual retest

Restart both commands above. Sign in yourself, recover/start a learning session,
and explicitly monitor a disposable practice source. Keep screen-share privacy ON.
Check that session HTTP diagnostics use `/sessions/{id}/validate` (native endpoint
is sanitized), `deadline_ms=12000`, and a shared activation trace. Valid responses
between five and twelve seconds should continue monitoring. Navigate questions;
confirm stale answers clear, manual capture remains usable when paused, and grounded
sessions still stop on deleted/reindexed materials or revision changes.

While a session check is pending, Pause and Stop must clear activity immediately;
Resume must be explicit. Test source changes, logout, End Session and replacement
without allowing old results to reappear. With a deliberately unavailable local
backend, verify a bounded connection/timeout failure, no revoked-session label,
and no silent retry. Do not edit Neon credentials or run migrations to simulate
latency. Automated tests cover >5-second success, real 12-second expiry, cancellation
cleanup, expired/revoked authentication, ownership and revision/readiness failures.
No live database latency or provider behavior was verified by those offline tests.
