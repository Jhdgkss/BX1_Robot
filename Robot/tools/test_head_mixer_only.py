#!/usr/bin/env python3
"""BX1 v10.22.1 logical head mixer bench test.

Runs only bounded head commands through the local web API. It does not change
GPIO assignments, servo limits, firmware, or the persistent Arduino App.
"""
from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://127.0.0.1:8088"


def request_json(path: str, payload: dict | None = None, timeout: float = 15.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def print_state(label: str) -> None:
    data = request_json("/api/status")
    state = data.get("state", {})
    pins = state.get("head_servo_pins", {})
    targets = state.get("head_gimbal_targets_deg", {})
    print(f"\n{label}")
    print("  MCU:", state.get("mcu_ok"), "firmware:", state.get("firmware_version"))
    print("  Mode:", state.get("mode"))
    print("  Pins: yaw=", pins.get("yaw"), " left=", pins.get("gimbal_left"), " right=", pins.get("gimbal_right"))
    print("  Logical: yaw=", state.get("head_yaw_deg"), " pitch=", state.get("head_pitch_deg"), " roll=", state.get("head_roll_deg"))
    print("  Physical targets: left=", targets.get("left"), " right=", targets.get("right"))


def send_pose(label: str, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> None:
    result = request_json(
        "/api/action",
        {"action": {"type": "set_head_pose", "args": {"yaw_deg": yaw, "pitch_deg": pitch, "roll_deg": roll}}},
    )
    print(f"\nCommand {label}: {json.dumps(result, indent=2)[:1200]}")
    time.sleep(2.0)
    print_state(label)


if __name__ == "__main__":
    print_state("INITIAL")
    for label, yaw, pitch, roll in [
        ("CENTRE", 0, 0, 0),
        ("PITCH UP -5", 0, -5, 0),
        ("PITCH DOWN +5", 0, 5, 0),
        ("CENTRE", 0, 0, 0),
        ("ROLL LEFT -5", 0, 0, -5),
        ("ROLL RIGHT +5", 0, 0, 5),
        ("CENTRE", 0, 0, 0),
    ]:
        send_pose(label, yaw=yaw, pitch=pitch, roll=roll)
    print("\nComplete. The printed physical targets prove whether the two-servo mixer is receiving commands.")
