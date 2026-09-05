"""Real Watch UI taps. Simulated silence does not prove paired-device delivery."""

import argparse
import json
import re
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

from watch_launch_smoke import choose_simulators, simctl

WATCH_ID = "com.mertbasar.cevizwatch.watchkitapp"
FINISH_TEST = "CevizWatchUITests/WatchCaptureUITests/testManualAndAutomaticFinishRetainRecording"
LARGER_TEST = "CevizWatchUITests/WatchCaptureUITests/testLargerTextReadyAndDiscardBothLanguages"


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


class CaptureSimulatorPair:
    """Keep one selected pair warm; app containers remain isolated per scenario."""
    def __init__(self):
        self.current = ()
        self.started = []

    @staticmethod
    def device_states():
        inventory = json.loads(simctl("list", "devices", "--json", capture=True))["devices"]
        return {device["udid"]: device["state"] for devices in inventory.values() for device in devices}

    def use(self, phone, watch):
        selected = (phone["udid"], watch["udid"])
        if selected != self.current:
            previous = self.current
            self.close()
            states = self.device_states()
            if any(states.get(udid) != "Shutdown" for udid in previous):
                raise RuntimeError("Previous pair is not confirmed shut down; refusing a second concurrent pair outside this runner's ownership")
            self.current = selected
        for udid in selected:
            state = self.device_states().get(udid)
            if state is None:
                raise RuntimeError(f"Simulator state is unknown: {udid}")
            if state != "Booted":
                # A timed-out boot may still start the device; retain cleanup ownership.
                if udid not in self.started:
                    self.started.append(udid)
                simctl("boot", udid)
            simctl("bootstatus", udid, "-b")

    def close(self):
        errors = []
        for udid in reversed(self.started.copy()):
            try:
                state = self.device_states().get(udid)
                if state is None:
                    raise RuntimeError(f"Simulator state is unknown: {udid}")
                if state != "Shutdown":
                    subprocess.run(["xcrun", "simctl", "shutdown", udid], check=True, timeout=60)
                    if self.device_states().get(udid) != "Shutdown":
                        raise RuntimeError(f"Simulator shutdown was not confirmed: {udid}")
                self.started.remove(udid)
            except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                errors.append(f"Simulator shutdown failed for {udid}: {error}")
        if errors:
            raise RuntimeError("; ".join(errors))
        self.current = ()


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
    active_pair = CaptureSimulatorPair()
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
