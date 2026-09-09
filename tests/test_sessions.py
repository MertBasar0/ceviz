"""Gateway conversation boundary tests; no real model or user Gateway calls."""
import io
import http.client
import json
import socket
import subprocess
import sys
import unittest
import threading
import time
from urllib import request, error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import session_api


KEY = "agent:writer:main"
RUN = "43104842-292e-48b0-bc84-55b4335b28ae"


def snapshot(**changes):
    return {
        "sessionKey": KEY, "sessionId": "physical-1", "messages": [],
        "sessionInfo": {"key": KEY, "sessionId": "physical-1", "derivedTitle": "Travel plan",
                        "activeLeafEntryId": "leaf-1", "hasActiveRun": False},
        "pendingInputs": {"items": [], "total": 0},
        "hasMore": False, **changes,
    }


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.api = session_api.OpenClawSessions()

    def test_roster_reuses_tui_window_titles_and_gateway_order(self):
        rows = [
            {"key": "agent:writer:two", "derivedTitle": "First", "updatedAt": 4},
            {"key": KEY, "derivedTitle": "Second", "displayName": "Wrong title", "updatedAt": 8},
        ]
        with patch.object(session_api, "call_gateway", side_effect=[
            {"sessions": rows, "hasMore": True}, {"agents": [{"id": "writer", "name": "Writer"}]},
        ]) as rpc:
            result = self.api.list_sessions({"agent_id": ["writer"]})
        self.assertEqual([row["title"] for row in result["sessions"]], ["First", "Second"])
        self.assertEqual(result["next_offset"], 2)
        self.assertEqual(result["agents"], [{"id": "writer", "name": "Writer"}])
        self.assertEqual(rpc.call_args_list[0].args, ("sessions.list", {
            "limit": 50, "offset": 0, "includeGlobal": False, "includeUnknown": False,
            "includeDerivedTitles": True, "includeLastMessage": True,
            "activeMinutes": 10080, "agentId": "writer",
        }))

    def test_older_window_does_not_silently_keep_seven_day_filter(self):
        with patch.object(session_api, "call_gateway", side_effect=[
            {"sessions": [], "hasMore": False}, {"agents": []},
        ]) as rpc:
            self.api.list_sessions({"older": ["true"], "offset": ["50"]})
        self.assertNotIn("activeMinutes", rpc.call_args_list[0].args[1])
        self.assertEqual(rpc.call_args_list[0].args[1]["offset"], 50)

    def test_search_is_forwarded_with_window_and_page_not_just_first_page_filter(self):
        with patch.object(session_api, "call_gateway", side_effect=[
            {"sessions": [], "hasMore": False}, {"agents": []},
        ]) as rpc:
            self.api.list_sessions({"search": ["  route notes  "], "offset": ["50"], "older": ["true"]})
        params = rpc.call_args_list[0].args[1]
        self.assertEqual(params["search"], "route notes")
        self.assertEqual(params["offset"], 50)
        self.assertNotIn("activeMinutes", params)

    def test_invalid_page_and_window_fail_before_any_gateway_request(self):
        for query in [{"offset": ["-1"]}, {"offset": ["NaN"]}, {"offset": ["1000001"]},
                      {"older": ["all"]}, {"search": ["a" * 201]}]:
            with self.subTest(query=query), patch.object(session_api, "call_gateway") as rpc:
                with self.assertRaises(session_api.SessionError):
                    self.api.list_sessions(query)
            rpc.assert_not_called()

    def test_bare_owner_and_empty_session_are_rejected_before_gateway(self):
        with patch.object(session_api, "call_gateway") as rpc:
            for key in ["main", "agent::main", "agent:writer:", " agent:writer:main", "agent:writer:x\n"]:
                with self.subTest(key=key), self.assertRaises(session_api.SessionError):
                    self.api.history({"session_key": [key]})
        rpc.assert_not_called()

    def test_history_keeps_conversation_identity_order_and_older_cursor(self):
        upstream = snapshot(messages=[
            {"role": "user", "content": "Question", "timestamp": 100,
             "__openclaw": {"id": "m1"}},
            {"role": "toolResult", "content": "Internal tool payload"},
            {"role": "assistant", "content": [{"type": "thinking", "thinking": "private reasoning"},
                                                   {"type": "text", "text": "Answer"}],
             "__openclaw": {"id": "m2"}},
        ], hasMore=True, nextOffset=101)
        with patch.object(session_api, "call_gateway", return_value=upstream) as rpc:
            result = self.api.history({"session_key": [KEY]})
        self.assertEqual(result["session"]["session_key"], KEY)
        self.assertEqual(result["session"]["session_id"], "physical-1")
        self.assertEqual([row["text"] for row in result["messages"]], ["Question", "Answer"])
        self.assertNotIn("private reasoning", json.dumps(result))
        self.assertNotIn("Internal tool payload", json.dumps(result))
        self.assertTrue(result["messages"][1]["has_other_content"])
        self.assertEqual(result["next_offset"], 101)
        rpc.assert_called_once_with("chat.history", {
            "sessionKey": KEY, "agentId": "writer", "limit": 100, "offset": 0,
        })

    def test_history_for_deleted_or_rerouted_session_is_not_new_conversation(self):
        for changes in [{"sessionId": None}, {"sessionKey": "agent:other:main"}]:
            with self.subTest(changes=changes), patch.object(session_api, "call_gateway", return_value=snapshot(**changes)):
                with self.assertRaises(session_api.SessionError):
                    self.api.history({"session_key": [KEY]})

    def test_cli_timeout_is_uncertain_only_for_a_possible_send(self):
        for method, uncertain in [("sessions.list", False), ("chat.send", True)]:
            with self.subTest(method=method), patch.object(session_api.subprocess, "run", side_effect=subprocess.TimeoutExpired("openclaw", 12)) as run:
                with self.assertRaises(session_api.SessionError) as caught:
                    session_api.call_gateway(method, {})
                self.assertEqual(caught.exception.uncertain, uncertain)
                run.assert_called_once()

    def test_cli_error_does_not_leak_diagnostics_or_replay_the_message(self):
        for output in ['{"error":{"message":"private transcript and token"}}', 'not json private token']:
            with self.subTest(output=output), patch.object(session_api.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout=output, stderr="secret")) as run:
                with self.assertRaises(session_api.SessionError) as caught:
                    session_api.call_gateway("chat.send", {"message": "sensitive text"})
                self.assertTrue(caught.exception.uncertain)
                self.assertNotIn("private", str(caught.exception))
                self.assertNotIn("token", str(caught.exception))
                run.assert_called_once()

    def test_missing_cli_is_definitely_not_sent(self):
        with patch.object(session_api.subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(session_api.SessionError) as caught:
                session_api.call_gateway("chat.send", {})
        self.assertFalse(caught.exception.uncertain)

    def message(self, **changes):
        return {"session_key": KEY, "session_id": "physical-1", "expected_leaf_entry_id": "leaf-1",
                "text": "Continue the travel plan", "request_id": RUN, **changes}

    def accept(self, **changes):
        with patch.object(session_api, "call_gateway", side_effect=[snapshot(), {"runId": RUN, "status": "started"}]):
            return self.api.send_message(self.message(**changes))

    def test_send_targets_real_session_with_explicit_leaf_and_followup_queue(self):
        with patch.object(session_api, "call_gateway", side_effect=[snapshot(), {"runId": RUN, "status": "started"}]) as rpc:
            result = self.api.send_message(self.message(expected_leaf_entry_id=None))
        self.assertTrue(result["delivery_confirmed"])
        rpc.assert_called_with("chat.send", {
            "sessionKey": KEY, "agentId": "writer", "sessionId": "physical-1", "expectedLeafEntryId": None,
            "message": "Continue the travel plan", "idempotencyKey": RUN, "queueMode": "followup",
        })
        self.assertEqual(len(rpc.call_args_list), 2)

    def test_reset_and_archive_are_not_silently_new_jobs(self):
        for upstream in [snapshot(sessionId="reset-session"), snapshot(sessionInfo={"archived": True})]:
            with self.subTest(upstream=upstream), patch.object(session_api, "call_gateway", return_value=upstream) as rpc:
                with self.assertRaises(session_api.SessionError):
                    self.api.send_message(self.message())
                rpc.assert_called_once()

    def test_missing_guard_invalid_identity_or_control_never_sends(self):
        missing_leaf = self.message()
        del missing_leaf["expected_leaf_entry_id"]
        for payload in [missing_leaf, self.message(request_id=""), self.message(session_id=""),
                        self.message(text=""), self.message(text="x" * 16001),
                        self.message(text="/reset"), self.message(text="STOP!"),
                        self.message(text="Please   stop…"), self.message(text="arrête!"),
                        self.message(text="stop don’t do anything"),
                        self.message(text="arre\u0302te!"), self.message(text="st\x07op"),
                        self.message(text="st\x7fop"), self.message(text="\ufeffstop"),
                        self.message(text="\ufeff/reset"), self.message(text="\x00")]:
            with self.subTest(payload=payload), patch.object(session_api, "call_gateway") as rpc:
                with self.assertRaises(session_api.SessionError):
                    self.api.send_message(payload)
                rpc.assert_not_called()

    def test_same_uuid_is_not_resent_and_conflicting_body_is_rejected(self):
        original = self.accept()
        with patch.object(session_api, "call_gateway") as rpc:
            self.assertEqual(self.api.send_message(self.message()), original)
            with self.assertRaises(session_api.SessionError) as caught:
                self.api.send_message(self.message(text="Do something else"))
            self.assertEqual(caught.exception.code, "message_identity_conflict")
            rpc.assert_not_called()

    def test_lost_acceptance_keeps_binding_and_does_not_dispatch_again(self):
        with patch.object(session_api, "call_gateway", side_effect=[snapshot(), session_api.SessionError("gateway_unavailable", "Unknown", 503, uncertain=True)]):
            with self.assertRaises(session_api.SessionError):
                self.api.send_message(self.message())
        with patch.object(session_api, "call_gateway") as rpc:
            result = self.api.send_message(self.message())
        self.assertFalse(result["delivery_confirmed"])
        self.assertEqual(result["status"], "unconfirmed")
        rpc.assert_not_called()

    def test_terminal_cli_run_needs_no_ui_history_receipt_and_never_regresses(self):
        self.accept()
        with patch.object(session_api, "call_gateway", side_effect=[snapshot(), {"runId": RUN, "status": "ok", "endedAt": 100}]) as rpc:
            result = self.api.run_status({"session_key": [KEY], "run_id": [RUN]})
        self.assertEqual(result["status"], "completed")
        self.assertEqual(rpc.call_args_list[-1].args, ("agent.wait", {"runId": RUN, "timeoutMs": 0}))
        with patch.object(session_api, "call_gateway") as rpc:
            self.assertEqual(self.api.run_status({"session_key": [KEY], "run_id": [RUN]}), result)
            rpc.assert_not_called()

    def test_wait_timeouts_are_not_automatically_failed_and_queue_is_not_completed(self):
        self.accept()
        for wait, expected in [
            ({"status": "timeout"}, "unconfirmed"),
            ({"status": "ok", "endedAt": True}, "unconfirmed"),
            ({"status": "ok", "endedAt": float("nan")}, "unconfirmed"),
            ({"status": "ok", "endedAt": float("inf")}, "unconfirmed"),
            ({"status": "timeout", "endedAt": 200}, "failed"),
            ({"status": "pending", "providerStarted": False}, "queued"),
            ({"status": "error", "endedAt": 200, "stopReason": "aborted"}, "aborted"),
        ]:
            self.api.submissions[RUN].terminal_result = None
            with self.subTest(wait=wait), patch.object(session_api, "call_gateway", side_effect=[snapshot(), {"runId": RUN, **wait}]):
                self.assertEqual(self.api.run_status({"session_key": [KEY], "run_id": [RUN]})["status"], expected)

    def test_wrong_session_terminal_receipt_is_not_completion(self):
        self.accept()
        with patch.object(session_api, "call_gateway", side_effect=[snapshot(), {
            "runId": RUN, "status": "ok", "endedAt": 100,
            "terminalReceipt": {"runId": RUN, "sessionId": "different-session"},
        }]):
            self.assertEqual(self.api.run_status({"session_key": [KEY], "run_id": [RUN]})["status"], "unconfirmed")

    def test_unknown_run_without_owner_is_not_read_from_another_session(self):
        with patch.object(session_api, "call_gateway", return_value=snapshot()) as rpc:
            self.assertEqual(self.api.run_status({"session_key": [KEY], "run_id": [RUN]})["status"], "unconfirmed")
        rpc.assert_called_once()
        self.accept()
        with patch.object(session_api, "call_gateway") as rpc:
            with self.assertRaises(session_api.SessionError):
                self.api.run_status({"session_key": ["agent:else:main"], "run_id": [RUN]})
        rpc.assert_not_called()

    def test_capacity_never_retires_an_identity_then_replays_it(self):
        for index in range(512):
            self.api.submissions[str(index)] = session_api.Submission(KEY, "physical-1", "fingerprint",
                terminal_result={"status": "completed"})
        with patch.object(session_api, "call_gateway", return_value=snapshot()) as rpc:
            with self.assertRaises(session_api.SessionError) as caught:
                self.api.send_message(self.message())
        self.assertEqual(caught.exception.code, "request_capacity")
        self.assertEqual(len(self.api.submissions), 512)
        rpc.assert_called_once()


class ConversationHTTPTests(unittest.TestCase):
    def setUp(self):
        import main
        self.main = main
        self.auth = patch.object(main, "AUTH_TOKEN", "ceviz-test-only")
        self.api = patch.object(session_api, "sessions_api", session_api.OpenClawSessions())
        self.auth.start()
        self.api.start()
        self.server = main.HTTPServer(("127.0.0.1", 0), main.WatchCevizHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.api.stop()
        self.auth.stop()

    def http(self, path, *, method="GET", body=None, authorized=True):
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer ceviz-test-only"
        req = request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            response = request.urlopen(req, timeout=3)
        except error.HTTPError as exc:
            response = exc
        with response:
            if authorized:
                self.assertIsNotNone(response.headers.get("Content-Length"),
                                     "Bounded responses must not rely on EOF after rejecting an unread body")
                self.assertEqual(response.headers.get("Connection"), "close")
            data = response.read()
            if authorized:
                self.assertEqual(int(response.headers["Content-Length"]), len(data))
            return response.status, json.loads(data)

    def test_all_conversation_endpoints_share_the_existing_bearer_boundary(self):
        with patch.object(session_api, "call_gateway") as rpc:
            for path, method in [("/api/v1/sessions", "GET"), ("/api/v1/sessions/history", "GET"),
                                 ("/api/v1/sessions/run", "GET"), ("/api/v1/sessions/message", "POST")]:
                status, _ = self.http(path, method=method, body=b"{}" if method == "POST" else None, authorized=False)
                self.assertEqual(status, 401)
            rpc.assert_not_called()

    def test_wire_submit_targets_selected_session_and_does_not_create_ceviz_job(self):
        payload = {"session_key": KEY, "session_id": "physical-1", "expected_leaf_entry_id": None,
                   "request_id": RUN, "text": "Continue the route notes"}
        original_jobs = set(self.main.jobs_db)
        with patch.object(session_api, "call_gateway", side_effect=[snapshot(), {"runId": RUN, "status": "started"}]) as rpc:
            status, result = self.http("/api/v1/sessions/message", method="POST", body=json.dumps(payload).encode())
        self.assertEqual(status, 200)
        self.assertEqual(result["run_id"], RUN)
        self.assertEqual(rpc.call_args_list[-1].args[1]["sessionKey"], KEY)
        self.assertEqual(set(self.main.jobs_db), original_jobs)

    def test_bad_message_shapes_and_oversized_body_have_safe_errors(self):
        with patch.object(session_api, "call_gateway") as rpc:
            for body in [b"not-json", b"null", b"[]", b"{}", b"x" * 96001]:
                with self.subTest(body_size=len(body)):
                    status, result = self.http("/api/v1/sessions/message", method="POST", body=body)
                    self.assertEqual(status, 400)
                    self.assertFalse(result["delivery_uncertain"])
                    self.assertIn("code", result)
            rpc.assert_not_called()

    def test_incomplete_oversized_body_cannot_hold_the_service_open(self):
        with patch.object(session_api, "call_gateway") as rpc:
            with socket.create_connection(self.server.server_address, timeout=3) as client:
                client.sendall(b"POST /api/v1/sessions/message HTTP/1.1\r\n"
                               b"Host: localhost\r\nAuthorization: Bearer ceviz-test-only\r\n"
                               b"Content-Type: application/json\r\nContent-Length: 96001\r\n\r\n")
                # Keep the sending socket open without its declared body.
                with http.client.HTTPResponse(client) as response:
                    response.begin()
                    self.assertEqual(response.status, 400)
                    self.assertEqual(response.headers.get("Connection"), "close")
                    self.assertEqual(json.load(response)["code"], "invalid_request")
                status, _ = self.http("/api/v1/sessions/not-a-route")
                self.assertEqual(status, 404, "The single-threaded server can handle its next request")
            rpc.assert_not_called()

    def test_trickling_oversized_body_has_a_total_drain_deadline(self):
        with patch.object(session_api, "call_gateway") as rpc:
            with socket.create_connection(self.server.server_address, timeout=2) as client:
                client.sendall(b"POST /api/v1/sessions/message HTTP/1.1\r\n"
                               b"Host: localhost\r\nAuthorization: Bearer ceviz-test-only\r\n"
                               b"Content-Length: 96001\r\n\r\n")
                stop = threading.Event()

                def trickle():
                    while not stop.wait(0.05):
                        try:
                            client.sendall(b"x")
                        except OSError:
                            return

                sender = threading.Thread(target=trickle, daemon=True)
                sender.start()
                started = time.monotonic()
                try:
                    with http.client.HTTPResponse(client) as response:
                        response.begin()
                        self.assertEqual(response.status, 400)
                        self.assertEqual(json.load(response)["code"], "invalid_request")
                    self.assertLess(time.monotonic() - started, 1.5,
                                    "Incoming bytes must not renew the rejected body's drain budget")
                finally:
                    stop.set()
                    sender.join(timeout=1)
                status, _ = self.http("/api/v1/sessions/not-a-route")
                self.assertEqual(status, 404)
            rpc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
