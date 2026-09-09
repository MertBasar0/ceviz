"""Isolated native-UI fixture: real Ceviz HTTP routes, in-process fake Gateway.

Run on a macOS test host before pairing the simulator normally. No production
test flags, model subprocesses, operator state, or real Gateway are involved.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, nullcontext
import faulthandler
import hmac
import json
import os
from pathlib import Path
import sys
from socketserver import TCPServer
import tempfile
import time
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


TOKEN = "ceviz-phone-ui-test-only"
PORT = 18790
MAIN_KEY = "agent:planner:weekend"
BUSY_KEY = "agent:builder:review"


class PhoneFixtureGateway:
    def __init__(self):
        self.reset("normal")

    def reset(self, scenario: str):
        if scenario not in {"normal", "queued", "failed", "uncertain", "reset"}:
            raise ValueError("Unknown fixture scenario")
        self.scenario = scenario
        self.calls = []
        self.runs = {}
        now = int(time.time() * 1000)
        self.rows = [
            {"key": MAIN_KEY, "sessionId": "planner-session", "derivedTitle": "Weekend plan",
             "lastMessagePreview": "Compare two walking routes.", "updatedAt": now,
             "activeLeafEntryId": "planner-leaf", "hasActiveRun": False},
            {"key": BUSY_KEY, "sessionId": "builder-session", "derivedTitle": "Build review",
             "lastMessagePreview": "The checks are still running.", "updatedAt": now - 1000,
             "activeLeafEntryId": "builder-leaf", "hasActiveRun": True, "activeRunIds": ["existing-run"]},
            {"key": "agent:planner:untitled-thread", "sessionId": "unnamed-session",
             "lastMessagePreview": "Rota notları hazır.", "updatedAt": now - 2000,
             "activeLeafEntryId": None, "hasActiveRun": False},
            {"key": "agent:planner:earlier", "sessionId": "earlier-session", "derivedTitle": "Earlier notes",
             "updatedAt": now - 3000, "activeLeafEntryId": "earlier-leaf", "hasActiveRun": False},
        ]
        self.messages = {row["key"]: [
            {"id": "question", "role": "user", "content": "Compare two walking routes.", "timestamp": now - 1000},
            {"id": "answer", "role": "assistant", "content": "The riverside route is quieter.", "timestamp": now},
        ] for row in self.rows}

    def __call__(self, method: str, params: dict) -> dict:
        import session_api
        self.calls.append({"method": method, "params": dict(params)})
        if method == "agents.list":
            return {"agents": [{"id": "planner", "name": "Planner"}, {"id": "builder", "name": "Builder"}]}
        if method == "sessions.list":
            rows = [row for row in self.rows if not params.get("agentId") or row["key"].split(":")[1] == params["agentId"]]
            offset = params.get("offset", 0)
            # A short first page exercises a real cursor without 50 native swipes.
            page = rows[offset:offset + 3]
            more = offset + len(page) < len(rows)
            return {"sessions": page, "hasMore": more, "nextOffset": offset + len(page) if more else None}
        if method == "chat.history":
            key = params["sessionKey"]
            row = next(row for row in self.rows if row["key"] == key)
            if self.scenario == "reset" and params.get("limit") == 1 and "inputRunIds" not in params:
                row["sessionId"] = "reset-session"
            earlier = params.get("offset", 0) > 0
            messages = ([{"id": "earlier", "role": "user", "content": "Earlier route notes.", "timestamp": 1}]
                        if earlier else self.messages[key])
            active = [run_id for run_id, run in self.runs.items() if run["key"] == key and run["status"] == "pending"]
            info = {**row, "activeRunIds": row.get("activeRunIds", []) + active}
            return {"sessionKey": key, "sessionId": row["sessionId"], "sessionInfo": info,
                    "messages": messages, "hasMore": not earlier, "nextOffset": None if earlier else 2,
                    "pendingInputs": {"items": [], "total": len(active)},
                    "inputReceipts": [{"runId": run_id} for run_id, run in self.runs.items() if run["key"] == key]}
        if method == "chat.send":
            if self.scenario == "uncertain":
                raise session_api.SessionError("gateway_unavailable", "Fixture acceptance is unconfirmed.", 503, uncertain=True)
            run_id = params["idempotencyKey"]
            key = params["sessionKey"]
            status = "pending" if self.scenario == "queued" or key == BUSY_KEY else "started"
            self.runs[run_id] = {"key": key, "status": status, "session_id": params["sessionId"]}
            self.messages[key].append({"id": run_id, "role": "user", "content": params["message"]})
            if status == "started" and self.scenario != "failed":
                self.messages[key].append({"id": run_id + "-answer", "role": "assistant", "content": "Fixture reply received."})
            return {"runId": run_id, "status": status}
        if method == "agent.wait":
            run_id = params["runId"]
            if run_id not in self.runs:
                return {"runId": run_id, "status": "timeout"}
            run = self.runs[run_id]
            if run["status"] == "pending":
                return {"runId": run_id, "status": "pending"}
            return {"runId": run_id, "status": "error" if self.scenario == "failed" else "ok",
                    "endedAt": int(time.time() * 1000),
                    "terminalReceipt": {"runId": run_id, "sessionId": run["session_id"]}}
        raise AssertionError(f"Unexpected Gateway call in native fixture: {method}")

    def evidence(self) -> dict:
        return {"pid": os.getpid(), "scenario": self.scenario, "calls": self.calls,
                "send_calls": [call["params"] for call in self.calls if call["method"] == "chat.send"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--state-dir", type=Path, help="Test-parent-owned temporary state directory")
    args = parser.parse_args()
    state = nullcontext(str(args.state_dir)) if args.state_dir else tempfile.TemporaryDirectory(prefix="ceviz-phone-ui-")
    with state as temporary, ExitStack() as scope:
        # Capture an actual stack if a clean-machine startup stalls; do not
        # replace a missing ready signal with a larger sleep or deadline.
        faulthandler.dump_traceback_later(5)
        scope.callback(faulthandler.cancel_dump_traceback_later)
        print("Phone UI fixture: importing isolated backend", file=sys.stderr, flush=True)
        scope.enter_context(patch.dict(os.environ, {
            "WATCH_CEVIZ_STATE_DIR": temporary, "OPENCLAW_WATCH_RUNTIME_DIR": str(Path(temporary) / "runtime"),
            "WATCH_CEVIZ_AUTH_TOKEN": TOKEN,
        }))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        import main as backend
        import session_api
        print("Phone UI fixture: binding numeric loopback", file=sys.stderr, flush=True)
        fake = PhoneFixtureGateway()
        scope.enter_context(patch.object(backend, "AUTH_TOKEN", TOKEN))
        initial_state_path = Path(temporary) / "initial.sqlite"
        scope.enter_context(patch.object(session_api, "sessions_api", session_api.OpenClawSessions(initial_state_path)))
        scope.enter_context(patch.object(session_api, "call_gateway", fake))
        scope.enter_context(patch.object(backend.openclaw_client, "invoke_watch_command",
                                        side_effect=AssertionError("Native fixture cannot execute a real command")))
        scope.enter_context(patch.object(backend.stt_client, "transcribe_watch_payload",
                                        side_effect=AssertionError("Native fixture does not transcribe audio")))
        scope.enter_context(patch.object(backend.push_notifier, "register", return_value={"ok": True, "fixture": True}))

        class FixtureHandler(backend.WatchCevizHandler):
            state_path = initial_state_path
            helper_generation = 0

            def _do_GET_impl(self):
                parsed = urlparse(self.path)
                if parsed.path.startswith("/__fixture/"):
                    if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + TOKEN):
                        self.send_error(401)
                        return
                    if parsed.path == "/__fixture/reset":
                        fake.reset(parse_qs(parsed.query).get("scenario", ["normal"])[0])
                        # Each scenario is a new normal pairing, not a hidden
                        # production-state erase. Restart keeps both identities.
                        backend.AUTH_TOKEN = "ceviz-fixture-" + uuid.uuid4().hex
                        FixtureHandler.state_path = Path(temporary) / (uuid.uuid4().hex + ".sqlite")
                        backend.jobs_db.clear()
                    if parsed.path in {"/__fixture/reset", "/__fixture/restart_helper"}:
                        session_api.sessions_api = session_api.OpenClawSessions(FixtureHandler.state_path)
                        FixtureHandler.helper_generation += 1
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(json.dumps({**fake.evidence(), "pairing_token": backend.AUTH_TOKEN,
                                                "helper_generation": FixtureHandler.helper_generation}).encode())
                    return
                super()._do_GET_impl()

        class NumericLoopbackHTTPServer(backend.HTTPServer):
            def server_bind(self):
                # HTTPServer otherwise reverse-resolves its address before it
                # starts listening. This isolated numeric endpoint needs no DNS.
                TCPServer.server_bind(self)
                self.server_name, self.server_port = self.server_address[:2]

        server = NumericLoopbackHTTPServer(("127.0.0.1", args.port), FixtureHandler)
        faulthandler.cancel_dump_traceback_later()
        print(f"Phone UI fixture ready at http://127.0.0.1:{server.server_port}; no real Gateway", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
