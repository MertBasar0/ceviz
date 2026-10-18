#!/usr/bin/env python3
"""Time Whisper large-v3 on this machine; the installer uses it only if it is fast enough.

The installer runs it after the plan, on the plan's device. large-v3 is loaded the way the service
loads it and transcribes an 11-second sample twice; the second run is timed. It is used only if it
finishes within the budget (3 s by default) and hears the speech. Otherwise the installer leaves
speech recognition to the iPhone: in daily use the smaller Whisper models misheard too many
commands to be worth running. Loading the model downloads it once into the Hugging Face cache,
where the service later finds it; a download that turns out too slow to use is removed again.

Stdout carries only the model name when it fits (or JSON with --json); progress goes to stderr.
Exit codes: 0 fits, 1 too slow or heard nothing, 2 could not run.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "large-v3"
DEFAULT_BUDGET_SECONDS = 3.0
DEFAULT_SAMPLE = ROOT / "deploy" / "assets" / "stt-sample.wav"  # 11.0 s of speech


def cached_model_dir(model: str) -> Path:
    """Where faster-whisper keeps a named model (Systran's repo in the Hugging Face hub cache)."""
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")
    return Path(hub) / f"models--Systran--faster-whisper-{model}"


def measure(model: str, device: str, sample: Path, budget: float, opener=None, transcriber=None,
            log=lambda message: print(message, file=sys.stderr, flush=True)) -> dict:
    """One timed decode of the sample. Never raises for a model that cannot run."""
    if opener is None or transcriber is None:
        sys.path.insert(0, str(ROOT / "backend"))
        import local_whisper
        opener = opener or local_whisper.open_model
        transcriber = transcriber or local_whisper.transcribe_file
    log(f"    {model}: loading (downloads once if needed)")
    started = time.perf_counter()
    loaded_model = None
    try:
        loaded_model, used = opener(model, device)
        loaded = time.perf_counter() - started
        transcriber(loaded_model, str(sample), "en")  # first decode allocates; not timed
        started = time.perf_counter()
        text = transcriber(loaded_model, str(sample), "en")
        seconds = time.perf_counter() - started
    except Exception as exc:
        log(f"    {model}: could not run ({type(exc).__name__}: {str(exc)[:120]})")
        return {"model": model, "fits": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        loaded_model = None
        gc.collect()
    heard = text.strip()
    result = {"model": model, "device": used, "load_seconds": round(loaded, 1), "seconds": round(seconds, 2),
              "fits": bool(heard) and seconds <= budget, "heard": heard[:60]}
    log(f"    {model} on {used}: {seconds:.2f} s for the sample (budget {budget} s)"
        + ("" if result["fits"] else " - too slow" if heard else " - heard nothing"))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=MODEL, help=argparse.SUPPRESS)  # experiments only
    parser.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET_SECONDS,
                        help="longest acceptable time for the 11 s sample")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--json", action="store_true", help="print the measurement as JSON")
    args = parser.parse_args(argv)
    cache = cached_model_dir(args.model)
    was_cached = cache.exists()
    result = measure(args.model, args.device, args.sample, args.budget)
    if not result["fits"] and not was_cached and cache.exists():
        shutil.rmtree(cache, ignore_errors=True)  # do not leave 3 GB the service will never load
        result["removed_download"] = True
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["fits"]:
        print(result["model"])
    return 0 if result["fits"] else 2 if "error" in result else 1


if __name__ == "__main__":
    sys.exit(main())
