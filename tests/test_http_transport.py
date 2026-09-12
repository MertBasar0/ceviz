"""Real TCP ingress/lifecycle regressions; private state, no model or Gateway."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class HTTPFixture(unittest.TestCase):
    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        temporary = self.guards.enter_context(tempfile.TemporaryDirectory(prefix="ceviz-http-ingress-"))
        self.guards.enter_context(patch.dict(os.environ, {
            "WATCH_CEVIZ_STATE_DIR": temporary,
            "OPENCLAW_WATCH_RUNTIME_DIR": str(Path(temporary) / "runtime"),
        }))
        self.guards.enter_context(patch.object(Path, "home", return_value=Path(temporary)))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
        self.addCleanup(sys.path.pop, 0)
        self.main = importlib.import_module("main")
        self.transport = importlib.import_module("http_transport")
        self.guards.enter_context(patch.object(self.main, "AUTH_TOKEN", "ingress-fixture"))
        self.guards.enter_context(patch.object(self.main, "jobs_db", {}))
        self.guards.enter_context(patch.object(self.main, "STATE_DIR", Path(temporary)))
        self.guards.enter_context(patch.object(self.main, "JOBS_STATE_PATH", Path(temporary) / "jobs.json"))
        self.forbidden = []
        for owner, method in ((self.main.openclaw_client, "invoke_watch_command"),
                              (self.main.stt_client, "transcribe_watch_payload"),
                              (self.main.push_notifier, "register")):
            self.forbidden.append(self.guards.enter_context(patch.object(owner, method,
                side_effect=AssertionError("No external command is allowed in an ingress test"))))
        self.forbidden.append(self.guards.enter_context(patch("session_api.call_gateway",
            side_effect=AssertionError("No Gateway is allowed in an ingress test"))))
        self.server = self.main.HTTPServer(("127.0.0.1", 0), self.main.WatchCevizHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.clients = []
        self.addCleanup(self.stop_server)

    def stop_server(self):
        for client in self.clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        for forbidden in self.forbidden:
            forbidden.assert_not_called()

    def connect(self, data):
        client = socket.create_connection(self.server.server_address, timeout=1)
        self.clients.append(client)
        client.sendall(data)
        return client

    def capabilities(self):
        client = http.client.HTTPConnection(*self.server.server_address, timeout=1)
        try:
            client.request("GET", "/api/v1/capabilities", headers={"Authorization": "Bearer ingress-fixture"})
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())["conversations_v1"])
        except TimeoutError:
            self.fail("An incomplete peer must not block a complete authenticated request")
        finally:
            client.close()

    def http(self, method, path, payload=None, timeout=3):
        client = http.client.HTTPConnection(*self.server.server_address, timeout=timeout)
        try:
            client.request(method, path, body=None if payload is None else json.dumps(payload),
                           headers={"Authorization": "Bearer ingress-fixture", "Content-Type": "application/json"})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def response(self, client):
        with http.client.HTTPResponse(client) as response:
            response.begin()
            body = response.read()
            self.assertEqual(int(response.headers["Content-Length"]), len(body))
            self.assertEqual(response.headers["Connection"], "close")
            return response.status, json.loads(body)

    @staticmethod
    def headers(path, extra):
        return (f"POST {path} HTTP/1.1\r\nHost: localhost\r\n"
                "Authorization: Bearer ingress-fixture\r\n" + extra + "\r\n").encode()


class HTTPIngressTests(HTTPFixture):
    def test_incomplete_authorized_body_does_not_block_other_requests(self):
        self.connect(b"POST /api/v1/watch/command HTTP/1.1\r\nHost: localhost\r\n"
                     b"Authorization: Bearer ingress-fixture\r\nContent-Length: 4096\r\n\r\n{")
        self.capabilities()
        self.assertEqual(self.main.jobs_db, {})

    def test_incomplete_headers_do_not_block_other_requests(self):
        self.connect(b"GET /api/v1/capabilities HTTP/1.1\r\nHost: localhost\r\n")
        self.capabilities()

    def test_header_and_sibling_upload_trickles_share_one_real_total_deadline(self):
        paths = ["/api/v1/watch/command", "/api/v1/shortcuts/command", "/api/v1/push/register",
                 "/api/v1/sessions/message", "/api/v1/jobs/missing/cancel", "/api/v1/jobs/missing/summarize"]
        started = time.monotonic()
        clients = [self.connect(self.headers(path, "Content-Length: 4096\r\n")) for path in paths]
        clients.append(self.connect(b"GET /api/v1/capabilities HTTP/1.1\r\nX-Trickle: "))
        stop = threading.Event()

        def trickle(client):
            while not stop.wait(0.05):
                try:
                    client.sendall(b"x")
                except OSError:
                    return

        senders = [threading.Thread(target=trickle, args=(client,)) for client in clients]
        for sender in senders:
            sender.start()
        try:
            self.capabilities()
            for client in clients:
                client.settimeout(12)
                status, payload = self.response(client)
                self.assertEqual(status, 408)
                self.assertFalse(payload["delivery_uncertain"])
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 9, "Exercise the actual production deadline, not a test timeout")
            self.assertLess(elapsed, 12, "Trickled bytes must not renew the ten-second ingress budget")
        finally:
            stop.set()
            for sender in senders:
                sender.join(timeout=1)
                self.assertFalse(sender.is_alive())
        self.capabilities()
        self.assertEqual(self.main.jobs_db, {})

    def test_invalid_framing_and_huge_decimal_are_rejected_before_dispatch(self):
        for extra in ["Content-Length: -1\r\n", "Content-Length: garbage\r\n",
                      "Content-Length: 2\r\nContent-Length: 2\r\n",
                      "Transfer-Encoding: chunked\r\n", "Content-Length: " + "9" * 5000 + "\r\n"]:
            with self.subTest(extra=extra[:65]):
                client = self.connect(self.headers("/api/v1/watch/command", extra))
                status, payload = self.response(client)
                self.assertEqual(status, 400)
                self.assertFalse(payload["delivery_uncertain"])
        self.capabilities()

    def test_completing_headers_does_not_restart_body_deadline(self):
        started = time.monotonic()
        client = self.connect(self.headers("/api/v1/watch/command", "Content-Length: 4096\r\n")[:-2])
        self.capabilities()
        # Four seconds spent on headers leave six, not ten, for the body.
        time.sleep(4)
        client.sendall(b"\r\n{")
        client.settimeout(8)
        self.assertEqual(self.response(client)[0], 408)
        self.assertGreaterEqual(time.monotonic() - started, 9)
        self.assertLess(time.monotonic() - started, 12)
        self.capabilities()

    def test_header_bytes_and_body_sizes_have_independent_caps(self):
        client = self.connect(b"GET /api/v1/capabilities HTTP/1.1\r\n" +
                              (b"X-Padding: " + b"x" * 1000 + b"\r\n") * 66 + b"\r\n")
        self.assertEqual(self.response(client)[0], 431)
        for path, size, expected in [("/api/v1/watch/command", 1024 * 1024 + 1, 413),
                                     ("/api/v1/shortcuts/command", 1024 * 1024 + 1, 413),
                                     ("/api/v1/push/register", 1024 * 1024 + 1, 413),
                                     ("/api/v1/sessions/message", 96001, 400)]:
            with self.subTest(path=path):
                client = self.connect(self.headers(path, f"Content-Length: {size}\r\n"))
                self.assertEqual(self.response(client)[0], expected)
        self.capabilities()

    def test_eight_connections_bound_workers_and_release_after_disconnect(self):
        self.assertEqual(self.transport.MAX_CONNECTIONS, 8)
        for _ in range(8):
            self.connect(b"GET /api/v1/capabilities HTTP/1.1\r\nX-Pending: ")
        deadline = time.monotonic() + 2
        while self.server._connections._value and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server._connections._value, 0)
        self.assertEqual(len(self.server._threads), 8)
        refused = self.connect(b"")
        self.assertEqual(self.response(refused)[0], 503)
        self.assertEqual(len(self.server._threads), 8, "Refused peers must not create waiting threads")
        for client in self.clients:
            client.shutdown(socket.SHUT_RDWR)
            client.close()
        self.clients.clear()
        deadline = time.monotonic() + 2
        while self.server._connections._value != 8 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.server._connections._value, 8)
        self.capabilities()


class HTTPConcurrencyTests(HTTPFixture):
    def setUp(self):
        super().setUp()
        self.invoke, self.transcribe = self.forbidden[:2]
        del self.forbidden[:2]
        self.transcribe.side_effect = None
        self.transcribe.return_value = SimpleNamespace(transcript="fixture command", source="test", error="")
        self.invoke.side_effect = lambda payload: SimpleNamespace(
            process=SimpleNamespace(poll=lambda: None), log_path=str(self.main.STATE_DIR / "not-created.log"),
            prompt="fixture", command=["never-executed"], started_at=time.time())
        self.payload = {"audio_data": "ZmFrZQ==", "format": "m4a"}

    def test_simultaneous_same_audio_and_lost_reply_dispatch_only_once(self):
        entered, release = threading.Event(), threading.Event()

        def transcribe(payload):
            entered.set()
            if not release.wait(3):
                raise AssertionError("Owned STT gate was not released")
            return SimpleNamespace(transcript="fixture command", source="test", error="")

        self.transcribe.side_effect = transcribe
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.http, "POST", "/api/v1/watch/command", self.payload)
            try:
                self.assertTrue(entered.wait(1))
                second = pool.submit(self.http, "POST", "/api/v1/watch/command", self.payload)
                self.capabilities()
            finally:
                release.set()
            responses = [first.result(), second.result()]
        self.assertEqual([status for status, _ in responses], [200, 200])
        self.assertEqual(responses[0][1]["job_id"], responses[1][1]["job_id"])
        self.invoke.assert_called_once()
        self.transcribe.assert_called_once()
        # Drop a real reply, then replay identical audio through the same owner.
        wire = json.dumps(self.payload).encode()
        abandoned = self.connect(self.headers("/api/v1/watch/command", f"Content-Length: {len(wire)}\r\n") + wire)
        abandoned.shutdown(socket.SHUT_RDWR)
        abandoned.close()
        status, replay = self.http("POST", "/api/v1/watch/command", self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(replay["job_id"], responses[0][1]["job_id"])
        self.invoke.assert_called_once()
        stored = json.loads(self.main.JOBS_STATE_PATH.read_text(encoding="utf-8"))["jobs"]
        self.assertEqual(len(stored), 1)
        self.assertIn("audio_fingerprint", stored[0])

    def test_slow_stt_seven_full_uploads_refuse_promptly_and_polling_recovers(self):
        entered, release = threading.Event(), threading.Event()

        def slow(payload):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Owned STT gate was not released")
            return SimpleNamespace(transcript="fixture", source="test", error="")

        self.transcribe.side_effect = slow
        with ThreadPoolExecutor(max_workers=8) as pool:
            first = pool.submit(self.http, "POST", "/api/v1/watch/command", self.payload, 6)
            try:
                self.assertTrue(entered.wait(1))
                self.capabilities()
                started = time.monotonic()
                waiting = [pool.submit(self.http, "POST", "/api/v1/watch/command", self.payload) for _ in range(7)]
                self.assertEqual([future.result()[0] for future in waiting], [503] * 7)
                self.assertLess(time.monotonic() - started, 2.5)
                self.capabilities()
                self.assertEqual(self.http("GET", "/api/v1/jobs/active"), (200, {"jobs": []}))
                self.invoke.assert_not_called()
            finally:
                release.set()
            self.assertEqual(first.result()[0], 200)
        self.invoke.assert_called_once()

    def test_same_audio_different_explicit_parents_remains_distinct(self):
        for parent_id in ("job-parent-a", "job-parent-b"):
            self.main.remember_job({"id": parent_id, "conversation_id": parent_id, "created_at": 0,
                                    "status": "completed", "watch_summary": "fixture parent", "transcript": "earlier"})
        results = [self.http("POST", "/api/v1/watch/command", {**self.payload, "continue_job_id": parent})
                   for parent in ("job-parent-a", "job-parent-b")]
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertNotEqual(results[0][1]["job_id"], results[1][1]["job_id"])
        self.assertEqual(self.invoke.call_count, 2)

    def test_concurrent_shortcuts_and_job_polling_preserve_every_persisted_job(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(self.http, "POST", "/api/v1/shortcuts/command", {"text": f"fixture {index}"})
                       if index % 2 else pool.submit(self.http, "GET", "/api/v1/jobs/active") for index in range(32)]
            responses = [future.result() for future in futures]
        self.assertEqual([status for status, _ in responses], [200] * 32)
        self.assertEqual(self.invoke.call_count, 16)
        self.assertEqual(len(self.main.jobs_db), 16)
        stored = json.loads(self.main.JOBS_STATE_PATH.read_text(encoding="utf-8"))["jobs"]
        self.assertEqual({job["id"] for job in stored}, set(self.main.jobs_db))

    def test_push_network_does_not_hold_jobs_lock_or_overwrite_new_state(self):
        self.main.remember_job({"id": "job-push", "name": "fixture", "elapsed_seconds": 0,
                               "created_at": 0, "status": "completed", "watch_summary": "old"})
        entered, release = threading.Event(), threading.Event()

        def notify(snapshot):
            entered.set()
            if not release.wait(3):
                raise AssertionError("Owned push gate was not released")
            snapshot.update(push_notification_sent_at=1, push_notification_apns_id="fixture")
            return True

        with patch.object(self.main.push_notifier, "notify_terminal_job", side_effect=notify), \
             ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.main.notify_jobs_once)
            try:
                self.assertTrue(entered.wait(1))
                self.capabilities()
                self.assertEqual(self.http("GET", "/api/v1/jobs/active")[0], 200)
                with self.main.jobs_lock:
                    self.main.jobs_db["job-push"]["watch_summary"] = "new"
            finally:
                release.set()
            pending.result()
        self.assertEqual(self.main.jobs_db["job-push"]["watch_summary"], "new")
        self.assertEqual(self.main.jobs_db["job-push"]["push_notification_apns_id"], "fixture")

    def test_server_close_joins_owned_stt_worker_after_work_is_released(self):
        entered, release, closing = threading.Event(), threading.Event(), threading.Event()

        def slow(payload):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Owned STT gate was not released")
            return SimpleNamespace(transcript="fixture", source="test", error="")

        def close_server():
            self.server.shutdown()
            closing.set()
            self.server.server_close()

        self.transcribe.side_effect = slow
        with ThreadPoolExecutor(max_workers=2) as pool:
            request = pool.submit(self.http, "POST", "/api/v1/watch/command", self.payload, 6)
            try:
                self.assertTrue(entered.wait(1))
                workers = list(self.server._threads)
                stopped = pool.submit(close_server)
                self.assertTrue(closing.wait(1))
                self.assertFalse(stopped.done(), "Do not hide active STT behind abandoned daemon workers")
            finally:
                release.set()
            self.assertEqual(request.result()[0], 200)
            stopped.result(timeout=2)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
