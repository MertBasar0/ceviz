"""Capture runner scheduling and isolation only; no native UI/audio claims."""

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import watch_capture_ui as capture


class CaptureRunPlanTests(unittest.TestCase):
    def test_four_short_matrix_runs_and_one_small_normal_finish(self):
        runs = capture.capture_runs(False)
        self.assertEqual(runs, [(40, "large", "short"), (40, "extra-extra-extra-large", "short"),
                                (49, "large", "short"), (49, "extra-extra-extra-large", "short"),
                                (40, "large", "finish")])
        self.assertEqual(capture.test_selection("short"), [f"-skip-testing:{capture.FINISH_TEST}"])
        self.assertEqual(capture.test_selection("finish"), [f"-only-testing:{capture.FINISH_TEST}"])

    def test_baseline_only_runs_existing_english_text_selectors(self):
        self.assertEqual(capture.capture_runs(True), [(40, "large", "baseline")])
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


if __name__ == "__main__":
    unittest.main()
