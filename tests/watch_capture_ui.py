"""Real Watch UI taps. Simulated silence does not prove paired-device delivery."""

import argparse
import json
import re
import subprocess
from pathlib import Path

from watch_launch_smoke import choose_simulators, simctl

WATCH_ID = "com.mertbasar.cevizwatch.watchkitapp"
FINISH_TEST = "CevizWatchUITests/WatchCaptureUITests/testManualAndAutomaticFinishRetainRecording"


def capture_runs(baseline):
    if baseline:
        return [(40, "large", "baseline")]
    return [(screen, size, "short") for screen in (40, 49)
            for size in ("large", "extra-extra-extra-large")] + [(40, "large", "finish")]


def select_watch(inventory, pairs, sdk_versions, screen):
    filtered = {runtime: [device for device in devices
                         if "watchOS" not in runtime or f"({screen}mm)" in device["name"]]
                for runtime, devices in inventory.items()}
    return choose_simulators(filtered, pairs, sdk_versions)


def test_selection(mode):
    if mode == "baseline":
        return ["-only-testing:CevizWatchUITests/WatchCaptureUITests/testReadyScreenEnglish"]
    if mode == "finish":
        return [f"-only-testing:{FINISH_TEST}"]
    if mode == "short":
        return [f"-skip-testing:{FINISH_TEST}"]
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


def capture_file_metrics(log):
    rows = re.findall(r"Capture finalized: duration_seconds=([0-9.]+) bytes=(\d+) codec=(\d+) sample_rate=([0-9.]+) channels=(\d+)", log)
    return [{"duration_seconds": float(duration), "bytes": int(size), "codec": int(codec),
             "sample_rate": float(rate), "channels": int(channels)} for duration, size, codec, rate, channels in rows]


def require_capture_durations(metrics):
    if len(metrics) < 2:
        raise RuntimeError("Actual file metadata missing for manual and automatic captures")
    # UI polling/tap latency permits a small margin around six seconds remaining.
    for metric, bounds in zip(metrics[-2:], [(8.0, 12.0), (14.5, 16.0)]):
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
    try:
        for screen, size, mode in capture_runs(baseline):
            # Re-read pair ownership: a previous run may have safely created a pair.
            inventory = json.loads(simctl("list", "devices", "available", "--json", capture=True))["devices"]
            pairs = list(json.loads(simctl("list", "pairs", "--json", capture=True))["pairs"].values())
            choice = select_watch(inventory, pairs, context["sdk_versions"], screen)
            watch, phone = choice["watch"], choice["phone"]
            started = []
            name = re.sub(r"[^a-zA-Z0-9-]", "-", watch["name"]) + "-" + size + "-" + mode
            result = output / (name + ".xcresult")
            log_path = output / (name + ".log")
            record = {"device": watch, "runtime": choice["watch_runtime"], "content_size": size,
                      "mode": mode, "result": str(result), "status": "preparing"}
            evidence.append(record)
            if choice["needs_pair"]:
                simctl("pair", watch["udid"], phone["udid"])
            try:
                for device in (phone, watch):
                    state = json.loads(simctl("list", "devices", "--json", capture=True))["devices"]
                    booted = any(item["udid"] == device["udid"] and item["state"] == "Booted"
                                 for devices in state.values() for item in devices)
                    if not booted:
                        simctl("boot", device["udid"])
                        started.append(device["udid"])
                    simctl("bootstatus", device["udid"], "-b")
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
                simctl("ui", watch["udid"], "content_size", size)
                record["observed_content_size"] = simctl("ui", watch["udid"], "content_size", capture=True).strip()
                record["status"] = "running"
                command = ["xcodebuild", "test-without-building", *common, "-resultBundlePath", str(result), *test_selection(mode)]
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
            except Exception as error:
                record.update(status="failed", failure=f"{type(error).__name__}: {error}")
                raise
            finally:
                metadata_error = None
                if mode == "finish":
                    try:
                        capture_log = subprocess.run([
                            "xcrun", "simctl", "spawn", watch["udid"], "log", "show", "--last", "10m", "--info",
                            "--style", "compact", "--predicate",
                            'subsystem == "com.mertbasar.ceviz.watch" AND category == "AudioCapture"',
                        ], text=True, capture_output=True, timeout=60, check=False)
                        (output / (name + "-audio-capture.log")).write_text(
                            capture_log.stdout + capture_log.stderr, encoding="utf-8")
                        record["audio_capture_log_exit_code"] = capture_log.returncode
                        record["capture_file_metrics"] = capture_file_metrics(capture_log.stdout)
                        if record["status"] == "passed":
                            try:
                                require_capture_durations(record["capture_file_metrics"])
                            except RuntimeError as error:
                                record.update(status="failed", failure=str(error))
                                metadata_error = error
                    except subprocess.TimeoutExpired:
                        record["audio_capture_log_error"] = "Diagnostic log read timed out; file metadata proof unavailable"
                        if record["status"] == "passed":
                            record["status"] = "failed"
                            metadata_error = RuntimeError(record["audio_capture_log_error"])
                for udid in reversed(started):
                    try:
                        subprocess.run(["xcrun", "simctl", "shutdown", udid], check=False, timeout=60)
                    except subprocess.TimeoutExpired:
                        record.setdefault("cleanup_errors", []).append(f"Simulator shutdown timed out: {udid}")
                if metadata_error:
                    raise metadata_error
    finally:
        (output / "context.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    main(args.project.resolve(), args.baseline)
