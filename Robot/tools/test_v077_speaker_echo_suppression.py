"""Focused v0.7.7 playback suppression and settings checks."""
from __future__ import annotations

import sys
import tempfile
import threading
import queue
from collections import deque
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(ROOT))
import main  # noqa: E402


class SpeakerSuppressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = main.BX1RobotBodyService.__new__(main.BX1RobotBodyService)
        self.service.cfg = {"speaker_echo_tail_ms": 1500, "voice_enabled": True}
        self.service.speaker_playback_lock = threading.Lock()
        self.service.speaker_playback_active = False
        self.service.speaker_playback_started_mono = 0.0
        self.service.speaker_echo_tail_until_mono = 0.0
        self.service.speaker_playback_generation = 0
        self.service.speaker_rearm_required = False
        self.service.speaker_rearm_quiet_since_mono = 0.0
        self.service.speaker_playback_started_at = ""
        self.service.speaker_playback_finished_at = ""
        self.service.discarded_speaker_frames_total = 0
        self.service.cleared_pre_roll_frames_total = 0
        self.service.voice_stt_queue = queue.Queue(maxsize=1)
        self.service.speaker_gate = main.SpeakerActiveMicrophoneGate(echo_tail_ms=1500)
        self.events = []
        self.service.set_voice_runtime = lambda state, label="", **updates: self.events.append((state, label, updates))
        self.service.get_voice_runtime_snapshot = lambda: {"loop_active": True}
        self.service.recent_robot_speech = deque()
        self.service._normalise_spoken_text = lambda text: " ".join(str(text).lower().split())

    def test_actual_playback_then_tail_transitions(self) -> None:
        with patch.object(main.time, "monotonic", side_effect=[10.0, 10.0, 12.0, 12.2, 12.2, 12.2, 12.2, 12.2]):
            self.service._speaker_playback_started()
            self.assertTrue(self.service.speaker_suppression_snapshot()["playback_active"])
            self.service._speaker_playback_finished()
            tail = self.service.speaker_suppression_snapshot()
        self.assertFalse(tail["playback_active"])
        self.assertGreater(tail["echo_tail_remaining_s"], 1.0)
        self.assertEqual([item[0] for item in self.events], ["speaking", "echo_suppressed"])

    def test_tail_is_bounded(self) -> None:
        self.service.cfg["speaker_echo_tail_ms"] = 99999
        self.assertEqual(self.service._speaker_echo_tail_s(), 5.0)
        self.service.cfg["speaker_echo_tail_ms"] = 1
        self.assertEqual(self.service._speaker_echo_tail_s(), 0.25)

    def test_voice_settings_allow_only_echo_tail_range(self) -> None:
        self.service.cfg.update({"wake_words": ["hello"], "wake_command_window_s": 12.0, "stt_end_silence_ms": 600,
                                 "mic_noise_gate_dbfs": -45.0, "stt_noise_margin_db": 6.0, "stt_adaptive_margin_db": 4.0,
                                 "stt_transcription_backend": "brain_faster_whisper"})
        self.service.get_wake_words = lambda: list(self.service.cfg["wake_words"])
        self.service._refresh_mic_monitor_settings = lambda: None
        self.service.save_config_file = lambda: None
        self.assertFalse(self.service.web_update_bx1_voice_settings({"settings": {"speaker_echo_tail_ms": 10}})["ok"])
        result = self.service.web_update_bx1_voice_settings({"settings": {"speaker_echo_tail_ms": 1750}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["effective"]["speaker_echo_tail_ms"], 1750)

    def test_suppressed_result_never_reaches_brain_submission(self) -> None:
        submitted = []
        self.service.speaker_suppression_snapshot = lambda: {"suppressed": True, "playback_active": True, "echo_tail_remaining_s": 0.0}
        self.service.handle_user_text = lambda *args, **kwargs: submitted.append(args)
        self.service._process_voice_worker_result({"accepted": True, "text": "hello leo", "confidence": 0.9})
        self.assertEqual(submitted, [])
        self.assertEqual(self.events[-1][0], "echo_suppressed")

    def test_per_frame_guard_blocks_playback_and_tail_frames(self) -> None:
        self.service._speaker_playback_started()
        self.assertTrue(self.service.production_microphone_frame_guard(b"speaker"))
        self.service._speaker_playback_finished()
        self.assertTrue(self.service.production_microphone_frame_guard(b"tail"))

    def test_near_verbatim_tts_copy_is_rejected_with_minor_stt_errors(self) -> None:
        self.service.recent_robot_speech.append((0.0, "Hey there I was wondering about the battery level today"))
        with patch.object(main.time, "monotonic", return_value=10.0):
            rejected, score = self.service.is_likely_tts_echo("hey there i was wonderin about the battery level today")
        self.assertTrue(rejected)
        self.assertGreaterEqual(score, 0.78)

    def test_idle_life_playback_suppression_never_submits_its_audio(self) -> None:
        submitted = []
        self.service.speaker_suppression_snapshot = lambda: {"suppressed": True, "playback_active": False, "echo_tail_remaining_s": 1.2}
        self.service.handle_user_text = lambda *args, **kwargs: submitted.append((args, kwargs))
        self.service._process_voice_worker_result({"accepted": True, "text": "leo's idle comment", "confidence": 0.98})
        self.assertEqual(submitted, [])
        self.assertEqual(self.events[-1][0], "echo_suppressed")

    def test_direct_body_file_playback_uses_the_authoritative_lifecycle(self) -> None:
        lifecycle = []
        self.service.handle_mouth_audio_event = lambda event, info: lifecycle.append((event, info["tag"]))
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio_file, patch.object(main, "play_audio_file", return_value={"ok": True}) as play:
            result = self.service.play_body_audio_file(audio_file.name, tag="idle-local", backend="local-cue")
        self.assertTrue(result["ok"])
        self.assertEqual(lifecycle, [("speech_audio_file_start", "idle-local"), ("speech_audio_file_stop", "idle-local")])
        play.assert_called_once()


if __name__ == "__main__":
    unittest.main()
