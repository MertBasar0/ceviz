"""Synthetic retained-log audit tests; no app, simulator, network, or release."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import watch_touch_audit as audit


def metadata():
    run = {"id": audit.RUN_ID, "head_sha": audit.SOURCE_SHA, "head_branch": audit.BRANCH,
           "status": "completed", "conclusion": "failure", "event": "workflow_dispatch",
           "repository": {"full_name": audit.REPOSITORY}}
    artifact = {"id": audit.ARTIFACT_ID, "name": audit.ARTIFACT_NAME,
                "size_in_bytes": audit.ARTIFACT_SIZE, "expired": False,
                "workflow_run": {"id": audit.RUN_ID, "head_sha": audit.SOURCE_SHA, "head_branch": audit.BRANCH}}
    return run, artifact


def line(message, process="testmanagerd", pid=1234, timestamp="2026-09-19 19:04:44.000"):
    return f"{timestamp} Df {process}[{pid}:abcd] {message}"


class ProvenanceTests(unittest.TestCase):
    def test_exact_failed_source_only(self):
        self.assertEqual(audit.verify_metadata(*metadata()), audit.provenance_record())
        for target, key, bad in [(0, "head_sha", "newer-head-not-the-failure"),
                                 (0, "id", audit.RUN_ID + 1), (0, "conclusion", "success"),
                                 (1, "id", audit.ARTIFACT_ID + 1), (1, "expired", True),
                                 (1, "size_in_bytes", audit.ARTIFACT_SIZE + 1)]:
            pair = metadata()
            pair[target][key] = bad
            with self.subTest(key=key), self.assertRaises(audit.AuditFailure):
                audit.verify_metadata(*pair)

    def test_repository_and_artifact_owner_cannot_change(self):
        run, artifact = metadata()
        run["repository"]["full_name"] = "other/private"
        with self.assertRaisesRegex(audit.AuditFailure, "repository_mismatch"):
            audit.verify_metadata(run, artifact)
        for key, value in [("id", 1), ("head_sha", "other"), ("head_branch", "main")]:
            run, artifact = metadata()
            artifact["workflow_run"][key] = value
            with self.assertRaisesRegex(audit.AuditFailure, "owner_mismatch"):
                audit.verify_metadata(run, artifact)

    def test_only_fixed_metadata_endpoints_and_bounded_response(self):
        with patch.object(audit.urllib.request, "build_opener") as opener:
            with self.assertRaisesRegex(audit.AuditFailure, "unapproved_metadata_endpoint"):
                audit.github_json("arbitrary", "secret")
            opener.assert_not_called()
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b"x" * (audit.MAX_API_BYTES + 1)
            with self.assertRaisesRegex(audit.AuditFailure, "metadata_exceeds_bound"):
                audit.github_json(f"actions/runs/{audit.RUN_ID}", "secret")
            response.read.assert_called_once_with(audit.MAX_API_BYTES + 1)
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 30)


class ArchiveOwnerTests(unittest.TestCase):
    def test_only_exact_finish_bundle_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "other.xcresult").mkdir()
            with self.assertRaisesRegex(audit.AuditFailure, "exact_result_missing"):
                audit.select_result(root)
            expected = root / "after" / audit.BUNDLE_NAME
            expected.mkdir(parents=True)
            self.assertEqual(audit.select_result(root), expected)
            (root / "duplicate" / audit.BUNDLE_NAME).mkdir(parents=True)
            with self.assertRaisesRegex(audit.AuditFailure, "ambiguous"):
                audit.select_result(root)

    def test_exact_watch_token_and_unique_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("iPhone_other", "watch_" + audit.WATCH_UDID + "F"):
                (root / name / "system.logarchive").mkdir(parents=True)
            with self.assertRaisesRegex(audit.AuditFailure, "missing_or_ambiguous"):
                audit.select_watch_archive(root)
            expected = root / ("Watch_" + audit.WATCH_UDID) / "simctl_diagnostics" / "system.logarchive"
            expected.mkdir(parents=True)
            self.assertEqual(audit.select_watch_archive(root), expected)
            (root / ("other_" + audit.WATCH_UDID) / "system.logarchive").mkdir(parents=True)
            with self.assertRaisesRegex(audit.AuditFailure, "ambiguous"):
                audit.select_watch_archive(root)

    def test_symlink_cannot_claim_an_archive_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "real"
            target.mkdir()
            link = root / ("Watch_" + audit.WATCH_UDID) / "system.logarchive"
            link.parent.mkdir()
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("OS does not allow creating a synthetic symlink")
            with self.assertRaisesRegex(audit.AuditFailure, "symlink_or_reparse"):
                audit.select_watch_archive(root)

    def test_outside_owner_and_mock_reparse_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(audit.AuditFailure, "outside_owner"):
                audit.plain_path(root.parent, root)
            with patch.object(audit.stat, "S_ISLNK", return_value=True):
                with self.assertRaisesRegex(audit.AuditFailure, "symlink_or_reparse"):
                    audit.plain_path(root, root)

    def test_platform_ancestor_alias_outside_owned_root_is_not_an_internal_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            actual = parent / "platform"
            root = actual / "owned"
            root.mkdir(parents=True)
            alias = parent / "alias"
            try:
                alias.symlink_to(actual, target_is_directory=True)
            except OSError:
                self.skipTest("OS does not allow creating a synthetic ancestor alias")
            through_alias = alias / "owned"
            candidate = through_alias / "new-file"
            self.assertEqual(audit.plain_path(candidate, through_alias), candidate)
            with self.assertRaisesRegex(audit.AuditFailure, "symlink_or_reparse"):
                audit.plain_path(alias, alias)


class PrivacyProjectionTests(unittest.TestCase):
    def project(self, *rows):
        return audit.project_events("\n".join(rows).encode(), audit.WINDOWS[1])

    def test_app_handler_and_closed_schema_never_export_message(self):
        secret = "https://private.example/pair?token=secret-transcript"
        proof = self.project(line("[com.mertbasar.ceviz.watch:AudioCapture] Capture event: primary_action "
                                  "recording=false scene=active " + secret, "CevizWatchApp", audit.APP_PID),
                             line("TouchEventsCompleted " + secret, "unrelated", 1234))
        self.assertEqual(proof["event_counts"]["app_primary_action"], 1)
        self.assertEqual(proof["events"][0]["target_app_correlation"], "process_identity")
        output = json.dumps(proof)
        for forbidden in (secret, "recording=false", "scene=active", "transcript", "private.example"):
            self.assertNotIn(forbidden, output)

    def test_wrong_pid_bad_timestamp_and_outside_window_are_not_evidence(self):
        message = "[com.mertbasar.ceviz.watch:AudioCapture] Capture event: primary_action"
        proof = self.project(line(message, "CevizWatchApp", audit.APP_PID + 1),
                             line(message, "CevizWatchApp", audit.APP_PID, "2026-09-19 19:03:20.000"),
                             line(message, "CevizWatchApp", audit.APP_PID, "2026-99-99 19:04:44.000"),
                             "unrecognized secret-body")
        self.assertEqual(proof["events"], [])
        self.assertEqual(proof["status"], "no_matching_records")

    def test_quoted_app_marker_is_not_an_acknowledged_handler(self):
        proof = self.project(line("unrelated quoted marker: [com.mertbasar.ceviz.watch:AudioCapture] "
                                  "Capture event: primary_action", "CevizWatchApp", audit.APP_PID))
        self.assertEqual(proof["events"], [])
        self.assertEqual(proof["status"], "no_classified_events")

    def test_header_only_or_format_drift_cannot_report_collected(self):
        for payload in (b"", b"Timestamp OtherColumns\n", b"unrecognized secret-raw-format\n"):
            proof = audit.project_events(payload, audit.WINDOWS[1])
            self.assertEqual(proof["status"], "no_matching_records")
            self.assertNotIn("secret", json.dumps(proof))

    def test_registration_wait_and_multiline_notification_are_distinct(self):
        proof = self.project(
            line("Registering for user testing event TouchEventsCompleted"),
            line("Waiting up to 5.0s for TouchEventsCompleted to be received"),
            line("Got user testing notification with {\n    event = TouchEventsCompleted;\n    secret = do-not-export;\n}"),
        )
        self.assertEqual(proof["event_counts"].get("native_touch_completion_acknowledgement"), 1)
        self.assertNotIn("do-not-export", json.dumps(proof))
        self.assertEqual(len(proof["events"]), 3)

    def test_synthesis_cancellation_and_ack_can_coexist_without_delivery_verdict(self):
        proof = self.project(
            line("Synthesizing event with {\n Touch down;\n Touch up;\n secret = hidden;\n}"),
            line("cancel -- digitizer did disappear: hidden", "backboardd"),
            line("Got user testing notification with {\n event = TouchEventsCompleted;\n}"),
        )
        counts = proof["event_counts"]
        self.assertEqual(counts.get("native_event_synthesis_log"), 1)
        self.assertEqual(counts.get("native_digitizer_disappeared"), 1)
        self.assertEqual(counts.get("native_touch_completion_acknowledgement"), 1)
        self.assertNotIn("delivered", proof)
        self.assertNotIn("hidden", json.dumps(proof))

    def test_negative_destination_and_service_cancellation_are_not_touch_delivery_failure(self):
        proof = self.project(line("not removing destination secret", "backboardd"),
                             line("service canceled: (secret digitizer)", "testmanagerd"))
        self.assertNotIn("native_touch_delivery_log", proof["event_counts"])
        self.assertNotIn("native_touch_cancellation_log", proof["event_counts"])

    def test_bounds_encoding_and_unapproved_window_fail_closed(self):
        for payload, reason in [(b"x" * (audit.MAX_QUERY_BYTES + 1), "exceeds_4_mib"),
                                (b"\xff", "encoding_unrecognized")]:
            with self.assertRaisesRegex(audit.AuditFailure, reason):
                audit.project_events(payload, audit.WINDOWS[1])
        with self.assertRaisesRegex(audit.AuditFailure, "unapproved_time_window"):
            audit.project_events(b"", ("wide", "2026-09-19 19:00:00", "2026-09-19 20:00:00"))
        payload = (line("Synthesizing event with") + "\n").encode() * (audit.MAX_EVENTS + 1)
        with self.assertRaisesRegex(audit.AuditFailure, "event_limit_exceeded"):
            audit.project_events(payload, audit.WINDOWS[1])


class NativeReadIsolationTests(unittest.TestCase):
    def test_exact_export_archive_and_two_windows_without_app_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / audit.BUNDLE_NAME).mkdir()
            commands = []

            def run(command, **kwargs):
                commands.append((command, kwargs))
                if command[:4] == ["xcrun", "xcresulttool", "export", "diagnostics"]:
                    native = Path(command[-1])
                    (native / ("Watch_" + audit.WATCH_UDID) / "system.logarchive").mkdir(parents=True)
                else:
                    start = command[command.index("--start") + 1]
                    kwargs["stdout"].write(line("Synthesizing event with", timestamp=start[:-5] + ".000").encode())
                return subprocess.CompletedProcess(command, 0)

            with patch.object(audit.subprocess, "run", side_effect=run):
                proof = audit.inspect(root, audit.provenance_record())
            self.assertEqual(proof["original_gate_result"], "failure_not_waived")
            self.assertEqual(len(proof["windows"]), 2)
            self.assertEqual(len(commands), 3)
            self.assertFalse(Path(commands[0][0][-1]).exists(), "Owned raw export must be removed")
            for (command, kwargs), window in zip(commands[1:], audit.WINDOWS):
                self.assertEqual(command[:2], ["/usr/bin/log", "show"])
                self.assertIn(window[1] + "+0000", command)
                self.assertIn(window[2] + "+0000", command)
                self.assertEqual(command[-1], audit.PREDICATE)
                self.assertEqual(kwargs["timeout"], 45)
                self.assertIs(kwargs["stderr"], subprocess.DEVNULL)

    def test_empty_window_preserves_both_projections_but_inspection_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / audit.BUNDLE_NAME).mkdir()
            first = audit.project_events(line("Synthesizing event with", timestamp="2026-09-19 19:03:20.000").encode(), audit.WINDOWS[0])
            second = audit.project_events(b"", audit.WINDOWS[1])
            with patch.object(audit.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(audit, "select_watch_archive", return_value=root), \
                    patch.object(audit, "query_window", side_effect=[first, second]):
                proof = audit.inspect(root, audit.provenance_record())
            self.assertEqual(proof["status"], "unavailable")
            self.assertEqual(proof["windows"], [first, second])

    def test_empty_evidence_is_written_but_cli_returns_failure(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "OUTPUT_ROOT", Path(temporary)), \
                patch.object(audit, "plain_path", side_effect=lambda path, root: path), \
                patch.object(audit, "inspect", return_value={"status": "unavailable", "windows": []}), \
                patch("sys.argv", ["audit", "inspect"]), contextlib.redirect_stdout(io.StringIO()) as output:
            (Path(temporary) / "provenance.json").write_text(json.dumps(audit.provenance_record()))
            self.assertEqual(audit.main(), 1)
            self.assertEqual(json.loads((Path(temporary) / "touch-evidence.json").read_text())["status"], "unavailable")
        self.assertEqual(json.loads(output.getvalue())["status"], "unavailable")

    def test_unverified_provenance_prevents_all_native_calls(self):
        with patch.object(audit.subprocess, "run") as run:
            with self.assertRaisesRegex(audit.AuditFailure, "provenance_missing_or_changed"):
                audit.inspect(Path("not-read"), {"source_sha": "different"})
            run.assert_not_called()

    def test_failed_and_oversized_query_never_leak_native_stderr(self):
        for mode, reason in [("timeout", "native_query_timed_out"),
                             ("exit", "native_query_failed"), ("size", "exceeds_4_mib")]:
            def run(command, **kwargs):
                if mode == "timeout":
                    raise subprocess.TimeoutExpired("secret-command", 45, output=b"secret-output")
                if mode == "size":
                    kwargs["stdout"].write(b"x" * (audit.MAX_QUERY_BYTES + 1))
                return subprocess.CompletedProcess(command, int(mode == "exit"))
            with patch.object(audit.subprocess, "run", side_effect=run):
                with self.assertRaisesRegex(audit.AuditFailure, reason) as caught:
                    audit.query_window(Path("private-native-archive"), audit.WINDOWS[1])
                self.assertNotIn("secret", str(caught.exception))

    def test_top_level_error_never_emits_exception_body(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "OUTPUT_ROOT", Path(temporary)), \
                patch.object(audit, "plain_path", side_effect=lambda path, root: path), \
                patch.object(audit, "verify_remote", side_effect=RuntimeError("secret-auth-path")), \
                patch("sys.argv", ["audit", "verify-provenance"]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(audit.main(), 1)
            evidence = (Path(temporary) / "provenance.json").read_text()
        self.assertNotIn("secret", output.getvalue() + evidence)


if __name__ == "__main__":
    unittest.main()
