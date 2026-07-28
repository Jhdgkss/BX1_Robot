#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from hardware_doctor import BX1HardwareDoctor  # noqa: E402
from hardware_freshness import HardwareFreshnessTracker  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, value: float) -> None:
        self.value += value / 1000.0


def frame(heartbeat=1, sample=1, age=20, *, initialised=True):
    return {
        "heartbeat_sequence": heartbeat,
        "imu_sample_sequence": sample,
        "imu_last_update_age_ms": age,
        "imu_address": "0x6A",
        "imu_ok": initialised,
        "imu_error": "",
        "imu_read_failures": 0,
        "accel_g": {"x": 0, "y": 0, "z": 1},
        "gyro_dps": {"roll": 0, "pitch": 0, "yaw": 0},
    }


class FreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.tracker = HardwareFreshnessTracker(warning_ms=250, stale_ms=1000, clock=self.clock)

    def test_fresh_mcu_and_imu(self):
        out = self.tracker.evaluate(frame(), transport_connected=True)
        self.assertTrue(out["mcu_heartbeat_fresh"])
        self.assertTrue(out["imu_healthy"])
        self.assertTrue(out["imu_ok"])
        self.assertFalse(out["balance_ready"])

    def test_router_connected_but_heartbeat_stale(self):
        self.tracker.evaluate(frame(), transport_connected=True)
        self.clock.advance_ms(1001)
        out = self.tracker.evaluate(frame(), transport_connected=True)
        self.assertTrue(out["mcu_transport_connected"])
        self.assertFalse(out["mcu_heartbeat_fresh"])
        self.assertTrue(out["mcu_data_stale"])
        self.assertFalse(out["imu_healthy"])

    def test_mcu_fresh_but_imu_stale(self):
        self.tracker.evaluate(frame(), transport_connected=True)
        self.clock.advance_ms(1001)
        out = self.tracker.evaluate(frame(heartbeat=2), transport_connected=True)
        self.assertTrue(out["mcu_heartbeat_fresh"])
        self.assertFalse(out["imu_sample_fresh"])
        self.assertIn("stale", out["imu_health_reason"])

    def test_not_initialised(self):
        out = self.tracker.evaluate(frame(initialised=False), transport_connected=True)
        self.assertFalse(out["imu_initialised"])
        self.assertFalse(out["imu_healthy"])
        self.assertEqual(out["imu_health_reason"], "IMU not initialised")

    def test_cached_payload_does_not_refresh(self):
        payload = frame()
        self.tracker.evaluate(payload, transport_connected=True)
        self.clock.advance_ms(900)
        self.tracker.evaluate(payload, transport_connected=True)
        self.clock.advance_ms(101)
        out = self.tracker.evaluate(payload, transport_connected=True)
        self.assertTrue(out["mcu_data_stale"])
        self.assertTrue(out["imu_data_stale"])

    def test_new_sequences_refresh(self):
        self.tracker.evaluate(frame(), transport_connected=True)
        self.clock.advance_ms(900)
        out = self.tracker.evaluate(frame(heartbeat=2, sample=2), transport_connected=True)
        self.assertEqual(out["mcu_last_update_age_ms"], 0.0)
        self.assertTrue(out["imu_healthy"])

    def test_counter_rollover_refreshes(self):
        self.tracker.evaluate(frame(heartbeat=0xFFFFFFFF, sample=0xFFFFFFFF), transport_connected=True)
        self.clock.advance_ms(900)
        out = self.tracker.evaluate(frame(heartbeat=0, sample=0), transport_connected=True)
        self.assertTrue(out["mcu_heartbeat_fresh"])
        self.assertTrue(out["imu_healthy"])

    def test_missing_age_is_not_fresh(self):
        payload = frame()
        payload.pop("imu_last_update_age_ms")
        out = self.tracker.evaluate(payload, transport_connected=True)
        self.assertFalse(out["imu_sample_fresh"])
        self.assertIn("missing", out["imu_health_reason"])

    def test_negative_and_malformed_age_are_not_fresh(self):
        for age in (-1, "bad"):
            tracker = HardwareFreshnessTracker(clock=self.clock)
            out = tracker.evaluate(frame(age=age), transport_connected=True)
            self.assertFalse(out["imu_healthy"])

    def test_compatibility_imu_ok_maps_to_health(self):
        out = self.tracker.evaluate(frame(age=5000), transport_connected=True)
        self.assertFalse(out["imu_healthy"])
        self.assertFalse(out["imu_ok"])


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_stale_heartbeat_reason(self):
        state = frame()
        state.update({
            "mcu_transport_connected": True,
            "mcu_heartbeat_fresh": False,
            "mcu_data_stale": True,
            "mcu_last_update_age_ms": 21084941,
            "mcu_health_reason": "MCU heartbeat stale for 21084941 ms",
            "mcu_ok": False,
            "imu_present": True,
            "imu_initialised": True,
            "imu_sample_fresh": False,
            "imu_healthy": False,
            "imu_health_reason": "MCU heartbeat stale",
        })
        with tempfile.TemporaryDirectory() as tmp:
            doctor = BX1HardwareDoctor(object(), Path(tmp), {})
            socket_context = MagicMock()
            socket_context.__enter__.return_value = MagicMock()
            with patch("hardware_doctor.os.path.exists", return_value=True), \
                 patch("hardware_doctor.socket.AF_UNIX", 1, create=True), \
                 patch("hardware_doctor.socket.socket", return_value=socket_context), \
                 patch.object(doctor, "_service_state", return_value={"available": True, "active": True}):
                report = doctor.diagnose(state)
        self.assertEqual(report["severity"], "fault")
        self.assertIn("21084941", report["summary"])
        self.assertFalse(report["evidence"]["mcu_heartbeat_fresh"])
        self.assertFalse(report["evidence"]["imu_healthy"])


if __name__ == "__main__":
    unittest.main()
