"""Capture runner scheduling and isolation only; no native UI/audio claims."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext

import watch_capture_ui as capture


class CaptureRunPlanTests(unittest.TestCase):
    def test_four_short_matrix_runs_and_one_small_normal_finish(self):
        runs = capture.capture_runs(False)
        self.assertEqual(runs, [(40, "device-default", "short"), (40, "larger-settings", "short"),
                                (40, "device-default", "finish"), (49, "device-default", "short"),
                                (49, "larger-settings", "short")])
        self.assertEqual(capture.test_selection("short"), [
            "-only-testing:CevizWatchUITests/WatchCaptureUITests/testReadyScreenEnglish",
            "-only-testing:CevizWatchUITests/WatchCaptureUITests/testRecordAndDiscardBothLanguages"])
        self.assertEqual(capture.test_selection("short", "larger-settings"), [f"-only-testing:{capture.LARGER_TEST}"])
        self.assertEqual(capture.test_selection("finish"), [f"-only-testing:{capture.FINISH_TEST}"])

    def test_baseline_only_runs_existing_english_text_selectors(self):
        self.assertEqual(capture.capture_runs(True), [(40, "device-default", "baseline")])
        self.assertEqual(capture.test_selection("baseline"),
                         ["-only-testing:CevizWatchUITests/WatchCaptureUITests/testReadyScreenEnglish"])
        with self.assertRaises(ValueError):
            capture.test_selection("unsupported")

    def test_screen_selection_cannot_silently_repeat_ultra_for_small_screen(self):
        inventory = {"watchOS-26-4": [{"name": "Apple Watch SE (40mm)"}, {"name": "Apple Watch Ultra (49mm)"}],
                     "iOS-26-4": [{"name": "iPhone"}]}
        with patch.object(capture, "choose_simulators", return_value="choice") as choose:
            self.assertEqual(capture.select_watch(inventory, ["current-pair"], {"watch": "26.4"}, 40), "choice")
        filtered, pairs, versions = choose.call_args.args
        self.assertEqual(filtered["watchOS-26-4"], [{"name": "Apple Watch SE (40mm)"}])
        self.assertEqual(filtered["iOS-26-4"], inventory["iOS-26-4"])
        self.assertEqual(pairs, ["current-pair"])
        self.assertEqual(versions, {"watch": "26.4"})


class WatchContainerIsolationTests(unittest.TestCase):
    def test_existing_app_is_removed_before_install_then_permission_grant(self):
        with patch.object(capture, "simctl") as simctl, patch.object(capture.subprocess, "run") as run:
            run.return_value.stdout = json.dumps({capture.WATCH_ID: {}, "unrelated.app": {}})
            capture.reinstall_watch("sim-watch", Path("built-watch.app"))
        self.assertEqual([call.args for call in simctl.call_args_list], [
            ("listapps", "sim-watch"), ("uninstall", "sim-watch", capture.WATCH_ID),
            ("install", "sim-watch", "built-watch.app"), ("privacy", "sim-watch", "grant", "microphone", capture.WATCH_ID)])

    def test_first_install_does_not_uninstall_other_apps(self):
        with patch.object(capture, "simctl") as simctl, patch.object(capture.subprocess, "run") as run:
            run.return_value.stdout = json.dumps({"unrelated.app": {}})
            capture.reinstall_watch("sim-watch", Path("built-watch.app"))
        self.assertFalse(any(call.args[0] == "uninstall" for call in simctl.call_args_list))

    def test_inventory_failure_does_not_mutate_or_grant_anything(self):
        with patch.object(capture, "simctl") as simctl, patch.object(capture.subprocess, "run") as run:
            run.side_effect = subprocess.CalledProcessError(1, ["plutil"])
            with self.assertRaises(subprocess.CalledProcessError):
                capture.reinstall_watch("sim-watch", Path("built-watch.app"))
        self.assertEqual([call.args[0] for call in simctl.call_args_list], ["listapps"])


class ActualCaptureMetadataTests(unittest.TestCase):
    def test_numeric_file_metadata_preserves_real_sizes_without_codec_size_guesses(self):
        log = "\n".join(f"Capture finalized: duration_seconds={duration} bytes={size} codec=1633772320 sample_rate=16000 channels=1"
                        for duration, size in [(9.2, 41000), (15.0, 68000)])
        metrics = capture.capture_file_metrics(log)
        capture.require_capture_durations(metrics)
        self.assertEqual([row["bytes"] for row in metrics], [41000, 68000])

    def test_missing_or_short_native_recording_cannot_pass_as_a_15s_file(self):
        with self.assertRaisesRegex(RuntimeError, "missing"):
            capture.require_capture_durations(capture.capture_file_metrics("Capture finalized: bytes=400 file_metadata=unavailable"))
        metrics = [{"duration_seconds": 9.0, "bytes": 41000, "codec": 1, "sample_rate": 16000, "channels": 1}] * 2
        with self.assertRaisesRegex(RuntimeError, "9s/15s"):
            capture.require_capture_durations(metrics)

    def test_extra_finalization_cannot_be_hidden_by_two_valid_measurements(self):
        valid = [f"Capture finalized: duration_seconds={duration} bytes=41000 codec=1633772320 sample_rate=16000 channels=1"
                 for duration in (9.2, 15.0)]
        extras = ["Capture finalized: duration_seconds=2.0 bytes=4000 codec=1633772320 sample_rate=16000 channels=1",
                  "Capture finalized: bytes=400 file_metadata=unavailable",
                  "Capture finalized: bytes=400"]
        for extra in extras:
            for position in range(3):
                with self.subTest(extra=extra, position=position):
                    lines = valid.copy()
                    lines.insert(position, extra)
                    with self.assertRaises(RuntimeError):
                        capture.require_capture_durations(capture.capture_file_metrics("\n".join(lines)))

    def test_unavailable_metadata_is_retained_for_context_before_validation_fails(self):
        log = "Capture finalized: bytes=400 file_metadata=unavailable\nCapture finalized: duration_seconds=15.0 bytes=68000 codec=1633772320 sample_rate=16000 channels=1"
        metrics = capture.capture_file_metrics(log)
        self.assertEqual(metrics[0], {"file_metadata": "unavailable", "bytes": 400})
        self.assertEqual(len(metrics), 2)
        self.assertEqual(json.loads(json.dumps(metrics)), metrics)
        with self.assertRaisesRegex(RuntimeError, "missing"):
            capture.require_capture_durations(metrics)


class CaptureLogStreamTests(unittest.TestCase):
    def test_collector_is_ready_before_body_and_only_owned_process_is_stopped(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(capture.subprocess, "Popen") as popen:
            process = popen.return_value
            process.poll.return_value = None

            def started(*args, **kwargs):
                kwargs["stdout"].write("Filtering the log data using the AudioCapture predicate\n")
                kwargs["stdout"].flush()
                return process

            popen.side_effect = started
            log_path = Path(temporary) / "audio.log"
            with capture.capture_log_stream("watch-udid", log_path) as running:
                self.assertIs(running, process)
                self.assertIn("Filtering the log data using", log_path.read_text())
                process.terminate.assert_not_called()
            command = popen.call_args.args[0]
            self.assertEqual(command, ["xcrun", "simctl", "spawn", "watch-udid", "log", "stream",
                                       "--level", "info", "--style", "compact", "--timeout", "13m", "--predicate",
                                       'subsystem == "com.mertbasar.ceviz.watch" AND category == "AudioCapture"'])
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=10)
            process.kill.assert_not_called()

    def test_early_collector_exit_never_runs_ui_body(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(capture.subprocess, "Popen") as popen:
            popen.return_value.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "before readiness"):
                with capture.capture_log_stream("watch-udid", Path(temporary) / "audio.log"):
                    self.fail("The UI test must not start without an active collector")
            popen.return_value.terminate.assert_not_called()

    def test_readiness_timeout_kills_stuck_owned_collector(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(capture.subprocess, "Popen") as popen, \
                patch.object(capture.time, "monotonic", side_effect=[0, 16]):
            process = popen.return_value
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired("log stream", 10), 0]
            with self.assertRaisesRegex(RuntimeError, "did not confirm readiness"):
                with capture.capture_log_stream("watch-udid", Path(temporary) / "audio.log"):
                    self.fail("The UI test must not start after a collector timeout")
            process.terminate.assert_called_once()
            process.kill.assert_called_once()
            self.assertEqual(process.wait.call_count, 2)

    def test_cleanup_timeout_does_not_mask_existing_ui_failure(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(capture.subprocess, "Popen") as popen:
            process = popen.return_value
            process.poll.return_value = None
            process.wait.side_effect = subprocess.TimeoutExpired("log stream", 10)

            def started(*args, **kwargs):
                kwargs["stdout"].write("Filtering the log data using the AudioCapture predicate\n")
                kwargs["stdout"].flush()
                return process

            popen.side_effect = started
            log_path = Path(temporary) / "audio.log"
            with self.assertRaisesRegex(RuntimeError, "original UI failure"):
                with capture.capture_log_stream("watch-udid", log_path):
                    raise RuntimeError("original UI failure")
            self.assertIn("cleanup timed out", log_path.read_text())
            process.kill.assert_called_once()


class CaptureFailureDiagnosticsTests(unittest.TestCase):
    watch = "032D47F9-6038-4F30-B9D3-A6C7B665465F"
    # Actual retained 34417538624 compact log line, not a JSON-schema guess.
    native_line = ("2026-09-09 23:54:18.279 I  CevizWatchApp[55221:264bd] "
                   "[com.mertbasar.ceviz.watch:AudioCapture] Capture event: view_appeared scene=active")

    def collect(self, payload=None, archives=None, failure=None, export_code=0, query_code=0):
        with tempfile.TemporaryDirectory() as temporary:
            result = Path(temporary) / "capture.xcresult"
            result.mkdir()
            log = Path(temporary) / "capture.log"
            log.write_text("Test Suite 'WatchCaptureUITests' failed at 2026-09-09 23:54:32.993.\n")
            calls = []

            def run(command, **kwargs):
                calls.append((command, kwargs))
                if failure:
                    raise failure
                if command[:4] == ["xcrun", "xcresulttool", "export", "diagnostics"]:
                    native = Path(command[-1])
                    for name in archives if archives is not None else [f"Apple Watch SE (40mm)_{self.watch}", "iPhone_other"]:
                        (native / name / "simctl_diagnostics" / "system.logarchive").mkdir(parents=True)
                    return subprocess.CompletedProcess(command, export_code)
                kwargs["stdout"].write((self.native_line if payload is None else payload).encode())
                return subprocess.CompletedProcess(command, query_code)

            with patch.object(capture.subprocess, "run", side_effect=run):
                proof = capture.capture_failure_diagnostics(result, self.watch, log)
            if calls and calls[0][0][:4] == ["xcrun", "xcresulttool", "export", "diagnostics"]:
                self.assertFalse(Path(calls[0][0][-1]).exists(), "Owned raw diagnostics must be cleaned up")
            return proof, calls

    def test_observed_compact_envelope_watch_archive_window_and_redaction(self):
        secret = "must-not-export-url-token-transcript"
        payload = "\n".join([self.native_line, self.native_line + " " + secret,
                             "2026-09-09 23:54:22.853 Df testmanagerd[55111:abc] TouchEventsCompleted " + secret,
                             "2026-09-09 23:54:22.853 Df unrelated[111:abc] TouchEventsCompleted " + secret])
        proof, calls = self.collect(payload)
        self.assertEqual(proof["status"], "collected")
        self.assertEqual(proof["start"], "2026-09-09 23:52:32")
        self.assertEqual(proof["end"], "2026-09-09 23:54:34")
        self.assertEqual(proof["anchor_source"], "first_failed_native_suite")
        self.assertEqual(proof["matching_watch_archives"], 1)
        self.assertEqual(proof["recognized_rows"], 3)
        self.assertEqual([row["kind"] for row in proof["events"]],
                         ["app_view_appeared", "app_view_appeared", "native_touch_completion_acknowledgement"])
        self.assertEqual(proof["events"][0]["pid"], 55221)
        self.assertNotIn(secret, json.dumps(proof))
        self.assertNotIn("scene=active", json.dumps(proof))
        self.assertIn(self.watch, calls[1][0][3])
        self.assertEqual(calls[1][0][-1], capture.DIAGNOSTIC_PREDICATE)
        self.assertEqual([call[1]["timeout"] for call in calls], [60, 45])
        self.assertTrue(all(call[1]["stderr"] is subprocess.DEVNULL for call in calls))

    def test_missing_wrong_or_ambiguous_watch_archive_never_queries_host_or_phone(self):
        for archives in ([], ["iPhone_other"], ["watch_" + self.watch + "F"],
                         ["first_" + self.watch, "second_" + self.watch]):
            with self.subTest(archives=archives):
                proof, calls = self.collect(archives=archives)
                self.assertEqual(proof["reason"], "watch_archive_missing_or_ambiguous")
                self.assertEqual(len(calls), 1)

    def test_export_query_timeout_and_disk_errors_stay_unavailable_without_raw_error(self):
        for failure in (subprocess.TimeoutExpired("secret-command", 60, output=b"secret-output"),
                        OSError("secret-path")):
            proof, _ = self.collect(failure=failure)
            self.assertEqual(proof["status"], "unavailable")
            self.assertEqual(proof["error_type"], type(failure).__name__)
            self.assertNotIn("secret", json.dumps(proof))
        self.assertEqual(self.collect(export_code=1)[0]["reason"], "native_export_failed")
        self.assertEqual(self.collect(query_code=65)[0]["reason"], "native_log_query_failed")
        with patch.object(capture.subprocess, "run") as run:
            proof = capture.capture_failure_diagnostics(Path("nonexistent.xcresult"), self.watch, Path("unused.log"))
        run.assert_not_called()
        self.assertEqual(proof["reason"], "result_bundle_missing")

    def test_unrecognized_rows_and_output_limits_have_no_raw_fallback(self):
        proof, _ = self.collect("unexpected-format secret\n")
        self.assertEqual(proof["recognized_rows"], 0)
        self.assertEqual(proof["events"], [])
        self.assertNotIn("secret", json.dumps(proof))
        proof, _ = self.collect("x" * (4 * 1024 * 1024 + 1))
        self.assertEqual(proof["reason"], "query_output_exceeds_4_mib")
        self.assertNotIn("events", proof)
        proof, _ = self.collect((self.native_line + "\n") * 2001)
        self.assertEqual(len(proof["events"]), 2000)
        self.assertTrue(proof["event_limit_reached"])

    def test_runner_only_collects_on_failure_and_preserves_native_and_metadata_errors(self):
        for code, mode, expected in ((0, "short", None), (1, "short", "Native capture UI tests failed"),
                                     (0, "finish", "Actual file metadata missing")):
            with self.subTest(code=code, mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                context = root / "build/watch-launch-smoke/context.json"
                context.parent.mkdir(parents=True)
                context.write_text(json.dumps({"sdk_versions": {}}))
                (root / "build/watch-capture-ui/after/derived/Build/Products/Release-watchsimulator/CevizWatchApp.app").mkdir(parents=True)
                choice = {"watch": {"udid": self.watch, "name": "Apple Watch (40mm)"},
                          "phone": {"udid": "phone"}, "watch_runtime": "watchOS", "needs_pair": False}
                with patch.object(capture.Path, "cwd", return_value=root), \
                        patch.object(capture, "capture_runs", return_value=[(40, "device-default", mode)]), \
                        patch.object(capture, "select_watch", return_value=choice), \
                        patch.object(capture, "simctl", return_value=json.dumps({"devices": {}, "pairs": {}})), \
                        patch.object(capture, "WatchSimulatorPair"), patch.object(capture, "reinstall_watch"), \
                        patch.object(capture, "capture_log_stream", return_value=nullcontext()), \
                        patch.object(capture.subprocess, "run", return_value=subprocess.CompletedProcess([], code)), \
                        patch.object(capture, "capture_failure_diagnostics", return_value={"status": "unavailable"}) as diagnostics, \
                        patch("builtins.print"):
                    if expected:
                        with self.assertRaisesRegex(RuntimeError, expected):
                            capture.main(root)
                    else:
                        capture.main(root)
                self.assertEqual(diagnostics.call_count, int(expected is not None))
                evidence = json.loads((root / "build/watch-capture-ui/after/context.json").read_text())[0]
                self.assertEqual(evidence["status"], "failed" if expected else "passed")


if __name__ == "__main__":
    unittest.main()
