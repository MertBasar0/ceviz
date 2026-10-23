# Ceviz Helper 2026.10.24 Beta 1

Tag: `ceviz-helper-v2026.10.24-beta.1`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
Answer buttons need the next TestFlight build; older builds keep working without them.
This is a helper-source release, not a new TestFlight binary or app version.

## Included behavior

- **Answer choices for a question the agent asks.** When the agent needs the user to pick one
  of a few answers (outcome `needs_input`), it may now return 2–4 short `choices`. The helper
  keeps a complete set of valid answers (each at most 60 characters, all different) or none: a
  set with one dropped answer would misstate the question. Kept answers are listed among the
  job's `next_actions` as kind `choice` (`choice-1`, …). A client sends
  `intent: choose_option` with `continue_job_id` and the answer's `next_action_id`; the helper
  takes the answer text from the stored job, never from the client, and tells the agent the user
  chose that answer. The same answer to the same question returns its first job, so a retry
  after a lost Watch-to-phone reply starts no second job. The helper's
  `/api/v1/capabilities` adds `choice_reply_v1` (the release manifest's compatibility list, which
  the updater checks, is unchanged). Live check on NVIDIA Nemotron 3 Ultra: a request to choose dinner returned
  `needs_input` with three valid answers; "17 × 23" returned `done` and no answers.
- **An empty iPhone transcript no longer asks for an app update.** With speech on the iPhone,
  three of nine commands on 23 October arrived with no text and an empty reason, and the helper
  told the user to update the iPhone app, which was current. Only an app that predates phone
  transcription omits the field; an empty one now reads "the iPhone heard no words in the
  recording". Why the recognizer heard nothing in those three is not known yet.

Everything in [2026.10.20 Beta 3](release-notes-helper-2026.10.20-beta.3.md) is included.

## Compatibility

Older apps show answer actions in the iPhone report as plain rows that do nothing; they cannot
send `choose_option`. Apps that support answers check `choice_reply_v1` first and ask for a
helper update without it.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag. The updater is unchanged since 2026.10.17 Beta 1 (same
SHA-256). Python dependencies are unchanged, so the automatic update path applies.

## Validation

- Exact-source CI: helper contracts on Ubuntu and macOS (350 Python tests) and the Windows WSL
  lifetime boundaries. New tests: answers are kept only as a complete valid set and only for a
  question; answer actions belong only to a finished question; `choose_option` sends the stored
  answer once per question and answer and is refused for answers the job does not offer; an
  empty phone transcript reason is not read as an old app.
- Native Swift contracts on macOS for the app side of answers (command encoding, capability,
  Watch job list, spoken answers).
