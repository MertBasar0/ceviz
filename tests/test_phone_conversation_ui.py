"""Exercise native-runner ownership at subprocess/HTTP boundaries, without Xcode."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import phone_conversation_ui as runner


RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
DEVICE_TYPE = "com.apple.CoreSimulator.SimDeviceType.iPhone-16"
EXISTING = "AAAA0000-0000-4000-8000-000000000000"
CREATED = "BBBB0000-0000-4000-8000-000000000000"
PHONE = {"name": "iPhone 16", "udid": EXISTING, "state": "Booted", "isAvailable": True}
TYPES = [{"name": "iPhone 16", "identifier": DEVICE_TYPE}]


class PhoneConversationRunnerTests(unittest.TestCase):
    def exercise(self, *, failure=None, cleanup_failures=(), process_exited=False,
                 hung_fixture=False, ready_pid=123, created_id=CREATED):
        calls = []
        state_paths = []
        fixture = Mock(pid=123)
        fixture.poll.return_value = 1 if process_exited else None
        if hung_fixture:
            fixture.wait.side_effect = [subprocess.TimeoutExpired("fixture", 10), 0]

        def start_fixture(args, **kwargs):
            directory = Path(args[args.index("--state-dir") + 1])
            self.assertTrue(directory.is_dir())
            state_paths.append(directory)
            if failure == "start":
                raise RuntimeError("primary start failure")
            return fixture

        def command(args, **kwargs):
            calls.append(args)
            if args[:3] == ["xcodebuild", "-version", "-sdk"]:
                return "26.5"
            if args[:4] == ["xcrun", "simctl", "list", "devices"]:
                return json.dumps({"devices": {RUNTIME: [PHONE]}})
            if args[:4] == ["xcrun", "simctl", "list", "devicetypes"]:
                return json.dumps({"devicetypes": TYPES})
            if args[:3] == ["xcrun", "simctl", "create"]:
                return created_id
            if (args[:3] == ["xcrun", "simctl", "shutdown"] and "shutdown" in cleanup_failures
                    or args[:3] == ["xcrun", "xcresulttool", "export"] and "export" in cleanup_failures
                    or args == ["xcodegen", "generate"] and "project" in cleanup_failures):
                raise RuntimeError("cleanup " + args[-1])
            if args[:3] == ["xcrun", "simctl", "boot"] and failure == "boot":
                raise RuntimeError("primary boot failure")
            return ""

        def run(args, **kwargs):
            calls.append(args)
            if "test-without-building" in args:
                Path(args[args.index("-resultBundlePath") + 1]).mkdir()
            stage = "test" if "test-without-building" in args else "build"
            if failure == stage:
                raise RuntimeError("primary " + stage + " failure")
            return subprocess.CompletedProcess(args, 0)

        with tempfile.TemporaryDirectory(prefix="ceviz-phone-runner-test-") as temporary:
            with patch.object(runner.Path, "cwd", return_value=Path(temporary)), \
                    patch.object(runner, "command", side_effect=command), \
                    patch.object(runner.subprocess, "run", side_effect=run), \
                    patch.object(runner.subprocess, "Popen", side_effect=start_fixture), \
                    patch.object(runner, "urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps({
                        "pid": ready_pid, "conversations_v1": True,
                    }).encode())), patch("sys.stderr", new_callable=io.StringIO):
                error = None
                try:
                    runner.main()
                except Exception as caught:
                    error = caught
            records = list(Path(temporary).glob("build/phone-conversation-ui/run-*/context.json"))
            context = json.loads(records[0].read_text()) if records else None
        self.assertTrue(state_paths)
        self.assertTrue(all(not directory.exists() for directory in state_paths),
                        "Parent-owned fixture state must be removed even when its child exits abruptly")
        return calls, fixture, error, context

    def test_creates_owns_and_removes_only_a_fresh_phone(self):
        calls, fixture, error, context = self.exercise()
        self.assertIsNone(error)
        create = next(args for args in calls if args[:3] == ["xcrun", "simctl", "create"])
        self.assertEqual(create[-2:], [DEVICE_TYPE, RUNTIME])
        for operation in ["boot", "bootstatus", "install", "openurl", "shutdown", "delete"]:
            with self.subTest(operation=operation):
                found = [args for args in calls if args[:3] == ["xcrun", "simctl", operation]]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0][3], CREATED, "Never mutate the operator's existing simulator")
        test = next(args for args in calls if "test-without-building" in args)
        self.assertEqual(test[test.index("-parallel-testing-enabled") + 1], "NO")
        self.assertEqual(context["udid"], CREATED)
        self.assertEqual(context["template"]["udid"], EXISTING)
        fixture.terminate.assert_called_once_with()
        fixture.wait.assert_called_once_with(timeout=10)

    def test_failures_still_remove_owned_simulator_and_stop_fixture(self):
        for stage in ["boot", "build", "test"]:
            with self.subTest(stage=stage):
                calls, fixture, error, _ = self.exercise(failure=stage)
                self.assertEqual(str(error), "primary " + stage + " failure")
                self.assertIn(["xcrun", "simctl", "delete", CREATED], calls)
                fixture.terminate.assert_called_once_with()

    def test_cleanup_is_independent_and_preserves_original_test_failure(self):
        calls, fixture, error, _ = self.exercise(failure="test", cleanup_failures=("export", "project", "shutdown"),
                                                hung_fixture=True)
        self.assertEqual(str(error), "primary test failure")
        self.assertIn(["xcodegen", "generate"], calls)
        self.assertIn(["xcrun", "simctl", "shutdown", CREATED], calls)
        self.assertIn(["xcrun", "simctl", "delete", CREATED], calls)
        fixture.kill.assert_called_once_with()
        self.assertEqual(fixture.wait.call_count, 2)

    def test_cleanup_failure_is_not_reported_as_success(self):
        calls, _, error, _ = self.exercise(cleanup_failures=("export",))
        self.assertIsInstance(error, RuntimeError)
        self.assertIn(["xcrun", "simctl", "delete", CREATED], calls)

    def test_readiness_requires_the_owned_process(self):
        for exited, pid in [(True, 123), (False, 987)]:
            with self.subTest(exited=exited, pid=pid):
                calls, fixture, error, _ = self.exercise(process_exited=exited, ready_pid=pid)
                self.assertIsInstance(error, RuntimeError)
                self.assertFalse(any(args[:3] == ["xcrun", "simctl", "create"] for args in calls))
                if exited:
                    fixture.terminate.assert_not_called()
                else:
                    fixture.terminate.assert_called_once_with()

    def test_failed_process_start_leaves_no_state_or_simulator(self):
        calls, fixture, error, _ = self.exercise(failure="start")
        self.assertEqual(str(error), "primary start failure")
        self.assertFalse(any(args[:3] == ["xcrun", "simctl", "create"] for args in calls))
        fixture.terminate.assert_not_called()

    def test_unverified_create_output_never_grants_cleanup_authority(self):
        for returned in ["", "unexpected output", EXISTING]:
            with self.subTest(returned=returned):
                calls, fixture, error, _ = self.exercise(created_id=returned)
                self.assertIsInstance(error, RuntimeError)
                self.assertFalse(any(args[:3] == ["xcrun", "simctl", "delete"] for args in calls))
                self.assertFalse(any(args[:3] == ["xcrun", "simctl", "install"] for args in calls))
                fixture.terminate.assert_called_once_with()

    def test_selects_only_available_sdk_matching_phone_with_observed_type(self):
        old_runtime = "com.apple.CoreSimulator.SimRuntime.iOS-18-5"
        inventory = {old_runtime: [PHONE], RUNTIME: [
            {**PHONE, "isAvailable": False},
            {**PHONE, "name": "iPad Pro"},
            {**PHONE, "name": "iPhone 16 Pro"}, PHONE,
        ]}
        selected = runner.select_phone(inventory, "26.5.1", TYPES)
        self.assertEqual(selected, {"template": PHONE, "runtime": RUNTIME, "device_type": DEVICE_TYPE})
        for inventory, types in [({old_runtime: [PHONE]}, TYPES), ({RUNTIME: [PHONE]}, []),
                                 ({RUNTIME: [{**PHONE, "isAvailable": False}]}, TYPES)]:
            with self.subTest(inventory=inventory, types=types):
                with self.assertRaises(RuntimeError):
                    runner.select_phone(inventory, "26.5", types)


if __name__ == "__main__":
    unittest.main()
