"""Focused v0.7.9 conversational flow and primary-STT contract checks."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "python"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class ConversationalVoiceFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.brain = (REPO / "Brain" / "main_pyqt.py").read_text(encoding="utf-8")
        cls.server = (ROOT / "bx1_management" / "server.py").read_text(encoding="utf-8")
        ast.parse(cls.body); ast.parse(cls.brain); ast.parse(cls.server)

    def test_legacy_wake_window_migrates_to_fifteen_seconds(self) -> None:
        self.assertIn('cfg["wake_command_window_s"] = 15.0 if existing_wake_window > 60.0', self.body)

    def test_brain_stt_evaluations_return_structured_http_success(self) -> None:
        self.assertIn('self._send_json(200, result)', self.brain)

    def test_console_keys_state_rows_without_countdown_spam(self) -> None:
        self.assertIn('state_key = str(audio.get("pipeline_state")', self.server)
        self.assertIn('self._last_state = state_key', self.server)

    def test_wake_chime_and_timeout_use_existing_suppression_lifecycle(self) -> None:
        self.assertIn('self.acknowledge_voice_event("wake")', self.body)
        self.assertIn('Listening — say your request now.', self.body)
        self.assertIn('I did not hear a request', self.body)

    def test_primary_handoff_and_fallback_reason_remain_metadata_only(self) -> None:
        self.assertIn('"primary_stt_handoff"', self.body)
        self.assertIn('result.pop("_submitted_wav_bytes", b"")', self.body)
        self.assertIn('"fallback_reason"', self.server)


if __name__ == "__main__":
    unittest.main()
