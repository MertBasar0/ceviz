# Ceviz Helper 2026.10.17 Beta 1

Tag: `ceviz-helper-v2026.10.17-beta.1`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **The updater no longer stops when the new helper writes its own state at start.** Updating a
  live install to 2026.10.13 Beta 2 stopped with "Ceviz state changed during maintenance", and
  `--recover` would have refused for the same reason. No job, conversation or pairing state had
  changed: the new helper loads router plugins at start, and Pusula refreshed its model-list
  cache, which was older than 6 hours, while the updater was still verifying.

  The updater now compares the state files byte for byte only while no helper runs (before and
  after the stop). Once the new helper has started, it owns its state and may write it at once
  (push receipts, plugin caches). Job identities, authentication, capabilities and conversations
  are still checked through the helper's API, and the service settings must still match.
  Recovery keeps refusing changed state, so the previous code never runs on state a newer helper
  wrote.

Everything in [2026.10.13 Beta 2](release-notes-helper-2026.10.13-beta.2.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag. The updater itself changed in this release, so its SHA-256
is new.

Python dependencies are unchanged, so the automatic update path applies. Installing or updating the
helper changes no OpenClaw Gateway settings, model selections, fallback lists or permissions.

## Validation

- 297 Python tests passed (12 platform-specific skips). A new test starts the new helper and writes
  a plugin cache into the state directory, as Pusula did; the previous updater fails it with the
  same "state changed during maintenance" error seen live, and this updater completes.
- The existing test that recovery refuses state changed after activation still passes.
