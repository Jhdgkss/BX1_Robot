#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

# Run from project root: .venv/bin/python tools/test_mouth_led_d3.py
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from hardware_bridge import BX1HardwareBridge

bridge = BX1HardwareBridge()
print("BX1 Mouth LED D3 Test")
print("=" * 30)
print("Bridge mode preference:", bridge.last_state.get("bridge_mode"))

config_action = {
    "type": "configure_hardware",
    "source": "local_config",
    "head_yaw_pin": -1,
    "head_pitch_pin": -1,
    "head_roll_pin": -1,
    "eyes_led_pin": -1,
    "eyes_led_count": 1,
    "mouth_led_pin": 3,
    "mouth_led_count": 1,
    "head_yaw_min_deg": -75,
    "head_yaw_max_deg": 75,
    "head_yaw_home_deg": 0,
    "head_pitch_min_deg": -45,
    "head_pitch_max_deg": 45,
    "head_pitch_home_deg": 0,
    "head_roll_min_deg": -35,
    "head_roll_max_deg": 35,
    "head_roll_home_deg": 0,
}

res = bridge.send_action(config_action)
print("Configure:", res)
if not res.ok:
    raise SystemExit(1)

def led(colour: str, brightness: float = 0.25):
    action = {"type":"set_led", "args":{"target":"mouth", "colour":colour, "brightness":brightness}}
    r = bridge.send_action(action)
    print(f"Mouth {colour}:", r.ok, r.error or r.value)
    time.sleep(0.8)

for c in ("red", "green", "blue", "cyan", "off"):
    led(c, 0.25)

status = bridge.get_status()
print("Status:")
print(json.dumps(status, indent=2))
print("RESULT:", "PASS" if status.get("mcu_ok") else "CHECK STATUS")
