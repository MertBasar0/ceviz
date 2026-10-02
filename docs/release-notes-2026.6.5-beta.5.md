# Ceviz 2026.6.5 Beta 5 — Delivery recovery

External TestFlight beta candidate. Exact release and validation evidence is
recorded in `STATUS.md`.

Signed build **2026.6.5 (1790966589)** was built from `e167545` in
[run 37040464700](https://github.com/MertBasar0/ceviz/actions/runs/37040464700)
and uploaded on 2 October. Apple reports **VALID** and **APP_STORE_ELIGIBLE**;
the **Mert** internal group is **IN_BETA_TESTING**. External distribution to the
**Beta** group needs Apple beta review; this note is updated when it is approved.
The existing [TestFlight invitation](https://testflight.apple.com/join/nEdn2Np2)
does not change.

## Compatibility

Update both the iPhone and Watch apps, and update the helper to
[`ceviz-helper-v2026.10.1-beta.2`](https://github.com/MertBasar0/ceviz/releases/tag/ceviz-helper-v2026.10.1-beta.2)
with the [existing-installation update guide](../deploy/README.md#update-existing-installation).
An older helper cannot confirm deliveries; the app asks for an update before
sending. No OpenClaw Gateway, model or permission change is required.

## What's new

Compared with the previous external Beta, **1789005793** (source `c3404f1`),
the app adds the 13 September delivery-recovery work:

- **Unconfirmed delivery is visible and never resent automatically.** When the
  Watch cannot confirm that a recording reached the helper, it says so and offers
  **Check delivery**. The phone first asks the helper about the same delivery
  identity; an uncertain record never authorizes an automatic resend.
- **A new recording while an earlier one is unconfirmed.** It can be sent; the
  earlier recording is not resent. Unconfirmed audio still expires after
  15 minutes.
- **Watch Jobs states.** Loading, refreshing and error states, newest jobs first,
  and the last received jobs stay visible when a refresh fails. The phone sends a
  smaller, bounded summary list.
- **Refresh Connection.** Refreshing the same connection on iPhone keeps recordings
  waiting on the Watch; only a real pairing change clears them.
- **Native ownership fixes.** Connection changes cancel the current and previous
  sessions together, and task creation/reset can no longer carry a command from an
  old connection into a new one.

The delivery records on the phone and helper hold only identity, target and
state; they never contain audio, transcripts or access tokens.

## Device checks

- On **1789855234** (same app code, internal-only build), the owner reported four
  checks without problems: a second recording without reopening the app, the
  15-second automatic finish, opening from the complication, and recovery after
  an internet drop.
- On **1790966589** on 2 October, the owner repeated a short internal test. One
  observation: a result notification arrived while the Watch Jobs list still
  showed the job as running; the result summary was already on the capture
  screen, and the list caught up later. This is listed as a known issue below.

These are reported device checks, not independent observation of every scenario.

## Validation

The signed run passed the strict (non-candidate) native suite: Watch launch and
capture-link contract, all five capture scenarios on 40 mm and 49 mm (English and
Turkish, normal and larger text, manual and automatic finish) and the iPhone
conversation UI. Its first attempt failed only in an iPhone UI step where tapping
**Earlier** did not show older messages; that job was re-run and passed with no
code change.

Simulator gates changed on 2 October, in tests only:

- watchOS simulators cannot route a custom URL scheme to a third-party app, so the
  launch check verifies the capture link's contract (complication URL, route test,
  installed URL registration) instead of requiring `simctl openurl` to succeed.
- The finish scenario runs with the paired iPhone simulator shut down, so the
  offline queue path is deterministic.
- A start tap the simulator never delivers is retried once, only while no capture
  has begun; each retry is recorded as evidence.

Details and run links are in `STATUS.md`. Simulator tests do not prove microphone
quality, physical file transfer or remote exactly-once effects.

## Known issue

After a result notification, the Watch Jobs list can show that job as running for
a while before it refreshes. The result itself is not lost. Updating the list when
the result arrives is the next planned fix.
