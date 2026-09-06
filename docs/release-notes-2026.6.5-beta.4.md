# Ceviz 2026.6.5 Beta 4 — Reliable wrist flow

Internal release candidate. External distribution and physical device acceptance
remain pending; exact evidence is recorded in `STATUS.md`.

Signed candidate **2026.6.5 (1788715054)** is available to the **Mert** internal
TestFlight group. Apple reports **VALID / internal IN_BETA_TESTING**; upload
processing is complete without errors or warnings. External state is
**READY_FOR_BETA_SUBMISSION**, with no **Beta** group assignment. External Beta
distribution is held for the capture reliability and layout checks below.

## Capture correction — shipped to internal TestFlight

The tester reported a successful physical complication-to-command flow, followed
by a premature “recording too long” error and unreadable/clipped capture controls.
The source of that message was a serialized-message byte limit, not the recording
duration. The rejected audio file is unavailable, so its actual encoding/size has
not been measured. Build **1788570416** does not contain this correction.

The approved correction separates recording completion from rendering, preserves
elapsed time at stop, keeps failed deliveries queued, and uses native file transfer
for requests above the interactive message budget. Matching receipts, connection
reset boundaries, and request expiry must be checked on both devices. A reserved
action area and a dedicated recording state replace the crowded microphone screen.

All five native simulator scenarios passed in
[validation run 34021753131](https://github.com/MertBasar0/ceviz/actions/runs/34021753131)
at source `4ca09062de9dfa7c5f4cf4aae71bf29abe267975`: 40 mm and 49 mm,
English/Turkish, normal and actual maximum system text, verified restoration,
and manual/automatic recording completion. Screenshots were also inspected.
The two recorded files measured **9.724 seconds** and **14.908 seconds**;
the screen showed a saved, queued request after each finish. This does not
independently verify persisted queue contents or physical delivery.
This validation did not produce or upload a new TestFlight
build. Earlier intermittent simulator start/termination failures did not recur
in this run; their root causes are not claimed as fixed.

The subsequent signed-candidate attempt at documentation-only successor
`f29baf52eca5e3f73af90c4f640df47a690667cc`,
[run 34029580846](https://github.com/MertBasar0/ceviz/actions/runs/34029580846),
was stopped by the last scenario's real Settings navigation check: its first
49 mm list drag made no observed progress, before changing text size. The
preceding four scenarios passed, with actual files of **9.468 / 14.908 seconds**;
manual finish showed Queued and automatic finish showed a demo result, not a
real gateway acknowledgement. Signing and upload were skipped, no IPA was
produced, and that attempt did not change TestFlight. The same drag worked in the earlier
green run; why it did not move Settings in this attempt remains unverified.
No retry or weakened test gate was used to obtain a distribution result.

Subsequent native investigation also captured an actual synthetic-touch
cancellation in [run 34043752041](https://github.com/MertBasar0/ceviz/actions/runs/34043752041):
the Apple test input service removed its virtual digitizer while a contact was
still down, and BackBoard cancelled that contact in Ceviz's window. XCTest's
completion notification did not mean the button action ran. No recording or
hit-target behavior was changed to compensate. The supported Xcode 26.6
comparison kept the same five scenarios and audio thresholds. Apple does not
document this specific bug as fixed; earlier intermittent failures are not
all claimed resolved.

The complete signed-candidate pipeline subsequently passed in
[run 34046167349](https://github.com/MertBasar0/ceviz/actions/runs/34046167349),
source `e156d252b25d57d9638edc820596718bc903ad70`, Xcode **26.6 / 17F113**,
iOS/watchOS **26.5**. All five native scenarios passed, including actual positive
Crown navigation, maximum system text, and **9/9** restoration on each size.
Recorded files measured **9.916 seconds / 25,204 bytes** and
**14.908 seconds / 25,516 bytes**, AAC, 16 kHz, mono. Manual finish showed
Queued; automatic finish showed the app's demo Completed result, not a gateway
acknowledgement. Recording controls were visually checked on 40 mm and 49 mm.
Individual image reinspection confirmed the manual Queued result and the
initial ready-screen microphone. Actual Default/max/restored screens and
measurements provide the layout proof; physical acceptance remains separate.

The signed package contains matching iPhone, Watch and widget versions.
Apple accepted **1788715054** as **VALID**, upload **COMPLETE** without errors
or warnings, internal **IN_BETA_TESTING**, assigned only to **Mert**.
No external Beta assignment, main-branch update, or live service change was made.
EN/TR TestFlight test notes are empty; this document records the release changes.

Before external distribution, verify both updated apps on a paired real device:
manual send and automatic 15-second finish; no premature size error; readable
counter and reachable Delete/Send with larger text; retained audio and correct
receipt after a connection interruption. Simulator UI and pure state tests are
not proof of microphone quality, physical file transfer, or remote exactly-once
effects. Executed checks and the next exact build belong in `STATUS.md`.

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
