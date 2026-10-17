import sys
import time
import unittest
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY_DIR))

import measure_stt  # noqa: E402

SAMPLE = DEPLOY_DIR / "assets" / "stt-sample.wav"


class FakeWhisper:
    """Per-size decode time, heard text and load failures, standing in for local_whisper."""

    def __init__(self, seconds=None, text=None, broken=(), device="cuda"):
        self.seconds = seconds or {}
        self.text = text or {}
        self.broken = set(broken)
        self.device = device
        self.opened = []

    def open(self, size, device):
        self.opened.append((size, device))
        if size in self.broken:
            raise RuntimeError(f"cannot load {size}")
        return size, self.device

    def transcribe(self, model, path, lang):
        time.sleep(self.seconds.get(model, 0.0))
        return self.text.get(model, "And so, my fellow Americans")

    def run(self, sizes, budget):
        return measure_stt.measure(sizes, "auto", SAMPLE, budget, opener=self.open, transcriber=self.transcribe,
                                   log=lambda message: None)


class MeasureTests(unittest.TestCase):
    def test_sample_ships_with_the_installer(self):
        self.assertTrue(SAMPLE.exists())
        self.assertEqual(SAMPLE.read_bytes()[:4], b"RIFF")

    def test_candidates_step_down_from_the_plan(self):
        self.assertEqual(measure_stt.candidates_from("large-v3"), ["large-v3", "medium", "small"])
        self.assertEqual(measure_stt.candidates_from("medium"), ["medium", "small"])
        self.assertEqual(measure_stt.candidates_from("/models/custom"), ["/models/custom"])

    def test_first_model_within_budget_is_chosen_without_trying_smaller_ones(self):
        whisper = FakeWhisper()
        result = whisper.run(["large-v3", "medium", "small"], budget=1.0)
        self.assertEqual((result["chosen"]["model"], result["chosen"]["device"]), ("large-v3", "cuda"))
        self.assertEqual([size for size, _ in whisper.opened], ["large-v3"])

    def test_too_slow_steps_down(self):
        whisper = FakeWhisper(seconds={"large-v3": 0.12})
        result = whisper.run(["large-v3", "medium", "small"], budget=0.05)
        self.assertEqual(result["chosen"]["model"], "medium")
        self.assertFalse(result["tried"][0]["fits"])

    def test_a_model_that_cannot_load_is_skipped(self):
        result = FakeWhisper(broken={"large-v3"}).run(["large-v3", "medium"], budget=1.0)
        self.assertEqual(result["chosen"]["model"], "medium")
        self.assertIn("cannot load large-v3", result["tried"][0]["error"])

    def test_hearing_nothing_does_not_count_as_fast(self):
        result = FakeWhisper(text={"large-v3": ""}).run(["large-v3", "small"], budget=1.0)
        self.assertEqual(result["chosen"]["model"], "small")

    def test_when_none_fits_the_fastest_working_one_is_marked_slow(self):
        whisper = FakeWhisper(seconds={"medium": 0.12, "small": 0.06})
        result = whisper.run(["medium", "small"], budget=0.01)
        self.assertEqual((result["chosen"]["model"], result["chosen"]["slow"]), ("small", True))

    def test_nothing_runs_means_no_choice(self):
        result = FakeWhisper(broken={"medium", "small"}).run(["medium", "small"], budget=1.0)
        self.assertIsNone(result["chosen"])


if __name__ == "__main__":
    unittest.main()
