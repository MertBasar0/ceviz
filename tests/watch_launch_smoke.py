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


def main():
    bridge = Path("build/validation/Build/Products/Release-iphonesimulator/CevizBridge.app")
    watch_id = "com.mertbasar.cevizwatch.watchkitapp"
    watches = [
        app for app in (bridge / "Watch").glob("*.app")
        if plistlib.loads((app / "Info.plist").read_bytes())["CFBundleIdentifier"] == watch_id
    ]
    if len(watches) != 1:
        raise RuntimeError("Expected exactly one embedded Ceviz Watch application")

    # Enumerate attached hardware before choosing the CI simulator proof surface.
    subprocess.run(["xcrun", "xctrace", "list", "devices"], check=True)
    inventory = json.loads(simctl("list", "devices", "available", "--json", capture=True))["devices"]
    devices = {device["udid"]: (runtime, device) for runtime, entries in inventory.items() for device in entries}
    pairs = json.loads(simctl("list", "pairs", "--json", capture=True))["pairs"].values()
    compatible = [pair for pair in pairs if pair["watch"]["udid"] in devices and pair["phone"]["udid"] in devices]
    if compatible:
        pair = max(compatible, key=lambda item: runtime_version(devices[item["watch"]["udid"]][0]))
        watch = devices[pair["watch"]["udid"]][1]
        phone = devices[pair["phone"]["udid"]][1]
    else:
        def choose(platform, name):
            available = [(runtime, device) for runtime, device in devices.values() if platform in runtime and device["name"].startswith(name)]
            if not available:
                raise RuntimeError(f"No available {platform} simulator; install its runtime before signing")
            return max(available, key=lambda item: (runtime_version(item[0]), item[1]["name"]))[1]

        watch = choose("watchOS", "Apple Watch")
        phone = choose("iOS", "iPhone")
        simctl("pair", watch["udid"], phone["udid"])

    output = Path("build/watch-launch-smoke")
    output.mkdir(parents=True, exist_ok=True)
    (output / "context.json").write_text(json.dumps({
        "watch": watch,
        "phone": phone,
        "watch_runtime": devices[watch["udid"]][0],
        "watch_app": str(watches[0]),
        "scope": "Unconfigured cold launch and capture URL; no real job or complication tap tested",
    }, indent=2), encoding="utf-8")

    started = []
    try:
        for device in (phone, watch):
            if device["state"] != "Booted":
                simctl("boot", device["udid"])
                started.append(device["udid"])
            simctl("bootstatus", device["udid"], "-b")
        simctl("install", phone["udid"], str(bridge))
        simctl("install", watch["udid"], str(watches[0]))
        simctl("launch", watch["udid"], watch_id)
        # Allow the initial SwiftUI frame to draw. Captures require visual inspection;
        # a successful command alone is not evidence of a correct screen.
        time.sleep(3)
        simctl("io", watch["udid"], "screenshot", str(output / "01-cold-launch.png"))
        simctl("openurl", watch["udid"], "ceviz-watch://capture")
        time.sleep(2)
        simctl("io", watch["udid"], "screenshot", str(output / "02-capture-url.png"))
    finally:
        for udid in reversed(started):
            subprocess.run(["xcrun", "simctl", "shutdown", udid], check=False)


if __name__ == "__main__":
    main()
