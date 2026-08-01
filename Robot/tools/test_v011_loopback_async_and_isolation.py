"""Focused loopback async/isolation contract checks."""
from __future__ import annotations

import ast
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(ROOT))


class LoopbackAsyncIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.audio = (ROOT / "audio_io.py").read_text(encoding="utf-8")
        cls.app = (ROOT / "bx1_management" / "static" / "app.js").read_text(encoding="utf-8")
        cls.client = (ROOT / "bx1_robot_client.py").read_text(encoding="utf-8")
        ast.parse(cls.body)
        ast.parse(cls.audio)

    def test_loopback_start_returns_worker_and_capture_id(self) -> None:
        start = self.body.index("def web_loopback_test")
        worker = self.body.index("def _run_loopback_test")
        source = self.body[start:worker]
        self.assertIn('"state": "preparing"', source)
        self.assertIn('"capture_id": capture_id', source)
        self.assertIn('threading.Thread(target=self._run_loopback_test', source)
        self.assertIn('return {"ok": True, "state": "preparing"', source)

    def test_diagnostic_capture_has_raw_sink_but_no_production_guard(self) -> None:
        worker = self.body.index("def _run_loopback_test")
        source = self.body[worker:self.body.index("def web_loopback_action", worker)]
        self.assertIn("frame_sink=diagnostic_frame_sink", source)
        self.assertIn("diagnostic_frames_written", source)
        self.assertIn('"stage": "post_roll"', source)
        self.assertNotIn("frame_guard=self.production_microphone_frame_guard", source)

    def test_playback_timeout_uses_generated_duration_and_margin(self) -> None:
        worker = self.body[self.body.index("def _run_loopback_test"):self.body.index("def web_loopback_action")]
        self.assertIn("generated_audio_duration_s", worker)
        self.assertIn("float(duration) + 3.0", worker)
        self.assertIn("playback_completion_timeout", worker)

    def test_playback_completion_is_signalled_in_finally(self) -> None:
        worker = self.body[self.body.index("def _run_loopback_test"):self.body.index("def web_loopback_action")]
        self.assertIn("finally:", worker)
        self.assertIn("playback_ready.set()", worker)
        self.assertIn("playback_done.set()", worker)

    def test_diagnostic_capture_is_gated_from_production_without_discarding_frames(self) -> None:
        worker = self.body[self.body.index("def _run_loopback_test"):self.body.index("def web_loopback_action")]
        self.assertIn('"production_listening_gated": True', worker)
        self.assertIn('"diagnostic_capture_active": True', worker)
        self.assertIn('"diagnostic_frames_written"', worker)
        self.assertIn('frame_sink=diagnostic_frame_sink', worker)

    def test_timeout_keeps_capture_for_transcription_and_fast_whisper_rejection_is_distinct(self) -> None:
        worker = self.body[self.body.index("def _run_loopback_test"):self.body.index("def web_loopback_action")]
        self.assertIn("os.replace(part, target)", worker)
        self.assertIn('"stt_rejected"', worker)
        self.assertIn('"no_acoustic_return"', worker)
        self.assertIn('"no_output_signal"', worker)
        self.assertIn('"no_speech_detected"', worker)

    def test_fatal_playback_stops_capture_and_preserves_valid_wav(self) -> None:
        worker = self.body[self.body.index("def _run_loopback_test"):self.body.index("def web_loopback_action")]
        self.assertIn("preserve_capture_if_valid", worker)
        self.assertIn('capture_stop.set()', worker)
        self.assertIn('capture_done.wait(timeout=3.0)', worker)
        self.assertIn('"capture_preserved": capture_preserved', worker)

    def test_raw_stream_sink_writes_diagnostic_frames(self) -> None:
        self.assertIn("frame_sink: Optional[Callable[[bytes], None]] = None", self.audio)
        self.assertIn("frame_sink(bytes(block))", self.audio)
        self.assertIn("stop_event: Any = None", self.audio)

    def test_browser_polls_current_capture_id(self) -> None:
        self.assertIn("state.loopbackId=payload.capture_id", self.app)
        self.assertIn("/api/audio/loopback/status?capture_id=", self.app)

    def test_endpoint_resolver_is_local_first_and_non_replaying(self) -> None:
        self.assertIn("class EndpointResolver", self.client)
        self.assertIn("http://192.168.68.53:8765", self.client)
        self.assertIn("http://100.92.216.101:8765", self.client)
        self.assertIn("A failed POST is never replayed", self.client)

    def test_endpoint_resolver_falls_back_without_replaying_post(self) -> None:
        from bx1_robot_client import BX1BrainClient, BrainClientConfig

        class Response:
            status_code = 200
            text = '{"ok":true}'
            def json(self): return {"ok": True}

        calls = []
        def get(url, **kwargs):
            calls.append(("GET", url))
            if "192.168.68.53" in url:
                raise OSError("local down")
            return Response()
        def post(url, **kwargs):
            calls.append(("POST", url))
            return Response()
        with mock.patch("bx1_robot_client.requests.get", side_effect=get), mock.patch("bx1_robot_client.requests.post", side_effect=post):
            client = BX1BrainClient(BrainClientConfig(base_url="http://192.168.68.53:8765"))
            result = client.chat("body", "hello", return_audio=False)
        self.assertTrue(result["ok"])
        self.assertEqual(sum(1 for method, _ in calls if method == "POST"), 1)
        self.assertIn("100.92.216.101", client.base_url)

    def test_loopback_worker_releases_authoritative_lock(self) -> None:
        worker = self.body[self.body.index("def _run_loopback_test"):self.body.index("def web_loopback_action")]
        self.assertIn("finally:", worker)
        self.assertIn('self.loopback_session.update({"running": False, "worker": None})', worker)
        self.assertIn("capture_stop.set()", worker)


if __name__ == "__main__":
    unittest.main()
