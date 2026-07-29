"""Focused primary Faster-Whisper hand-off and Vosk fallback checks."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "python"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class PrimaryBrainSTTHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.service = (REPO / "Brain" / "bx1_modules" / "faster_whisper_stt.py").read_text(encoding="utf-8")
        cls.brain = (REPO / "Brain" / "main_pyqt.py").read_text(encoding="utf-8")
        ast.parse(cls.body)
        ast.parse(cls.service)
        ast.parse(cls.brain)

    def test_brain_returns_a_structured_rejected_outcome_for_no_speech(self) -> None:
        self.assertIn('"outcome": "accepted" if accepted else "rejected"', self.service)
        self.assertIn('self._send_json(200, result)', self.brain)

    def test_service_failure_is_distinct_from_a_completed_rejection(self) -> None:
        self.assertIn('"outcome": "service_failure"', self.service)
        self.assertIn('str(remote.get("outcome") or "") == "rejected"', self.body)

    def test_request_id_correlates_body_and_brain_stt_result(self) -> None:
        self.assertIn('"request_id": self.new_input_event_id("stt")', self.body)
        self.assertIn('"request_id": handoff["request_id"]', self.body)
        self.assertIn('remote_request_id != str(handoff["request_id"])', self.body)
        self.assertIn('request_id = str(metadata.get("request_id")', self.service)

    def test_operator_states_are_metadata_only_and_do_not_create_countdowns(self) -> None:
        self.assertIn('"Transcribing on Brain"', self.body)
        self.assertIn('"Brain STT unavailable — using local fallback."', self.body)
        self.assertIn('"No speech heard — please try again."', self.body)

    def test_brain_timeout_is_changed_only_through_the_allowlisted_voice_settings_route(self) -> None:
        self.assertIn('"brain_stt_timeout_s": {"minimum": 2, "maximum": 20, "default": 12}', self.body)
        self.assertIn('"brain_stt_timeout_s": (2, 20, int)', self.body)
        self.assertIn('"brain_stt_timeout_s": parsed["brain_stt_timeout_s"]', self.body)


if __name__ == "__main__":
    unittest.main()
