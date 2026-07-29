#!/usr/bin/env python3
"""Focused offline validation for BX1 OS v0.6 voice observer contracts."""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import tarfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from bx1_management.server import ManagementApplication, ManagementServer  # noqa: E402
from bx1_management.voice_vertical import VoiceTimeline, VoiceVerticalSlice  # noqa: E402
from build_voice_vertical_body_patch import FILES, build, production_patch_file_modes  # noqa: E402
from main import BX1RobotBodyService  # noqa: E402


def config() -> dict:
    return json.loads((ROOT / "python" / "config.alpha-qualification.json").read_text(encoding="utf-8"))


class VoiceTimelineTests(unittest.TestCase):
    def test_body_vertical_slice_disables_actions_camera_local_fallback_and_mouth_events(self):
        body = (ROOT / "python" / "main.py").read_text(encoding="utf-8")
        audio = (ROOT / "python" / "audio_io.py").read_text(encoding="utf-8")
        section = body[body.find("def web_voice_vertical_slice"):body.find("def get_identity_settings")]
        self.assertIn("allow_vision=False", section)
        self.assertIn("allow_actions=False", section)
        self.assertIn("_voice_vertical_slice_no_actuators = True", section)
        self.assertIn("privacy_mode=True", section)
        self.assertIn("fallback_on_failure=allow_actions", body)
        self.assertIn("emit_mouth_events=not privacy_mode", body)
        self.assertIn("on_playback_started=playback_started", body)
        self.assertIn("if emit_mouth_events:", audio)

    def test_event_is_versioned_and_redacts_private_fields(self):
        timeline = VoiceTimeline()
        event = timeline.record({
            "event": "SpeechRecognised", "session_id": "voice-abc", "text": "private speech",
            "transcript": "private speech", "audio_base64": "private", "reason": "accepted",
        })
        self.assertEqual(event["schema"], "bx1.voice.event.v1")
        self.assertEqual(event["metadata"], {"reason": "accepted"})
        self.assertNotIn("text", json.dumps(event))
        self.assertNotIn("transcript", json.dumps(event))

    def test_fault_clear_does_not_remove_timeline_evidence(self):
        timeline = VoiceTimeline()
        timeline.record({"event": "FaultRaised", "session_id": "voice-fault", "reason": "brain_offline"})
        cleared = timeline.clear_observer_faults()
        self.assertEqual(cleared["cleared"], 1)
        self.assertEqual(len(timeline.snapshot()["active_faults"]), 0)
        self.assertEqual(len(timeline.snapshot()["events"]), 1)

    def test_body_bridge_is_loopback_port_8088_only(self):
        timeline = VoiceTimeline()
        with self.assertRaises(ValueError):
            VoiceVerticalSlice(timeline, body_url="http://192.168.68.50:8088")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self, _limit):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class VoiceVerticalBridgeTests(unittest.TestCase):
    def test_endpoint_discovery_uses_nested_body_telemetry_and_redacts_host(self):
        bridge = VoiceVerticalSlice(VoiceTimeline())
        endpoint = bridge.update_brain_endpoint({
            "telemetry": {"value": {"network": {"brain_app_base_url": "http://192.168.68.53:8765"}}},
        })
        self.assertEqual(endpoint, "192.168.68.*:8765")

    def test_real_probe_uses_only_body_route_and_connected_state(self):
        calls = []

        def opener(req, timeout):
            calls.append((req.full_url, timeout, json.loads(req.data.decode("utf-8"))))
            return FakeResponse({"ok": True, "state": "connected", "reason": "brain_and_tts_ready"})

        bridge = VoiceVerticalSlice(VoiceTimeline(), opener=opener)
        outcome = bridge.brain_probe()
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["state"], "connected")
        self.assertEqual(calls, [("http://127.0.0.1:8088/api/voice/vertical-slice/probe", 5.0, {})])

    def test_probe_degraded_and_unavailable_states_are_redacted(self):
        bridge = VoiceVerticalSlice(VoiceTimeline(), opener=lambda *_args, **_kwargs: FakeResponse({
            "ok": False, "state": "degraded", "reason": "brain_tts_unavailable",
        }))
        self.assertEqual(bridge.brain_probe()["state"], "degraded")
        unavailable = VoiceVerticalSlice(VoiceTimeline(), opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.timeout()))
        self.assertEqual(unavailable.brain_probe()["reason"], "body_probe_unavailable")

    def test_typed_request_has_no_text_or_reply_retention(self):
        calls = []

        def opener(req, timeout):
            calls.append(json.loads(req.data.decode("utf-8")))
            return FakeResponse({"ok": True, "session_id": "ignored", "stage": "playback_pending", "reply": "PRIVATE_BRAIN_ANSWER"})

        timeline = VoiceTimeline()
        bridge = VoiceVerticalSlice(timeline, opener=opener)
        outcome = bridge.typed_test("private typed content")
        self.assertTrue(outcome["ok"])
        self.assertEqual(calls[0]["text"], "private typed content")  # in-flight Body relay only
        retained = json.dumps({"result": outcome, "timeline": timeline.snapshot()})
        self.assertNotIn("private typed content", retained)
        self.assertNotIn("PRIVATE_BRAIN_ANSWER", retained)

    def test_timeout_and_body_failure_stages_are_distinct(self):
        timed_out = VoiceVerticalSlice(VoiceTimeline(), opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.timeout()))
        self.assertEqual(timed_out.typed_test("question")["error"], "body_response_timeout")
        for failure in ("brain_chat_failed", "brain_tts_missing", "brain_tts_download_failed", "body_playback_failed"):
            bridge = VoiceVerticalSlice(VoiceTimeline(), opener=lambda *_args, **_kwargs: FakeResponse({
                "ok": False, "failure_stage": failure,
            }))
            outcome = bridge.typed_test("question")
            self.assertEqual(outcome["error"], failure)
            self.assertEqual(bridge.timeline.snapshot()["events"][-1]["metadata"]["reason"], failure)

    def test_missing_post_acceptance_observer_event_is_not_false_success(self):
        wall_clock = [100.0]
        bridge = VoiceVerticalSlice(
            VoiceTimeline(clock=lambda: wall_clock[0]),
            opener=lambda *_args, **_kwargs: FakeResponse({"ok": True}),
        )
        outcome = bridge.typed_test("question")
        bridge._accepted_sessions[outcome["session_id"]] = 0.0
        self.assertEqual(bridge.session_state(outcome["session_id"])["reason"], "observer_event_delay")

    def test_body_privacy_path_blocks_actions_and_local_tts_when_brain_tts_is_missing(self):
        body = object.__new__(BX1RobotBodyService)
        events = []
        body.metrics_lock = threading.RLock()
        body.performance = {}
        body.set_voice_runtime = lambda *_args, **_kwargs: None
        body.stop_active_thinking_cues = lambda *_args, **_kwargs: None
        body.emit_voice_observer_event = lambda event, _session, **meta: events.append({"event": event, **meta})
        body.execute_actions = lambda *_args, **_kwargs: self.fail("voice route must not execute Brain actions")
        body.tts = type("NoFallbackTTS", (), {"speak": lambda *_args, **_kwargs: self.fail("local TTS fallback must be disabled")})()
        outcome = body.handle_brain_result(
            {"ok": True, "speech": "PRIVATE_BRAIN_ANSWER"},
            original_message="private typed content",
            session_id="voice-body-test",
            allow_actions=False,
            privacy_mode=True,
        )
        self.assertEqual(outcome["error"], "brain_tts_missing")
        self.assertNotIn("PRIVATE_BRAIN_ANSWER", json.dumps(events))
        self.assertEqual(events[-1]["reason"], "brain_tts_missing")

    def test_body_playback_failure_is_classified_without_fallback_or_content_retention(self):
        body = object.__new__(BX1RobotBodyService)
        done = threading.Event()
        events = []
        case = self

        class Brain:
            def download_response_audio(self, _result):
                return "not-retained.wav"

        class TTS:
            def play_response_audio_file(self, _filename, text, **kwargs):
                case.assertEqual(text, "")
                case.assertFalse(kwargs["emit_mouth_events"])
                kwargs["on_playback_started"]()
                done.set()
                return {"ok": False, "error": "private player detail"}

            def speak(self, *_args, **_kwargs):
                case.fail("local TTS fallback must be disabled")

        body.brain = Brain()
        body.tts = TTS()
        body.emit_voice_observer_event = lambda event, _session, **meta: events.append({"event": event, **meta})
        body.web_log = lambda *_args, **_kwargs: case.fail("privacy path must not log content")
        self.assertTrue(body.play_brain_response_audio(
            {"audio": {"elapsed_sec": 0.1}, "speech": "PRIVATE_BRAIN_ANSWER"},
            "PRIVATE_BRAIN_ANSWER",
            session_id="voice-playback-test",
            fallback_on_failure=False,
            privacy_mode=True,
        ))
        self.assertTrue(done.wait(2.0))
        self.assertEqual(events[0]["event"], "SpeechStarted")
        self.assertEqual(events[-1], {"event": "FaultRaised", "reason": "body_playback_failed"})
        self.assertNotIn("PRIVATE_BRAIN_ANSWER", json.dumps(events))


class VoiceManagementApiTests(unittest.TestCase):
    def setUp(self):
        self.server = ManagementServer(ManagementApplication(config()), host="127.0.0.1", port=0)
        self.server.start()
        self.base = "http://127.0.0.1:%s" % self.server.port

    def tearDown(self):
        self.server.stop()

    def post(self, path, payload):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_metadata_event_and_redacted_export_are_available(self):
        status, payload = self.post("/api/voice/events", {
            "event": "BrainRequestSent", "session_id": "voice-api", "prompt": "must not persist", "stage": "chat",
        })
        self.assertEqual(status, 202)
        self.assertEqual(payload["event"]["metadata"], {"stage": "chat"})
        with urllib.request.urlopen(self.base + "/api/voice/diagnostics", timeout=3) as response:
            exported = json.loads(response.read().decode("utf-8"))
        self.assertEqual(exported["schema"], "bx1.voice.timeline.v1")
        self.assertNotIn("must not persist", json.dumps(exported))

    def test_connectivity_diagnostic_returns_state_not_a_framework_placeholder(self):
        self.server.application.voice.brain_probe = lambda: {
            "ok": False, "state": "degraded", "reason": "brain_tts_unavailable", "endpoint": "192.168.68.*:8765",
        }
        status, payload = self.post("/api/voice/brain-test", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "degraded")
        self.assertNotIn("framework", json.dumps(payload).lower())

    def test_talk_ui_keeps_content_browser_only_and_blocks_hardware_actions(self):
        app = (ROOT / "python" / "bx1_management" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Talk to Leo", app)
        self.assertIn("maxlength=\"1000\"", app)
        self.assertIn("event.ctrlKey || event.metaKey", app)
        self.assertIn("/api/voice/typed-test", app)
        for phase in ("Ready", "Sending to Brain", "Leo is thinking", "Playing reply", "Complete", "Failed"):
            self.assertIn(phase, app)
        self.assertNotIn("payload.reply", app)
        self.assertNotIn("state.talk.text", app)


class BodyPatchPackageTests(unittest.TestCase):
    def test_body_patch_contains_only_the_voice_observer_files_with_production_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive, _, manifest = build(ROOT.parent, Path(temporary), "20260728_230000")
            self.assertEqual([item["path"] for item in manifest["files"]], list(FILES))
            self.assertTrue(manifest["machine_local_config_merge_required"])
            self.assertEqual(
                manifest["required_machine_local_config_keys"],
                ["brain_base_url", "voice_observer_url"],
            )
            expected_modes = production_patch_file_modes(ROOT.parent)
            with tarfile.open(archive, "r:gz") as bundle:
                self.assertEqual(sorted(bundle.getnames()), sorted(["body_patch_manifest.json", *FILES]))
                for relative in FILES:
                    self.assertEqual(
                        bundle.getmember(relative).mode,
                        expected_modes[relative],
                    )


if __name__ == "__main__":
    unittest.main()
