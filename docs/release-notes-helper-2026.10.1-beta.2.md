# Ceviz Helper 2026.10.1 Beta 2

Tag: `ceviz-helper-v2026.10.1-beta.2`.
Compatible existing app: **Ceviz 2026.6.5 (1789005793)** on iPhone and Apple Watch.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **Optional router plugins (contract v1).**
  - The helper can hand the model choice to a separately installed router plugin, such as
    [Pusula](https://github.com/MertBasar0/ceviz-pusula).
  - Routing stays off unless the operator installs a plugin into the helper's environment **and**
    sets `WATCH_CEVIZ_ROUTER` to its name. Without that, nothing changes: commands carry no
    `--model` or `--thinking`, and the OpenClaw agent's model and its fallback chain decide.
  - A plugin that fails to load, raises, times out (`WATCH_CEVIZ_ROUTER_TIMEOUT_MS`, default
    1500 ms) or returns an invalid value is ignored, and the command runs on the agent default.
    Only plain `provider/model` selectors and short thinking levels can reach the command line.
  - A routed command that fails before running any tool is retried once without the pin, so the
    fallback chain still applies.
  - See the [router plugin guide](router-plugins.md) for enabling a plugin and for the contract.
- **Doctor** reports whether model routing is off, enabled, or names a plugin that is not
  installed. It reads only `WATCH_CEVIZ_ROUTER` from the service environment and never prints the
  rest of it.

Everything in [2026.10.1 Beta 1](release-notes-helper-2026.10.1-beta.1.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag.

Python dependencies are unchanged, so the automatic update path applies. Installing or updating the
helper changes no OpenClaw Gateway settings, model selections, fallback lists or permissions, and
does not enable any router plugin. An installed plugin lives in the helper's virtual environment,
which updates reuse, so it survives helper updates.

## Validation

- 277 Python tests passed (12 platform-specific skips). They include contract tests with a real
  installed entry point and a Doctor check that the pairing token never appears in its output.
- On a live WSL2 install, the updater installed this source. With `WATCH_CEVIZ_ROUTER` unset,
  commands carried no model flags. With Pusula 0.1.0 installed and enabled, ordinary turns stayed
  on the agent default and a correction ran on the configured Sonnet model with medium thinking.
- Not covered: physical Watch microphone quality, and macOS helpers.
