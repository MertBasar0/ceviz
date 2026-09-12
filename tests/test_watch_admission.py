"""Durable Watch admission: real HTTP/SQLite, only isolated fake execution."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, ExitStack
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from test_http_transport import HTTPFixture


def command(ledger, **changes):
    payload = {"ledger_id": ledger, "command_id": str(uuid.uuid4()),
               "client_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "audio_data": "ZmFrZSBhdWRpbyBub3Qgc3RvcmVk", "format": "m4a"}
    payload.update(changes)
    material = payload["client_timestamp"] + "\n" + payload["audio_data"]
    if "continue_job_id" in payload:
        material += "\ncontinue_job_id=" + payload["continue_job_id"]
    payload["audio_digest"] = hashlib.sha256(material.encode()).hexdigest()
    return payload


def metadata(payload):
    return {key: value for key, value in payload.items() if key not in {"audio_data", "format", "locale"}}


class WatchAdmissionHTTPTests(HTTPFixture):
    def setUp(self):
        super().setUp()
        self.invoke, self.transcribe = self.forbidden[:2]
        del self.forbidden[:2]
        self.transcribe.side_effect = None
        self.transcribe.return_value = SimpleNamespace(transcript="private fixture transcript", source="test", error="")
        self.invoke.side_effect = lambda payload: SimpleNamespace(
            process=SimpleNamespace(poll=lambda: None), log_path=str(self.main.STATE_DIR / "not-created.log"),
            prompt="private fixture transcript", command=["never-executed"], started_at=time.time())
        self.database = self.main.STATE_DIR / "conversations.sqlite"
        if hasattr(self.main, "WatchAdmission"):
            self.guards.enter_context(patch.object(self.main, "watch_admission", self.main.WatchAdmission(self.database)))

    def bootstrap(self):
        status, result = self.http("GET", "/api/v1/watch/command/capabilities")
        self.assertEqual(status, 200, "Recovery needs a versioned durable ledger before a voice upload")
        self.assertTrue(result["watch_command_recovery_v1"])
        return result["watch_command_ledger_id"]

    def test_feature_ledger_is_lazy_and_stable_and_legacy_capability_is_read_only(self):
        status, result = self.http("GET", "/api/v1/capabilities")
        self.assertEqual(status, 200)
        self.assertFalse(self.database.exists())
        ledger = self.bootstrap()
        self.assertEqual(self.bootstrap(), ledger)
        uuid.UUID(ledger)
        with self.main.watch_admission.connection(readonly=False) as database:
            self.assertEqual(database.execute("PRAGMA synchronous").fetchone()[0], 3)
            self.assertEqual(database.execute("PRAGMA fullfsync").fetchone()[0], 1)
        before = (self.database.read_bytes(), self.database.stat().st_mtime_ns)
        self.http("POST", "/api/v1/watch/command/status", metadata(command(ledger)))
        self.assertEqual((self.database.read_bytes(), self.database.stat().st_mtime_ns), before)
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()

    def test_reserved_receipt_survives_owner_reopen_without_second_dispatch(self):
        payload = command(self.bootstrap())
        status, receipt = self.http("POST", "/api/v1/watch/command/submit", payload)
        self.assertEqual(status, 200)
        self.assertEqual(receipt["delivery_state"], "accepted")
        self.main.watch_admission = self.main.WatchAdmission(self.database)
        status, recovered = self.http("POST", "/api/v1/watch/command/status", metadata(payload))
        self.assertEqual(status, 200)
        self.assertEqual(recovered["delivery_state"], "accepted")
        self.assertEqual(recovered["job_id"], receipt["job_id"])
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[1]["job_id"], receipt["job_id"])
        self.invoke.assert_called_once()
        self.transcribe.assert_called_once()
        for forbidden in [payload["audio_data"], "private fixture transcript", "ingress-fixture"]:
            self.assertNotIn(forbidden.encode(), self.database.read_bytes())

    def test_missing_or_recreated_ledger_never_claims_not_submitted(self):
        payload = command(str(uuid.uuid4()))
        self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]["delivery_state"], "unknown")
        self.assertFalse(self.database.exists(), "Status must not initialize a ledger")
        original = self.bootstrap()
        payload = command(original)
        self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]["delivery_state"], "not_submitted")
        self.database.rename(self.database.with_suffix(".preserved"))
        self.assertNotEqual(self.bootstrap(), original)
        for route in ("status", "submit"):
            status, result = self.http("POST", "/api/v1/watch/command/" + route, metadata(payload) if route == "status" else payload)
            self.assertEqual(status, 200 if route == "status" else 409)
            self.assertEqual(result["delivery_state"], "unknown")
            self.assertEqual(result["ledger_id"], original)
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()

    def test_age_future_and_identity_mutations_never_dispatch(self):
        ledger = self.bootstrap()
        for offset in (-901, 32):
            payload = command(ledger, client_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset)))
            self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[0], 409)
            self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]["delivery_state"], "unknown")
        original = command(ledger)
        for changes in ({"audio_data": "different"}, {"command_id": "not-uuid"}, {"audio_digest": "g" * 64},
                        {"client_timestamp": "2026-09-13"}, {"continue_job_id": "../invalid"},
                        {"transcript": "unbound text must not bypass audio"}, {"format": "wav"}, {"locale": []}):
            with self.subTest(changes=changes):
                self.assertIn(self.http("POST", "/api/v1/watch/command/submit", {**original, **changes})[0], {400, 409})
        self.assertEqual(self.http("POST", "/api/v1/watch/command/status", original)[0], 400)
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()

    def test_bound_identity_parent_target_and_uuid_case_remain_immutable(self):
        payload = command(self.bootstrap(), command_id=str(uuid.uuid4()).upper())
        accepted = self.http("POST", "/api/v1/watch/command/submit", payload)[1]
        self.assertEqual(accepted["command_id"], payload["command_id"])
        lowercase = {**payload, "command_id": payload["command_id"].lower()}
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", lowercase)[1]["job_id"], accepted["job_id"])
        for changes in ({"audio_data": "differentaudio"}, {"continue_job_id": "job-other"},
                        {"client_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))}):
            changed = {**payload, **changes}
            changed = command(changed.pop("ledger_id"), **changed)
            with self.subTest(changes=changes):
                self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", changed)[0], 409)
        with patch.object(self.main.openclaw_client, "agent", "different-agent"):
            self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[0], 409)
            self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[0], 409)
        self.invoke.assert_called_once()

    def test_distinct_explicit_parents_dispatch_distinct_jobs_and_terminal_status_is_not_working(self):
        ledger = self.bootstrap()
        results = []
        for parent in ("job-parent-a", "job-parent-b"):
            self.main.remember_job({"id": parent, "conversation_id": parent, "created_at": 0,
                                   "status": "completed", "watch_summary": "fixture parent", "transcript": "earlier"})
            payload = command(ledger, continue_job_id=parent)
            status, result = self.http("POST", "/api/v1/watch/command/submit", payload)
            self.assertEqual((status, result["delivery_state"]), (200, "accepted"))
            self.assertEqual(result["continue_job_id"], parent)
            results.append(result["job_id"])
        self.assertNotEqual(*results)
        self.assertEqual(self.invoke.call_count, 2)
        with self.main.jobs_lock:
            job = self.main.jobs_db[results[-1]]
            job.pop("invocation")
            job.update(status="completed", outcome="done", watch_summary="Actual fixture result", phone_report="Actual fixture result")
        state = self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]
        self.assertEqual(state["response"]["status"], "completed")
        self.assertEqual(state["response"]["outcome"], "done")
        self.assertEqual(state["response"]["job_id"], results[-1])
        self.assertNotIn(b"Actual fixture result", self.database.read_bytes())

    def test_lost_reply_and_concurrent_status_replay_and_legacy_share_one_admission(self):
        payload = command(self.bootstrap())
        entered, release = threading.Event(), threading.Event()

        def slow(value):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Private STT gate was not released")
            return SimpleNamespace(transcript="fixture", source="test", error="")

        self.transcribe.side_effect = slow
        wire = json.dumps(payload).encode()
        abandoned = self.connect(self.headers("/api/v1/watch/command/submit", f"Content-Length: {len(wire)}\r\n") + wire)
        try:
            self.assertTrue(entered.wait(1), "The real upload must reach the reserved STT boundary")
            abandoned.shutdown(socket.SHUT_RDWR)
            abandoned.close()
            started = time.monotonic()
            status, state = self.http("POST", "/api/v1/watch/command/status", metadata(payload))
            self.assertEqual((status, state["delivery_state"]), (200, "in_flight"))
            self.assertLess(time.monotonic() - started, 0.8)
            duplicate = self.http("POST", "/api/v1/watch/command/submit", payload)
            self.assertEqual((duplicate[0], duplicate[1]["delivery_state"]), (503, "in_flight"))
            self.capabilities()
            self.invoke.assert_not_called()
        finally:
            release.set()
        status, accepted = self.http("POST", "/api/v1/watch/command/submit", payload)
        self.assertEqual((status, accepted["delivery_state"]), (200, "accepted"))
        self.main.watch_admission = self.main.WatchAdmission(self.database)
        self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]["job_id"], accepted["job_id"])
        self.assertEqual(self.http("POST", "/api/v1/watch/command", payload)[1]["job_id"], accepted["job_id"])
        alias = {**payload, "command_id": str(uuid.uuid4())}
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", alias)[1]["job_id"], accepted["job_id"])
        self.invoke.assert_called_once()
        self.transcribe.assert_called_once()

    def test_sqlite_reserve_and_receipt_failures_and_job_write_failure_are_closed(self):
        ledger = self.bootstrap()
        with closing(sqlite3.connect(self.database)) as database, database:
            database.execute("CREATE TRIGGER deny_reservation BEFORE INSERT ON watch_submissions BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        payload = command(ledger)
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[0], 503)
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()
        with closing(sqlite3.connect(self.database)) as database, database:
            database.execute("DROP TRIGGER deny_reservation")
            database.execute("CREATE TRIGGER deny_receipt BEFORE UPDATE ON watch_submissions BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        status, result = self.http("POST", "/api/v1/watch/command/submit", payload)
        self.assertEqual((status, result["delivery_state"]), (503, "unknown"))
        self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]["delivery_state"], "unknown")
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[1]["delivery_state"], "unknown")
        self.assertEqual(self.http("POST", "/api/v1/watch/command", payload)[0], 409)
        self.invoke.assert_called_once()
        with closing(sqlite3.connect(self.database)) as database, database:
            database.execute("DROP TRIGGER deny_receipt")
        # Real filesystem failure after dispatch: a directory cannot be the
        # atomic jobs.json target. Do not promote the reservation from memory.
        self.main.JOBS_STATE_PATH.rename(self.main.STATE_DIR / "preserved-jobs.json")
        self.main.JOBS_STATE_PATH.mkdir()
        second = command(ledger, audio_data="c2Vjb25k")
        status, result = self.http("POST", "/api/v1/watch/command/submit", second)
        self.assertEqual((status, result["delivery_state"]), (503, "unknown"))
        self.assertEqual(self.http("POST", "/api/v1/watch/command", second)[0], 409)
        self.assertEqual(self.invoke.call_count, 2)

    def test_unknown_alias_and_missing_accepted_job_never_use_legacy_dispatch(self):
        payload = command(self.bootstrap())
        self.transcribe.side_effect = RuntimeError("private STT failure")
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[1]["delivery_state"], "unknown")
        alias = {**payload, "command_id": str(uuid.uuid4())}
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", alias)[1]["delivery_state"], "unknown")
        self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(alias))[1]["delivery_state"], "unknown")
        self.assertEqual(self.http("POST", "/api/v1/watch/command", payload)[0], 409)
        self.invoke.assert_not_called()
        self.transcribe.side_effect = None
        fresh = command(payload["ledger_id"], audio_data="bmV3")
        accepted = self.http("POST", "/api/v1/watch/command/submit", fresh)[1]
        self.main.jobs_db.clear()
        recovered = self.http("POST", "/api/v1/watch/command/status", metadata(fresh))[1]
        self.assertEqual(recovered["job_id"], accepted["job_id"])
        self.assertNotIn("response", recovered)
        self.assertEqual(self.http("POST", "/api/v1/watch/command", fresh)[0], 409)
        self.invoke.assert_called_once()

    def test_process_death_before_stt_after_real_popen_and_after_job_save_never_replays(self):
        ledger = self.bootstrap()
        for mode in ("before_stt", "after_popen", "before_receipt"):
            with self.subTest(mode=mode):
                payload = command(ledger, audio_data=mode)
                child = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--crash", mode, str(self.main.STATE_DIR)],
                                       input=json.dumps(payload), text=True, capture_output=True, timeout=12)
                self.assertEqual(child.returncode, 73, child.stdout + child.stderr)
                events = self.main.STATE_DIR / (mode + ".event")
                self.assertEqual(events.exists(), mode != "before_stt")
                if events.exists():
                    self.assertEqual(events.read_text(), "one fake external action")
                self.main.watch_admission = self.main.WatchAdmission(self.database)
                self.assertEqual(self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]["delivery_state"], "unknown")
                self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[1]["delivery_state"], "unknown")
                self.assertEqual(self.http("POST", "/api/v1/watch/command", payload)[0], 409)
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()

    def test_competing_helper_processes_share_sqlite_reservation_not_python_lock(self):
        payload = command(self.bootstrap())

        def submit_child():
            return subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--crash", "competing", str(self.main.STATE_DIR)],
                                  input=json.dumps(payload), text=True, capture_output=True, timeout=12)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result() for future in [pool.submit(submit_child), pool.submit(submit_child)]]
        for result in results:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(json.loads(result.stdout)[1]["delivery_state"], {"accepted", "unknown"})
        self.assertEqual((self.main.STATE_DIR / "competing.event").read_text(), "one fake external action")
        state = self.http("POST", "/api/v1/watch/command/status", metadata(payload))[1]
        self.assertEqual(state["delivery_state"], "accepted")
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", payload)[1]["job_id"], state["job_id"])
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()

    def test_capacity_prunes_only_expired_accepted_and_expired_identity_stays_unknown(self):
        ledger = self.bootstrap()
        payload = command(ledger)
        self.http("POST", "/api/v1/watch/command/submit", payload)
        owner = self.main.watch_admission
        with closing(sqlite3.connect(self.database)) as database, database:
            row = database.execute("SELECT * FROM watch_submissions").fetchone()
            for index in range(511):
                database.execute("INSERT INTO watch_submissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (str(uuid.uuid4()), row[1], str(index), None, row[4], time.time() - 1, row[6], "reserved", None))
        fresh = command(ledger, audio_data="ZnJlc2g=")
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", fresh)[0], 503)
        expired = command(ledger, command_id=payload["command_id"], client_timestamp="2000-01-01T00:00:00Z")
        with closing(sqlite3.connect(self.database)) as database, database:
            database.execute("UPDATE watch_submissions SET expires_at=?, client_timestamp=?, audio_digest=? WHERE state='accepted'",
                             (946684800 + 900, expired["client_timestamp"], expired["audio_digest"]))
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", fresh)[1]["delivery_state"], "accepted")
        with closing(sqlite3.connect(self.database)) as database, database:
            self.assertEqual(database.execute("SELECT count(*) FROM watch_submissions WHERE state='reserved'").fetchone()[0], 511)
            self.assertEqual(database.execute("SELECT count(*) FROM watch_submissions").fetchone()[0], 512)
        # Real old timestamp, not merely an aged retention column: absence can
        # never become replay authority for a capture older than 15 minutes.
        self.assertEqual(owner.status(metadata(expired), self.main.openclaw_client.agent)["delivery_state"], "unknown")
        self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", expired)[0], 409)
        self.assertEqual(self.invoke.call_count, 2)

    def test_auth_and_corrupt_store_have_no_dispatch_or_hidden_reset(self):
        with patch.object(self.main, "AUTH_TOKEN", "different-fixture-token"):
            self.assertEqual(self.http("GET", "/api/v1/watch/command/capabilities")[0], 401)
            self.assertEqual(self.http("POST", "/api/v1/watch/command/submit", command(str(uuid.uuid4())))[0], 401)
        self.assertFalse(self.database.exists())
        payload = command(self.bootstrap())
        self.database.write_bytes(b"fixture corrupt database; do not replace")
        before = self.database.read_bytes()
        for route in ("status", "submit"):
            status, result = self.http("POST", "/api/v1/watch/command/" + route, metadata(payload) if route == "status" else payload)
            self.assertEqual((status, result["delivery_state"]), (503, "unknown"))
        self.assertEqual(self.http("GET", "/api/v1/watch/command/capabilities")[0], 503)
        self.assertEqual(self.database.read_bytes(), before)
        self.invoke.assert_not_called()
        self.transcribe.assert_not_called()


def crash_boundary(mode, root):
    """Actual private process death; fake action uses actual Popen, no CLI/model."""
    os.environ["WATCH_CEVIZ_STATE_DIR"] = root
    os.environ["OPENCLAW_WATCH_RUNTIME_DIR"] = str(Path(root) / "runtime")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    with patch.object(Path, "home", return_value=Path(root)):
        import main
    payload = json.loads(sys.stdin.read())

    def transcribe(value):
        if mode == "before_stt":
            os._exit(73)
        return SimpleNamespace(transcript="fake command", source="test", error="")

    def invoke(value):
        event = str(Path(root) / (mode + ".event"))
        process = subprocess.Popen([sys.executable, "-B", "-c",
            "import sys,time; stream=open(sys.argv[1], 'a'); stream.write('one fake external action'); stream.close(); time.sleep(0.15)", event])
        if process.wait(timeout=3) != 0:
            raise AssertionError("Private fake action failed")
        if mode == "after_popen":
            os._exit(73)
        return SimpleNamespace(process=process, log_path=str(Path(root) / "missing.log"), prompt="fake", command=["private fake"], started_at=time.time())

    with ExitStack() as scope:
        scope.enter_context(patch.object(main.stt_client, "transcribe_watch_payload", side_effect=transcribe))
        scope.enter_context(patch.object(main.openclaw_client, "invoke_watch_command", side_effect=invoke))
        if mode == "before_receipt":
            scope.enter_context(patch.object(main.watch_admission, "record_accepted", side_effect=lambda *args: os._exit(73)))
        result = main.watch_admission.submit(payload, main.openclaw_client.agent,
                                            lambda value: main.execute_watch_command(value, strict_save=True)["id"])
    if mode != "competing":
        raise AssertionError("Crash boundary was not reached")
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--crash":
        crash_boundary(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
