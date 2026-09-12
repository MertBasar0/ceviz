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
BASH = shutil.which("bash") if os.name == "posix" else next(
    (str(path) for path in (Path(r"C:\Program Files\Git\bin\bash.exe"), Path(r"C:\Program Files\Git\usr\bin\bash.exe"))
     if path.is_file()), None)


@unittest.skipUnless(BASH, "Actual Bash installer boundary")
class WindowsTailscaleInstallerTests(unittest.TestCase):
    def run_install(self, mode="success", network="tailscale", content=INSTALLER):
        with tempfile.TemporaryDirectory(prefix="ceviz-windows-install-") as temporary:
            root = Path(temporary)
            app = root / "app"
            for path in (app / "deploy", app / ".venv/bin", root / "home/.config/systemd/user", root / "empty-path"):
                path.mkdir(parents=True)
            (app / "deploy/install.sh").write_bytes(content.replace(b"\r\n", b"\n"))
            python = app / ".venv/bin/python"
            python.write_text('#!/bin/bash\nif [[ "$1" == "-c" ]]; then exit 0; fi\nprintf "pair-url %s\\n" "$2" >> "$CEVIZ_TEST_CALLS"\n')
            python.chmod(0o700)
            pip = app / ".venv/bin/pip"
            pip.write_text('#!/bin/bash\nprintf "pip\\n" >> "$CEVIZ_TEST_CALLS"\n')
            pip.chmod(0o700)
            # Source the complete installer in actual Bash. Closed PATH and
            # shell functions prevent all real service, package, network, WSL
            # or Windows task operations, including on Git Bash for Windows.
            harness = r'''
set -euo pipefail
cd "$1"
FIXTURE_ROOT="$PWD"
export HOME="$FIXTURE_ROOT/home" CEVIZ_TEST_CALLS="$FIXTURE_ROOT/calls"
export PATH="$FIXTURE_ROOT/empty-path" WSL_DISTRO_NAME='Fixture Distro'
export WATCH_CEVIZ_NETWORK_MODE="$2" CEVIZ_TEST_MODE="$3"
record() { printf '%s\n' "$1" >> "$CEVIZ_TEST_CALLS"; }
dirname() { printf '%s\n' "${1%/*}"; }
mkdir() { [[ "$*" == "-p $HOME/.config/systemd/user" ]]; }
grep() { [[ "$*" == '-qi microsoft /proc/version' ]]; }
openclaw() { return 99; }
systemctl() {
  record "systemctl $*"
  case "$*" in
    '--user show watch-ceviz-backend.service -p LoadState --value') printf 'not-found\n';;
    '--user show-environment'|'--user daemon-reload'|'--user enable --now watch-ceviz-backend') return 0;;
    *) return 98;;
  esac
}
openssl() { [[ "$*" == 'rand -hex 24' ]] && printf 'private-fixture-token\n'; }
wslpath() { [[ "$1" == '-w' ]] && printf '%s\n' "$2"; }
tr() { local line; while IFS= read -r line || [[ -n "$line" ]]; do printf '%s\n' "${line//$'\r'/}"; done; }
sed() { local line; while IFS= read -r line; do [[ "$line" == CEVIZ_RELAY_URL=* ]] && printf '%s\n' "${line#CEVIZ_RELAY_URL=}"; done; return 0; }
tail() { local line last=''; while IFS= read -r line; do last="$line"; done; printf '%s\n' "$last"; }
function powershell.exe {
  case "$*" in
    *install-wsl-lifetime.ps1*) record 'lifetime'; [[ "$CEVIZ_TEST_MODE" != lifetime-failure ]];;
    *install-relay.ps1*) record 'lan-relay'; printf 'CEVIZ_RELAY_URL=http://192.0.2.10:8080\n';;
    *Get-Command\ tailscale*) return 0;;
    *Invoke-RestMethod*)
      record 'localhost-probe'
      local token=''; IFS= read -r token || true
      [[ "$token" == private-fixture-token && "$CEVIZ_TEST_MODE" != probe-failure ]];;
    *tailscale\ serve*)
      record "serve $*"
      [[ "$CEVIZ_TEST_MODE" != serve-failure ]];;
    *Self.DNSName*)
      case "$CEVIZ_TEST_MODE" in
        dns-empty) printf '\n';;
        dns-invalid) printf 'https://not-a-host/path\n';;
        dns-failure) return 1;;
        *) printf 'fixture.tail.ts.net\n';;
      esac;;
    *Get-ScheduledTask*)
      record 'passive-lifetime-query'
      [[ "$*" == *'wsl.exe --list --running --quiet'* && "$*" != *'wsl.exe --distribution'* ]] || return 96
      local distro=''; IFS= read -r distro || true
      [[ "$distro" == 'Fixture Distro' && "$CEVIZ_TEST_MODE" != keeper-down ]];;
    *) return 97;;
  esac
}
source "$FIXTURE_ROOT/app/deploy/install.sh"
'''
            result = subprocess.run([BASH, "-c", harness, "--", root.as_posix(), network, mode],
                                    capture_output=True, text=True, timeout=15,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            calls = (root / "calls").read_text().splitlines() if (root / "calls").exists() else []
            return result, calls

    def test_windows_tailscale_uses_independent_lifetime_and_authenticated_localhost_without_lan(self):
        result, calls = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(calls.index("lifetime"), calls.index("localhost-probe"))
        self.assertNotIn("lan-relay", calls)
        serve = [call for call in calls if call.startswith("serve ")]
        self.assertEqual(len(serve), 1)
        self.assertIn("http://127.0.0.1:8080", serve[0])
        self.assertNotIn("192.0.2.10", serve[0])
        self.assertEqual(calls[-1], "pair-url https://fixture.tail.ts.net/ceviz")
        self.assertNotIn("private-fixture-token", result.stdout + result.stderr + "\n".join(calls))

    def test_lifetime_localhost_or_publish_failure_cannot_report_pairing_success(self):
        for mode in ("lifetime-failure", "probe-failure", "serve-failure", "dns-empty", "dns-invalid", "dns-failure"):
            with self.subTest(mode=mode):
                result, calls = self.run_install(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call.startswith("pair-url ") for call in calls))
                self.assertNotIn("lan-relay", calls)
                if mode == "lifetime-failure":
                    self.assertNotIn("localhost-probe", calls)
                if mode in ("lifetime-failure", "probe-failure"):
                    self.assertFalse(any(call.startswith("serve ") for call in calls))

    def test_explicit_lan_mode_remains_separate(self):
        result, calls = self.run_install(network="relay")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("lifetime", calls)
        self.assertIn("lan-relay", calls)
        self.assertNotIn("localhost-probe", calls)
        self.assertFalse(any(call.startswith("serve ") for call in calls))
        self.assertEqual(calls[-1], "pair-url http://192.0.2.10:8080")

    def test_doctor_reports_lifetime_gap_without_starting_wsl_or_installing(self):
        for mode in ("success", "keeper-down"):
            with self.subTest(mode=mode):
                result, calls = self.run_install(mode=mode, content=DOCTOR)
                self.assertIn("passive-lifetime-query", calls)
                self.assertNotIn("lifetime", calls)
                self.assertNotIn("lan-relay", calls)
                self.assertFalse(any(call.startswith(("serve ", "pair-url ", "pip")) for call in calls))
                expected = "Independent Windows WSL lifetime task and selected distro are running" if mode == "success" else "Persistent WSL availability is not established"
                self.assertIn(expected, result.stdout)


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
