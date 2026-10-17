#!/usr/bin/env python3
"""Measure speech recognition on this machine and pick the largest Whisper model that is fast enough.

The installer runs it after the plan. Starting at the plan's suggestion, each model is loaded the
way the service loads it and transcribes an 11-second sample twice; the second run is timed. The
first model that finishes within the budget (3 s by default) is chosen; otherwise the next smaller
one is tried. Loading a model downloads it once into the Hugging Face cache, where the service
later finds it.

Stdout carries only the chosen model name (or JSON with --json); progress goes to stderr. The exit
code is 1 when no model could run at all, so the installer can fall back to its default.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZES = ("large-v3", "medium", "small")
DEFAULT_BUDGET_SECONDS = 3.0
DEFAULT_SAMPLE = ROOT / "deploy" / "assets" / "stt-sample.wav"  # 11.0 s of speech


def candidates_from(start: str) -> list[str]:
    return list(SIZES[SIZES.index(start):]) if start in SIZES else [start]


def measure(sizes: list[str], device: str, sample: Path, budget: float, opener=None, transcriber=None,
            log=lambda message: print(message, file=sys.stderr, flush=True)) -> dict:
    """Times each size until one fits the budget. Never raises for a model that cannot run."""
    if opener is None or transcriber is None:
        sys.path.insert(0, str(ROOT / "backend"))
        import local_whisper
        opener = opener or local_whisper.open_model
        transcriber = transcriber or local_whisper.transcribe_file
    tried = []
    for size in sizes:
        log(f"    {size}: loading (downloads once if needed)")
        started = time.perf_counter()
        try:
            model, used = opener(size, device)
            loaded = time.perf_counter() - started
            transcriber(model, str(sample), "en")  # first decode allocates; not timed
            started = time.perf_counter()
            text = transcriber(model, str(sample), "en")
            seconds = time.perf_counter() - started
        except Exception as exc:
            log(f"    {size}: could not run ({type(exc).__name__}: {str(exc)[:120]})")
            tried.append({"model": size, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        finally:
            model = None
            gc.collect()
        result = {"model": size, "device": used, "load_seconds": round(loaded, 1), "seconds": round(seconds, 2),
                  "fits": bool(text.strip()) and seconds <= budget, "heard": text.strip()[:60]}
        tried.append(result)
        log(f"    {size} on {used}: {seconds:.2f} s for the sample (budget {budget} s)"
            + ("" if result["fits"] else " - too slow" if text.strip() else " - heard nothing"))
        if result["fits"]:
            return {"chosen": result, "tried": tried}
    working = [r for r in tried if "error" not in r and r["heard"]]
    if working:
        fastest = min(working, key=lambda r: r["seconds"])
        log(f"    no model fits {budget} s; {fastest['model']} is the fastest that works")
        return {"chosen": {**fastest, "slow": True}, "tried": tried}
    return {"chosen": None, "tried": tried}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default="large-v3", help="largest size to try (the plan's suggestion)")
    parser.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET_SECONDS,
                        help="longest acceptable time for the 11 s sample")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--json", action="store_true", help="print every measurement as JSON")
    args = parser.parse_args(argv)
    result = measure(candidates_from(args.start), args.device, args.sample, args.budget)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["chosen"]:
        print(result["chosen"]["model"])
    return 0 if result["chosen"] else 1


if __name__ == "__main__":
    sys.exit(main())
