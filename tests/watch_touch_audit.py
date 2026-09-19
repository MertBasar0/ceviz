"""Read two fixed windows from one retained failure; never launch an app or test.

Raw log text stays in temporary files. Only closed-schema event classifications
leave the process. This audit cannot change the failed release gate's result.
"""

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import urllib.request


REPOSITORY = "MertBasar0/ceviz"
RUN_ID = 35461915830
ARTIFACT_ID = 10590107782
ARTIFACT_NAME = "ceviz-watch-ui-failure-results"
ARTIFACT_SIZE = 59549981
SOURCE_SHA = "4b9dd16f018751c6e0d3bc490353ece4a1ccf951"
BRANCH = "codex/phone-conversations"
WATCH_UDID = "16265CCF-DA78-4BF8-AF5F-8E9D91FFDFE8"
APP_PID = 48882
BUNDLE_NAME = "Apple-Watch-SE-3--40mm--device-default-finish.xcresult"
INPUT_ROOT = Path("build/watch-touch-audit-input")
OUTPUT_ROOT = Path("build/watch-touch-audit")
MAX_QUERY_BYTES = 4 * 1024 * 1024
MAX_API_BYTES = 1024 * 1024
MAX_EVENTS = 2000
WINDOWS = (
    ("first_start_succeeded", "2026-09-19 19:03:16", "2026-09-19 19:03:24"),
    ("second_start_failed", "2026-09-19 19:04:40", "2026-09-19 19:04:48"),
)
PROCESSES = ("CevizWatchApp", "CevizWatchUITests-Runner", "testmanagerd", "Carousel", "backboardd", "runningboardd")
PREDICATE = " OR ".join(
    [f'(process == "CevizWatchApp" AND processIdentifier == {APP_PID})']
    + [f'process == "{name}"' for name in PROCESSES[1:]]
)
ENVELOPE = re.compile(
    r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+\w+\s+"
    r"([A-Za-z0-9-]+)\[(\d+):[0-9a-fA-F]+\]\s+(.*)"
)
APP_EVENT = re.compile(
    r"\[com\.mertbasar\.ceviz\.watch:AudioCapture\] Capture event: "
    r"(view_appeared|scene_changed|primary_action|view_start|view_cancel|recorder_start|permission|native_start|native_finish)\b"
)
# These are log classifications, not assertions that input reached the app.
NATIVE_RULES = (
    ("testmanagerd", "native_event_synthesis_log", r"^Synthesizing event with\b"),
    ("testmanagerd", "native_completion_registration", r"^Registering for user testing event TouchEventsCompleted$"),
    ("testmanagerd", "native_completion_wait", r"^Waiting up to [0-9]+(?:\.[0-9]+)?s for TouchEventsCompleted\b"),
    ("testmanagerd", "native_touch_completion_acknowledgement", r"^Got user testing notification with\b(?=[\s\S]*\bevent\s*=\s*TouchEventsCompleted\s*;)"),
    ("testmanagerd", "native_completion_handler", r"^Calling handler for\b(?=[\s\S]*\bevent\s*=\s*TouchEventsCompleted\s*;)"),
    ("testmanagerd", "native_digitizer_service_canceled", r"^service canceled:(?=[\s\S]*\bdigitizer\b)"),
    ("testmanagerd", "native_generator_touch_down", r"^touch down \{"),
    ("testmanagerd", "native_generator_touch_up", r"^touch up \{"),
    ("backboardd", "native_digitizer_disappeared", r"^cancel -- digitizer did disappear:"),
    ("backboardd", "native_contacts_cancel_requested", r"^canceling\b[^\r\n]*\bcontacts:(?=[^\r\n]*-- HID)"),
    (None, "native_main_thread_response", r"\bmt responded in time\b"),
    (None, "native_main_run_loop_log", r"\bmain run loop\b"),
    (None, "native_hid_mention", r"\b(?:hid|iohidevent\w*)\b"),
    (None, "native_scene_mention", r"\bscene\w*\b"),
)
COMPILED_RULES = tuple((owner, name, re.compile(pattern, re.I)) for owner, name, pattern in NATIVE_RULES)
FRAMEWORK_SYMBOLS = ("UITouch", "UIEvent", "XCSynthesizedEventRecord", "XCEventGenerator", "XCTRunnerDaemonSession", "IOHIDEvent")


class AuditFailure(RuntimeError):
    """All callers supply a fixed reason, never a native exception message."""


def provenance_record():
    return {"repository": REPOSITORY, "run_id": RUN_ID, "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME, "artifact_size_bytes": ARTIFACT_SIZE,
            "source_sha": SOURCE_SHA, "source_conclusion": "failure"}


def verify_metadata(run, artifact):
    expected_run = {"id": RUN_ID, "head_sha": SOURCE_SHA, "head_branch": BRANCH,
                    "status": "completed", "conclusion": "failure", "event": "workflow_dispatch"}
    expected_artifact = {"id": ARTIFACT_ID, "name": ARTIFACT_NAME,
                         "size_in_bytes": ARTIFACT_SIZE, "expired": False}
    if not isinstance(run, dict) or any(run.get(key) != value for key, value in expected_run.items()):
        raise AuditFailure("source_run_mismatch")
    if run.get("repository", {}).get("full_name") != REPOSITORY:
        raise AuditFailure("source_repository_mismatch")
    if not isinstance(artifact, dict) or any(artifact.get(key) != value for key, value in expected_artifact.items()):
        raise AuditFailure("source_artifact_mismatch")
    owner = artifact.get("workflow_run", {})
    if owner.get("id") != RUN_ID or owner.get("head_sha") != SOURCE_SHA or owner.get("head_branch") != BRANCH:
        raise AuditFailure("artifact_owner_mismatch")
    return provenance_record()


def github_json(endpoint, token):
    if endpoint not in {f"actions/runs/{RUN_ID}", f"actions/artifacts/{ARTIFACT_ID}"}:
        raise AuditFailure("unapproved_metadata_endpoint")
    request = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/{endpoint}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ceviz-retained-watch-audit",
    })
    # Only metadata endpoints are used; never follow an artifact's signed URL here.
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            payload = response.read(MAX_API_BYTES + 1)
        if len(payload) > MAX_API_BYTES:
            raise AuditFailure("metadata_exceeds_bound")
        return json.loads(payload)
    except AuditFailure:
        raise
    except Exception:
        raise AuditFailure("metadata_read_failed") from None


def verify_remote():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise AuditFailure("metadata_token_missing")
    return verify_metadata(github_json(f"actions/runs/{RUN_ID}", token),
                           github_json(f"actions/artifacts/{ARTIFACT_ID}", token))


def plain_path(path, root):
    root = root.absolute()
    path = path.absolute()
    if not path.is_relative_to(root):
        raise AuditFailure("path_outside_owner")
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            attributes = part.lstat()
            if stat.S_ISLNK(attributes.st_mode) or getattr(attributes, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise AuditFailure("symlink_or_reparse_path")
        if part == root:
            break
    if not path.resolve().is_relative_to(root.resolve()):
        raise AuditFailure("resolved_path_outside_owner")
    return path


def select_result(root):
    plain_path(root, root)
    matches = [plain_path(path, root) for path in root.rglob(BUNDLE_NAME)]
    if len(matches) != 1 or not matches[0].is_dir():
        raise AuditFailure("exact_result_missing_or_ambiguous")
    return matches[0]


def select_watch_archive(root):
    plain_path(root, root)
    token = re.compile(rf"(?<![0-9a-f-]){WATCH_UDID}(?![0-9a-f-])", re.I)
    matches = []
    for path in root.rglob("system.logarchive"):
        plain_path(path, root)
        if path.is_dir() and any(token.search(part) for part in path.relative_to(root).parts):
            matches.append(path)
    if len(matches) != 1:
        raise AuditFailure("watch_archive_missing_or_ambiguous")
    return matches[0]


def compact_records(rows):
    """Keep notification/synthesis continuation lines with their native envelope."""
    current = None
    parts = []
    for row in rows:
        envelope = ENVELOPE.fullmatch(row)
        if envelope or re.match(r"^\d{4}-", row):
            if current:
                yield (*current, "\n".join(parts))
            current = envelope.groups()[:3] if envelope else None
            parts = [envelope[4]] if envelope else []
        elif current:
            parts.append(row)
    if current:
        yield (*current, "\n".join(parts))


def project_events(payload, window):
    name, start, end = window
    if window not in WINDOWS:
        raise AuditFailure("unapproved_time_window")
    if len(payload) > MAX_QUERY_BYTES:
        raise AuditFailure("query_output_exceeds_4_mib")
    try:
        rows = payload.decode("utf-8").splitlines()
    except UnicodeError:
        raise AuditFailure("query_encoding_unrecognized") from None
    start_time, end_time = (datetime.strptime(value, "%Y-%m-%d %H:%M:%S") for value in (start, end))
    events = []
    recognized = 0
    counts = Counter()
    for timestamp, process, raw_pid, message in compact_records(rows):
        if process not in PROCESSES or len(raw_pid) > 10:
            continue
        pid = int(raw_pid)
        if pid > 2147483647 or (process == "CevizWatchApp" and pid != APP_PID):
            continue
        try:
            instant = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            continue
        if not start_time <= instant <= end_time:
            continue
        recognized += 1
        kinds = []
        if process == "CevizWatchApp" and (app_event := APP_EVENT.match(message)):
            kinds.append("app_" + app_event[1])
        # Compact output can prefix an eventMessage with its subsystem/category.
        # This prefix is discarded, never emitted or used as a dynamic label.
        body = re.sub(r"^\[[A-Za-z0-9_.-]+(?::[A-Za-z0-9_. -]+)?\]\s*", "", message, count=1)
        kinds.extend(kind for owner, kind, pattern in COMPILED_RULES
                     if (owner is None or owner == process) and pattern.search(body))
        symbols = [symbol for symbol in FRAMEWORK_SYMBOLS if re.search(rf"\b{symbol}\b", message)]
        if not kinds and not symbols:
            continue
        event = {"timestamp_utc": timestamp, "process": process, "pid": pid, "kinds": kinds,
                 "target_app_correlation": "process_identity" if process == "CevizWatchApp" else
                 "not_established"}
        if symbols:
            event["framework_symbols"] = symbols
        if len(events) == MAX_EVENTS:
            raise AuditFailure("event_limit_exceeded")
        events.append(event)
        counts.update(kinds)
    status = "collected" if events else "no_classified_events" if recognized else "no_matching_records"
    return {"status": status, "name": name, "start_utc": start, "end_utc": end, "query_bytes": len(payload),
            "read_rows": len(rows), "recognized_rows": recognized, "event_counts": dict(sorted(counts.items())),
            "events": events, "meaning": "Log classifications only; synthesis is not proof of delivery, and absence is not proof of a cause."}


def query_window(archive, window):
    if window not in WINDOWS:
        raise AuditFailure("unapproved_time_window")
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(["/usr/bin/log", "show", "--archive", str(archive),
                                     "--start", window[1] + "+0000", "--end", window[2] + "+0000", "--timezone", "UTC",
                                     "--style", "compact", "--info", "--debug", "--predicate", PREDICATE],
                                    stdout=output, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                    timeout=45, check=False)
        except subprocess.TimeoutExpired:
            raise AuditFailure("native_query_timed_out") from None
        if result.returncode:
            raise AuditFailure("native_query_failed")
        output.seek(0)
        return project_events(output.read(MAX_QUERY_BYTES + 1), window)


def inspect(root, provenance):
    if provenance != provenance_record():
        raise AuditFailure("verified_provenance_missing_or_changed")
    result = select_result(root)
    with tempfile.TemporaryDirectory(prefix="ceviz-retained-touch-") as temporary:
        native = Path(temporary) / "native"
        try:
            export = subprocess.run(["xcrun", "xcresulttool", "export", "diagnostics", "--path", str(result),
                                     "--output-path", str(native)], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        except subprocess.TimeoutExpired:
            raise AuditFailure("native_export_timed_out") from None
        if export.returncode:
            raise AuditFailure("native_export_failed")
        archive = select_watch_archive(native)
        windows = [query_window(archive, window) for window in WINDOWS]
        status = "collected" if all(window["status"] == "collected" for window in windows) else "unavailable"
        return {"status": status, "provenance": provenance, "watch_udid": WATCH_UDID,
                "app_pid": APP_PID, "original_gate_result": "failure_not_waived",
                "windows": windows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify-provenance", "inspect"))
    args = parser.parse_args()
    filename = "provenance.json" if args.operation == "verify-provenance" else "touch-evidence.json"
    try:
        plain_path(OUTPUT_ROOT / filename, Path.cwd())
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        if args.operation == "verify-provenance":
            evidence = verify_remote()
        else:
            provenance_file = plain_path(OUTPUT_ROOT / "provenance.json", Path.cwd())
            evidence = inspect(INPUT_ROOT, json.loads(provenance_file.read_text(encoding="utf-8")))
        (OUTPUT_ROOT / filename).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        complete = evidence.get("status", "collected") == "collected"
        print(json.dumps({"operation": args.operation, "status": "complete" if complete else "unavailable", "run_id": RUN_ID}))
        return 0 if complete else 1
    except Exception as error:
        # No native output, file path, token, URL, or traceback leaves this boundary.
        reason = str(error) if isinstance(error, AuditFailure) else "audit_failed_without_raw_details"
        evidence = {"status": "unavailable", "reason": reason, "run_id": RUN_ID,
                    "original_gate_result": "failure_not_waived"}
        try:
            plain_path(OUTPUT_ROOT / filename, Path.cwd()).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        print(json.dumps(evidence))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
