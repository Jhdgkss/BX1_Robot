#!/usr/bin/env python3
"""Migrate an existing BX1 body configuration to v10.25.

The migration preserves network addresses, audio devices, servo trims/ranges,
LED zone addresses and other calibrated values. It deliberately activates the
local web interface and live voice listener, sets natural wake words, and fixes
the confirmed BX1 head GPIO mapping.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

WAKE_WORDS = ["hello", "hey", "robot"]
SERVO_PINS = {"head_yaw": 9, "gimbal_left": 10, "gimbal_right": 11}
LEGACY_SERVO_PINS = {"head_yaw": 9, "head_pitch": 10, "head_roll": 11}


def load_json(path: Path | None) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Config root must be a JSON object: {path}")
    return value


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def seed_dict(parent: Dict[str, Any], key: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = copy.deepcopy(defaults)
        parent[key] = value
    return value


def migrate(config_path: Path, defaults_path: Path | None = None) -> Dict[str, Any]:
    current = load_json(config_path)
    defaults = load_json(defaults_path)
    if not current:
        current = copy.deepcopy(defaults)

    # Startup behaviour requested for the robot body.
    current["web_enabled"] = True
    current["web_host"] = str(current.get("web_host") or "0.0.0.0")
    current["web_port"] = int(current.get("web_port") or 8088)
    current["input_mode"] = "both"
    current["voice_enabled"] = True
    current["wake_words"] = list(WAKE_WORDS)
    current["voice_feedback_led_enabled"] = True
    current["mouth_audio_reactive_enabled"] = True
    current["mouth_audio_use_wav_profile"] = True
    current["expression_engine_enabled"] = True

    default_registry = as_dict(defaults.get("hardware_registry"))
    registry = seed_dict(current, "hardware_registry", default_registry)
    registry.setdefault("schema", "bx1.hardware_registry.v1")

    default_servos = as_dict(default_registry.get("servos"))
    servos = seed_dict(registry, "servos", default_servos)
    for name, pin in SERVO_PINS.items():
        item = seed_dict(servos, name, as_dict(default_servos.get(name)))
        item["enabled"] = True
        item["pin"] = pin
        if name == "head_yaw":
            item["invert"] = True

    # Retain the legacy mirror for older code/firmware paths.
    default_legacy = as_dict(defaults.get("hardware_map"))
    legacy = seed_dict(current, "hardware_map", default_legacy)
    for name, pin in LEGACY_SERVO_PINS.items():
        item = seed_dict(legacy, name, as_dict(default_legacy.get(name)))
        item["enabled"] = True
        item["pin"] = pin
        if name == "head_yaw":
            item["invert"] = True

    default_buses = as_dict(default_registry.get("led_buses"))
    buses = seed_dict(registry, "led_buses", default_buses)
    main_bus = seed_dict(buses, "main", as_dict(default_buses.get("main")))
    main_bus["enabled"] = True
    try:
        main_bus["data_pin"] = int(main_bus.get("data_pin", 3))
    except (TypeError, ValueError):
        main_bus["data_pin"] = 3
    if main_bus["data_pin"] < 0:
        main_bus["data_pin"] = 3

    default_zones = as_dict(default_registry.get("led_zones"))
    zones = seed_dict(registry, "led_zones", default_zones)
    highest_address = 3
    for zone_name in ("mouth", "left_eye", "right_eye", "chest", "status"):
        zone = seed_dict(zones, zone_name, as_dict(default_zones.get(zone_name)))
        if zone_name in {"mouth", "left_eye", "right_eye"}:
            zone["enabled"] = True
        try:
            highest_address = max(highest_address, int(zone.get("end", 1)))
        except (TypeError, ValueError):
            pass
    try:
        main_bus["total_pixels"] = max(highest_address, min(500, int(main_bus.get("total_pixels", highest_address))))
    except (TypeError, ValueError):
        main_bus["total_pixels"] = highest_address
    try:
        if float(main_bus.get("brightness_limit", 0.0)) <= 0.0:
            main_bus["brightness_limit"] = 0.60
    except (TypeError, ValueError):
        main_bus["brightness_limit"] = 0.60

    # Ensure state profiles exist without replacing user-edited colours.
    if not isinstance(current.get("led_state_profiles"), dict):
        profiles = defaults.get("led_state_profiles")
        if isinstance(profiles, dict):
            current["led_state_profiles"] = copy.deepcopy(profiles)

    current["version"] = "10.25"
    current["app_version"] = "10.25"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = config_path.with_name(f"{config_path.name}.before_v10_25_{stamp}")
        shutil.copy2(config_path, backup)
        print(f"Config backup: {backup}")

    config_path.write_text(json.dumps(current, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path, help="Existing python/config.json")
    parser.add_argument("--defaults", type=Path, default=None, help="Packaged v10.25 default config")
    args = parser.parse_args()
    cfg = migrate(args.config, args.defaults)
    print(f"Migrated {args.config} to BX1 v{cfg.get('version')}")
    print("Live voice: enabled; wake words: Hello / Hey / Robot")
    print("Head servos: D9 yaw (reversed), D10 left gimbal, D11 right gimbal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
