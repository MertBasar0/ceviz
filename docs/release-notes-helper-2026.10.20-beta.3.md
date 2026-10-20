# Ceviz Helper 2026.10.20 Beta 3

Tag: `ceviz-helper-v2026.10.20-beta.3`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

These come from reviewing the first day of commands on the iPhone's speech recognition
(20 October).

- **A standing thinking level (`WATCH_CEVIZ_THINKING`, opt-in).** OpenClaw keeps the last
  `--thinking` a command sent on the agent's session. That day every Pusula escalation to
  Claude Sonnet failed Claude CLI authentication and was retried unpinned, but its `medium` or
  `high` stayed on the session, so later commands on the agent's own model ran at whatever the
  last escalation chose. With `WATCH_CEVIZ_THINKING=high`, every command a router sets no level
  for, and every unpinned retry, sends `--thinking high`. Measured on NVIDIA Nemotron 3 Ultra in
  fresh sessions: `off` returned no reasoning, `medium` about 2,200 characters of it, `high`
  about 3,400. Unset, Ceviz sends no level of its own, as before.
- **More than one comparison model.** `WATCH_CEVIZ_STT_COMPARE` takes a list: `whisper` is the
  service's own model, `whisper:<model>` another faster-whisper model such as
  `whisper:large-v3-turbo`, loaded once beside it. The first engine's text stays in
  `stt_compare`; further engines' texts are in `stt_compare_more`. As before, the phone's text
  is the one used and the comparison never delays a command.
- **More default hotwords.** On the iPhone, English technical terms in Turkish speech were the
  most frequent misses ("IMAP" heard as "iMac" in five commands, "Node" as "not"). The default
  list, sent to Whisper and as hints to the iPhone, adds IMAP, SMTP, URL, OAuth, API, Node,
  Chrome, Windows and PowerShell. A `WATCH_CEVIZ_WHISPER_HOTWORDS` setting still replaces it.

Everything in [2026.10.20 Beta 2](release-notes-helper-2026.10.20-beta.2.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag. The updater is unchanged since 2026.10.17 Beta 1 (same
SHA-256). Python dependencies are unchanged, so the automatic update path applies.

Choose a `WATCH_CEVIZ_THINKING` level the agent's primary model supports; OpenClaw rejects a run
with an unsupported explicit level. A comparison model is downloaded the first time it runs
(large-v3-turbo: 1.6 GB) and uses GPU memory beside the service's own model; without room it
runs on the CPU.

## Validation

- Exact-source CI: helper contracts on Ubuntu and macOS (346 Python tests) and the Windows WSL
  lifetime boundaries. New tests: the standing level applies only where no router set one and
  replaces a failed pin's level on the retry; comparison engines run in order, are saved one by
  one, and never accept a path or an option as a model name; a failing comparison model is
  dropped without touching the service's own model.
