# Ceviz Helper 2026.10.19 Beta 1

Tag: `ceviz-helper-v2026.10.19-beta.1`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **Using the computer from the Watch under WSL.** OpenClaw in WSL reaches Linux but not your
  Windows apps and files. `deploy/pc-node.sh` connects Windows to the helper's OpenClaw Gateway as
  a node, and the installer now runs it by default ([guide](../deploy/README.md#using-the-computer-from-the-watch)).
  The helper then tells the agent that the PC is the node `Ceviz PC`, so a command such as "open
  Notepad on my computer" runs in PowerShell on Windows (`exec host=node`).
  - The Gateway mints a single-use, limited setup code (no admin access). It reaches Windows on
    standard input and through a private file that `openclaw connect` deletes. Windows then uses
    its own device token; the Gateway token never leaves WSL.
  - Ceviz keeps its own OpenClaw on Windows at the Gateway's version
    (`%LOCALAPPDATA%\Ceviz\pc-node`, about 500 MB with dependencies), its own OpenClaw profile
    `ceviz-pc`, and its own scheduled task `Ceviz PC Node`. An `OpenClaw Node` task you set up
    yourself is left alone.
  - Commands run on Windows without approval prompts, the same trust as OpenClaw's exec in WSL.
  - Existing installations: run `bash deploy/pc-node.sh` once after this update.
- **Speech recognition: Whisper large-v3 or the iPhone, nothing in between.** In daily use the
  smaller Whisper models misheard too many commands to help. A new installation runs large-v3 when
  it fits the GPU (about 5 GB free) or, without one, when a 16-thread CPU with 16 GB hears an
  11-second sample within 3 seconds. Otherwise it is installed with `WATCH_CEVIZ_STT_ENGINE=phone`
  and downloads no model. Existing installations keep their speech settings.
- **iPhone transcription, helper side.** A helper in phone mode says so (`speech_on_phone` in its
  capabilities) and accepts the iPhone's text with the audio on the versioned command route. Only
  such a helper accepts that text, and it is not part of the command identity. The iPhone side
  (Apple's on-device speech recognition) is in the source but not yet in a TestFlight build; see
  the limitations.
- `deploy/plan.py` shows where Watch commands act on this computer, and reads a service `PATH`
  that contains spaces.

Everything in [2026.10.17 Beta 1](release-notes-helper-2026.10.17-beta.1.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag. The updater is unchanged since 2026.10.17 Beta 1 (same
SHA-256).

Python dependencies are unchanged, so the automatic update path applies. Installing or updating the
helper changes no OpenClaw Gateway settings, model selections, fallback lists or permissions. The
PC node is a paired device on that Gateway; `openclaw devices remove` and removing the
`Ceviz PC Node` task undo it.

## Limitations

- **A phone-mode helper needs an app build that does not exist yet.** With app 1791334823, every
  voice command to such a helper fails with "update the Ceviz iPhone app". Only new installations
  on machines without room for large-v3 are affected.
- OpenClaw 2026.9.6 refuses to install its own node service for a separate state folder or a named
  profile (it compares the node's task name with the profile's gateway task name). Ceviz therefore
  lets OpenClaw only pair and runs the node from its own task.
- The node starts at Windows logon. A Windows account that never signs in has no PC node.

## Validation

- Exact-source CI: helper contracts on Ubuntu and macOS (334 Python tests, 15 platform-specific
  skips; bash 3.2 included) and the Windows WSL lifetime boundaries. 15 Windows PowerShell tests
  run the Windows installer with substituted task, process, npm and node calls.
- The iPhone transcription change compiled in a validation-only app build (iPhone and Watch UI
  checks green, nothing signed or uploaded); Swift delivery contracts cover sending the text only
  to a phone-mode helper and never storing it.
- Live on WSL2 with Windows 11: `Ceviz PC` connected and approved with `system.run` on the helper's
  Gateway (OpenClaw 2026.9.6), `system.which` resolved PowerShell, Notepad and Explorer on Windows,
  and the helper restarted with the node name. The first attempts found the OpenClaw service
  refusal above, an `OpenClaw Node` task from an elevated terminal that only an administrator
  could remove, and a broken hidden-launcher line; all are fixed and covered by tests.
- Not yet validated: a Watch command carried out on Windows end to end (this release makes it
  possible), iPhone transcription on a device, and the installer's phone path on a machine without
  a GPU.
