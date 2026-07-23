#!/usr/bin/env python3
"""Migrate BX1 body configuration to v10.26.

Preserves calibrated microphone, servo, LED and network values while enabling
reactive speech lighting, natural visual requests, passive camera frames and
lightweight local visual awareness.
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
VISION_PHRASES = [
    "what can you see", "look around", "describe what you see", "describe this", "describe that",
    "use your camera", "use the camera", "check the camera", "take a look", "look at this", "look here",
    "can you see this", "what is this", "what's this", "what is that", "what's that",
    "what am i holding", "what is in my hand", "what's in my hand", "what do i have here",
    "what am i showing you", "identify this", "look at my hand", "tell me what this is",
    "can you tell me what this is", "do you recognise this", "do you recognize this",
    "who is this", "who is that",
]


def load_json(path: Path | None) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Config root must be a JSON object: {path}")
    return value


def merge_missing(target: Dict[str, Any], defaults: Dict[str, Any]) -> None:
    for key, value in defaults.items():
        if key not in target:
            target[key] = copy.deepcopy(value)
        elif isinstance(target.get(key), dict) and isinstance(value, dict):
            merge_missing(target[key], value)


def migrate(config_path: Path, defaults_path: Path | None = None) -> Dict[str, Any]:
    current = load_json(config_path)
    defaults = load_json(defaults_path)
    if not current:
        current = copy.deepcopy(defaults)
    elif defaults:
        merge_missing(current, defaults)

    current["web_enabled"] = True
    current["web_host"] = str(current.get("web_host") or "0.0.0.0")
    current["web_port"] = int(current.get("web_port") or 8088)
    current["input_mode"] = "both"
    current["voice_enabled"] = True
    current["wake_words"] = list(WAKE_WORDS)

    current["mouth_audio_reactive_enabled"] = True
    current["mouth_audio_use_wav_profile"] = True
    current["mouth_audio_off_after_speech"] = bool(current.get("mouth_audio_off_after_speech", False))
    current["voice_feedback_led_enabled"] = True

    registry = current.get("hardware_registry")
    if not isinstance(registry, dict):
        registry = {}
        current["hardware_registry"] = registry
    servos = registry.get("servos")
    if not isinstance(servos, dict):
        servos = {}
        registry["servos"] = servos
    for name, pin in SERVO_PINS.items():
        item = servos.get(name)
        if not isinstance(item, dict):
            item = {}
            servos[name] = item
        item["enabled"] = True
        item["pin"] = pin
        if name == "head_yaw":
            item["invert"] = True

    legacy = current.get("hardware_map")
    if not isinstance(legacy, dict):
        legacy = {}
        current["hardware_map"] = legacy
    for name, pin in LEGACY_SERVO_PINS.items():
        item = legacy.get(name)
        if not isinstance(item, dict):
            item = {}
            legacy[name] = item
        item["enabled"] = True
        item["pin"] = pin
        if name == "head_yaw":
            item["invert"] = True

    current["camera_enabled"] = True
    current["auto_camera_on_vision_request"] = True
    current["send_periodic_camera_frames"] = True
    current["periodic_camera_frame_interval_s"] = max(2.0, float(current.get("periodic_camera_frame_interval_s", 5.0) or 5.0))
    current["visual_awareness_enabled"] = True
    current["visual_awareness_interval_s"] = max(0.75, float(current.get("visual_awareness_interval_s", 2.0) or 2.0))
    current["visual_motion_threshold"] = max(0.005, min(0.30, float(current.get("visual_motion_threshold", 0.035) or 0.035)))
    current["visual_presence_hold_s"] = max(1.0, float(current.get("visual_presence_hold_s", 4.0) or 4.0))
    current["visual_alone_timeout_s"] = max(5.0, float(current.get("visual_alone_timeout_s", 20.0) or 20.0))
    current["visual_wake_on_person"] = bool(current.get("visual_wake_on_person", True))
    current["visual_wake_window_s"] = max(5.0, float(current.get("visual_wake_window_s", 20.0) or 20.0))
    current["visual_send_event_frames"] = bool(current.get("visual_send_event_frames", True))
    current["visual_analysis_width"] = max(160, min(640, int(current.get("visual_analysis_width", 320) or 320)))

    existing = current.get("vision_trigger_phrases", [])
    if isinstance(existing, str):
        existing = [x.strip() for x in existing.replace(",", "\n").splitlines() if x.strip()]
    elif not isinstance(existing, list):
        existing = []
    phrases: list[str] = []
    for phrase in list(VISION_PHRASES) + [str(x).strip().lower() for x in existing]:
        phrase = str(phrase).strip().lower()
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    current["vision_trigger_phrases"] = phrases

    current["version"] = "10.26"
    current["app_version"] = "10.26"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = config_path.with_name(f"{config_path.name}.before_v10_26_{stamp}")
        shutil.copy2(config_path, backup)
        print(f"Config backup: {backup}")

    config_path.write_text(json.dumps(current, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--defaults", type=Path, default=None)
    args = parser.parse_args()
    cfg = migrate(args.config, args.defaults)
    print(f"Migrated {args.config} to BX1 v{cfg.get('version')}")
    print("Live listening: enabled; wake words: Hello / Hey / Robot")
    print("Camera: natural visual triggers + passive Brain frames + local face/motion awareness")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
