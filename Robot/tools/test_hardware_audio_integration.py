#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bx1_core import BX1Core  # noqa: E402
from bx1_core.hardware import (  # noqa: E402
    HardwareEnvironment,
    ReadOnlyHardwareInventory,
    RobotBodyClient,
)
from bx1_core.hardware.serial import SerialAdapter  # noqa: E402
from bx1_management.server import (  # noqa: E402
    ManagementApplication,
    ManagementServer,
)


def qualification_config():
    return json.loads(
        (PYTHON_ROOT / "config.alpha-qualification.json").read_text(
            encoding="utf-8"
        )
    )


class FakeResponse:
    def __init__(self, value, *, server="RobotBodyClient/10.42.1"):
        self.raw = (
            value
            if isinstance(value, bytes)
            else json.dumps(value).encode("utf-8")
        )
        self.headers = {"Server": server}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self.raw if limit < 0 else self.raw[:limit]


class FakeRobotBodyClient:
    def __init__(self, connected=True):
        self.connected = connected

    def collect(self):
        if not self.connected:
            return {
                "connected": False,
                "version": "unknown",
                "health": "unavailable",
                "active_faults": [],
                "timestamp": 100.0,
                "source": "Existing Robot Body",
                "error": "unavailable",
                "microphone": {},
                "speaker": {},
                "stt": {"state": "unknown"},
                "tts": {"state": "unknown"},
                "mcu": {"state": "unknown"},
                "imu": {"state": "unknown"},
                "camera": {"state": "unknown"},
                "hardware": {},
            }
        return {
            "connected": True,
            "version": "10.42.1",
            "health": "healthy",
            "active_faults": [],
            "timestamp": 100.0,
            "source": "Existing Robot Body",
            "error": "",
            "microphone": {
                "configured_device": "hw:0,0",
                "settings": {"sample_rate": 16000, "channels": 1},
                "devices": [
                    {
                        "device": "hw:0,0",
                        "description": "USB Microphone",
                    }
                ],
                "level": {
                    "rms_dbfs": -36.2,
                    "peak_dbfs": -12.5,
                    "noise_floor_dbfs": -51.0,
                    "timestamp": 99.9,
                },
            },
            "speaker": {
                "configured_device": "hw:0,0",
                "volume": 80,
                "muted": False,
                "devices": [
                    {
                        "device": "hw:0,0",
                        "description": "USB Speaker",
                    }
                ],
            },
            "stt": {"state": "listening", "listening": True},
            "tts": {"state": "enabled", "backend": "brain-tts"},
            "mcu": {"state": "online"},
            "imu": {"state": "fresh", "driver": "robot_body"},
            "camera": {"state": "online", "device": "/dev/video0"},
            "mouth_led": {"state": "idle"},
            "hardware": {
                "hardware_registry": {
                    "servos": {"head": {"enabled": True}}
                },
                "hardware_control": {
                    "serial_port": "/dev/ttyACM0",
                    "rs485_enabled": False,
                },
            },
        }


class HardwareFixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dev = self.root / "dev"
        self.proc = self.root / "proc"
        self.sys = self.root / "sys"
        self.dev.mkdir()
        self.proc.mkdir()
        self.sys.mkdir()

    def environment(self, **updates):
        values = {
            "dev_root": self.dev,
            "proc_root": self.proc,
            "sys_root": self.sys,
            "clock": lambda: 100.0,
            "which": lambda name: None,
        }
        values.update(updates)
        return HardwareEnvironment(**values)

    def close(self):
        self.temporary.cleanup()


class RobotBodyClientTests(unittest.TestCase):
    def test_collects_allowlisted_get_data_and_sanitises_status(self):
        values = {
            "/api/status": {
                "ok": True,
                "identity": {"version": "10.42.1"},
                "mic": {"mic_device": "hw:2,0"},
                "audio": {
                    "tts_enabled": True,
                    "tts_playback_device": "hw:2,0",
                    "tts_volume": 70,
                    "api_key": "must-not-leak",
                },
                "voice_runtime": {"state": "listening"},
                "mic_level": {"level": {"rms_dbfs": -30}},
                "brain": {"api_key": "must-not-leak"},
            },
            "/api/mic_devices": {"ok": True, "devices": []},
            "/api/mic_playback_devices": {"ok": True, "devices": []},
        }
        requests = []

        def opener(request, timeout):
            self.assertLessEqual(timeout, 2)
            self.assertEqual(request.get_method(), "GET")
            requests.append(request.full_url)
            path = request.full_url.split(":8088", 1)[1]
            return FakeResponse(values[path])

        snapshot = RobotBodyClient(opener=opener, clock=lambda: 100.0).collect()
        self.assertTrue(snapshot["connected"])
        self.assertEqual(snapshot["version"], "10.42.1")
        self.assertEqual(len(requests), 3)
        self.assertNotIn("api_key", json.dumps(snapshot))

    def test_unavailable_timeout_and_malformed_responses_fail_closed(self):
        failures = [
            lambda request, timeout: (_ for _ in ()).throw(
                urllib.error.URLError("offline")
            ),
            lambda request, timeout: (_ for _ in ()).throw(socket.timeout()),
            lambda request, timeout: FakeResponse(b"{not json"),
        ]
        expected = {"unavailable", "timeout", "malformed_response"}
        for opener in failures:
            with self.subTest(opener=opener):
                result = RobotBodyClient(opener=opener).collect()
                self.assertFalse(result["connected"])
                self.assertIn(result["error"], expected)

    def test_rejects_non_loopback_or_non_production_port(self):
        for url in ("http://robot:8088", "http://127.0.0.1:8089"):
            with self.assertRaises(ValueError):
                RobotBodyClient(url)

    def test_maps_existing_robot_body_sensor_telemetry_without_probing(self):
        values = {
            "/api/status": {
                "state": {
                    "sensors": {
                        "mcu_ok": True,
                        "mcu_transport_connected": True,
                        "mcu_heartbeat_fresh": True,
                        "mcu_last_update_age_ms": 12,
                        "imu_present": True,
                        "imu_initialised": True,
                        "imu_sample_fresh": True,
                        "imu_healthy": True,
                        "imu_source": "bno055",
                    }
                }
            },
            "/api/mic_devices": {"devices": []},
            "/api/mic_playback_devices": {"devices": []},
        }

        def opener(request, timeout):
            path = request.full_url.split(":8088", 1)[1]
            return FakeResponse(values[path])

        snapshot = RobotBodyClient(opener=opener).collect()
        self.assertEqual(snapshot["mcu"]["state"], "online")
        self.assertEqual(snapshot["imu"]["state"], "fresh")
        self.assertEqual(snapshot["imu"]["imu_source"], "bno055")


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = HardwareFixture()

    def tearDown(self):
        self.fixture.close()

    def test_inventory_is_safe_when_hardware_and_alsa_tools_are_absent(self):
        inventory = ReadOnlyHardwareInventory(
            environment=self.fixture.environment(),
            robot_body_client=FakeRobotBodyClient(False),
        ).collect()
        self.assertTrue(inventory["observer_only"])
        self.assertFalse(inventory["ownership_taken"])
        self.assertFalse(inventory["devices_opened"])
        self.assertEqual(inventory["camera"], [])
        self.assertEqual(inventory["serial"], [])
        self.assertEqual(
            inventory["audio"]["telemetry"]["alsa_tools"]["arecord"],
            "missing",
        )
        self.assertFalse(inventory["diagnostics"]["optional_absence_is_fault"])

    def test_audio_devices_and_levels_are_proxied_without_opening_devices(self):
        asound = self.fixture.proc / "asound"
        asound.mkdir()
        (asound / "pcm").write_text(
            "00-00: USB Audio : USB Audio : playback 1 : capture 1\n",
            encoding="utf-8",
        )
        (asound / "cards").write_text(
            " 0 [USB ]: USB-Audio - USB Audio\n",
            encoding="utf-8",
        )
        inventory = ReadOnlyHardwareInventory(
            environment=self.fixture.environment(),
            robot_body_client=FakeRobotBodyClient(),
        ).collect()
        microphone = inventory["audio"]["microphones"][0]
        self.assertEqual(microphone["ownership"], "bx1-web.service")
        self.assertEqual(microphone["health"]["state"], "owned_elsewhere")
        self.assertFalse(microphone["capabilities"]["live_measurement"])
        self.assertEqual(inventory["audio"]["telemetry"]["level_rms"], -36.2)
        self.assertEqual(
            inventory["audio"]["telemetry"]["measurement_state"],
            "proxied_from_robot_body",
        )

    def test_permission_denied_is_reported_and_does_not_abort_inventory(self):
        denied = self.fixture.proc / "bus" / "input" / "devices"

        def reader(path):
            if path == denied:
                raise PermissionError("denied")
            return path.read_text(encoding="utf-8")

        inventory = ReadOnlyHardwareInventory(
            environment=self.fixture.environment(text_reader=reader),
            robot_body_client=FakeRobotBodyClient(False),
        ).collect()
        input_records = [
            item
            for item in inventory["inventory"]
            if item["category"] == "input_device"
        ]
        self.assertEqual(
            input_records[0]["health"]["state"], "permission_denied"
        )

    def test_owned_camera_is_detected_without_opening_device(self):
        camera = self.fixture.dev / "video0"
        camera.write_bytes(b"not-a-real-camera")
        environment = self.fixture.environment()
        environment.owners = lambda path, limit=4096: [
            {"pid": 42, "process": "python", "service": "bx1-web.service"}
        ]
        inventory = ReadOnlyHardwareInventory(
            environment=environment,
            robot_body_client=FakeRobotBodyClient(),
        ).collect()
        record = inventory["camera"][0]
        self.assertEqual(record["health"]["state"], "owned_elsewhere")
        self.assertEqual(record["ownership"], "bx1-web.service")
        self.assertFalse(record["capabilities"]["streaming"])

    def test_private_device_namespace_uses_sysfs_detection_fallback(self):
        video = self.fixture.sys / "class" / "video4linux" / "video0"
        video.mkdir(parents=True)
        (video / "name").write_text("USB Camera\n", encoding="utf-8")
        serial = self.fixture.sys / "class" / "tty" / "ttyACM0"
        serial.mkdir(parents=True)
        inventory = ReadOnlyHardwareInventory(
            environment=self.fixture.environment(),
            robot_body_client=FakeRobotBodyClient(False),
        ).collect()
        camera = inventory["camera"][0]
        serial_candidate = inventory["serial"][0]
        self.assertTrue(camera["present"])
        self.assertFalse(camera["available"])
        self.assertFalse(camera["details"]["device_node_visible"])
        self.assertTrue(serial_candidate["present"])
        self.assertFalse(serial_candidate["available"])
        self.assertEqual(
            serial_candidate["error"], "device_node_not_visible"
        )

    def test_serial_permission_denied_never_sends_or_opens_a_probe(self):
        serial = self.fixture.dev / "ttyACM0"
        serial.write_bytes(b"")
        adapter = SerialAdapter(self.fixture.environment())
        with mock.patch.object(adapter, "_readable", return_value=False):
            records = adapter.discover(FakeRobotBodyClient().collect())
        self.assertEqual(records[0].health.state, "permission_denied")
        self.assertFalse(records[0].capabilities["probe"])
        self.assertFalse(records[0].capabilities["write"])

    def test_one_adapter_failure_does_not_stop_other_observers(self):
        inventory = ReadOnlyHardwareInventory(
            environment=self.fixture.environment(),
            robot_body_client=FakeRobotBodyClient(),
        )
        inventory.camera.discover = mock.Mock(
            side_effect=RuntimeError("camera metadata failed")
        )
        result = inventory.collect()
        self.assertEqual(result["camera"], [])
        self.assertEqual(
            result["adapter_failures"]["camera"], "camera metadata failed"
        )
        self.assertTrue(result["robot_body"]["connected"])
        self.assertEqual(
            result["audio"]["telemetry"]["level_rms"], -36.2
        )


class PublishedStateAndAPITests(unittest.TestCase):
    def setUp(self):
        fixture = HardwareFixture()
        self.addCleanup(fixture.close)
        inventory = ReadOnlyHardwareInventory(
            environment=fixture.environment(),
            robot_body_client=FakeRobotBodyClient(),
        )
        self.core = BX1Core(
            qualification_config(),
            install_root=ROOT,
            service_provider=lambda: [],
            plugin_metadata={"hardware_inventory": inventory},
        )

    def test_hardware_and_audio_state_include_observation_evidence(self):
        state = self.core.state_snapshot()["state"]
        self.assertIn("inventory", state["hardware"])
        self.assertIn("timestamp", state["hardware"]["inventory"])
        self.assertIsInstance(
            state["hardware"]["microphone"]["value"], list
        )
        self.assertIsInstance(state["hardware"]["speaker"]["value"], list)
        self.assertEqual(state["hardware"]["ownership"], False)
        self.assertEqual(
            state["audio"]["input"]["owner"]["value"], "bx1-web.service"
        )
        self.assertEqual(
            state["audio"]["input"]["level_rms"]["value"], -36.2
        )
        self.assertEqual(
            state["audio"]["input"]["measurement_state"]["value"],
            "proxied_from_robot_body",
        )
        self.assertEqual(
            state["audio"]["input"]["last_sample_timestamp"]["value"],
            99.9,
        )
        self.assertTrue(state["robot_body"]["connected"]["value"])

    def test_read_only_hardware_audio_and_robot_body_apis(self):
        application = ManagementApplication(
            qualification_config(), core=self.core
        )
        server = ManagementServer(application, host="127.0.0.1", port=0)
        server.start()
        self.addCleanup(server.stop)
        base = "http://127.0.0.1:%s" % server.port
        schemas = {
            "/api/core/hardware": "bx1.core.hardware.v1",
            "/api/core/hardware/inventory": "bx1.core.hardware.inventory.api.v1",
            "/api/core/audio": "bx1.core.audio.v1",
            "/api/core/audio/devices": "bx1.core.audio.devices.v1",
            "/api/core/robot-body": "bx1.core.robot_body.v1",
            "/api/core/robot-body/health": "bx1.core.robot_body.health.v1",
        }
        for path, schema in schemas.items():
            with urllib.request.urlopen(base + path, timeout=3) as response:
                value = json.loads(response.read())
            self.assertEqual(value["schema"], schema)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            request = urllib.request.Request(
                base + "/api/core/audio",
                data=b"{}",
                method=method,
            )
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request, timeout=3)
            self.assertEqual(rejected.exception.code, 501)


class SourceSafetyTests(unittest.TestCase):
    def test_hardware_layer_contains_no_device_open_or_write_capability(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((PYTHON_ROOT / "bx1_core" / "hardware").glob("*.py"))
        )
        for forbidden in (
            "subprocess",
            "os.open(",
            "serial.Serial",
            ".write_text(",
            ".write_bytes(",
            "systemctl",
            "amixer set",
            "arecord -",
            "aplay ",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn('method="POST"', source)
        self.assertIn('method="GET"', source)

    def test_ui_has_audio_navigation_missing_and_owned_states(self):
        source = (
            PYTHON_ROOT / "bx1_management" / "static" / "app.js"
        ).read_text(encoding="utf-8")
        self.assertIn('id: "audio", label: "Audio"', source)
        self.assertIn("No devices detected", source)
        self.assertIn("Owned by Robot Body", source)
        self.assertIn("Measurement unavailable while owned", source)
        self.assertIn("Future controlled operation", source)
        self.assertIn('"/api/core/audio"', source)


if __name__ == "__main__":
    unittest.main()
