import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import local_whisper  # noqa: E402
from openclaw_client import OpenClawClient, redact_secrets  # noqa: E402


class SecretRedactionTests(unittest.TestCase):
    def test_masks_labeled_and_prefixed_secrets(self) -> None:
        # Shape of the 2026-09-22 leak: a gateway token written into the watch summary.
        leaked = "Token ile giriş yap: 0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a6978"
        self.assertEqual(redact_secrets(leaked), "Token ile giriş yap: [redacted]")
        self.assertEqual(redact_secrets("api_key=sk-ant-api03-abcDEF1234567890xyz"), "api_key=[redacted]")
        self.assertEqual(redact_secrets("Authorization: Bearer abcdef0123456789abcdef"),
                         "Authorization: Bearer [redacted]")
        self.assertEqual(redact_secrets("use ghp_0123456789abcdefABCDEF0123 now"), "use [redacted] now")

    def test_keeps_ordinary_text_and_commit_shas(self) -> None:
        for text in (
            "Commit 71cc1041e99251f3b21ec7d535f714ebb9a63bd2 fixed it.",
            "Parolanı Ayarlar > Güvenlik altında değiştirebilirsin.",
            "Token süresi doldu, yeniden giriş yap.",
            "password: hunter",
        ):
            self.assertEqual(redact_secrets(text), text)

    def test_extract_result_redacts_watch_and_phone_text(self) -> None:
        text = (
            "<watch_ceviz_phone_report>Gateway hazır. Token: a1b2c3d4e5f6a7b8c9d0e1f2</watch_ceviz_phone_report>"
            '<watch_ceviz_meta>{"watch_summary":"Token ile giriş yap: a1b2c3d4e5f6a7b8c9d0e1f2",'
            '"outcome":"done","requires_phone_handoff":true}</watch_ceviz_meta>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "result.log"
            log.write_text(json.dumps({"result": {"payloads": [{"text": text}]}}), encoding="utf-8")
            result = OpenClawClient(agent="cevizmain", runtime_dir=tmp).extract_result(str(log), locale="tr")
        for field in (result.watch_summary, result.phone_report, result.canned_result):
            self.assertNotIn("a1b2c3d4e5f6a7b8c9d0e1f2", field)
            self.assertIn("[redacted]", field)


class WhisperHotwordTests(unittest.TestCase):
    def test_default_hotwords_bias_proper_nouns_and_can_be_disabled(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            self.assertIn("Claude Code", local_whisper.hotwords())
        with mock.patch.dict("os.environ", {"WATCH_CEVIZ_WHISPER_HOTWORDS": ""}):
            self.assertIsNone(local_whisper.hotwords())

    def test_transcribe_passes_hotwords_to_whisper(self) -> None:
        segment = mock.Mock(text=" Claude Code'a iş devret ")
        model = mock.Mock()
        model.transcribe.return_value = ([segment], None)
        with mock.patch.object(local_whisper, "_load_model", return_value=model), \
             mock.patch.dict("os.environ", {"WATCH_CEVIZ_WHISPER_HOTWORDS": "Claude Code, Codex"}):
            self.assertEqual(local_whisper.transcribe_bytes(b"audio", "m4a", "tr"), "Claude Code'a iş devret")
        self.assertEqual(model.transcribe.call_args.kwargs["hotwords"], "Claude Code, Codex")


if __name__ == "__main__":
    unittest.main()
