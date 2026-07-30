"""Focused v0.7.10 speaker-loop and vision-isolation contract checks."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "python"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class VoiceLoopAndVisionIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.client = (ROOT / "bx1_robot_client.py").read_text(encoding="utf-8")
        cls.brain = (REPO / "Brain" / "main_pyqt.py").read_text(encoding="utf-8")
        ast.parse(cls.body)
        ast.parse(cls.client)
        ast.parse(cls.brain)

    def test_playback_generation_invalidates_queued_or_inflight_capture(self) -> None:
        self.assertIn("self.speaker_playback_generation += 1", self.body)
        self.assertIn('payload["_playback_generation"]', self.body)
        self.assertIn('captured_generation != int(suppression.get("playback_generation", 0))', self.body)
        self.assertIn("self.voice_stt_queue.get_nowait()", self.body)

    def test_rearm_requires_echo_tail_and_quiet_live_capture_dwell(self) -> None:
        self.assertIn("def _observe_speaker_rearm", self.body)
        self.assertIn("speaker_rearm_quiet_since_mono", self.body)
        self.assertIn('self.set_voice_runtime("listening", "Ready for wake."', self.body)
        self.assertIn('"quiet_dwell_remaining_s"', self.body)

    def test_normal_chat_explicitly_disables_vision_context(self) -> None:
        self.assertIn('"vision_context": False', self.client)
        self.assertIn("vision_requested = self.is_vision_request(text)", self.body)
        self.assertIn("image_b64 and not explicit_vision", self.brain)
        self.assertIn('"vision_context": "on" if has_image else "off"', self.brain)

    def test_explicit_vision_route_keeps_supported_image_path(self) -> None:
        self.assertIn('"vision_context": True', self.client)
        self.assertIn('body["vision_context"] = True', self.brain)
        self.assertIn("if not has_image:", self.brain)


if __name__ == "__main__":
    unittest.main()
