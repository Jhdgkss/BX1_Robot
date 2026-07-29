"""Focused BX1 OS v0.7.6 voice ownership checks."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(ROOT))
import main  # noqa: E402


class VoiceOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = main.BX1RobotBodyService.__new__(main.BX1RobotBodyService)
        self.service.cfg = {
            "wake_words": ["hello", "hey", "robot"], "wake_command_window_s": 12.0,
            "stt_end_silence_ms": 600, "mic_noise_gate_dbfs": -45.0,
            "stt_noise_margin_db": 6.0, "stt_adaptive_margin_db": 4.0,
            "stt_transcription_backend": "brain_faster_whisper", "unrelated": "preserved",
        }
        self.service.get_wake_words = lambda: list(self.service.cfg["wake_words"])
        self.service._refresh_mic_monitor_settings = lambda: None

    def test_allowlisted_settings_validate_and_atomically_save(self) -> None:
        old_path = main.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps({"unrelated": "preserved"}), encoding="utf-8")
            os.chmod(path, 0o640)
            main.CONFIG_PATH = path
            try:
                result = self.service.web_update_bx1_voice_settings({"settings": {
                    "wake_phrases": ["Hello Leo", "  hey robot "],
                    "wake_listen_timeout_s": 15, "speech_end_timeout_ms": 750,
                    "noise_gate_dbfs": -42, "noise_margin_db": 7,
                    "adaptive_margin_db": 5, "stt_policy": "vosk",
                }})
                self.assertTrue(result["ok"])
                self.assertEqual(result["effective"]["wake_phrases"], ["hello leo", "hey robot"])
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["wake_words"], ["hello leo", "hey robot"])
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["unrelated"], "preserved")
                if os.name != "nt":
                    self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            finally:
                main.CONFIG_PATH = old_path

    def test_rejects_arbitrary_or_invalid_settings(self) -> None:
        self.assertFalse(self.service.web_update_bx1_voice_settings({"settings": {"api_key": "no"}})["ok"])
        self.assertFalse(self.service.web_update_bx1_voice_settings({"settings": {"wake_phrases": []}})["ok"])
        self.assertFalse(self.service.web_update_bx1_voice_settings({"settings": {"speech_end_timeout_ms": 12}})["ok"])

    def test_single_pending_queue_drops_busy_utterance(self) -> None:
        self.service.voice_stt_queue = main.queue.Queue(maxsize=1)
        self.service.set_voice_runtime = lambda *args, **kwargs: None
        self.assertTrue(self.service._queue_voice_stt({"_submitted_wav_bytes": b"x"}))
        self.assertFalse(self.service._queue_voice_stt({"_submitted_wav_bytes": b"y"}))
        queued = self.service.voice_stt_queue.get_nowait()
        self.assertEqual(queued["_submitted_wav_bytes"], b"x")


if __name__ == "__main__":
    unittest.main()
