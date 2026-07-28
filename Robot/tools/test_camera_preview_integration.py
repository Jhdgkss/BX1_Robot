#!/usr/bin/env python3
from __future__ import annotations

import inspect
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bx1_core.hardware.camera import (  # noqa: E402
    CameraAdapter,
    CameraFrame,
    CameraProxyError,
    RobotBodyCameraClient,
)
from bx1_core.hardware.device import (  # noqa: E402
    DeviceHealth,
    DeviceRecord,
    HardwareEnvironment,
)
from bx1_management.server import (  # noqa: E402
    ManagementApplication,
    ManagementServer,
)
from web_control import WebControlServer  # noqa: E402


JPEG = (
    b"\xff\xd8"
    b"\xff\xc0\x00\x0b\x08\x01\xe0\x02\x80\x01\x01\x11\x00"
    b"\xff\xd9"
)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, headers=None):
        self.body = io.BytesIO(body)
        self.headers = {
            "Content-Type": content_type,
            **(headers or {}),
        }
        self.closed = False

    def read(self, size=-1):
        return self.body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True


class FakeRobotBody:
    def __init__(self, frame=True):
        self.cfg = {"web_log_http": False}
        self.frame = frame
        self.capture_calls = 0
        self.streams = 0

    def get_cached_camera_frame(self):
        if not self.frame:
            raise RuntimeError("no cached frame")
        return {
            "jpeg": JPEG,
            "sequence": 7,
            "timestamp": "2026-07-28T12:00:00Z",
            "age_ms": 20.0,
            "width": 640,
            "height": 480,
        }

    def camera_preview_stream_opened(self):
        self.streams += 1

    def camera_preview_stream_closed(self):
        self.streams -= 1

    def get_camera_snapshot_jpeg(self, **_kwargs):
        self.capture_calls += 1
        raise AssertionError("legacy capture route must not be used")

    def web_log(self, *_args, **_kwargs):
        return None


class FakeCameraClient:
    def __init__(self):
        self.snapshot_calls = 0
        self.stream_calls = 0
        self.last_fps = None

    def status(self):
        return {
            "proxy_available": True,
            "owner": "bx1-web.service",
            "source": "Existing Robot Body",
            "device_nodes_opened": False,
            "capture_created": False,
            "settings_changed": False,
            "maximum_fps": 15,
            "queue_depth": 1,
        }

    def snapshot(self):
        self.snapshot_calls += 1
        return CameraFrame(
            JPEG,
            8,
            "2026-07-28T12:00:01Z",
            30.0,
            640,
            480,
            time.time(),
        )

    def relay_stream(self, *, on_open, writer, fps=None):
        self.stream_calls += 1
        if fps is not None and fps > 15:
            fps = 15
        self.last_fps = fps
        on_open("multipart/x-mixed-replace; boundary=frame")
        writer(
            b"--frame\r\nContent-Type: image/jpeg\r\n"
            + b"Content-Length: "
            + str(len(JPEG)).encode("ascii")
            + b"\r\n\r\n"
            + JPEG
            + b"\r\n"
        )
        return {"ok": True, "bytes_relayed": len(JPEG), "fps": fps}


def qualification_config():
    return json.loads(
        (PYTHON_ROOT / "config.alpha-qualification.json").read_text(
            encoding="utf-8"
        )
    )


class RobotBodyCachedEndpointTests(unittest.TestCase):
    def start_body(self, frame=True):
        service = FakeRobotBody(frame=frame)
        server = WebControlServer(service, host="127.0.0.1", port=0)
        server.start()
        port = server.httpd.server_address[1]
        self.addCleanup(server.stop)
        return service, "http://127.0.0.1:%s" % port

    def test_snapshot_endpoint_returns_only_cached_jpeg(self):
        service, base = self.start_body()
        with urllib.request.urlopen(
            base + "/api/camera/snapshot", timeout=2
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/jpeg")
            self.assertEqual(
                response.headers["Cache-Control"],
                "no-store, no-cache, must-revalidate",
            )
            self.assertEqual(response.headers["X-BX1-Frame-Sequence"], "7")
            self.assertEqual(response.read(), JPEG)
        self.assertEqual(service.capture_calls, 0)

    def test_snapshot_endpoint_returns_503_when_cache_empty(self):
        service, base = self.start_body(frame=False)
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(
                base + "/api/camera/snapshot", timeout=2
            )
        self.assertEqual(raised.exception.code, 503)
        self.assertEqual(service.capture_calls, 0)

    def test_mjpeg_endpoint_reuses_cache_and_cleans_up_disconnect(self):
        service, base = self.start_body()
        response = urllib.request.urlopen(
            base + "/api/camera/stream?fps=15", timeout=2
        )
        self.assertIn(
            "multipart/x-mixed-replace",
            response.headers["Content-Type"],
        )
        self.assertEqual(response.readline(), b"--frame\r\n")
        self.assertEqual(response.readline(), b"Content-Type: image/jpeg\r\n")
        length_line = response.readline()
        self.assertIn(b"Content-Length:", length_line)
        while response.readline() != b"\r\n":
            pass
        self.assertEqual(response.read(len(JPEG)), JPEG)
        response.close()
        for _ in range(30):
            if service.streams == 0:
                break
            time.sleep(0.02)
        self.assertEqual(service.streams, 0)
        self.assertEqual(service.capture_calls, 0)


class CameraClientTests(unittest.TestCase):
    def test_snapshot_success_and_fixed_allowlisted_url(self):
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["method"] = request.method
            seen["timeout"] = timeout
            return FakeResponse(
                JPEG,
                "image/jpeg",
                {
                    "X-BX1-Frame-Sequence": "12",
                    "X-BX1-Frame-Timestamp": "now",
                    "X-BX1-Frame-Age-Ms": "9.5",
                },
            )

        client = RobotBodyCameraClient(opener=opener)
        frame = client.snapshot()
        self.assertEqual(seen["url"], "http://127.0.0.1:8088/api/camera/snapshot")
        self.assertEqual(seen["method"], "GET")
        self.assertEqual(frame.sequence, 12)
        self.assertEqual(frame.resolution, "640x480")

    def test_arbitrary_upstream_is_rejected(self):
        for value in (
            "http://robot.example:8088",
            "http://127.0.0.1:8089",
            "https://127.0.0.1:8088",
            "http://127.0.0.1:8088/api",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RobotBodyCameraClient(value)

    def test_snapshot_503_timeout_and_malformed_jpeg(self):
        def unavailable(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "http://127.0.0.1:8088/api/camera/snapshot",
                503,
                "missing",
                {},
                None,
            )

        with self.assertRaises(CameraProxyError) as raised:
            RobotBodyCameraClient(opener=unavailable).snapshot()
        self.assertEqual(raised.exception.status, 503)

        def timeout(*_args, **_kwargs):
            raise TimeoutError()

        with self.assertRaises(CameraProxyError) as raised:
            RobotBodyCameraClient(opener=timeout).snapshot()
        self.assertEqual(raised.exception.error, "robot_body_snapshot_timeout")

        client = RobotBodyCameraClient(
            opener=lambda *_args, **_kwargs: FakeResponse(
                b"not-jpeg", "image/jpeg"
            )
        )
        with self.assertRaises(CameraProxyError) as raised:
            client.snapshot()
        self.assertEqual(
            raised.exception.error,
            "robot_body_snapshot_malformed_jpeg",
        )

    def test_mjpeg_disconnect_releases_single_stream_gate(self):
        body = (
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            + JPEG
            + b"\r\n"
        )
        responses = []

        def opener(*_args, **_kwargs):
            response = FakeResponse(
                body, "multipart/x-mixed-replace; boundary=frame"
            )
            responses.append(response)
            return response

        client = RobotBodyCameraClient(opener=opener)

        def disconnect(_chunk):
            raise BrokenPipeError()

        result = client.relay_stream(
            on_open=lambda _content_type: None,
            writer=disconnect,
            fps=99,
        )
        self.assertTrue(result["browser_disconnected"])
        self.assertTrue(responses[0].closed)
        second = client.relay_stream(
            on_open=lambda _content_type: None,
            writer=lambda _chunk: None,
        )
        self.assertTrue(second["ok"])
        status = client.status()
        self.assertEqual(status["maximum_fps"], 15)
        self.assertEqual(status["queue_depth"], 1)


class CameraInventoryTests(unittest.TestCase):
    def test_physical_nodes_group_and_qcom_venus_stays_advanced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dev = root / "dev"
            sys_root = root / "sys"
            dev.mkdir()
            for name, friendly, usb in (
                ("video0", "UVC Camera", True),
                ("video1", "UVC Camera Metadata", True),
                ("video2", "qcom-venus decoder", False),
            ):
                (dev / name).write_bytes(b"metadata fixture")
                base = sys_root / "class" / "video4linux" / name
                (base / "device").mkdir(parents=True)
                (base / "name").write_text(friendly, encoding="utf-8")
                if usb:
                    (base / "device" / "idVendor").write_text(
                        "046d", encoding="utf-8"
                    )
                    (base / "device" / "idProduct").write_text(
                        "0825", encoding="utf-8"
                    )
            adapter = CameraAdapter(
                HardwareEnvironment(
                    dev_root=dev,
                    sys_root=sys_root,
                    proc_root=root / "proc",
                )
            )
            body = {
                "connected": True,
                "camera": {
                    "device": str(dev / "video0"),
                    "configured": True,
                    "preview": {
                        "preview_available": True,
                        "resolution": "640x480",
                        "frame_age_ms": 25,
                    },
                },
            }
            raw = adapter.discover(body)
            groups = adapter.summarise(raw, body)
        self.assertEqual(len(raw), 3)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["name"], "Logitech UVC Camera")
        self.assertEqual(
            len(groups[0]["details"]["underlying_nodes"]), 2
        )
        internal = next(item for item in raw if item.name.startswith("qcom"))
        self.assertTrue(internal.details["internal_video_device"])
        self.assertFalse(internal.details["user_visible"])

    def test_stale_preview_is_reported_without_global_fault(self):
        record = DeviceRecord(
            "camera:video0",
            "UVC",
            "camera",
            True,
            False,
            "bx1-web.service",
            DeviceHealth("owned_elsewhere", "owned"),
            details={
                "physical_group_id": "usb:046d:0825",
                "user_visible": True,
                "configured": True,
                "usb_identity": {"vendor": "046d", "product": "0825"},
            },
        )
        groups = CameraAdapter(mock.Mock()).summarise(
            [record],
            {
                "connected": True,
                "camera": {
                    "preview": {
                        "preview_available": True,
                        "stale": True,
                        "health": "warning",
                    }
                },
            },
        )
        self.assertEqual(groups[0]["ownership"], "bx1-web.service")
        self.assertTrue(groups[0]["telemetry"]["stale"])


class ManagementCameraAPITests(unittest.TestCase):
    def setUp(self):
        self.client = FakeCameraClient()
        application = ManagementApplication(
            qualification_config(), camera_client=self.client
        )
        self.server = ManagementServer(
            application, host="127.0.0.1", port=0
        )
        self.server.start()
        self.base = "http://127.0.0.1:%s" % self.server.port

    def tearDown(self):
        self.server.stop()

    def test_camera_metadata_snapshot_and_stream_routes(self):
        with urllib.request.urlopen(
            self.base + "/api/core/camera", timeout=3
        ) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["proxy"]["proxy_available"])
        self.assertFalse(payload["proxy"]["device_nodes_opened"])

        with urllib.request.urlopen(
            self.base + "/api/core/camera/snapshot", timeout=3
        ) as response:
            self.assertEqual(response.headers.get_content_type(), "image/jpeg")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.read(), JPEG)

        with urllib.request.urlopen(
            self.base + "/api/core/camera/stream?fps=8", timeout=3
        ) as response:
            self.assertIn(
                "multipart/x-mixed-replace",
                response.headers["Content-Type"],
            )
            self.assertIn(JPEG, response.read())

    def test_write_methods_remain_disabled(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                request = urllib.request.Request(
                    self.base + "/api/core/camera",
                    data=b"{}",
                    method=method,
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=3)
                self.assertEqual(raised.exception.code, 501)

    def test_high_cpu_exposes_degraded_state_and_reduces_fps(self):
        self.server.application.core.state.set(
            "system.cpu", 92.0, source="test"
        )
        camera = self.server.application.core_camera()
        self.assertEqual(
            camera["proxy"]["performance_state"], "degraded_cpu"
        )
        self.assertEqual(camera["proxy"]["effective_fps_limit"], 5.0)
        self.server.application.relay_camera_stream(
            on_open=lambda _content_type: None,
            writer=lambda _chunk: None,
            fps=12,
        )
        self.assertEqual(self.client.last_fps, 5.0)


class StaticSafetyAndUITests(unittest.TestCase):
    def test_bx1_proxy_has_no_capture_or_device_access(self):
        source = inspect.getsource(RobotBodyCameraClient)
        self.assertNotIn("cv2", source)
        self.assertNotIn("VideoCapture", source)
        self.assertNotIn("/dev/video", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("method=\"POST\"", source)

    def test_ui_has_camera_states_cleanup_and_no_controls(self):
        source = (
            PYTHON_ROOT / "bx1_management" / "static" / "app.js"
        ).read_text(encoding="utf-8")
        for value in (
            'id: "camera", label: "Camera"',
            "cameraPreviewState",
            "cameraStaleWarning",
            "visibilitychange",
            "stopCameraPreview",
            "/api/core/camera/stream",
            "/api/core/camera/snapshot",
            "Owned by Robot Body",
            "Future controlled operation",
            "LEO",
        ):
            self.assertIn(value, source)
        for control in ("Exposure control", "Focus control", "Zoom control"):
            self.assertNotIn(control, source)

    def test_existing_ui_port_is_only_a_fixed_read_only_source(self):
        source = (
            PYTHON_ROOT / "bx1_core" / "hardware" / "camera.py"
        ).read_text(encoding="utf-8")
        self.assertIn("parsed.port != 8088", source)
        self.assertIn('method="GET"', source)
        self.assertNotIn('method="POST"', source)


if __name__ == "__main__":
    unittest.main()
