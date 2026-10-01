# Optional model-routing plugins

Ceviz does not choose models. By default, every Watch command runs on the OpenClaw agent's own
model, and the fallback chain configured in OpenClaw handles provider outages. Ceviz never sends
`--model` or `--thinking`.

A router plugin is a separately installed package that can pick a model and thinking level per
command, for example a stronger model after the user corrects a missed answer. Routing stays off
until an operator installs a plugin **and** enables it. Installing a package alone changes
nothing. Without the setting, the helper never even looks for plugins.

## Enable a router

1. Install the plugin into the helper's own Python environment:

   ```bash
   ~/path/to/ceviz/.venv/bin/pip install <router-package>
   ```

2. Enable it by its entry-point name in the user service, then restart:

   ```bash
   systemctl --user edit watch-ceviz-backend
   # add:
   # [Service]
   # Environment=WATCH_CEVIZ_ROUTER=<name>
   systemctl --user restart watch-ceviz-backend
   ```

3. Run `deploy/doctor.sh`. It reports `Router plugin "<name>" is installed and enabled`, or warns
   when the setting names a plugin that is not installed.

To turn routing off, remove `WATCH_CEVIZ_ROUTER` and restart the service. The package can stay
installed. Helper updates reuse the virtual environment and verify only the helper's own release
files, so an installed plugin survives updates. Keep plugin dependencies small and pinned: they
share that environment with the helper.

## What the helper guarantees

- **Off by default.** With no `WATCH_CEVIZ_ROUTER`, commands are never pinned.
- **Errors never fail a command.** A router that cannot load, raises, times out
  (`WATCH_CEVIZ_ROUTER_TIMEOUT_MS`, default 1500 ms), or returns anything invalid is ignored. The
  command then runs on the agent default.
- **Only plain selectors reach the command line.** A `model` must look like `provider/model`
  (letters, digits and `._:/@+-`, up to 200 characters). A `thinking` value must be a short
  lowercase word. Anything else is dropped, so an answer cannot inject options.
- **Fallbacks come back after a failed pin.** OpenClaw disables the fallback chain for an explicit
  `--model`. If a pinned command fails before running any tool (an auth refresh, overload or rate
  limit), Ceviz retries it once without the pin.
- **One routing decision at a time.** The router is called from a single worker thread. A hung
  router makes later commands time out and run unpinned; it never piles up threads.

## Writing a router (contract v1)

Requests and answers are plain JSON-compatible `dict`s, so a plugin never imports Ceviz code.

Declare an entry point in the `ceviz.routers` group:

```toml
[project.entry-points."ceviz.routers"]
example = "example_router:create"
```

The helper calls the target once, as `create(host)`:

| `host` key | Meaning |
|---|---|
| `api_version` | `1` |
| `agent` | The OpenClaw agent Ceviz sends commands to |
| `state_dir` | Ceviz state directory; keep plugin config and caches under it |

It must return an object with `api_version = 1` and `route(request) -> dict | None`:

| `request` key | Meaning |
|---|---|
| `api_version` | `1` |
| `agent` | Same as above |
| `transcript` | The command text (after speech recognition) |
| `locale` | Device locale, for example `tr-TR`, or an empty string |
| `continuation` | The prior job's context when the user continues it, otherwise `null` |
| `recent_jobs` | Up to 8 finished jobs from the last 15 minutes, oldest first: `transcript`, `status`, `outcome` (`done`, `needs_input`, `blocked`, or `null`), `created_at` |

Return `None` to keep the agent default, or a dict:

| Answer key | Meaning |
|---|---|
| `model` | Optional `provider/model` selector |
| `thinking` | Optional thinking level, for example `medium` |
| `reason` | Optional short label for the helper log (first 80 characters) |

```python
class ExampleRouter:
    api_version = 1

    def __init__(self, host):
        self.agent = host["agent"]

    def route(self, request):
        missed = [job for job in request["recent_jobs"] if job["outcome"] == "blocked"]
        if missed and request["transcript"] == missed[-1]["transcript"]:
            return {"model": "anthropic/claude-sonnet-5", "thinking": "medium", "reason": "repeat"}
        return None


def create(host):
    return ExampleRouter(host)
```

Only choose models the operator already configured in OpenClaw. A model that is merely
available may sit behind a paid API key the operator never chose for Ceviz.

## Privacy

A router runs inside the helper process and receives the command text and the recent jobs'
command texts and outcomes. Ceviz itself sends nothing anywhere else; any network call a router
makes, for example to a decision model, belongs to that plugin and should be documented by it.
