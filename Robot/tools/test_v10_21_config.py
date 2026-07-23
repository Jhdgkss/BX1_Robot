#!/usr/bin/env python3
"""Offline v10.21 configuration smoke test. Does not access physical hardware."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
sys.path.insert(0, str(PYTHON_DIR))
spec = importlib.util.spec_from_file_location("bx1_body_main", PYTHON_DIR / "main.py")
if spec is None or spec.loader is None:
    raise SystemExit("Could not load python/main.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

config = json.loads((PYTHON_DIR / "config.json").read_text(encoding="utf-8"))
registry = module.normalise_hardware_registry(config.get("hardware_registry", {}))
packet = module.flatten_hardware_registry_for_mcu(registry)
profiles = module.normalise_led_state_profiles(config.get("led_state_profiles", {}))

required_packet = {
    "head_gimbal_left_pin", "head_gimbal_right_pin", "head_pitch_gain", "head_roll_gain",
    "head_left_pitch_sign", "head_right_pitch_sign", "head_left_roll_sign", "head_right_roll_sign",
}
missing = sorted(required_packet.difference(packet))
if missing:
    raise SystemExit(f"FAIL: missing MCU mixer packet fields: {missing}")

for state in module.LED_STATE_ORDER:
    if state not in profiles:
        raise SystemExit(f"FAIL: missing LED state profile: {state}")
    for zone in module.LED_ZONE_ORDER:
        item = profiles[state]["zones"].get(zone)
        if not isinstance(item, dict) or not str(item.get("colour", "")).startswith("#"):
            raise SystemExit(f"FAIL: invalid LED profile: {state}/{zone}")

print("PASS: v10.21 mixed-gimbal registry and LED state profiles are valid.")
print(json.dumps({
    "version": config.get("app_version"),
    "physical_servos": registry.get("servos"),
    "head_kinematics": registry.get("head_kinematics"),
    "led_states": list(profiles),
}, indent=2))
