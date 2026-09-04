"""Capture the real, unconfigured Watch app. No job fixtures or recording are injected."""

import json
import plistlib
import re
import subprocess
import time
from pathlib import Path


def simctl(*args, capture=False):
    return subprocess.run(
        ["xcrun", "simctl", *args], check=True, text=True, capture_output=capture
    ).stdout


def runtime_version(runtime):
    return tuple(int(part) for part in re.findall(r"\d+", runtime))


def release_version(version):
    """Compare SDK/runtime releases without confusing SDK patch-level differences."""
    parts = runtime_version(version)
    return (parts + (0, 0))[:2]


def choose_simulators(inventory, pairs, sdk_versions):
    devices = {
        device["udid"]: (runtime, device)
        for runtime, entries in inventory.items() for device in entries
        if device.get("isAvailable", True)
    }
    expected = {"watch": ("watchOS", "Apple Watch"), "phone": ("iOS", "iPhone")}

    def eligible(role, udid, exact=False):
        if udid not in devices:
            return False
        runtime, device = devices[udid]
        platform, prefix = expected[role]
        current, sdk = release_version(runtime), release_version(sdk_versions[role])
        return (platform in runtime and device["name"].startswith(prefix)
                and (current == sdk if exact else current <= sdk))

    available_pairs = [
        pair for pair in pairs
        if all(eligible(role, pair.get(role, {}).get("udid")) for role in expected)
    ]
    exact_pairs = [
        pair for pair in available_pairs
        if all(eligible(role, pair[role]["udid"], exact=True) for role in expected)
    ]

    def selected(pair, reason, needs_pair=False):
        return {
            "watch": devices[pair["watch"]["udid"]][1],
            "phone": devices[pair["phone"]["udid"]][1],
            "watch_runtime": devices[pair["watch"]["udid"]][0],
            "phone_runtime": devices[pair["phone"]["udid"]][0],
            "selection_reason": reason,
            "needs_pair": needs_pair,
        }

    def pair_rank(pair):
        watch = devices[pair["watch"]["udid"]][1]
        return (release_version(devices[pair["watch"]["udid"]][0]),
                release_version(devices[pair["phone"]["udid"]][0]),
                watch_size_rank(watch), pair["phone"]["udid"])

    def watch_size_rank(device):
        size = re.search(r"(\d+)mm", device["name"])
        # Smaller real screens expose truncation; only break equivalent-runtime ties.
        return (-(int(size[1]) if size else 999), device["name"], device["udid"])

    if exact_pairs:
        return selected(max(exact_pairs, key=pair_rank), "Existing SDK-matched pair")

    # Do not unpair or replace existing simulator associations. A new pair is only
    # created from free devices matching both selected Xcode SDK release versions.
    paired_ids = {pair.get(role, {}).get("udid") for pair in pairs for role in expected}
    free = {
        role: sorted((device for udid, (_, device) in devices.items()
                      if udid not in paired_ids and eligible(role, udid, exact=True)),
                     key=lambda device: watch_size_rank(device) if role == "watch"
                     else (device["name"], device["udid"]))
        for role in expected
    }
    if all(free.values()):
        pair = {role: free[role][-1] for role in expected}
        return selected(pair, "New pair from available SDK-matched devices", needs_pair=True)
    if available_pairs:
        # The existing association is compatibility evidence; do not invent an
        # older watchOS/iOS version pairing based on similar version numbers.
        return selected(max(available_pairs, key=pair_rank),
                        "Fallback: existing compatible pair not newer than either selected SDK")
    options = sorted({runtime for runtime, _ in devices.values()})
    raise RuntimeError(f"No safe Watch/iPhone pair for SDKs {sdk_versions}; available runtimes: {options}")


def record_command(output, name, command, *, required=False, timeout=60, input_text=None):
    """Preserve exact CLI diagnostics; these run before any CI signing secrets exist."""
    print(f"Diagnostic command: {command}", flush=True)
    try:
        result = subprocess.run(command, input=input_text, capture_output=True,
                                text=True, timeout=timeout, check=False)
        payload = {"command": command, "returncode": result.returncode,
                   "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired as error:
        def as_text(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""
        payload = {"command": command, "timed_out_seconds": timeout,
                   "stdout": as_text(error.stdout), "stderr": as_text(error.stderr)}
        (output / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if required:
            raise
        return None
    (output / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if required:
        result.check_returncode()
    return result


def collect_url_failure_diagnostics(output, watch_udid):
    record_command(output, "simctl-openurl-help", ["xcrun", "simctl", "help", "openurl"])
    record_command(output, "simctl-launch-help", ["xcrun", "simctl", "help", "launch"])
    predicate = ('process == "lsd" OR process CONTAINS[c] "FrontBoard" '
                 'OR process == "Carousel" OR subsystem CONTAINS[c] "FrontBoard" '
                 'OR subsystem CONTAINS[c] "LaunchServices"')
    record_command(output, "watch-url-system-log", [
        "xcrun", "simctl", "spawn", watch_udid, "log", "show", "--last", "3m",
        "--style", "compact", "--predicate", predicate,
    ])


def main():
    output = Path("build/watch-launch-smoke")
    output.mkdir(parents=True, exist_ok=True)
    diagnostics = output / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    context = {
        "scope": "Unconfigured normal app launch and external simulator URL injection; no real job or complication tap tested",
        "cold_launch": {"status": "not_run", "visual_review": "pending"},
        "capture_url": {"status": "not_run", "url": "ceviz-watch://capture", "visual_review": "pending"},
    }
    started = []
    try:
        run_smoke(output, diagnostics, context, started)
    except Exception as error:
        context["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (output / "context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
        for udid in reversed(started):
            subprocess.run(["xcrun", "simctl", "shutdown", udid], check=False, timeout=60)


def run_smoke(output, diagnostics, context, started):
    bridge = Path("build/validation/Build/Products/Release-iphonesimulator/CevizBridge.app")
    watch_id = "com.mertbasar.cevizwatch.watchkitapp"
    watches = [
        app for app in (bridge / "Watch").glob("*.app")
        if plistlib.loads((app / "Info.plist").read_bytes())["CFBundleIdentifier"] == watch_id
    ]
    if len(watches) != 1:
        raise RuntimeError("Expected exactly one embedded Ceviz Watch application")

    # Read the selected Xcode SDKs, not the newest runtime installed on the runner.
    sdk_versions = {}
    for role, sdk in (("watch", "watchsimulator"), ("phone", "iphonesimulator")):
        result = record_command(diagnostics, f"{sdk}-sdk", [
            "xcrun", "--sdk", sdk, "--show-sdk-version",
        ], required=True)
        sdk_versions[role] = result.stdout.strip()
    context["sdk_versions"] = sdk_versions
    record_command(diagnostics, "hardware-and-simulators", ["xcrun", "xctrace", "list", "devices"], required=True)
    inventory = json.loads(simctl("list", "devices", "available", "--json", capture=True))["devices"]
    pairs = list(json.loads(simctl("list", "pairs", "--json", capture=True))["pairs"].values())
    (diagnostics / "simulator-inventory.json").write_text(
        json.dumps({"devices": inventory, "pairs": pairs}, indent=2), encoding="utf-8")
    choice = choose_simulators(inventory, pairs, sdk_versions)
    context.update(choice)
    context["watch_app"] = str(watches[0])
    print(f"Simulator selection: {json.dumps(choice)}", flush=True)
    watch, phone = choice["watch"], choice["phone"]
    if choice["needs_pair"]:
        simctl("pair", watch["udid"], phone["udid"])

    for device in (phone, watch):
        if device["state"] != "Booted":
            simctl("boot", device["udid"])
            started.append(device["udid"])
        simctl("bootstatus", device["udid"], "-b")
    simctl("install", phone["udid"], str(bridge))
    simctl("install", watch["udid"], str(watches[0]))
    installed_path = simctl("get_app_container", watch["udid"], watch_id, "app", capture=True).strip()
    installed_plist = Path(installed_path, "Info.plist").read_bytes()
    (diagnostics / "installed-watch-Info.plist").write_bytes(installed_plist)
    info = plistlib.loads(installed_plist)
    schemes = [scheme for url_type in info.get("CFBundleURLTypes", [])
               for scheme in url_type.get("CFBundleURLSchemes", [])]
    capture_types = [item for item in info.get("CFBundleURLTypes", [])
                     if "ceviz-watch" in item.get("CFBundleURLSchemes", [])]
    if (info.get("CFBundleIdentifier") != watch_id or not capture_types
            or any(item.get("CFBundleTypeRole") != "Editor" for item in capture_types)):
        raise RuntimeError("Installed Watch app has an unexpected identifier or missing ceviz-watch Editor URL registration")
    apps = record_command(diagnostics, "watch-listapps", ["xcrun", "simctl", "listapps", watch["udid"]], required=True)
    converted = record_command(diagnostics, "watch-listapps-json", ["plutil", "-convert", "json", "-o", "-", "-"],
                               required=True, input_text=apps.stdout)
    if watch_id not in json.loads(converted.stdout):
        raise RuntimeError("Installed Watch app is absent from simctl listapps")
    context["installed_app"] = {"bundle_id": watch_id, "url_schemes": schemes,
                                "capture_role": "Editor", "listapps_verified": True}
    try:
        simctl("launch", watch["udid"], watch_id)
        # Allow the initial SwiftUI frame to draw. Captures require visual inspection;
        # a successful command alone is not evidence of a correct screen.
        time.sleep(3)
        simctl("io", watch["udid"], "screenshot", str(output / "01-cold-launch.png"))
        context["cold_launch"].update(status="succeeded", screenshot="01-cold-launch.png")
    except Exception:
        context["cold_launch"]["status"] = "failed"
        raise
    try:
        record_command(diagnostics, "watch-openurl", ["xcrun", "simctl", "openurl", watch["udid"], "ceviz-watch://capture"], required=True)
        time.sleep(2)
        simctl("io", watch["udid"], "screenshot", str(output / "02-capture-url.png"))
        context["capture_url"].update(status="succeeded", screenshot="02-capture-url.png")
    except Exception:
        context["capture_url"]["status"] = "failed"
        collect_url_failure_diagnostics(diagnostics, watch["udid"])
        raise  # URL injection failure still blocks signing; it is not a passing complication test.


if __name__ == "__main__":
    main()
