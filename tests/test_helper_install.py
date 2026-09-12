"""Actual Bash installer/Doctor guards with fixture tools; no real installation."""
import http.server
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "deploy/install.sh").read_bytes()
DOCTOR = (ROOT / "deploy/doctor.sh").read_bytes()
FEATURES = {"continuation_v1": True, "suggestion_approval_v1": True, "conversations_v1": True}


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "Actual Bash guards run on Linux/macOS")
class HelperInstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ceviz-install-guard-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.app = self.directory / "app"
        self.tools = self.directory / "fixture-bin"
        self.home = self.directory / "home"
        self.calls = self.directory / "calls.txt"
        for path in (self.app / "deploy", self.tools, self.home):
            path.mkdir(parents=True)
        self.bash = shutil.which("bash")
        self.environment = {
            "HOME": str(self.home), "PATH": str(self.tools), "LANG": "C.UTF-8",
            "CEVIZ_TEST_CALLS": str(self.calls), "CEVIZ_TEST_LOAD_STATE": "not-found",
            "WATCH_CEVIZ_NETWORK_MODE": "manual",
        }
        # A closed PATH prevents even a failed test from reaching real systemctl,
        # pip, openssl, Tailscale, kill commands or the operator's OpenClaw CLI.
        for name in ("dirname", "uname", "tr", "stat", "grep"):
            executable = shutil.which(name)
            if executable is None:
                self.skipTest("Read-only fixture prerequisite missing: " + name)
            (self.tools / name).symlink_to(executable)
        self.stub("systemctl", '''printf 'systemctl %s\\n' "$*" >> "$CEVIZ_TEST_CALLS"
case "$*" in
  '--user show watch-ceviz-backend.service -p LoadState --value') printf '%s\\n' "$CEVIZ_TEST_LOAD_STATE" ;;
  '--user show-environment'|'--user is-active --quiet watch-ceviz-backend') exit 0 ;;
  *) exit 97 ;;
esac
''')
        self.stub("python3", '''printf 'python3 %s\\n' "$*" >> "$CEVIZ_TEST_CALLS"
if [[ "$1" == '-c' && "$2" == 'import sys; raise SystemExit(sys.version_info < (3, 11))' ]]; then
  exit "${CEVIZ_TEST_VERSION_STATUS:-0}"
fi
# Old installers reach the mutation boundary here; do not create a real venv.
exit 89
''')
        self.stub("openclaw", "exit 98\n")
        self.stub("tailscale", '''printf 'tailscale %s\\n' "$*" >> "$CEVIZ_TEST_CALLS"
[[ "$*" == 'status' ]]
''')

    def stub(self, name, text):
        target = self.tools / name
        target.write_text("#!" + self.bash + "\n" + text)
        target.chmod(0o700)
        return target

    def run_script(self, content, name="install.sh", extra_environment=None):
        script = self.app / "deploy" / name
        script.write_bytes(content.replace(b"\r\n", b"\n"))
        return subprocess.run([self.bash, str(script)], cwd=self.app,
                              env={**self.environment, **(extra_environment or {})},
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)

    def recorded_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def assert_no_install_artifacts(self):
        self.assertFalse((self.app / ".venv").exists())
        self.assertFalse((self.app / ".auth-token").exists())
        self.assertFalse((self.home / ".config").exists())

    def test_existing_loaded_service_refuses_before_python_packages_token_or_unit_changes(self):
        unit = self.home / ".config/systemd/user/watch-ceviz-backend.service"
        unit.parent.mkdir(parents=True)
        original = b"[Service]\nEnvironment=OPENCLAW_WATCH_AGENT=user-selected\n"
        unit.write_bytes(original)
        result = self.run_script(INSTALLER, extra_environment={"CEVIZ_TEST_LOAD_STATE": "loaded"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.recorded_calls(), ["systemctl --user show watch-ceviz-backend.service -p LoadState --value"])
        self.assertIn("Existing Ceviz installation", result.stderr)
        self.assertEqual(unit.read_bytes(), original)
        self.assertFalse((self.app / ".venv").exists())
        self.assertFalse((self.app / ".auth-token").exists())

    def test_existing_token_refuses_even_without_a_service(self):
        token = self.app / ".auth-token"
        token.write_bytes(b"private-fixture-pairing-token")
        token.chmod(0o600)
        result = self.run_script(INSTALLER)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.recorded_calls(), [], "A saved pairing should short-circuit all tool operations")
        self.assertIn("Existing Ceviz installation", result.stderr)
        self.assertEqual(token.read_bytes(), b"private-fixture-pairing-token")
        self.assertNotIn("private-fixture-pairing-token", result.stdout + result.stderr)
        self.assertFalse((self.app / ".venv").exists())
        self.assertFalse((self.home / ".config").exists())

    def test_dangling_pairing_token_link_refuses_before_any_installation_work(self):
        token = self.app / ".auth-token"
        outside = self.directory / "outside-token-target"
        token.symlink_to(outside)
        result = self.run_script(INSTALLER)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.recorded_calls(), [], "A dangling pairing link is not a fresh installation")
        self.assertIn("Existing Ceviz installation", result.stderr)
        self.assertTrue(token.is_symlink())
        self.assertEqual(token.readlink(), outside)
        self.assertFalse(outside.exists())
        self.assertFalse((self.app / ".venv").exists())
        self.assertFalse((self.home / ".config").exists())

    def test_unsupported_python_explains_requirement_before_venv_or_configuration_creation(self):
        result = self.run_script(INSTALLER, extra_environment={"CEVIZ_TEST_VERSION_STATUS": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.recorded_calls(), [
            "systemctl --user show watch-ceviz-backend.service -p LoadState --value",
            "python3 -c import sys; raise SystemExit(sys.version_info < (3, 11))",
        ])
        self.assertIn("Python 3.11 or newer", result.stderr)
        self.assert_no_install_artifacts()

    def test_doctor_distinguishes_new_features_upgrade_requirement_and_auth_failure(self):
        token = self.app / ".auth-token"
        token.write_text("private-fixture-pairing-token")
        token.chmod(0o600)
        python = self.app / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text("#!" + self.bash + "\n"
                          "if [[ \"$1\" == '-c' && \"$2\" == 'import faster_whisper, qrcode' ]]; then exit 0; fi\n"
                          "exec " + shlex.quote(sys.executable) + " \"$@\"\n")
        python.chmod(0o700)
        records = []
        response = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                records.append((self.path, self.headers.get("Authorization")))
                code = response["jobs"] if self.path == "/api/v1/jobs/active" else response["capabilities"]
                body = {"jobs": []} if self.path == "/api/v1/jobs/active" else response["features"]
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_args):
                pass

        with http.server.HTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            worker.start()
            try:
                for label, jobs_code, capability_code, features, expected in (
                    ("matching", 200, 200, FEATURES, "supported"),
                    ("old helper", 200, 404, {}, "upgrade"),
                    ("missing flag", 200, 200, {**FEATURES, "conversations_v1": False}, "upgrade"),
                    ("capability auth failure", 200, 401, {}, "auth"),
                    ("initial auth failure", 401, 200, FEATURES, "auth"),
                ):
                    with self.subTest(case=label):
                        response.update(jobs=jobs_code, capabilities=capability_code, features=features)
                        records.clear()
                        before = token.read_bytes()
                        result = self.run_script(DOCTOR, "doctor.sh", {"WATCH_CEVIZ_PORT": str(server.server_port)})
                        output = result.stdout + result.stderr
                        self.assertNotIn("private-fixture-pairing-token", output)
                        self.assertEqual(token.read_bytes(), before)
                        self.assertTrue(records)
                        self.assertTrue(all(auth == "Bearer private-fixture-pairing-token" for _, auth in records))
                        self.assertEqual(records[0][0], "/api/v1/jobs/active")
                        self.assertEqual(len(records), 1 if jobs_code == 401 else 2)
                        if expected == "supported":
                            self.assertEqual(result.returncode, 0)
                            self.assertIn("Helper supports Conversations", output)
                        elif expected == "upgrade":
                            self.assertEqual(result.returncode, 0)
                            self.assertIn("needs an update for the new app features", output)
                            self.assertNotIn("Helper supports Conversations", output)
                        else:
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn("Authenticated local backend request failed", output)
                            self.assertNotIn("needs an update for the new app features", output)
                self.assertTrue(all(call in {
                    "systemctl --user show-environment", "systemctl --user is-active --quiet watch-ceviz-backend",
                    "tailscale status",
                } for call in self.recorded_calls()))
                self.assertFalse((self.home / ".config").exists())
            finally:
                server.shutdown()
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
