#!/usr/bin/env python3
"""Ceviz plan: a read-only survey of this machine and the setup it can run well.

It changes nothing. It reads the hardware, the installed software and, unless --offline is
given, whether the services Ceviz depends on are reachable. It then prints a recipe: whether
Whisper large-v3 runs here or the iPhone transcribes, whether the optional Pusula router can
run, how the phone will reach the helper, and what to fix first. --json prints the same as
structured data for the installer or for an assistant that explains the plan; it never contains
credentials.

Standard library only, so it runs with the system Python before anything is installed.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA_VERSION = 1
SERVICE = "watch-ceviz-backend"

# Resident GPU memory while serving, including working buffers, in GB. Measured on an RTX 5070 Ti
# with faster-whisper fp16 (large-v3) and Ollama at a 2,048-token context (OpenJev 4B).
# Only large-v3 is planned: in daily use the smaller models misheard too many commands to help.
WHISPER_MODEL = "large-v3"
WHISPER_GPU_GB = 4.5
WHISPER_DISK_GB = 3.1
DECISION_MODEL = "hf.co/apus-ailab/APUS-OpenJev-v1-4B-GGUF:Q8_0"
DECISION_MODEL_GB = 6.7
DECISION_MODEL_DISK_GB = 4.5
# Memory the desktop and driver keep for themselves on a shared card, and a margin per plan.
DESKTOP_RESERVE_GB = 1.5
HEADROOM_GB = 0.6
# Without a GPU: warm large-v3 took 3.5 s for 11 s of speech on 16 threads (Ryzen 9 9950X3D under
# WSL), just over the installer's 3 s budget. From 16 threads and 16 GB the installer times it;
# anything else leaves speech recognition to the iPhone.
STRONG_CPU_THREADS = 16
STRONG_CPU_RAM_GB = 16
MEASURED_AT_INSTALL = ("The installer times it on this machine; if it is too slow, the iPhone transcribes "
                       "instead.")
ON_PHONE = ("The iPhone transcribes each command with Apple's on-device speech recognition and sends the "
            "text; no Whisper model is downloaded.")
FRONTIER_PROVIDERS = ("anthropic", "openai", "google", "xai")
# Only these service settings are read; the pairing token and everything else stay unread.
SERVICE_SETTINGS = ("WATCH_CEVIZ_WHISPER_MODEL", "WATCH_CEVIZ_STT_ENGINE", "WATCH_CEVIZ_ROUTER",
                    "WATCH_CEVIZ_PUSH_RELAY_URL", "OPENCLAW_WATCH_AGENT", "OPENCLAW_HOME", "OCM_ACTIVE_ENV")
# Used only to run OpenClaw the way the helper does; never printed.
SERVICE_RUNTIME = ("PATH",)
ENDPOINTS = {
    "push_relay": "https://push.cevizrelay.dev/healthz",
    "huggingface": "https://huggingface.co",
    "ollama_registry": "https://ollama.com",
}


# --- probing ---------------------------------------------------------------------------------
def run(arguments: list[str], timeout: float = 10) -> tuple[int, str]:
    """(exit code, combined output); 127 when the program is missing or does not finish."""
    try:
        done = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return done.returncode, (done.stdout + done.stderr).strip()


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def memory_gb() -> dict:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values = {}
        for line in meminfo.read_text().splitlines():
            key, _, rest = line.partition(":")
            number = rest.strip().split(" ")[0]
            if number.isdigit():
                values[key] = int(number) / 1024 / 1024
        return {"total": round(values.get("MemTotal", 0), 1), "available": round(values.get("MemAvailable", 0), 1)}
    code, out = run(["sysctl", "-n", "hw.memsize"])
    total = int(out) / 1024 ** 3 if code == 0 and out.isdigit() else 0
    return {"total": round(total, 1), "available": None}


def cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    code, out = run(["sysctl", "-n", "machdep.cpu.brand_string"])
    return out if code == 0 else platform.processor()


def nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    wsl_copy = Path("/usr/lib/wsl/lib/nvidia-smi")
    return str(wsl_copy) if wsl_copy.exists() else None


def parse_nvidia(code: int, output: str) -> dict:
    """GPU list from `nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version`."""
    if "GPU access blocked" in output or "Failed to initialize NVML" in output:
        # Seen on WSL on 11 October 2026: the card exists but WSL lost access to it.
        return {"status": "blocked", "devices": [], "detail": output.splitlines()[0][:160]}
    if code != 0:
        return {"status": "error", "devices": [], "detail": output.splitlines()[0][:160] if output else ""}
    devices = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit():
            devices.append({"name": parts[0], "total_gb": round(int(parts[1]) / 1024, 1),
                            "used_gb": round(int(parts[2]) / 1024, 1), "driver": parts[3]})
    return {"status": "ok" if devices else "error", "devices": devices, "detail": ""}


def gpu() -> dict:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return {"status": "apple_silicon", "devices": [], "detail": "unified memory; no CUDA"}
    binary = nvidia_smi()
    if not binary:
        return {"status": "absent", "devices": [], "detail": ""}
    code, out = run([binary, "--query-gpu=name,memory.total,memory.used,driver_version",
                     "--format=csv,noheader,nounits"])
    return parse_nvidia(code, out)


def version_of(program: str, *arguments: str) -> dict:
    path = shutil.which(program)
    if not path:
        return {"present": False}
    code, out = run([path, *arguments] if arguments else [path, "--version"], timeout=20)
    match = re.search(r"\d+\.\d+(?:\.\d+)?", out)
    return {"present": True, "version": match.group(0) if code == 0 and match else None}


def ollama_state() -> dict:
    state = version_of("ollama")
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            tags = json.loads(response.read().decode())
        state["server"] = True
        state["models"] = sorted(item.get("name", "") for item in tags.get("models", []))
    except (OSError, ValueError, urllib.error.URLError):
        state["server"] = False
        state["models"] = []
    return state


def parse_openclaw_models(stdout: str) -> dict:
    """Configured models from `openclaw models list --json` (an object with a `models` list).

    Only models the user configured count (tagged default, configured or fallback#n): a model that
    is merely available may sit behind a paid key nobody chose for Ceviz. Escalation targets are
    configured models from direct frontier providers other than the default, as Pusula uses them.
    """
    try:
        data = json.loads(stdout or "{}")
    except ValueError:
        return {"readable": False}
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        return {"readable": False}
    configured, default = [], None
    for row in data["models"]:
        tags = [str(tag) for tag in (row.get("tags") or [])] if isinstance(row, dict) else []
        key = str(row.get("key") or "") if isinstance(row, dict) else ""
        if not key or not any(t in ("default", "configured") or t.startswith("fallback") for t in tags):
            continue
        configured.append(key)
        if "default" in tags:
            default = key
    targets = [key for key in configured if key != default and key.split("/", 1)[0] in FRONTIER_PROVIDERS]
    return {"readable": True, "default": default, "configured": configured, "escalation_targets": targets}


def openclaw_state(agent: str, environment: dict | None = None) -> dict:
    """The OpenClaw the helper uses: with an installed service, its PATH and OpenClaw settings."""
    env = {**os.environ, **(environment or {})}
    path = shutil.which("openclaw", path=env.get("PATH"))
    if not path:
        return {"present": False}
    state = {"present": True, "path": path, "version": None}
    try:
        done = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20, env=env)
        match = re.search(r"\d+\.\d+(?:\.\d+)?", done.stdout)
        state["version"] = match.group(0) if done.returncode == 0 and match else None
        arguments = [path, "models", "list", "--json"] + (["--agent", agent] if agent else [])
        done = subprocess.run(arguments, capture_output=True, text=True, timeout=60, env=env)
        state["models"] = parse_openclaw_models(done.stdout) if done.returncode == 0 else {"readable": False}
    except (OSError, subprocess.SubprocessError):
        state["models"] = {"readable": False}
    return state


def parse_service_environment(line: str, keys: tuple[str, ...] = SERVICE_SETTINGS) -> dict:
    """Allowlisted settings from `systemctl show -p Environment`; nothing else is kept."""
    settings = {}
    for item in line.replace("Environment=", "", 1).split():
        key, _, value = item.partition("=")
        if key in keys:
            settings[key] = value
    return settings


def ceviz_service() -> tuple[dict, dict]:
    """(what can be shown, the PATH needed to run OpenClaw as the helper does)."""
    if not shutil.which("systemctl"):
        return {"systemd_user": False, "installed": False}, {}
    code, out = run(["systemctl", "--user", "show", SERVICE, "-p", "LoadState", "-p", "ActiveState"])
    if code != 0:
        return {"systemd_user": False, "installed": False}, {}
    fields = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    installed = fields.get("LoadState") == "loaded"
    state = {"systemd_user": True, "installed": installed, "active": fields.get("ActiveState") == "active"}
    if not installed:
        return state, {}
    _, environment = run(["systemctl", "--user", "show", SERVICE, "-p", "Environment"])
    state["settings"] = parse_service_environment(environment)
    runtime = parse_service_environment(environment, SERVICE_RUNTIME)
    runtime.update({key: value for key, value in state["settings"].items() if key in ("OPENCLAW_HOME", "OCM_ACTIVE_ENV")})
    return state, runtime


def reachable(url: str) -> dict:
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "ceviz-plan"})
    try:
        with urllib.request.urlopen(request, timeout=6, context=ssl.create_default_context()) as response:
            return {"ok": response.status < 500, "status": response.status}
    except urllib.error.HTTPError as error:
        return {"ok": error.code < 500, "status": error.code}
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        reset = isinstance(reason, ConnectionResetError) or "reset" in str(reason).lower()
        return {"ok": False, "error": "connection_reset" if reset else type(reason).__name__}


def disk_free_gb(path: Path) -> float:
    try:
        return round(shutil.disk_usage(path).free / 1024 ** 3, 1)
    except OSError:
        return 0.0


def probe(offline: bool = False, agent: str = "") -> dict:
    home = Path.home()
    service, runtime = ceviz_service()
    agent = agent or (service.get("settings") or {}).get("OPENCLAW_WATCH_AGENT", "")
    return {
        "platform": {"system": platform.system(), "machine": platform.machine(), "wsl": is_wsl(),
                     "python": platform.python_version()},
        "cpu": {"model": cpu_model(), "threads": os.cpu_count() or 0},
        "memory_gb": memory_gb(),
        "gpu": gpu(),
        "disk_free_gb": disk_free_gb(home),
        "software": {
            "openclaw": {**openclaw_state(agent, runtime), "agent": agent or None},
            "node": version_of("node"),
            "ollama": ollama_state(),
            "tailscale": version_of("tailscale"),
        },
        "ceviz": service,
        "network": None if offline else {name: reachable(url) for name, url in ENDPOINTS.items()},
    }


# --- recipe ----------------------------------------------------------------------------------
def step(module: str, status: str, choice: str, reasons: list[str], **extra) -> dict:
    """status: recommended | optional | later | not_recommended | blocked."""
    return {"module": module, "status": status, "choice": choice, "reasons": reasons, **extra}


def gpu_budget(facts: dict) -> float:
    """GB of GPU memory Ceviz may plan with: the card minus what the desktop keeps."""
    gpu_facts = facts["gpu"]
    if gpu_facts["status"] != "ok" or not gpu_facts["devices"]:
        return 0.0
    card = max(device["total_gb"] for device in gpu_facts["devices"])
    return max(0.0, card - DESKTOP_RESERVE_GB)


def plan_speech(facts: dict) -> tuple[dict, float]:
    """Whisper large-v3 where it can run well, otherwise the iPhone; and the GPU memory it takes."""
    budget = gpu_budget(facts)
    if budget >= WHISPER_GPU_GB + HEADROOM_GB:
        return step("speech", "recommended", f"Whisper {WHISPER_MODEL} on the GPU",
                    [f"{budget:.1f} GB of GPU memory is available to Ceviz; {WHISPER_MODEL} needs about "
                     f"{WHISPER_GPU_GB} GB.", MEASURED_AT_INSTALL],
                    engine="local", whisper_model=WHISPER_MODEL, device="cuda"), WHISPER_GPU_GB
    threads = facts["cpu"]["threads"]
    ram = facts["memory_gb"]["total"] or 0
    reasons = []
    if facts["gpu"]["status"] == "blocked":
        reasons.append("An NVIDIA card is installed but this system cannot reach it; fix that first "
                       f"(on WSL: `wsl --shutdown` from Windows) to run {WHISPER_MODEL} on it.")
    elif facts["gpu"]["status"] == "apple_silicon":
        reasons.append("Apple Silicon: the current speech engine runs on the CPU only; a Metal engine is planned.")
    elif budget:
        reasons.append(f"The GPU leaves only {budget:.1f} GB for Ceviz; {WHISPER_MODEL} needs about "
                       f"{WHISPER_GPU_GB + HEADROOM_GB:.1f} GB.")
    else:
        reasons.append("No usable NVIDIA GPU was found.")
    if threads >= STRONG_CPU_THREADS and ram >= STRONG_CPU_RAM_GB:
        reasons += [f"{threads} CPU threads may run {WHISPER_MODEL} fast enough.", MEASURED_AT_INSTALL]
        return step("speech", "recommended", f"Whisper {WHISPER_MODEL} on the CPU", reasons,
                    engine="local", whisper_model=WHISPER_MODEL, device="cpu"), 0.0
    reasons += [f"{threads} CPU threads and {ram:.0f} GB of memory are too little for {WHISPER_MODEL} without "
                "a GPU, and smaller models mishear too many commands.", ON_PHONE]
    return step("speech", "recommended", "Transcribe on the iPhone", reasons,
                engine="phone", whisper_model=None, device=None), 0.0


def speech_label(value: str) -> str:
    return "transcription on the iPhone" if value == "phone" else f"Whisper {value}"


def plan_executor(facts: dict) -> dict:
    openclaw = facts["software"]["openclaw"]
    if not openclaw["present"]:
        return step("executor", "blocked", "Install OpenClaw, then sign in with an AI account you already have",
                    ["Ceviz runs every command through OpenClaw, which is not installed.",
                     "Recommended default: the model from your existing subscription (Claude: Sonnet; "
                     "ChatGPT: GPT), with a smaller model from the same provider as the fallback."])
    models = openclaw.get("models") or {}
    if not models.get("readable"):
        return step("executor", "recommended", "Keep OpenClaw's configured model",
                    ["OpenClaw is installed; its model list could not be read, so the model was not checked."])
    default = models.get("default")
    if default and default.split("/", 1)[0] not in FRONTIER_PROVIDERS:
        return step("executor", "recommended", f"Consider a frontier default instead of {default}",
                    ["In Ceviz's tests, 30B–120B models often failed tool-heavy requests and wrote weaker Turkish. "
                     "A Claude or ChatGPT subscription model is the more reliable default."], default=default)
    return step("executor", "recommended", f"Keep {default or 'the configured model'}",
                ["OpenClaw is installed with a frontier model as its default."], default=default)


def plan_pusula(facts: dict, speech_gb: float) -> dict:
    budget = gpu_budget(facts)
    left = budget - speech_gb
    models = (facts["software"]["openclaw"].get("models") or {})
    reasons = [f"Pusula's decision model ({DECISION_MODEL}) needs about {DECISION_MODEL_GB} GB of GPU memory "
               "beside speech recognition and answers within the 1.2 s routing budget only on a GPU."]
    if left < DECISION_MODEL_GB + HEADROOM_GB:
        reasons.append(f"After speech recognition, {max(left, 0):.1f} GB would remain.")
        return step("pusula", "not_recommended", "Standard model use (no automatic routing)", reasons)
    if not facts["software"]["openclaw"]["present"] or not models.get("readable"):
        reasons.append(f"{left:.1f} GB would remain, enough for it. Whether a stronger model exists to escalate to "
                       "is decided after OpenClaw is set up.")
        return step("pusula", "later", "Decide after OpenClaw setup", reasons)
    if not models.get("escalation_targets"):
        reasons.append("Pusula moves a missed turn to a stronger configured model; apart from the default, "
                       "no Anthropic, OpenAI, Google or xAI model is configured, so there is nothing to escalate to.")
        return step("pusula", "not_recommended", "Standard model use (no automatic routing)", reasons)
    ollama = facts["software"]["ollama"]
    needs = []
    if not ollama.get("present"):
        needs.append("install Ollama")
    if DECISION_MODEL not in ollama.get("models", []):
        needs.append(f"download the decision model (~{DECISION_MODEL_DISK_GB} GB)")
    reasons.append(f"{left:.1f} GB would remain after speech recognition. It is optional: routing can pin "
                   "a paid model for a turn.")
    return step("pusula", "optional", "Pusula with OpenJev 4B (your choice)", reasons, needs=needs)


def plan_network(facts: dict) -> dict:
    if facts["software"]["tailscale"]["present"]:
        return step("network", "recommended", "Tailscale", ["Tailscale is installed; the phone reaches the helper "
                                                            "through your tailnet from anywhere."])
    if facts["platform"]["wsl"]:
        return step("network", "recommended", "Local network relay on Windows",
                    ["No Tailscale; the phone can reach the helper on the same Wi-Fi through a Windows relay. "
                     "Installing Tailscale also allows use away from home."])
    return step("network", "recommended", "Manual address", ["No Tailscale; enter the helper's address in the app."])


def recommend(facts: dict) -> dict:
    warnings, blockers = [], []
    python = tuple(int(part) for part in facts["platform"]["python"].split(".")[:2])
    if python < (3, 11):
        blockers.append(f"Python {facts['platform']['python']} is too old; Ceviz needs 3.11 or newer.")
    if facts["platform"]["system"] == "Linux" and not facts["ceviz"].get("systemd_user"):
        blockers.append("No systemd user session; the helper runs as a systemd user service.")
    if facts["platform"]["system"] == "Darwin":
        warnings.append("macOS helpers are not covered by automatic updates yet.")
    openclaw_path = facts["software"]["openclaw"].get("path") or ""
    if facts["platform"]["wsl"] and openclaw_path.startswith("/mnt/"):
        warnings.append(f"The OpenClaw found is the Windows install ({openclaw_path}); the helper in WSL needs "
                        "OpenClaw installed inside WSL.")

    speech, speech_gb = plan_speech(facts)
    executor = plan_executor(facts)
    pusula = plan_pusula(facts, speech_gb)
    network = plan_network(facts)

    disk_need = ((WHISPER_DISK_GB if speech["engine"] == "local" else 0)
                 + (DECISION_MODEL_DISK_GB if pusula["status"] == "optional" else 0))
    if facts["disk_free_gb"] < disk_need + 5:
        warnings.append(f"Only {facts['disk_free_gb']} GB free in your home folder; the models need about "
                        f"{disk_need:.1f} GB plus room to update.")
    if facts["gpu"]["status"] == "ok" and facts["software"]["ollama"].get("server"):
        warnings.append("Ollama is running and shares the GPU; models it keeps loaded reduce what Ceviz can use.")
    network_facts = facts.get("network") or {}
    relay = network_facts.get("push_relay")
    if relay and not relay["ok"]:
        hint = " The connection was reset, which looks like network filtering." if relay.get("error") == "connection_reset" else ""
        warnings.append("The notification relay is not reachable; results will not arrive as notifications." + hint)
    for name in ("huggingface", "ollama_registry"):
        if network_facts.get(name) and not network_facts[name]["ok"]:
            warnings.append(f"{name} is not reachable; models cannot be downloaded from it.")

    current = facts["ceviz"].get("settings") or {}
    changes = []
    installed = ("phone" if current.get("WATCH_CEVIZ_STT_ENGINE") == "phone"
                 else current.get("WATCH_CEVIZ_WHISPER_MODEL"))
    planned = speech["whisper_model"] or "phone"
    if installed and installed != planned:
        changes.append(f"Speech recognition uses {speech_label(installed)}; the plan for this machine is "
                       f"{speech_label(planned)}.")
    return {"schema": SCHEMA_VERSION, "blockers": blockers, "steps": [executor, speech, network, pusula],
            "warnings": warnings, "differences_from_current": changes}


# --- output ----------------------------------------------------------------------------------
LABELS = {"recommended": "RECOMMENDED", "optional": "OPTIONAL", "later": "LATER",
          "not_recommended": "NOT ADVISED", "blocked": "NEEDED"}


def describe_machine(facts: dict) -> list[str]:
    system = "WSL2 on Windows" if facts["platform"]["wsl"] else facts["platform"]["system"]
    memory = facts["memory_gb"]
    lines = [f"  {system} ({facts['platform']['machine']}), Python {facts['platform']['python']}",
             f"  CPU: {facts['cpu']['model']} ({facts['cpu']['threads']} threads)",
             f"  Memory: {memory['total']} GB" + (f" ({memory['available']} GB free)" if memory.get("available") else "")]
    gpu_facts = facts["gpu"]
    if gpu_facts["devices"]:
        for device in gpu_facts["devices"]:
            lines.append(f"  GPU: {device['name']}, {device['total_gb']} GB ({device['used_gb']} GB in use)")
    else:
        lines.append(f"  GPU: {gpu_facts['status']}" + (f" ({gpu_facts['detail']})" if gpu_facts["detail"] else ""))
    lines.append(f"  Disk: {facts['disk_free_gb']} GB free in your home folder")
    software = facts["software"]
    for name in ("openclaw", "node", "ollama", "tailscale"):
        item = software[name]
        lines.append(f"  {name}: " + (f"installed {item.get('version') or ''}".rstrip() if item["present"] else "not installed"))
    service = facts["ceviz"]
    if service.get("installed"):
        lines.append("  Ceviz helper: installed, " + ("running" if service.get("active") else "stopped"))
    return lines


def render(facts: dict, recipe: dict) -> str:
    out = ["Ceviz plan (nothing was changed)", "", "This machine"] + describe_machine(facts) + ["", "Recipe"]
    for item in recipe["steps"]:
        out.append(f"  [{LABELS[item['status']]}] {item['module']}: {item['choice']}")
        out.extend(f"      - {reason}" for reason in item["reasons"])
        out.extend(f"      - to do: {need}" for need in item.get("needs", []))
    for title, key in (("Fix first", "blockers"), ("Warnings", "warnings"), ("Differences from your install", "differences_from_current")):
        if recipe[key]:
            out += ["", title] + [f"  - {line}" for line in recipe[key]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print facts and recipe as JSON")
    parser.add_argument("--offline", action="store_true", help="skip the reachability checks")
    parser.add_argument("--agent", default=os.environ.get("OPENCLAW_WATCH_AGENT", ""),
                        help="OpenClaw agent whose models are read (default: the installed helper's agent)")
    parser.add_argument("--speech", action="store_true",
                        help="for the installer: the report on stderr, 'large-v3 cuda|cpu' or 'phone none' on stdout")
    args = parser.parse_args(argv)
    facts = probe(offline=args.offline, agent=args.agent)
    recipe = recommend(facts)
    if args.speech:
        print(render(facts, recipe), file=sys.stderr)
        speech = next(item for item in recipe["steps"] if item["module"] == "speech")
        print(f"{speech['whisper_model']} {speech['device']}" if speech["engine"] == "local" else "phone none")
        return 0  # the installer decides what is fatal; it has its own Python and service checks
    if args.json:
        print(json.dumps({"facts": facts, "recipe": recipe}, indent=2, ensure_ascii=False))
    else:
        print(render(facts, recipe))
    return 1 if recipe["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
