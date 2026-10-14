# Ceviz Helper 2026.10.13 Beta 2

Tag: `ceviz-helper-v2026.10.13-beta.2`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **Speech recognition falls back to the CPU when the GPU goes away.** On 11 October WSL lost GPU
  access ("GPU access blocked by the operating system"). The Whisper model loaded on CUDA at start
  then failed on every command, and every command came back as unclear speech. Now a CUDA model
  that fails while transcribing is dropped and the same recording is transcribed again on the CPU,
  so that command still gets its text. The helper stays on the CPU until the service restarts,
  because a dead CUDA context fails every later call; restarting WSL (`wsl --shutdown`) brings the
  GPU back.
- **Local Whisper errors are no longer swallowed.** In the default `auto` mode a local failure used
  to fall through silently to the OpenAI path; without an OpenAI key the job only said that no
  transcript was produced. The failure is now logged, and the job's error names it (for example
  `local Whisper error: CUDA failed …`). A CUDA start failure during warm-up is logged too, instead
  of quietly choosing the CPU.
- Silence still reports an empty transcript, as before.

Everything in [2026.10.13 Beta 1](release-notes-helper-2026.10.13-beta.1.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag.

Python dependencies are unchanged, so the automatic update path applies. Installing or updating the
helper changes no OpenClaw Gateway settings, model selections, fallback lists or permissions.

## Validation

- 296 Python tests passed (12 platform-specific skips). Six new tests cover the CPU fallback after a
  CUDA failure mid-transcription, a CPU failure reaching the caller, the logged warm-up failure, and
  the error text in `auto` and `local` modes; five of them fail on the previous code. They use
  stand-ins for faster-whisper, so they also run where it is not installed.
- On a live WSL2 install, the fixed code transcribed an 11-second sample on CUDA in 1.1 seconds.
  The CPU fallback itself was not triggered live, since there is no safe way to break the GPU
  context on purpose.
- Not covered: macOS helpers.
