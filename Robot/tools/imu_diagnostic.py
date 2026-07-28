#!/usr/bin/env python3
"""Read-only BX1 IMU diagnostic through the existing MCU Router bridge."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from hardware_bridge import BX1HardwareBridge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--interval", type=float, default=0.02)
    args = parser.parse_args()
    bridge = BX1HardwareBridge()
    scan = bridge.call("bx1_i2c_scan")
    readings, times = [], []
    for _ in range(max(2, args.samples)):
        state = bridge.get_status()
        accel = state.get("accel_g") if isinstance(state.get("accel_g"), dict) else {}
        gyro = state.get("gyro_dps") if isinstance(state.get("gyro_dps"), dict) else {}
        readings.append({
            "ax": accel.get("x"), "ay": accel.get("y"), "az": accel.get("z"),
            "gyro_roll": gyro.get("roll"), "gyro_pitch": gyro.get("pitch"),
            "gyro_yaw": gyro.get("yaw"),
            **{key: state.get(key) for key in
               ("imu_last_update_age_ms", "imu_ok", "imu_error", "imu_address")},
        })
        times.append(time.monotonic())
        time.sleep(max(0.005, args.interval))
    intervals = [b - a for a, b in zip(times, times[1:])]
    last = bridge.get_status()
    ages = [row.get("imu_last_update_age_ms") for row in readings
            if isinstance(row.get("imu_last_update_age_ms"), (int, float))]
    stale = bool(ages and (max(ages) > max(250.0, args.interval * 5000.0) or len(set(ages)) == 1))
    scan_value = scan.value
    if scan.ok and isinstance(scan_value, str):
        try:
            scan_value = json.loads(scan_value)
        except json.JSONDecodeError:
            scan_value = {"ok": False, "error": "MCU returned non-JSON scan data", "raw": scan_value}
    result = {
        "schema": "bx1.imu_diagnostic.v1",
        "read_only": True,
        "balance_control_enabled": False,
        "i2c_scan": scan_value if scan.ok else {"ok": False, "error": scan.error},
        "imu_initialisation_result": {"ok": bool(last.get("imu_ok")), "error": last.get("imu_error", "")},
        "imu_bus": last.get("imu_bus", "Wire1/Qwiic"),
        "imu_address": last.get("imu_address", "unknown"),
        "processor_context": "STM32 MCU firmware, observed from UNO Q Linux via Router RPC",
        "axis_mapping": {
            "accelerometer": {"x": "ax", "y": "ay", "z": "az", "unit": "g"},
            "gyroscope": {"roll": "gyro_roll", "pitch": "gyro_pitch", "yaw": "gyro_yaw", "unit": "deg/s"},
        },
        "latest_sample": readings[-1],
        "requested_sample_interval_s": args.interval,
        "measured_median_interval_s": round(statistics.median(intervals), 6),
        "estimated_sample_rate_hz": round(1.0 / statistics.median(intervals), 2),
        "stale_sample_detected": stale,
        "sample_count": len(readings),
    }
    print(json.dumps(result, indent=2))
    return 0 if last.get("imu_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
