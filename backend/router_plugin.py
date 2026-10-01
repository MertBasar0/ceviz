"""Optional model-routing plugins (contract v1).

Ceviz itself never chooses a model: without a router every command runs on the OpenClaw agent's
own model and its configured fallback chain. An operator can opt in to a router that is installed
separately into the helper's Python environment:

- The plugin package exposes an entry point in the ``ceviz.routers`` group. Its target is a
  factory called once as ``factory(host)`` with a plain ``dict`` (see ``_host_info``), returning
  a router object.
- The router declares ``api_version = 1`` and implements ``route(request: dict) -> dict | None``.
- The operator enables it explicitly with ``WATCH_CEVIZ_ROUTER=<entry point name>``. Installing
  a package alone never changes routing, and an unset variable never even looks for plugins.

Host guarantees: a router error, timeout or invalid answer never fails a command and never
pins a model; the command simply runs unpinned. A pinned command that fails before running any
tool is retried once without the pin (``OpenClawClient.relaunch_unpinned``), so the fallback
chain still applies.

Requests and answers are plain JSON-compatible dicts, so a plugin never imports Ceviz code.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("watch_ceviz.router_plugin")

ROUTER_API_VERSION = 1
ENTRY_POINT_GROUP = "ceviz.routers"
DEFAULT_TIMEOUT_MS = 1500
RECENT_JOB_WINDOW_SECONDS = 900
RECENT_JOB_LIMIT = 8

# The answer becomes argv for `openclaw agent`; accept only plain selector shapes, never options.
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")
_THINKING_PATTERN = re.compile(r"^[a-z][a-z-]{0,15}$")


@dataclass(frozen=True)
class RouteChoice:
    model: str | None
    thinking: str | None
    reason: str
    router: str
    latency_ms: int

    def argv(self) -> list[str]:
        args: list[str] = []
        if self.model:
            args += ["--model", self.model]
        if self.thinking:
            args += ["--thinking", self.thinking]
        return args


def _state_dir() -> Path:
    return Path(os.environ.get("WATCH_CEVIZ_STATE_DIR", str(Path.home() / ".openclaw" / "ceviz-state")))


def _host_info(agent: str) -> dict[str, Any]:
    return {
        "api_version": ROUTER_API_VERSION,
        "agent": agent,
        # Plugins keep their own configuration and caches under this directory.
        "state_dir": str(_state_dir()),
    }


def recent_jobs(now: float | None = None) -> list[dict[str, Any]]:
    """Finished jobs from the last 15 minutes, oldest first: the conversation's trajectory."""
    try:
        path = _state_dir() / "jobs.json"
        jobs = json.loads(path.read_text(encoding="utf-8")).get("jobs", []) if path.is_file() else []
    except Exception:
        return []
    now = time.time() if now is None else now
    recent = [
        {
            "transcript": job.get("transcript") or job.get("name") or "",
            "outcome": job.get("outcome"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
        }
        for job in jobs
        if isinstance(job, dict)
        and isinstance(job.get("created_at"), (int, float))
        and now - job["created_at"] <= RECENT_JOB_WINDOW_SECONDS
        and job.get("status") in ("completed", "failed")
    ]
    return sorted(recent, key=lambda job: job["created_at"])[-RECENT_JOB_LIMIT:]


def _timeout_seconds() -> float:
    try:
        value = int(os.environ.get("WATCH_CEVIZ_ROUTER_TIMEOUT_MS", DEFAULT_TIMEOUT_MS))
    except ValueError:
        value = DEFAULT_TIMEOUT_MS
    return max(50, min(value, 10_000)) / 1000


class RouterHost:
    """Loads the configured router once and turns its answers into validated argv."""

    def __init__(
        self,
        agent: str,
        name: str | None = None,
        loader: Callable[[str], Any] | None = None,
    ) -> None:
        self.agent = agent
        self.name = (os.environ.get("WATCH_CEVIZ_ROUTER", "") if name is None else name).strip()
        self._loader = loader or _load_entry_point
        self._router: Any = None
        self._loaded = False
        self._executor: ThreadPoolExecutor | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.name)

    def status(self) -> str:
        """One line for diagnostics; never includes request contents."""
        if not self.enabled:
            return "disabled (no WATCH_CEVIZ_ROUTER)"
        return f"{self.name}: active" if self._get_router() is not None else f"{self.name}: unavailable"

    def _get_router(self) -> Any:
        if self._loaded:
            return self._router
        self._loaded = True
        if not self.enabled:
            return None
        try:
            factory = self._loader(self.name)
            router = factory(_host_info(self.agent))
            if getattr(router, "api_version", None) != ROUTER_API_VERSION or not callable(getattr(router, "route", None)):
                logger.warning(f"[router] '{self.name}' does not implement router contract v{ROUTER_API_VERSION}; routing stays off")
                return None
            self._router = router
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ceviz-router")
            logger.info(f"[router] '{self.name}' enabled (contract v{ROUTER_API_VERSION})")
        except Exception as exc:
            logger.warning(f"[router] '{self.name}' could not be loaded; routing stays off: {exc}")
            self._router = None
        return self._router

    def choose(self, transcript: str, continuation: str = "", locale: str = "") -> RouteChoice | None:
        """Ask the router for this turn. None means: run on the agent default."""
        router = self._get_router()
        if router is None or not transcript.strip():
            return None
        request = {
            "api_version": ROUTER_API_VERSION,
            "agent": self.agent,
            "transcript": transcript,
            "locale": locale,
            "continuation": continuation or None,
            "recent_jobs": recent_jobs(),
        }
        if self._executor is None:
            return None
        started = time.monotonic()
        try:
            # A hung router keeps its single worker busy, so later turns time out too and run
            # unpinned instead of piling up threads.
            answer = self._executor.submit(router.route, request).result(timeout=_timeout_seconds())
        except FutureTimeout:
            logger.warning(f"[router] '{self.name}' timed out; running on the agent default")
            return None
        except Exception as exc:
            logger.warning(f"[router] '{self.name}' failed; running on the agent default: {exc}")
            return None
        latency_ms = int((time.monotonic() - started) * 1000)
        if answer is None:
            return None
        if not isinstance(answer, dict):
            logger.warning(f"[router] '{self.name}' returned {type(answer).__name__}, not a dict; ignored")
            return None
        model = answer.get("model")
        thinking = answer.get("thinking")
        if model is not None and not (isinstance(model, str) and _MODEL_PATTERN.match(model)):
            logger.warning(f"[router] '{self.name}' returned an invalid model value; ignored")
            model = None
        if thinking is not None and not (isinstance(thinking, str) and _THINKING_PATTERN.match(thinking)):
            logger.warning(f"[router] '{self.name}' returned an invalid thinking value; ignored")
            thinking = None
        if not model and not thinking:
            return None
        reason = str(answer.get("reason") or "")[:80]
        return RouteChoice(model=model, thinking=thinking, reason=reason, router=self.name, latency_ms=latency_ms)


def _load_entry_point(name: str) -> Any:
    matches = list(entry_points(group=ENTRY_POINT_GROUP, name=name))
    if not matches:
        raise LookupError(f"no '{ENTRY_POINT_GROUP}' entry point named '{name}' is installed")
    if len(matches) > 1:
        raise LookupError(f"several packages provide router '{name}'")
    return matches[0].load()
