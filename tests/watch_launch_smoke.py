"""Capture the real, unconfigured Watch app. No job fixtures or recording are injected."""

import json
import plistlib
import re
import subprocess
import time
from pathlib import Path


def simctl(*args, capture=False):
    boot_status = args[0] == "bootstatus"
    try:
        result = subprocess.run(
            ["xcrun", "simctl", *args], check=True, text=True,
            capture_output=capture or boot_status, timeout=300 if boot_status else 120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        for diagnostic in (error.stdout, error.stderr):
            if diagnostic:
                print(diagnostic.decode(errors="replace") if isinstance(diagnostic, bytes) else diagnostic, flush=True)
        raise
    if boot_status:
        if not capture:
            print(result.stdout, flush=True)
        if result.stderr:
            print(result.stderr, flush=True)
        # CoreSimulator can report terminal migration failure with exit code zero.
        # Do not install/test on that failed boot or mistake it for app evidence.
        if "Data Migration Failed" in result.stdout:
            raise RuntimeError(f"Simulator {args[1]} data migration failed before app installation")
    return result.stdout


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


def validate_local_signature_text(details, bundle_id):
    fields = dict(line.split("=", 1) for line in details.splitlines() if "=" in line)
    if fields.get("Identifier") != bundle_id:
        raise RuntimeError(f"Simulator code Identifier does not match CFBundleIdentifier {bundle_id}")
    if fields.get("Signature") != "adhoc":
        raise RuntimeError(f"Simulator bundle {bundle_id} must use certificate-free ad hoc signing")
    return {"identifier": bundle_id, "signature": "adhoc"}


def verify_local_bundle_signature(diagnostics, name, bundle, expected_id):
    info = plistlib.loads((bundle / "Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != expected_id:
        raise RuntimeError(f"Unexpected simulator bundle identifier at {bundle}")
    details = record_command(diagnostics, f"{name}-codesign-display", [
        "codesign", "-d", "--verbose=4", str(bundle),
    ], required=True)
    signature = validate_local_signature_text(details.stdout + "\n" + details.stderr, expected_id)
    record_command(diagnostics, f"{name}-codesign-verify", [
        "codesign", "--verify", "--strict", "--verbose=2", str(bundle),
    ], required=True)
    return {"bundle": str(bundle), **signature, "verified": True}


def initial_context(candidate_for_device_check=False):
    return {
        "scope": "Unconfigured normal app launch and external simulator URL injection; no real job or complication tap tested",
        "candidate_for_device_check": candidate_for_device_check,
        "cold_launch": {"status": "not_run", "visual_review": "pending"},
        "capture_url": {"status": "not_run", "url": "ceviz-watch://capture", "visual_review": "pending"},
        "widget_tap": {"status": "not_tested", "reason": "Generic simctl URL injection is not a WidgetKit complication tap"},
        "external_distribution": {"status": "blocked_pending_device_validation"},
    }


def main(*, candidate_for_device_check=False):
    output = Path("build/watch-launch-smoke")
    output.mkdir(parents=True, exist_ok=True)
    diagnostics = output / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    context = initial_context(candidate_for_device_check)
    started = []
    try:
        run_smoke(output, diagnostics, context, started,
                  candidate_for_device_check=candidate_for_device_check)
    except Exception as error:
        context["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (output / "context.json").write_text(json.dumps(context, indent=2), encoding="utf-8")
        for udid in reversed(started):
            subprocess.run(["xcrun", "simctl", "shutdown", udid], check=False, timeout=60)


def run_smoke(output, diagnostics, context, started, *, candidate_for_device_check=False):
    bridge = Path("build/validation/Build/Products/Release-iphonesimulator/CevizBridge.app")
    watch_id = "com.mertbasar.cevizwatch.watchkitapp"
    watches = [
        app for app in (bridge / "Watch").glob("*.app")
        if plistlib.loads((app / "Info.plist").read_bytes())["CFBundleIdentifier"] == watch_id
    ]
    if len(watches) != 1:
        raise RuntimeError("Expected exactly one embedded Ceviz Watch application")

    # Simulator execution needs its ordinary local identity, not distribution
    # credentials. Check all three Xcode-produced bundles before installation.
    context["local_signatures"] = []
    for name, bundle, bundle_id in (
        ("bridge", bridge, "com.mertbasar.cevizwatch"),
        ("watch", watches[0], watch_id),
        ("widget", watches[0] / "PlugIns" / "CevizWatchWidget.appex", watch_id + ".widget"),
    ):
        context["local_signatures"].append(
            verify_local_bundle_signature(diagnostics, name, bundle, bundle_id))

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
    context["installed_watch_signature"] = verify_local_bundle_signature(
        diagnostics, "installed-watch", Path(installed_path), watch_id)
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
    run_capture_url_probe(output, diagnostics, context, watch["udid"],
                          candidate_for_device_check=candidate_for_device_check)


def run_capture_url_probe(output, diagnostics, context, watch_udid, *, candidate_for_device_check=False):
    probe_command = ["xcrun", "simctl", "openurl", watch_udid, "ceviz-watch://capture"]
    try:
        record_command(diagnostics, "watch-openurl", probe_command, required=True)
        time.sleep(2)
        simctl("io", watch_udid, "screenshot", str(output / "02-capture-url.png"))
        context["capture_url"].update(status="succeeded", screenshot="02-capture-url.png")
    except Exception as error:
        context["capture_url"].update(status="failed", failure=f"{type(error).__name__}: {error}")
        collect_url_failure_diagnostics(diagnostics, watch_udid)
        known_115 = (
            isinstance(error, subprocess.CalledProcessError)
            and error.cmd == probe_command
            and error.returncode == 115
            and re.search(r"\(domain=LSApplicationWorkspaceErrorDomain,\s*code=115\)", error.stderr or "") is not None
        )
        if candidate_for_device_check and known_115:
            context["capture_url"]["candidate_exception_applied"] = True
            context["candidate_status"] = "unresolved_widget_navigation_requires_device_check"
            print("::warning::Generic simulator URL injection failed with LSApplicationWorkspaceErrorDomain 115. "
                  "Explicit device-check candidate only: WidgetKit tap is NOT TESTED and external distribution remains blocked.", flush=True)
            return
        raise  # Strict by default; other errors and timeouts remain fatal in candidate mode.


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-for-device-check", action="store_true",
                        help="Retain known external URL error 115 as unresolved candidate evidence; does not authorize external distribution")
    options = parser.parse_args()
    main(candidate_for_device_check=options.candidate_for_device_check)
