#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from bx1_core.hardware.camera import RobotBodyCameraClient  # noqa: E402


class OperatorIntegrationTests(unittest.TestCase):
    def test_body_camera_proxy_uses_live_cached_jpeg_contract(self):
        self.assertEqual(RobotBodyCameraClient.SNAPSHOT_PATH, "/api/camera_snapshot.jpg")
        self.assertEqual(RobotBodyCameraClient.STREAM_PATH, "/api/camera/stream")
    def test_kiosk_waits_for_os_dashboard_and_keeps_legacy_fallback(self):
        script = (ROOT / "tools" / "bx1_touchscreen_kiosk.sh").read_text(encoding="utf-8")
        unit = (ROOT / "service" / "bx1-touchscreen.service").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:${BX1_WEB_PORT}/dashboard", script)
        self.assertIn("BX1_TOUCH_LEGACY_URL", script)
        self.assertIn("After=graphical.target network-online.target bx1-os-alpha.service", unit)
        self.assertIn("ExecStart=/home/arduino/BX1_OS/tools/bx1_touchscreen_kiosk.sh", unit)


if __name__ == "__main__": unittest.main()
