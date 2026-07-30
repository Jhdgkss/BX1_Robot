import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from voice_pipeline import SpeakerActiveMicrophoneGate, extract_request, highlight_segments


class VoiceControlTests(unittest.TestCase):
    def test_gate_discards_during_playback_and_tail_then_reopens(self):
        events = []
        gate = SpeakerActiveMicrophoneGate(echo_tail_ms=250, event=lambda n, d: events.append(n))
        gate.start(); self.assertTrue(gate.discard_frame(b"abc")); gate.finish()
        self.assertTrue(gate.discard_frame(b"x")); time.sleep(.27)
        self.assertFalse(gate.discard_frame(b"ok")); gate.flush(); gate.open()
        self.assertIn("speaker_started", events); self.assertIn("microphone_gate_closed", events)
        self.assertIn("echo_tail_started", events); self.assertIn("microphone_buffer_flushed", events)

    def test_request_extraction_and_highlights(self):
        result = extract_request("I was talking, hey robot, check battery", ["hey robot"])
        self.assertEqual(result["request"], "check battery")
        kinds = [x["kind"] for x in highlight_segments(result["transcript"], result["wake_range"], result["request_range"])]
        self.assertIn("wake", kinds); self.assertIn("request", kinds)


if __name__ == "__main__": unittest.main()
