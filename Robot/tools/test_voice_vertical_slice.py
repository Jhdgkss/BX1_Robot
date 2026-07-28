#!/usr/bin/env python3
"""Focused offline validation for BX1 OS v0.6 voice observer contracts."""
from __future__ import annotations

import json
import sys
import tempfile
import tarfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from bx1_management.server import ManagementApplication, ManagementServer  # noqa: E402
from bx1_management.voice_vertical import VoiceTimeline, VoiceVerticalSlice  # noqa: E402
from build_voice_vertical_body_patch import FILES, build, production_patch_file_modes  # noqa: E402


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
        self.assertIn("emit_mouth_events=allow_actions", body)
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
