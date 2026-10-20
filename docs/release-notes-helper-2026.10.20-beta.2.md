# Ceviz Helper 2026.10.20 Beta 2

Tag: `ceviz-helper-v2026.10.20-beta.2`.
Compatible app: **Ceviz 2026.6.5** on iPhone and Apple Watch, tested with build **1791334823**.
Any build that asks for the command capabilities before sending (all builds with command
recovery) triggers the router's `prepare()`.
This is a helper-source release, not a new TestFlight binary or app version. The app–helper
contract (`contracts/`) and the capability list are unchanged.

## Included behavior

These matter only with a router plugin enabled (`WATCH_CEVIZ_ROUTER`), for example
[Pusula](https://github.com/MertBasar0/ceviz-pusula) 0.2.2.

- **Routers get 3 s instead of 1.5 s.** Pusula asks its local decision model two to four
  questions per command. Warm, each takes 0.2 to 0.5 s, but on the first command after the model
  sat idle beside other GPU work they took 1.27 s and 0.98 s, so the 1.5 s timeout ran that
  command on the agent default. `WATCH_CEVIZ_ROUTER_TIMEOUT_MS` still overrides the default.
- **Routers learn the timeout.** The host info passed to a router now includes
  `routing_timeout_ms`, so a router can keep its own work inside it. Pusula 0.2.2 keeps its
  decisions 200 ms under it.
- **Routers hear that a command is coming.** The helper calls a router's optional `prepare()`
  when the iPhone asks for the command capabilities (right before it sends) and again when the
  audio arrives, both before speech recognition. It runs on its own thread and is never waited
  for. With Pusula, this loads a decision model that Ollama no longer holds (for example after the
  GPU was freed for other work): loading took 2.8 to 4.6 s, more than any routing budget. With
  the load starting 1.5 s ahead, the first command's decision questions took 1.6 s.

Everything in [2026.10.20 Beta 1](release-notes-helper-2026.10.20-beta.1.md) is included.

## Installation and safety

New installations follow the [new-installation guide](../README.md#install-the-backend). Existing
users follow the [update and recovery guide](../deploy/README.md#update-existing-installation) with
the updater downloaded from this tag. The updater is unchanged since 2026.10.17 Beta 1 (same
SHA-256). Python dependencies are unchanged, so the automatic update path applies.

Without `WATCH_CEVIZ_ROUTER`, nothing changes: no router is loaded and no command is pinned. A
router that does not implement `prepare()` is never asked, and an error in it is only logged.

## Validation

- Exact-source CI: helper contracts on Ubuntu and macOS (341 Python tests) and the Windows WSL
  lifetime boundaries. New tests: routers receive `routing_timeout_ms`; `prepare()` reaches a
  loaded router without the helper waiting and is skipped while the router loads; a failing hook
  is only logged; the phone's capability request and the audio both reach `prepare()` before
  speech recognition.
- End to end on the development machine: this helper's router host loading Pusula 0.2.2 against
  the real Ollama and APUS-OpenJev 4B gave Pusula a 2500 ms decision budget from the 3000 ms
  timeout and routed escalations in 0.38 to 0.63 s after 150 s idle.
