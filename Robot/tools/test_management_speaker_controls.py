"""Focused contract checks for the BX1 Management Speaker card (8089)."""
from pathlib import Path
import http.client
import json
import sys
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SERVER = (ROOT / "Robot/python/bx1_management/server.py").read_text(encoding="utf-8")
APP = (ROOT / "Robot/python/bx1_management/static/app.js").read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "Robot/python"))

from bx1_management import server as server_module


class ManagementSpeakerControlTests(unittest.TestCase):
    def test_management_volume_proxy_exposes_body_controller(self):
        self.assertIn('"/api/audio_controls"', SERVER)
        for field in ("requested_volume_percent", "effective_volume_percent", "physical_playback_device", "apply_ok", "last_error"):
            self.assertIn(field, SERVER)

    def test_speaker_card_reads_confirmed_state_and_output_signal(self):
        for marker in ('data-audio-volume', 'effective_volume_percent', 'requested_volume_percent', 'Output RMS', 'output_peak_dbfs', 'physical_playback_device'):
            self.assertIn(marker, APP)
        self.assertIn('fetch("/api/audio/volume"', APP)

    def test_management_mute_uses_body_audio_controls(self):
        self.assertIn('"/api/audio/bridge/settings"', APP)
        self.assertIn('"/api/audio_controls"', SERVER)
        self.assertIn('speaker_muted', SERVER)

    def test_handler_audio_routes_use_application_body_resolver(self):
        handler = SERVER[SERVER.index("class Handler"):SERVER.index("return ReusableThreadingHTTPServer", SERVER.index("class Handler"))]
        self.assertIn('application._body_url("/api/audio_controls")', handler)
        self.assertNotIn('self._body_url("/api/audio_controls")', handler)

    def test_get_and_post_volume_proxy_succeed(self):
        class FakeApplication:
            def __init__(self):
                self.urls = []

            def _body_url(self, path):
                self.urls.append(path)
                return "http://body.test:8088" + path

            @staticmethod
            def _flatten_body_audio_controls(payload):
                return {"ok": bool(payload.get("ok", True)), "volume": payload.get("tts_volume", 55), "requested_volume_percent": 55, "effective_volume_percent": 55}

        class BodyResponse:
            status = 200
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, *_): return json.dumps(self.payload).encode("utf-8")

        app = FakeApplication()
        management = server_module.ManagementServer(app, host="127.0.0.1", port=0, static_root=server_module.STATIC_ROOT)
        httpd = management._build_httpd()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.object(server_module.url_request, "urlopen", return_value=BodyResponse({"ok": True, "tts_volume": 55})) as opener:
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
                connection.request("GET", "/api/audio/volume")
                get_response = connection.getresponse()
                get_payload = json.loads(get_response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(get_response.status, 200)
                self.assertTrue(get_payload["ok"])
                self.assertEqual(app.urls, ["/api/audio_controls"])
                opener.assert_called_once()

            with mock.patch.object(server_module.url_request, "urlopen", return_value=BodyResponse({"ok": True, "tts_volume": 62})):
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
                connection.request("POST", "/api/audio/volume", body=json.dumps({"volume": 62}), headers={"Content-Type": "application/json"})
                post_response = connection.getresponse()
                post_payload = json.loads(post_response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(post_response.status, 200)
                self.assertTrue(post_payload["ok"])
                self.assertEqual(post_payload["volume"], 62)
                self.assertEqual(app.urls[-1], "/api/audio_controls")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_body_http_errors_are_returned_cleanly(self):
        class FakeApplication:
            def _body_url(self, path): return "http://body.test:8088" + path
            @staticmethod
            def _flatten_body_audio_controls(payload): return {"ok": bool(payload.get("ok", False)), "raw": payload}

        management = server_module.ManagementServer(FakeApplication(), host="127.0.0.1", port=0, static_root=server_module.STATIC_ROOT)
        httpd = management._build_httpd()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.object(server_module.url_request, "urlopen", side_effect=server_module.error.URLError("body unavailable")):
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
                connection.request("GET", "/api/audio/volume")
                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                connection.close()
                self.assertEqual(response.status, 503)
                self.assertFalse(payload["ok"])
                self.assertNotIn("AttributeError", json.dumps(payload))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
