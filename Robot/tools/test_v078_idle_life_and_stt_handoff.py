"""Focused v0.7.8 idle-life and primary-STT route contract checks."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRAIN_MAIN = ROOT / "Brain" / "main_pyqt.py"
BODY_MAIN = ROOT / "Robot" / "python" / "main.py"
OS_APP = ROOT / "Robot" / "python" / "bx1_management" / "static" / "app.js"
KIOSK = ROOT / "Robot" / "tools" / "bx1_touchscreen_kiosk.sh"
TOUCH_UNIT = ROOT / "Robot" / "service" / "bx1-touchscreen.service"


class IdleLifeAndSttContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.brain_source = BRAIN_MAIN.read_text(encoding="utf-8")
        cls.body_source = BODY_MAIN.read_text(encoding="utf-8")
        cls.app_source = OS_APP.read_text(encoding="utf-8")
        cls.kiosk_source = KIOSK.read_text(encoding="utf-8")
        cls.unit_source = TOUCH_UNIT.read_text(encoding="utf-8")
        ast.parse(cls.brain_source)
        ast.parse(cls.body_source)

    def test_idle_life_uses_a_local_personality_route_without_tools_or_rag(self) -> None:
        self.assertIn("def _idle_life_system_prompt", self.brain_source)
        self.assertIn("if fast_voice_mode or idle_life_request:", self.brain_source)
        self.assertIn('"route": "idle_local" if idle_life_request else "none"', self.brain_source)
        self.assertIn("Never claim a lookup failed or tools were disabled.", self.brain_source)

    def test_idle_life_model_failure_is_silent_not_a_tool_error_reply(self) -> None:
        self.assertIn("def _idle_life_silent_response", self.brain_source)
        self.assertIn('"idle_silent": True', self.brain_source)
        self.assertIn('if bool(result.get("idle_silent")):', self.body_source)

    def test_primary_faster_whisper_remains_preferred_and_vosk_is_labelled_fallback(self) -> None:
        self.assertIn('"transcription_backend": "brain_faster_whisper"', self.body_source)
        self.assertIn('backend_name: str = "local_vosk_fallback"', self.body_source)
        self.assertIn('timeout_s=max(2, min(20, int(self.cfg.get("brain_stt_timeout_s", 12)', self.body_source)

    def test_primary_handoff_exposes_metadata_not_wav_bytes(self) -> None:
        self.assertIn('"schema": "bx1.body.primary_stt_handoff.v1"', self.body_source)
        self.assertIn('rate == 16000 and channels == 1 and width == 2', self.body_source)
        self.assertIn('result.pop("_submitted_wav_bytes", b"")', self.body_source)

    def test_dashboard_has_summary_not_shared_transcript(self) -> None:
        dashboard = self.app_source.split("function dashboardPage", 1)[1].split("function liveVoiceMarkup", 1)[0]
        self.assertIn('data-live-voice="dashboard"', dashboard)
        self.assertNotIn("data-shared-voice", dashboard)
        self.assertIn("Open Live Voice", self.app_source)

    def test_kiosk_waits_for_status_and_restarts_browser(self) -> None:
        self.assertIn("BX1_TOUCH_STATUS_URL", self.kiosk_source)
        self.assertIn('curl --fail --silent --max-time 2 "$BX1_TOUCH_STATUS_URL"', self.kiosk_source)
        self.assertIn("Restart=always", self.unit_source)


if __name__ == "__main__":
    unittest.main()
