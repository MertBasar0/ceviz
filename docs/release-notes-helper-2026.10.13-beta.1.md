# Ceviz Helper 2026.10.13 Beta 1

Tag: `ceviz-helper-v2026.10.13-beta.1`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

- **Push notifications reach the relay on its own domain.** The helper used to send result
  notifications through `ceviz-push-relay.mertbasar30.workers.dev`. Türk Telekom and Vodafone reset
  TLS connections to `*.workers.dev` addresses, so on those networks no notification was delivered
  and registration failed. The same relay now answers at `https://push.cevizrelay.dev`, which is the
  new default. `WATCH_CEVIZ_PUSH_RELAY_URL` still points the helper at a self-hosted relay.
- **Failed notifications back off and old jobs are not retried.** A notification that cannot be
  delivered is retried after 30 seconds, then with doubling delays up to 15 minutes, and a job older
  than 3 hours is never attempted. Before, an unreachable relay was retried every 5 seconds for
  every finished job; one install logged 3,614 failures in two days.
- **Router plugins are loaded when the service starts.** A plugin such as
  [Pusula](https://github.com/MertBasar0/ceviz-pusula) can now prepare (for example load its local
  decision model) before the first command. Before, the plugin was created on the first command,
  and a slow start made that command run on the agent default. Routing still stays off unless
  `WATCH_CEVIZ_ROUTER` names an installed plugin.

Everything in [2026.10.1 Beta 2](release-notes-helper-2026.10.1-beta.2.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag.

Python dependencies are unchanged, so the automatic update path applies. Installing or updating the
helper changes no OpenClaw Gateway settings, model selections, fallback lists or permissions.
A service drop-in that sets `WATCH_CEVIZ_PUSH_RELAY_URL` keeps overriding the new default; remove
it if it only pointed at the old `workers.dev` address.

## Validation

- 290 Python tests passed (12 platform-specific skips), including a check that the default relay is
  not on `workers.dev`, and preload tests for a slow plugin: a command that arrives while the plugin
  is still being created waits for it, and the plugin is created once.
- On a live WSL2 install on a Vodafone line, `push.cevizrelay.dev/healthz` answered over a valid TLS
  connection while the `workers.dev` address was reset. With the relay set to the new domain,
  registration succeeded and two result notifications reached the iPhone and the Watch.
- Not covered: macOS helpers, and networks outside Türkiye.
