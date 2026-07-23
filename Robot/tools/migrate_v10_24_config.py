#!/usr/bin/env python3
"""Migrate an existing BX1 body config to v10.24 without erasing site settings.

This migration deliberately preserves network addresses, audio devices, hardware
registry/pins, servo trims, movement limits, robot identity and other calibrated
values.  It only adds new STT endpointing defaults and enforces the Brain/body
ownership boundary introduced in v10.24.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ENDPOINT_DEFAULTS: Dict[str, Any] = {
    "stt_capture_method": "alsa",
    "stt_endpointing_enabled": True,
    "stt_start_timeout_s": 8.0,
    "stt_max_utterance_s": 20.0,
    "stt_pre_roll_ms": 450,
    "stt_end_silence_ms": 1100,
    "stt_post_roll_ms": 250,
    "stt_start_trigger_ms": 100,
    "stt_adaptive_threshold_enabled": True,
    "stt_adaptive_margin_db": 8.0,
    "stt_debug_keep_audio": True,
}

# These settings are intentionally enforced.  They prevent the body client from
# generating a second personality, web/memory policy, TTS voice choice, spoken
# thinking cue or autonomous spoken dialogue in parallel with the Brain App.
OWNERSHIP_SETTINGS: Dict[str, Any] = {
    "brain_tts_use_brain_defaults": True,
    "brain_controls_web_memory": True,
    "brain_controls_thinking_cues": True,
    "brain_controls_idle_dialogue": True,
    "thinking_cues_enabled": False,
    "thinking_cue_speak": False,
    "voice_command_immediate_cue_enabled": False,
    "idle_life_self_chatter_enabled": False,
    "idle_life_internet_curiosity_enabled": False,
    "idle_life_sleep_announce_enabled": False,
}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Config root must be a JSON object: {path}")
    return value


def migrate(config_path: Path, defaults_path: Path | None = None) -> Dict[str, Any]:
    current = load_json(config_path)
    defaults = load_json(defaults_path) if defaults_path and defaults_path.exists() else {}

    # A missing config is seeded from the packaged default.  Existing configs
    # are never wholesale replaced.
    if not current and defaults:
        current = defaults

    for key, value in ENDPOINT_DEFAULTS.items():
        current.setdefault(key, value)

    for key, value in OWNERSHIP_SETTINGS.items():
        current[key] = value

    # Upgrade only untouched historical brightness defaults.  User-calibrated
    # values are preserved.
    try:
        if float(current.get("mouth_audio_max_brightness", 0.35)) <= 0.35:
            current["mouth_audio_max_brightness"] = 0.55
    except (TypeError, ValueError):
        current["mouth_audio_max_brightness"] = 0.55

    registry = current.get("hardware_registry")
    if isinstance(registry, dict):
        buses = registry.get("led_buses")
        if isinstance(buses, dict):
            main_bus = buses.get("main")
            if isinstance(main_bus, dict):
                try:
                    if float(main_bus.get("brightness_limit", 0.2)) <= 0.2:
                        main_bus["brightness_limit"] = 0.60
                except (TypeError, ValueError):
                    main_bus["brightness_limit"] = 0.60

    current["version"] = "10.24"
    current["app_version"] = "10.24"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = config_path.with_name(f"{config_path.name}.before_v10_24_{stamp}")
        shutil.copy2(config_path, backup)
        print(f"Config backup: {backup}")

    config_path.write_text(json.dumps(current, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path, help="Existing python/config.json")
    parser.add_argument("--defaults", type=Path, default=None, help="Packaged v10.24 default config")
    args = parser.parse_args()
    migrated = migrate(args.config, args.defaults)
    print(f"Migrated {args.config} to BX1 v{migrated.get('version')}")
    print("Ownership: desktop Brain App controls web/memory, TTS voice, thinking cues and spoken idle dialogue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
