"""Updater ownership, release activation and recovery tests; no real services."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


MODULE = Path(__file__).resolve().parents[1] / "deploy/update.py"
SPEC = importlib.util.spec_from_file_location("ceviz_helper_update_tests", MODULE)
update = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update)

SHA = "1" * 40
CAPABILITIES = ["continuation_v1", "suggestion_approval_v1", "conversations_v1"]
MANIFEST = {"release": "ceviz-helper-v2026.9.12-beta.1", "capabilities": CAPABILITIES}
RUNTIME = b'''import json, os, sys
from pathlib import Path
import companion
if __name__ == "__main__":
    contract = json.loads((Path(__file__).resolve().parents[1] / "contracts/watch-command-request.schema.json").read_text())
    print(json.dumps({"module": companion.GENERATION, "contract": contract["generation"],
                      "entry": str(Path(__file__).resolve()), "cwd": str(Path.cwd()),
                      "arguments": sys.argv[1:], "sentinel": os.environ.get("CEVIZ_TEST_SENTINEL")}))
'''


def runtime_files(generation):
    return {
        "backend/main.py": RUNTIME,
        "backend/companion.py": ("GENERATION = " + repr(generation) + "\n").encode(),
        "backend/session_api.py": b"# Minimal import-only runtime fixture.\n",
        "contracts/watch-command-request.schema.json": json.dumps({"generation": generation}).encode(),
        "contracts/retained-contract.json": b'{"retained": true}',
        "deploy/requirements.txt": b"# Existing dependencies are unchanged.\n",
        "deploy/helper-release.json": json.dumps(MANIFEST).encode(),
    }


def archive_bytes(files, extra=()):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w") as stream:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            stream.addfile(item, io.BytesIO(data))
        for item, data in extra:
            stream.addfile(item, io.BytesIO(data) if data is not None else None)
    return result.getvalue()


class HelperUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ceviz-helper-unit-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.root = self.directory / "installation"
        self.root.mkdir()
        self.addCleanup(self.make_writable)

    def make_writable(self):
        # Only the test-owned directory: snapshot permissions intentionally deny writes.
        for path in [self.directory, *self.directory.rglob("*")]:
            if not path.is_symlink():
                path.chmod(0o700 if path.is_dir() else 0o600)

    def write_files(self, files, root=None):
        root = self.root if root is None else root
        for name, data in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def snapshot_release(self, files=None, extra=(), revision=SHA):
        data = archive_bytes(runtime_files("new") if files is None else files, extra)
        with patch.object(update, "command", side_effect=[revision + "\n", data]):
            return update.release_snapshot(self.directory / "source", revision, self.root / ".ceviz-updates")

    def installation(self):
        # Exercise the filesystem/recovery owner without addressing a real unit.
        instance = object.__new__(update.Installation)
        instance.root = self.root
        instance.entry = self.root / "backend/main.py"
        instance.area = self.root / ".ceviz-updates"
        instance.area.mkdir(exist_ok=True)
        instance.pending = instance.area / "pending.json"
        instance.installed = instance.area / "installed.json"
        instance.config_hash = update.digest(b"fixture service")
        return instance

    @contextlib.contextmanager
    def service_fixture(self):
        """Real Git/files/SQLite/Python exec, with only the systemd and HTTP peers replaced."""
        self.write_files(runtime_files("old"))
        self.init_git()
        instance = self.installation()
        python = self.root / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        state = self.directory / "state"
        state.mkdir()
        (state / "jobs.json").write_text('{"jobs": []}')
        (state / "push-registration.json").write_text('{"fixture": "keep registration"}')
        with contextlib.closing(sqlite3.connect(state / "conversations.sqlite")) as database, database:
            database.execute("CREATE TABLE conversation_submissions (request_id TEXT PRIMARY KEY, terminal_status TEXT)")
            database.execute("INSERT INTO conversation_submissions VALUES ('existing-id', 'completed')")
        (self.root / ".auth-token").write_text("fixture-pairing-token")
        environment = {**os.environ, "HOME": str(self.directory), "WATCH_CEVIZ_STATE_DIR": str(state),
                       "WATCH_CEVIZ_AUTH_TOKEN": "fixture-pairing-token", "CEVIZ_TEST_SENTINEL": "keep me",
                       "PYTHONDONTWRITEBYTECODE": "1"}
        service = {"active": True, "entry": str(instance.entry), "started": "1", "events": [], "runs": []}
        original_command = update.command

        def properties(name):
            return {"MainPID": "123" if service["active"] else "0",
                    "ActiveState": "active" if service["active"] else "inactive"}[name]

        def process(pid):
            self.assertEqual(pid, 123)
            return [str(python), service["entry"], "8080"], environment.copy(), service["started"]

        def commands(arguments, **kwargs):
            if arguments[:2] != ["systemctl", "--user"]:
                return original_command(arguments, **kwargs)
            self.assertEqual(arguments[3], update.SERVICE)
            action = arguments[2]
            if action == "cat":
                return b"fixture service"
            self.assertIn(action, {"start", "stop"})
            service["events"].append(action)
            service["active"] = action == "start"
            if action == "start":
                result = subprocess.run([str(python), str(instance.entry), "8080"], env=environment,
                                        cwd=self.root, capture_output=True, text=True, check=True, timeout=10)
                output = json.loads(result.stdout)
                self.assertEqual(output["module"], output["contract"], "A mixed runtime was activated")
                self.assertEqual(output["cwd"], str(self.root))
                self.assertEqual(output["arguments"], ["8080"])
                self.assertEqual(output["sentinel"], "keep me")
                service["runs"].append(output)
                service["entry"] = output["entry"]
                service["started"] = str(int(service["started"]) + 1)
            return b""

        def api(before, path, token=None):
            if token == "":
                raise HTTPError("http://fixture.invalid", 401, "Unauthorized", {}, io.BytesIO())
            self.assertEqual(before["token"], "fixture-pairing-token")
            if path == "/api/v1/jobs/active":
                return {"jobs": []}
            if path == "/api/v1/capabilities":
                return dict.fromkeys(CAPABILITIES, True)
            if path == "/api/v1/sessions":
                return {"sessions": [], "agents": []}
            self.fail("Unexpected fixture API call: " + path)

        with patch.object(update, "command", side_effect=commands), \
                patch.object(update, "property_value", side_effect=properties), \
                patch.object(update, "process_details", side_effect=process), \
                patch.object(instance, "api", side_effect=api), contextlib.redirect_stdout(io.StringIO()):
            yield instance, state, service

    def init_git(self):
        if not shutil.which("git"):
            self.skipTest("Git is required for the real local-change boundary")
        for arguments in (["init", "-q"], ["add", "backend", "contracts", "deploy/requirements.txt"],
                          ["-c", "user.name=Ceviz Test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", str(self.root), *arguments], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_hostile_archive_paths_and_link_members_refuse_before_snapshot_creation(self):
        cases = []
        for name in ("../outside.py", "/absolute.py", "backend/../../outside.py", "unrelated/private.txt"):
            item = tarfile.TarInfo(name)
            item.size = 1
            cases.append((name, item, b"x"))
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            item = tarfile.TarInfo("backend/linked.py")
            item.type, item.linkname = kind, "../../outside.py"
            cases.append((repr(kind), item, None))
        duplicate = tarfile.TarInfo("backend/main.py")
        duplicate.size = 1
        cases.append(("duplicate", duplicate, b"x"))
        for label, item, data in cases:
            with self.subTest(label=label), self.assertRaises(update.UpdateError):
                self.snapshot_release(extra=[(item, data)])
            self.assertFalse((self.root / ".ceviz-updates/releases").exists())
        self.assertFalse((self.directory / "outside.py").exists())

    def test_snapshot_rejects_incomplete_runtime_or_changed_capability_contract(self):
        missing = runtime_files("new")
        missing.pop("backend/main.py")
        wrong = runtime_files("new")
        wrong["deploy/helper-release.json"] = json.dumps({**MANIFEST, "capabilities": []}).encode()
        for files in (missing, wrong):
            with self.subTest(files=list(files)), self.assertRaises(update.UpdateError):
                self.snapshot_release(files)
        self.assertFalse((self.root / ".ceviz-updates/releases").exists())

    def test_confined_path_rejects_symlinked_parent_without_changing_target(self):
        outside = self.directory / "outside"
        outside.mkdir()
        try:
            (self.root / "backend").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("This host does not permit test symlinks")
        with self.assertRaises(update.UpdateError):
            update.confined(self.root, "backend/main.py")
        self.assertEqual(list(outside.iterdir()), [])

    def test_idle_journal_is_read_only_and_null_identity_blocks_without_repair(self):
        state = self.directory / "state"
        state.mkdir()
        update.journal_idle(state)
        self.assertEqual(list(state.iterdir()), [])
        path = state / "conversations.sqlite"
        with contextlib.closing(sqlite3.connect(path)) as database, database:
            database.execute("CREATE TABLE conversation_submissions (request_id TEXT PRIMARY KEY, terminal_status TEXT)")
            database.execute("INSERT INTO conversation_submissions VALUES ('completed-id', 'completed')")
        original = path.read_bytes()
        update.journal_idle(state)
        self.assertEqual(path.read_bytes(), original)
        with contextlib.closing(sqlite3.connect(path)) as database, database:
            database.execute("INSERT INTO conversation_submissions VALUES ('unconfirmed-id', NULL)")
        original = path.read_bytes()
        with self.assertRaisesRegex(update.UpdateError, "unconfirmed"):
            update.journal_idle(state)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual({p.name for p in state.iterdir()}, {"conversations.sqlite"})

    def test_corrupt_journal_is_not_deleted_or_recreated(self):
        path = self.directory / "conversations.sqlite"
        path.write_bytes(b"not a sqlite database")
        with self.assertRaisesRegex(update.UpdateError, "could not be checked"):
            update.journal_idle(self.directory)
        self.assertEqual(path.read_bytes(), b"not a sqlite database")

    def test_busy_and_unknown_jobs_refuse_and_empty_history_is_valid(self):
        for status in ("queued", "processing", "running", "unconfirmed", "unexpected", None):
            rows = [{"id": "existing", "status": status}]
            original = json.dumps(rows)
            with self.subTest(status=status), self.assertRaises(update.UpdateError):
                update.lifecycle(rows)
            self.assertEqual(json.dumps(rows), original)
        self.assertEqual(update.lifecycle([]), [])
        self.assertEqual(update.lifecycle([{"id": "done", "status": "completed"}]), [("done", "completed")])

    def test_unsupported_platform_and_unknown_service_refuse_before_mutation(self):
        with patch.object(update.sys, "platform", "darwin"), patch.object(update, "command") as commands:
            with self.assertRaisesRegex(update.UpdateError, "Linux/WSL"):
                update.Installation(self.root)
            commands.assert_not_called()
        for properties in ({"LoadState": "not-found"}, {"LoadState": "loaded", "Transient": "yes"},
                           {"LoadState": "loaded", "Transient": "no", "WorkingDirectory": str(self.directory / "other")}):
            with self.subTest(properties=properties), patch.object(update.sys, "platform", "linux"), \
                    patch.object(update, "property_value", side_effect=properties.__getitem__), \
                    patch.object(update, "command") as commands:
                with self.assertRaises(update.UpdateError):
                    update.Installation(self.root)
                commands.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_foreign_process_owner_is_rejected_before_reading_command_or_environment(self):
        class ForeignProcess:
            st_uid = 456
        with patch.object(update.os, "getuid", return_value=123, create=True), \
                patch.object(update.Path, "stat", return_value=ForeignProcess()), \
                patch.object(update.Path, "read_bytes") as contents:
            with self.assertRaisesRegex(update.UpdateError, "not owned"):
                update.process_details(1234)
            contents.assert_not_called()

    def test_real_git_modified_and_untracked_runtime_files_are_never_overwritten(self):
        self.write_files(runtime_files("old"))
        self.init_git()
        instance = self.installation()
        update.validate_unmanaged_source(instance)
        original = instance.entry.read_bytes()
        instance.entry.write_bytes(original + b"# Local customization.\n")
        customized = instance.entry.read_bytes()
        with self.assertRaisesRegex(update.UpdateError, "Local backend changes"):
            update.validate_unmanaged_source(instance)
        self.assertEqual(instance.entry.read_bytes(), customized)
        instance.entry.write_bytes(original)
        extra = self.root / "backend/local_plugin.py"
        extra.write_bytes(b"# User-owned module.\n")
        with self.assertRaisesRegex(update.UpdateError, "Local backend changes"):
            update.validate_unmanaged_source(instance)
        self.assertEqual(extra.read_bytes(), b"# User-owned module.\n")
        self.assertFalse(instance.pending.exists())

    def test_environment_comparison_preserves_config_but_ignores_new_service_invocation(self):
        original = {"HOME": "/home/test", "PATH": "/bin", "LD_LIBRARY_PATH": "/cuda",
                    "OPENAI_BASE_URL": "https://fixture.invalid", "TMPDIR": "/private/tmp",
                    "WATCH_CEVIZ_AUTH_TOKEN": "fixture-only", "INVOCATION_ID": "old"}
        self.assertEqual(update.environment_hash(original),
                         update.environment_hash({**original, "INVOCATION_ID": "new"}))
        for name in ("HOME", "PATH", "LD_LIBRARY_PATH", "OPENAI_BASE_URL", "TMPDIR", "WATCH_CEVIZ_AUTH_TOKEN"):
            with self.subTest(name=name):
                self.assertNotEqual(update.environment_hash(original),
                                    update.environment_hash({**original, name: "changed"}))

    @unittest.skipUnless(os.name == "posix", "Virtual-environment executable identity is tested on Linux")
    def test_foreign_virtual_environment_is_rejected_even_when_python_binary_is_the_same(self):
        with self.service_fixture() as (instance, _state, service):
            original = instance.snapshot()
            other = self.directory / "other-venv/bin/python"
            other.parent.mkdir(parents=True)
            other.symlink_to(sys.executable)
            self.assertEqual(other.resolve(), (self.root / ".venv/bin/python").resolve())
            foreign = ([str(other), str(instance.entry), "8080"], original["environment"], original["started"])
            with patch.object(update, "process_details", return_value=foreign), patch.object(instance, "api") as api:
                with self.assertRaises(update.UpdateError):
                    instance.snapshot()
                api.assert_not_called()
            self.assertEqual(service["events"], [])
            self.assertFalse(instance.pending.exists())

    @unittest.skipUnless(os.name == "posix", "Native POSIX fsync/atomic activation is tested on Linux")
    def test_complete_snapshot_keeps_every_runtime_file_and_rejects_later_tampering(self):
        files = runtime_files("new")
        destination, sha, manifest = self.snapshot_release(files)
        self.assertEqual(sha, SHA)
        self.assertEqual(manifest, MANIFEST)
        for name, data in files.items():
            self.assertEqual((destination / name).read_bytes(), data)
        # Reopening the same immutable release must verify, not silently repair.
        changed = destination / "backend/companion.py"
        changed.chmod(0o600)
        changed.write_bytes(b"GENERATION = 'tampered'\n")
        with self.assertRaisesRegex(update.UpdateError, "verification"):
            self.snapshot_release(files)
        self.assertEqual(changed.read_bytes(), b"GENERATION = 'tampered'\n")

    @unittest.skipUnless(os.name == "posix", "Native POSIX fsync/atomic activation is tested on Linux")
    def test_snapshot_extra_runtime_file_is_not_silently_accepted(self):
        destination, _, _ = self.snapshot_release()
        (destination / "backend").chmod(0o700)
        (destination / "backend/unreviewed.py").write_bytes(b"raise RuntimeError('not part of release')\n")
        with self.assertRaisesRegex(update.UpdateError, "file set"):
            self.snapshot_release()

    @unittest.skipUnless(os.name == "posix", "Native POSIX fsync/atomic activation is tested on Linux")
    def test_atomic_file_failure_leaves_whole_old_or_whole_new_bytes_and_no_staging_file(self):
        target = self.root / "launcher.py"
        target.write_bytes(b"old complete entry")
        with patch.object(update.os, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                update.atomic_bytes(target, b"new complete entry")
        self.assertEqual(target.read_bytes(), b"old complete entry")
        self.assertEqual([p.name for p in self.root.iterdir()], ["launcher.py"])
        with patch.object(update, "sync_directory", side_effect=OSError("simulated directory sync failure")):
            with self.assertRaises(OSError):
                update.atomic_bytes(target, b"new complete entry")
        self.assertEqual(target.read_bytes(), b"new complete entry")
        self.assertEqual([p.name for p in self.root.iterdir()], ["launcher.py"])

    @unittest.skipUnless(os.name == "posix", "Native POSIX launcher/recovery is tested on Linux")
    def test_managed_launcher_executes_complete_snapshot_without_changing_existing_siblings_or_state(self):
        with self.service_fixture() as (instance, state, service):
            destination, sha, manifest = self.snapshot_release()
            originals = {name: (self.root / name).read_bytes() for name in runtime_files("old") if name != "backend/main.py"}
            original_state = update.state_hashes(state)
            update.apply_update(instance, destination, sha, manifest)
            self.assertEqual(service["events"], ["stop", "start"])
            self.assertEqual(service["runs"][-1]["module"], "new")
            self.assertEqual(service["runs"][-1]["entry"], str(destination / "backend/main.py"))
            self.assertTrue(instance.entry.read_bytes().startswith(update.LAUNCHER_HEADER))
            self.assertFalse(instance.pending.exists())
            self.assertTrue(instance.installed.exists())
            for name, original in originals.items():
                self.assertEqual((self.root / name).read_bytes(), original)
            self.assertEqual(update.state_hashes(state), original_state)
            self.assertEqual((self.root / ".auth-token").read_text(), "fixture-pairing-token")
            for receipt in instance.area.glob("*.json"):
                self.assertNotIn(b"fixture-pairing-token", receipt.read_bytes())
                self.assertNotIn(b"keep registration", receipt.read_bytes())
            update.apply_update(instance, destination, sha, manifest)
            self.assertEqual(service["events"], ["stop", "start"], "Already-current updates must not restart")

    @unittest.skipUnless(os.name == "posix", "Native POSIX launcher/recovery is tested on Linux")
    def test_busy_or_unconfirmed_delivery_prevents_launcher_switch_and_service_stop(self):
        with self.service_fixture() as (instance, state, service):
            destination, sha, manifest = self.snapshot_release()
            original = instance.entry.read_bytes()
            with patch.object(instance, "api", return_value={"jobs": [{"id": "busy", "status": "running"}]}):
                with self.assertRaisesRegex(update.UpdateError, "active or unconfirmed"):
                    update.apply_update(instance, destination, sha, manifest)
            with contextlib.closing(sqlite3.connect(state / "conversations.sqlite")) as database, database:
                database.execute("INSERT INTO conversation_submissions VALUES ('unknown-id', NULL)")
            original_state = update.state_hashes(state)
            with self.assertRaisesRegex(update.UpdateError, "unconfirmed"):
                update.apply_update(instance, destination, sha, manifest)
            self.assertEqual(instance.entry.read_bytes(), original)
            self.assertEqual(service["events"], [])
            self.assertFalse(instance.pending.exists())
            self.assertEqual(update.state_hashes(state), original_state)

    @unittest.skipUnless(os.name == "posix", "Native POSIX launcher/recovery is tested on Linux")
    def test_failed_verification_restores_only_code_and_keeps_runtime_state_bytes(self):
        with self.service_fixture() as (instance, state, service):
            destination, sha, manifest = self.snapshot_release()
            original, original_state = instance.entry.read_bytes(), update.state_hashes(state)
            original_verify = instance.verify_started

            def verify(receipt, expected, capabilities=()):
                if expected == str(destination / "backend/main.py"):
                    raise update.UpdateError("Injected candidate health failure")
                return original_verify(receipt, expected, capabilities)

            with patch.object(instance, "verify_started", side_effect=verify):
                with self.assertRaisesRegex(update.UpdateError, "Injected candidate"):
                    update.apply_update(instance, destination, sha, manifest)
            self.assertEqual(instance.entry.read_bytes(), original)
            self.assertEqual(service["runs"][-1]["module"], "old")
            self.assertEqual(update.state_hashes(state), original_state)
            self.assertFalse(instance.pending.exists())
            self.assertFalse(instance.installed.exists())

    @unittest.skipUnless(os.name == "posix", "Native POSIX launcher/recovery is tested on Linux")
    def test_recovery_refuses_changed_runtime_state_instead_of_restoring_a_stale_backup(self):
        with self.service_fixture() as (instance, state, service):
            destination, sha, manifest = self.snapshot_release()
            new_state = b'{"jobs": [{"id": "arrived-after-check", "status": "running"}]}'

            def fail_after_state_change(*_args, **_kwargs):
                (state / "jobs.json").write_bytes(new_state)
                raise update.UpdateError("Injected post-activation state race")

            with patch.object(instance, "verify_started", side_effect=fail_after_state_change):
                with self.assertRaisesRegex(update.UpdateError, "state race"):
                    update.apply_update(instance, destination, sha, manifest)
            self.assertEqual((state / "jobs.json").read_bytes(), new_state)
            self.assertTrue(instance.pending.exists())
            self.assertTrue(instance.entry.read_bytes().startswith(update.LAUNCHER_HEADER))
            self.assertEqual(service["events"], ["stop"], "Recovery must refuse before another lifecycle mutation")

    @unittest.skipUnless(os.name == "posix", "Native POSIX launcher/recovery is tested on Linux")
    def test_second_managed_update_recovers_after_installed_receipt_write_before_archive(self):
        with self.service_fixture() as (instance, state, service):
            first, sha, manifest = self.snapshot_release()
            update.apply_update(instance, first, sha, manifest)
            old_launcher = instance.entry.read_bytes()
            old_receipt = instance.installed.read_bytes()
            original_state = update.state_hashes(state)
            second, second_sha, manifest = self.snapshot_release(runtime_files("next"), revision="2" * 40)
            original_rename = Path.rename
            interrupted = []

            def rename(path, target):
                if path == instance.pending and Path(target).name.startswith("completed-") and not interrupted:
                    interrupted.append(True)
                    self.assertEqual(json.loads(instance.installed.read_text())["new_entry"], str(second / "backend/main.py"))
                    raise OSError("Injected interruption after installed receipt commit")
                return original_rename(path, target)

            with patch.object(Path, "rename", new=rename):
                with self.assertRaisesRegex(OSError, "installed receipt"):
                    update.apply_update(instance, second, second_sha, manifest)
            self.assertTrue(interrupted)
            self.assertEqual(instance.entry.read_bytes(), old_launcher)
            self.assertEqual(instance.installed.read_bytes(), old_receipt)
            self.assertFalse(instance.pending.exists())
            self.assertEqual(service["runs"][-1]["module"], "new")
            self.assertEqual(update.state_hashes(state), original_state)
            update.validate_unmanaged_source(instance)

    @unittest.skipUnless(os.name == "posix", "Native managed snapshots are tested on Linux")
    def test_installed_snapshot_tamper_is_rejected_before_any_new_update(self):
        with self.service_fixture() as (instance, state, service):
            destination, sha, manifest = self.snapshot_release()
            update.apply_update(instance, destination, sha, manifest)
            original_state = update.state_hashes(state)
            changed = destination / "backend/companion.py"
            changed.chmod(0o600)
            changed.write_bytes(b"GENERATION = 'user-modified-runtime'\n")
            events = service["events"].copy()
            with self.assertRaises(update.UpdateError):
                update.validate_unmanaged_source(instance)
            self.assertEqual(service["events"], events)
            self.assertEqual(update.state_hashes(state), original_state)
            self.assertEqual(changed.read_bytes(), b"GENERATION = 'user-modified-runtime'\n")

    @unittest.skipUnless(os.name == "posix", "Native managed snapshots are tested on Linux")
    def test_receipt_cannot_name_a_lexically_nested_entry_outside_its_release(self):
        with self.service_fixture() as (instance, _state, service):
            destination, sha, manifest = self.snapshot_release()
            update.apply_update(instance, destination, sha, manifest)
            receipt = json.loads(instance.installed.read_text())
            receipt["new_entry"] = str(destination / ".." / ".." / "outside" / "backend/main.py")
            instance.installed.write_text(json.dumps(receipt))
            events = service["events"].copy()
            with self.assertRaises(update.UpdateError):
                instance.read_receipt(instance.installed)
            self.assertEqual(service["events"], events)

    @unittest.skipUnless(os.name == "posix", "Native managed snapshots are tested on Linux")
    def test_recovery_will_not_execute_a_previous_snapshot_changed_after_activation(self):
        with self.service_fixture() as (instance, state, service):
            first, sha, manifest = self.snapshot_release()
            update.apply_update(instance, first, sha, manifest)
            second, second_sha, manifest = self.snapshot_release(runtime_files("next"), revision="2" * 40)
            original_state = update.state_hashes(state)
            original_verify = instance.verify_started

            def verify(receipt, expected, capabilities=()):
                if expected == str(second / "backend/main.py"):
                    for name, content in {
                        "backend/companion.py": b"GENERATION = 'unreviewed-rollback'\n",
                        "contracts/watch-command-request.schema.json": b'{"generation": "unreviewed-rollback"}',
                    }.items():
                        target = first / name
                        target.chmod(0o600)
                        target.write_bytes(content)
                    raise update.UpdateError("Injected activation failure after old snapshot changed")
                return original_verify(receipt, expected, capabilities)

            with patch.object(instance, "verify_started", side_effect=verify):
                with self.assertRaisesRegex(update.UpdateError, "old snapshot changed"):
                    update.apply_update(instance, second, second_sha, manifest)
            self.assertTrue(instance.pending.exists(), "Tampered rollback code must remain a visible recovery blocker")
            self.assertEqual(service["events"], ["stop", "start", "stop"], "Recovery must refuse before further lifecycle changes")
            self.assertEqual([run["module"] for run in service["runs"]], ["new"])
            self.assertEqual(update.state_hashes(state), original_state)


if __name__ == "__main__":
    unittest.main()
