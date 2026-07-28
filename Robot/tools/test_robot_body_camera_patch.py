#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import subprocess
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
PATCH_SOURCE = ROOT / "tools" / "robot_body_camera_patch"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(PATCH_SOURCE))

import patch_runtime as patch  # noqa: E402
import build_robot_body_camera_patch as patch_builder  # noqa: E402
from bx1_robot_client import now_iso  # noqa: E402
from main import BX1RobotBodyService  # noqa: E402
from web_control import WebControlServer  # noqa: E402


JPEG = (
    b"\xff\xd8"
    b"\xff\xc0\x00\x0b\x08\x01\xe0\x02\x80\x01\x01\x11\x00"
    b"\xff\xd9"
)


class FakeResponse:
    def __init__(
        self,
        body=b"",
        content_type="application/json",
        *,
        status=200,
    ):
        self.body = io.BytesIO(body)
        self.headers = {"Content-Type": content_type}
        self.status = status
        self.closed = False

    def read(self, size=-1):
        return self.body.read(size)

    def readline(self, size=-1):
        return self.body.readline(size)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeRobotBody:
    def __init__(self, *, frame=True, stale=False):
        self.cfg = {"web_log_http": False}
        self.frame = frame
        self.stale = stale
        self.streams = 0
        self.capture_calls = 0

    def get_cached_camera_frame(self):
        if not self.frame:
            raise RuntimeError("No cached Robot Body camera frame is available")
        return {
            "jpeg": JPEG,
            "sequence": 17,
            "timestamp": "2026-07-28T12:00:00Z",
            "age_ms": 9000.0 if self.stale else 20.0,
            "width": 640,
            "height": 480,
        }

    def get_camera_endpoint_status(self):
        return {
            "available": self.frame,
            "owner": "bx1-web.service",
            "source": "Existing Robot Body",
            "resolution": "640x480" if self.frame else "unknown",
            "frame_sequence": 17 if self.frame else 0,
            "last_frame_timestamp": (
                "2026-07-28T12:00:00Z" if self.frame else ""
            ),
            "frame_age_ms": (
                9000.0 if self.stale else 20.0 if self.frame else None
            ),
            "estimated_fps": 8.0 if self.frame else 0.0,
            "stale": self.stale or not self.frame,
            "error": "" if self.frame else "no_cached_frame",
            "active_preview_streams": self.streams,
        }

    def camera_preview_stream_opened(self):
        self.streams += 1

    def camera_preview_stream_closed(self):
        self.streams -= 1

    def get_camera_snapshot_jpeg(self, **_kwargs):
        self.capture_calls += 1
        raise AssertionError("safe endpoint invoked legacy capture")

    def web_snapshot(self):
        return {
            "ok": True,
            "mic": {"mic_device": "hw:0,0"},
            "voice_runtime": {"state": "listening"},
            "state": {"sensors": {"imu": {"state": "online"}}},
            "events": [],
        }

    def web_log(self, *_args, **_kwargs):
        return None


class CameraEndpointTests(unittest.TestCase):
    def start_body(self, **kwargs):
        service = FakeRobotBody(**kwargs)
        server = WebControlServer(service, host="127.0.0.1", port=0)
        server.start()
        self.addCleanup(server.stop)
        return service, "http://127.0.0.1:%s" % server.httpd.server_address[1]

    def test_no_cached_frame_status_and_snapshot_503(self):
        service, base = self.start_body(frame=False)
        with urllib.request.urlopen(
            base + "/api/camera/status", timeout=2
        ) as response:
            status = json.loads(response.read())
        self.assertFalse(status["available"])
        self.assertTrue(status["stale"])
        self.assertEqual(status["error"], "no_cached_frame")
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(
                base + "/api/camera/snapshot", timeout=2
            )
        self.assertEqual(raised.exception.code, 503)
        self.assertEqual(service.capture_calls, 0)

    def test_snapshot_returns_valid_cached_jpeg_and_required_headers(self):
        service, base = self.start_body()
        with urllib.request.urlopen(
            base + "/api/camera/snapshot", timeout=2
        ) as response:
            self.assertEqual(response.headers.get_content_type(), "image/jpeg")
            self.assertEqual(
                response.headers["Cache-Control"],
                "no-store, no-cache, must-revalidate",
            )
            self.assertEqual(response.headers["Pragma"], "no-cache")
            self.assertEqual(response.read(), JPEG)
        self.assertEqual(service.capture_calls, 0)

    def test_camera_status_reports_stale_frame(self):
        _service, base = self.start_body(stale=True)
        with urllib.request.urlopen(
            base + "/api/camera/status", timeout=2
        ) as response:
            status = json.loads(response.read())
        self.assertTrue(status["available"])
        self.assertTrue(status["stale"])
        self.assertGreater(status["frame_age_ms"], 5000)

    def test_mjpeg_request_disconnects_cleanly(self):
        service, base = self.start_body()
        response = urllib.request.urlopen(
            base + "/api/camera/stream?fps=15", timeout=2
        )
        self.assertEqual(response.readline(), b"--frame\r\n")
        self.assertEqual(response.readline(), b"Content-Type: image/jpeg\r\n")
        while response.readline() != b"\r\n":
            pass
        self.assertEqual(response.read(len(JPEG)), JPEG)
        response.close()
        for _ in range(40):
            if service.streams == 0:
                break
            time.sleep(0.02)
        self.assertEqual(service.streams, 0)
        self.assertEqual(service.capture_calls, 0)

    def test_multiple_preview_clients_share_cache(self):
        service, base = self.start_body()
        first = urllib.request.urlopen(
            base + "/api/camera/stream?fps=15", timeout=2
        )
        second = urllib.request.urlopen(
            base + "/api/camera/stream?fps=15", timeout=2
        )
        self.assertGreaterEqual(service.streams, 2)
        for response in (first, second):
            self.assertEqual(response.readline(), b"--frame\r\n")
            response.close()
        for _ in range(40):
            if service.streams == 0:
                break
            time.sleep(0.02)
        self.assertEqual(service.streams, 0)
        self.assertEqual(service.capture_calls, 0)

    def test_existing_api_and_ui_remain_compatible(self):
        _service, base = self.start_body()
        for path, expected in (
            ("/", "text/html"),
            ("/api/status", "application/json"),
        ):
            with self.subTest(path=path), urllib.request.urlopen(
                base + path, timeout=2
            ) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), expected)

    def test_camera_write_routes_are_not_added(self):
        _service, base = self.start_body()
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                request = urllib.request.Request(
                    base + "/api/camera/status",
                    data=b"{}",
                    method=method,
                )
                try:
                    urllib.request.urlopen(request, timeout=2)
                except urllib.error.HTTPError as exc:
                    self.assertIn(exc.code, {404, 501})
                except ConnectionResetError:
                    pass
                else:
                    self.fail("%s camera request unexpectedly succeeded" % method)


class BufferContractTests(unittest.TestCase):
    def service_fixture(self, *, age_seconds=0.0):
        service = object.__new__(BX1RobotBodyService)
        service.camera_frame_lock = threading.Lock()
        service.latest_camera_jpeg = JPEG
        service.latest_camera_frame_at = now_iso()
        service.latest_camera_frame_mono = time.monotonic() - age_seconds
        service.latest_camera_frame_source = "existing_awareness"
        service.camera_frame_sequence = 4
        service.camera_frame_times = [
            time.monotonic() - 0.25,
            time.monotonic() - 0.125,
            time.monotonic(),
        ]
        service.camera_preview_streams = 0
        service.cfg = {"camera_preview_stale_after_s": 5.0}
        return service

    def test_frame_is_copied_while_locked_then_lock_is_released(self):
        service = self.service_fixture()
        frame = BX1RobotBodyService.get_cached_camera_frame(service)
        self.assertEqual(frame["jpeg"], JPEG)
        self.assertTrue(service.camera_frame_lock.acquire(blocking=False))
        service.camera_frame_lock.release()
        frame["jpeg"] += b"changed"
        self.assertEqual(service.latest_camera_jpeg, JPEG)

    def test_status_contract_and_stale_detection(self):
        service = self.service_fixture(age_seconds=8)
        status = BX1RobotBodyService.get_camera_endpoint_status(service)
        self.assertEqual(
            set(status),
            {
                "available",
                "owner",
                "source",
                "resolution",
                "frame_sequence",
                "last_frame_timestamp",
                "frame_age_ms",
                "estimated_fps",
                "stale",
                "error",
                "active_preview_streams",
            },
        )
        self.assertTrue(status["stale"])

    def test_frame_memory_and_preview_client_limits_are_bounded(self):
        service = self.service_fixture()
        service.cfg["camera_preview_max_frame_bytes"] = 64 * 1024
        service.latest_camera_jpeg = (
            b"\xff\xd8" + b"x" * (70 * 1024) + b"\xff\xd9"
        )
        with self.assertRaises(RuntimeError):
            BX1RobotBodyService.get_cached_camera_frame(service)
        status = BX1RobotBodyService.get_camera_endpoint_status(service)
        self.assertFalse(status["available"])
        self.assertEqual(
            status["error"], "cached_frame_exceeds_preview_limit"
        )
        service.cfg["camera_preview_max_streams"] = 2
        self.assertTrue(
            BX1RobotBodyService.camera_preview_stream_opened(service)
        )
        self.assertTrue(
            BX1RobotBodyService.camera_preview_stream_opened(service)
        )
        self.assertFalse(
            BX1RobotBodyService.camera_preview_stream_opened(service)
        )
        BX1RobotBodyService.camera_preview_stream_closed(service)
        BX1RobotBodyService.camera_preview_stream_closed(service)

    def test_endpoint_code_has_no_capture_device_or_setting_access(self):
        main_source = (
            PYTHON_ROOT / "main.py"
        ).read_text(encoding="utf-8")
        web_source = (
            PYTHON_ROOT / "web_control.py"
        ).read_text(encoding="utf-8")
        safe_main = main_source[
            main_source.index("    def get_cached_camera_frame"):
            main_source.index("    def get_camera_snapshot_jpeg")
        ]
        route_start = web_source.index("            def _camera_snapshot")
        route_end = web_source.index("            def _read_json", route_start)
        safe_web = web_source[route_start:route_end]
        for forbidden in (
            "VideoCapture",
            "capture_jpeg",
            "/dev/video",
            "cv2.",
            ".set(",
            "subprocess",
            "os.open",
        ):
            self.assertNotIn(forbidden, safe_main)
            self.assertNotIn(forbidden, safe_web)
        self.assertNotIn("camera_frame_lock", safe_web)
        self.assertIn(
            "service.get_cached_camera_frame()",
            web_source,
        )
        self.assertIn(
            "self._camera_snapshot(\n"
            "                            service.get_cached_camera_frame()",
            web_source,
        )


class FakeRunner:
    def __init__(self, *, fail_first_restart=False):
        self.commands = []
        self.fail_first_restart = fail_first_restart
        self.restart_attempts = 0
        self.states = {
            patch.BODY_SERVICE: {
                "LoadState": "loaded",
                "ActiveState": "active",
                "MainPID": "731",
            },
            patch.BX1_SERVICE: {
                "LoadState": "loaded",
                "ActiveState": "active",
                "MainPID": "900",
            },
        }

    def run(self, command, **_kwargs):
        command = list(command)
        self.commands.append(command)
        if command[:2] == ["systemctl", "show"]:
            service = command[2]
            prop = command[command.index("--property") + 1]
            value = self.states.get(
                service,
                {
                    "LoadState": "not-found",
                    "ActiveState": "inactive",
                    "MainPID": "0",
                },
            )[prop]
            return subprocess.CompletedProcess(command, 0, value + "\n", "")
        if command[:2] == ["systemctl", "restart"]:
            self.restart_attempts += 1
            if self.fail_first_restart and self.restart_attempts == 1:
                return subprocess.CompletedProcess(command, 1, "", "failed")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")


class PatchFixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.target = self.root / "Arduino_Q_Client_V1"
        self.package = self.root / "package"
        self.backups = self.root / "backups"
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.old = {}
        self.new = {}
        files = {
            "python/main.py": b"VALUE = 'old-main'\n",
            "python/web_control.py": b"VALUE = 'old-web'\n",
            "python/camera_io.py": b"VALUE = 'old-camera'\n",
        }
        for name, data in files.items():
            target = self.target / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            changed = self.package / "changed_files" / name
            changed.parent.mkdir(parents=True, exist_ok=True)
            replacement = data.replace(b"old", b"new")
            changed.write_bytes(replacement)
            self.old[name] = data
            self.new[name] = replacement
        manifest = {
            "schema": "bx1.robot_body.camera_patch.v1",
            "patch_id": patch.PATCH_ID,
            "patch_version": patch.PATCH_VERSION,
            "patch_tag": patch.PATCH_TAG,
            "target_root": str(patch.TARGET_ROOT),
            "target_service": patch.BODY_SERVICE,
            "target_port": patch.BODY_PORT,
            "files": [
                {
                    "path": name,
                    "pre_patch_sha256": hashlib.sha256(data).hexdigest(),
                    "post_patch_sha256": hashlib.sha256(
                        self.new[name]
                    ).hexdigest(),
                    "mode": 0o644,
                }
                for name, data in files.items()
            ],
        }
        (self.package / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        self.runner = FakeRunner()
        self.env = patch.PatchEnvironment(
            target_root=self.target,
            backup_root=self.backups,
            proc_root=self.proc,
            runner=self.runner,
            urlopen=self.urlopen,
            system_name=lambda: "Linux",
            geteuid=lambda: 0,
            clock=lambda: 1_785_237_600.0,
            sleeper=lambda _seconds: None,
            chown=lambda _path, _uid, _gid: None,
        )

    def close(self):
        self.temporary.cleanup()

    @staticmethod
    def status():
        return {
            "ok": True,
            "mic": {"mic_device": "hw:0,0"},
            "voice_runtime": {"state": "listening"},
            "state": {"sensors": {"imu": {"state": "online"}}},
            "events": [],
        }

    def urlopen(self, request, timeout=0):
        path = request.full_url.removeprefix(patch.BODY_BASE_URL)
        if path == "/":
            return FakeResponse(b"<html>Robot Body</html>", "text/html")
        if path == "/api/status":
            return FakeResponse(
                json.dumps(self.status()).encode("utf-8")
            )
        if path == "/api/camera/status":
            return FakeResponse(
                json.dumps(
                    {
                        "available": True,
                        "owner": patch.BODY_SERVICE,
                        "source": "Existing Robot Body",
                        "resolution": "640x480",
                        "frame_sequence": 1,
                        "last_frame_timestamp": "now",
                        "frame_age_ms": 10,
                        "estimated_fps": 8,
                        "stale": False,
                        "error": "",
                        "active_preview_streams": 0,
                    }
                ).encode("utf-8")
            )
        if path == "/api/camera/snapshot":
            return FakeResponse(JPEG, "image/jpeg")
        if path.startswith("/api/camera/stream"):
            body = (
                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(JPEG)).encode("ascii")
                + b"\r\n\r\n"
                + JPEG
                + b"\r\n"
            )
            return FakeResponse(
                body,
                "multipart/x-mixed-replace; boundary=frame",
            )
        raise AssertionError("unexpected URL %s" % path)


class InstallerRollbackTests(unittest.TestCase):
    def setUp(self):
        self.fixture = PatchFixture()
        self.addCleanup(self.fixture.close)
        self.ports = mock.patch.object(
            patch, "port_listening", side_effect=lambda _port: True
        )
        self.ports.start()
        self.addCleanup(self.ports.stop)
        self.owners = mock.patch.object(
            patch,
            "camera_owners",
            return_value={
                "owners": [
                    {
                        "pid": 731,
                        "nodes": ["/dev/video0"],
                        "cmdline": "python main.py",
                        "exe": "/usr/bin/python3",
                        "fingerprint": "/usr/bin/python3|python main.py",
                    }
                ],
                "examined_processes": 20,
                "permission_errors": 0,
                "error": "",
            },
        )
        self.owners.start()
        self.addCleanup(self.owners.stop)

    def test_default_dry_run_makes_no_changes_or_backup(self):
        before = {
            name: (self.fixture.target / name).read_bytes()
            for name in self.fixture.old
        }
        report = patch.validate_prepatch(
            self.fixture.package, self.fixture.env
        )
        self.assertTrue(report["ok"])
        self.assertFalse(report["changes_made"])
        self.assertFalse(self.fixture.backups.exists())
        self.assertEqual(
            before,
            {
                name: (self.fixture.target / name).read_bytes()
                for name in self.fixture.old
            },
        )

    def test_prepatch_mismatch_refuses_installation(self):
        (self.fixture.target / "python/main.py").write_text(
            "unexpected = True\n", encoding="utf-8"
        )
        with self.assertRaises(patch.PatchError):
            patch.validate_prepatch(
                self.fixture.package, self.fixture.env
            )
        self.assertFalse(self.fixture.backups.exists())

    def test_no_restart_install_creates_backup_and_preserves_service(self):
        report = patch.install(
            self.fixture.package,
            self.fixture.env,
            no_restart=True,
        )
        self.assertTrue(report["success"])
        self.assertEqual(report["qualification_state"], "pending_restart")
        self.assertFalse(report["service_restarted"])
        backup = Path(report["backup"])
        self.assertTrue((backup / "backup_manifest.json").is_file())
        self.assertTrue((backup / "baseline.json").is_file())
        for name, data in self.fixture.new.items():
            self.assertEqual(
                (self.fixture.target / name).read_bytes(), data
            )
        self.assertFalse(
            any(
                command[:2] == ["systemctl", "restart"]
                for command in self.fixture.runner.commands
            )
        )

    def test_restart_failure_automatically_rolls_back(self):
        self.fixture.runner.fail_first_restart = True
        with self.assertRaises(patch.PatchError):
            patch.install(self.fixture.package, self.fixture.env)
        for name, data in self.fixture.old.items():
            self.assertEqual(
                (self.fixture.target / name).read_bytes(), data
            )
        backup = next(self.fixture.backups.iterdir())
        report = json.loads(
            (backup / "deployment_report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(report["rollback_attempted"])
        self.assertTrue(report["rollback_success"])
        self.assertEqual(self.fixture.runner.restart_attempts, 2)

    def test_qualification_failure_automatically_rolls_back(self):
        failed = {
            "passed": False,
            "failures": ["camera status"],
            "checks": [],
        }
        with mock.patch.object(patch, "qualify", return_value=failed):
            with self.assertRaises(patch.PatchError):
                patch.install(self.fixture.package, self.fixture.env)
        for name, data in self.fixture.old.items():
            self.assertEqual(
                (self.fixture.target / name).read_bytes(), data
            )
        backup = next(self.fixture.backups.iterdir())
        self.assertTrue((backup / "qualification_report.json").is_file())
        self.assertTrue((backup / "rollback_report.json").is_file())

    def test_explicit_rollback_restores_exact_files(self):
        install_report = patch.install(
            self.fixture.package,
            self.fixture.env,
            no_restart=True,
        )
        report = patch.rollback(
            Path(install_report["backup"]), self.fixture.env
        )
        self.assertTrue(report["success"])
        self.assertFalse(report["bx1_os_touched"])
        for name, data in self.fixture.old.items():
            self.assertEqual(
                (self.fixture.target / name).read_bytes(), data
            )

    def test_qualification_preserves_bx1_service_port_and_existing_status(self):
        baseline = patch.capture_baseline(self.fixture.env)
        result = patch.qualify(self.fixture.env, baseline)
        self.assertTrue(result["passed"], result["failures"])
        names = {item["name"] for item in result["checks"]}
        self.assertIn("bx1-os-alpha.service state unchanged", names)
        self.assertIn("Port 8089 state unchanged", names)
        self.assertIn("Microphone status remains available", names)
        self.assertIn("IMU telemetry remains available", names)
        self.assertFalse(result["hardware_actions_requested"])
        self.assertFalse(result["camera_capture_requested"])

    def test_only_existing_service_is_ever_restarted(self):
        with mock.patch.object(
            patch,
            "qualify",
            return_value={"passed": True, "failures": [], "checks": []},
        ):
            report = patch.install(
                self.fixture.package, self.fixture.env
            )
        self.assertTrue(report["success"])
        restarts = [
            command
            for command in self.fixture.runner.commands
            if command[:2] == ["systemctl", "restart"]
        ]
        self.assertEqual(restarts, [["systemctl", "restart", patch.BODY_SERVICE]])
        self.assertNotIn(patch.BX1_SERVICE, " ".join(" ".join(c) for c in restarts))


class PackageScopeTests(unittest.TestCase):
    def test_builder_scope_is_three_robot_body_files(self):
        builder = (
            ROOT / "tools" / "build_robot_body_camera_patch.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"Robot/python/main.py"', builder)
        self.assertIn('"Robot/python/web_control.py"', builder)
        self.assertIn('"Robot/python/camera_io.py"', builder)
        self.assertIn('"complete_project_included": False', builder)
        self.assertNotIn('"Robot/service/', builder)

    def test_patch_runtime_has_fixed_targets_and_no_arbitrary_source(self):
        source = (PATCH_SOURCE / "patch_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'TARGET_ROOT = Path("/home/arduino/Arduino_Q_Client_V1")',
            source,
        )
        self.assertIn('BODY_SERVICE = "bx1-web.service"', source)
        self.assertIn("BODY_PORT = 8088", source)
        self.assertNotIn("--target-root", source)
        self.assertNotIn("--service-name", source)
        self.assertNotIn("--source-url", source)
        self.assertNotIn("shell=True", source)

    def test_builder_creates_minimal_verified_archive_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = patch_builder.build(
                ROOT.parent,
                Path(temporary),
            )
            manifest = json.loads(
                Path(result["manifest"]).read_text(encoding="utf-8")
            )
            self.assertEqual(result["changed_file_count"], 3)
            self.assertEqual(
                {item["path"] for item in manifest["files"]},
                {
                    "python/main.py",
                    "python/web_control.py",
                    "python/camera_io.py",
                },
            )
            self.assertFalse(manifest["complete_project_included"])
            names = {item["path"] for item in manifest["package_files"]}
            self.assertNotIn("python/config.json", names)
            self.assertNotIn("service/bx1-web.service", names)
            self.assertNotIn("service/bx1-os-alpha.service", names)


if __name__ == "__main__":
    unittest.main()
