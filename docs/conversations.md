# Phone conversations — development candidate

This feature is not in the current external TestFlight build. It requires the
updated iPhone app and Ceviz helper. It does not change the Watch's OpenClaw
target or the operator's Gateway configuration.

## Product behavior

Open **Conversations** on the phone home screen to find an existing OpenClaw
conversation, inspect its history, and send a message to that exact conversation.
The list keeps Gateway ordering and uses the TUI's title and last-message
metadata. The default window is the latest 50 sessions active in seven days;
the older-conversations switch removes the time filter. Assistant selection,
server-side search and paging are explicit. This is not a claim that every web,
TUI and phone filter is identical.

Phone messages use the canonical assistant-owned session key, physical session
ID and a transcript-leaf guard. The Gateway rechecks the target at admission;
a reset or branch switch cannot silently send into a different conversation.
Ordinary messages explicitly use `queueMode: followup`, so busy conversations
queue the message instead of interrupting the active work. Slash commands and
the Gateway's recognized stop phrases are rejected in this first version; use
OpenClaw's controls for those operations.

This is a separate surface from Ceviz **Jobs**. A Ceviz job follow-up adds the
selected job's short context to its configured agent invocation; a phone
conversation message continues the real OpenClaw session without that wrapper.
No new phone microphone recorder, Watch session chooser, model controls,
session deletion or approval-management panel is included. The phone composer
uses the normal text keyboard, including system dictation when available.

## Delivery semantics

- The phone generates one UUID per attempted message. Acknowledgment is not
  task success. The UI separately shows queued, running, finished, stopped,
  failed and unconfirmed states.
- A timeout never triggers automatic resubmission. The draft stays in memory
  during the current app session. Local SQLite metadata preserves the exact
  delivery identity and status across phone/helper restarts, without storing
  conversation text or credentials in those journals.
- The helper records the message's owner before submission and checks only
  matching run results. A bare `agent.wait` timeout is unknown, not failure;
  a terminal result stays terminal after Gateway result-cache expiry.
- The helper commits ownership before dispatch in `conversations.sqlite`
  under its existing `WATCH_CEVIZ_STATE_DIR`. It retains at most 512 request
  identities without automatic eviction. Capacity exhaustion visibly rejects
  new messages; restarting does not reset this limit. A safe capacity/retention
  management flow is a named follow-up, not permission to delete replay guards.
- The phone keeps its last delivery per conversation and pairing in its private
  Application Support SQLite journal, excluded from device backup. A hashed
  pairing identifier separates connections; switching back restores that
  pairing's guard. Late callbacks from a previous pairing are ignored.
- A disk failure prevents a new send. Once dispatch is possible, missing
  evidence remains **unconfirmed**: no timeout or restart proves non-execution.
  A result never observed before upstream retention expires may stay unknown.
- **Continue after reviewing** is available only for an unconfirmed delivery.
  Its confirmation explains that the earlier message may still run. It records
  an operator-reviewed state, clears the old draft and opens an empty composer;
  it neither retries nor cancels the old request, nor removes the helper's
  deduplication record. Queued/running messages cannot use this action.
- Neither opening a conversation nor choosing an assistant changes the
  Watch's destination. Gateway model and permission settings remain in force.

## HTTP boundary

All routes use the existing Ceviz bearer authorization. Responses are JSON and
conversation content is marked `Cache-Control: no-store`. Gateway credentials,
raw CLI diagnostics and hidden reasoning are not returned by this surface.

| Route | Purpose |
| --- | --- |
| `GET /api/v1/capabilities` | Advertise `continuation_v1`, `suggestion_approval_v1`, `conversations_v1`. |
| `GET /api/v1/sessions` | `agent_id`, `search`, `older`, `offset`; return sessions, assistant names and next page. |
| `GET /api/v1/sessions/history` | `session_key`, `offset`; chronological messages, earlier-page cursor and current target guard. |
| `POST /api/v1/sessions/message` | `session_key`, `session_id`, `expected_leaf_entry_id` (including explicit null), `text`, `request_id`; return acceptance/run identity. |
| `GET /api/v1/sessions/run` | `session_key`, `run_id`; check the exact submission without replay. |

History includes readable user/assistant text; other content is marked rather
than rendered as arbitrary HTML. Message text is limited to 16,000 characters.
Errors contain `code`, a safe `error` summary and `delivery_uncertain`.
Run IDs are opaque, case-sensitive identifiers; retain the exact UUID spelling
returned by the request rather than generating a replacement.

## Continuation and suggestion approval

The shortcut endpoint accepts `intent: follow_up` (also the legacy default) and
`intent: approve_suggestion`. Approval requires a completed `continue_job_id`
and an existing agent-action `next_action_id`; the server resolves its full
text. A free-text follow-up never implies approval. New standalone commands
never inherit the globally most recent job.

The Watch freezes the displayed result's job ID when recording starts within
its 180-second continuation window. Delayed delivery retains that same parent.
Both transport identity and backend duplicate detection include it. A linked
recording is kept if an older phone/helper cannot preserve these semantics.

## Verification and upstream contracts

The dependency baseline is OpenClaw **2026.9.1**:
[TUI query](https://github.com/openclaw/openclaw/blob/v2026.9.1/src/tui/tui-session-picker.ts),
[history projection](https://github.com/openclaw/openclaw/blob/v2026.9.1/src/gateway/server-methods/chat-history-handler.ts),
[send admission](https://github.com/openclaw/openclaw/blob/v2026.9.1/src/gateway/server-methods/chat-send-admission.ts),
[control text](https://github.com/openclaw/openclaw/blob/v2026.9.1/src/auto-reply/reply/abort-primitives.ts).
Changes to that control-text normalization require reviewing this boundary;
do not silently assume compatibility with every future Gateway version.

Python tests cover real local HTTP routes and injected Gateway calls without
running a model. Native phone tests pair the real app normally with an isolated
helper/Gateway fixture, then navigate, read history and submit test messages.
Simulator screenshots must be inspected before calling UI verification complete.
Python tests exercise real SQLite reopen, competing helpers, child-process
crash after dispatch, corruption and write failure. Native tests include app
termination/helper reconstruction, explicit review without a second send,
and light/dark system appearance against Ceviz's fixed dark palette. Current
test results and native proof are recorded in `STATUS.md`; test definitions
alone are not evidence that a candidate passed.
Live production sends, physical Watch continuation and mixed-version device
delivery remain separate acceptance checks.
