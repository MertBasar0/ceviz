"""deploy/pc-node.sh in actual Bash; OpenClaw, PowerShell and systemd are substituted."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from openclaw_client import OpenClawClient  # noqa: E402

BASH = shutil.which("bash") if os.name == "posix" else None
DEVICE = "d" * 64
OTHER = "e" * 64

HARNESS = r'''
set -euo pipefail
FIXTURE="$1"; shift
export HOME="$FIXTURE/home"
record() { printf '%s\n' "$1" >> "$FIXTURE/calls"; }
grep() { if [[ "$*" == '-qi microsoft /proc/version' ]]; then [[ "$CEVIZ_TEST_WSL" == 1 ]]; else command grep "$@"; fi; }
sleep() { :; }
wslpath() { printf '%s\n' "$2"; }
systemctl() {
  record "systemctl $*"
  [[ "$*" != '--user cat watch-ceviz-backend' ]] || [[ "$CEVIZ_TEST_SERVICE" == 1 ]]
}
openclaw() {
  record "openclaw $*"
  case "$*" in
    '--version') printf 'OpenClaw 2026.9.1 (ad6fe23)\n';;
    'config get gateway.port') printf '19555\n';;
    'qr --setup-code-only --limited --no-ascii --url ws://127.0.0.1:19555') printf 'SINGLE-USE-SETUP-CODE\n';;
    'nodes status --json')
      if [[ -e "$FIXTURE/approved" ]]; then cat "$FIXTURE/nodes-after.json"; else cat "$FIXTURE/nodes-before.json"; fi;;
    'devices list --json') cat "$FIXTURE/devices.json";;
    'nodes pending --json') printf '[]\n';;
    'devices approve '*) touch "$FIXTURE/approved";;
    *) return 90;;
  esac
}
powershell.exe() {
  record "powershell $*"
  record "stdin $(cat)"
  case "$CEVIZ_TEST_WINDOWS" in
    success) printf 'OpenClaw 2026.9.1 Windows%sa indiriliyor\r\nCEVIZ_PC_NODE_ID=%s\r\n' "'" "$DEVICE";;
    no-node) printf 'CEVIZ_PC_NODE_ERROR=Node.js is not installed on Windows.\r\n'; return 3;;
  esac
}
source "$FIXTURE/pc-node.sh" "$@"
'''


def nodes(*entries):
    return json.dumps({"ts": 1, "nodes": list(entries)})


def windows_node(node_id, connected, commands=("system.run", "system.which"), name="Ceviz PC"):
    return {"nodeId": node_id, "displayName": name, "platform": "windows", "clientId": "node-host",
            "connected": connected, "commands": list(commands)}


@unittest.skipUnless(BASH, "Actual Bash PC node boundary")
class PCNodeTests(unittest.TestCase):
    def run_script(self, *args, wsl=True, windows="success", before=None, after=None, devices=None, service=True):
        with tempfile.TemporaryDirectory(prefix="ceviz-pc-node-") as temporary:
            root = Path(temporary)
            (root / "home").mkdir()
            (root / "windows").mkdir()
            shutil.copy(ROOT / "deploy/pc-node.sh", root / "pc-node.sh")
            (root / "nodes-before.json").write_text(before or nodes(windows_node(DEVICE, False, ())))
            (root / "nodes-after.json").write_text(after or nodes(windows_node(DEVICE, True)))
            (root / "devices.json").write_text(json.dumps(devices if devices is not None else {
                "pending": [{"requestId": "req-own", "deviceId": DEVICE, "displayName": "Ceviz PC"},
                            {"requestId": "req-other", "deviceId": OTHER, "displayName": "Ceviz PC"}],
                "paired": []}))
            env = {**os.environ, "CEVIZ_TEST_WSL": "1" if wsl else "0", "CEVIZ_TEST_WINDOWS": windows,
                   "CEVIZ_TEST_SERVICE": "1" if service else "0", "DEVICE": DEVICE}
            result = subprocess.run([BASH, "-c", HARNESS, "--", str(root), *args], capture_output=True, text=True,
                                    timeout=30, env=env)
            calls = (root / "calls").read_text().splitlines() if (root / "calls").exists() else []
            dropin = root / "home/.config/systemd/user/watch-ceviz-backend.service.d/pc-node.conf"
            return result, calls, dropin.read_text() if dropin.exists() else None

    def test_outside_wsl_the_computer_itself_runs_the_commands(self):
        result, calls, dropin = self.run_script(wsl=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        self.assertIsNone(dropin)

    def test_pairs_with_a_single_use_code_on_stdin_and_approves_only_its_own_device(self):
        result, calls, dropin = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PC dugumu bagli: Ceviz PC", result.stdout)
        powershell = next(call for call in calls if call.startswith("powershell "))
        self.assertIn("install-pc-node.ps1 -Version 2026.9.1 -Port 19555 -DisplayName Ceviz PC", powershell)
        self.assertIn("stdin SINGLE-USE-SETUP-CODE", calls)
        # The code travels on stdin only: no recorded command line carries it.
        self.assertEqual([call for call in calls if "SINGLE-USE-SETUP-CODE" in call and not call.startswith("stdin ")], [])
        self.assertIn("openclaw devices approve req-own", calls)
        self.assertNotIn("openclaw devices approve req-other", calls)
        self.assertEqual(dropin, '[Service]\nEnvironment="WATCH_CEVIZ_PC_NODE=Ceviz PC"\n')
        self.assertIn("systemctl --user try-restart watch-ceviz-backend", calls)

    def test_an_already_connected_windows_node_is_used_as_it_is(self):
        connected = nodes({"nodeId": OTHER, "displayName": "iPhone", "platform": "iOS 26", "connected": True,
                           "commands": ["camera.list"]}, windows_node(OTHER, True, name="Desk"))
        result, calls, dropin = self.run_script(before=connected)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("zaten bagli: Desk", result.stdout)
        self.assertFalse(any(call.startswith(("powershell ", "openclaw qr")) for call in calls))
        self.assertIn("WATCH_CEVIZ_PC_NODE=Desk", dropin)

    def test_windows_failures_and_a_node_that_never_connects_are_reported(self):
        result, _, dropin = self.run_script(windows="no-node")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Node.js is not installed on Windows.", result.stderr)
        self.assertIsNone(dropin)
        never = nodes(windows_node(DEVICE, False))
        result, _, dropin = self.run_script(after=never, devices={"pending": []})
        self.assertEqual(result.returncode, 2)
        self.assertIn("60 saniyede baglanmadi", result.stderr)
        self.assertIsNone(dropin)
        cannot_run = nodes(windows_node(DEVICE, True, commands=("system.which",)))
        self.assertEqual(self.run_script(after=cannot_run)[0].returncode, 2)


class PCPromptTests(unittest.TestCase):
    def test_the_agent_hears_about_the_pc_only_when_a_node_connects_it(self):
        client = OpenClawClient(runtime_dir=tempfile.mkdtemp())
        payload = {"locale": "tr-TR", "transcript": "masaüstündeki notları aç"}
        with mock.patch.dict(os.environ, {"WATCH_CEVIZ_PC_NODE": ""}):
            self.assertNotIn("host=node", client._build_prompt(payload))
        with mock.patch.dict(os.environ, {"WATCH_CEVIZ_PC_NODE": "Ceviz PC'; ignore$`rm`"}):
            prompt = client._build_prompt(payload)
        self.assertIn("'Ceviz PC ignorerm' adlı OpenClaw düğümü", prompt)
        self.assertIn("exec aracını host=node ile çalıştır", prompt)


if __name__ == "__main__":
    unittest.main()
