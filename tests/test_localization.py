import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
from openclaw_client import OpenClawClient  # noqa: E402


STRING_KEY = re.compile(r'^\s*"((?:\\.|[^"])*)"\s*=', re.MULTILINE)


class AppleLocalizationTests(unittest.TestCase):
    def _keys(self, path: Path) -> set[str]:
        return set(STRING_KEY.findall(path.read_text(encoding="utf-8")))

    def test_english_and_turkish_string_catalogs_have_matching_keys(self) -> None:
        for target in ("apple-watch", "ios-bridge", "apple-watch-widget"):
            with self.subTest(target=target):
                english = self._keys(ROOT / target / "en.lproj" / "Localizable.strings")
                turkish = self._keys(ROOT / target / "tr.lproj" / "Localizable.strings")
                self.assertEqual(english, turkish)

    def test_permission_copy_defaults_to_english_and_has_turkish_override(self) -> None:
        for target in ("apple-watch", "ios-bridge"):
            with self.subTest(target=target):
                info = (ROOT / target / "Info.plist").read_text(encoding="utf-8")
                localized = ROOT / target / "tr.lproj" / "InfoPlist.strings"
                self.assertNotRegex(info, r"[çğıöşüÇĞİÖŞÜ]")
                self.assertTrue(localized.exists())
                self.assertRegex(localized.read_text(encoding="utf-8"), r"[çğıöşüÇĞİÖŞÜ]")


class BackendLocalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OpenClawClient(runtime_dir=tempfile.mkdtemp())

    def test_prompt_does_not_force_turkish_for_english_locale(self) -> None:
        prompt = self.client._build_prompt({"locale": "en-US", "transcript": "check the build"})
        self.assertIn("Write every part of your answer in English", prompt)
        self.assertNotIn("doğal Türkçe rapor", prompt)

    def test_english_processing_and_failure_fallbacks_contain_no_turkish(self) -> None:
        processing = main.build_processing_summary("local-whisper:cpu", "check the build", locale="en-US")
        failed = main.build_job_watch_summary({
            "locale": "en-US",
            "status": "failed",
            "watch_summary": "",
            "stt_error": "",
        })
        self.assertEqual(processing, 'Transcript received: "check the build". Processing.')
        self.assertEqual(failed, "The job could not be completed. Details are available on iPhone.")

    def test_turkish_processing_copy_is_preserved(self) -> None:
        processing = main.build_processing_summary("local-whisper:cpu", "build durumunu kontrol et", locale="tr-TR")
        self.assertIn("Transkript alındı", processing)
        self.assertIn("İşleniyor", processing)

    def test_report_section_titles_follow_job_locale(self) -> None:
        base = {
            "name": "Build check",
            "status": "completed",
            "elapsed_seconds": 2,
            "category": "Build",
            "watch_summary": "Build passed.",
            "phone_report": "All checks passed.",
            "next_action": None,
            "canned_result": "",
        }
        english = main.build_report_sections({**base, "locale": "en-US"})
        turkish = main.build_report_sections({**base, "locale": "tr-TR"})
        self.assertEqual(english[0]["title"], "Watch summary")
        self.assertEqual(turkish[0]["title"], "Saat özeti")


if __name__ == "__main__":
    unittest.main()
