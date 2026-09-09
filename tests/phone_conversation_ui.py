"""Run the real iPhone conversation UI against an isolated Ceviz/Gateway fixture."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from uuid import UUID

from phone_ui_fixture import TOKEN, PORT


def command(args, *, timeout=120):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout.strip()


def select_phone(inventory, sdk, device_types):
    version = tuple(int(part) for part in sdk.split(".")[:2])
    types = {device["name"]: device["identifier"] for device in device_types}
    for runtime, devices in inventory.items():
        if ".iOS-" not in runtime:
            continue
        runtime_version = tuple(int(part) for part in runtime.split(".iOS-")[1].split("-")[:2])
        if runtime_version != version:
            continue
        phones = [device for device in devices if device.get("isAvailable")
                  and device["name"].startswith("iPhone") and device["name"] in types]
        if phones:
            phone = next((phone for phone in phones if phone["name"] == "iPhone 16"), phones[0])
            return {"template": phone, "runtime": runtime, "device_type": types[phone["name"]]}
    raise RuntimeError("No available iPhone simulator matches the selected Xcode SDK")


def main():
    root = Path.cwd()
    output_root = root / "build/phone-conversation-ui"
    output_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="run-", dir=output_root))
    sdk = command(["xcodebuild", "-version", "-sdk", "iphonesimulator", "SDKVersion"])
    inventory = json.loads(command(["xcrun", "simctl", "list", "devices", "available", "--json"]))["devices"]
    device_types = json.loads(command(["xcrun", "simctl", "list", "devicetypes", "--json"]))["devicetypes"]
    choice = select_phone(inventory, sdk, device_types)
    existing_ids = {UUID(device["udid"]) for devices in inventory.values() for device in devices}
    udid = None
    generated_project = False
    result_path = output / "conversation-tests.xcresult"
    derived = output / "derived"
    with (output / "fixture.log").open("w") as fixture_log:
        # State belongs to the parent: terminating Python does not reliably run
        # the child's finally blocks (in particular on Windows).
        fixture_state = tempfile.TemporaryDirectory(prefix="ceviz-phone-ui-")
        fixture = None
        try:
            fixture = subprocess.Popen([sys.executable, "-B", "tests/phone_ui_fixture.py",
                                        "--state-dir", fixture_state.name],
                                       stdout=fixture_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 15
            ready = Request(f"http://127.0.0.1:{PORT}/__fixture/state",
                            headers={"Authorization": f"Bearer {TOKEN}"})
            while True:
                if fixture.poll() is not None:
                    raise RuntimeError("The isolated phone fixture exited before readiness")
                try:
                    with urlopen(ready, timeout=1) as response:
                        if json.load(response).get("pid") != fixture.pid:
                            raise RuntimeError("Another process owns the phone fixture port")
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("The isolated phone fixture did not become ready")
                time.sleep(0.1)
            # Existing devices provide compatible type/runtime facts only. Never
            # overwrite their apps, pairing, permissions, or current boot state.
            created = command(["xcrun", "simctl", "create", "Ceviz-Conversation-" + output.name,
                               choice["device_type"], choice["runtime"]])
            try:
                identity = UUID(created)
            except ValueError as exc:
                raise RuntimeError("Simulator creation did not return an owned UUID") from exc
            if identity in existing_ids:
                raise RuntimeError("Simulator creation returned an existing device; refusing to modify it")
            udid = created
            (output / "context.json").write_text(json.dumps({**choice, "udid": udid, "sdk": sdk}, indent=2))
            common = ["xcodebuild", "-project", "CevizWatch.xcodeproj", "-scheme", "CevizPhoneUI",
                      "-configuration", "Release", "-destination", f"id={udid}", "-derivedDataPath", str(derived),
                      "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-"]
            command(["xcrun", "simctl", "boot", udid])
            command(["xcrun", "simctl", "bootstatus", udid, "-b"], timeout=180)
            generated_project = True
            command(["xcodegen", "generate", "--spec", "project.phone-ui.yml"])
            with (output / "build.log").open("w") as log:
                subprocess.run(common + ["build-for-testing"], stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=900)
            app = derived / "Build/Products/Release-iphonesimulator/CevizBridge.app"
            command(["xcrun", "simctl", "install", udid, str(app)])
            # This is the same supported pairing link used by people, with a
            # fixture-only credential and localhost URL, not injected app state.
            pairing = f"ceviz://pair?u=http%3A%2F%2F127.0.0.1%3A{PORT}&t={TOKEN}&m=relay"
            command(["xcrun", "simctl", "openurl", udid, pairing], timeout=60)
            with (output / "test.log").open("w") as log:
                subprocess.run(common + ["test-without-building", "-parallel-testing-enabled", "NO",
                                         "-resultBundlePath", str(result_path)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        except Exception:
            # The fixture emits startup phases and a stalled-thread traceback;
            # retain the full artifact and surface its bounded tail in CI logs.
            fixture_log.flush()
            print((output / "fixture.log").read_text(encoding="utf-8", errors="replace")[-8000:], file=sys.stderr)
            raise
        finally:
            had_error = sys.exc_info()[0] is not None
            cleanup_errors = []
            try:
                if fixture is not None and fixture.poll() is None:
                    fixture.terminate()
                    try:
                        fixture.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        fixture.kill()
                        fixture.wait(timeout=10)
            except Exception as exc:
                cleanup_errors.append(exc)
            try:
                fixture_state.cleanup()
            except Exception as exc:
                cleanup_errors.append(exc)
            cleanup_commands = []
            if result_path.exists():
                cleanup_commands.append(["xcrun", "xcresulttool", "export", "attachments", "--path", str(result_path),
                                         "--output-path", str(output / "attachments")])
            if generated_project:
                cleanup_commands.append(["xcodegen", "generate"])
            if udid:
                cleanup_commands.append(["xcrun", "simctl", "shutdown", udid])
                cleanup_commands.append(["xcrun", "simctl", "delete", udid])
            for cleanup in cleanup_commands:
                try:
                    command(cleanup)
                except Exception as exc:
                    cleanup_errors.append(exc)
            if cleanup_errors:
                for exc in cleanup_errors:
                    print(f"Phone UI cleanup failed: {exc}", file=sys.stderr)
                if not had_error:
                    raise cleanup_errors[0]


if __name__ == "__main__":
    main()
