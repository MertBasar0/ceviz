# Ceviz Helper 2026.9.12 Beta 1

Tag: `ceviz-helper-v2026.9.12-beta.1`.
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

## Validation

- [Code-source checks](https://github.com/MertBasar0/ceviz/actions/runs/34706593707)
  passed on Ubuntu and macOS: 180 Python tests and 3 notification-relay tests
  per host, plus installer/Doctor/updater syntax. Windows discovered the same
  180 Python tests: 162 passed and 18 platform/permission cases were skipped.
- A disposable WSL user ran the real installer, dependency installation,
  systemd service and backend HTTP flow. Actual old `040d1df` source upgraded
  with existing jobs/terminal SQLite records preserved; a separate cohort with
  no conversation journal also upgraded without creating one.
- Wrong installation, missing maintenance consent, existing-installation
  reruns and active/unconfirmed delivery refused before service mutation.
  Authentication, capabilities, sessions/history, idempotent update and
  delivery-identity replay after a real service restart were checked.
- An intentionally broken startup rolled back automatically. A real SIGKILL
  after activation left a pending receipt; explicit recovery restored previous
  code without rewinding state. Whole-bundle tampering, path escape and foreign
  virtualenv regressions also passed after independent review.
- A second fresh application environment/token on the same disposable OS user
  passed installation and restart, including a CLI PATH with spaces, percent
  and quote characters. This is not a second clean operating system. Gateway
  responses were synthetic; no personal Gateway, Whisper model-quality or
  physical-device behavior was exercised by these deployment tests.

The iPhone/Watch app and backend runtime are unchanged from the previously
device-tested `c3404f1` source. The updater SHA-256 is
`dc4b03531ecf6c92dfbf9cba755bcf70133e89ad006c55e170aad797ee62162e`.
The published GitHub release identifies its exact source commit; latest
publication/download readback is recorded in [STATUS.md](../STATUS.md).

The helper-check workflow contains no Apple credentials, signing, TestFlight
upload or production service operation. Its macOS unit-test job is not macOS
automatic-update support.
