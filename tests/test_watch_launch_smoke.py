"""SDK/runtime selection fixtures only; these do not prove native Watch behavior."""

import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("watch_launch_smoke", Path(__file__).with_name("watch_launch_smoke.py"))
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


def device(udid, name, available=True):
    return {"udid": udid, "name": name, "isAvailable": available, "state": "Shutdown"}


def pair(watch, phone):
    return {"watch": {"udid": watch}, "phone": {"udid": phone}}


class SimulatorBootTests(unittest.TestCase):
    def test_failed_or_timed_out_boot_preserves_diagnostics(self):
        for failure in (subprocess.TimeoutExpired(["xcrun"], 300, output=b"Boot progress", stderr=b"Migration stalled"),
                        subprocess.CalledProcessError(1, ["xcrun"], output="Boot progress", stderr="Migration stalled")):
            with self.subTest(failure=failure), patch.object(SMOKE.subprocess, "run", side_effect=failure), \
                    patch("builtins.print") as diagnostics:
                with self.assertRaises(type(failure)):
                    SMOKE.simctl("bootstatus", "fixture-phone", "-b")
                self.assertEqual([call.args[0] for call in diagnostics.call_args_list],
                                 ["Boot progress", "Migration stalled"])

    def test_zero_exit_migration_diagnostic_is_preserved_without_claiming_readiness(self):
        diagnostic = "Status=3, isTerminal=YES, Elapsed=02:06.\n\tData Migration Failed\n"
        with patch.object(SMOKE.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, diagnostic)), \
                patch("builtins.print") as warning:
            self.assertEqual(SMOKE.simctl("bootstatus", "fixture-phone", "-b", capture=True), diagnostic)
            self.assertIn("not app readiness proof", warning.call_args.args[0])

    def test_successful_boot_preserves_diagnostics_and_has_a_deadline(self):
        for diagnostic in ("Status=4294967295, isTerminal=YES\nFinished\n", "Device already booted, nothing to do.\n"):
            with self.subTest(diagnostic=diagnostic), \
                    patch.object(SMOKE.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, diagnostic)) as run:
                self.assertEqual(SMOKE.simctl("bootstatus", "fixture-phone", "-b", capture=True), diagnostic)
                self.assertEqual(run.call_args.kwargs["timeout"], 300)
        with patch.object(SMOKE.subprocess, "run") as run:
            SMOKE.simctl("boot", "fixture-watch")
            self.assertEqual(run.call_args.kwargs["timeout"], 300)


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

        def failed_smoke(output, diagnostics, context, started, *, candidate_for_device_check=False):
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


class CandidateURLProbeTests(unittest.TestCase):
    @staticmethod
    def url_failure(code=115, domain="LSApplicationWorkspaceErrorDomain"):
        import subprocess
        return subprocess.CalledProcessError(
            code, ["xcrun", "simctl", "openurl", "fixture-watch", "ceviz-watch://capture"],
            stderr=f"An error was encountered processing the command (domain={domain}, code={code}):\n")

    def probe(self, error, *, candidate=False):
        context = SMOKE.initial_context(candidate)
        self.context = context
        with patch.object(SMOKE, "record_command", side_effect=error), \
                patch.object(SMOKE, "collect_url_failure_diagnostics") as diagnostics:
            try:
                SMOKE.run_capture_url_probe(Path("unused"), Path("unused"), context, "fixture-watch",
                                            candidate_for_device_check=candidate)
            finally:
                diagnostics.assert_called_once()
        return context

    def test_default_strict_known_115_is_fatal(self):
        import subprocess
        with self.assertRaises(subprocess.CalledProcessError):
            self.probe(self.url_failure())
        self.assertEqual(self.context["capture_url"]["status"], "failed")
        self.assertNotIn("candidate_exception_applied", self.context["capture_url"])

    def test_explicit_candidate_retains_known_115_as_unresolved(self):
        with patch("builtins.print") as warning:
            context = self.probe(self.url_failure(), candidate=True)
        self.assertEqual(context["capture_url"]["status"], "failed")
        self.assertTrue(context["capture_url"]["candidate_exception_applied"])
        self.assertEqual(context["candidate_status"], "unresolved_widget_navigation_requires_device_check")
        self.assertEqual(context["widget_tap"]["status"], "not_tested")
        self.assertEqual(context["external_distribution"]["status"], "blocked_pending_device_validation")
        self.assertIn("::warning::", warning.call_args.args[0])

    def test_unknown_error_or_other_domain_115_remains_fatal(self):
        import subprocess
        for error in (self.url_failure(code=1), self.url_failure(domain="UnknownErrorDomain"), RuntimeError("unknown")):
            with self.subTest(error=error), self.assertRaises((subprocess.CalledProcessError, RuntimeError)):
                self.probe(error, candidate=True)

    def test_timeout_remains_fatal_in_candidate_mode(self):
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            self.probe(subprocess.TimeoutExpired(["xcrun", "simctl", "openurl"], 60), candidate=True)

    def test_successful_generic_injection_never_claims_widget_tap(self):
        context = SMOKE.initial_context(True)
        with patch.object(SMOKE, "record_command"), patch.object(SMOKE, "simctl"), patch.object(SMOKE.time, "sleep"):
            SMOKE.run_capture_url_probe(Path("unused"), Path("unused"), context, "fixture-watch",
                                        candidate_for_device_check=True)
        self.assertEqual(context["capture_url"]["status"], "succeeded")
        self.assertEqual(context["widget_tap"]["status"], "not_tested")
        self.assertEqual(context["external_distribution"]["status"], "blocked_pending_device_validation")

    def test_error_115_from_screenshot_is_not_the_allowed_url_exception(self):
        import subprocess
        context = SMOKE.initial_context(True)
        error = self.url_failure()
        error.cmd = ["xcrun", "simctl", "io", "fixture-watch", "screenshot", "unused.png"]
        with patch.object(SMOKE, "record_command"), patch.object(SMOKE, "simctl", side_effect=error), \
                patch.object(SMOKE.time, "sleep"), patch.object(SMOKE, "collect_url_failure_diagnostics"):
            with self.assertRaises(subprocess.CalledProcessError):
                SMOKE.run_capture_url_probe(Path("unused"), Path("unused"), context, "fixture-watch",
                                            candidate_for_device_check=True)
        self.assertNotIn("candidate_exception_applied", context["capture_url"])


if __name__ == "__main__":
    unittest.main()
