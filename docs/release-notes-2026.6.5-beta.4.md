# Ceviz 2026.6.5 Beta 4 — Reliable wrist flow

Release candidate. Build, external TestFlight availability, and device checks
must be recorded in `STATUS.md` before this is described as distributed.

Signed candidate **2026.6.5 (1788570416)** has been uploaded to Apple for internal
device validation. The latest upload audit reports **PROCESSING**, without
errors or warnings; installable internal access is not yet confirmed. External
Beta assignment is held until the real Watch-face capture route is checked.

## What's new

- A Ceviz Voice complication opens the Watch directly into a capture-ready
  screen. It never starts the microphone automatically. Supports circular,
  rectangular, inline, and corner complication families on compatible faces.
- Larger, glanceable Watch result cards show the reported outcome and one
  phone continuation action. Full reports and decisions stay on iPhone.
- Completed execution is separated from its reported outcome: completed,
  blocked, needs your input, or result ready when the outcome is unknown.
  The same interpretation drives job lists, report headers, and result haptics.
- The microphone becomes available after the backend acknowledges a request;
  earlier jobs remain in Jobs. Capture displays the actual remaining time,
  and microphone permission cancellation cannot start a recording later.
- Every Watch recording enters the existing persisted queue before delivery.
  Retries retain command identity. A late receipt for the same retried command
  is accepted; an older job cannot replace a newer focused job.
- Pausing foreground result checks no longer forgets an accepted job. Reopen
  or reconnect to check again. Expired, unconfirmed queued audio is not resent
  after 15 minutes and now has a visible explanation.
- Phone reports refresh while working and on foreground; a refresh failure
  keeps an already received result visible. Late refreshes do not reopen a
  report the user has left.
- Notification payloads carry the same reported outcome. Unknown outcomes
  and errors no longer inherit a success summary. Terminal alerts use APNs;
  explicit Watch-to-phone handoff nudges remain separate.

## Add the Watch-face button

On Apple Watch, edit a compatible watch face, open **Complications**, and choose
**Ceviz Voice**. Tap it, then tap the microphone to record. Placement choices
depend on the watch face. Install/update the Watch app as well as the iPhone app.

## Outcome and compatibility

`status` describes execution lifecycle. Additive `outcome` is
`done`, `blocked`, `needs_input`, or `unknown`. It describes an agent-reported
result, not independently verified external effects. Old backend payloads and
stored jobs remain readable; missing outcome stays neutral rather than being
invented as success. Update the Ceviz backend and notification relay for full
outcome-aware notifications. No OpenClaw gateway/model configuration change is
required by this release.

The Watch focuses one result at a time; Jobs is the full backend-owned list.
An interrupted connection does not prove the remote task failed or was
cancelled. Check the recorded result before resubmitting a consequential task.

## Device acceptance checks (not yet claimed as passed)

1. Add the complication, cold-open it, and open it from the Jobs tab. It must
   land on capture-ready without recording or claiming the gateway is ready.
2. Grant/deny microphone permission; cancel a pending prompt. A cancelled
   capture must not start later. Confirm the 15-second recording limit.
3. Run a harmless short task, lower the wrist, and tap its completion
   notification. The main card and both job lists must agree on the outcome.
4. Run a task requiring user input. It must not receive a success label/haptic;
   inspect the next step on iPhone.
5. Send another request after acknowledgement. Let the older task finish
   later; it must remain accessible in Jobs without overwriting the newer one.
6. Disconnect/reconnect and background/reopen during a longer task. A polling
   pause must not erase its receipt or cause automatic duplicate execution.
7. Check EN/TR, the smallest available Watch display, larger text, and
   VoiceOver. Simulator launch pictures do not prove physical complication,
   microphone, delivery, or haptic behavior.

## Validation and follow-ups

Required gates: Python endpoint/contract tests, real relay-handler tests with
synthetic keys, shared Swift state/upgrade tests, Watch focus/retry tests,
secretless signing-lane tests, locally signed simulator/embedded-widget build,
and distribution-signed IPA.
Record executed gates and exact build identity in `STATUS.md`.

The generic external `simctl openurl` probe currently fails with LaunchServices
error 115 even with matching runtime, installed URL metadata, and verified local
signatures. This is unresolved and is not the actual WidgetKit tap path. Normal
CI keeps the strict probe. An explicitly selected internal device-check candidate
may retain that specific failure as diagnostic evidence while producing a signed
TestFlight build for physical validation. Other native smoke failures still stop
the build. Neither a successful generic URL probe nor navigation unit tests prove
WidgetKit delivery. Keep external Beta distribution pending the device check.

Next product slice: explicit follow-up/new-task context, personal quick actions,
and in-app Doctor guidance. Existing backend file-write concurrency and
per-device notification retry behavior need a separate persistence/delivery
review; this release does not claim guaranteed delivery or exactly-once remote
effects. OpenClaw configuration and the user's live gateway are out of scope.
