# Ceviz Helper 2026.9.30 Beta 1

Tag: `ceviz-helper-v2026.9.30-beta.1`.
Compatible existing app: **Ceviz 2026.6.5 (1789005793)** on iPhone and Apple Watch.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **Pusula model routing.**
  - Every turn runs on the OpenClaw agent's own model and its configured fallback chain. Ceviz
    sends no `--model` for normal turns, so a provider outage can still fall back.
  - When the conversation shows a miss, Ceviz climbs a two-step ladder. A miss is a correction
    ("anlamadın", "kastetmedim", "that's not what I meant"…), a repeat of a request that did not
    finish, or a second miss inside 15 minutes.
  - Escalation uses the best configured "balanced" frontier model OpenClaw reports for the agent
    (for example the newest Sonnet on a Claude subscription): thinking medium on the first step,
    high on the second.
  - Only models you already configured in OpenClaw are used; merely available models are never
    chosen. With no suitable model, the turn stays on the agent default.
- **Resilient pinned turns.** If an escalated turn fails before running any tool, Ceviz retries it
  once without the pin, so your fallback chain applies. This covers Claude CLI token refresh, auth,
  overload and rate limits.
- **Optional light tier and local decisions.**
  - Pusula can ask a local System One server (such as Kev) whether a fresh turn is small talk:
    set `decision_endpoint`, `light_instructions`, `light_threshold` and a `low_local` group in
    `pusula.json`.
  - It is off by default, and no hosted decision service is contacted unless you configure one.
- **Speech recognition.** Whisper is biased toward names such as Claude Code, Codex, OpenClaw and
  Ceviz (`WATCH_CEVIZ_WHISPER_HOTWORDS` overrides or disables the list).
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

Python dependencies are unchanged, so the automatic update path applies. No OpenClaw Gateway
settings, model selections, fallback lists or permissions are changed by installing or updating
the helper; routing only chooses among models you already configured.

## Validation

- 263 Python tests passed (12 platform-specific skips) on the release branch.
- On a live WSL2 install, normal turns ran unpinned on the agent default. Pusula discovered the
  configured Claude Sonnet 5 and routed a correction to it with medium thinking, and a repeated
  miss with high thinking. The light tier was exercised earlier through a local Kev-0.8B server.
- Through the same helper and agent, Claude Sonnet 5 and Claude Haiku 4.5 each built, started,
  health-checked and stopped a small HTTP bridge from scratch under `/tmp`.
- An existing install with more than 50 jobs updated and recovered with the fixed updater; job
  history was preserved.
- Not covered: physical Watch microphone quality, macOS helpers, and non-Claude frontier providers
  in live runs. Discovery for OpenAI, Google and xAI is covered by unit tests only.
