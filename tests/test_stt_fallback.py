import sys
import types
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import local_whisper  # noqa: E402
from stt import WatchSTT  # noqa: E402

# 11 October, WSL had lost GPU access: the loaded CUDA model failed on every call.
DEAD_CONTEXT = "CUDA failed with error CUDA driver version is insufficient for CUDA runtime version"


class FakeWhisperModel:
    """faster_whisper.WhisperModel stand-in: the warm-up always works, real audio follows `fail_on`."""

    created: list = []
    fail_on: set = set()

    def __init__(self, size, device, compute_type):
        self.device = device
        FakeWhisperModel.created.append(device)

    def transcribe(self, audio, **kwargs):
        if isinstance(audio, str) and self.device in FakeWhisperModel.fail_on:
            def failing():
                raise RuntimeError(DEAD_CONTEXT)
                yield  # segments are lazy; the error surfaces while iterating
            return failing(), None
        segment = types.SimpleNamespace(text=f" metin {self.device} ")
        return iter([segment] if isinstance(audio, str) else []), None


class CudaFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeWhisperModel.created = []
        FakeWhisperModel.fail_on = set()
        fake_modules = {
            "faster_whisper": types.SimpleNamespace(WhisperModel=FakeWhisperModel),
            "numpy": types.SimpleNamespace(zeros=lambda n, dtype=None: [0.0] * n, float32="float32"),
        }
        for patcher in (
            mock.patch.dict(sys.modules, fake_modules),
            mock.patch.dict("os.environ", {"WATCH_CEVIZ_WHISPER_DEVICE": "auto", "WATCH_CEVIZ_WHISPER_MODEL": "tiny"}),
            mock.patch.multiple(local_whisper, _model=None, _model_key=None, _active_device="none", _cuda_failed=False,
                                _extra_models={}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_dead_cuda_context_retries_the_same_audio_on_cpu_and_stays_there(self) -> None:
        self.assertEqual(local_whisper.warmup(), "cuda")
        FakeWhisperModel.fail_on = {"cuda"}
        with self.assertLogs("watch_ceviz.local_whisper", "ERROR") as logs:
            self.assertEqual(local_whisper.transcribe_bytes(b"audio", "m4a", "tr"), "metin cpu")
        self.assertIn(DEAD_CONTEXT, logs.output[0])
        self.assertEqual(local_whisper.active_device(), "cpu")
        # Later calls go straight to the CPU model; CUDA is not tried again before a restart.
        self.assertEqual(local_whisper.transcribe_bytes(b"audio", "m4a", "tr"), "metin cpu")
        self.assertEqual(FakeWhisperModel.created, ["cuda", "cpu"])

    def test_a_cpu_failure_is_raised_to_the_caller(self) -> None:
        local_whisper.warmup()
        FakeWhisperModel.fail_on = {"cuda", "cpu"}
        with self.assertLogs("watch_ceviz.local_whisper", "ERROR"):
            with self.assertRaisesRegex(RuntimeError, "CUDA failed"):
                local_whisper.transcribe_bytes(b"audio", "m4a", "tr")

    def test_a_comparison_model_stays_loaded_beside_the_service_model_until_it_fails(self) -> None:
        local_whisper.warmup()
        self.assertEqual(local_whisper.transcribe_bytes_with("large-v3-turbo", b"audio", "m4a", "tr"), ("metin cuda", "cuda"))
        self.assertEqual(local_whisper.transcribe_bytes_with("large-v3-turbo", b"audio", "m4a", "tr"), ("metin cuda", "cuda"))
        self.assertEqual(FakeWhisperModel.created, ["cuda", "cuda"])  # the service model, then one comparison model
        FakeWhisperModel.fail_on = {"cuda"}
        with self.assertRaisesRegex(RuntimeError, "CUDA failed"):
            local_whisper.transcribe_bytes_with("large-v3-turbo", b"audio", "m4a", "tr")
        self.assertNotIn("large-v3-turbo", local_whisper._extra_models)  # the next capture loads it again
        self.assertIsNotNone(local_whisper._model)  # the service's own model is untouched

    def test_a_cuda_start_failure_is_logged_before_falling_back(self) -> None:
        def broken_cuda(size, device, compute_type):
            if device == "cuda":
                raise RuntimeError(DEAD_CONTEXT)
            return FakeWhisperModel(size, device, compute_type)

        sys.modules["faster_whisper"] = types.SimpleNamespace(WhisperModel=broken_cuda)
        with self.assertLogs("watch_ceviz.local_whisper", "WARNING") as logs:
            self.assertEqual(local_whisper.warmup(), "cpu")
        self.assertIn("could not start on cuda", logs.output[0])
        self.assertIn(DEAD_CONTEXT, logs.output[0])


class WatchSTTErrorTests(unittest.TestCase):
    PAYLOAD = {"audio_data": "YXVkaW8=", "format": "m4a", "locale": "tr-TR"}

    def _stt(self, engine: str) -> WatchSTT:
        with mock.patch.dict("os.environ", {"WATCH_CEVIZ_STT_ENGINE": engine, "OPENAI_API_KEY": ""}):
            return WatchSTT()

    def test_auto_mode_logs_and_reports_the_local_error(self) -> None:
        with mock.patch.object(local_whisper, "is_available", return_value=True), \
             mock.patch.object(local_whisper, "transcribe_bytes", side_effect=RuntimeError(DEAD_CONTEXT)), \
             self.assertLogs("watch_ceviz.stt", "WARNING") as logs:
            result = self._stt("auto").transcribe_watch_payload(self.PAYLOAD)
        self.assertEqual(result.transcript, "")
        self.assertIn("lokal whisper hatası", result.error)
        self.assertIn(DEAD_CONTEXT, result.error)
        self.assertIn(DEAD_CONTEXT, logs.output[0])

    def test_local_mode_reports_the_error_as_before(self) -> None:
        with mock.patch.object(local_whisper, "is_available", return_value=True), \
             mock.patch.object(local_whisper, "transcribe_bytes", side_effect=RuntimeError(DEAD_CONTEXT)), \
             self.assertLogs("watch_ceviz.stt", "WARNING"):
            result = self._stt("local").transcribe_watch_payload(self.PAYLOAD)
        self.assertEqual(result.error, f"local whisper hatası: {DEAD_CONTEXT}")

    def test_silence_without_a_key_keeps_the_no_transcript_message(self) -> None:
        with mock.patch.object(local_whisper, "is_available", return_value=True), \
             mock.patch.object(local_whisper, "transcribe_bytes", return_value=""):
            result = self._stt("auto").transcribe_watch_payload(self.PAYLOAD)
        self.assertEqual(result.error, "STT yok: lokal whisper transkript üretemedi ve OPENAI_API_KEY tanımlı değil")

    def test_phone_mode_uses_the_phone_text_and_never_loads_whisper(self) -> None:
        stt = self._stt("phone")
        with mock.patch.object(local_whisper, "transcribe_bytes", side_effect=AssertionError("no Whisper")):
            heard = stt.transcribe_watch_payload({**self.PAYLOAD, "transcript": "notları aç",
                                                  "transcript_source": "speech-transcriber"})
            self.assertEqual((heard.transcript, heard.source), ("notları aç", "iphone:speech-transcriber"))
            missing = stt.transcribe_watch_payload({**self.PAYLOAD, "transcript_error": "Türkçe modeli indirilmedi"})
            self.assertEqual(missing.error, "Bu bilgisayarda konuşmayı iPhone çözüyor ama metin gelmedi: "
                                            "Türkçe modeli indirilmedi")
            old_app = stt.transcribe_watch_payload({**self.PAYLOAD, "locale": "en-US"})
            self.assertIn("update the Ceviz iPhone app", old_app.error)
            # 23 October, live: the current app heard nothing and sent an empty reason; that is not an old app.
            nothing = stt.transcribe_watch_payload({**self.PAYLOAD, "transcript_error": ""})
            self.assertEqual(nothing.error, "Bu bilgisayarda konuşmayı iPhone çözüyor ama metin gelmedi: "
                                            "iPhone kayıtta söz duymadı")
            self.assertNotIn("update", stt.transcribe_watch_payload(
                {**self.PAYLOAD, "locale": "en-US", "transcript_error": " "}).error)

    def test_comparison_whisper_and_hints_for_the_phone(self) -> None:
        with mock.patch.dict("os.environ", {"WATCH_CEVIZ_STT_COMPARE": "whisper",
                                            "WATCH_CEVIZ_WHISPER_HOTWORDS": "RustDesk, Ceviz ,, OpenClaw"}):
            self.assertTrue(self._stt("phone").compare_with_whisper)
            self.assertFalse(self._stt("auto").compare_with_whisper)  # only beside the phone's text
            self.assertEqual(WatchSTT.speech_hints(), ["RustDesk", "Ceviz", "OpenClaw"])
        stt = self._stt("phone")
        with mock.patch.object(local_whisper, "transcribe_bytes", return_value=" RustDesk'e bağlan ") as whisper, \
             mock.patch.object(local_whisper, "active_device", return_value="cuda"):
            heard = stt.whisper_transcript(self.PAYLOAD)
        self.assertEqual((heard["engine"], heard["transcript"]), ("local-whisper:cuda", "RustDesk'e bağlan"))
        self.assertEqual(whisper.call_args.args[1:], ("m4a", "tr"))
        with mock.patch.object(local_whisper, "transcribe_bytes", side_effect=RuntimeError(DEAD_CONTEXT)), \
             self.assertLogs("watch_ceviz.stt", "WARNING"):
            self.assertIn(DEAD_CONTEXT, stt.whisper_transcript(self.PAYLOAD)["error"])

    def test_comparison_engines_include_other_whisper_models_but_never_paths(self) -> None:
        setting = "whisper:large-v3-turbo, Whisper, whisper:../models/x, whisper:--device, whisper:org/model-ct2, whisper"
        with mock.patch.dict("os.environ", {"WATCH_CEVIZ_STT_COMPARE": setting}):
            self.assertEqual(self._stt("phone").compare_engines,
                             ["whisper:large-v3-turbo", "whisper", "whisper:org/model-ct2"])
            self.assertEqual(self._stt("auto").compare_engines, [])
        stt = self._stt("phone")
        with mock.patch.object(local_whisper, "transcribe_bytes_with", return_value=(" IMAP'i aç ", "cuda")) as other:
            heard = stt.whisper_transcript(self.PAYLOAD, "whisper:large-v3-turbo")
        self.assertEqual((heard["engine"], heard["transcript"]), ("local-whisper:large-v3-turbo:cuda", "IMAP'i aç"))
        self.assertEqual(other.call_args.args[0], "large-v3-turbo")
        with mock.patch.object(local_whisper, "transcribe_bytes_with", side_effect=RuntimeError("no model")), \
             self.assertLogs("watch_ceviz.stt", "WARNING"):
            failed = stt.whisper_transcript(self.PAYLOAD, "whisper:large-v3-turbo")
        self.assertEqual(failed["engine"], "local-whisper:large-v3-turbo")


if __name__ == "__main__":
    unittest.main()
