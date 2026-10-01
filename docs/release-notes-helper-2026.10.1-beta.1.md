# Ceviz Helper 2026.10.1 Beta 1

Tag: `ceviz-helper-v2026.10.1-beta.1`.
Compatible existing app: **Ceviz 2026.6.5 (1789005793)** on iPhone and Apple Watch.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **Model choice stays with OpenClaw.** Ceviz sends every command without `--model` or
  `--thinking`. The agent's own model runs, and the fallback chain configured in OpenClaw handles
  provider outages. Ceviz itself never switches models.
- **Speech recognition.** Whisper is biased toward names such as Claude Code, Codex, OpenClaw and
  Ceviz. `WATCH_CEVIZ_WHISPER_HOTWORDS` overrides the list, and an empty value disables it.
- **Safer watch and phone text.**
  - The agent is told never to write tokens or passwords.
  - Recognizable secret shapes are masked before text reaches the watch, the push relay or
    `jobs.json`.
  - Failure summaries no longer show raw CLI output.
  - The agent no longer claims a specific model identity it was not told.
- **Updater.** A helper that had served more than 50 jobs no longer stops mid-update or during
  `--recover`. Jobs trimmed from history are accepted; new or changed jobs are still refused.

## Also included since 2026.9.12 Beta 1

These helper changes come from the 13–20 September reliability work on the development branch.
They were in this release from the start but were not listed when it was first published:

- **HTTP intake.**
  - The helper owns connection, header and body limits and bounded concurrency, so a
    half-finished upload no longer blocks health or job queries.
  - Concurrent admission of the same audio or target and push-registration merging were fixed
    at the same boundary (`backend/watch_admission.py`).
- **Windows/WSL lifetime.**
  - On WSL, a fresh install now also installs the independent **Ceviz WSL Lifetime** Windows
    scheduled task, which keeps the selected distribution running. The task tracks that
    distribution's WSL client directly, not a PowerShell wrapper.
  - The Windows Tailscale route is published only after the authenticated backend answers on
    Windows `127.0.0.1`.
  - The LAN relay installer requires `-Distro`, and distribution names are passed without
    literal quotes.
  - An explicit, limited non-interactive (S4U) task mode was added.
  - Doctor reports whether the lifetime task and the selected distribution are running.
  - These scripts remain a repair candidate until autostart after a Windows restart is proven.

The matching iPhone and Watch changes from the same work (delivery recovery, connection refresh
and native task ownership) ship in app builds, not in this helper. The external TestFlight build
is unchanged.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag, which includes the job-history fix above.

Python dependencies are unchanged, so the automatic update path applies. Installing or updating the
helper changes no OpenClaw Gateway settings, model selections, fallback lists or permissions.

## Validation

- 263 Python tests passed (12 platform-specific skips) on the release branch.
- An existing install with more than 50 jobs updated and recovered with the fixed updater; job
  history was preserved.
- Not covered: physical Watch microphone quality for the new speech hints, and macOS helpers.
