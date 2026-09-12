# Ceviz Helper 2026.9.12 Beta 1

Release preparation — final source identity, clean-install/update proof and
publication are pending. Do not describe the helper tag as available until its
published release has been verified.

Intended tag: `ceviz-helper-v2026.9.12-beta.1`.
Compatible existing app: **Ceviz 2026.6.5 (1789005793)** on iPhone and Apple Watch.
This is a helper-source release, not a new TestFlight binary or app version.

## Included behavior

- Publishes the matching backend for phone Conversations: assistant selection,
  search, history and guarded text delivery to the chosen OpenClaw session.
- Keeps queued, finished and unconfirmed delivery distinct. Helper SQLite
  metadata retains delivery identity across restart without keeping message
  text or credentials in that journal.
- Separates a Watch follow-up from explicit suggestion approval on iPhone.
- Adds an existing-installation updater for Linux/WSL systemd user services.
  It checks ownership and idle state, stages a complete source snapshot, and
  switches one launcher before restarting only Ceviz.
- Preserves pairing, service settings, dependencies, network configuration and
  runtime state. Interrupted activation has code-only recovery; conversation
  and job records are never rewound or cleared by that recovery.

## Installation and safety

Use the [new-installation guide](../README.md#install-the-backend) only on a
machine without an existing Ceviz installation. Existing users should follow
the [update and recovery guide](../deploy/README.md#update-existing-installation),
starting with `--check` and a no-new-requests maintenance window.

Automatic updating refuses macOS/non-systemd setups, custom runtime changes,
changed Python dependencies, and active or unconfirmed work. These cases need
assisted updating, not an installer rerun or deletion of delivery records.
Source commit identity and per-file verification are not a claim that GitHub
release immutability has been enabled.

The updater's post-start checks are read-only. They do not prove microphone
quality, physical Watch delivery, or exactly-once effects in an external system.
Neither helper publication nor updating changes OpenClaw Gateway settings,
model selection, permissions, or the existing TestFlight build.

## Validation status

Pending before publication:

- Final-source Python regression suite and installer/Doctor/updater syntax
  checks on the supported validation hosts.
- Isolated real-service installation/update/recovery proof, including preserved
  settings/state and refusal paths. Synthetic Gateway fixtures are not a claim
  that a real user command was executed.
- Independent review, exact source/tag identity and public download/readback.

The helper-check workflow contains no Apple credentials, signing, TestFlight
upload or production service operation. Its macOS unit-test job is not macOS
automatic-update support.
