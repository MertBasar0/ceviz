#!/usr/bin/env python3
"""Update an existing Linux/WSL Ceviz user service without reinstalling it.

Only backend/main.py is activated: it execs a complete, verified release snapshot.
Service settings, Python dependencies, pairing, network and runtime state are not
rewritten. Receipts/backups below .ceviz-updates are deployment artifacts, never
restorable conversation/job state. See deploy/README.md before using --recover.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SERVICE = "watch-ceviz-backend.service"
REPOSITORY = "https://github.com/MertBasar0/ceviz.git"
DEFAULT_RELEASE = "ceviz-helper-v2026.9.12-beta.1"
LAUNCHER_HEADER = b"# Ceviz managed release launcher; use deploy/update.py, not git reset.\n"
TRANSIENT_ENV = {"INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID", "NOTIFY_SOCKET", "LISTEN_PID", "WATCHDOG_PID"}


class UpdateError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise UpdateError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    if not path.exists():
        return None
    require(path.is_file() and not path.is_symlink(), "A protected path is not a regular file.")
    return digest(path.read_bytes())


def confined(root, relative):
    part = PurePosixPath(relative)
    require(not part.is_absolute() and part.parts and all(p not in {".", ".."} for p in part.parts), "Unsafe release path.")
    target = root.joinpath(*part.parts)
    require(target.resolve().is_relative_to(root.resolve()) and not target.is_symlink(), "Release path escapes its directory.")
    require(all(not parent.is_symlink() for parent in target.parents if parent != root and parent.is_relative_to(root)),
            "Symlinked deployment directories are not supported.")
    return target


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_bytes(path, content, mode=0o600):
    require(not path.is_symlink(), "Refusing to replace a symlink.")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".ceviz-write-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()  # Only this call's mkstemp file, never a user directory.


def write_receipt(path, value):
    atomic_bytes(path, json.dumps(value, sort_keys=True).encode())


def command(arguments, **kwargs):
    try:
        return subprocess.check_output(arguments, stderr=subprocess.PIPE, timeout=30, **kwargs)
    except (OSError, subprocess.SubprocessError):
        # Subprocess output can contain service credentials or CLI diagnostics.
        raise UpdateError("A required local command failed; no credentials or command output were printed.") from None


def property_value(name):
    return command(["systemctl", "--user", "show", SERVICE, "--property=" + name, "--value"], text=True).strip()


def process_details(pid):
    process = Path("/proc") / str(pid)
    require(pid > 0 and process.stat().st_uid == os.getuid(), "Ceviz process is not owned by this user.")
    arguments = [os.fsdecode(value) for value in (process / "cmdline").read_bytes().split(b"\0") if value]
    environment = dict(os.fsdecode(value).split("=", 1) for value in (process / "environ").read_bytes().split(b"\0") if b"=" in value)
    # PID alone is not identity: field 22 survives exec, but changes on PID reuse.
    started = (process / "stat").read_text().rsplit(")", 1)[1].split()[19]
    return arguments, environment, started


def environment_hash(environment):
    return digest(json.dumps(sorted((key, value) for key, value in environment.items() if key not in TRANSIENT_ENV)).encode())


def state_hashes(directory):
    if not directory.exists():
        return {}
    require(directory.is_dir(), "Ceviz state directory is invalid.")
    # Do not copy runtime state into code rollback artifacts. Hashes detect races.
    result = {}
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Symlinked Ceviz state needs manual update assistance.")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = file_hash(path)
    return result


def runtime_hashes(directory, legacy=False):
    """Hash the whole executable bundle; legacy launchers have separate ownership."""
    require(directory.is_dir() and not directory.is_symlink(), "Invalid runtime directory.")
    roots = [directory / name for name in ("backend", "contracts")] if legacy else [directory]
    result = {}
    for root in roots:
        require(root.is_dir() and not root.is_symlink(), "Incomplete runtime directory.")
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink(), "Symlinked runtime requires manual assistance.")
            relative = path.relative_to(directory).as_posix()
            if legacy and "__pycache__" in path.relative_to(root).parts:
                continue  # Python's compiled cache is not source or a rollback artifact.
            require(path.is_dir() or path.is_file(), "Unsupported runtime file.")
            if path.is_file():
                result[relative] = file_hash(path)
    return result


def verify_runtime(directory, expected, legacy=False, launcher_hashes=()):
    require(isinstance(expected, dict) and bool(expected), "Missing runtime verification receipt.")
    for name, value in expected.items():
        confined(directory, name)
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Invalid runtime hash.")
    actual = runtime_hashes(directory, legacy)
    if legacy and launcher_hashes:
        require(actual.get("backend/main.py") in launcher_hashes, "Legacy launcher changed outside this update.")
        actual["backend/main.py"] = expected.get("backend/main.py")
    require(actual == expected, "Runtime snapshot verification failed; no changed files were overwritten or executed.")


def journal_idle(directory):
    path = directory / "conversations.sqlite"
    if not path.exists():
        return
    require(path.is_file() and not path.is_symlink(), "Conversation journal needs manual inspection.")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)) as database:
            pending = database.execute("SELECT count(*) FROM conversation_submissions WHERE terminal_status IS NULL").fetchone()[0]
    except sqlite3.Error:
        raise UpdateError("Conversation tracking could not be checked. No records were removed or repaired.") from None
    require(pending == 0, "Active or unconfirmed conversation delivery remains. Review it in Ceviz; contact support if unresolved.")


def lifecycle(jobs):
    require(isinstance(jobs, list) and all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in jobs), "Invalid job response.")
    require(all(row.get("status") in {"completed", "failed"} for row in jobs),
            "Ceviz has active or unconfirmed work. Wait before updating; nothing was stopped.")
    return sorted((row["id"], row["status"]) for row in jobs)


class Installation:
    def __init__(self, root):
        require(sys.platform == "linux", "Automatic update currently supports Linux/WSL systemd user services. Contact support for manual/macOS installations.")
        require(root.is_dir() and not root.is_symlink() and root != Path(root.anchor), "Choose the actual Ceviz installation directory.")
        self.root = root.resolve()
        self.entry = confined(self.root, "backend/main.py")
        self.area = confined(self.root, ".ceviz-updates")
        self.pending = self.area / "pending.json"
        self.installed = self.area / "installed.json"
        require(property_value("LoadState") == "loaded" and property_value("Transient") == "no", "A persistent Ceviz user service is required. No process was stopped.")
        require(Path(property_value("WorkingDirectory")).resolve() == self.root, "The Ceviz service belongs to a different installation.")
        self.config_hash = digest(command(["systemctl", "--user", "cat", SERVICE]))

    def snapshot(self, allowed_entries=None):
        require(property_value("ActiveState") == "active", "Start your existing Ceviz service before updating, or use --recover for an interrupted update.")
        pid = int(property_value("MainPID"))
        arguments, environment, started = process_details(pid)
        require(len(arguments) in {2, 3} and Path(arguments[0]).is_absolute(), "Unrecognized Ceviz launch command; contact support.")
        # Distinct virtualenv executables often resolve to the same system
        # binary. The invocation path, not that shared symlink target, owns it.
        require(arguments[0] == str(self.root / ".venv/bin/python"), "Ceviz is not using this installation's Python environment.")
        allowed = {str(self.entry)} if allowed_entries is None else set(allowed_entries)
        if allowed_entries is None and self.installed.exists():
            receipt = self.read_receipt(self.installed)
            require(file_hash(self.entry) == receipt["new_hash"], "Managed launcher changed outside the updater.")
            allowed.add(receipt["new_entry"])
        require(arguments[1] in allowed, "Running Ceviz code differs from the expected installation.")
        port = int(arguments[2]) if len(arguments) == 3 else 8080
        require(0 < port <= 65535, "Invalid Ceviz port.")
        token = environment.get("WATCH_CEVIZ_AUTH_TOKEN", "").strip()
        require(bool(token), "An authenticated Ceviz service is required before updating.")
        home = environment.get("HOME", "")
        require(Path(home).is_absolute(), "Ceviz has no absolute HOME directory.")
        state = Path(environment.get("WATCH_CEVIZ_STATE_DIR", str(Path(home) / ".openclaw/ceviz-state"))).resolve()
        require(not state.is_relative_to(self.area) and not self.area.is_relative_to(state)
                and not self.entry.is_relative_to(state), "Runtime state overlaps code deployment paths.")
        return {"pid": pid, "started": started, "environment": environment, "environment_hash": environment_hash(environment),
                "token": token, "port": port, "state": state, "python": arguments[0], "entry": arguments[1]}

    def read_receipt(self, path):
        require(not path.is_symlink() and path.is_file(), "Invalid deployment receipt.")
        receipt = json.loads(path.read_text())
        require(receipt.get("root") == str(self.root) and receipt.get("service") == SERVICE, "Deployment receipt belongs to another installation.")
        for key in ("old_hash", "new_hash", "environment_hash", "config_hash"):
            require(re.fullmatch(r"[0-9a-f]{64}", receipt.get(key, "")), "Invalid deployment hash.")
        backup = confined(self.area, receipt["backup"])
        require(file_hash(backup) == receipt["old_hash"], "Previous launcher backup failed verification.")
        if receipt.get("old_receipt_backup"):
            require(file_hash(confined(self.area, receipt["old_receipt_backup"])) == receipt["old_receipt_hash"],
                    "Previous deployment receipt failed verification.")
        require(re.fullmatch(r"[0-9a-f]{40}", receipt.get("source_sha", "")), "Invalid release revision.")
        runtime = confined(self.area, "releases/" + receipt["source_sha"])
        require(receipt["new_entry"] == str(confined(runtime, "backend/main.py")), "Invalid release entry.")
        verify_runtime(runtime, receipt.get("runtime_files"))
        return receipt

    def api(self, before, path, token=None):
        require(path.startswith("/api/v1/"), "Only Ceviz read-only verification routes are allowed.")
        request = Request("http://127.0.0.1:" + str(before["port"]) + path, method="GET")
        request.add_header("Authorization", "Bearer " + (before["token"] if token is None else token))
        with urlopen(request, timeout=12) as response:
            require(response.status == 200, "Unexpected Ceviz response.")
            body = response.read(16 * 1024 * 1024 + 1)
            require(len(body) <= 16 * 1024 * 1024, "Ceviz verification response is too large.")
            return json.loads(body)

    def idle(self, before):
        require(int(property_value("MainPID")) == before["pid"], "Ceviz restarted during preparation; try again.")
        _, environment, started = process_details(before["pid"])
        require(started == before["started"] and environment_hash(environment) == before["environment_hash"], "Ceviz process changed during preparation.")
        jobs = self.api(before, "/api/v1/jobs/active").get("jobs")
        expected = lifecycle(jobs)
        journal_idle(before["state"])
        before["state_hashes"] = state_hashes(before["state"])
        before["jobs"] = expected
        return before

    def preserved(self, receipt):
        require(digest(command(["systemctl", "--user", "cat", SERVICE])) == receipt["config_hash"], "Service settings changed; automatic recovery stopped.")
        require(state_hashes(Path(receipt["state_dir"])) == receipt["state_hashes"], "Ceviz state changed during maintenance; do not resend commands. Contact support.")

    def stop(self):
        command(["systemctl", "--user", "stop", SERVICE])
        require(int(property_value("MainPID")) == 0 and property_value("ActiveState") == "inactive", "Ceviz did not fully stop.")

    def verify_started(self, receipt, expected_entry, capabilities=()):
        command(["systemctl", "--user", "start", SERVICE])
        deadline = time.monotonic() + 20
        while True:
            try:
                current = self.snapshot({expected_entry})
                jobs = self.api(current, "/api/v1/jobs/active").get("jobs")
                break
            except (UpdateError, OSError, URLError):
                if time.monotonic() >= deadline:
                    raise UpdateError("Ceviz did not become healthy after restart.") from None
                time.sleep(0.2)
        require(current["entry"] == expected_entry and current["environment_hash"] == receipt["environment_hash"], "Restarted Ceviz environment/code differs.")
        require(str(current["state"]) == receipt["state_dir"] and current["port"] == receipt["port"], "Ceviz connection/state location changed.")
        require(lifecycle(jobs) == [tuple(row) for row in receipt["jobs"]], "Job identities changed during update.")
        try:
            self.api(current, "/api/v1/jobs/active", token="")
        except HTTPError as unauthorized:
            require(unauthorized.code == 401, "Authentication verification failed.")
        else:
            raise UpdateError("Ceviz unexpectedly allowed an unauthenticated request.")
        if capabilities:
            actual = self.api(current, "/api/v1/capabilities")
            require(all(actual.get(key) is True for key in capabilities), "The new Ceviz capabilities are unavailable.")
            catalog = self.api(current, "/api/v1/sessions")
            require(isinstance(catalog.get("sessions"), list) and isinstance(catalog.get("agents"), list), "Conversation discovery failed.")
            sample = next((row for row in catalog["sessions"] if row.get("session_id") and not row.get("archived")), None)
            if sample:
                history = self.api(current, "/api/v1/sessions/history?" + urlencode({"session_key": sample["session_key"]}))
                require(history.get("session", {}).get("session_key") == sample["session_key"] and isinstance(history.get("messages"), list), "Conversation history verification failed.")
        self.preserved(receipt)


def release_snapshot(source, revision, area):
    require(re.fullmatch(r"[0-9a-f]{40}", revision) or re.fullmatch(r"ceviz-helper-v[0-9.]+-beta\.[0-9]+", revision), "Use an exact commit or a Ceviz helper release tag.")
    sha = command(["git", "-C", str(source), "rev-parse", "--verify", revision + "^{commit}"], text=True).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "Could not identify the source commit.")
    archive = command(["git", "-C", str(source), "archive", sha, "backend", "contracts", "deploy/requirements.txt", "deploy/helper-release.json"])
    require(len(archive) <= 16 * 1024 * 1024, "Helper release is unexpectedly large.")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        for member in stream:
            if member.isdir():
                continue
            require(member.isfile() and member.size <= 2 * 1024 * 1024, "Unsupported release archive entry.")
            name = member.name
            require(name not in files and (name.startswith(("backend/", "contracts/"))
                    or name in {"deploy/requirements.txt", "deploy/helper-release.json"}), "Unexpected release path.")
            confined(area, name)
            data = stream.extractfile(member).read()
            if name.endswith(".py"):
                compile(data, name, "exec")
            elif name.endswith(".json"):
                json.loads(data)
            files[name] = data
    require("backend/main.py" in files and "contracts/watch-command-request.schema.json" in files, "Incomplete Ceviz runtime.")
    manifest = json.loads(files["deploy/helper-release.json"])
    require(re.fullmatch(r"ceviz-helper-v[0-9.]+-beta\.[0-9]+", manifest.get("release", "")), "Invalid helper release identity.")
    require(manifest.get("capabilities") == ["continuation_v1", "suggestion_approval_v1", "conversations_v1"], "Unexpected compatibility contract.")
    destination = confined(area, "releases/" + sha)
    if not destination.exists():
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="preparing-", dir=destination.parent))
        for name, data in files.items():
            path = confined(staging, name)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            atomic_bytes(path, data, 0o444)
        for path in sorted((p for p in staging.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            path.chmod(0o500)  # Runtime imports must not add caches to the verified snapshot.
            sync_directory(path)
        staging.chmod(0o500)
        sync_directory(staging)
        os.rename(staging, destination)
        sync_directory(destination.parent)
    require({path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()} == set(files), "Existing snapshot file set changed.")
    require(all(file_hash(confined(destination, name)) == digest(data) for name, data in files.items()), "Release snapshot failed verification.")
    return destination, sha, manifest


def validate_unmanaged_source(installation):
    if installation.installed.exists():
        installation.read_receipt(installation.installed)
        return
    require(not installation.entry.read_bytes().startswith(LAUNCHER_HEADER), "Managed launcher has no valid receipt; contact support.")
    changed = command(["git", "-C", str(installation.root), "status", "--porcelain", "--untracked-files=all", "--", "backend", "contracts", "deploy/requirements.txt"])
    require(not changed.strip(), "Local backend changes were found. They were not overwritten; contact support before updating.")


def recover_update(installation):
    receipt = installation.read_receipt(installation.pending)
    require(file_hash(installation.entry) in {receipt["old_hash"], receipt["new_hash"]}, "Launcher changed outside this update; recovery stopped.")
    old_runtime = Path(receipt["old_runtime_root"])
    if receipt["old_entry"] == str(installation.entry):
        require(old_runtime == installation.root, "Invalid previous runtime directory.")
        verify_runtime(old_runtime, receipt.get("old_runtime_files"), legacy=True,
                       launcher_hashes={receipt["old_hash"], receipt["new_hash"]})
    else:
        require(receipt.get("old_receipt_backup"), "Previous managed runtime receipt is missing.")
        previous = installation.read_receipt(confined(installation.area, receipt["old_receipt_backup"]))
        require(receipt["old_entry"] == previous["new_entry"] and old_runtime == Path(previous["new_entry"]).parents[1],
                "Previous runtime does not match its verified receipt.")
        verify_runtime(old_runtime, receipt.get("old_runtime_files"))
    installation.preserved(receipt)
    journal_idle(Path(receipt["state_dir"]))
    if int(property_value("MainPID")) > 0:
        before = installation.snapshot({receipt["old_entry"], receipt["new_entry"]})
        installation.idle(before)
        require(before["environment_hash"] == receipt["environment_hash"], "Service environment changed before recovery.")
    installation.stop()
    installation.preserved(receipt)
    atomic_bytes(installation.entry, confined(installation.area, receipt["backup"]).read_bytes(), receipt["old_mode"])
    installation.verify_started(receipt, receipt["old_entry"])
    if receipt.get("old_receipt_backup"):
        atomic_bytes(installation.installed, confined(installation.area, receipt["old_receipt_backup"]).read_bytes())
    elif installation.installed.exists():
        require(installation.installed.read_bytes() == json.dumps(receipt, sort_keys=True).encode(),
                "Installed receipt changed outside this update; contact support.")
        installation.installed.unlink()
    installation.pending.rename(installation.area / ("recovered-" + receipt["id"] + ".json"))
    sync_directory(installation.area)
    print("RECOVERED: previous Ceviz code is healthy; pairing/settings/runtime state were not restored or deleted.", flush=True)


def apply_update(installation, destination, sha, manifest):
    validate_unmanaged_source(installation)
    before = installation.snapshot()
    expected_requirements = (destination / "deploy/requirements.txt").read_bytes()
    require((installation.root / "deploy/requirements.txt").read_bytes() == expected_requirements,
            "This release changes Python dependencies. Guided upgrade is required; no packages/settings were changed.")
    target = destination / "backend/main.py"
    launcher = LAUNCHER_HEADER + ("import os, sys\nos.execv(sys.executable, [sys.executable, " + repr(str(target)) + "] + sys.argv[1:])\n").encode()
    if before["entry"] == str(target) and file_hash(installation.entry) == digest(launcher):
        print("UP TO DATE: this helper release is already running.", flush=True)
        return
    # Import checks run with the real interpreter/config but no service/model/Gateway call.
    command([before["python"], "-c", "import sys; sys.path.insert(0, sys.argv[1]); import main, session_api; import sqlite3",
             str(destination / "backend")], env={**before["environment"], "PYTHONDONTWRITEBYTECODE": "1"}, cwd=installation.root)
    installation.idle(before)
    identifier = str(time.time_ns())
    old = installation.entry.read_bytes()
    backup = "backups/" + identifier + ".py"
    saved = confined(installation.area, backup)
    saved.parent.mkdir(mode=0o700, exist_ok=True)
    atomic_bytes(saved, old, 0o400)
    old_receipt_backup = None
    old_receipt_hash = None
    if installation.installed.exists():
        old_receipt_backup = "backups/" + identifier + ".json"
        old_receipt = installation.installed.read_bytes()
        old_receipt_hash = digest(old_receipt)
        atomic_bytes(confined(installation.area, old_receipt_backup), old_receipt, 0o400)
    legacy = before["entry"] == str(installation.entry)
    old_runtime = installation.root if legacy else Path(before["entry"]).parents[1]
    receipt = {"id": identifier, "root": str(installation.root), "service": SERVICE, "source_sha": sha,
               "release": manifest["release"], "backup": backup, "old_hash": digest(old), "new_hash": digest(launcher),
               "old_mode": stat.S_IMODE(installation.entry.stat().st_mode), "old_entry": before["entry"], "new_entry": str(target),
               "environment_hash": before["environment_hash"], "config_hash": installation.config_hash,
               "state_dir": str(before["state"]), "state_hashes": before["state_hashes"], "port": before["port"], "jobs": before["jobs"],
               "old_receipt_backup": old_receipt_backup, "old_receipt_hash": old_receipt_hash,
               "runtime_files": runtime_hashes(destination), "old_runtime_root": str(old_runtime),
               "old_runtime_files": runtime_hashes(old_runtime, legacy)}
    write_receipt(installation.pending, receipt)
    print("PREPARED: complete helper snapshot and code-only recovery backup verified.", flush=True)
    try:
        # The explicit maintenance acknowledgment is required; idle observation
        # alone cannot stop a phone from sending between this check and stop.
        installation.idle(before)
        installation.preserved(receipt)
        installation.stop()
        installation.preserved(receipt)
        require(file_hash(installation.entry) == receipt["old_hash"], "Launcher changed during preparation.")
        atomic_bytes(installation.entry, launcher, receipt["old_mode"])
        print("ACTIVATED: one launcher switch; no mixed-version runtime files.", flush=True)
        installation.verify_started(receipt, str(target), manifest["capabilities"])
        write_receipt(installation.installed, receipt)
        installation.pending.rename(installation.area / ("completed-" + identifier + ".json"))
        sync_directory(installation.area)
        print("UPDATED: " + manifest["release"] + " (" + sha + "). Pairing, settings and job history preserved; conversations verified.", flush=True)
    except BaseException:
        try:
            recover_update(installation)
        except BaseException:
            print("RECOVERY REQUIRED: keep Ceviz clients idle and run this updater with --recover. Runtime state was not rolled back. Contact support if recovery refuses.", flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", type=Path, default=Path.cwd())
    parser.add_argument("--revision", default=DEFAULT_RELEASE, help="Published helper tag or exact source commit")
    parser.add_argument("--source", type=Path, help="Use a trusted local Git checkout for offline/staged updates")
    parser.add_argument("--check", action="store_true", help="Read-only installation/idle check")
    parser.add_argument("--recover", action="store_true", help="Recover only the pending update's previous code")
    parser.add_argument("--yes-maintenance", action="store_true", help="Confirm that all Ceviz clients will remain idle until completion")
    args = parser.parse_args()
    require(sys.version_info >= (3, 10), "Python 3.10 or newer is required.")
    installation = Installation(args.install_dir)
    if args.check:
        require(not args.recover, "Choose --check or --recover, not both.")
        installation.idle(installation.snapshot())
        print("READY: owned authenticated Ceviz service; no active/unconfirmed delivery. No changes made.")
        return
    if not args.yes_maintenance:
        require(sys.stdin.isatty(), "Keep every Ceviz client idle, then pass --yes-maintenance. No service changes made.")
        require(input("Do not send Ceviz commands until this finishes. Continue? [y/N] ").strip().lower() == "y", "Update cancelled; no changes made.")
    installation.area.mkdir(mode=0o700, exist_ok=True)
    require(not installation.area.is_symlink() and installation.area.stat().st_uid == os.getuid(), "Invalid deployment directory owner.")
    import fcntl
    with confined(installation.area, "update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateError("Another Ceviz update is in progress.") from None
        if args.recover:
            require(installation.pending.exists(), "There is no pending update to recover.")
            recover_update(installation)
            return
        require(not installation.pending.exists(), "An interrupted update exists. Run --recover before another update.")
        validate_unmanaged_source(installation)
        installation.idle(installation.snapshot())
        with tempfile.TemporaryDirectory(prefix="ceviz-release-") as temporary:
            source = args.source
            if source is None:
                source = Path(temporary)
                command(["git", "init", "--bare", str(source)])
                require(re.fullmatch(r"[0-9a-f]{40}", args.revision) or re.fullmatch(r"ceviz-helper-v[0-9.]+-beta\.[0-9]+", args.revision), "Invalid release revision.")
                command(["git", "-C", str(source), "fetch", "--depth=1", REPOSITORY, args.revision])
                revision = command(["git", "-C", str(source), "rev-parse", "FETCH_HEAD"], text=True).strip()
            else:
                revision = args.revision
            destination, sha, manifest = release_snapshot(source, revision, installation.area)
            apply_update(installation, destination, sha, manifest)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as failure:
        print("STOPPED: " + (str(failure) if isinstance(failure, UpdateError) else "Update could not complete; no credentials were printed. Check --recover or contact support."), file=sys.stderr)
        raise SystemExit(1) from None
