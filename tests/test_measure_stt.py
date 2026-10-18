import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY_DIR))

import measure_stt  # noqa: E402

SAMPLE = DEPLOY_DIR / "assets" / "stt-sample.wav"


class FakeWhisper:
    """Decode time, heard text and a load failure, standing in for local_whisper."""

    def __init__(self, seconds=0.0, text="And so, my fellow Americans", broken=False, device="cuda"):
        self.seconds = seconds
        self.text = text
        self.broken = broken
        self.device = device
        self.opened = []

    def open(self, size, device):
        self.opened.append((size, device))
        if self.broken:
            raise RuntimeError(f"cannot load {size}")
        return size, self.device

    def transcribe(self, model, path, lang):
        time.sleep(self.seconds)
        return self.text

    def run(self, budget):
        return measure_stt.measure("large-v3", "auto", SAMPLE, budget, opener=self.open,
                                   transcriber=self.transcribe, log=lambda message: None)


class MeasureTests(unittest.TestCase):
    def test_sample_ships_with_the_installer(self):
        self.assertTrue(SAMPLE.exists())
        self.assertEqual(SAMPLE.read_bytes()[:4], b"RIFF")

    def test_large_v3_within_budget_fits(self):
        whisper = FakeWhisper()
        result = whisper.run(budget=1.0)
        self.assertEqual((result["model"], result["device"], result["fits"]), ("large-v3", "cuda", True))
        self.assertEqual(whisper.opened, [("large-v3", "auto")])

    def test_too_slow_does_not_fit_and_no_smaller_model_is_tried(self):
        whisper = FakeWhisper(seconds=0.12)
        result = whisper.run(budget=0.05)
        self.assertFalse(result["fits"])
        self.assertEqual(whisper.opened, [("large-v3", "auto")])

    def test_hearing_nothing_does_not_count_as_fast(self):
        self.assertFalse(FakeWhisper(text="").run(budget=1.0)["fits"])

    def test_a_model_that_cannot_load_is_reported(self):
        result = FakeWhisper(broken=True).run(budget=1.0)
        self.assertFalse(result["fits"])
        self.assertIn("cannot load large-v3", result["error"])

    def test_exit_codes_and_a_useless_download_is_removed(self):
        with tempfile.TemporaryDirectory() as hub, mock.patch.dict(os.environ, {"HF_HUB_CACHE": hub}):
            cache = measure_stt.cached_model_dir("large-v3")
            self.assertEqual(cache.parent, Path(hub))

            def slow(model, device, sample, budget):
                cache.mkdir(parents=True)  # the load downloaded it
                return {"model": model, "fits": False, "seconds": 9.0, "heard": "words"}

            with mock.patch.object(measure_stt, "measure", side_effect=slow), mock.patch("builtins.print"):
                self.assertEqual(measure_stt.main([]), 1)
            self.assertFalse(cache.exists())

            cache.mkdir(parents=True)  # already cached before: keep it
            with mock.patch.object(measure_stt, "measure", return_value={"model": "large-v3", "fits": False,
                                                                          "error": "RuntimeError: x"}), \
                 mock.patch("builtins.print"):
                self.assertEqual(measure_stt.main([]), 2)
            self.assertTrue(cache.exists())

            with mock.patch.object(measure_stt, "measure", return_value={"model": "large-v3", "fits": True}), \
                 mock.patch("builtins.print") as printed:
                self.assertEqual(measure_stt.main(["--device", "cpu"]), 0)
            printed.assert_called_once_with("large-v3")


if __name__ == "__main__":
    unittest.main()
