# Ceviz Helper 2026.10.20 Beta 1

Tag: `ceviz-helper-v2026.10.20-beta.1`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**; the
speech hints below need an app build newer than **1792443198**.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

These come from the first tests of transcription on the iPhone (20 October).

- **Comparing iPhone and Whisper on the same audio.** With `WATCH_CEVIZ_STT_COMPARE=whisper`, a
  helper in phone mode also transcribes each capture with local Whisper, in the background after
  the job has started, and keeps that text on the job as `stt_compare`. The iPhone's text is still
  the one used. The first comparison used different sentences for each engine, so it showed only
  a trend.
- **Proper-noun hints for the iPhone.** A phone-mode helper sends Whisper's hotwords
  (`WATCH_CEVIZ_WHISPER_HOTWORDS`) as `speech_hints`. The iPhone app passes them to Apple's
  recognizer as contextual strings. The dictation model had heard "RustDesk" as "rast TESS" and
  "Ras desk".
- **A reply cut off at the model's output limit no longer counts as done.** OpenClaw ends such a
  reply with "Reply truncated at the model's output token limit". Ceviz now marks the job blocked,
  shows "the reply was cut off; the outcome is unknown" on the Watch, and asks for a new command.
  Live, a model stopped after "The" and the Watch showed that fragment as the result.

Everything in [2026.10.19 Beta 1](release-notes-helper-2026.10.19-beta.1.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag. The updater is unchanged since 2026.10.17 Beta 1 (same
SHA-256). Python dependencies are unchanged, so the automatic update path applies.

The comparison is off unless `WATCH_CEVIZ_STT_COMPARE=whisper` is set, and it only runs in phone
mode. While on, it loads Whisper large-v3 on this machine the first time a command arrives.

## Validation

- Exact-source CI: helper contracts on Ubuntu and macOS (337 Python tests) and the Windows WSL
  lifetime boundaries. New tests: the comparison runs after the command is accepted and never
  delays it; hints are sent only in phone mode; a cut reply is blocked in Turkish and English.
- Swift delivery contracts: the helper's hints reach the recognizer only for a phone-mode helper. A
  validation-only app build (iPhone and Watch UI checks) compiled the `AnalysisContext` hints.
- Not yet validated on a device: whether the hints improve the dictation model's proper nouns.
