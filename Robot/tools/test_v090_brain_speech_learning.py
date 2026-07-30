import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "python/bx1_management/static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "python/bx1_management/static/styles.css").read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT.parent / "Brain"))

from main import apply_speech_corrections


class SpeechLearningBrainTests(unittest.TestCase):
    def test_phrase_correction_preserves_raw_and_boundaries(self):
        result = apply_speech_corrections("make a base motor and baseboard", [{"id": "makerbase", "recognised": "make a base", "canonical": "Makerbase", "enabled": True}])
        self.assertEqual(result["raw_text"], "make a base motor and baseboard")
        self.assertEqual(result["corrected_text"], "Makerbase motor and baseboard")
        self.assertEqual(result["applied_corrections"][0]["id"], "makerbase")

    def test_disabled_and_speaker_rules_are_omitted(self):
        result = apply_speech_corrections("make a base", [{"recognised": "make a base", "canonical": "Makerbase", "enabled": False}, {"recognised": "base", "canonical": "BASE", "speaker_id": "john"}], "visitor")
        self.assertEqual(result["corrected_text"], "make a base")
        self.assertFalse(result["applied_corrections"])

    def test_ui_ownership_and_overflow_safety(self):
        self.assertNotIn("${canonicalQuick()}", APP)
        for marker in ("max-width:100%", "overflow-wrap:anywhere", "minmax(min(100%,150px),1fr)", "json-viewer", "chat-input-row"):
            self.assertIn(marker, CSS)
        self.assertEqual(APP.count('function canonicalConversation'), 1)


if __name__ == "__main__":
    unittest.main()
