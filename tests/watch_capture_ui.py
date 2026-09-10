"""Real Watch UI taps. Simulated silence does not prove paired-device delivery."""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from pathlib import Path

from watch_launch_smoke import WatchSimulatorPair, choose_simulators, simctl

WATCH_ID = "com.mertbasar.cevizwatch.watchkitapp"
FINISH_TEST = "CevizWatchUITests/WatchCaptureUITests/testManualAndAutomaticFinishRetainRecording"
LARGER_TEST = "CevizWatchUITests/WatchCaptureUITests/testLargerTextReadyAndDiscardBothLanguages"
DIAGNOSTIC_PROCESSES = ("CevizWatchApp", "CevizWatchUITests-Runner", "testmanagerd", "Carousel", "backboardd", "runningboardd")
DIAGNOSTIC_PREDICATE = " OR ".join(f'process == "{process}"' for process in DIAGNOSTIC_PROCESSES)


def capture_failure_diagnostics(result, watch_udid, log_path):
    """Project native diagnostics to fixed event labels; never publish raw messages."""
    summary = {"status": "unavailable", "scope": "120 seconds before failure anchor through 2 seconds after; not exact tap coverage"}
    try:
        if not result.is_dir():
            return {**summary, "reason": "result_bundle_missing"}
        logs = log_path.read_text(errors="replace") if log_path.exists() else ""
        failed_at = re.search(r"Test Suite '[^'\r\n]+' failed at (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\.", logs)
        anchor = datetime.strptime(failed_at[1], "%Y-%m-%d %H:%M:%S.%f") if failed_at else datetime.now()
        summary.update(anchor_source="first_failed_native_suite" if failed_at else "runner_failure_time",
                       start=(anchor - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S"),
                       end=(anchor + timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S"))
        # Keep raw exports outside the workflow's broad **/*.log artifact glob.
        with tempfile.TemporaryDirectory(prefix="ceviz-watch-failure-") as temporary:
            native = Path(temporary) / "native"
            export = subprocess.run(["xcrun", "xcresulttool", "export", "diagnostics", "--path", str(result),
                                     "--output-path", str(native)], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=60, check=False)
            summary["export_exit_code"] = export.returncode
            if export.returncode:
                return {**summary, "reason": "native_export_failed"}
            archives = [path for path in native.rglob("system.logarchive") if path.is_dir()
                        and path.resolve().is_relative_to(native.resolve())
                        and any(re.search(rf"(?<![0-9a-f-]){re.escape(watch_udid)}(?![0-9a-f-])", part, re.I)
                                for part in path.relative_to(native).parts)]
            summary["matching_watch_archives"] = len(archives)
            if len(archives) != 1:
                return {**summary, "reason": "watch_archive_missing_or_ambiguous"}
            with tempfile.TemporaryFile() as output:
                query = subprocess.run(["/usr/bin/log", "show", "--archive", str(archives[0]),
                                        "--start", summary["start"], "--end", summary["end"],
                                        "--style", "compact", "--info", "--debug", "--predicate", DIAGNOSTIC_PREDICATE],
                                       stdout=output, stderr=subprocess.DEVNULL, timeout=45, check=False)
                summary["query_exit_code"] = query.returncode
                if query.returncode:
                    return {**summary, "reason": "native_log_query_failed"}
                output.seek(0)
                payload = output.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024:
                    return {**summary, "reason": "query_output_exceeds_4_mib", "truncated": True}
            rows = payload.decode("utf-8").splitlines()
            summary["read_rows"] = len(rows)
            summary["recognized_rows"] = 0
            events = []
            for row in rows:
                # Envelope observed in retained native Watch compact logs. The
                # message suffix is used only for classification and discarded.
                envelope = re.fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+\w+\s+([A-Za-z0-9-]+)\[(\d+):[0-9a-fA-F]+\]\s+(.*)", row)
                if not envelope or envelope[2] not in DIAGNOSTIC_PROCESSES:
                    continue
                summary["recognized_rows"] += 1
                timestamp, process, pid, message = envelope.groups()
                capture_event = re.search(r"\[com\.mertbasar\.ceviz\.watch:AudioCapture\] Capture event: (view_appeared|scene_changed|primary_action|view_start|view_cancel|native_start)\b", message)
                if capture_event and process == "CevizWatchApp":
                    kind = "app_" + capture_event[1]
                else:
                    kind = next((label for token, label in (
                        ("toucheventscompleted", "native_touch_completion_acknowledgement"),
                        ("synthesiz", "native_event_synthesis_log"),
                        ("mt responded in time", "native_main_thread_response"),
                        ("main run loop", "native_main_run_loop_log"),
                        ("hid", "native_hid_log"), ("scene", "native_scene_log"),
                    ) if token in message.casefold()), None)
                if kind:
                    events.append({"timestamp": timestamp, "process": process, "kind": kind, "pid": int(pid)})
                    if len(events) == 2000:
                        break
            return {**summary, "status": "collected", "events": events, "event_limit_reached": len(events) == 2000}
    except Exception as error:
        # Even diagnostic timeout/schema/disk errors cannot replace the UI failure.
        return {**summary, "error_type": type(error).__name__}


def capture_runs(baseline):
    if baseline:
        return [(40, "device-default", "baseline")]
    return [(40, "device-default", "short"), (40, "larger-settings", "short"),
            (40, "device-default", "finish"), (49, "device-default", "short"),
            (49, "larger-settings", "short")]


def select_watch(inventory, pairs, sdk_versions, screen):
    filtered = {runtime: [device for device in devices
                         if "watchOS" not in runtime or f"({screen}mm)" in device["name"]]
                for runtime, devices in inventory.items()}
    return choose_simulators(filtered, pairs, sdk_versions)


def test_selection(mode, size="device-default"):
    if mode == "baseline":
        return ["-only-testing:CevizWatchUITests/WatchCaptureUITests/testReadyScreenEnglish"]
    if mode == "finish":
        return [f"-only-testing:{FINISH_TEST}"]
    if mode == "short":
        if size == "larger-settings":
            return [f"-only-testing:{LARGER_TEST}"]
        return ["-only-testing:CevizWatchUITests/WatchCaptureUITests/testReadyScreenEnglish",
                "-only-testing:CevizWatchUITests/WatchCaptureUITests/testRecordAndDiscardBothLanguages"]
    raise ValueError(f"Unknown capture test mode: {mode}")


def reinstall_watch(watch_udid, watch_app):
    # Inspect and reset only this test app's simulator container, never a whole device.
    apps = simctl("listapps", watch_udid, capture=True)
    converted = subprocess.run(["plutil", "-convert", "json", "-o", "-", "-"],
                               input=apps, text=True, capture_output=True, check=True)
    if WATCH_ID in json.loads(converted.stdout):
        simctl("uninstall", watch_udid, WATCH_ID)
    simctl("install", watch_udid, str(watch_app))
    simctl("privacy", watch_udid, "grant", "microphone", WATCH_ID)


@contextmanager
def capture_log_stream(watch_udid, log_path):
    # Info messages are memory-only unless collected. Subscribe before the test,
    # and keep only this run's numeric capture category, not historical app logs.
    command = ["xcrun", "simctl", "spawn", watch_udid, "log", "stream", "--level", "info",
               "--style", "compact", "--timeout", "13m", "--predicate",
               'subsystem == "com.mertbasar.ceviz.watch" AND category == "AudioCapture"']
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while "Filtering the log data using" not in log_path.read_text(errors="replace"):
                if process.poll() is not None:
                    raise RuntimeError(f"Capture log stream exited before readiness: {log_path}")
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Capture log stream did not confirm readiness: {log_path}")
                time.sleep(0.1)
            if process.poll() is not None:
                raise RuntimeError(f"Capture log stream exited before the UI test: {log_path}")
            yield process
        finally:
            # Only the owned collector is terminated; never an app or other log session.
            # Its native timeout also bounds the simulator-side process if the host dies.
            had_error = sys.exc_info()[0] is not None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        log.write("Capture log stream cleanup timed out after kill\n")
                        if not had_error:
                            raise


def capture_file_metrics(log):
    metrics = []
    for row in re.findall(r"Capture finalized: ([^\r\n]*)", log):
        match = re.fullmatch(r"duration_seconds=(\d+(?:\.\d+)?) bytes=(\d+) codec=(\d+) sample_rate=(\d+(?:\.\d+)?) channels=(\d+)", row.strip())
        if match:
            duration, size, codec, rate, channels = match.groups()
            metrics.append({"duration_seconds": float(duration), "bytes": int(size), "codec": int(codec),
                            "sample_rate": float(rate), "channels": int(channels)})
        else:
            # Retain every finalization so missing metadata cannot hide behind later
            # valid captures. Validation, not parsing, owns the recorded failure state.
            unavailable = {"file_metadata": "unavailable"}
            if size := re.search(r"\bbytes=(\d+)\b", row):
                unavailable["bytes"] = int(size.group(1))
            metrics.append(unavailable)
    return metrics


def require_capture_durations(metrics):
    if len(metrics) != 2:
        raise RuntimeError(f"Actual file metadata missing or unexpected finalization count: expected exactly 2, found {len(metrics)}")
    if any(metric.get("file_metadata") == "unavailable" for metric in metrics):
        raise RuntimeError("Actual file metadata missing for manual or automatic capture")
    # UI polling/tap latency permits a small margin around six seconds remaining.
    for metric, bounds in zip(metrics, [(8.0, 12.0), (14.5, 16.0)]):
        if not (bounds[0] <= metric["duration_seconds"] <= bounds[1]
                and all(metric[key] > 0 for key in ("bytes", "codec", "sample_rate", "channels"))):
            raise RuntimeError(f"Actual capture file metadata does not match the 9s/15s scenarios: {metric}")


def main(project, baseline=False):
    root = Path.cwd()
    context = json.loads((root / "build/watch-launch-smoke/context.json").read_text())
    output = root / "build/watch-capture-ui" / ("before" if baseline else "after")
    output.mkdir(parents=True, exist_ok=True)
    bridge = root / "build/validation/Build/Products/Release-iphonesimulator/CevizBridge.app"
    derived = output / "derived"
    watch_app = derived / "Build/Products/Release-watchsimulator/CevizWatchApp.app"
    subprocess.run(["xcodegen", "generate", "--spec", "project.watch-ui.yml"], cwd=project, check=True)
    evidence = []
    built = False
    active_pair = WatchSimulatorPair()
    try:
        for screen, size, mode in capture_runs(baseline):
            # Re-read pair ownership: a previous run may have safely created a pair.
            inventory = json.loads(simctl("list", "devices", "available", "--json", capture=True))["devices"]
            pairs = list(json.loads(simctl("list", "pairs", "--json", capture=True))["pairs"].values())
            choice = select_watch(inventory, pairs, context["sdk_versions"], screen)
            watch, phone = choice["watch"], choice["phone"]
            name = re.sub(r"[^a-zA-Z0-9-]", "-", watch["name"]) + "-" + size + "-" + mode
            result = output / (name + ".xcresult")
            log_path = output / (name + ".log")
            audio_log_path = output / (name + "-audio-capture.log")
            capture_stream = None
            record = {"device": watch, "runtime": choice["watch_runtime"], "content_size": size,
                      "mode": mode, "result": str(result), "status": "preparing"}
            evidence.append(record)
            if choice["needs_pair"]:
                simctl("pair", watch["udid"], phone["udid"])
            try:
                active_pair.use(phone, watch)
                simctl("install", phone["udid"], str(bridge))
                common = ["-project", "CevizWatch.xcodeproj", "-scheme", "CevizWatchUI", "-configuration", "Release",
                          "-destination", f"platform=watchOS Simulator,id={watch['udid']}", "-derivedDataPath", str(derived),
                          "-parallel-testing-enabled", "NO", "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-"]
                if not built:
                    with (output / "build-for-testing.log").open("w") as log:
                        subprocess.run(["xcodebuild", "build-for-testing", *common], cwd=project,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=720, check=True)
                    if not watch_app.is_dir():
                        raise RuntimeError(f"The selected project did not produce its Watch test app: {watch_app}")
                    built = True
                reinstall_watch(watch["udid"], watch_app)
                # XCTest operates real Settings and verifies the application's text.
                # The test runner's own category is diagnostic, not live system proof.
                record["content_size_evidence"] = ("Actual Settings value and Ceviz text geometry before/after/restore" if size == "larger-settings"
                                                   else "Normal-device app screenshots; test-runner category diagnostic")
                record["status"] = "running"
                command = ["xcodebuild", "test-without-building", *common, "-resultBundlePath", str(result), *test_selection(mode, size)]
                collector = capture_log_stream(watch["udid"], audio_log_path) if mode == "finish" else nullcontext()
                with collector as capture_stream:
                    with log_path.open("w") as log:
                        process = subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT, timeout=720, check=False)
                    logs = log_path.read_text(errors="replace")
                    print(logs[-7000:], flush=True)
                    record["exit_code"] = process.returncode
                    if result.exists():
                        subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", str(result),
                                        "--output-path", str(output / (name + "-attachments"))], check=True)
                    if baseline:
                        reproduced = process.returncode != 0 and "15-second limit must be fully visible" in logs
                        record["status"] = "regression_reproduced" if reproduced else "regression_not_reproduced"
                        if not reproduced:
                            raise RuntimeError("Previous build did not reproduce the specific ready-screen visibility assertion")
                    else:
                        record["status"] = "passed" if process.returncode == 0 else "failed"
                        if process.returncode:
                            raise RuntimeError(f"Native capture UI tests failed: {log_path}")
                    if capture_stream and capture_stream.poll() is not None:
                        raise RuntimeError(f"Capture log stream ended during the UI test: {audio_log_path}")
            except Exception as error:
                record.update(status="failed", failure=f"{type(error).__name__}: {error}")
                raise
            finally:
                metadata_error = None
                if mode == "finish":
                    record["audio_capture_log_exit_code"] = capture_stream.returncode if capture_stream else None
                    capture_log = audio_log_path.read_text(errors="replace") if audio_log_path.exists() else ""
                    record["capture_file_metrics"] = capture_file_metrics(capture_log)
                    if record["status"] == "passed":
                        try:
                            require_capture_durations(record["capture_file_metrics"])
                        except RuntimeError as error:
                            record.update(status="failed", failure=str(error))
                            metadata_error = error
                if record["status"] == "failed":
                    record["native_failure_diagnostics"] = capture_failure_diagnostics(
                        result, watch["udid"], log_path)
                if metadata_error:
                    raise metadata_error
    finally:
        had_error = sys.exc_info()[0] is not None
        try:
            active_pair.close()
        except RuntimeError as error:
            if evidence:
                evidence[-1].setdefault("cleanup_errors", []).append(str(error))
                evidence[-1]["status"] = "failed"
            if not had_error:
                raise
        finally:
            (output / "context.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    main(args.project.resolve(), args.baseline)
