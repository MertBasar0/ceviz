"""Capture runner scheduling and isolation only; no native UI/audio claims."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class SimulatorPairLifetimeTests(unittest.TestCase):
    def test_same_pair_stays_warm_and_previous_pair_stops_before_next_boot(self):
        owner = capture.CaptureSimulatorPair()
        states = {udid: "Shutdown" for udid in ("phone40", "watch40", "phone49", "watch49")}
        actions = []

        def simctl(command, udid, *args):
            actions.append((command, udid))
            if command == "boot":
                states[udid] = "Booted"

        def shutdown(command, **kwargs):
            self.assertEqual(kwargs, {"check": True, "timeout": 60})
            actions.append(("shutdown", command[-1]))
            states[command[-1]] = "Shutdown"

        with patch.object(owner, "device_states", side_effect=lambda: states.copy()), \
                patch.object(capture, "simctl", side_effect=simctl), \
                patch.object(capture.subprocess, "run", side_effect=shutdown):
            owner.use({"udid": "phone40"}, {"udid": "watch40"})
            owner.use({"udid": "phone40"}, {"udid": "watch40"})
            owner.use({"udid": "phone40"}, {"udid": "watch40"})
            self.assertEqual([action for action in actions if action[0] != "bootstatus"],
                             [("boot", "phone40"), ("boot", "watch40")])
            warm_end = len(actions)
            owner.use({"udid": "phone49"}, {"udid": "watch49"})
            owner.close()
        self.assertEqual(actions[warm_end:], [("shutdown", "watch40"), ("shutdown", "phone40"),
                                      ("boot", "phone49"), ("bootstatus", "phone49"),
                                      ("boot", "watch49"), ("bootstatus", "watch49"),
                                      ("shutdown", "watch49"), ("shutdown", "phone49")])
        self.assertTrue(all(state == "Shutdown" for state in states.values()))

    def test_preexisting_pair_is_not_stopped_or_run_alongside_another_pair(self):
        owner = capture.CaptureSimulatorPair()
        with patch.object(owner, "device_states", return_value={"phone40": "Booted", "watch40": "Booted"}), \
                patch.object(capture, "simctl") as simctl, patch.object(capture.subprocess, "run") as shutdown:
            owner.use({"udid": "phone40"}, {"udid": "watch40"})
            with self.assertRaisesRegex(RuntimeError, "outside this runner's ownership"):
                owner.use({"udid": "phone49"}, {"udid": "watch49"})
            owner.close()
        shutdown.assert_not_called()
        self.assertEqual([call.args for call in simctl.call_args_list],
                         [("bootstatus", "phone40", "-b"), ("bootstatus", "watch40", "-b")])

    def test_partial_boot_timeout_keeps_cleanup_ownership(self):
        owner = capture.CaptureSimulatorPair()
        states = {"phone40": "Shutdown", "watch40": "Shutdown"}

        def timeout(*args):
            states["phone40"] = "Booted"
            raise subprocess.TimeoutExpired("boot", 300)

        def stopped(*args, **kwargs):
            states["phone40"] = "Shutdown"

        with patch.object(owner, "device_states", side_effect=lambda: states.copy()), \
                patch.object(capture, "simctl", side_effect=timeout), \
                patch.object(capture.subprocess, "run") as shutdown:
            shutdown.side_effect = stopped
            with self.assertRaises(subprocess.TimeoutExpired):
                owner.use({"udid": "phone40"}, {"udid": "watch40"})
            owner.close()
        shutdown.assert_called_once_with(["xcrun", "simctl", "shutdown", "phone40"], check=True, timeout=60)

    def test_failed_shutdown_prevents_booting_next_pair(self):
        owner = capture.CaptureSimulatorPair()
        owner.current = ("phone40", "watch40")
        owner.started = ["phone40", "watch40"]
        with patch.object(owner, "device_states", return_value={"phone40": "Booted", "watch40": "Booted"}), \
                patch.object(capture, "simctl") as simctl, \
                patch.object(capture.subprocess, "run", side_effect=subprocess.TimeoutExpired("shutdown", 60)):
            with self.assertRaisesRegex(RuntimeError, "shutdown failed"):
                owner.use({"udid": "phone49"}, {"udid": "watch49"})
        simctl.assert_not_called()
        self.assertEqual(owner.started, ["phone40", "watch40"])

    def test_same_pair_reboots_framework_stopped_device_without_duplicate_ownership(self):
        owner = capture.CaptureSimulatorPair()
        owner.current = ("phone40", "watch40")
        owner.started = ["phone40", "watch40"]
        states = {"phone40": "Booted", "watch40": "Shutdown"}
        with patch.object(owner, "device_states", return_value=states), patch.object(capture, "simctl") as simctl:
            owner.use({"udid": "phone40"}, {"udid": "watch40"})
        self.assertEqual([call.args for call in simctl.call_args_list], [
            ("bootstatus", "phone40", "-b"), ("boot", "watch40"), ("bootstatus", "watch40", "-b")])
        self.assertEqual(owner.started, ["phone40", "watch40"])

    def test_close_accepts_verified_shutdown_but_not_unknown_state(self):
        owner = capture.CaptureSimulatorPair()
        owner.current = ("phone40", "watch40")
        owner.started = ["phone40", "watch40"]
        with patch.object(owner, "device_states", return_value={"phone40": "Shutdown", "watch40": "Shutdown"}), \
                patch.object(capture.subprocess, "run") as shutdown:
            owner.close()
        shutdown.assert_not_called()
        self.assertEqual(owner.started, [])
        owner.started = ["unknown-device"]
        with patch.object(owner, "device_states", return_value={}), patch.object(capture.subprocess, "run") as shutdown:
            with self.assertRaisesRegex(RuntimeError, "state is unknown"):
                owner.close()
        shutdown.assert_not_called()
        self.assertEqual(owner.started, ["unknown-device"])


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


if __name__ == "__main__":
    unittest.main()
