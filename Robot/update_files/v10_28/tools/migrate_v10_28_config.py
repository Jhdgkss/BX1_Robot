#!/usr/bin/env python3
"""Migrate BX1 body configuration to v10.28 without losing calibration.

The migration preserves the Brain address, microphone device, servo trims, LED
ranges and other user values. It changes only known v10.26 defaults that caused
lost first words, false visual 'alone' status or inaccessible idle-life controls.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

VERSION = "10.28"
NATURAL_WAKE_WORDS = ["hello", "hey", "robot"]
SERVO_PINS = {"head_yaw": 9, "gimbal_left": 10, "gimbal_right": 11}
LEGACY_SERVO_PINS = {"head_yaw": 9, "head_pitch": 10, "head_roll": 11}
VISION_PHRASES = [
    "what can you see", "look around", "describe what you see", "describe this", "describe that",
    "use your camera", "use the camera", "check the camera", "take a look", "look at this", "look here",
    "can you see this", "what is this", "what's this", "what is that", "what's that",
    "what am i holding", "what is in my hand", "what's in my hand", "what do i have here",
    "what am i showing you", "what object is this", "identify this", "identify what i am holding",
    "look at my hand", "look at this in my hand", "camera view", "show you this",
    "tell me what this is", "can you tell me what this is", "do you recognise this",
    "do you recognize this", "who is this", "who is that",
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


def float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def int_value(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def replace_old_default(cfg: Dict[str, Any], key: str, old: Any, new: Any) -> None:
    """Upgrade only missing values or values still equal to the old shipped default."""
    if key not in cfg or cfg.get(key) == old:
        cfg[key] = new


def ensure_servo_mapping(cfg: Dict[str, Any]) -> None:
    registry = cfg.get("hardware_registry")
    if not isinstance(registry, dict):
        registry = {}
        cfg["hardware_registry"] = registry
    servos = registry.get("servos")
    if not isinstance(servos, dict):
        servos = {}
        registry["servos"] = servos
    for name, pin in SERVO_PINS.items():
        item = servos.get(name)
        if not isinstance(item, dict):
            item = {}
            servos[name] = item
        item["enabled"] = bool(item.get("enabled", True))
        item["pin"] = pin
        if name == "head_yaw":
            item["invert"] = True

    legacy = cfg.get("hardware_map")
    if not isinstance(legacy, dict):
        legacy = {}
        cfg["hardware_map"] = legacy
    for name, pin in LEGACY_SERVO_PINS.items():
        item = legacy.get(name)
        if not isinstance(item, dict):
            item = {}
            legacy[name] = item
        item["enabled"] = bool(item.get("enabled", True))
        item["pin"] = pin
        if name == "head_yaw":
            item["invert"] = True


def migrate(config_path: Path, defaults_path: Path | None = None) -> Dict[str, Any]:
    current = load_json(config_path)
    defaults = load_json(defaults_path)
    if not current:
        current = copy.deepcopy(defaults)
    elif defaults:
        merge_missing(current, defaults)

    current["web_enabled"] = True
    current["web_host"] = str(current.get("web_host") or "0.0.0.0")
    current["web_port"] = int_value(current.get("web_port"), 8088)
    current["input_mode"] = "both"
    current["voice_enabled"] = True

    wake = current.get("wake_words")
    if isinstance(wake, str):
        wake = [x.strip().lower() for x in wake.replace(",", "\n").splitlines() if x.strip()]
    elif isinstance(wake, list):
        wake = [str(x).strip().lower() for x in wake if str(x).strip()]
    else:
        wake = []
    legacy_only = not wake or all(x in {"bx1", "be ex one", "leo"} for x in wake)
    if legacy_only:
        wake = []
    # Keep user additions, but always install the natural default wake words.
    current["wake_words"] = list(dict.fromkeys(list(NATURAL_WAKE_WORDS) + wake))

    # Protect sentence beginnings/endings and reduce speech damage from strong NR.
    replace_old_default(current, "stt_pre_roll_ms", 450, 700)
    replace_old_default(current, "stt_end_silence_ms", 1100, 1350)
    replace_old_default(current, "stt_post_roll_ms", 250, 300)
    replace_old_default(current, "stt_start_trigger_ms", 100, 80)
    replace_old_default(current, "audio_noise_reduction_strength", 0.45, 0.20)
    current["audio_noise_reduction_strength"] = min(0.20, max(0.0, float_value(current.get("audio_noise_reduction_strength"), 0.20)))
    replace_old_default(current, "stt_min_confidence", 0.45, 0.40)
    replace_old_default(current, "stt_min_voiced_ms", 320, 280)
    current["stt_endpointing_enabled"] = bool(current.get("stt_endpointing_enabled", True))
    current["stt_adaptive_threshold_enabled"] = bool(current.get("stt_adaptive_threshold_enabled", True))
    current["stt_debug_keep_audio"] = True

    # Use the improved model automatically when it has already been installed.
    project_root = config_path.parent.parent
    improved_model = project_root / "models" / "vosk-model-en-us-0.22-lgraph"
    if (improved_model / "am").is_dir() and (improved_model / "conf").is_dir():
        current["vosk_model_path"] = "models/vosk-model-en-us-0.22-lgraph"

    current["mouth_audio_reactive_enabled"] = True
    current["mouth_audio_use_wav_profile"] = True
    current["voice_feedback_led_enabled"] = True

    ensure_servo_mapping(current)

    current["camera_enabled"] = True
    current["auto_camera_on_vision_request"] = True
    current["send_periodic_camera_frames"] = bool(current.get("send_periodic_camera_frames", True))
    current["periodic_camera_frame_interval_s"] = max(2.0, float_value(current.get("periodic_camera_frame_interval_s"), 5.0))
    current["camera_live_preview_enabled"] = bool(current.get("camera_live_preview_enabled", True))
    current["camera_live_preview_interval_s"] = max(1.0, min(30.0, float_value(current.get("camera_live_preview_interval_s"), 2.0)))
    current["camera_preview_max_age_s"] = max(0.5, min(30.0, float_value(current.get("camera_preview_max_age_s"), 4.0)))
    current["visual_awareness_enabled"] = bool(current.get("visual_awareness_enabled", True))
    current["visual_awareness_interval_s"] = max(0.75, float_value(current.get("visual_awareness_interval_s"), 2.0))
    current["visual_motion_threshold"] = max(0.005, min(0.30, float_value(current.get("visual_motion_threshold"), 0.035)))
    current["visual_presence_hold_s"] = max(1.0, float_value(current.get("visual_presence_hold_s"), 4.0))
    current["visual_alone_timeout_s"] = max(5.0, float_value(current.get("visual_alone_timeout_s"), 20.0))
    current["visual_wake_on_person"] = bool(current.get("visual_wake_on_person", True))
    current["visual_wake_window_s"] = max(5.0, float_value(current.get("visual_wake_window_s"), 20.0))
    current["visual_send_event_frames"] = bool(current.get("visual_send_event_frames", True))
    current["visual_analysis_width"] = max(160, min(640, int_value(current.get("visual_analysis_width"), 320)))

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

    # Body triggers the phase; desktop Brain supplies personality and wording.
    replace_old_default(current, "idle_life_micro_action_delay_s", 120.0, 60.0)
    replace_old_default(current, "idle_life_comment_delay_s", 300.0, 180.0)
    current["idle_life_enabled"] = True
    current["idle_life_micro_actions_enabled"] = True
    current["idle_life_self_chatter_enabled"] = True
    current["idle_life_response_mode"] = "brain"
    current["idle_life_require_alone"] = bool(current.get("idle_life_require_alone", True))
    current["idle_life_brain_prompt"] = str(current.get("idle_life_brain_prompt", "") or "")
    current["brain_controls_idle_dialogue"] = True
    current["idle_life_event_provenance_enabled"] = True

    current["version"] = VERSION
    current["app_version"] = VERSION

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = config_path.with_name(f"{config_path.name}.before_v10_28_{stamp}")
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
    print("Speech: longer pre-roll/end-silence and gentler noise reduction")
    print("Vision: cached live preview; unknown presence is no longer reported as alone")
    print("Idle life: body timer + desktop Brain personality responses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
