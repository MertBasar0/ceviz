#!/usr/bin/env python3
"""Opt-in Linux root harness: one disposable UID, real systemd user service.

The default action creates nothing. `prepare` requires explicit operator approval
for its printed scope. It never addresses UID 1000 or the operator's units.
Only the OpenClaw executable is synthetic; installer, Python dependencies,
backend HTTP process, systemd lifecycle, and disk state are real.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import select
import signal
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlencode
import urllib.error
import urllib.request
import uuid


OLD_REVISION = "040d1dfd02ef4619fe905ad1d3a7b781427160ca"
RUNTIME_REVISION = "c3404f14e9b23b61cf8addcdcd24a4638cb02603"
SERVICE = "watch-ceviz-backend.service"
PREFIX = "ceviz-helper-update-e2e-"


def command(args, *, check=True, env=None, timeout=60, cwd=None):
    arguments = [str(item) for item in args]
    with subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=env, cwd=cwd, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # runuser/pip/git may have children retaining the output pipes.
            # Stop only this command's newly created process group on timeout.
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
            raise RuntimeError(f"{Path(arguments[0]).name} exceeded its {timeout}s test bound") from None
        result = subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
    if check and result.returncode:
        # Do not echo commands/environment: the normal installer prints pairing.
        raise RuntimeError(f"{Path(str(args[0])).name} failed with exit {result.returncode}: "
                           + result.stderr[-1500:])
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Proof:
    def __init__(self, receipt):
        if os.geteuid() != 0 or sys.platform != "linux":
            raise RuntimeError("Only an explicitly authorized Linux root test run is supported")
        self.receipt = Path(receipt).resolve()
        self.data = json.loads(self.receipt.read_text()) if self.receipt.exists() else {}

    def save(self):
        self.receipt.write_text(json.dumps(self.data, indent=2) + "\n")
        os.chmod(self.receipt, 0o600)

    @property
    def home(self):
        return Path(self.data["home"])

    @property
    def app(self):
        return Path(self.data.get("active_app", str(self.home / "app")))

    @property
    def unit(self):
        return self.home / ".config/systemd/user" / SERVICE

    def owner(self):
        uid = self.data["uid"]
        name = self.data["user"]
        if uid in {0, 1000} or not name.startswith("ceviz-e2e-"):
            raise RuntimeError("Refusing non-test UID")
        record = pwd.getpwnam(name)
        if record.pw_uid != uid or Path(record.pw_dir).resolve() != self.home.resolve():
            raise RuntimeError("Test account identity changed")
        if self.home.parent != Path("/var/tmp") or not self.home.name.startswith(PREFIX):
            raise RuntimeError("Refusing unowned test home")
        marker = self.home / ".ceviz-test-owner"
        if marker.is_symlink() or marker.read_text() != self.data["nonce"]:
            raise RuntimeError("Test ownership marker changed")
        return uid

    def user_arguments(self, args, extra=None):
        uid = self.owner()
        environment = {
            "HOME": str(self.home), "USER": self.data["user"], "LOGNAME": self.data["user"],
            "PATH": f"{self.home}/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": f"/run/user/{uid}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
        }
        environment.update(extra or {})
        return ["runuser", "-u", self.data["user"], "--", "env", "-i",
                *[f"{key}={value}" for key, value in environment.items()], *map(str, args)]

    def user_command(self, args, *, check=True, timeout=60, extra=None):
        return command(self.user_arguments(args, extra), check=check, timeout=timeout, cwd=self.home)

    def systemctl(self, *args, check=True):
        return self.user_command(["systemctl", "--user", *args], check=check)

    def service(self):
        fields = "MainPID,ActiveState,SubState,FragmentPath,WorkingDirectory,ExecMainStartTimestampMonotonic"
        result = self.systemctl("show", SERVICE, f"--property={fields}").stdout
        state = dict(line.split("=", 1) for line in result.splitlines() if "=" in line)
        pid = int(state.get("MainPID", "0"))
        if pid:
            if Path(f"/proc/{pid}").stat().st_uid != self.owner():
                raise RuntimeError("Refusing foreign service process")
            state["cmdline"] = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        return state

    def process_environment(self):
        state = self.service()
        raw = Path(f"/proc/{state['MainPID']}/environ").read_bytes()
        return dict(os.fsdecode(item).split("=", 1) for item in raw.split(b"\0") if b"=" in item)

    def http(self, path, *, token=True, payload=None):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + (self.app / ".auth-token").read_text().strip()
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"http://127.0.0.1:{self.data['port']}{path}", headers=headers,
                                         data=None if payload is None else json.dumps(payload).encode())
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                body = json.loads(raw)
            except ValueError:
                body = raw.decode()
            return response.status, body

    def ready(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.service()
            if state["ActiveState"] == "active":
                try:
                    status, _ = self.http("/api/v1/jobs/active")
                    if status == 200:
                        return state
                except (OSError, TimeoutError):
                    pass
            time.sleep(0.2)
        raise RuntimeError("Owned real backend did not become healthy in 30 seconds")

    def write_owned(self, path, content, mode=0o600):
        path.parent.mkdir(parents=True, exist_ok=True)
        for parent in path.parents:
            if parent == self.home:
                break
            if parent.is_relative_to(self.home):
                os.chown(parent, self.data["uid"], self.data["gid"])
        path.write_text(content)
        os.chmod(path, mode)
        os.chown(path, self.data["uid"], self.data["gid"])

    def archive_bytes(self, source, revision):
        source = Path(source).resolve()
        git_args = ["git", "-C", str(source)]
        marker = source / ".git"
        if marker.is_file():
            git_dir = marker.read_text().strip().removeprefix("gitdir: ")
            if len(git_dir) > 2 and git_dir[1] == ":":
                git_dir = command(["wslpath", "-u", git_dir]).stdout.strip()
                git_args = ["git", f"--git-dir={git_dir}", f"--work-tree={source}"]
        return subprocess.run([*git_args, "archive", revision], check=True, capture_output=True).stdout

    def archive(self, source, revision):
        archive = self.archive_bytes(source, revision)
        self.app.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            contents.extractall(self.app, filter="data")

    def capture(self, name, result):
        # Normal installer output includes the fixture pairing token: retain a
        # redacted real process log, never the raw stdout in the workspace.
        output = result.stdout + result.stderr
        token_file = self.app / ".auth-token"
        if token_file.exists():
            output = output.replace(token_file.read_text().strip(), "<fixture-token-redacted>")
        output = "\n".join(line for line in output.splitlines()
                           if not any("\u2580" <= character <= "\u259f" for character in line)) + "\n"
        self.receipt.with_name(name + ".log").write_text(output)

    def prepare(self, source):
        if self.data:
            self.owner()
            if self.data["phase"] != "created" or self.app.exists():
                raise RuntimeError("Refusing to replace an existing test installation")
            name, home = self.data["user"], self.home
            account = pwd.getpwnam(name)
        else:
            suffix = uuid.uuid4().hex[:8]
            name = "ceviz-e2e-" + suffix
            home = Path(tempfile.mkdtemp(prefix=PREFIX, dir="/var/tmp"))
            nonce = uuid.uuid4().hex
            command(["useradd", "--no-create-home", "--home-dir", home, "--shell", "/bin/bash", name])
            account = pwd.getpwnam(name)
            if account.pw_uid in {0, 1000}:
                raise RuntimeError("Unsafe test UID allocated")
            self.data = {"user": name, "uid": account.pw_uid, "gid": account.pw_gid,
                         "home": str(home), "nonce": nonce, "old_revision": OLD_REVISION,
                         "source": str(Path(source).resolve()), "phase": "created"}
            os.chown(home, account.pw_uid, account.pw_gid)
            self.write_owned(home / ".ceviz-test-owner", nonce)
            self.save()
        self.archive(source, OLD_REVISION)
        for item in self.home.rglob("*"):
            if not item.is_symlink():
                os.chown(item, account.pw_uid, account.pw_gid)
        (home / "bin").mkdir()
        (home / "fixture").mkdir()
        (home / "empty-local-model").mkdir()
        for path in (home / "bin", home / "fixture", home / "empty-local-model"):
            os.chown(path, account.pw_uid, account.pw_gid)
        fixture = Path(__file__).with_name("helper_update_fake_openclaw.py")
        self.write_owned(home / "bin/openclaw", fixture.read_text(), 0o755)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.data["port"] = probe.getsockname()[1]
        self.save()
        command(["systemctl", "start", f"user@{account.pw_uid}.service"])
        self.systemctl("show-environment")  # Require a real user bus before installer fallback can run.
        env = {"WATCH_CEVIZ_NETWORK_MODE": "manual", "WATCH_CEVIZ_PORT": str(self.data["port"]),
               "WATCH_CEVIZ_WHISPER_MODEL": str(home / "empty-local-model"),
               "WATCH_CEVIZ_WHISPER_LANGUAGE": "en", "OPENCLAW_WATCH_AGENT": "fixture-custom"}
        result = self.user_command(["bash", self.app / "deploy/install.sh"], check=False, timeout=900, extra=env)
        self.capture("fresh-old-install", result)
        if result.returncode:
            raise RuntimeError(f"Real fresh installer failed ({result.returncode}); inspect redacted log")
        state = self.ready()
        assert state["FragmentPath"] == str(self.unit), state
        assert state["WorkingDirectory"] == str(self.app), state
        assert self.http("/api/v1/jobs/active", token=False)[0] == 401
        self.data.update(phase="fresh-old-installed", fresh_service=state,
                         fresh_token_hash=digest(self.app / ".auth-token"))
        self.save()
        print(json.dumps({"phase": self.data["phase"], "user": name, "uid": account.pw_uid,
                          "home": str(home), "port": self.data["port"], "real_pid": state["MainPID"]}))

    def reproduce(self):
        self.owner()
        if self.data["phase"] != "fresh-old-installed":
            raise RuntimeError("Reproduction requires its untouched fresh old install")
        before = self.ready()
        before_unit = self.unit.read_text()
        assert "OPENCLAW_WATCH_AGENT=fixture-custom" in before_unit
        assert "WATCH_CEVIZ_WHISPER_LANGUAGE=en" in before_unit
        token_hash = digest(self.app / ".auth-token")
        actual_path = self.process_environment().get("PATH", "")
        inherited_fixture = str(self.home / "bin") in actual_path.split(os.pathsep)
        resolved_cli = shutil.which("openclaw", path=actual_path)
        assert not inherited_fixture and resolved_cli != str(self.home / "bin/openclaw"), \
            "The installer PATH regression was masked by a manager/environment override"
        # Existing documented invocation on an installed helper: no customized
        # language/agent supplied again. Keep only isolation + no-model settings.
        result = self.user_command(["bash", self.app / "deploy/install.sh"], check=False, timeout=900,
                                   extra={"WATCH_CEVIZ_NETWORK_MODE": "manual",
                                          "WATCH_CEVIZ_PORT": str(self.data["port"]),
                                          "WATCH_CEVIZ_WHISPER_MODEL": str(self.home / "empty-local-model")})
        self.capture("old-installer-rerun", result)
        if result.returncode:
            raise RuntimeError("Old rerun did not reach the intended preservation regression")
        after = self.ready()
        after_unit = self.unit.read_text()
        observed = {"custom_agent_overwritten": "OPENCLAW_WATCH_AGENT=main" in after_unit,
                    "custom_language_overwritten": "WATCH_CEVIZ_WHISPER_LANGUAGE=tr" in after_unit,
                    "running_process_not_restarted": before["MainPID"] == after["MainPID"]
                    and before["ExecMainStartTimestampMonotonic"] == after["ExecMainStartTimestampMonotonic"],
                    "pairing_token_preserved": token_hash == digest(self.app / ".auth-token"),
                    "shell_fixture_path_not_inherited_by_service": not inherited_fixture}
        assert all(observed.values()), observed
        self.data.update(phase="old-rerun-regression-observed", old_rerun=observed)
        self.save()
        # Restore only this test installation's customization for upgrade proof.
        self.write_owned(self.unit, before_unit, 0o600)
        self.systemctl("daemon-reload")
        self.systemctl("restart", SERVICE)
        self.ready()
        print(json.dumps(observed))

    def commit_fixture(self, root):
        if not (root / ".git").exists():
            self.user_command(["git", "init", "-q", root])
        self.user_command(["git", "-C", root, "add", "--", "backend", "contracts", "deploy", ".gitignore"])
        self.user_command(["git", "-C", root, "-c", "user.name=Ceviz isolated test",
                           "-c", "user.email=ceviz-e2e@invalid.local", "commit", "-q", "-m", "Owned fixture snapshot"])
        return self.user_command(["git", "-C", root, "rev-parse", "HEAD"]).stdout.strip()

    def stage(self, source):
        self.owner()
        if self.data["phase"] != "old-rerun-regression-observed":
            raise RuntimeError("Staging requires the observed old-installer regression")
        source = Path(source).resolve()
        candidate = self.home / "candidate"
        if candidate.exists():
            raise RuntimeError("Refusing to overwrite a staged fixture")
        candidate.mkdir()
        os.chown(candidate, self.data["uid"], self.data["gid"])
        # Archive provenance is exact c340; only new updater/installer metadata
        # is copied from the explicitly reviewed uncommitted source lane.
        runtime_files = {}
        with tarfile.open(fileobj=io.BytesIO(self.archive_bytes(source, RUNTIME_REVISION))) as archive:
            for member in archive:
                if member.isfile() and member.name.startswith(("backend/", "contracts/")):
                    raw = archive.extractfile(member).read()
                    assert (source / member.name).read_bytes().replace(b"\r\n", b"\n") == raw, member.name
                    runtime_files[member.name] = hashlib.sha256(raw).hexdigest()
                    self.write_owned(candidate / member.name, raw.decode(), 0o644)
        for name in ("update.py", "install.sh", "doctor.sh", "requirements.txt", "helper-release.json"):
            self.write_owned(candidate / "deploy" / name, (source / "deploy" / name).read_text(), 0o644)
        self.user_command(["bash", "-n", candidate / "deploy/install.sh"])
        self.write_owned(candidate / ".gitignore", (source / ".gitignore").read_text(), 0o644)
        candidate_revision = self.commit_fixture(candidate)
        old_fixture_revision = self.commit_fixture(self.app)
        self.data.update(candidate=str(candidate), candidate_revision=candidate_revision,
                         old_fixture_revision=old_fixture_revision, runtime_revision=RUNTIME_REVISION,
                         runtime_file_hashes=runtime_files, updater_hash=digest(candidate / "deploy/update.py"))
        self.save()
        self.systemctl("stop", SERVICE)
        state = self.home / "saved-state"
        env_file = self.home / "operator.env"
        self.write_owned(env_file, "OPENCLAW_WATCH_AGENT=fixture-envfile\n", 0o600)
        dropin = self.unit.parent / (SERVICE + ".d") / "operator.conf"
        self.write_owned(dropin, "[Service]\n"
                         + f"Environment=PATH={self.home}/bin:/usr/bin:/bin\n"
                         + f"Environment=WATCH_CEVIZ_STATE_DIR={state}\n"
                         + "Environment=WATCH_CEVIZ_WHISPER_DEVICE=cpu\n"
                         + "Environment=WATCH_CEVIZ_PUSH_RELAY_URL=http://127.0.0.1:9\n"
                         + f"EnvironmentFile={env_file}\n")
        self.write_owned(self.app / ".env", "FIXTURE_LOCAL_SETTING=preserve-this-file\n")
        self.write_owned(self.app / ".env.local", "FIXTURE_SECOND_SETTING=preserve-too\n")
        jobs = [{"id": "saved-" + status, "name": "Saved fixture " + status, "status": status,
                 "created_at": 1, "elapsed_seconds": 0, "watch_summary": "Saved fixture summary.",
                 "phone_report": "Saved fixture report.", "transcript": "Synthetic retained text.",
                 "requires_phone_handoff": False, "next_actions": [], "outcome": "done"}
                for status in ("completed", "failed")]
        self.write_owned(state / "jobs.json", json.dumps({"jobs": jobs}))
        self.write_owned(state / "push-registration.json", json.dumps({"devices": {}, "installation_id": "fixture-only"}))
        seed = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from session_api import SubmissionStore, Submission
store = SubmissionStore(Path(sys.argv[2]))
identity = '11111111-1111-4111-8111-111111111111'
store.reserve(identity, Submission('agent:fixture:upgrade', 'fixture-session', 'fixture-fingerprint'))
store.record_reply(identity, 'started')
store.record_terminal(identity, 'completed')
"""
        self.user_command([self.app / ".venv/bin/python", "-B", "-c", seed,
                           candidate / "backend", state / "conversations.sqlite"])
        self.systemctl("daemon-reload")
        self.systemctl("start", SERVICE)
        self.ready()
        environment = self.process_environment()
        assert shutil.which("openclaw", path=environment["PATH"]) == str(self.home / "bin/openclaw")
        assert environment["OPENCLAW_WATCH_AGENT"] == "fixture-envfile"
        self.data.update(phase="staged", state_dir=str(state), dropin=str(dropin), env_file=str(env_file))
        self.save()
        print(json.dumps({"phase": "staged", "old_source": OLD_REVISION,
                          "runtime_source": RUNTIME_REVISION, "fixture_commit": candidate_revision,
                          "updater_hash": self.data["updater_hash"]}))

    def protected(self):
        paths = [self.app / ".auth-token", self.app / ".env", self.app / ".env.local",
                 self.unit, Path(self.data["dropin"]), Path(self.data["env_file"])]
        paths.extend(path for path in Path(self.data["state_dir"]).rglob("*") if path.is_file())
        hashes = {str(path.relative_to(self.home)): digest(path) for path in paths}
        # Whole installed environment, not just a sentinel file. Bytecode is
        # interpreter-generated cache rather than installed package/config data.
        venv = hashlib.sha256()
        for path in sorted((self.app / ".venv").rglob("*")):
            if "__pycache__" in path.parts or not (path.is_file() or path.is_symlink()):
                continue
            venv.update(path.relative_to(self.app).as_posix().encode())
            venv.update(os.readlink(path).encode() if path.is_symlink() else bytes.fromhex(digest(path)))
        hashes["venv_installed_content"] = venv.hexdigest()
        environment = self.process_environment()
        transient = {"INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID", "NOTIFY_SOCKET",
                     "LISTEN_PID", "WATCHDOG_PID"}
        hashes["service_environment"] = hashlib.sha256(json.dumps(
            sorted((key, value) for key, value in environment.items() if key not in transient)).encode()).hexdigest()
        return hashes

    def updater_arguments(self, *extra, revision=None, install_dir=None):
        candidate = Path(self.data["candidate"])
        return ["python3", candidate / "deploy/update.py", "--install-dir", install_dir or self.app,
                "--source", candidate, "--revision", revision or self.data["candidate_revision"], *extra]

    def update(self, name, *extra, revision=None, install_dir=None):
        result = self.user_command(self.updater_arguments(*extra, revision=revision, install_dir=install_dir),
                                   check=False, timeout=90)
        self.capture(name, result)
        return result

    def exercise(self):
        self.owner()
        if self.data["phase"] != "staged":
            raise RuntimeError("Expected the prepared old040 fixture")
        assert self.http("/api/v1/capabilities")[0] == 404
        baseline = self.protected()
        old_pid = self.service()["MainPID"]
        area = self.app / ".ceviz-updates"
        readonly = self.update("readonly-old-check", "--check")
        assert readonly.returncode == 0 and "READY:" in readonly.stdout, readonly.stderr
        assert not area.exists() and self.protected() == baseline
        consent = self.update("noninteractive-consent-refusal")
        assert consent.returncode != 0 and "--yes-maintenance" in consent.stderr
        assert not area.exists() and self.service()["MainPID"] == old_pid
        foreign = self.home / "not-this-installation"
        foreign.mkdir()
        os.chown(foreign, self.data["uid"], self.data["gid"])
        wrong = self.update("wrong-installation-refusal", "--yes-maintenance", install_dir=foreign)
        assert wrong.returncode != 0 and "different installation" in wrong.stderr
        assert self.service()["MainPID"] == old_pid and self.protected() == baseline
        # Exercise the new installer's actual early guard from an otherwise new
        # app root while this user's existing service is loaded.
        candidate = Path(self.data["candidate"])
        installer = self.user_command(["bash", candidate / "deploy/install.sh"], check=False)
        self.capture("new-installer-existing-unit-refusal", installer)
        assert installer.returncode != 0 and "Existing Ceviz installation" in installer.stderr
        assert not (candidate / ".venv").exists() and not (candidate / ".auth-token").exists()
        assert self.service()["MainPID"] == old_pid and self.protected() == baseline
        applied = self.update("real-old-to-new-upgrade", "--yes-maintenance")
        assert applied.returncode == 0 and "UPDATED:" in applied.stdout, applied.stderr
        new_state = self.ready()
        assert new_state["MainPID"] != old_pid
        assert self.protected() == baseline, "Upgrade altered operator configuration/state/dependencies"
        assert self.http("/api/v1/jobs/active", token=False)[0] == 401
        status, capabilities = self.http("/api/v1/capabilities")
        assert status == 200 and all(capabilities[key] is True for key in
                                    ("continuation_v1", "suggestion_approval_v1", "conversations_v1"))
        status, catalog = self.http("/api/v1/sessions")
        assert status == 200 and catalog["sessions"][0]["session_key"] == "agent:fixture:upgrade"
        query = urlencode({"session_key": "agent:fixture:upgrade"})
        status, history = self.http("/api/v1/sessions/history?" + query)
        assert status == 200 and history["messages"][0]["text"] == "Saved fixture history."
        repeated = self.update("already-current-no-restart", "--yes-maintenance")
        assert repeated.returncode == 0 and "UP TO DATE:" in repeated.stdout, repeated.stderr
        assert self.service()["MainPID"] == new_state["MainPID"] and self.protected() == baseline
        payload = {"session_key": "agent:fixture:upgrade", "session_id": "fixture-session",
                   "expected_leaf_entry_id": "fixture-leaf", "request_id": str(uuid.uuid4()),
                   "text": "Synthetic persistent delivery proof."}
        status, reply = self.http("/api/v1/sessions/message", payload=payload)
        assert status == 200 and reply["delivery_confirmed"] is True
        sending_pid = self.service()["MainPID"]
        busy = self.update("pending-delivery-no-stop", "--yes-maintenance")
        assert busy.returncode != 0 and "Active or unconfirmed conversation" in busy.stderr
        assert self.service()["MainPID"] == sending_pid
        status, terminal = self.http("/api/v1/sessions/run?" + query + "&run_id=" + payload["request_id"])
        assert status == 200 and terminal["status"] == "completed"
        after_send = self.protected()
        self.systemctl("restart", SERVICE)
        assert self.ready()["MainPID"] != sending_pid
        status, replay = self.http("/api/v1/sessions/message", payload=payload)
        assert status == 200 and replay == reply
        assert self.protected() == after_send
        calls = [json.loads(line) for line in (self.home / "fixture/calls.jsonl").read_text().splitlines()]
        sends = [call for call in calls if call["method"] == "chat.send"]
        assert len(sends) == 1 and sends[0]["params"]["idempotencyKey"] == payload["request_id"]
        assert sends[0]["params"]["sessionKey"] == payload["session_key"]
        self.data.update(phase="upgrade-proved", upgrade={"old_pid": old_pid, "new_pid": new_state["MainPID"],
                         "protected_hashes": baseline, "post_send_hashes": after_send,
                         "single_send_after_real_restart": True, "pending_refused_before_stop": True,
                         "repeat_update_without_restart": True, "new_installer_refused_before_writes": True})
        self.save()
        print(json.dumps({"phase": "upgrade-proved", "old_pid": old_pid, "new_pid": new_state["MainPID"],
                          "single_real_fixture_send_after_restart": len(sends), "preserved": True}))

    def faults(self):
        self.owner()
        if self.data["phase"] != "upgrade-proved":
            raise RuntimeError("Fault proof requires the healthy managed upgrade")
        candidate = Path(self.data["candidate"])
        entry = candidate / "backend/main.py"
        original = entry.read_text()
        baseline = self.protected()
        area = self.app / ".ceviz-updates"
        installed = digest(area / "installed.json")
        launcher = digest(self.app / "backend/main.py")
        try:
            self.write_owned(entry, "if __name__ == '__main__':\n"
                             "    raise RuntimeError('Intentional isolated startup failure')\n" + original, 0o644)
            failed_revision = self.commit_fixture(candidate)
            failed = self.update("real-startup-failure-rollback", "--yes-maintenance", revision=failed_revision)
            assert failed.returncode != 0 and "RECOVERED:" in failed.stdout, failed.stdout + failed.stderr
            assert "did not become healthy" in failed.stderr
            assert self.protected() == baseline and digest(area / "installed.json") == installed
            assert digest(self.app / "backend/main.py") == launcher and not (area / "pending.json").exists()
            journal = self.user_command(["journalctl", "--user-unit", SERVICE, "--no-pager", "-n", "100", "-o", "cat"])
            assert "Intentional isolated startup failure" in journal.stdout
            self.capture("real-startup-failure-journal", journal)
            self.write_owned(entry, original + "\n# Isolated crash-checkpoint fixture revision.\n", 0o644)
            crash_revision = self.commit_fixture(candidate)
            arguments = self.user_arguments(self.updater_arguments("--yes-maintenance", revision=crash_revision))
            process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, cwd=self.home, start_new_session=True)
            observed = []
            activated = False
            deadline = time.monotonic() + 30
            try:
                while time.monotonic() < deadline:
                    if select.select([process.stdout], [], [], 0.2)[0]:
                        line = process.stdout.readline()
                        if not line:
                            break
                        observed.append(line)
                        if line.startswith("ACTIVATED:"):
                            activated = True
                            # Kill only this harness-created updater process group;
                            # systemd's separately owned backend is not in that group.
                            os.killpg(process.pid, signal.SIGKILL)
                            break
                    elif process.poll() is not None:
                        break
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                remainder, _ = process.communicate(timeout=5)
            observed.append(remainder)
            self.capture("real-updater-sigkill", subprocess.CompletedProcess(arguments, process.returncode,
                                                                           "".join(observed), ""))
            assert activated and process.returncode != 0 and (area / "pending.json").exists()
            pending = digest(area / "pending.json")
            refused = self.update("interrupted-update-refusal", "--yes-maintenance")
            assert refused.returncode != 0 and "interrupted update exists" in refused.stderr
            assert digest(area / "pending.json") == pending
            recovered = self.update("real-sigkill-recovery", "--recover", "--yes-maintenance")
            assert recovered.returncode == 0 and "RECOVERED:" in recovered.stdout, recovered.stdout + recovered.stderr
            assert not (area / "pending.json").exists() and digest(area / "installed.json") == installed
            assert digest(self.app / "backend/main.py") == launcher and self.protected() == baseline
            self.data.update(phase="faults-proved", faults={"startup_failure_revision": failed_revision,
                             "sigkill_revision": crash_revision, "automatic_rollback_verified": True,
                             "explicit_recovery_verified": True, "runtime_state_unchanged": True})
            self.save()
            print(json.dumps(self.data["faults"]))
        finally:
            self.write_owned(entry, original, 0o644)
            self.commit_fixture(candidate)

    def fresh(self):
        self.owner()
        if self.data["phase"] != "faults-proved":
            raise RuntimeError("Fresh application proof follows recovery proof")
        candidate = Path(self.data["candidate"])
        old_app = self.app
        baseline = self.protected()
        old_token_hash = digest(old_app / ".auth-token")
        assert not (candidate / ".venv").exists() and not (candidate / ".auth-token").exists()
        assert str(self.home / "bin") not in self.systemctl("show-environment").stdout
        saved_unit = self.home / "fixture/old-installed.service"
        saved_dropins = self.home / "fixture/old-installed.service.d"
        dropins = self.unit.parent / (SERVICE + ".d")
        self.systemctl("disable", "--now", SERVICE)
        os.replace(self.unit, saved_unit)
        os.replace(dropins, saved_dropins)
        self.systemctl("daemon-reload")
        try:
            assert self.systemctl("show", SERVICE, "-p", "LoadState", "--value", check=False).stdout.strip() == "not-found"
            guard_root = self.home / "auth-only"
            self.write_owned(guard_root / "deploy/install.sh", (candidate / "deploy/install.sh").read_text(), 0o644)
            self.write_owned(guard_root / ".auth-token", "fixture-guard-only")
            guarded = self.user_command(["bash", guard_root / "deploy/install.sh"], check=False)
            self.capture("new-installer-auth-file-refusal", guarded)
            assert guarded.returncode != 0 and "Existing Ceviz installation" in guarded.stderr
            assert not self.unit.exists() and not (guard_root / ".venv").exists()
            # A real executable in an ordinary PATH containing spaces, a percent
            # and a quote validates systemd escaping, not only string generation.
            cli_dir = self.home / 'CLI space%quote"'
            self.write_owned(cli_dir / "openclaw", (self.home / "bin/openclaw").read_text(), 0o755)
            expected_path = f"{cli_dir}:/usr/bin:/bin"
            self.data["active_app"] = str(candidate)
            self.save()
            result = self.user_command(["bash", candidate / "deploy/install.sh"], check=False, timeout=900,
                                       extra={"PATH": expected_path, "WATCH_CEVIZ_NETWORK_MODE": "manual",
                                              "WATCH_CEVIZ_PORT": str(self.data["port"]),
                                              "WATCH_CEVIZ_WHISPER_MODEL": str(self.home / "empty-local-model"),
                                              "WATCH_CEVIZ_WHISPER_LANGUAGE": "en"})
            self.capture("fresh-new-application-install", result)
            assert result.returncode == 0, result.stderr
            first = self.ready()
            environment = self.process_environment()
            assert environment["PATH"] == expected_path and not dropins.exists()
            assert shutil.which("openclaw", path=environment["PATH"]) == str(cli_dir / "openclaw")
            assert digest(candidate / ".auth-token") != old_token_hash
            assert self.http("/api/v1/jobs/active", token=False)[0] == 401
            assert self.http("/api/v1/capabilities")[1]["conversations_v1"] is True
            assert self.http("/api/v1/sessions")[1]["sessions"][0]["session_key"] == "agent:fixture:upgrade"
            assert self.http("/api/v1/sessions/history?" + urlencode({"session_key": "agent:fixture:upgrade"}))[0] == 200
            self.systemctl("restart", SERVICE)
            restarted = self.ready()
            assert restarted["MainPID"] != first["MainPID"] and self.process_environment()["PATH"] == expected_path
            assert self.http("/api/v1/sessions")[0] == 200
            self.data["fresh_application"] = {"initial_pid": first["MainPID"], "restart_pid": restarted["MainPID"],
                                               "new_venv_and_pairing": True, "installer_path_survived_restart": True,
                                               "real_session_history_routes": True, "same_private_uid_not_clean_os": True}
        finally:
            self.systemctl("disable", "--now", SERVICE, check=False)
            if self.unit.exists():
                os.replace(self.unit, self.home / "fixture/fresh-installed.service")
            os.replace(saved_unit, self.unit)
            os.replace(saved_dropins, dropins)
            self.data.pop("active_app", None)
            self.save()
            self.systemctl("daemon-reload")
            self.systemctl("enable", "--now", SERVICE)
            self.ready()
        assert self.protected() == baseline, "Sequential fresh proof did not preserve the prior test installation"
        self.data["phase"] = "all-native-proved"
        self.save()
        print(json.dumps(self.data["fresh_application"]))

    def final(self, source):
        self.owner()
        if self.data["phase"] != "all-native-proved":
            raise RuntimeError("Final proof requires the completed fault/fresh cohorts")
        candidate = Path(self.data["candidate"])
        final_updater = (Path(source) / "deploy/update.py").read_text()
        expected = "dc4b03531ecf6c92dfbf9cba755bcf70133e89ad006c55e170aad797ee62162e"
        assert hashlib.sha256(final_updater.encode()).hexdigest() == expected, "Final updater changed; coordinate a fresh freeze"
        self.write_owned(candidate / "deploy/update.py", final_updater, 0o644)
        self.write_owned(candidate / "deploy/install.sh", (Path(source) / "deploy/install.sh").read_text(), 0o644)
        self.user_command(["bash", "-n", candidate / "deploy/install.sh"])
        baseline = self.protected()
        fresh_unit = self.home / "fixture/fresh-installed.service"
        saved_unit = self.home / "fixture/final-old-installed.service"
        dropins = self.unit.parent / (SERVICE + ".d")
        saved_dropins = self.home / "fixture/final-old-installed.service.d"
        runtime_backup = self.home / "fixture/new-runtime-backup"
        runtime_backup.mkdir()
        for name in ("backend", "contracts"):
            os.replace(candidate / name, runtime_backup / name)
        with tarfile.open(fileobj=io.BytesIO(self.archive_bytes(source, OLD_REVISION))) as archive:
            for member in archive:
                if member.isfile() and member.name.startswith(("backend/", "contracts/")):
                    self.write_owned(candidate / member.name, archive.extractfile(member).read().decode(), 0o644)
        self.commit_fixture(candidate)
        self.systemctl("disable", "--now", SERVICE)
        os.replace(self.unit, saved_unit)
        os.replace(dropins, saved_dropins)
        os.replace(fresh_unit, self.unit)
        self.data["active_app"] = str(candidate)
        self.save()
        self.systemctl("daemon-reload")
        try:
            self.systemctl("enable", "--now", SERVICE)
            before = self.ready()
            state = self.home / ".openclaw/ceviz-state"
            assert not (state / "conversations.sqlite").exists()
            assert self.http("/api/v1/capabilities")[0] == 404
            protected = {str(path): digest(path) for path in (self.unit, candidate / ".auth-token",
                                                              candidate / ".venv/pyvenv.cfg")}
            applied = self.update("final-no-sqlite-old040-upgrade", "--yes-maintenance")
            assert applied.returncode == 0 and "UPDATED:" in applied.stdout, applied.stdout + applied.stderr
            after = self.ready()
            assert after["MainPID"] != before["MainPID"] and self.http("/api/v1/capabilities")[1]["conversations_v1"]
            assert self.http("/api/v1/sessions")[0] == 200 and not (state / "conversations.sqlite").exists()
            assert protected == {name: digest(Path(name)) for name in protected}
            no_sqlite = {"old_pid": before["MainPID"], "new_pid": after["MainPID"],
                         "old_source": OLD_REVISION, "journal_absent_before_and_after": True}
        finally:
            self.systemctl("disable", "--now", SERVICE, check=False)
            os.replace(self.unit, fresh_unit)
            os.replace(saved_unit, self.unit)
            os.replace(saved_dropins, dropins)
            self.data.pop("active_app", None)
            self.save()
            self.systemctl("daemon-reload")
            self.systemctl("enable", "--now", SERVICE)
            self.ready()
            # Retain the no-store test's old code/launcher for inspection; restore
            # the candidate checkout's complete c340 source for the final update.
            for name in ("backend", "contracts"):
                os.replace(candidate / name, self.home / "fixture" / ("no-store-" + name))
                os.replace(runtime_backup / name, candidate / name)
        assert self.protected() == baseline
        self.data["candidate_revision"] = self.commit_fixture(candidate)
        self.data["updater_hash"] = expected
        self.save()
        before_pid = self.service()["MainPID"]
        applied = self.update("final-managed-to-managed-upgrade", "--yes-maintenance")
        assert applied.returncode == 0 and "UPDATED:" in applied.stdout, applied.stdout + applied.stderr
        assert self.ready()["MainPID"] != before_pid and self.protected() == baseline
        repeated = self.update("final-idempotent-rerun", "--yes-maintenance")
        assert repeated.returncode == 0 and "UP TO DATE:" in repeated.stdout
        self.data.update(phase="final-native-proved", final_native={"updater_hash": expected,
                         "fixture_commit": self.data["candidate_revision"], "no_sqlite_upgrade": no_sqlite,
                         "existing_metadata_preserved": True, "managed_update_and_rerun": True})
        self.save()
        print(json.dumps(self.data["final_native"]))

    def public(self, release_sha):
        self.owner()
        if self.data["phase"] != "final-native-proved" or not re.fullmatch(r"[0-9a-f]{40}", release_sha or ""):
            raise RuntimeError("Public proof requires the verified fixture and exact published release SHA")
        tag = "ceviz-helper-v2026.9.12-beta.1"
        expected_hash = self.data["final_native"]["updater_hash"]
        url = f"https://raw.githubusercontent.com/MertBasar0/ceviz/{tag}/deploy/update.py"
        with urllib.request.urlopen(url, timeout=30) as response:
            downloaded = response.read(1024 * 1024 + 1)
        assert len(downloaded) <= 1024 * 1024 and hashlib.sha256(downloaded).hexdigest() == expected_hash
        updater = self.home / "public-update.py"
        self.write_owned(updater, downloaded.decode(), 0o644)
        public_source = self.home / "public-source"
        assert not public_source.exists(), "Refusing to overwrite public-source evidence"
        self.user_command(["git", "clone", "--depth=1", "--branch", tag,
                           "https://github.com/MertBasar0/ceviz.git", public_source], timeout=60)
        actual_sha = self.user_command(["git", "-C", public_source, "rev-parse", "HEAD"]).stdout.strip()
        assert actual_sha == release_sha and digest(public_source / "deploy/update.py") == expected_hash
        names = self.user_command(["git", "-C", public_source, "ls-tree", "-r", "--name-only", "HEAD",
                                   "backend", "contracts"]).stdout.splitlines()
        actual_runtime = {name: digest(public_source / name) for name in names}
        assert actual_runtime == self.data["runtime_file_hashes"], "Published runtime differs from native-tested c340"
        installer_hash = digest(public_source / "deploy/install.sh")
        assert installer_hash == digest(Path(self.data["candidate"]) / "deploy/install.sh")
        self.user_command(["bash", "-n", public_source / "deploy/install.sh"])
        baseline = self.protected()
        before_pid = self.service()["MainPID"]
        guarded = self.user_command(["bash", public_source / "deploy/install.sh"], check=False)
        self.capture("public-installer-existing-service-refusal", guarded)
        assert guarded.returncode != 0 and "Existing Ceviz installation" in guarded.stderr
        assert not (public_source / ".venv").exists() and not (public_source / ".auth-token").exists()
        assert self.service()["MainPID"] == before_pid and self.protected() == baseline
        calls_file = self.home / "fixture/calls.jsonl"
        sends_before = sum(json.loads(line)["method"] == "chat.send" for line in calls_file.read_text().splitlines())
        # This is the published user flow: the HTTPS-fetched script performs its
        # default official remote/tag fetch. No local --source or --revision.
        arguments = ["python3", updater, "--install-dir", self.app, "--yes-maintenance"]
        applied = self.user_command(arguments, check=False, timeout=90)
        self.capture("public-default-remote-upgrade", applied)
        assert applied.returncode == 0 and "UPDATED:" in applied.stdout, applied.stdout + applied.stderr
        after = self.ready()
        assert after["MainPID"] != before_pid and self.protected() == baseline
        installed = json.loads((self.app / ".ceviz-updates/installed.json").read_text())
        assert installed["source_sha"] == release_sha and installed["release"] == tag
        assert self.http("/api/v1/jobs/active", token=False)[0] == 401
        status, capabilities = self.http("/api/v1/capabilities")
        assert status == 200 and all(capabilities.get(key) is True for key in
                                    ("continuation_v1", "suggestion_approval_v1", "conversations_v1"))
        status, catalog = self.http("/api/v1/sessions")
        assert status == 200 and catalog["sessions"][0]["session_key"] == "agent:fixture:upgrade"
        status, history = self.http("/api/v1/sessions/history?" + urlencode({"session_key": "agent:fixture:upgrade"}))
        assert status == 200 and history["messages"][0]["text"] == "Saved fixture history."
        repeated = self.user_command(arguments, check=False, timeout=90)
        self.capture("public-default-remote-idempotent-rerun", repeated)
        assert repeated.returncode == 0 and "UP TO DATE:" in repeated.stdout
        assert self.service()["MainPID"] == after["MainPID"] and self.protected() == baseline
        sends_after = sum(json.loads(line)["method"] == "chat.send" for line in calls_file.read_text().splitlines())
        assert sends_after == sends_before
        self.data.update(phase="public-proved", public_proof={"tag": tag, "release_sha": release_sha,
                         "updater_https_hash": expected_hash, "installer_lf_hash": installer_hash,
                         "runtime_matches_c340": True, "old_pid": before_pid, "new_pid": after["MainPID"],
                         "default_remote_fetch_and_rerun": True, "protected_data_unchanged": True,
                         "new_gateway_sends": sends_after - sends_before})
        self.save()
        print(json.dumps(self.data["public_proof"]))

    def cleanup(self):
        uid = self.owner()
        state = self.service()
        if state["FragmentPath"] and state["FragmentPath"] != str(self.unit):
            raise RuntimeError("Unexpected owned service definition; cleanup requires inspection")
        self.systemctl("disable", "--now", SERVICE, check=False)
        # The legacy installer enables lingering for its own user. Undo only
        # that test account, then stop its manager and remove the owned account.
        command(["loginctl", "disable-linger", self.data["user"]])
        command(["systemctl", "stop", f"user@{uid}.service"])
        command(["userdel", self.data["user"]])
        self.home.resolve().relative_to(Path("/var/tmp"))
        shutil.rmtree(self.home)
        self.data["phase"] = "cleaned"
        self.save()
        print("Only the owned test user, service manager, and marked temporary home were removed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "reproduce", "stage", "exercise", "faults", "fresh", "final", "public", "inspect", "cleanup"))
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--release-sha", help="Exact published SHA; required only for the explicitly authorized public proof")
    args = parser.parse_args()
    proof = Proof(args.receipt)
    if args.action == "prepare":
        if not args.source:
            parser.error("prepare requires --source")
        proof.prepare(args.source)
    elif args.action == "reproduce":
        proof.reproduce()
    elif args.action == "stage":
        if not args.source:
            parser.error("stage requires --source")
        proof.stage(args.source)
    elif args.action == "exercise":
        proof.exercise()
    elif args.action == "faults":
        proof.faults()
    elif args.action == "fresh":
        proof.fresh()
    elif args.action == "final":
        if not args.source:
            parser.error("final requires --source")
        proof.final(args.source)
    elif args.action == "public":
        proof.public(args.release_sha)
    elif args.action == "cleanup":
        proof.cleanup()
    else:
        proof.owner()
        print(json.dumps({"phase": proof.data["phase"], "service": proof.service()}))


if __name__ == "__main__":
    main()
