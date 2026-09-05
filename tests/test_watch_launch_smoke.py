"""SDK/runtime selection fixtures only; these do not prove native Watch behavior."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("watch_launch_smoke", Path(__file__).with_name("watch_launch_smoke.py"))
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


def device(udid, name, available=True):
    return {"udid": udid, "name": name, "isAvailable": available, "state": "Shutdown"}


def pair(watch, phone):
    return {"watch": {"udid": watch}, "phone": {"udid": phone}}


class SimulatorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.sdks = {"watch": "26.4", "phone": "26.4"}
        self.inventory = {
            "com.apple.CoreSimulator.SimRuntime.watchOS-26-4": [device("w4", "Apple Watch Series 11 (42mm)")],
            "com.apple.CoreSimulator.SimRuntime.iOS-26-4-1": [device("p4", "iPhone 17")],
            "com.apple.CoreSimulator.SimRuntime.watchOS-26-5": [device("w5", "Apple Watch Ultra 3 (49mm)")],
            "com.apple.CoreSimulator.SimRuntime.iOS-26-5": [device("p5", "iPhone 17")],
        }

    def test_exact_sdk_pair_wins_over_newer_installed_runtime(self):
        choice = SMOKE.choose_simulators(self.inventory, [pair("w5", "p5"), pair("w4", "p4")], self.sdks)
        self.assertEqual(choice["watch"]["udid"], "w4")
        self.assertFalse(choice["needs_pair"])
        self.assertEqual(choice["selection_reason"], "Existing SDK-matched pair")

    def test_sdk_patch_differences_stay_in_same_release(self):
        self.assertEqual(SMOKE.release_version("26.4.1"), (26, 4))
        choice = SMOKE.choose_simulators(self.inventory, [], {"watch": "26.4.1", "phone": "26.4.2"})
        self.assertEqual(choice["phone"]["udid"], "p4")
        self.assertTrue(choice["needs_pair"])

    def test_new_sdk_matched_free_pair_precedes_old_existing_pair(self):
        self.inventory["watchOS-26-2"] = [device("w2", "Apple Watch Series 11 (42mm)")]
        self.inventory["iOS-26-2"] = [device("p2", "iPhone 17")]
        choice = SMOKE.choose_simulators(self.inventory, [pair("w2", "p2")], self.sdks)
        self.assertEqual(choice["watch"]["udid"], "w4")
        self.assertTrue(choice["needs_pair"])

    def test_fallback_only_uses_existing_pair_below_both_sdks(self):
        choice = SMOKE.choose_simulators(self.inventory, [pair("w4", "p4"), pair("w5", "p5")],
                                         {"watch": "26.6", "phone": "26.4"})
        self.assertEqual(choice["watch"]["udid"], "w4")
        self.assertIn("Fallback", choice["selection_reason"])

    def test_no_arbitrary_or_newer_runtime_pair_is_invented(self):
        with self.assertRaisesRegex(RuntimeError, "available runtimes"):
            SMOKE.choose_simulators(self.inventory, [], {"watch": "26.3", "phone": "26.3"})

    def test_existing_associations_are_not_replaced(self):
        with self.assertRaisesRegex(RuntimeError, "No safe"):
            SMOKE.choose_simulators(self.inventory, [pair("w4", "p5")], self.sdks)

    def test_small_screen_wins_only_with_equivalent_runtime(self):
        self.inventory["com.apple.CoreSimulator.SimRuntime.watchOS-26-4"].append(device("ultra", "Apple Watch Ultra 3 (49mm)"))
        self.inventory["com.apple.CoreSimulator.SimRuntime.iOS-26-4-1"].append(device("pro", "iPhone 17 Pro"))
        choice = SMOKE.choose_simulators(self.inventory, [pair("ultra", "pro"), pair("w4", "p4")], self.sdks)
        self.assertEqual(choice["watch"]["udid"], "w4")
        free_choice = SMOKE.choose_simulators(self.inventory, [], self.sdks)
        self.assertEqual(free_choice["watch"]["udid"], "w4")

    def test_unavailable_pair_is_not_selected(self):
        self.inventory["com.apple.CoreSimulator.SimRuntime.watchOS-26-4"][0]["isAvailable"] = False
        with self.assertRaisesRegex(RuntimeError, "No safe"):
            SMOKE.choose_simulators(self.inventory, [pair("w4", "p4")], self.sdks)


class GateReportingTests(unittest.TestCase):
    def test_failed_capture_route_is_not_changed_to_success_or_swallowed(self):
        import json
        import os

        def failed_smoke(output, diagnostics, context, started):
            context["cold_launch"]["status"] = "succeeded"
            context["capture_url"]["status"] = "failed"
            raise RuntimeError("synthetic URL injection failure")

        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                with patch.object(SMOKE, "run_smoke", side_effect=failed_smoke):
                    with self.assertRaisesRegex(RuntimeError, "synthetic URL"):
                        SMOKE.main()
                context = json.loads(Path("build/watch-launch-smoke/context.json").read_text())
                self.assertEqual(context["cold_launch"]["status"], "succeeded")
                self.assertEqual(context["capture_url"]["status"], "failed")
                self.assertIn("synthetic URL", context["failure"])
            finally:
                os.chdir(previous)


class LocalSignatureTests(unittest.TestCase):
    def test_matching_ad_hoc_signature_is_accepted(self):
        proof = SMOKE.validate_local_signature_text(
            "Executable=/sample/CevizWatchApp\nIdentifier=com.example.watch\nSignature=adhoc\nTeamIdentifier=not set\n",
            "com.example.watch")
        self.assertEqual(proof, {"identifier": "com.example.watch", "signature": "adhoc"})

    def test_executable_name_identity_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Identifier does not match"):
            SMOKE.validate_local_signature_text("Identifier=CevizWatchApp\nSignature=adhoc\n", "com.example.watch")

    def test_certificate_signature_is_not_accepted_as_local(self):
        with self.assertRaisesRegex(RuntimeError, "certificate-free"):
            SMOKE.validate_local_signature_text(
                "Identifier=com.example.watch\nAuthority=Apple Development: Example\n", "com.example.watch")

    def test_missing_code_identity_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Identifier does not match"):
            SMOKE.validate_local_signature_text("code object is not signed at all\n", "com.example.watch")


if __name__ == "__main__":
    unittest.main()
