# Ceviz 2026.6.5 Beta 6 — Jobs list and notifications

External TestFlight beta. Exact release and validation evidence is recorded in
`STATUS.md`.

Signed build **2026.6.5 (1791334823)** was built from `ae1bfd0` in
[run 37550617824](https://github.com/MertBasar0/ceviz/actions/runs/37550617824)
and uploaded on 7 October. It is available to the **Mert** internal and **Beta**
external TestFlight groups. Apple reports **VALID**, beta review **APPROVED**, and
both internal and external **IN_BETA_TESTING**. Automatic tester notification is
enabled; the existing [TestFlight invitation](https://testflight.apple.com/join/nEdn2Np2)
is unchanged. EN/TR test notes were written for this build and read back exactly.

## Compatibility

Update both the iPhone and Watch apps, and update the helper to
[`ceviz-helper-v2026.10.13-beta.1`](https://github.com/MertBasar0/ceviz/releases/tag/ceviz-helper-v2026.10.13-beta.1)
with the [existing-installation update guide](../deploy/README.md#update-existing-installation).
The app–helper contract is unchanged, so the app also works with
`ceviz-helper-v2026.10.1-beta.2`, but that helper cannot deliver result
notifications on networks that block its relay address (seen on Türk Telekom and
Vodafone). No OpenClaw Gateway, model or permission change is required.

## What's new

Compared with the previous external Beta, **1790966589** (source `e167545`), the
app changes only in the Watch Jobs list:

- **A finished job shows its result at once.** When a result arrives, from a
  notification or on the capture screen, the Jobs list marks that job with its
  final state. Before, it could show the job as running until the next refresh.
  The Watch keeps the final state until the helper's list reports it too, so an
  older list cannot move the job back to running.
- **A refresh is no longer lost.** A refresh asked for while another one was still
  running used to be dropped; it now runs when the first one finishes.

## Helper changes released with this build

[`ceviz-helper-v2026.10.13-beta.1`](https://github.com/MertBasar0/ceviz/releases/tag/ceviz-helper-v2026.10.13-beta.1)
sends notifications through `push.cevizrelay.dev` instead of a `workers.dev`
address, backs off failed deliveries instead of retrying every 5 seconds, and
loads router plugins when the service starts. See its
[release notes](release-notes-helper-2026.10.13-beta.1.md).

## Device checks

- On **1791334823** on 11 October, the owner sent commands from the Watch and
  opened the Jobs list as the results arrived; each job showed its result state
  immediately.
- Notifications did not arrive in that test because the owner's network blocked
  the old relay address. On 13 October, with the helper using
  `push.cevizrelay.dev`, the owner received result notifications on the iPhone and
  the Watch.

These are reported device checks, not independent observation of every scenario.

## Validation

The signed run passed the strict (non-candidate) native suite on its first
attempt: Watch launch and capture-link contract, all five capture scenarios on
40 mm and 49 mm (English and Turkish, normal and larger text, manual and automatic
finish) and the iPhone conversation UI. A new Swift test covers the Jobs list
keeping a confirmed final state against an older list.

Simulator tests do not prove microphone quality, physical file transfer or remote
exactly-once effects.

## Known issues

None new in the app. The helper's speech recognition can fail on every command if
WSL loses GPU access (11 October); `wsl --shutdown` restores it, and a code fix
that surfaces the error and falls back to the CPU is planned.
