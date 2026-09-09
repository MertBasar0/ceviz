"""Prove the native fixture serves real authenticated routes without a Gateway."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib import error, request

import phone_ui_fixture
from phone_ui_fixture import TOKEN, MAIN_KEY, BUSY_KEY


class PhoneUIFixtureTests(unittest.TestCase):
    api_token = TOKEN
    @classmethod
    def setUpClass(cls):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.state = tempfile.TemporaryDirectory(prefix="ceviz-phone-fixture-test-")
        cls.addClassCleanup(cls.state.cleanup)
        cls.log_path = Path(cls.state.name) / "fixture.log"
        cls.log = cls.log_path.open("w")
        cls.addClassCleanup(cls.log.close)
        cls.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("phone_ui_fixture.py")), "--port", str(port),
             "--state-dir", cls.state.name],
            stdout=cls.log, stderr=subprocess.STDOUT,
        )
        cls.addClassCleanup(cls.stop_fixture)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                raise cls.startup_error("exited before readiness")
            try:
                if cls.http("/__fixture/state")["pid"] != cls.process.pid:
                    raise cls.startup_error("reached a different process")
                return
            except error.URLError:
                time.sleep(0.05)
        raise cls.startup_error("did not become ready")

    @classmethod
    def startup_error(cls, reason):
        diagnostics = cls.log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        return RuntimeError(f"Isolated phone fixture {reason}\n{diagnostics}")

    @classmethod
    def stop_fixture(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)

    @classmethod
    def http(cls, path, payload=None):
        req = request.Request(cls.base + path,
                              data=json.dumps(payload).encode() if payload is not None else None,
                              headers={"Authorization": "Bearer " + (TOKEN if path.startswith("/__fixture/") else cls.api_token),
                                       "Content-Type": "application/json"})
        with request.urlopen(req, timeout=3) as response:
            result = json.loads(response.read())
        if path.startswith("/__fixture/reset"):
            cls.api_token = result["pairing_token"]
        return result

    def test_helper_restart_preserves_owner_and_scenario_reset_uses_new_pairing(self):
        first = self.http("/__fixture/reset?scenario=uncertain")
        payload = {"session_key": MAIN_KEY, "session_id": "planner-session", "expected_leaf_entry_id": "planner-leaf",
                   "text": "Check route after restart", "request_id": "a3f743fd-1c15-4140-a3e7-714a1b6314cd"}
        with self.assertRaises(error.HTTPError):
            self.http("/api/v1/sessions/message", payload)
        restarted = self.http("/__fixture/restart_helper")
        self.assertEqual(restarted["helper_generation"], first["helper_generation"] + 1)
        self.assertEqual(restarted["pairing_token"], first["pairing_token"])
        self.assertEqual(self.http("/api/v1/sessions/message", payload)["status"], "unconfirmed")
        self.assertEqual(len(self.http("/__fixture/state")["send_calls"]), 1)
        replacement = self.http("/__fixture/reset?scenario=normal")
        self.assertNotEqual(replacement["pairing_token"], first["pairing_token"])
        self.assertEqual(replacement["send_calls"], [])

    def test_native_fixture_uses_canonical_list_history_and_guarded_send(self):
        self.assertEqual(self.http("/__fixture/reset?scenario=normal")["pid"], self.process.pid)
        page = self.http("/api/v1/sessions")
        self.assertEqual([row["title"] for row in page["sessions"]], ["Weekend plan", "Build review", "untitled-thread"])
        self.assertTrue(page["has_more"])
        older = self.http("/api/v1/sessions?offset=3")
        self.assertEqual(older["sessions"][0]["title"], "Earlier notes")
        history = self.http("/api/v1/sessions/history?session_key=" + MAIN_KEY)
        self.assertEqual(history["session"]["session_id"], "planner-session")
        payload = {"session_key": MAIN_KEY, "session_id": "planner-session", "expected_leaf_entry_id": "planner-leaf",
                   "text": "Check route", "request_id": "a3f743fd-1c15-4140-a3e7-714a1b6314cd"}
        sent = self.http("/api/v1/sessions/message", payload)
        self.assertTrue(sent["delivery_confirmed"])
        result = self.http("/api/v1/sessions/run?session_key=" + MAIN_KEY + "&run_id=" + sent["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.http("/__fixture/state")["send_calls"]), 1)

    def test_native_fixture_exercises_queued_reset_and_uncertain_boundaries(self):
        payload = {"session_key": BUSY_KEY, "session_id": "builder-session", "expected_leaf_entry_id": "builder-leaf",
                   "text": "Check build", "request_id": "a3f743fd-1c15-4140-a3e7-714a1b6314cd"}
        self.http("/__fixture/reset?scenario=queued")
        sent = self.http("/api/v1/sessions/message", payload)
        self.assertEqual(sent["status"], "pending")
        result = self.http("/api/v1/sessions/run?session_key=" + BUSY_KEY + "&run_id=" + sent["run_id"])
        self.assertEqual(result["status"], "queued")
        for scenario, status, count, uncertain in [("reset", 409, 0, False), ("uncertain", 503, 1, True)]:
            with self.subTest(scenario=scenario):
                self.http("/__fixture/reset?scenario=" + scenario)
                with self.assertRaises(error.HTTPError) as rejected:
                    self.http("/api/v1/sessions/message", payload)
                self.assertEqual(rejected.exception.code, status)
                self.assertEqual(json.loads(rejected.exception.read())["delivery_uncertain"], uncertain)
                self.assertEqual(len(self.http("/__fixture/state")["send_calls"]), count)


class PhoneUIFixtureStartupTests(unittest.TestCase):
    def test_numeric_loopback_fixture_does_not_depend_on_reverse_dns(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-phone-startup-test-") as state, \
                patch.object(sys, "argv", ["phone_ui_fixture.py", "--port", "0", "--state-dir", state]), \
                patch("socket.getfqdn", side_effect=AssertionError("Reverse DNS is unavailable")), \
                patch("http.server.HTTPServer.serve_forever") as serve:
            phone_ui_fixture.main()
        serve.assert_called_once_with()

    def test_startup_failure_reports_bounded_child_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-phone-log-test-") as state:
            path = Path(state) / "fixture.log"
            path.write_text("x" * 9000 + "\nStalled in fixture bind\n", encoding="utf-8")
            with patch.object(PhoneUIFixtureTests, "log_path", path, create=True):
                failure = PhoneUIFixtureTests.startup_error("did not become ready")
            self.assertIn("Stalled in fixture bind", str(failure))
            self.assertLess(len(str(failure)), 8100)


if __name__ == "__main__":
    unittest.main()
