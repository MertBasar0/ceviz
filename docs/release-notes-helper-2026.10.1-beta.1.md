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
