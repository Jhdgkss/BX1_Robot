import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "python/bx1_management/static/app.js").read_text(encoding="utf-8")
HTML = (ROOT / "python/bx1_management/static/index.html").read_text(encoding="utf-8")
CSS = (ROOT / "python/bx1_management/static/styles.css").read_text(encoding="utf-8")
SERVER = (ROOT / "python/bx1_management/server.py").read_text(encoding="utf-8")


class ManagementUiTests(unittest.TestCase):
    def test_management_version_is_owned_by_8089(self):
        self.assertIn('version: "0.8.0-voice-controls"', APP)
        self.assertIn('RELEASE_VERSION = "0.8.0-voice-controls"', SERVER)
        self.assertNotIn('version: deployment.version || "0.5.0"', APP)

    def test_dashboard_has_real_operational_sections(self):
        for marker in ("operationalVoiceStatus", "Live Speech Recognition", "operationalConversation", "speech-scan-rendered"):
            self.assertIn(marker, APP)
        for marker in ("Mute Microphone", "Pause Listening", "Push to Talk", "Mute Speaker", "Stop Speaking"):
            self.assertIn(marker, HTML)
        self.assertIn("global-audio-controls", CSS)

    def test_navigation_themes_documentation_and_live_diagnostics(self):
        self.assertIn('id: "themes"', APP); self.assertIn('id: "documentation"', APP)
        self.assertIn('function themesPage', APP); self.assertIn('function documentationPage', APP)
        self.assertIn('function voiceConsolePage', APP); self.assertIn('Download diagnostic package', APP)

    def test_transcript_ranges_are_rendered_structurally(self):
        self.assertIn("spans.map", APP); self.assertIn("slice(Number(s.start), Number(s.end))", APP)
        self.assertIn("/api/audio/speech-scan", APP); self.assertIn("body_speech_scan", SERVER)


if __name__ == "__main__": unittest.main()
