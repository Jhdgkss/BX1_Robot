from __future__ import annotations

import json
import hashlib
import importlib.util
import io
import math
import os
import uuid
import random
import re
import shutil
import signal
import sys
import threading
import queue
import time
import tempfile
import textwrap
import wave
import urllib.error
import urllib.request
from array import array
from collections import deque
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from arduino.app_utils import App  # type: ignore
    APP_LAB_AVAILABLE = True
except Exception:
    App = None  # type: ignore
    APP_LAB_AVAILABLE = False

from audio_io import (
    AlsaMicrophoneMonitor,
    AudioConfig,
    analyse_wav_file,
    analyse_wav_diagnostics,
    analyse_transcript_quality,
    build_audio_dsp_settings,
    TextToSpeech,
    VoskSpeechToText,
    list_audio_capture_devices,
    list_audio_playback_devices,
    list_elevenlabs_voices,
    play_audio_file,
    record_microphone_sample,
    set_alsa_capture_volume,
    transcribe_wav_with_vosk,
)
from bx1_robot_client import BX1BrainClient, BrainClientConfig, now_iso
from camera_io import CameraCapture, CameraConfig
from hardware_bridge import BX1HardwareBridge
from hardware_doctor import BX1HardwareDoctor
from location_io import LocationProvider
from web_control import WebControlServer

def _read_startup_options(argv: List[str]) -> Dict[str, str]:
    opts = {
        "config_path": os.environ.get("BX1_BODY_CONFIG", ""),
        "web_host": os.environ.get("BX1_WEB_HOST", ""),
        "web_port": os.environ.get("BX1_WEB_PORT", ""),
        "web_enabled": os.environ.get("BX1_WEB_ENABLED", ""),
        "brain_url": os.environ.get("BX1_BRAIN_URL", ""),
        "body_id": os.environ.get("BX1_BODY_ID", ""),
    }
    i = 1
    while i < len(argv):
        arg = argv[i]
        def take_value() -> str:
            nonlocal i
            if "=" in arg:
                return arg.split("=", 1)[1]
            if i + 1 >= len(argv):
                return ""
            i += 1
            return argv[i]
        if arg.startswith("--config"):
            opts["config_path"] = take_value()
        elif arg.startswith("--web-host"):
            opts["web_host"] = take_value()
        elif arg.startswith("--web-port") or arg.startswith("--port"):
            opts["web_port"] = take_value()
        elif arg == "--web-enabled" or arg == "--web":
            opts["web_enabled"] = "1"
        elif arg == "--no-web":
            opts["web_enabled"] = "0"
        elif arg.startswith("--brain-url") or arg.startswith("--brain-base-url"):
            opts["brain_url"] = take_value()
        elif arg.startswith("--body-id") or arg.startswith("--robot-id"):
            opts["body_id"] = take_value()
        i += 1
    return opts


STARTUP_OPTIONS = _read_startup_options(sys.argv)
CONFIG_PATH = Path(str(STARTUP_OPTIONS.get("config_path") or Path(__file__).with_name("config.json"))).expanduser()
ROBOT_PROFILE_PATH = Path(__file__).with_name("robot_profile.deprecated.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOCAL_CUE_DIR = RUNTIME_DIR / "audio" / "cues"
LOCAL_CUE_MANIFEST = LOCAL_CUE_DIR / "manifest.json"
VOICE_FEEDBACK_DIR = RUNTIME_DIR / "audio" / "feedback"

DEFAULT_SLEEP_PHRASES = [
    "sleep",
    "go to sleep",
    "stand down",
    "stop listening",
    "that is all",
    "that's all",
    "good night",
    "goodnight",
]

DEFAULT_LOCAL_VOICE_CUES = {
    "wake_ack": "Yes John?",
    "wake_ack_02": "I'm listening.",
    "wake_ack_03": "Go ahead.",
    "sleep_ack": "Going quiet.",
    "thinking_01": "I am checking that.",
    "thinking_02": "One moment.",
    "thinking_03": "Let me look into that.",
    "thinking_04": "Small robot brain noises.",
    "thinking_05": "Working on it.",
    "heard_ack": "Understood.",
}


DEFAULT_IDLE_CHATTER_PHRASES = [
    "I am still here, quietly pretending this is a very important charging station.",
    "No urgent robot business detected. I will continue monitoring politely.",
    "I have not moved, which I believe counts as excellent balance training.",
    "Still awake. Slightly bored, but operational.",
    "I am doing a tiny systems check while I wait.",
]

DEFAULT_VISION_TRIGGER_PHRASES = [
    "what can you see",
    "look around",
    "describe what you see",
    "describe this",
    "describe that",
    "look here",
    "look at what i am showing you",
    "tell me what this is",
    "tell me what that is",
    "can you tell me what this is",
    "do you recognise this",
    "do you recognize this",
    "who is this",
    "who is that",
    "use your camera",
    "use the camera",
    "check the camera",
    "take a look",
    "look at this",
    "can you see this",
    "what is this",
    "what's this",
    "what is that",
    "what's that",
    "what am i holding",
    "what i am holding",
    "what i'm holding",
    "what i was holding",
    "what was i holding",
    "what am i holding in my hand",
    "what is in my hand",
    "what's in my hand",
    "what do i have in my hand",
    "what do i have here",
    "what am i showing you",
    "what object is this",
    "identify this",
    "identify what i am holding",
    "look at my hand",
    "look at this in my hand",
    "camera view",
    "show you this",
]


DEFAULT_HARDWARE_REGISTRY = {
    "schema": "bx1.hardware_registry.v1",
    "led_buses": {
        "main": {
            "label": "Main addressable LED chain",
            "type": "neopixel",
            "enabled": True,
            "data_pin": 3,
            "total_pixels": 100,
            "brightness_limit": 0.20,
            "colour_order": "GRB",
            "human_addressing": True,
        }
    },
    "led_zones": {
        "mouth": {"label": "Mouth", "bus": "main", "enabled": True, "start": 1, "end": 1, "default_colour": "#00ffff", "brightness": 0.20},
        "left_eye": {"label": "Left eye", "bus": "main", "enabled": True, "start": 2, "end": 2, "default_colour": "#0088ff", "brightness": 0.25},
        "right_eye": {"label": "Right eye", "bus": "main", "enabled": True, "start": 3, "end": 3, "default_colour": "#0088ff", "brightness": 0.25},
        "chest": {"label": "Chest / status", "bus": "main", "enabled": False, "start": 4, "end": 19, "default_colour": "#00ffff", "brightness": 0.20},
        "status": {"label": "Status strip", "bus": "main", "enabled": False, "start": 20, "end": 29, "default_colour": "#ff9900", "brightness": 0.20},
    },
    "servos": {
        "head_yaw": {"label": "Head rotation / yaw", "enabled": True, "pin": 9, "min_deg": -20, "home_deg": 0, "max_deg": 20, "invert": True, "speed_deg_s": 90},
        "gimbal_left": {"label": "Left push-pull gimbal servo", "enabled": True, "pin": 10, "min_deg": -20, "home_deg": 0, "max_deg": 20, "invert": False, "speed_deg_s": 75},
        "gimbal_right": {"label": "Right push-pull gimbal servo", "enabled": True, "pin": 11, "min_deg": -20, "home_deg": 0, "max_deg": 20, "invert": False, "speed_deg_s": 75},
    },
    "servo_behaviour": {
        "quiet_release_enabled": True,
        "release_after_ms": 1200,
        "pulse_deadband_us": 4,
        "note": "Release PWM after a pose settles to reduce servo buzz; disable if the head needs continuous holding torque.",
    },
    "head_kinematics": {
        "type": "dual_servo_push_pull",
        "pitch_min_deg": -10.0,
        "pitch_home_deg": 0.0,
        "pitch_max_deg": 10.0,
        "roll_min_deg": -10.0,
        "roll_home_deg": 0.0,
        "roll_max_deg": 10.0,
        "pitch_gain": 1.0,
        "roll_gain": 1.0,
        "left_pitch_sign": 1,
        "right_pitch_sign": -1,
        "left_roll_sign": 1,
        "right_roll_sign": 1,
    },
    "sensors": {
        "modulino_movement": {
            "label": "Arduino Modulino Movement IMU",
            "enabled": True,
            "driver": "Arduino_LSM6DSOX explicit Wire1",
            "bus": "Wire1/Qwiic",
            "i2c_address": "0x6A",
            "sample_rate_hz": 50,
            "use_for": ["pitch", "roll", "gyro", "motion_awareness"],
        }
    },
    "drive_buses": {
        "rs485_wheels": {
            "label": "Future closed-loop wheel steppers",
            "enabled": False,
            "motor_armed": False,
            "primary_control": "step_dir_enable_pending_confirmation",
            "diagnostics_interface": "rs485",
            "adapter": "usb_rs485_or_uart_rs485",
            "port": "",
            "baud": 115200,
            "left_motor_id": 1,
            "right_motor_id": 2,
            "max_linear_mps": 0.25,
            "max_angular_dps": 60,
            "safety_timeout_ms": 500,
            "protocol_confirmed": False,
        }
    },
}

# Legacy shape retained for older parts of the service and older sketches.
DEFAULT_HARDWARE_MAP = {
    "head_yaw": {"label": "Head rotation", "role": "head_yaw", "device_type": "servo", "enabled": True, "pin": 9, "min_deg": -20, "max_deg": 20, "home_deg": 0, "invert": True},
    "head_pitch": {"label": "Left gimbal servo (legacy pitch slot)", "role": "head_pitch", "device_type": "servo", "enabled": True, "pin": 10, "min_deg": -20, "max_deg": 20, "home_deg": 0, "invert": False},
    "head_roll": {"label": "Right gimbal servo (legacy roll slot)", "role": "head_roll", "device_type": "servo", "enabled": True, "pin": 11, "min_deg": -20, "max_deg": 20, "home_deg": 0, "invert": False},
    "eyes_led": {"label": "Eyes LED zone", "role": "eyes", "device_type": "neopixel_zone", "enabled": True, "pin": 3, "count": 2, "brightness": 0.25, "colour": "#0088ff"},
    "mouth_led": {"label": "Mouth LED zone", "role": "mouth", "device_type": "neopixel_zone", "enabled": True, "pin": 3, "count": 1, "brightness": 0.20, "colour": "#00ffff"},
}

_COLOUR_NAME_TO_HEX = {
    "off": "#000000", "black": "#000000", "red": "#ff0000", "green": "#00ff00",
    "blue": "#0000ff", "cyan": "#00ffff", "amber": "#ff9900", "orange": "#ff6600",
    "yellow": "#ffff00", "purple": "#8000ff", "pink": "#ff0080", "magenta": "#ff00ff",
    "white": "#ffffff", "soft_white": "#ffdca8",
}

LED_STATE_ORDER = ["idle", "listening", "heard", "awake", "processing", "thinking", "speaking", "success", "warning", "error", "sleep", "vision", "diagnostic"]
LED_ZONE_ORDER = ["mouth", "left_eye", "right_eye", "chest", "status"]


def _state_profile(label: str, mouth: tuple[str, float], eyes: tuple[str, float], chest: tuple[str, float], status: tuple[str, float]) -> Dict[str, Any]:
    return {
        "label": label,
        "enabled": True,
        "zones": {
            "mouth": {"enabled": True, "colour": mouth[0], "brightness": mouth[1]},
            "left_eye": {"enabled": True, "colour": eyes[0], "brightness": eyes[1]},
            "right_eye": {"enabled": True, "colour": eyes[0], "brightness": eyes[1]},
            "chest": {"enabled": True, "colour": chest[0], "brightness": chest[1]},
            "status": {"enabled": True, "colour": status[0], "brightness": status[1]},
        },
    }


DEFAULT_LED_STATE_PROFILES = {
    "idle": _state_profile("Idle", ("#00ffff", 0.03), ("#0066ff", 0.16), ("#003344", 0.04), ("#003322", 0.04)),
    "listening": _state_profile("Listening", ("#00ffff", 0.10), ("#00ffff", 0.30), ("#0066ff", 0.10), ("#00ffff", 0.14)),
    "heard": _state_profile("Heard you", ("#00ff66", 0.55), ("#00ff66", 0.38), ("#00ff66", 0.18), ("#00ff66", 0.22)),
    "awake": _state_profile("Conversation active", ("#00ffff", 0.18), ("#33ccff", 0.30), ("#004488", 0.10), ("#00aaff", 0.16)),
    "processing": _state_profile("Processing", ("#ff9900", 0.34), ("#ff9900", 0.22), ("#8000ff", 0.16), ("#ff9900", 0.18)),
    "thinking": _state_profile("Thinking / processing", ("#ff9900", 0.08), ("#ff9900", 0.24), ("#8000ff", 0.10), ("#ff9900", 0.16)),
    "speaking": _state_profile("Talking", ("#00ffff", 0.22), ("#00ccff", 0.24), ("#0066ff", 0.10), ("#00ffff", 0.12)),
    "success": _state_profile("Success / ready", ("#00ff66", 0.18), ("#00ff88", 0.28), ("#00aa44", 0.12), ("#00ff66", 0.16)),
    "warning": _state_profile("Warning", ("#ff9900", 0.20), ("#ff6600", 0.30), ("#552200", 0.12), ("#ff9900", 0.20)),
    "error": _state_profile("Error / fault", ("#ff0000", 0.24), ("#ff0000", 0.34), ("#660000", 0.16), ("#ff0000", 0.24)),
    "sleep": _state_profile("Sleeping", ("#000000", 0.0), ("#001133", 0.05), ("#000000", 0.0), ("#000000", 0.0)),
    "vision": _state_profile("Using camera", ("#8000ff", 0.10), ("#cc33ff", 0.28), ("#440066", 0.10), ("#8000ff", 0.16)),
    "diagnostic": _state_profile("Hardware diagnostic", ("#ff9900", 0.10), ("#00aaff", 0.24), ("#443300", 0.10), ("#ff9900", 0.18)),
}


def _int_or(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _bool_or(value: Any, default: bool = False) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    try:
        return bool(value)
    except Exception:
        return default


def _colour_hex(value: Any, default: str = "#000000") -> str:
    text = str(value or "").strip().lower()
    if text in _COLOUR_NAME_TO_HEX:
        return _COLOUR_NAME_TO_HEX[text]
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return text
    if re.fullmatch(r"[0-9a-f]{6}", text):
        return "#" + text
    return _COLOUR_NAME_TO_HEX.get(str(default).lower(), str(default) if re.fullmatch(r"#[0-9a-fA-F]{6}", str(default)) else "#000000")


def normalise_led_state_profiles(raw: Any) -> Dict[str, Any]:
    result = json.loads(json.dumps(DEFAULT_LED_STATE_PROFILES))
    if isinstance(raw, dict) and "profiles" in raw:
        raw = raw.get("profiles")
    if not isinstance(raw, dict):
        return result
    for state in LED_STATE_ORDER:
        inc = raw.get(state)
        if not isinstance(inc, dict):
            continue
        dst = result[state]
        dst["label"] = str(inc.get("label", dst["label"]))
        dst["enabled"] = _bool_or(inc.get("enabled", dst["enabled"]), True)
        zones = inc.get("zones", {}) if isinstance(inc.get("zones"), dict) else {}
        for zone in LED_ZONE_ORDER:
            z_in = zones.get(zone)
            if not isinstance(z_in, dict):
                continue
            z = dst["zones"][zone]
            z["enabled"] = _bool_or(z_in.get("enabled", z["enabled"]), True)
            z["colour"] = _colour_hex(z_in.get("colour", z_in.get("color", z["colour"])), z["colour"])
            z["brightness"] = max(0.0, min(1.0, _float_or(z_in.get("brightness", z["brightness"]), z["brightness"])))
    return result


def normalise_hardware_registry(raw: Any) -> Dict[str, Any]:
    """Normalise the hardware registry including BX1's mixed two-servo head gimbal."""
    result = json.loads(json.dumps(DEFAULT_HARDWARE_REGISTRY))
    if isinstance(raw, dict) and "hardware_registry" in raw:
        raw = raw.get("hardware_registry")
    if not isinstance(raw, dict):
        return result

    # Migrate legacy v9/v10 maps. The old pitch and roll physical servo slots now
    # become the left and right push-pull gimbal servos respectively.
    if any(k in raw for k in ("head_yaw", "head_pitch", "head_roll", "mouth_led", "eyes_led")):
        legacy = raw
        bus = result["led_buses"]["main"]
        mouth = legacy.get("mouth_led", {}) if isinstance(legacy.get("mouth_led"), dict) else {}
        eyes = legacy.get("eyes_led", {}) if isinstance(legacy.get("eyes_led"), dict) else {}
        mouth_pin = _int_or(mouth.get("pin", -1), -1)
        eyes_pin = _int_or(eyes.get("pin", -1), -1)
        bus["data_pin"] = mouth_pin if mouth_pin >= 0 else (eyes_pin if eyes_pin >= 0 else 3)
        bus["enabled"] = bool(mouth_pin >= 0 or eyes_pin >= 0)
        bus["total_pixels"] = max(100, _int_or(mouth.get("count", 1), 1), _int_or(eyes.get("count", 2), 2))
        if mouth:
            result["led_zones"]["mouth"].update({"enabled": _bool_or(mouth.get("enabled", mouth_pin >= 0)), "start": 1, "end": max(1, _int_or(mouth.get("count", 1), 1)), "brightness": _float_or(mouth.get("brightness", 0.2), 0.2), "default_colour": _colour_hex(mouth.get("colour", "#00ffff"), "#00ffff")})
        if eyes:
            for eye_name, address in (("left_eye", 2), ("right_eye", 3)):
                result["led_zones"][eye_name].update({"enabled": _bool_or(eyes.get("enabled", eyes_pin >= 0)), "start": address, "end": address, "brightness": _float_or(eyes.get("brightness", 0.25), 0.25), "default_colour": _colour_hex(eyes.get("colour", "#0088ff"), "#0088ff")})
        legacy_to_native = {"head_yaw": "head_yaw", "head_pitch": "gimbal_left", "head_roll": "gimbal_right"}
        for old_key, new_key in legacy_to_native.items():
            item = legacy.get(old_key, {}) if isinstance(legacy.get(old_key), dict) else {}
            if item:
                result["servos"][new_key].update({
                    "enabled": _bool_or(item.get("enabled", False)),
                    "pin": _int_or(item.get("pin", result["servos"][new_key].get("pin", -1)), -1),
                    "min_deg": _float_or(item.get("min_deg", result["servos"][new_key].get("min_deg", -20)), -20),
                    "home_deg": _float_or(item.get("home_deg", result["servos"][new_key].get("home_deg", 0)), 0),
                    "max_deg": _float_or(item.get("max_deg", result["servos"][new_key].get("max_deg", 20)), 20),
                    "invert": _bool_or(item.get("invert", False)),
                })
        return result

    buses = raw.get("led_buses", {}) if isinstance(raw.get("led_buses"), dict) else {}
    if isinstance(buses.get("main"), dict):
        inc = buses["main"]
        bus = result["led_buses"]["main"]
        bus["label"] = str(inc.get("label", bus["label"]))
        bus["type"] = str(inc.get("type", bus["type"]))
        bus["enabled"] = _bool_or(inc.get("enabled", bus["enabled"]))
        bus["data_pin"] = _int_or(inc.get("data_pin", bus["data_pin"]), bus["data_pin"])
        bus["total_pixels"] = max(1, min(500, _int_or(inc.get("total_pixels", bus["total_pixels"]), bus["total_pixels"])))
        bus["brightness_limit"] = max(0.0, min(1.0, _float_or(inc.get("brightness_limit", bus["brightness_limit"]), bus["brightness_limit"])))
        bus["colour_order"] = str(inc.get("colour_order", bus["colour_order"]))

    zones = raw.get("led_zones", {}) if isinstance(raw.get("led_zones"), dict) else {}
    for key, defaults in result["led_zones"].items():
        inc = zones.get(key)
        if not isinstance(inc, dict):
            continue
        defaults["label"] = str(inc.get("label", defaults["label"]))
        defaults["bus"] = str(inc.get("bus", "main")) or "main"
        defaults["enabled"] = _bool_or(inc.get("enabled", defaults["enabled"]))
        defaults["start"] = max(1, _int_or(inc.get("start", defaults["start"]), defaults["start"]))
        defaults["end"] = max(defaults["start"], _int_or(inc.get("end", defaults["end"]), defaults["end"]))
        defaults["default_colour"] = _colour_hex(inc.get("default_colour", defaults["default_colour"]), defaults["default_colour"])
        defaults["brightness"] = max(0.0, min(1.0, _float_or(inc.get("brightness", defaults["brightness"]), defaults["brightness"])))

    servos = raw.get("servos", {}) if isinstance(raw.get("servos"), dict) else {}
    # Native plus one-time migration from old v10 physical names.
    if "gimbal_left" not in servos and isinstance(servos.get("head_pitch"), dict):
        servos = dict(servos); servos["gimbal_left"] = servos["head_pitch"]
    if "gimbal_right" not in servos and isinstance(servos.get("head_roll"), dict):
        servos = dict(servos); servos["gimbal_right"] = servos["head_roll"]
    for key, defaults in result["servos"].items():
        inc = servos.get(key)
        if not isinstance(inc, dict):
            continue
        defaults["label"] = str(inc.get("label", defaults["label"]))
        defaults["enabled"] = _bool_or(inc.get("enabled", defaults["enabled"]))
        defaults["pin"] = _int_or(inc.get("pin", defaults["pin"]), defaults["pin"])
        defaults["min_deg"] = _float_or(inc.get("min_deg", defaults["min_deg"]), defaults["min_deg"])
        defaults["home_deg"] = _float_or(inc.get("home_deg", defaults["home_deg"]), defaults["home_deg"])
        defaults["max_deg"] = _float_or(inc.get("max_deg", defaults["max_deg"]), defaults["max_deg"])
        if defaults["max_deg"] < defaults["min_deg"]:
            defaults["min_deg"], defaults["max_deg"] = defaults["max_deg"], defaults["min_deg"]
        defaults["home_deg"] = max(defaults["min_deg"], min(defaults["max_deg"], defaults["home_deg"]))
        defaults["invert"] = _bool_or(inc.get("invert", defaults["invert"]))
        defaults["speed_deg_s"] = max(1, _int_or(inc.get("speed_deg_s", defaults.get("speed_deg_s", 75)), 75))

    behaviour_in = raw.get("servo_behaviour", {}) if isinstance(raw.get("servo_behaviour"), dict) else {}
    behaviour = result["servo_behaviour"]
    behaviour["quiet_release_enabled"] = _bool_or(
        behaviour_in.get("quiet_release_enabled", behaviour["quiet_release_enabled"]), True
    )
    behaviour["release_after_ms"] = max(250, min(10000, _int_or(
        behaviour_in.get("release_after_ms", behaviour["release_after_ms"]), behaviour["release_after_ms"]
    )))
    behaviour["pulse_deadband_us"] = max(0, min(30, _int_or(
        behaviour_in.get("pulse_deadband_us", behaviour["pulse_deadband_us"]), behaviour["pulse_deadband_us"]
    )))

    kin_in = raw.get("head_kinematics", {}) if isinstance(raw.get("head_kinematics"), dict) else {}
    kin = result["head_kinematics"]
    kin["type"] = "dual_servo_push_pull"
    for axis in ("pitch", "roll"):
        lo = _float_or(kin_in.get(f"{axis}_min_deg", kin[f"{axis}_min_deg"]), kin[f"{axis}_min_deg"])
        hi = _float_or(kin_in.get(f"{axis}_max_deg", kin[f"{axis}_max_deg"]), kin[f"{axis}_max_deg"])
        if hi < lo: lo, hi = hi, lo
        home = max(lo, min(hi, _float_or(kin_in.get(f"{axis}_home_deg", kin[f"{axis}_home_deg"]), kin[f"{axis}_home_deg"])))
        kin[f"{axis}_min_deg"], kin[f"{axis}_home_deg"], kin[f"{axis}_max_deg"] = lo, home, hi
    kin["pitch_gain"] = max(0.05, min(5.0, _float_or(kin_in.get("pitch_gain", kin["pitch_gain"]), kin["pitch_gain"])))
    kin["roll_gain"] = max(0.05, min(5.0, _float_or(kin_in.get("roll_gain", kin["roll_gain"]), kin["roll_gain"])))
    for key in ("left_pitch_sign", "right_pitch_sign", "left_roll_sign", "right_roll_sign"):
        kin[key] = 1 if _int_or(kin_in.get(key, kin[key]), kin[key]) >= 0 else -1

    sensors = raw.get("sensors", {}) if isinstance(raw.get("sensors"), dict) else {}
    if isinstance(sensors.get("modulino_movement"), dict):
        inc = sensors["modulino_movement"]
        result["sensors"]["modulino_movement"].update({
            "enabled": _bool_or(inc.get("enabled", True)),
            "driver": str(inc.get("driver", result["sensors"]["modulino_movement"].get("driver", "Arduino_LSM6DSOX explicit Wire1"))),
            "bus": str(inc.get("bus", "Wire1/Qwiic")),
            "i2c_address": str(inc.get("i2c_address", "0x6A")),
            "sample_rate_hz": max(1, min(400, _int_or(inc.get("sample_rate_hz", 50), 50))),
        })

    drives = raw.get("drive_buses", {}) if isinstance(raw.get("drive_buses"), dict) else {}
    if isinstance(drives.get("rs485_wheels"), dict):
        inc = drives["rs485_wheels"]
        d = result["drive_buses"]["rs485_wheels"]
        d.update({
            "enabled": _bool_or(inc.get("enabled", d["enabled"])), "adapter": str(inc.get("adapter", d["adapter"])),
            "port": str(inc.get("port", d["port"])), "baud": _int_or(inc.get("baud", d["baud"]), d["baud"]),
            "left_motor_id": _int_or(inc.get("left_motor_id", d["left_motor_id"]), d["left_motor_id"]),
            "right_motor_id": _int_or(inc.get("right_motor_id", d["right_motor_id"]), d["right_motor_id"]),
            "max_linear_mps": _float_or(inc.get("max_linear_mps", d["max_linear_mps"]), d["max_linear_mps"]),
            "max_angular_dps": _float_or(inc.get("max_angular_dps", d["max_angular_dps"]), d["max_angular_dps"]),
            "safety_timeout_ms": _int_or(inc.get("safety_timeout_ms", d["safety_timeout_ms"]), d["safety_timeout_ms"]),
            "motor_armed": False,
            "primary_control": str(inc.get("primary_control", d.get("primary_control", "step_dir_enable_pending_confirmation"))),
            "diagnostics_interface": str(inc.get("diagnostics_interface", d.get("diagnostics_interface", "rs485"))),
            "protocol_confirmed": _bool_or(inc.get("protocol_confirmed", d.get("protocol_confirmed", False))),
        })
    return result


def legacy_hardware_map_from_registry(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    reg = normalise_hardware_registry(registry)
    bus, zones, servos = reg["led_buses"]["main"], reg["led_zones"], reg["servos"]
    def zone_len(name: str, default: int) -> int:
        z = zones.get(name, {})
        return max(1, int(z.get("end", default)) - int(z.get("start", 1)) + 1)
    return {
        "head_yaw": {"label": "Head rotation", "role": "head_yaw", "device_type": "servo", **servos["head_yaw"]},
        "head_pitch": {"label": "Left push-pull gimbal servo", "role": "head_pitch", "device_type": "servo", **servos["gimbal_left"]},
        "head_roll": {"label": "Right push-pull gimbal servo", "role": "head_roll", "device_type": "servo", **servos["gimbal_right"]},
        "eyes_led": {"label": "Eyes LED zones", "role": "eyes", "device_type": "neopixel_zone", "enabled": bool(zones["left_eye"].get("enabled") or zones["right_eye"].get("enabled")), "pin": int(bus.get("data_pin", -1)), "count": zone_len("left_eye", 1) + zone_len("right_eye", 1), "brightness": max(float(zones["left_eye"].get("brightness", 0.25)), float(zones["right_eye"].get("brightness", 0.25))), "colour": zones["left_eye"].get("default_colour", "#0088ff")},
        "mouth_led": {"label": "Mouth LED zone", "role": "mouth", "device_type": "neopixel_zone", "enabled": bool(zones["mouth"].get("enabled")), "pin": int(bus.get("data_pin", -1)), "count": zone_len("mouth", 1), "brightness": float(zones["mouth"].get("brightness", 0.2)), "colour": zones["mouth"].get("default_colour", "#00ffff")},
    }


def normalise_hardware_map(raw: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(raw, dict) and "hardware_registry" in raw:
        return legacy_hardware_map_from_registry(raw.get("hardware_registry"))
    return legacy_hardware_map_from_registry(normalise_hardware_registry(raw))


def flatten_hardware_registry_for_mcu(registry: Dict[str, Any]) -> Dict[str, Any]:
    reg = normalise_hardware_registry(registry)
    bus, servos, zones, kin = reg["led_buses"]["main"], reg["servos"], reg["led_zones"], reg["head_kinematics"]
    servo_behaviour = reg.get("servo_behaviour", {})
    def pin_for(name: str) -> int:
        s = servos[name]
        return int(s.get("pin", -1)) if s.get("enabled") else -1
    def z_start(name: str) -> int:
        return int(zones[name].get("start", 1)) if zones[name].get("enabled") else -1
    def z_end(name: str) -> int:
        return int(zones[name].get("end", z_start(name))) if zones[name].get("enabled") else -1
    packet = {
        "type": "configure_hardware_v2",
        "led_bus_pin": int(bus.get("data_pin", -1)) if bus.get("enabled") else -1,
        "led_bus_count": int(bus.get("total_pixels", 100)),
        "led_bus_brightness_limit": float(bus.get("brightness_limit", 0.2)),
        "zone_mouth_start": z_start("mouth"), "zone_mouth_end": z_end("mouth"),
        "zone_left_eye_start": z_start("left_eye"), "zone_left_eye_end": z_end("left_eye"),
        "zone_right_eye_start": z_start("right_eye"), "zone_right_eye_end": z_end("right_eye"),
        "zone_chest_start": z_start("chest"), "zone_chest_end": z_end("chest"),
        "zone_status_start": z_start("status"), "zone_status_end": z_end("status"),
        "head_yaw_pin": pin_for("head_yaw"),
        "head_gimbal_left_pin": pin_for("gimbal_left"),
        "head_gimbal_right_pin": pin_for("gimbal_right"),
        "head_yaw_min_deg": float(servos["head_yaw"].get("min_deg", -20)),
        "head_yaw_max_deg": float(servos["head_yaw"].get("max_deg", 20)),
        "head_yaw_home_deg": float(servos["head_yaw"].get("home_deg", 0)),
        "head_yaw_invert": 1 if servos["head_yaw"].get("invert", False) else 0,
        "head_gimbal_left_min_deg": float(servos["gimbal_left"].get("min_deg", -20)),
        "head_gimbal_left_max_deg": float(servos["gimbal_left"].get("max_deg", 20)),
        "head_gimbal_left_home_deg": float(servos["gimbal_left"].get("home_deg", 0)),
        "head_gimbal_left_invert": 1 if servos["gimbal_left"].get("invert", False) else 0,
        "head_gimbal_right_min_deg": float(servos["gimbal_right"].get("min_deg", -20)),
        "head_gimbal_right_max_deg": float(servos["gimbal_right"].get("max_deg", 20)),
        "head_gimbal_right_home_deg": float(servos["gimbal_right"].get("home_deg", 0)),
        "head_gimbal_right_invert": 1 if servos["gimbal_right"].get("invert", False) else 0,
        "head_pitch_min_deg": float(kin.get("pitch_min_deg", -10)), "head_pitch_home_deg": float(kin.get("pitch_home_deg", 0)), "head_pitch_max_deg": float(kin.get("pitch_max_deg", 10)),
        "head_roll_min_deg": float(kin.get("roll_min_deg", -10)), "head_roll_home_deg": float(kin.get("roll_home_deg", 0)), "head_roll_max_deg": float(kin.get("roll_max_deg", 10)),
        "head_pitch_gain": float(kin.get("pitch_gain", 1.0)), "head_roll_gain": float(kin.get("roll_gain", 1.0)),
        "head_left_pitch_sign": int(kin.get("left_pitch_sign", 1)), "head_right_pitch_sign": int(kin.get("right_pitch_sign", -1)),
        "head_left_roll_sign": int(kin.get("left_roll_sign", 1)), "head_right_roll_sign": int(kin.get("right_roll_sign", 1)),
        "servo_quiet_release_enabled": 1 if servo_behaviour.get("quiet_release_enabled", True) else 0,
        "servo_release_after_ms": int(servo_behaviour.get("release_after_ms", 1200)),
        "servo_pulse_deadband_us": int(servo_behaviour.get("pulse_deadband_us", 4)),
        "eyes_led_pin": int(bus.get("data_pin", -1)) if bus.get("enabled") else -1,
        "eyes_led_count": int(bus.get("total_pixels", 100)),
        "mouth_led_pin": int(bus.get("data_pin", -1)) if bus.get("enabled") else -1,
        "mouth_led_count": int(bus.get("total_pixels", 100)),
    }
    # Legacy aliases keep older MCU firmware usable during a staged update.
    packet["head_pitch_pin"] = packet["head_gimbal_left_pin"]
    packet["head_roll_pin"] = packet["head_gimbal_right_pin"]
    return packet


def flatten_hardware_map_for_mcu(hardware_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return flatten_hardware_registry_for_mcu(normalise_hardware_registry(hardware_map))

# High-level personality controls were removed from the body client in v10.35.
# Robot identity, prompt style and personality are owned by the desktop Brain App.

def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if STARTUP_OPTIONS.get("web_host"):
        cfg["web_host"] = str(STARTUP_OPTIONS.get("web_host"))
    if STARTUP_OPTIONS.get("web_port"):
        try:
            cfg["web_port"] = int(str(STARTUP_OPTIONS.get("web_port")))
        except Exception:
            pass
    web_enabled_override = str(STARTUP_OPTIONS.get("web_enabled", "") or "").strip().lower()
    if web_enabled_override:
        cfg["web_enabled"] = web_enabled_override not in {"0", "false", "no", "off", "disabled"}
    if STARTUP_OPTIONS.get("brain_url"):
        cfg["brain_base_url"] = str(STARTUP_OPTIONS.get("brain_url")).rstrip("/")

    # Repair historical saved values such as 192.168.1.50:8765.  An empty
    # Brain URL is valid while disconnected, but it must never become the
    # relative requests URL '/api/body_state'.
    raw_brain_url = str(cfg.get("brain_base_url", "") or "").strip()
    if raw_brain_url:
        candidate = raw_brain_url if "://" in raw_brain_url else "http://" + raw_brain_url
        try:
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                cfg["brain_base_url"] = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8765}"
            else:
                print(f"[brain] WARNING: ignoring invalid Brain App URL: {raw_brain_url!r}")
                cfg["brain_base_url"] = ""
        except Exception:
            print(f"[brain] WARNING: ignoring invalid Brain App URL: {raw_brain_url!r}")
            cfg["brain_base_url"] = ""
    if STARTUP_OPTIONS.get("body_id"):
        cfg["robot_id"] = str(STARTUP_OPTIONS.get("body_id")).strip()
    cfg.setdefault("brain_owns_identity", True)
    # v10.35: the body requests the finished Dot.TTS reply as part of the
    # normal Brain API conversation.  Keep legacy brain_tts_* keys readable so
    # existing installations migrate without losing user hardware/audio data,
    # but make them point at the one Brain API rather than a second voice port.
    legacy_remote_backends = {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}
    if str(cfg.get("tts_backend", "")).strip().lower() in legacy_remote_backends:
        cfg["tts_backend"] = "edge-tts"
    cfg["brain_response_audio_enabled"] = True
    cfg["brain_tts_base_url"] = str(cfg.get("brain_base_url", "") or "")
    cfg["brain_tts_follow_brain_host"] = True
    cfg["brain_tts_engine"] = "dottts"
    cfg["brain_tts_voice"] = "active_profile"
    cfg["brain_tts_endpoint"] = "/api/tts"
    cfg["brain_tts_status_endpoint"] = "/api/tts/status"
    cfg["brain_tts_use_brain_defaults"] = True
    cfg["skip_body_tts_when_brain_audio_present"] = True
    cfg["tts_fallback_to_espeak"] = True
    try:
        cfg["chat_timeout_s"] = max(480, int(cfg.get("chat_timeout_s", 480) or 480))
    except (TypeError, ValueError):
        cfg["chat_timeout_s"] = 480
    try:
        cfg["vision_timeout_s"] = max(480, int(cfg.get("vision_timeout_s", 480) or 480))
    except (TypeError, ValueError):
        cfg["vision_timeout_s"] = 480

    # Natural conversation with strict noise/repetition rejection,
    # unambiguous voice phases and body-owned low-latency feedback.
    cfg["app_version"] = "10.39"
    cfg["version"] = "10.39"
    cfg.setdefault("stt_transcription_backend", "brain_faster_whisper")
    cfg.setdefault("brain_stt_enabled", True)
    # Desktop STT must never monopolise the sole ALSA capture loop.  Older
    # local configs used 120 seconds; retain the key but migrate that unsafe
    # value to the bounded worker timeout used by the voice pipeline.
    try:
        existing_stt_timeout = float(cfg.get("brain_stt_timeout_s", 12) or 12)
    except (TypeError, ValueError):
        existing_stt_timeout = 12.0
    cfg["brain_stt_timeout_s"] = 12 if existing_stt_timeout > 20 else max(2, min(20, int(existing_stt_timeout)))
    cfg.setdefault("brain_stt_fallback_to_vosk", True)
    cfg.setdefault("speaker_echo_tail_ms", 1500)
    cfg.setdefault("brain_stt_language", "en")
    cfg.setdefault("brain_stt_hotwords", "")
    cfg.setdefault("brain_stt_initial_prompt", "")
    cfg.setdefault("stt_defer_local_vosk_when_brain_enabled", True)
    cfg.setdefault("stt_speech_resume_trigger_ms", 140)
    cfg.setdefault("stt_transient_guard_after_ms", 220)
    cfg.setdefault("stt_endpoint_hysteresis_db", 3.0)
    cfg.setdefault("stt_debug_keep_audio", True)
    cfg.setdefault("wake_fuzzy_matching_enabled", True)
    cfg.setdefault("wake_fuzzy_threshold", 0.74)
    cfg.setdefault("wake_match_first_tokens", 4)
    cfg.setdefault("wake_word_aliases", {
        "hello": ["hullo", "yellow", "hello leo", "hello bx1"],
        "hey": ["hay", "hey leo", "hey bx1"],
        "robot": ["robo", "row bot", "robert"],
        "leo": ["leon", "leah"],
        "bx1": ["b x one", "bee ex one", "box one"],
    })
    cfg.setdefault("stt_repetition_guard_enabled", True)
    cfg.setdefault("stt_max_consecutive_word_repeats", 3)
    cfg.setdefault("stt_max_repeated_phrase_count", 2)
    cfg.setdefault("stt_min_unique_word_ratio", 0.30)
    cfg.setdefault("stt_max_words_per_second", 7.0)
    cfg.setdefault("stt_max_transcript_words", 90)
    cfg.setdefault("stt_reject_prompt_leakage", True)
    cfg.setdefault("thinking_feedback_enabled", False)
    cfg.setdefault("thinking_feedback_delay_s", 0.18)
    cfg.setdefault("voice_command_immediate_cue_enabled", True)
    cfg.setdefault("voice_feedback_tone_level", 0.30)
    cfg.setdefault("thinking_cues_enabled", True)
    cfg.setdefault("thinking_cue_speak", True)
    cfg.setdefault("thinking_cue_delay_s", 1.1)
    cfg.setdefault("thinking_cue_repeat_s", 10.0)
    cfg.setdefault("thinking_cue_max_per_reply", 2)
    cfg.setdefault("thinking_cue_total_timeout_s", 65.0)
    cfg.setdefault("thinking_cue_finish_wait_s", 1.0)
    cfg.setdefault("thinking_cues_continue_through_tts_generation", True)
    # The desktop Brain may choose the wording/personality, but the robot body
    # must own immediate playback timing. Otherwise the user hears nothing while
    # Dot.TTS is generating the final reply.
    cfg.setdefault("brain_controls_thinking_cues", False)
    cfg.setdefault("brain_request_watchdog_s", 50.0)
    cfg.setdefault("idle_life_enabled", True)
    cfg.setdefault("idle_life_micro_actions_enabled", True)
    cfg.setdefault("idle_life_self_chatter_enabled", True)
    return cfg


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def clamp_float_value(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except Exception:
        return default


def clamp_int_value(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(float(value))))
    except Exception:
        return default


def normalise_text_list(raw: Any) -> List[str]:
    if isinstance(raw, str):
        items = raw.replace(",", "\n").splitlines()
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    out: List[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in out:
            out.append(value)
    return out


def default_robot_profile(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a generic body profile.

    V10.16 change: the Arduino/UNO Q body client no longer owns robot name,
    character or personality. Those belong to the desktop Robot Brain instance so
    multiple Brain instances can run with different personalities and ports.
    """
    body_id = str(config.get("robot_id", config.get("body_id", "UNO_Q_BODY"))).strip() or "UNO_Q_BODY"
    wake_words = normalise_text_list(config.get("wake_words", ["hello", "hey", "robot"]))
    return {
        "schema_version": 2,
        "body_id": body_id,
        "robot_id": body_id,
        "wake_words": wake_words,
        "brain_owns_identity": True,
        "capabilities": {
            "has_microphone": bool(config.get("voice_enabled", False) or config.get("mic_device", "default") != ""),
            "has_speaker": bool(config.get("tts_enabled", True)),
            "has_camera": bool(config.get("camera_enabled", True)),
            "has_head_servo": bool(config.get("allow_head_servo", True)),
            "has_drive_motors": bool(config.get("motor_armed", False)),
            "has_lidar": bool(config.get("has_lidar", False)),
        },
        "physical_description": {
            "robot_type": str(config.get("robot_type", "generic robot body client")),
            "location": str(config.get("robot_location", "workshop or test environment")),
        },
        "ui": {
            "theme": str(config.get("ui_theme", "dark-blue")),
        },
    }


def merge_dict(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def normalise_robot_profile(profile: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    base = default_robot_profile(config)
    incoming = profile if isinstance(profile, dict) else {}
    # Only merge non-personality, non-name body metadata. The Brain owns the
    # robot identity and character.
    for key in ("capabilities", "physical_description", "ui"):
        if isinstance(incoming.get(key), dict):
            base[key] = merge_dict(dict(base.get(key) or {}), dict(incoming.get(key) or {}))
    if incoming.get("body_id") or incoming.get("robot_id"):
        body_id = str(incoming.get("body_id") or incoming.get("robot_id")).strip() or str(base.get("body_id"))
        base["body_id"] = body_id
        base["robot_id"] = body_id
    if incoming.get("wake_words"):
        base["wake_words"] = normalise_text_list(incoming.get("wake_words"))
    base["brain_owns_identity"] = True
    return base


def load_robot_profile_file(config: Dict[str, Any]) -> Dict[str, Any]:
    # Deprecated: robot_profile.json used to hold name/personality. The body client
    # now keeps only generic hardware/body metadata and does not create that file.
    raw: Dict[str, Any] = {}
    if ROBOT_PROFILE_PATH.exists():
        try:
            loaded = json.loads(ROBOT_PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}
    return normalise_robot_profile(raw, config)


class BX1RobotBodyService:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.cfg = config
        self.hardware_registry = normalise_hardware_registry(self.cfg.get("hardware_registry", self.cfg.get("hardware_map", {})))
        self.hardware_map = legacy_hardware_map_from_registry(self.hardware_registry)
        self.cfg["hardware_registry"] = self.hardware_registry
        self.cfg["hardware_map"] = self.hardware_map
        self.led_state_profiles = normalise_led_state_profiles(self.cfg.get("led_state_profiles", {}))
        self.cfg["led_state_profiles"] = self.led_state_profiles
        self.led_state_lock = threading.Lock()
        self.last_led_state = ""
        self.last_led_state_at = ""
        self.robot_profile = load_robot_profile_file(self.cfg)
        self.robot_id = str(self.robot_profile.get("body_id", self.cfg.get("robot_id", "UNO_Q_BODY"))).strip() or "UNO_Q_BODY"
        self.robot_name = "Robot Body"
        self.apply_robot_profile_to_config(save=False)
        self.stop_event = threading.Event()
        self.hardware = BX1HardwareBridge()
        self.brain = BX1BrainClient(BrainClientConfig(
            base_url=str(config.get("brain_base_url", "") or "").strip(),
            api_key=str(config.get("api_key", "")),
            chat_timeout_s=int(config.get("chat_timeout_s", 180)),
            vision_timeout_s=int(config.get("vision_timeout_s", 180)),
            command_ack_timeout_s=int(config.get("command_ack_timeout_s", 10)),
        ))
        self.tts = TextToSpeech(self.build_audio_config())
        if hasattr(self.tts, "set_mouth_event_handler"):
            self.tts.set_mouth_event_handler(self.handle_mouth_audio_event)  # type: ignore[attr-defined]
        self.mouth_audio_stop = threading.Event()
        self.mouth_audio_thread: Optional[threading.Thread] = None
        self.mouth_audio_lock = threading.Lock()
        self.mouth_audio_context: Dict[str, Any] = {}
        self.mouth_audio_started_at = 0.0
        self.mouth_audio_runtime: Dict[str, Any] = {
            "active": False, "commands": 0, "last_colour": "", "last_brightness": 0.0,
            "last_command_at": "", "last_ok": None, "last_error": "", "transport": "",
            "suspended": False, "suspended_until": "", "suppressed_commands": 0,
        }
        # A single missing MCU RPC used to produce dozens of LED failures per second
        # while the mouth animation was running.  This circuit breaker keeps the
        # web service responsive and records one useful error instead of a log storm.
        self.mouth_led_block_until_mono = 0.0
        self.mouth_led_last_error_log_mono = 0.0
        self.mouth_led_last_error_signature = ""
        # Shared with the wake listener.  Manual/web commands use a different
        # thread, so the live microphone must pause while the Brain is thinking.
        self.command_processing = threading.Event()
        self.expression_lock = threading.Lock()
        self.expression_busy_until = 0.0
        self.expression_last_head: Dict[str, float] = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        self.stt: Optional[VoskSpeechToText] = None
        self.last_stt_capture_id = ""
        self.last_stt_debug_audio_urls: Dict[str, str] = {}
        # One microphone capture device cannot be owned by wake listening,
        # Listen Once, and diagnostics at the same time.  The lock gives clear
        # behaviour instead of random ALSA "Device or resource busy" failures.
        self.audio_capture_lock = threading.Lock()
        self.manual_audio_capture_requested = threading.Event()
        self.tts_capture_mute_lock = threading.Lock()
        self.tts_capture_mute_until = 0.0
        self.local_cue_lock = threading.Lock()
        self.local_cue_playing = threading.Event()
        self.active_thinking_lock = threading.Lock()
        self.active_thinking_stop: Optional[threading.Event] = None
        self.active_thinking_started_mono = 0.0
        self.mic_monitor = AlsaMicrophoneMonitor(
            device=str(config.get("mic_device", "default")),
            sample_rate=int(config.get("sample_rate", 16000)),
            channels=int(config.get("mic_channels", 1)),
            noise_gate_dbfs=float(config.get("mic_noise_gate_dbfs", -48.0)),
            software_gain_db=float(config.get("mic_software_gain_db", 0.0)),
            dsp_settings=build_audio_dsp_settings(config),
            fft_bins=int(config.get("audio_live_fft_bins", 48)),
        )
        self.last_mic_test_wav = str(Path(tempfile.gettempdir()) / "bx1_mic_test.wav")
        self._mic_devices_cache: Dict[str, Any] = {"ok": False, "devices": []}
        self._mic_devices_cache_time = 0.0
        self.camera = CameraCapture(CameraConfig(
            camera_index=int(config.get("camera_index", 0)),
            camera_device=str(config.get("camera_device", "/dev/video0")),
            jpeg_quality=int(config.get("jpeg_quality", 85)),
        ))
        # Background camera loops, the web preview and explicit vision requests
        # share the latest JPEG. This prevents three processes repeatedly opening
        # the same USB camera and makes the browser preview genuinely live.
        self.camera_frame_lock = threading.Lock()
        self.latest_camera_jpeg: bytes = b""
        self.latest_camera_frame_at = ""
        self.latest_camera_frame_mono = 0.0
        self.latest_camera_frame_source = ""
        self.visual_awareness_lock = threading.Lock()
        self.visual_last_face_seen_mono = 0.0
        self.visual_previous_present: Optional[bool] = None
        self.visual_awareness_runtime: Dict[str, Any] = {
            "enabled": bool(config.get("visual_awareness_enabled", True)),
            "state": "starting",
            "camera_ok": None,
            "opencv_available": bool(getattr(self.camera, "opencv_available", False)),
            "face_detection_available": bool(getattr(self.camera, "face_detection_available", False)),
            "face_count": None,
            "person_present": None,
            "motion_detected": None,
            "motion_score": None,
            "alone": None,
            "last_person_seen_at": "",
            "last_motion_at": "",
            "last_frame_at": "",
            "last_frame_sent_at": "",
            "last_transition": "",
            "last_error": "",
            "identity": "not enrolled",
            "gesture_mode": "Brain vision on request",
            "updated_at": now_iso(),
        }
        self.location = LocationProvider(config)
        self.latest_state: Dict[str, Any] = {}
        self.last_status_print = 0.0
        self.last_status_signature: Optional[str] = None
        self.console_quiet = bool(config.get("console_quiet", True))
        self.threads: List[threading.Thread] = []

        # Web/manual debug interface state. This is deliberately Linux-side only;
        # it lets us test the Brain App before microphone/camera/sensor hardware is live.
        self.web_server: Optional[WebControlServer] = None
        self.command_lock = threading.Lock()
        self.feedback_audio_lock = threading.Lock()
        self.web_events = deque(maxlen=int(config.get("web_event_log_limit", 200)))
        self.input_events = deque(maxlen=int(config.get("input_event_log_limit", 150)))
        self.recent_accepted_transcripts = deque(maxlen=30)
        self.recent_robot_speech = deque(maxlen=12)
        self.hardware_doctor = BX1HardwareDoctor(self.hardware, PROJECT_ROOT, self.cfg, logger=self.web_log)
        self.last_reply_text = ""
        self.last_reply_at = ""
        self.last_reply_source = ""
        self.manual_debug_state: Dict[str, Any] = dict(config.get("manual_debug_state", {}))
        self.metrics_lock = threading.Lock()
        self.performance: Dict[str, Any] = {
            "started_at": now_iso(),
            "chat_count": 0,
            "telemetry_count": 0,
            "vision_count": 0,
            "last_chat_ms": None,
            "avg_chat_ms": None,
            "last_telemetry_ms": None,
            "avg_telemetry_ms": None,
            "last_vision_ms": None,
            "avg_vision_ms": None,
            "last_brain_latency_ms": None,
            "last_live_tool_route": "none",
            "last_live_tool_verified": None,
            "last_live_tool_query": "",
            "last_live_tool_sources": [],
            "last_live_tool_result_count": 0,
            "last_reply_chars": 0,
            "last_user_message_chars": 0,
            "last_chat_started_at": None,
            "last_chat_finished_at": None,
            "last_error": "",
        }

        # Runtime voice/wake-word state for the web UI. This is intentionally
        # separate from the saved config so the page can show whether the robot
        # is listening, has heard speech, has woken up, or is waiting for the
        # Brain App. It also keeps the most recent recognised/wake phrases for
        # diagnostics without changing the robot profile.
        self.voice_state_lock = threading.Lock()
        self.speaker_playback_lock = threading.Lock()
        self.speaker_playback_active = False
        self.speaker_playback_started_mono = 0.0
        self.speaker_echo_tail_until_mono = 0.0
        self.voice_runtime: Dict[str, Any] = {
            "enabled": bool(self.cfg.get("voice_enabled", False)),
            "loop_active": False,
            "state": "idle",
            "label": "Voice loop not started.",
            "wake_words": [],
            "last_heard": "",
            "last_ignored": "",
            "last_accepted": "",
            "last_rejected": "",
            "last_rejection_reason": "",
            "last_stt_metrics": {},
            "last_event_id": "",
            "last_wake_word": "",
            "last_error": "",
            "thinking_phase": "idle",
            "last_thinking_cue": "",
            "last_feedback_kind": "",
            "last_feedback_ok": None,
            "last_feedback_error": "",
            "last_feedback_at": "",
            "wake_match_source": "",
            "wake_match_score": None,
            "last_wake_diagnostics": {},
            "record_seconds": int(self.cfg.get("record_seconds", 5)),
            "updated_at": now_iso(),
        }
        # One capture loop owns ALSA. Completed utterances cross this bounded
        # in-memory hand-off to the STT/Brain worker; audio is never logged or
        # persisted here.  A full queue is an explicit busy/drop condition.
        self.voice_stt_queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=1)
        self.voice_stt_worker_started = False
        self.voice_stt_lock = threading.Lock()

        # Idle-life runtime: this gives BX1 small autonomous behaviour when it
        # has been left alone, without confusing that behaviour with a user
        # command.  It is deliberately rate-limited and pauses during voice/TTS.
        now_mono = time.monotonic()
        self.last_user_activity_mono = now_mono
        self.last_robot_activity_mono = now_mono
        self.conversation_active_until = 0.0
        self.idle_life_lock = threading.Lock()
        self.idle_life_runtime: Dict[str, Any] = {
            "enabled": bool(self.cfg.get("idle_life_enabled", True)),
            "state": "idle",
            "last_action": "",
            "last_action_at": "",
            "last_error": "",
            "idle_seconds": 0,
            "comments_this_hour": 0,
            "sleeping": False,
        }
        self.idle_life_comment_times = deque(maxlen=20)
        self.idle_life_last_micro_action_mono = 0.0
        self.idle_life_last_comment_mono = 0.0
        self.idle_life_last_curiosity_mono = 0.0
        self.idle_life_sleep_announced = False

    def set_voice_runtime(self, state: str, label: str = "", **updates: Any) -> None:
        """Update the live voice/wake-word status shown on the web UI."""
        with self.voice_state_lock:
            self.voice_runtime.update({
                "enabled": bool(self.cfg.get("voice_enabled", False)),
                "loop_active": bool(updates.pop("loop_active", self.voice_runtime.get("loop_active", False))),
                "state": str(state or "idle"),
                "label": str(label or state or "idle"),
                "wake_words": self.get_wake_words() if hasattr(self, "cfg") else [],
                "record_seconds": int(self.cfg.get("record_seconds", 5)),
                "updated_at": now_iso(),
            })
            for key, value in updates.items():
                self.voice_runtime[key] = value
        state_map = {
            "idle": "idle", "disabled": "idle", "paused": "idle", "listening": "listening",
            "awake": "awake", "heard": "heard", "recording": "listening", "transcribing": "processing",
            "starting": "thinking", "processing": "processing", "asleep": "sleep",
            "rejected": "warning", "ignored": "listening", "error": "error",
        }
        led_state = state_map.get(str(state or "idle").lower())
        if led_state and hasattr(self, "hardware") and not bool(getattr(self, "_voice_vertical_slice_no_actuators", False)):
            threading.Thread(target=self.apply_led_state, args=(led_state,), kwargs={"source": "voice_runtime"}, daemon=True).start()

    def get_voice_runtime_snapshot(self) -> Dict[str, Any]:
        with self.voice_state_lock:
            snap = dict(self.voice_runtime)
        snap["enabled"] = bool(self.cfg.get("voice_enabled", False))
        snap["wake_words"] = self.get_wake_words()
        snap["input_mode"] = str(self.cfg.get("input_mode", "keyboard"))
        snap["stt_ready"] = bool(getattr(self.stt, "ready", False)) if self.stt is not None else False
        snap["stt_error"] = str(getattr(self.stt, "error", "")) if self.stt is not None else ""
        snap["stt_guard_remaining_s"] = round(self.stt_guard_remaining_s(), 2) if hasattr(self, "stt_guard_remaining_s") else 0.0
        snap["speech_output_active"] = bool(self.speech_output_active()) if hasattr(self, "speech_output_active") else False
        snap["speaker_suppression"] = self.speaker_suppression_snapshot() if hasattr(self, "speaker_playback_lock") else {"playback_active": False, "echo_tail_remaining_s": 0.0, "suppressed": False}
        snap["command_processing"] = bool(self.command_processing.is_set()) if hasattr(self, "command_processing") else False
        snap["manual_audio_capture_requested"] = bool(self.manual_audio_capture_requested.is_set()) if hasattr(self, "manual_audio_capture_requested") else False
        snap["mic_monitor_running"] = bool(self.mic_monitor.is_running()) if hasattr(self, "mic_monitor") else False
        snap["conversation_awake_remaining_s"] = round(max(0.0, float(getattr(self, "conversation_active_until", 0.0) or 0.0) - time.monotonic()), 2)
        return snap

    def update_live_voice_observation(self, value: Dict[str, Any]) -> None:
        """Publish bounded active-ALSA metadata at six Hz; no audio is retained."""
        captured_at = value.get("captured_at")
        if not isinstance(captured_at, (int, float)):
            return
        with self.voice_state_lock:
            prior = self.voice_runtime.get("live_audio", {})
            published_at = prior.get("published_at") if isinstance(prior, dict) else None
            if isinstance(published_at, (int, float)) and captured_at - published_at < (1.0 / 6.0):
                return
            sequence = int(prior.get("sequence", 0)) + 1 if isinstance(prior, dict) else 1
            safe = {key: value.get(key) for key in ("rms_dbfs", "peak_dbfs", "noise_floor_dbfs", "threshold_dbfs", "gate_open", "speech_detected", "captured_at")}
            safe.update({"published_at": float(captured_at), "sequence": sequence, "publisher": "active_alsa_capture", "target_hz": 6})
            self.voice_runtime["live_audio"] = safe

    def _voice_feedback_wav(self, kind: str) -> Path:
        """Create a short local acknowledgement tone without involving Brain/TTS."""
        kind = str(kind or "heard").strip().lower()
        VOICE_FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        level = max(0.02, min(0.35, float(self.cfg.get("voice_feedback_tone_level", 0.16))))
        path = VOICE_FEEDBACK_DIR / f"{kind}_{int(round(level * 100)):02d}.wav"
        if path.exists() and path.stat().st_size > 500:
            return path
        patterns = {
            "wake": [(880.0, 0.085), (1175.0, 0.11)],
            "heard": [(1320.0, 0.07), (1568.0, 0.08)],
            "thinking": [(620.0, 0.055), (740.0, 0.055), (880.0, 0.070)],
            "rejected": [(440.0, 0.10)],
        }
        pattern = patterns.get(kind, patterns["heard"])
        sample_rate = 16000
        amplitude = int(32767 * level)
        pcm = array("h")
        for frequency, duration in pattern:
            count = max(1, int(sample_rate * duration))
            fade = max(8, int(sample_rate * 0.012))
            for i in range(count):
                env = min(1.0, i / float(fade), (count - i - 1) / float(fade))
                sample = int(amplitude * max(0.0, env) * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
                pcm.append(sample)
            pcm.extend([0] * int(sample_rate * 0.025))
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return path

    def play_voice_feedback(self, kind: str, blocking: bool = True) -> Dict[str, Any]:
        """Give an immediate deterministic cue and retain actual playback evidence."""
        if not bool(self.cfg.get("voice_feedback_audio_enabled", True)):
            return {"ok": True, "skipped": "disabled"}

        def worker() -> Dict[str, Any]:
            result: Dict[str, Any]
            try:
                path = self._voice_feedback_wav(kind)
                self.guard_stt_capture(0.45, f"voice_feedback_{kind}")
                acquired = self.feedback_audio_lock.acquire(timeout=1.5)
                if not acquired:
                    result = {"ok": False, "error": "speaker busy with another local feedback cue"}
                else:
                    try:
                        result = self.play_body_audio_file(
                            path,
                            device=str(self.cfg.get("tts_playback_device", "default") or "default"),
                            timeout_s=4.0,
                            text=f"voice feedback {kind}",
                            tag=f"voice-feedback-{kind}",
                            backend="voice-feedback",
                        )
                    finally:
                        self.feedback_audio_lock.release()
                error = str(result.get("error") or result.get("stderr") or "") if not result.get("ok") else ""
                self.set_voice_runtime(
                    self.get_voice_runtime_snapshot().get("state", "processing"),
                    self.get_voice_runtime_snapshot().get("label", "Thinking…"),
                    last_feedback_kind=str(kind),
                    last_feedback_ok=bool(result.get("ok")),
                    last_feedback_error=error[:500],
                    last_feedback_at=now_iso(),
                )
                if not result.get("ok"):
                    self.web_log("error", f"voice feedback tone failed: {error or result}", result)
                else:
                    self.web_log("thinking" if str(kind) == "thinking" else "voice", f"voice feedback played: {kind}", result)
                return result
            except Exception as exc:
                self.web_log("error", f"voice feedback tone failed: {exc}")
                self.set_voice_runtime(
                    self.get_voice_runtime_snapshot().get("state", "processing"),
                    self.get_voice_runtime_snapshot().get("label", "Thinking…"),
                    last_feedback_kind=str(kind), last_feedback_ok=False,
                    last_feedback_error=str(exc)[:500], last_feedback_at=now_iso(),
                )
                return {"ok": False, "error": str(exc)}
        if blocking:
            return worker()
        threading.Thread(target=worker, name=f"bx1-feedback-{kind}", daemon=True).start()
        return {"ok": True, "queued": True}

    def acknowledge_voice_event(self, kind: str) -> None:
        """Strong visible/audible acknowledgement that does not depend on the LLM."""
        kind = str(kind or "heard").strip().lower()
        state = "awake" if kind == "wake" else ("warning" if kind == "rejected" else "heard")
        if bool(self.cfg.get("voice_feedback_led_enabled", True)):
            self.apply_led_state(state, source=f"voice_feedback_{kind}", force=True)
        self.play_voice_feedback(kind, blocking=True)

    def touch_user_activity(self, reason: str = "user") -> None:
        self.last_user_activity_mono = time.monotonic()
        self.last_robot_activity_mono = self.last_user_activity_mono
        self.idle_life_sleep_announced = False
        with self.idle_life_lock:
            self.idle_life_runtime["sleeping"] = False
            self.idle_life_runtime["state"] = "active"
            self.idle_life_runtime["last_activity_reason"] = str(reason)

    def touch_robot_activity(self, reason: str = "robot") -> None:
        self.last_robot_activity_mono = time.monotonic()
        with self.idle_life_lock:
            self.idle_life_runtime["last_robot_activity_reason"] = str(reason)

    def set_conversation_active_until(self, when_mono: float) -> None:
        try:
            self.conversation_active_until = max(0.0, float(when_mono))
        except Exception:
            self.conversation_active_until = 0.0

    def get_idle_life_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self.idle_life_lock:
            snap = dict(self.idle_life_runtime)
        snap.update({
            "enabled": bool(self.cfg.get("idle_life_enabled", True)),
            "self_chatter_enabled": bool(self.cfg.get("idle_life_self_chatter_enabled", True)),
            "internet_curiosity_enabled": bool(self.cfg.get("idle_life_internet_curiosity_enabled", False)),
            "idle_seconds": round(max(0.0, now - float(self.last_user_activity_mono or now)), 1),
            "robot_idle_seconds": round(max(0.0, now - float(self.last_robot_activity_mono or now)), 1),
            "conversation_active": bool(now < float(self.conversation_active_until or 0.0)),
            "conversation_remaining_s": round(max(0.0, float(self.conversation_active_until or 0.0) - now), 1),
            "micro_action_delay_s": float(self.cfg.get("idle_life_micro_action_delay_s", 60.0)),
            "comment_delay_s": float(self.cfg.get("idle_life_comment_delay_s", 180.0)),
            "curiosity_delay_s": float(self.cfg.get("idle_life_curiosity_delay_s", 900.0)),
            "sleep_after_s": float(self.cfg.get("idle_life_sleep_after_s", 1800.0)),
            "max_comments_per_hour": int(self.cfg.get("idle_life_max_comments_per_hour", 3)),
        })
        return snap

    def set_idle_life_runtime(self, state: str, action: str = "", **updates: Any) -> None:
        with self.idle_life_lock:
            self.idle_life_runtime.update({
                "enabled": bool(self.cfg.get("idle_life_enabled", True)),
                "state": str(state or "idle"),
                "idle_seconds": round(max(0.0, time.monotonic() - float(self.last_user_activity_mono or time.monotonic())), 1),
            })
            if action:
                self.idle_life_runtime["last_action"] = str(action)
                self.idle_life_runtime["last_action_at"] = now_iso()
            for key, value in updates.items():
                self.idle_life_runtime[key] = value

    def guard_stt_capture(self, seconds: float, reason: str = "speech_output") -> None:
        """Temporarily prevent the wake listener from opening the microphone.

        This is the simple, reliable echo-avoidance layer: when BX1 is speaking
        or has just finished speaking, the STT loop waits instead of recording
        the robot speaker and accidentally treating it as the user's command.
        """
        try:
            seconds_f = max(0.0, float(seconds))
        except Exception:
            seconds_f = 0.0
        if seconds_f <= 0:
            return
        until = time.monotonic() + seconds_f
        with self.tts_capture_mute_lock:
            self.tts_capture_mute_until = max(float(getattr(self, "tts_capture_mute_until", 0.0) or 0.0), until)

    def _speaker_echo_tail_s(self) -> float:
        try:
            return max(0.25, min(5.0, float(self.cfg.get("speaker_echo_tail_ms", 1500)) / 1000.0))
        except (TypeError, ValueError):
            return 1.5

    def speaker_suppression_snapshot(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self.speaker_playback_lock:
            active = bool(self.speaker_playback_active)
            tail_remaining = max(0.0, self.speaker_echo_tail_until_mono - now)
            return {"playback_active": active, "echo_tail_remaining_s": round(tail_remaining, 2),
                    "suppressed": active or tail_remaining > 0.0}

    def _speaker_playback_started(self) -> None:
        with self.speaker_playback_lock:
            self.speaker_playback_active = True
            self.speaker_playback_started_mono = time.monotonic()
            self.speaker_echo_tail_until_mono = 0.0
        self.set_voice_runtime("speaking", "Leo speaking — microphone wake detection temporarily suppressed.",
                               loop_active=bool(self.get_voice_runtime_snapshot().get("loop_active", False)),
                               speaker_playback_active=True, echo_tail_remaining_s=0.0)

    def _speaker_playback_finished(self) -> None:
        tail_s = self._speaker_echo_tail_s()
        with self.speaker_playback_lock:
            self.speaker_playback_active = False
            self.speaker_echo_tail_until_mono = time.monotonic() + tail_s
        self.set_voice_runtime("echo_suppressed", f"Speaker playback finished — wake detection suppressed for {tail_s:.1f}s.",
                               loop_active=bool(self.get_voice_runtime_snapshot().get("loop_active", False)),
                               speaker_playback_active=False, echo_tail_remaining_s=round(tail_s, 2))

    def play_body_audio_file(
        self,
        filename: str | os.PathLike,
        *,
        device: str = "default",
        timeout_s: float = 30.0,
        text: str = "",
        tag: str = "body-audio-file",
        backend: str = "body-audio-file",
    ) -> Dict[str, Any]:
        """Play a Body-owned file through the authoritative speaker lifecycle."""
        path = Path(filename)
        if not path.is_file():
            return play_audio_file(path, device=device, timeout_s=timeout_s)
        info = {
            "text": str(text or ""), "tag": str(tag or "body-audio-file"),
            "backend": str(backend or "body-audio-file"), "filename": str(path),
            "wav": path.suffix.lower() == ".wav", "audio_profile": {},
        }
        self.handle_mouth_audio_event("speech_audio_file_start", info)
        try:
            return play_audio_file(path, device=device, timeout_s=timeout_s)
        finally:
            self.handle_mouth_audio_event("speech_audio_file_stop", info)

    def stt_guard_remaining_s(self) -> float:
        with self.tts_capture_mute_lock:
            return max(0.0, float(getattr(self, "tts_capture_mute_until", 0.0) or 0.0) - time.monotonic())

    def speech_output_active(self) -> bool:
        if not bool(self.cfg.get("stt_pause_during_tts", True)):
            return False
        if self.stt_guard_remaining_s() > 0.0:
            return True
        try:
            return bool(getattr(self.tts, "is_active_or_pending")())
        except Exception:
            try:
                return bool(getattr(self.tts, "_speak_queue").qsize() > 0)
            except Exception:
                return False

    def estimate_speech_guard_s(self, text: str, minimum: float = 1.0) -> float:
        words = len(str(text or "").split())
        chars = len(str(text or ""))
        # Conversational English at roughly 150 wpm plus a small audio tail.
        return max(float(minimum), min(12.0, (words / 2.5) + (chars / 45.0) + 0.8))

    def build_audio_config(self) -> AudioConfig:
        # Reply audio arrives with the Brain API result. This backend is used for
        # local acknowledgements and as a fallback when reply audio is unavailable.
        brain_tts_url = self.resolve_brain_tts_base_url(update_config=False)
        selected_tts_backend = str(self.cfg.get("tts_backend", "edge-tts"))
        if selected_tts_backend.strip().lower() in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"} and not brain_tts_url:
            selected_tts_backend = "espeak-ng"
        return AudioConfig(
            tts_enabled=bool(self.cfg.get("tts_enabled", True)),
            tts_backend=selected_tts_backend,
            tts_command=str(self.cfg.get("tts_command", "espeak-ng -ven-gb -s 155 -p 35")),
            tts_voice=str(self.cfg.get("tts_voice", "en-gb")),
            tts_rate=int(self.cfg.get("tts_rate", 155)),
            tts_pitch=int(self.cfg.get("tts_pitch", 35)),
            tts_volume=int(self.cfg.get("tts_volume", 80)),
            tts_playback_device=str(self.cfg.get("tts_playback_device", "default")),
            brain_tts_base_url=brain_tts_url,
            brain_tts_engine=str(self.cfg.get("brain_tts_engine", "dottts")),
            brain_tts_voice=str(self.cfg.get("brain_tts_voice", "active_profile")),
            brain_tts_use_brain_defaults=bool(self.cfg.get("brain_tts_use_brain_defaults", True)),
            brain_tts_format=str(self.cfg.get("brain_tts_format", "wav")),
            brain_tts_timeout_s=int(self.cfg.get("brain_tts_timeout_s", 240)),
            brain_tts_endpoint=str(self.cfg.get("brain_tts_endpoint", "/api/tts")),
            brain_tts_status_endpoint=str(self.cfg.get("brain_tts_status_endpoint", "/api/tts/status")),
            tts_piper_model=str(self.cfg.get("tts_piper_model", "models/piper/en_GB-alan-medium.onnx")),
            tts_piper_config=str(self.cfg.get("tts_piper_config", "")),
            tts_edge_voice=str(self.cfg.get("tts_edge_voice", "en-GB-SoniaNeural")),
            tts_elevenlabs_api_key=str(self.cfg.get("tts_elevenlabs_api_key", "")),
            tts_elevenlabs_voice_id=str(self.cfg.get("tts_elevenlabs_voice_id", "")),
            tts_elevenlabs_model_id=str(self.cfg.get("tts_elevenlabs_model_id", "eleven_flash_v2_5")),
            tts_elevenlabs_stability=float(self.cfg.get("tts_elevenlabs_stability", 0.45)),
            tts_elevenlabs_similarity_boost=float(self.cfg.get("tts_elevenlabs_similarity_boost", 0.75)),
            tts_elevenlabs_style=float(self.cfg.get("tts_elevenlabs_style", 0.10)),
            tts_elevenlabs_use_speaker_boost=bool(self.cfg.get("tts_elevenlabs_use_speaker_boost", True)),
            voice_backend=str(self.cfg.get("voice_backend", "vosk")),
            vosk_model_path=str(self.cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15")),
            sample_rate=int(self.cfg.get("sample_rate", 16000)),
            record_seconds=int(self.cfg.get("record_seconds", 5)),
            mic_device=str(self.cfg.get("mic_device", "default")),
            mic_channels=int(self.cfg.get("mic_channels", 1)),
            mic_software_gain_db=float(self.cfg.get("mic_software_gain_db", 0.0)),
            mic_noise_gate_dbfs=float(self.cfg.get("mic_noise_gate_dbfs", -48.0)),
            audio_filter_enabled=bool(self.cfg.get("audio_filter_enabled", True)),
            audio_highpass_enabled=bool(self.cfg.get("audio_highpass_enabled", True)),
            audio_highpass_hz=float(self.cfg.get("audio_highpass_hz", 90.0)),
            audio_notch_enabled=bool(self.cfg.get("audio_notch_enabled", True)),
            audio_notch_hz=float(self.cfg.get("audio_notch_hz", 50.0)),
            audio_notch_q=float(self.cfg.get("audio_notch_q", 25.0)),
            audio_notch_harmonics=int(self.cfg.get("audio_notch_harmonics", 2)),
            audio_noise_reduction_enabled=bool(self.cfg.get("audio_noise_reduction_enabled", True)),
            audio_noise_reduction_strength=float(self.cfg.get("audio_noise_reduction_strength", 0.20)),
            audio_noise_gate_knee_db=float(self.cfg.get("audio_noise_gate_knee_db", 10.0)),
            audio_live_fft_bins=int(self.cfg.get("audio_live_fft_bins", 48)),
            stt_validation_enabled=bool(self.cfg.get("stt_validation_enabled", True)),
            stt_min_confidence=float(self.cfg.get("stt_min_confidence", 0.40)),
            stt_min_voiced_ms=int(self.cfg.get("stt_min_voiced_ms", 280)),
            stt_min_longest_voiced_ms=int(self.cfg.get("stt_min_longest_voiced_ms", 160)),
            stt_min_words=int(self.cfg.get("stt_min_words", 1)),
            stt_min_chars=int(self.cfg.get("stt_min_chars", 2)),
            stt_noise_margin_db=float(self.cfg.get("stt_noise_margin_db", 6.0)),
            stt_reject_fillers=bool(self.cfg.get("stt_reject_fillers", True)),
            stt_repetition_guard_enabled=bool(self.cfg.get("stt_repetition_guard_enabled", True)),
            stt_max_consecutive_word_repeats=int(self.cfg.get("stt_max_consecutive_word_repeats", 3)),
            stt_max_repeated_phrase_count=int(self.cfg.get("stt_max_repeated_phrase_count", 2)),
            stt_min_unique_word_ratio=float(self.cfg.get("stt_min_unique_word_ratio", 0.30)),
            stt_max_words_per_second=float(self.cfg.get("stt_max_words_per_second", 7.0)),
            stt_max_transcript_words=int(self.cfg.get("stt_max_transcript_words", 90)),
            stt_reject_prompt_leakage=bool(self.cfg.get("stt_reject_prompt_leakage", True)),
            stt_capture_method=str(self.cfg.get("stt_capture_method", "alsa")),
            stt_endpointing_enabled=bool(self.cfg.get("stt_endpointing_enabled", True)),
            stt_start_timeout_s=float(self.cfg.get("stt_start_timeout_s", 8.0)),
            stt_max_utterance_s=float(self.cfg.get("stt_max_utterance_s", 20.0)),
            stt_pre_roll_ms=int(self.cfg.get("stt_pre_roll_ms", 700)),
            stt_end_silence_ms=int(self.cfg.get("stt_end_silence_ms", 1350)),
            stt_post_roll_ms=int(self.cfg.get("stt_post_roll_ms", 300)),
            stt_start_trigger_ms=int(self.cfg.get("stt_start_trigger_ms", 80)),
            stt_speech_resume_trigger_ms=int(self.cfg.get("stt_speech_resume_trigger_ms", 140)),
            stt_transient_guard_after_ms=int(self.cfg.get("stt_transient_guard_after_ms", 220)),
            stt_endpoint_hysteresis_db=float(self.cfg.get("stt_endpoint_hysteresis_db", 3.0)),
            stt_adaptive_threshold_enabled=bool(self.cfg.get("stt_adaptive_threshold_enabled", True)),
            stt_adaptive_margin_db=float(self.cfg.get("stt_adaptive_margin_db", 8.0)),
            stt_debug_keep_audio=bool(self.cfg.get("stt_debug_keep_audio", True)),
            tts_queue_enabled=bool(self.cfg.get("tts_queue_enabled", True)),
            tts_chunking_enabled=bool(self.cfg.get("tts_chunking_enabled", True)),
            tts_chunk_max_chars=int(self.cfg.get("tts_chunk_max_chars", 650)),
            tts_fallback_to_espeak=bool(self.cfg.get("tts_fallback_to_espeak", False)),
        )

    def _primary_brain_stt_active(self) -> bool:
        backend = str(self.cfg.get("stt_transcription_backend", "brain_faster_whisper") or "").lower().strip()
        return bool(self.cfg.get("brain_stt_enabled", True)) and backend in {
            "brain", "brain_whisper", "brain_faster_whisper", "faster_whisper",
        }

    def _defer_local_vosk_for_primary_stt(self) -> bool:
        return self._primary_brain_stt_active() and bool(self.cfg.get("stt_defer_local_vosk_when_brain_enabled", True))

    def _apply_primary_stt(
        self,
        result: Dict[str, Any],
        source: str = "live",
        stt_engine: Optional[VoskSpeechToText] = None,
    ) -> Dict[str, Any]:
        """Replace the local Vosk transcript with desktop faster-whisper.

        The body keeps ownership of microphone selection, filtering, natural
        endpointing and wake/session state.  The Brain PC receives only the
        finished mono PCM WAV.  Vosk remains a bounded offline fallback.
        """
        pipeline_started = time.monotonic()
        result = dict(result or {})
        wav_bytes = result.pop("_submitted_wav_bytes", b"") or b""
        handoff: Dict[str, Any] = {
            "schema": "bx1.body.primary_stt_handoff.v1",
            "audio_payload": "present" if wav_bytes else "absent",
            "valid_wav": False,
            "sample_rate_hz": None,
            "channels": None,
            "duration_s": None,
            "primary_request": "not_started",
            "request_started_at": None,
            "request_completed_at": None,
            "elapsed_ms": None,
            "engine_selected": "brain_faster_whisper" if self._primary_brain_stt_active() else "local_vosk",
            "fallback_reason": "",
        }
        if wav_bytes:
            try:
                with wave.open(io.BytesIO(wav_bytes), "rb") as submitted:
                    rate = int(submitted.getframerate())
                    channels = int(submitted.getnchannels())
                    width = int(submitted.getsampwidth())
                    duration_s = submitted.getnframes() / float(rate or 1)
                handoff.update({
                    "sample_rate_hz": rate, "channels": channels,
                    "duration_s": round(duration_s, 3),
                    "valid_wav": rate == 16000 and channels == 1 and width == 2 and duration_s > 0.0,
                })
                if not handoff["valid_wav"]:
                    handoff["fallback_reason"] = "submitted audio must be a complete 16 kHz mono 16-bit WAV"
            except (wave.Error, EOFError, ValueError) as exc:
                handoff["fallback_reason"] = f"invalid submitted WAV: {str(exc)[:120]}"
        result["primary_stt_handoff"] = handoff
        local_text = str(result.get("text") or "").strip()
        result["local_vosk_text"] = local_text
        result["transcription_backend"] = "local_vosk"
        result["primary_stt_error"] = ""
        local_deferred = bool(result.get("local_recognition_deferred", False))

        def apply_local_fallback(primary_error: str, backend_name: str = "local_vosk_fallback") -> bool:
            nonlocal local_text
            if local_text:
                handoff["fallback_reason"] = str(primary_error)[:240]
                result["transcription_backend"] = backend_name
                result["primary_stt_error"] = primary_error
                result["stt_pipeline_ms"] = round((time.monotonic() - pipeline_started) * 1000.0, 1)
                return bool(result.get("accepted", True))
            engine = stt_engine or self.stt
            if not local_deferred or engine is None or not bool(getattr(engine, "vosk_ready", False)) or not wav_bytes:
                return False
            fallback_result = engine.recognise_wav_bytes(wav_bytes, result.get("voice_activity", {}))
            local_text = str(fallback_result.get("text") or "").strip()
            result.update({
                "accepted": bool(fallback_result.get("accepted", False)),
                "reason": str(fallback_result.get("reason") or "local Vosk fallback"),
                "text": local_text,
                "local_vosk_text": local_text,
                "confidence": fallback_result.get("confidence"),
                "minimum_confidence": fallback_result.get("minimum_confidence"),
                "words": fallback_result.get("words", []),
                "transcript_quality": fallback_result.get("transcript_quality", {}),
                "local_recognition_ms": fallback_result.get("local_recognition_ms"),
                "transcription_backend": backend_name,
                "primary_stt_error": primary_error,
                "error": str(fallback_result.get("error") or ""),
                "stt_pipeline_ms": round((time.monotonic() - pipeline_started) * 1000.0, 1),
            })
            return bool(result.get("accepted", False))

        enabled = bool(self.cfg.get("brain_stt_enabled", True))
        backend = str(self.cfg.get("stt_transcription_backend", "brain_faster_whisper") or "").lower().strip()
        if not enabled or backend not in {"brain", "brain_whisper", "brain_faster_whisper", "faster_whisper"}:
            if local_deferred:
                apply_local_fallback("Primary Brain STT is disabled.", "local_vosk")
            return result
        if not wav_bytes:
            result["primary_stt_error"] = "No submitted WAV bytes were available for desktop transcription."
            handoff["fallback_reason"] = result["primary_stt_error"]
            result["stt_pipeline_ms"] = round((time.monotonic() - pipeline_started) * 1000.0, 1)
            return result
        if not self.brain.base_url:
            error = "Brain App URL is not configured; local Vosk fallback used."
            if not apply_local_fallback(error):
                result["primary_stt_error"] = error
                result["stt_pipeline_ms"] = round((time.monotonic() - pipeline_started) * 1000.0, 1)
            return result

        if not handoff["valid_wav"]:
            error = str(handoff["fallback_reason"] or "submitted WAV validation failed")
            if not apply_local_fallback(error):
                result["primary_stt_error"] = error
                result["stt_pipeline_ms"] = round((time.monotonic() - pipeline_started) * 1000.0, 1)
            return result

        remote_started = time.monotonic()
        handoff["primary_request"] = "started"
        handoff["request_started_at"] = now_iso()
        try:
            configured_hotwords = str(self.cfg.get("brain_stt_hotwords", "") or "").strip()
            wake_hints: List[str] = []
            for wake in self.get_wake_words():
                wake_hints.append(wake)
                wake_hints.extend(self._wake_aliases_for(wake))
            robot_hint = str(self.robot_name or self.robot_id or "BX1").strip()
            if robot_hint:
                wake_hints.append(robot_hint)
            hotwords = ", ".join(dict.fromkeys([part for part in ([configured_hotwords] if configured_hotwords else []) + wake_hints if part]))
            # Never put wake instructions into Whisper's initial prompt. In low
            # signal audio the decoder can emit the prompt itself as a transcript.
            # Wake names remain available through the dedicated hotwords field.
            initial_prompt = str(self.cfg.get("brain_stt_initial_prompt", "") or "").strip()
            remote = self.brain.transcribe_wav(
                wav_bytes,
                language=str(self.cfg.get("brain_stt_language", "en") or "en"),
                hotwords=hotwords,
                initial_prompt=initial_prompt,
                metadata={
                    "robot_id": self.robot_id,
                    "source": source,
                    "captured_at": result.get("captured_at", now_iso()),
                    "capture_method": result.get("capture_method", ""),
                    "local_vosk_text": local_text,
                },
                timeout_s=max(2, min(20, int(self.cfg.get("brain_stt_timeout_s", 12) or 12))),
            )
        except Exception as exc:
            remote = {"ok": False, "error": str(exc)}
        remote_roundtrip_ms = round((time.monotonic() - remote_started) * 1000.0, 1)
        handoff.update({"primary_request": "completed", "request_completed_at": now_iso(), "elapsed_ms": remote_roundtrip_ms})

        result["brain_stt"] = remote
        result["brain_stt_roundtrip_ms"] = remote_roundtrip_ms
        remote_text = str(remote.get("text") or "").strip() if isinstance(remote, dict) else ""
        if bool(remote.get("ok")) and remote_text:
            tokens = re.findall(r"[A-Za-z0-9']+", remote_text)
            fillers = {"huh", "uh", "um", "umm", "mm", "mmm", "hmm", "hm", "ah", "oh", "er", "erm", "eh"}
            quality = remote.get("transcript_quality") if isinstance(remote.get("transcript_quality"), dict) else analyse_transcript_quality(
                remote_text,
                duration_s=float(remote.get("duration_after_vad_s") or remote.get("duration_s") or 0.0),
                cfg=self.cfg,
            )
            accepted = bool(tokens) and not (tokens and all(t.lower() in fillers for t in tokens)) and bool(quality.get("ok", True))
            reason = "accepted" if accepted else (str(quality.get("reason") or "filler/noise fragment"))
            result.update({
                "accepted": accepted,
                "reason": reason,
                "transcript_quality": quality,
                "text": remote_text,
                "confidence": remote.get("confidence"),
                "words": [w for seg in remote.get("segments", []) if isinstance(seg, dict) for w in seg.get("words", [])],
                "transcription_backend": "brain_faster_whisper",
                "stt_model": remote.get("model", ""),
                "stt_device": remote.get("device", ""),
                "stt_compute_type": remote.get("compute_type", ""),
                "stt_latency_ms": remote.get("latency_ms"),
                "stt_pipeline_ms": round((time.monotonic() - pipeline_started) * 1000.0, 1),
                "primary_stt_error": "",
                "error": "" if accepted else str(remote.get("error") or ""),
            })
            return result

        error = str(remote.get("error") or "Desktop faster-whisper returned no transcript.")
        handoff["fallback_reason"] = error[:240]
        result["primary_stt_error"] = error
        # A valid desktop STT response that says "no speech" or "corrupt
        # transcript" is authoritative. Local Vosk must not resurrect the same
        # noise as a one-word wake command. Fallback is reserved for transport,
        # service or model failures where the desktop did not evaluate the WAV.
        desktop_evaluated = isinstance(remote, dict) and (
            "text" in remote or "transcript_quality" in remote or "wav" in remote
        )
        if desktop_evaluated:
            result.update({
                "accepted": False,
                "reason": str((remote.get("transcript_quality") or {}).get("reason") or error),
                "text": remote_text,
                "transcript_quality": remote.get("transcript_quality", {}),
                "transcription_backend": "brain_faster_whisper_rejected",
                "stt_latency_ms": remote.get("latency_ms"),
                "stt_pipeline_ms": round((time.monotonic() - pipeline_started) * 1000.0, 1),
                "error": error,
            })
            return result
        fallback = bool(self.cfg.get("brain_stt_fallback_to_vosk", True))
        if fallback and apply_local_fallback(error):
            return result
        result.update({
            "accepted": False,
            "reason": "desktop STT failed",
            "error": error,
            "transcription_backend": "brain_faster_whisper_failed",
            "stt_pipeline_ms": round((time.monotonic() - pipeline_started) * 1000.0, 1),
        })
        return result


    def get_led_state_settings(self) -> Dict[str, Any]:
        self.led_state_profiles = normalise_led_state_profiles(getattr(self, "led_state_profiles", self.cfg.get("led_state_profiles", {})))
        self.cfg["led_state_profiles"] = self.led_state_profiles
        return {
            "profiles": self.led_state_profiles,
            "state_order": list(LED_STATE_ORDER),
            "zone_order": list(LED_ZONE_ORDER),
            "current_state": self.last_led_state,
            "current_state_at": self.last_led_state_at,
        }

    def web_update_led_state_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.led_state_profiles = normalise_led_state_profiles(data.get("profiles", data.get("led_state_profiles", data)))
        self.cfg["led_state_profiles"] = self.led_state_profiles
        self.save_config_file()
        self.web_log("system", "LED state colour profiles saved")
        return {"ok": True, "led_states": self.get_led_state_settings(), "saved_to": str(CONFIG_PATH)}

    def apply_led_state(self, state: str, source: str = "system", include_mouth: bool = True, force: bool = False) -> Dict[str, Any]:
        state = str(state or "idle").strip().lower()
        # Do not hammer a known-offline MCU with a zone command for every state
        # transition.  The Hardware Doctor remains available and the requested
        # state is retained for when the bridge is repaired.
        if self.latest_state and self.latest_state.get("mcu_ok") is False:
            self.last_led_state = state
            self.last_led_state_at = now_iso()
            return {"ok": False, "state": state, "source": source, "skipped": "MCU bridge offline"}
        profiles = normalise_led_state_profiles(getattr(self, "led_state_profiles", {}))
        profile = profiles.get(state) or profiles.get("idle") or {}
        if not profile.get("enabled", True):
            return {"ok": False, "state": state, "error": "state profile disabled"}
        with self.led_state_lock:
            if not force and state == self.last_led_state and source not in {"manual", "web_test"}:
                return {"ok": True, "state": state, "skipped": "already active"}
            results = []
            zones = profile.get("zones", {}) if isinstance(profile.get("zones"), dict) else {}
            for zone in LED_ZONE_ORDER:
                if zone == "mouth" and not include_mouth:
                    continue
                z = zones.get(zone, {}) if isinstance(zones.get(zone), dict) else {}
                if not z.get("enabled", True):
                    continue
                action = {"type": "set_led_zone", "args": {"zone": zone, "colour": _colour_hex(z.get("colour", "#000000")), "brightness": max(0.0, min(1.0, float(z.get("brightness", 0.0))))}}
                res = self.hardware.send_action(action)
                results.append({"zone": zone, "ok": bool(res.ok), "value": res.value, "error": res.error})
            self.last_led_state = state
            self.last_led_state_at = now_iso()
        ok = all(item.get("ok") for item in results) if results else True
        self.web_log("led_state" if ok else "error", f"LED state applied: {state}", {"source": source, "results": results})
        return {"ok": ok, "state": state, "source": source, "results": results}

    def web_apply_led_state(self, state: str) -> Dict[str, Any]:
        return self.apply_led_state(state, source="web_test", force=True)

    def _mouth_audio_bool(self, key: str, default: bool) -> bool:
        try:
            return bool(self.cfg.get(key, default))
        except Exception:
            return default

    def _mouth_audio_float(self, key: str, default: float, lo: float, hi: float) -> float:
        try:
            value = float(self.cfg.get(key, default))
        except Exception:
            value = default
        return max(lo, min(hi, value))

    def _send_mouth_colour(self, colour: str, brightness: float) -> None:
        now_mono = time.monotonic()
        if self.latest_state and self.latest_state.get("mcu_ok") is False:
            self.mouth_audio_stop.set()
            self.mouth_audio_runtime.update({
                "active": False,
                "last_ok": False,
                "last_error": str(self.latest_state.get("bridge_error") or self.latest_state.get("mcu_error") or "MCU bridge offline"),
                "suspended": True,
                "suppressed_commands": int(self.mouth_audio_runtime.get("suppressed_commands", 0) or 0) + 1,
            })
            return
        if now_mono < self.mouth_led_block_until_mono:
            self.mouth_audio_runtime.update({
                "active": False,
                "suspended": True,
                "suppressed_commands": int(self.mouth_audio_runtime.get("suppressed_commands", 0) or 0) + 1,
            })
            return
        action = {
            "type": "set_led_zone",
            "args": {
                "zone": "mouth",
                "colour": str(colour or "cyan"),
                "brightness": float(max(0.0, min(1.0, brightness))),
            },
        }
        try:
            result = self.hardware.send_action(action)
            error_text = str(result.error or "")
            self.mouth_audio_runtime.update({
                "commands": int(self.mouth_audio_runtime.get("commands", 0) or 0) + 1,
                "last_colour": str(colour or "cyan"),
                "last_brightness": round(float(max(0.0, min(1.0, brightness))), 3),
                "last_command_at": now_iso(),
                "last_ok": bool(result.ok),
                "last_error": error_text,
                "transport": str((result.value or {}).get("mode", "")) if isinstance(result.value, dict) else "",
                "suspended": False if result.ok else bool(self.mouth_audio_runtime.get("suspended", False)),
            })
            if result.ok:
                self.mouth_led_block_until_mono = 0.0
                self.mouth_audio_runtime.update({"suspended": False, "suspended_until": ""})
                return
            low = error_text.lower()
            bridge_fault = any(token in low for token in (
                "not registered", "not available", "router socket not found",
                "no arduino mcu serial port", "connection refused", "broken pipe",
            ))
            if bridge_fault:
                cooldown = max(5.0, float(self.cfg.get("mouth_led_failure_cooldown_s", 30.0) or 30.0))
                self.mouth_led_block_until_mono = now_mono + cooldown
                self.mouth_audio_stop.set()
                self.mouth_audio_runtime.update({
                    "active": False,
                    "suspended": True,
                    "suspended_until": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() + cooldown)),
                })
            log_cooldown = max(5.0, float(self.cfg.get("mouth_led_error_log_cooldown_s", 30.0) or 30.0))
            signature = error_text[:240]
            if signature != self.mouth_led_last_error_signature or now_mono - self.mouth_led_last_error_log_mono >= log_cooldown:
                self.mouth_led_last_error_signature = signature
                self.mouth_led_last_error_log_mono = now_mono
                self.web_log("error", f"mouth LED suspended: {error_text}", {"action": action, "value": result.value, "cooldown_s": log_cooldown})
        except Exception as exc:
            error_text = str(exc)
            cooldown = max(5.0, float(self.cfg.get("mouth_led_failure_cooldown_s", 30.0) or 30.0))
            self.mouth_led_block_until_mono = now_mono + cooldown
            self.mouth_audio_stop.set()
            self.mouth_audio_runtime.update({
                "active": False, "last_ok": False, "last_error": error_text,
                "last_command_at": now_iso(), "suspended": True,
                "suspended_until": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() + cooldown)),
            })
            if error_text[:240] != self.mouth_led_last_error_signature or now_mono - self.mouth_led_last_error_log_mono >= cooldown:
                self.mouth_led_last_error_signature = error_text[:240]
                self.mouth_led_last_error_log_mono = now_mono
                self.web_log("error", f"mouth LED suspended: {error_text}", {"action": action, "cooldown_s": cooldown})

    def _led_profile_zone(self, state: str, zone: str) -> Dict[str, Any]:
        profiles = normalise_led_state_profiles(getattr(self, "led_state_profiles", {}))
        profile = profiles.get(str(state or "idle"), profiles.get("idle", {}))
        zones = profile.get("zones", {}) if isinstance(profile, dict) else {}
        return dict(zones.get(str(zone or "mouth"), {}) if isinstance(zones, dict) else {})

    def _mouth_style_from_text(self, text: str) -> Dict[str, Any]:
        lower = (text or "").lower()
        speaking_zone = self._led_profile_zone("speaking", "mouth")
        speaking_colour = _colour_hex(speaking_zone.get("colour", "#00ffff"), "#00ffff")
        state_level = max(0.0, min(1.0, float(speaking_zone.get("brightness", 0.22))))
        configured = list(self.cfg.get("mouth_audio_speaking_colours", []))
        colours = [speaking_colour] + [str(c) for c in configured if str(c).strip() and _colour_hex(c, speaking_colour) != speaking_colour]
        min_b = min(state_level, self._mouth_audio_float("mouth_audio_min_brightness", 0.04, 0.0, 1.0))
        max_b = max(state_level, self._mouth_audio_float("mouth_audio_max_brightness", 0.45, 0.0, 1.0))

        danger_words = ["danger", "warning", "error", "fault", "failed", "fail", "stop", "blocked", "unsafe", "hot", "overload"]
        thinking_words = ["thinking", "checking", "calculating", "processing", "looking", "searching", "wait", "stand by"]
        happy_words = ["done", "complete", "success", "working", "yes", "okay", "good", "ready"]
        humour_words = ["joke", "funny", "humour", "ridiculous", "silly", "sarcasm", "obviously"]

        if self._mouth_audio_bool("mouth_audio_use_text_intent", True):
            if any(w in lower for w in danger_words):
                colours = ["red", "amber", "red"]
                max_b = max(max_b, 0.55)
                min_b = max(min_b, 0.10)
            elif any(w in lower for w in thinking_words):
                colours = ["amber", "purple", "cyan"]
                max_b = max(max_b, 0.38)
            elif any(w in lower for w in humour_words):
                colours = ["purple", "pink", "blue"]
                max_b = max(max_b, 0.42)
            elif any(w in lower for w in happy_words):
                colours = ["green", "cyan", "soft_white"]
                max_b = max(max_b, 0.40)
            elif "?" in text:
                colours = ["cyan", "blue", "soft_white"]

        # Punctuation changes expression intensity. Very crude. Very useful.
        if "!" in text:
            max_b = min(0.80, max_b + 0.12)
        if "..." in text or "hmm" in lower:
            colours = ["purple", "amber", "cyan"]
            max_b = max(0.30, min(max_b, 0.42))

        colours = [str(c).strip() for c in colours if str(c).strip()] or ["cyan"]
        if max_b < min_b:
            min_b, max_b = max_b, min_b
        return {"colours": colours, "min_b": min_b, "max_b": max_b}

    def handle_mouth_audio_event(self, event: str, info: Dict[str, Any]) -> None:
        info = info or {}
        text = str(info.get("text", "") or "")
        backend = str(info.get("backend", "") or "").strip().lower()
        tag = str(info.get("tag", "") or "").strip().lower()
        is_local_cue = backend == "local-cue" or tag.startswith("local-cue")

        # Also use the mouth/speech events as an STT echo gate. Without this,
        # a USB microphone near the speaker can hear BX1's own Dot.TTS reply.
        if event == "speech_prepare":
            self.guard_stt_capture(1.5, "tts_prepare")
        elif event in {"speech_start", "speech_audio_file_start"}:
            self.guard_stt_capture(self.estimate_speech_guard_s(text, 1.5), "tts_start")
            self._speaker_playback_started()
        elif event in {"speech_stop", "speech_audio_file_stop"}:
            self.guard_stt_capture(float(self.cfg.get("stt_post_tts_guard_s", 1.25)), "tts_stop")
            self._speaker_playback_finished()

        if event == "speech_prepare" and not is_local_cue:
            # A long answer may be split into several Dot.TTS chunks. The
            # original thinking worker stops when chunk one starts speaking, so
            # restart bounded local feedback while a later chunk is rendered.
            if bool(self.cfg.get("thinking_cues_continue_through_tts_generation", True)):
                with self.active_thinking_lock:
                    has_progress_worker = self.active_thinking_stop is not None
                if not has_progress_worker:
                    self.start_thinking_cues("tts_continuation")
            before = self.get_voice_runtime_snapshot()
            prior = str(before.get("pre_speech_state") or before.get("state", "awake"))
            if prior in {"processing", "speechgen", "heard", "rejected"}:
                prior = "awake"
            self.set_voice_runtime(
                "speechgen",
                "Building the Dot.TTS voice; progress cues remain active.",
                loop_active=bool(before.get("loop_active", False)),
                pre_speech_state=prior,
                thinking_phase="tts_generation",
            )

        if not self._mouth_audio_bool("mouth_audio_reactive_enabled", True):
            return

        if event == "speech_prepare":
            # Subtle generation cue using the configured thinking LED profile.
            zone = self._led_profile_zone("thinking", "mouth")
            self._send_mouth_colour(_colour_hex(zone.get("colour", "#ff9900"), "#ff9900"), float(zone.get("brightness", 0.08)))
            return

        if event in {"speech_start", "speech_audio_file_start"}:
            if is_local_cue:
                # A short cached acknowledgement/filler is part of the thinking
                # phase, not the final answer. Animate the mouth but retain the
                # processing/speech-generation state in the UI.
                current = self.get_voice_runtime_snapshot()
                phase_state = "speechgen" if str(current.get("state")) == "speechgen" else "processing"
                self.set_voice_runtime(
                    phase_state,
                    text or ("Building the Dot.TTS voice…" if phase_state == "speechgen" else "Thinking…"),
                    loop_active=bool(current.get("loop_active", False)),
                    thinking_phase="local_progress_cue",
                    last_thinking_cue=text,
                )
                self.start_mouth_audio_animation(info)
                return

            # The final answer is about to reach the speaker. Stop further filler
            # cues and, if one is already playing, give it a brief chance to end
            # cleanly before the main reply starts.
            self.stop_active_thinking_cues("reply_audio_ready")
            wait_until = time.monotonic() + max(0.0, min(3.0, float(self.cfg.get("thinking_cue_finish_wait_s", 2.2))))
            while self.local_cue_playing.is_set() and time.monotonic() < wait_until:
                time.sleep(0.025)

            before = self.get_voice_runtime_snapshot()
            prior = str(before.get("pre_speech_state") or before.get("state", "idle"))
            if prior in {"processing", "speechgen", "heard", "rejected"}:
                prior = "awake"
            self.set_voice_runtime(
                "speaking",
                "BX1 is speaking; microphone muted.",
                loop_active=bool(before.get("loop_active", False)),
                pre_speech_state=prior,
                thinking_phase="reply_playback",
            )
            self.apply_led_state("speaking", source="tts_start", include_mouth=False, force=True)
            self.start_mouth_audio_animation(info)
        elif event in {"speech_stop", "speech_audio_file_stop"}:
            self.stop_mouth_audio_animation()
            if is_local_cue:
                # Do not return to awake/listening between a progress cue and the
                # final reply. The Dot.TTS request is still being generated.
                current = self.get_voice_runtime_snapshot()
                state = "speechgen" if str(current.get("state")) == "speechgen" else "processing"
                label = "Building the Dot.TTS voice; progress cues remain active." if state == "speechgen" else "Thinking…"
                self.set_voice_runtime(
                    state,
                    label,
                    loop_active=bool(current.get("loop_active", False)),
                    thinking_phase="tts_generation" if state == "speechgen" else "thinking",
                )
                return

            runtime = self.get_voice_runtime_snapshot()
            previous = str(runtime.get("pre_speech_state", "idle"))
            loop_active = bool(runtime.get("loop_active", False))

            # Start the conversational follow-up window when physical playback
            # finishes, not when the LLM text arrives. Dot.TTS can take many
            # seconds to render; starting the timer earlier consumed most of the
            # useful listening window and made BX1 appear not to hear follow-ups.
            if loop_active:
                hold_s = max(5.0, min(600.0, float(self.cfg.get("conversation_followup_window_s", 90.0))))
                self.set_conversation_active_until(time.monotonic() + hold_s)
                restore = "awake"
                label = f"Reply finished. Listening for follow-up for {hold_s:.0f}s."
            else:
                restore = "awake" if previous in {"awake", "processing", "speechgen", "heard"} else "idle"
                label = "Conversation active; listening for follow-up." if restore == "awake" else "Ready."
            self.set_voice_runtime(restore, label, loop_active=loop_active, thinking_phase="")
            self.apply_led_state(restore, source="tts_stop", include_mouth=False, force=True)

    def start_mouth_audio_animation(self, info: Optional[Dict[str, Any]] = None) -> None:
        info = info or {}
        if (self.latest_state and self.latest_state.get("mcu_ok") is False) or time.monotonic() < self.mouth_led_block_until_mono:
            self.mouth_audio_runtime.update({"active": False, "suspended": True})
            return
        text = str(info.get("text", "") or "")
        style = self._mouth_style_from_text(text)
        profile = info.get("audio_profile") if isinstance(info.get("audio_profile"), dict) else {}
        with self.mouth_audio_lock:
            self.mouth_audio_context = {
                "text": text,
                "style": style,
                "profile": profile if self._mouth_audio_bool("mouth_audio_use_wav_profile", True) else {},
                "event_info": info,
            }
            self.mouth_audio_started_at = time.time()
            self.mouth_audio_runtime.update({"active": True, "started_at": now_iso(), "profile_frames": len((profile or {}).get("levels", [])) if isinstance(profile, dict) else 0})
            if self.mouth_audio_thread and self.mouth_audio_thread.is_alive():
                return
            self.mouth_audio_stop.clear()
            self.mouth_audio_thread = threading.Thread(target=self._mouth_audio_animation_loop, name="bx1-mouth-audio", daemon=True)
            self.mouth_audio_thread.start()

    def stop_mouth_audio_animation(self) -> None:
        self.mouth_audio_stop.set()
        self.mouth_audio_runtime.update({"active": False, "stopped_at": now_iso()})
        idle_zone = self._led_profile_zone("idle", "mouth")
        idle_colour = _colour_hex(idle_zone.get("colour", "#00ffff"), "#00ffff")
        idle_brightness = max(0.0, min(1.0, float(idle_zone.get("brightness", 0.03))))
        if self._mouth_audio_bool("mouth_audio_off_after_speech", False):
            idle_colour = "#000000"
            idle_brightness = 0.0
        self._send_mouth_colour(idle_colour, idle_brightness)

    def _mouth_audio_animation_loop(self) -> None:
        min_s = self._mouth_audio_float("mouth_audio_pulse_min_s", 0.05, 0.02, 1.0)
        max_s = self._mouth_audio_float("mouth_audio_pulse_max_s", 0.13, 0.02, 1.0)
        if max_s < min_s:
            min_s, max_s = max_s, min_s

        step = 0
        while not self.mouth_audio_stop.is_set():
            with self.mouth_audio_lock:
                ctx = dict(self.mouth_audio_context)
                start_t = float(self.mouth_audio_started_at or time.time())
            style = ctx.get("style") if isinstance(ctx.get("style"), dict) else {}
            colours = list(style.get("colours") or ["cyan"])
            min_b = float(style.get("min_b", self._mouth_audio_float("mouth_audio_min_brightness", 0.04, 0.0, 1.0)))
            max_b = float(style.get("max_b", self._mouth_audio_float("mouth_audio_max_brightness", 0.45, 0.0, 1.0)))
            profile = ctx.get("profile") if isinstance(ctx.get("profile"), dict) else {}
            levels = profile.get("levels") if isinstance(profile.get("levels"), list) else []
            frame_s = float(profile.get("frame_s", 0.055) or 0.055)

            if levels:
                idx = int(max(0.0, time.time() - start_t) / max(0.01, frame_s))
                if idx >= len(levels):
                    level = 0.05
                else:
                    try:
                        level = float(levels[idx])
                    except Exception:
                        level = 0.05
            else:
                # No waveform available: pseudo speech envelope. Still much better than dead face.
                level = random.random() ** 0.45

            brightness = min_b + ((max_b - min_b) * max(0.0, min(1.0, level)))
            # Louder frames lean toward warmer/brighter colours.
            colour_idx = min(len(colours) - 1, int(max(0.0, min(0.999, level)) * len(colours)))
            if step % 7 == 0 and len(colours) > 1:
                colour_idx = (colour_idx + 1) % len(colours)
            colour = colours[colour_idx]
            self._send_mouth_colour(colour, brightness)
            step += 1
            delay = min_s if levels else random.uniform(min_s, max_s)
            if self.mouth_audio_stop.wait(delay):
                break



    # ------------------------------------------------------------------
    # AI / local expression engine
    # ------------------------------------------------------------------
    def expression_log(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        if bool(self.cfg.get("expression_debug_log", True)):
            self.web_log("expression", message, data or {})

    def expression_estimated_duration(self, text: str) -> float:
        cps = max(4.0, float(self.cfg.get("expression_speaking_estimated_chars_per_s", 13.0)))
        lo = max(0.2, float(self.cfg.get("expression_speaking_min_s", 1.2)))
        hi = max(lo, float(self.cfg.get("expression_speaking_max_s", 12.0)))
        return max(lo, min(hi, len(text or "") / cps))

    def expression_style_from_text(self, text: str, ai_expr: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return a safe expression plan.

        This can be driven by the Brain App later through result["expression"],
        but it also works now from the actual reply text. That gives BX1 a face
        even before the PC Brain is producing formal expression packets.
        """
        ai_expr = ai_expr if isinstance(ai_expr, dict) else {}
        lower = (text or "").lower()

        plan: Dict[str, Any] = {
            "mood": "neutral",
            "mouth_colour": "cyan",
            "mouth_brightness": 0.22,
            "eye_colour": "blue",
            "eye_brightness": 0.18,
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
            "nods": 1,
            "duration_s": self.expression_estimated_duration(text),
        }

        danger = ["danger", "warning", "error", "fault", "failed", "fail", "stop", "blocked", "unsafe", "hot", "overload"]
        success = ["done", "complete", "success", "working", "ready", "yes", "okay", "good", "fixed"]
        thinking = ["thinking", "checking", "calculating", "processing", "looking", "searching", "hmm", "stand by"]
        humour = ["joke", "funny", "humour", "ridiculous", "silly", "sarcasm", "obviously", "brilliant"]

        if any(w in lower for w in danger):
            plan.update({"mood": "warning", "mouth_colour": "amber", "eye_colour": "red", "mouth_brightness": 0.38, "eye_brightness": 0.24, "pitch": -2.0, "roll": -2.0, "nods": 0})
        elif any(w in lower for w in thinking):
            plan.update({"mood": "thinking", "mouth_colour": "purple", "eye_colour": "amber", "mouth_brightness": 0.20, "eye_brightness": 0.18, "yaw": -4.0, "pitch": 2.0, "roll": 2.0, "nods": 0})
        elif any(w in lower for w in humour):
            plan.update({"mood": "dry_humour", "mouth_colour": "purple", "eye_colour": "cyan", "mouth_brightness": 0.30, "eye_brightness": 0.22, "yaw": 5.0, "pitch": 1.5, "roll": -4.0, "nods": 1})
        elif any(w in lower for w in success):
            plan.update({"mood": "positive", "mouth_colour": "green", "eye_colour": "cyan", "mouth_brightness": 0.28, "eye_brightness": 0.22, "pitch": 2.5, "nods": 2})
        elif "?" in text:
            plan.update({"mood": "curious", "mouth_colour": "cyan", "eye_colour": "blue", "mouth_brightness": 0.24, "eye_brightness": 0.22, "yaw": -3.0, "pitch": 3.0, "roll": 2.0, "nods": 0})

        # Formal Brain expression packet can override the local inference.
        if bool(self.cfg.get("expression_ai_override_enabled", True)) and ai_expr:
            mood = str(ai_expr.get("mood") or ai_expr.get("emotion") or "").strip()
            if mood:
                plan["mood"] = mood
            for key in ("mouth_colour", "mouth_brightness", "eye_colour", "eye_brightness", "yaw", "pitch", "roll", "nods", "duration_s"):
                if key in ai_expr:
                    plan[key] = ai_expr[key]

        # Clamp before sending to hardware. Hard limits are still enforced lower down.
        plan["mouth_brightness"] = max(0.0, min(1.0, float(plan.get("mouth_brightness", 0.22))))
        plan["eye_brightness"] = max(0.0, min(1.0, float(plan.get("eye_brightness", 0.18))))
        plan["yaw"] = max(-20.0, min(20.0, float(plan.get("yaw", 0.0))))
        plan["pitch"] = max(-10.0, min(10.0, float(plan.get("pitch", 0.0))))
        plan["roll"] = max(-10.0, min(10.0, float(plan.get("roll", 0.0))))
        plan["nods"] = max(0, min(4, int(plan.get("nods", 1) or 0)))
        plan["duration_s"] = max(0.5, min(15.0, float(plan.get("duration_s", self.expression_estimated_duration(text)))))
        return plan

    def expression_send_led_zone(self, zone: str, colour: str, brightness: float) -> None:
        if not bool(self.cfg.get("expression_led_enabled", True)):
            return
        action = {"type": "set_led_zone", "args": {"zone": zone, "colour": colour, "brightness": float(brightness)}}
        try:
            self.hardware.send_action(action)
        except Exception as exc:
            self.expression_log(f"LED expression failed: {exc}", action)

    def expression_send_head(self, yaw: float, pitch: float, roll: float = 0.0) -> None:
        if not bool(self.cfg.get("expression_head_enabled", True)):
            return
        state = self.latest_state or self.read_body_state()
        if not bool(state.get("mcu_ok", False)):
            return
        if not bool(state.get("safety_ok", True)) or bool(state.get("fallen", False)):
            return
        pins = state.get("head_servo_pins") if isinstance(state.get("head_servo_pins"), dict) else {}
        yaw_pin = int(pins.get("yaw", -1) or -1)
        left_pin = int(pins.get("gimbal_left", pins.get("pitch", -1)) or -1)
        right_pin = int(pins.get("gimbal_right", pins.get("roll", -1)) or -1)
        if (abs(float(yaw)) > 0.01 and yaw_pin < 0) or ((abs(float(pitch)) > 0.01 or abs(float(roll)) > 0.01) and (left_pin < 0 or right_pin < 0)):
            self.expression_log("head movement requested but required servos are not attached", {
                "requested": {"yaw": yaw, "pitch": pitch, "roll": roll},
                "pins": {"yaw": yaw_pin, "gimbal_left": left_pin, "gimbal_right": right_pin},
                "hint": "Enable both gimbal servos, select valid pins, Save, then Apply Registry to MCU.",
            })
            return
        action = {"type": "set_head_pose", "args": {"yaw_deg": float(yaw), "pitch_deg": float(pitch), "roll_deg": float(roll)}}
        try:
            res = self.hardware.send_action(action)
            if res.ok:
                self.expression_last_head = {"yaw": float(yaw), "pitch": float(pitch), "roll": float(roll)}
            else:
                self.expression_log("head expression rejected", {"error": res.error, "action": action})
        except Exception as exc:
            self.expression_log(f"head expression failed: {exc}", action)

    def apply_expression_for_reply(self, reply: str, original_message: str = "", ai_expr: Optional[Dict[str, Any]] = None) -> None:
        if not bool(self.cfg.get("expression_engine_enabled", True)):
            return
        if not bool(self.cfg.get("expression_local_fallback_enabled", True)) and not ai_expr:
            return

        plan = self.expression_style_from_text(reply, ai_expr)
        duration = float(plan["duration_s"])
        with self.expression_lock:
            self.expression_busy_until = max(self.expression_busy_until, time.time() + duration + 0.5)

        self.expression_log("reply expression plan", {"plan": plan, "reply": reply[:220], "original_message": original_message[:220]})

        # LEDs immediately show the AI's expression. Mouth audio will take over
        # during actual speech, then return to idle afterwards.
        mouth_zone = str(self.cfg.get("expression_mouth_zone", "mouth") or "mouth")
        left_eye_zone = str(self.cfg.get("expression_eye_left_zone", "left_eye") or "left_eye")
        right_eye_zone = str(self.cfg.get("expression_eye_right_zone", "right_eye") or "right_eye")
        self.expression_send_led_zone(mouth_zone, str(plan["mouth_colour"]), float(plan["mouth_brightness"]))
        self.expression_send_led_zone(left_eye_zone, str(plan["eye_colour"]), float(plan["eye_brightness"]))
        self.expression_send_led_zone(right_eye_zone, str(plan["eye_colour"]), float(plan["eye_brightness"]))

        if bool(self.cfg.get("expression_speaking_head_enabled", True)):
            threading.Thread(target=self._expression_head_speech_worker, args=(plan,), name="bx1-expression-speech", daemon=True).start()

    def _expression_head_speech_worker(self, plan: Dict[str, Any]) -> None:
        yaw = float(plan.get("yaw", 0.0))
        pitch = float(plan.get("pitch", 0.0))
        roll = float(plan.get("roll", 0.0))
        duration = float(plan.get("duration_s", 2.0))
        nods = int(plan.get("nods", 1))

        # First move is a subtle "attention" pose.
        self.expression_send_head(yaw, pitch, roll)
        t_end = time.time() + duration

        for i in range(nods):
            if self.stop_event.is_set() or time.time() > t_end:
                break
            time.sleep(0.25)
            self.expression_send_head(yaw, max(-10.0, min(10.0, pitch + 3.0)), roll)
            time.sleep(0.18)
            self.expression_send_head(yaw, pitch, roll)

        # Small natural movement while speaking, not a twitchy parrot. Nobody wants that.
        while not self.stop_event.is_set() and time.time() < t_end:
            time.sleep(random.uniform(0.8, 1.8))
            if time.time() >= t_end:
                break
            self.expression_send_head(
                max(-20.0, min(20.0, yaw + random.uniform(-2.5, 2.5))),
                max(-10.0, min(10.0, pitch + random.uniform(-1.5, 1.5))),
                max(-10.0, min(10.0, roll + random.uniform(-1.2, 1.2))),
            )

        if bool(self.cfg.get("expression_head_home_after_reply", True)):
            time.sleep(0.15)
            self.expression_send_head(0.0, 0.0, 0.0)

        if bool(self.cfg.get("expression_led_idle_after_reply", True)):
            # Do not display IDLE while Dot.TTS is still generating or queued.
            # The previous behaviour produced a long visual dead zone immediately
            # before the robot actually started speaking.
            if not self.command_processing.is_set() and not self.speech_output_active():
                voice_state = str(self.get_voice_runtime_snapshot().get("state", "idle"))
                restore = "awake" if voice_state == "awake" else ("listening" if voice_state == "listening" else "idle")
                self.apply_led_state(restore, source="expression_complete", force=True)

    def expression_idle_loop(self) -> None:
        if not bool(self.cfg.get("expression_idle_head_enabled", True)):
            return
        while not self.stop_event.is_set():
            wait_s = random.uniform(float(self.cfg.get("expression_idle_head_min_s", 7.0)), float(self.cfg.get("expression_idle_head_max_s", 18.0)))
            if self.stop_event.wait(wait_s):
                return
            with self.expression_lock:
                if time.time() < self.expression_busy_until:
                    continue
            state = self.latest_state or self.read_body_state()
            if not bool(state.get("mcu_ok", False)) or not bool(state.get("safety_ok", True)) or bool(state.get("fallen", False)):
                continue
            yaw_max = abs(float(self.cfg.get("expression_idle_yaw_deg", 6.0)))
            pitch_max = abs(float(self.cfg.get("expression_idle_pitch_deg", 3.0)))
            yaw = random.uniform(-yaw_max, yaw_max)
            pitch = random.uniform(-pitch_max, pitch_max)
            roll = random.uniform(-2.0, 2.0)
            self.expression_send_head(yaw, pitch, roll)
            # Return home gently after a short look.
            if not self.stop_event.wait(random.uniform(0.8, 2.0)):
                self.expression_send_head(0.0, 0.0, 0.0)


    def hardware_startup_apply_loop(self) -> None:
        """Apply saved hardware registry after boot and move enabled servos to Home.

        This is deliberately retried because the MCU sketch/router can take a few
        seconds to become ready after upload or reboot. The apply action uses the
        same compact v10.5 Router RPC path as the web button. The MCU's
        bx1_config_servo() writes each enabled servo to its configured Home angle
        as soon as it attaches the pin.
        """
        if not bool(self.cfg.get("hardware_auto_apply_on_start", True)):
            return
        max_attempts = int(self.cfg.get("hardware_startup_apply_attempts", 20))
        delay_s = float(self.cfg.get("hardware_startup_apply_delay_s", 1.5))
        for attempt in range(1, max_attempts + 1):
            if self.stop_event.wait(delay_s):
                return
            try:
                state = self.hardware.get_status()
                if not bool(state.get("mcu_ok")):
                    self.web_log("system", f"startup hardware apply waiting for MCU ({attempt}/{max_attempts})", {"state": state})
                    continue
                result = self.web_apply_hardware_to_mcu()
                if result.get("ok"):
                    self.web_log("system", "startup hardware registry applied; enabled servos moved to Home", result)
                    print("[hardware] Startup hardware registry applied; enabled servos moved to Home.")
                    return
                self.web_log("error", "startup hardware apply failed", result)
            except Exception as exc:
                self.web_log("error", f"startup hardware apply exception: {exc}")
        print("[hardware] Startup hardware registry apply did not complete. Use Hardware / GPIO -> Apply Registry to MCU.")

    def start(self) -> None:
        self.print_banner()
        if bool(self.cfg.get("web_enabled", True)):
            self.start_web_interface()
        self._start_thread("telemetry", self.telemetry_loop)
        if bool(self.cfg.get("hardware_doctor_enabled", True)):
            self._start_thread("hardware_doctor", self.hardware_doctor_loop)
        self._start_thread("hardware_startup_apply", self.hardware_startup_apply_loop)
        if bool(self.cfg.get("expression_engine_enabled", True)) and bool(self.cfg.get("expression_idle_head_enabled", True)):
            self._start_thread("expression_idle", self.expression_idle_loop)
        if bool(self.cfg.get("idle_life_enabled", True)):
            self._start_thread("idle_life", self.idle_life_loop)

        input_mode = str(self.cfg.get("input_mode", "keyboard")).lower().strip()
        if input_mode in {"keyboard", "voice_or_keyboard", "both"}:
            self._start_thread("keyboard", self.keyboard_loop)
        if bool(self.cfg.get("voice_enabled", False)) and input_mode in {"voice", "voice_or_keyboard", "both"}:
            self.stt = VoskSpeechToText(self.build_audio_config())
            if self.stt.ready:
                self.set_voice_runtime("starting", "Starting live microphone/STT loop...", loop_active=False, last_error="")
                self._start_thread("voice", self.voice_loop)
            else:
                self.set_voice_runtime("error", f"STT not ready: {self.stt.error}", loop_active=False, last_error=str(self.stt.error))
                print(f"[audio] Voice disabled: {self.stt.error}")
        else:
            self.set_voice_runtime("disabled", "Live microphone/STT loop is disabled.", loop_active=False)

        if bool(self.cfg.get("send_periodic_vision", False)):
            self._start_thread("vision", self.periodic_vision_loop)
        if bool(self.cfg.get("send_periodic_camera_frames", True)):
            self._start_thread("camera_frame", self.periodic_camera_frame_loop)
        if bool(self.cfg.get("visual_awareness_enabled", True)):
            self._start_thread("visual_awareness", self.visual_awareness_loop)

    def _start_thread(self, name: str, target) -> None:  # type: ignore[no-untyped-def]
        t = threading.Thread(target=target, name=f"bx1-{name}", daemon=True)
        t.start()
        self.threads.append(t)

    def start_web_interface(self) -> None:
        host = str(self.cfg.get("web_host", "0.0.0.0"))
        port = int(self.cfg.get("web_port", 8088))
        self.web_server = WebControlServer(self, host=host, port=port)
        try:
            self.web_server.start()
        except OSError as exc:
            if getattr(exc, "errno", None) == 98:
                msg = (
                    f"Web port {port} is already in use. The body client is probably already running. "
                    f"Open the saved body-client URL, or stop the old copy with ./STOP_BX1_WEB.sh."
                )
                print(f"[web] ERROR: {msg}")
                self.web_log("error", msg)
                raise SystemExit(98) from exc
            raise
        self.web_log("system", f"Web control started on http://{host}:{port}")
        print(f"[web] Control interface: http://127.0.0.1:{port}")
        print(f"[web] From another machine try the robot hostname/IP on port {port}")

    def telemetry_loop(self) -> None:
        interval = float(self.cfg.get("telemetry_interval_s", 1.0))
        while not self.stop_event.is_set():
            state = self.read_body_state()
            t0 = time.perf_counter()
            try:
                if self.brain.base_url:
                    self.brain.send_body_state(state)
                    self.record_performance_sample("telemetry", (time.perf_counter() - t0) * 1000.0)
                else:
                    state["brain_error"] = "Brain App URL not configured"
            except Exception as exc:
                state["brain_error"] = str(exc)[:300]
                self.record_performance_sample("telemetry", (time.perf_counter() - t0) * 1000.0, error=str(exc))
            self.latest_state = state
            self.maybe_print_status(state)
            self.stop_event.wait(interval)

    def get_system_load_snapshot(self) -> Dict[str, Any]:
        """Return lightweight Linux/process load without requiring psutil.

        The Arduino Q Debian image may not have psutil installed.  Reading /proc
        keeps this visible on the web UI and in Brain telemetry by default.
        """
        report: Dict[str, Any] = {"ok": True, "source": "linux_proc"}
        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as fh:
                parts = fh.read().strip().split()
            if len(parts) >= 3:
                report["loadavg_1m"] = float(parts[0])
                report["loadavg_5m"] = float(parts[1])
                report["loadavg_15m"] = float(parts[2])
                cores = max(1, int(os.cpu_count() or 1))
                report["cpu_percent_est"] = round(min(100.0, (float(parts[0]) / cores) * 100.0), 1)
                report["cpu_cores"] = cores
        except Exception as exc:
            report["load_error"] = str(exc)

        try:
            mem: Dict[str, float] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    name, _, rest = line.partition(":")
                    val = rest.strip().split()[0] if rest.strip() else "0"
                    try:
                        mem[name] = float(val) / 1024.0
                    except Exception:
                        pass
            total = mem.get("MemTotal", 0.0)
            available = mem.get("MemAvailable", 0.0)
            used = max(0.0, total - available)
            if total > 0:
                report["memory_total_mb"] = round(total, 1)
                report["memory_available_mb"] = round(available, 1)
                report["memory_used_mb"] = round(used, 1)
                report["memory_percent"] = round((used / total) * 100.0, 1)
        except Exception as exc:
            report["memory_error"] = str(exc)

        try:
            import resource
            rss_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # Linux reports KB, macOS reports bytes; this target is Linux.
            report["process_rss_mb"] = round(rss_kb / 1024.0, 1)
        except Exception:
            pass
        try:
            report["process_threads"] = len(list(Path("/proc/self/task").iterdir()))
        except Exception:
            report["process_threads"] = threading.active_count()
        try:
            usage = shutil.disk_usage(str(PROJECT_ROOT))
            report["disk_total_gb"] = round(usage.total / (1024 ** 3), 2)
            report["disk_free_gb"] = round(usage.free / (1024 ** 3), 2)
            report["disk_percent"] = round(((usage.total - usage.free) / usage.total) * 100.0, 1) if usage.total else None
        except Exception:
            pass
        for temp_path in ("/sys/class/thermal/thermal_zone0/temp", "/sys/class/hwmon/hwmon0/temp1_input"):
            try:
                raw = Path(temp_path).read_text(encoding="utf-8").strip()
                val = float(raw)
                if val > 1000:
                    val /= 1000.0
                report["temperature_c"] = round(val, 1)
                break
            except Exception:
                continue
        report["speech_output_active"] = self.speech_output_active()
        report["stt_guard_remaining_s"] = round(self.stt_guard_remaining_s(), 2)
        return report

    def read_body_state(self) -> Dict[str, Any]:
        state = self.hardware.get_status()
        state.setdefault("robot_id", self.robot_id)
        state.setdefault("body_id", self.robot_id)
        state["body_profile"] = self.get_robot_profile_payload()
        state.setdefault("source", "uno_q_robot_body")
        state.setdefault("received_at_robot", now_iso())
        self.apply_manual_debug_state(state)
        # Apply final Linux-side safety fields so the Brain App gets consistent keys.
        pitch = float(state.get("pitch_deg", state.get("pitch", 0.0)) or 0.0)
        roll = float(state.get("roll_deg", state.get("roll", 0.0)) or 0.0)
        max_pitch = float(self.cfg.get("max_abs_pitch_deg", 35))
        max_roll = float(self.cfg.get("max_abs_roll_deg", 35))
        fallen = bool(state.get("fallen", False)) or abs(pitch) > max_pitch or abs(roll) > max_roll
        state["fallen"] = fallen
        if fallen:
            state["safety_ok"] = False
        else:
            state.setdefault("safety_ok", True)

        # V5 body packet additions: these are explicit fields for the Brain App.
        # They can be static now and later replaced by real sensors/SLAM/GPS.
        state["location"] = self.location.read()
        state["camera"] = {
            "enabled": bool(self.cfg.get("camera_enabled", True)),
            "device": str(self.cfg.get("camera_device", "/dev/video0")),
            "index": int(self.cfg.get("camera_index", 0)),
            "last_frame_sent_at": getattr(self, "last_camera_frame_sent_at", None),
        }
        state["mic"] = {
            "voice_enabled": bool(self.cfg.get("voice_enabled", False)),
            "backend": str(self.cfg.get("voice_backend", "vosk")),
            "device": str(self.cfg.get("mic_device", "default")),
            "sample_rate": int(self.cfg.get("sample_rate", 16000)),
            "monitor_running": bool(self.mic_monitor.is_running()),
            "level": self.mic_monitor.snapshot(),
            "runtime": self.get_voice_runtime_snapshot(),
        }
        state["sensors"] = {
            # MCU connectivity and IMU health are independent.
            "imu_ok": bool(state.get("imu_ok", False)),
            "imu_error": str(state.get("imu_error") or ""),
            "imu_source": str(state.get("imu_source") or "Modulino Movement / LSM6DSOX"),
            "imu_bus": str(state.get("imu_bus") or "Wire1/Qwiic"),
            "imu_address": str(state.get("imu_address") or "0x6A"),
            "imu_read_failures": int(state.get("imu_read_failures", 0) or 0),
            "imu_last_update_age_ms": state.get("imu_last_update_age_ms"),
            "mcu_ok": bool(state.get("mcu_ok", False)),
            "pitch_deg": pitch,
            "roll_deg": roll,
            "yaw_deg": state.get("yaw_deg", state.get("yaw")),
            "front_distance_mm": state.get("front_distance_mm", state.get("distance_front_mm", state.get("distance_mm"))),
            "obstacle": bool(state.get("obstacle", False)),
            "temperature_c": state.get("temperature_c", state.get("temperature")),
        }
        state["control_runtime"] = {
            "high_level_owner": "Linux Python",
            "high_level_language": "Python 3",
            "mcu_transport": "Arduino Router RPC",
            "mcu_runtime": str(state.get("mcu_runtime") or "minimal Arduino/Zephyr bridge shim"),
            "micropython_reference_bundle": "mcu_micropython/",
            "note": "UNO Q currently exposes the STM32 MCU through Arduino Core/Zephyr and Bridge; behaviour and tuning remain Python-owned.",
        }
        state["network"] = {
            "robot_direct_internet_required": False,
            "brain_app_base_url": str(self.cfg.get("brain_base_url", self.brain.base_url)),
            "brain_app_web_search_allowed_by_default": bool(self.cfg.get("use_web_for_robot_questions", False)),
            "note": "Internet/web lookup should be handled by the laptop Brain App when use_web is true; the robot body client only captures sensors and audio.",
        }
        state["hardware_map"] = self.get_hardware_settings()["hardware_map"]
        state["hardware_doctor"] = self.hardware_doctor.snapshot()
        state["system_load"] = self.get_system_load_snapshot()
        return state

    def apply_manual_debug_state(self, state: Dict[str, Any]) -> None:
        manual = dict(self.manual_debug_state or {})
        if not bool(manual.get("enabled", False)):
            return

        def parse_float(value: Any) -> Optional[float]:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        for src_key, state_key in [
            ("pitch_deg", "pitch_deg"),
            ("roll_deg", "roll_deg"),
            ("yaw_deg", "yaw_deg"),
            ("front_distance_mm", "front_distance_mm"),
            ("battery_v", "battery_v"),
        ]:
            parsed = parse_float(manual.get(src_key))
            if parsed is not None:
                state[state_key] = parsed

        location_label = str(manual.get("location_label", "") or "").strip()
        visual_context = str(manual.get("visual_context", "") or "").strip()
        state["manual_debug"] = {
            "enabled": True,
            "location_label": location_label,
            "visual_context": visual_context,
            "note": "Manual web debug context. Use only when real sensors/camera are not available.",
        }
        if visual_context:
            state["manual_visual_context"] = visual_context
        if location_label:
            state["manual_location_label"] = location_label

    def print_banner(self) -> None:
        print("\n" + "=" * 72)
        print(f" {self.robot_name} robot body service: {self.robot_id}")
        print("=" * 72)
        brain_url = str(self.cfg.get('brain_base_url', '') or '').strip()
        tts_url = str(self.cfg.get('brain_tts_base_url', '') or '').strip()
        print(f" Brain App : {brain_url or 'not configured - open /connection and use this browser PC'}")
        print(f" Brain voice : {tts_url or 'not configured - open /connection and use this browser PC'}")
        print(f" Bridge    : {'available' if self.hardware.available else 'not available / linux_only'}")
        print(f" Console   : {'quiet' if self.console_quiet else 'debug'}")
        print(" Commands  : /help  /status  /clear  /frame  /vision <prompt>  /quit")
        if bool(self.cfg.get("web_enabled", True)):
            print(f" Web UI    : http://127.0.0.1:{int(self.cfg.get('web_port', 8088))}")
        print("-" * 72)

    def format_state_line(self, state: Dict[str, Any]) -> str:
        fields = [
            f"mcu={state.get('mcu_ok')}",
            f"safe={state.get('safety_ok')}",
            f"pitch={state.get('pitch_deg', state.get('pitch'))}",
            f"roll={state.get('roll_deg', state.get('roll'))}",
            f"mode={state.get('mode')}",
        ]
        if state.get("fallen"):
            fields.append("fallen=True")
        if state.get("brain_error"):
            fields.append(f"brain_error={state.get('brain_error')}")
        return "; ".join(fields)

    def maybe_print_status(self, state: Dict[str, Any]) -> None:
        """Print telemetry without destroying the keyboard/chat prompt.

        In quiet mode the periodic telemetry still goes to the Brain App, but the
        terminal only prints state changes, errors, or manual /status requests.
        """
        now = time.monotonic()
        signature = "|".join([
            str(state.get("mcu_ok")),
            str(state.get("safety_ok")),
            str(state.get("fallen")),
            str(state.get("mode")),
            str(bool(state.get("brain_error"))),
        ])

        if self.console_quiet:
            # Print once at start and then only if the important state changes.
            if signature == self.last_status_signature:
                return
            self.last_status_signature = signature
            print(f"\n[status] {self.format_state_line(state)}")
            return

        interval = float(self.cfg.get("status_print_interval_s", 30))
        if now - self.last_status_print < interval:
            return
        self.last_status_print = now
        self.last_status_signature = signature
        print(f"\n[status] {self.format_state_line(state)}")

    def print_state_now(self) -> None:
        state = self.latest_state or self.read_body_state()
        print("\n" + "-" * 72)
        print(f" {self.robot_name} BODY STATE")
        print("-" * 72)
        print(self.format_state_line(state))
        print(json.dumps(state, indent=2, sort_keys=True))
        print("-" * 72)

    def print_help(self) -> None:
        print("\n" + "-" * 72)
        print(f" {self.robot_name} CONSOLE HELP")
        print("-" * 72)
        print(" Type normal text and press Enter to send it to the Brain App.")
        print(" /status              show current body telemetry")
        print(" /clear               clear this terminal")
        print(" /frame               send one webcam frame to the Brain App without LLM analysis")
        print(" /vision <prompt>     take a webcam image and ask the Brain App about it")
        print(" /quiet               enable quiet console mode")
        print(" /debug               enable periodic telemetry prints")
        print(" /quit                stop the robot body client")
        print("-" * 72)

    def handle_console_command(self, text: str) -> bool:
        command, _, arg = text.partition(" ")
        command = command.lower().strip()
        arg = arg.strip()
        if command in {"/help", "help"}:
            self.print_help()
            return True
        if command in {"/status", "status"}:
            self.print_state_now()
            return True
        if command in {"/clear", "clear", "cls"}:
            os.system("clear")
            self.print_banner()
            return True
        if command == "/quiet":
            self.console_quiet = True
            print("[console] quiet mode enabled")
            return True
        if command == "/debug":
            self.console_quiet = False
            print("[console] debug mode enabled; telemetry will print periodically")
            return True
        if command == "/frame":
            self.handle_camera_frame()
            return True
        if command == "/vision":
            self.handle_vision(arg or "Describe what you can see.")
            return True
        if command in {"/quit", "/exit", "quit", "exit", "shutdown"}:
            self.stop_event.set()
            return True
        return False

    def new_input_event_id(self, prefix: str = "evt") -> str:
        return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    def record_input_event(self, source: str, trigger: str, text: str = "", accepted: Optional[bool] = None,
                           reason: str = "", event_id: str = "", metadata: Optional[Dict[str, Any]] = None) -> str:
        eid = str(event_id or self.new_input_event_id(source.replace(" ", "_")[:12] or "evt"))
        event = {
            "event_id": eid, "timestamp": now_iso(), "source": str(source or "unknown"),
            "trigger": str(trigger or "unknown"), "text": str(text or ""),
            "accepted": accepted, "reason": str(reason or ""), "metadata": metadata or {},
        }
        self.input_events.append(event)
        self.web_log("input" if accepted is not False else "rejected_input",
                     f"{event['source']} / {event['trigger']}: {event['text'] or event['reason']}", event)
        return eid

    @staticmethod
    def _normalise_spoken_text(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(text or "").lower()))

    def _wake_aliases_for(self, configured: str) -> List[str]:
        configured = self._normalise_spoken_text(configured)
        aliases: List[str] = []
        raw = self.cfg.get("wake_word_aliases", {})
        if isinstance(raw, dict):
            values = raw.get(configured, [])
            if isinstance(values, str):
                values = [part.strip() for part in values.replace(",", "\n").splitlines() if part.strip()]
            if isinstance(values, list):
                aliases.extend(self._normalise_spoken_text(item) for item in values if str(item).strip())
        built_in = {
            "hello": ["hi", "hullo", "yellow"],
            "hey": ["hay"],
            "robot": ["robo", "row bot", "robert"],
            "leo": ["leon", "leah"],
            "bx1": ["b x one", "bee ex one", "box one"],
        }
        aliases.extend(built_in.get(configured, []))
        return list(dict.fromkeys(alias for alias in aliases if alias and alias != configured))

    def _match_wake_word_detailed(self, text: str, wake_words: List[str]) -> tuple[str, float, str]:
        low = self._normalise_spoken_text(text)
        normalised = [self._normalise_spoken_text(w) for w in wake_words if str(w).strip()]
        first_n = max(1, min(8, int(self.cfg.get("wake_match_first_tokens", 4) or 4)))
        prefix_tokens = low.split()[:first_n]
        prefix = " ".join(prefix_tokens)
        for wake in sorted(normalised, key=len, reverse=True):
            variants = [wake, *self._wake_aliases_for(wake)]
            for variant in sorted((v for v in variants if v), key=len, reverse=True):
                # Keep natural one-word wake choices (Hello, Hey, Robot), but
                # require them near the start of a sleeping utterance. This stops
                # a random mid-sentence hallucination from opening the session.
                haystack = prefix if wake in {"hello", "hey", "robot"} else low
                if re.search(r"(?:^|\s)" + re.escape(variant) + r"(?:$|\s)", haystack):
                    return wake, 1.0, "exact" if variant == wake else f"alias:{variant}"

        if not bool(self.cfg.get("wake_fuzzy_matching_enabled", True)) or not prefix_tokens:
            return "", 0.0, "none"
        threshold = max(0.60, min(0.95, float(self.cfg.get("wake_fuzzy_threshold", 0.74) or 0.74)))
        best_wake, best_score, best_variant = "", 0.0, ""
        candidates = []
        for width in range(1, min(3, len(prefix_tokens)) + 1):
            candidates.append(" ".join(prefix_tokens[:width]))
        for wake in normalised:
            for variant in [wake, *self._wake_aliases_for(wake)]:
                for candidate in candidates:
                    score = SequenceMatcher(None, candidate, variant).ratio()
                    if score > best_score:
                        best_wake, best_score, best_variant = wake, score, variant
        if best_wake and best_score >= threshold:
            return best_wake, best_score, f"fuzzy:{best_variant}"
        return "", best_score, "none"

    def _match_wake_word(self, text: str, wake_words: List[str]) -> str:
        return self._match_wake_word_detailed(text, wake_words)[0]

    def _strip_wake_words(self, text: str, wake_words: List[str]) -> str:
        cleaned = self._normalise_spoken_text(text)
        for wake in sorted((self._normalise_spoken_text(w) for w in wake_words if str(w).strip()), key=len, reverse=True):
            variants = {wake, *self._wake_aliases_for(wake)}
            for variant in sorted((v for v in variants if v), key=len, reverse=True):
                cleaned = re.sub(r"(?:^|\s)" + re.escape(variant) + r"(?=$|\s)", " ", cleaned, count=1)
        return " ".join(cleaned.split())

    def build_wake_diagnostics(
        self,
        stt_result: Dict[str, Any],
        metrics: Dict[str, Any],
        *,
        event_id: str,
        decision: str,
        reason: str = "",
        text: str = "",
        accepted: bool = False,
    ) -> Dict[str, Any]:
        """Create a compact evidence packet for live wake-word decisions."""
        capture = stt_result.get("capture") if isinstance(stt_result.get("capture"), dict) else {}
        voice = stt_result.get("voice_activity") if isinstance(stt_result.get("voice_activity"), dict) else {}
        audio = stt_result.get("audio") if isinstance(stt_result.get("audio"), dict) else {}
        threshold = voice.get("threshold_dbfs", capture.get("threshold_dbfs", self.cfg.get("mic_noise_gate_dbfs", -48.0)))
        peak = audio.get("peak_dbfs", capture.get("peak_dbfs"))
        rms = audio.get("rms_dbfs", capture.get("rms_dbfs"))
        try:
            gate_open = bool(float(peak if peak is not None else -120.0) >= float(threshold))
        except Exception:
            gate_open = bool(voice.get("voiced_ms", 0))
        diag = {
            "event_id": event_id,
            "decision": decision,
            "reason": reason,
            "accepted": bool(accepted),
            "listener_state": str(self.voice_runtime.get("state", "")),
            "audio_device": str(self.cfg.get("mic_device", "default")),
            "sample_rate": int(self.cfg.get("sample_rate", 16000)),
            "sample_width_bits": 16,
            "channels": int(self.cfg.get("mic_channels", 1)),
            "capture_method": str(stt_result.get("capture_method", self.cfg.get("stt_capture_method", "alsa"))),
            "record_seconds": int(self.cfg.get("record_seconds", 5)),
            "pre_roll_ms": int(self.cfg.get("stt_pre_roll_ms", 700)),
            "end_silence_ms": int(self.cfg.get("stt_end_silence_ms", 1350)),
            "post_roll_ms": int(self.cfg.get("stt_post_roll_ms", 300)),
            "start_trigger_ms": int(self.cfg.get("stt_start_trigger_ms", 80)),
            "noise_gate_dbfs": float(self.cfg.get("mic_noise_gate_dbfs", -48.0)),
            "threshold_dbfs": threshold,
            "rms_dbfs": rms,
            "peak_dbfs": peak,
            "gate_open": gate_open,
            "voiced_ms": voice.get("voiced_ms"),
            "speech_ratio": voice.get("speech_ratio"),
            "close_reason": capture.get("close_reason"),
            "duration_s": capture.get("duration_s"),
            "recognized_text": text,
            "recognition_confidence": stt_result.get("confidence"),
            "minimum_confidence": stt_result.get("minimum_confidence"),
            "wake_match": metrics.get("wake_match", ""),
            "wake_match_score": metrics.get("wake_match_score"),
            "wake_match_method": metrics.get("wake_match_method", ""),
            "wake_match_source": metrics.get("wake_match_source", ""),
            "cooldown_remaining_s": round(self.stt_guard_remaining_s(), 2),
            "tts_speaking_lockout": bool(self.speech_output_active()),
            "command_processing": bool(self.command_processing.is_set()),
            "manual_audio_capture_requested": bool(self.manual_audio_capture_requested.is_set()),
            "mic_monitor_running": bool(self.mic_monitor.is_running()),
        }
        return diag

    def log_wake_diagnostics(self, diagnostics: Dict[str, Any]) -> None:
        decision = str(diagnostics.get("decision") or "wake")
        kind = "system" if diagnostics.get("accepted") else "warning"
        score = diagnostics.get("wake_match_score")
        suffix = f", score={score}" if score is not None else ""
        self.web_log(kind, f"Wake diagnostic {decision}: {diagnostics.get('reason', '')}{suffix}", diagnostics)

    def is_duplicate_voice_transcript(self, text: str) -> bool:
        norm = self._normalise_spoken_text(text)
        if not norm:
            return False
        now = time.monotonic()
        window = max(2.0, float(self.cfg.get("stt_duplicate_window_s", 12.0) or 12.0))
        while self.recent_accepted_transcripts and now - float(self.recent_accepted_transcripts[0][0]) > window:
            self.recent_accepted_transcripts.popleft()
        if any(norm == item[1] for item in self.recent_accepted_transcripts):
            return True
        self.recent_accepted_transcripts.append((now, norm))
        return False

    def is_likely_tts_echo(self, text: str) -> tuple[bool, float]:
        norm = self._normalise_spoken_text(text)
        if len(norm) < 6:
            return False, 0.0
        now = time.monotonic()
        max_age = max(5.0, float(self.cfg.get("stt_echo_compare_window_s", 90.0) or 90.0))
        threshold = max(0.55, min(0.98, float(self.cfg.get("stt_echo_similarity_threshold", 0.78) or 0.78)))
        best = 0.0
        for spoken_at, spoken_text in list(self.recent_robot_speech):
            if now - float(spoken_at) > max_age:
                continue
            reply = self._normalise_spoken_text(spoken_text)
            if not reply:
                continue
            ratio = SequenceMatcher(None, norm, reply).ratio()
            n_tokens, r_tokens = set(norm.split()), set(reply.split())
            overlap = len(n_tokens & r_tokens) / max(1, len(n_tokens))
            score = max(ratio, overlap)
            best = max(best, score)
        return best >= threshold, best

    def hardware_doctor_loop(self) -> None:
        interval = max(5.0, float(self.cfg.get("hardware_doctor_interval_s", 15.0) or 15.0))
        while not self.stop_event.is_set():
            try:
                report = self.hardware_doctor.diagnose(self.latest_state or None)
                recovery = self.hardware_doctor.maybe_auto_recover(report)
                if recovery:
                    self.web_log("doctor" if recovery.get("ok") else "error", "Automatic bounded bridge recovery executed.", recovery)
            except Exception as exc:
                self.web_log("error", f"Hardware Doctor loop failed: {exc}")
            self.stop_event.wait(interval)

    def keyboard_loop(self) -> None:
        print("[console] Keyboard input active. Type a message and press Enter. Use /help for commands.")
        while not self.stop_event.is_set():
            try:
                text = input(f"\n{self.robot_name}> ").strip()
            except EOFError:
                print("[bx1] stdin closed; keyboard input disabled.")
                return
            except Exception as exc:
                print(f"[bx1] keyboard input error: {exc}")
                return
            if not text:
                continue
            if text.startswith("/") or text.lower() in {"help", "status", "clear", "cls", "quit", "exit", "shutdown"}:
                if self.handle_console_command(text):
                    continue
            self.handle_user_text(text)

    def _start_voice_stt_worker(self) -> None:
        with self.voice_stt_lock:
            if self.voice_stt_worker_started:
                return
            self.voice_stt_worker_started = True
            self._start_thread("voice-stt", self._voice_stt_worker_loop)

    def _queue_voice_stt(self, captured: Dict[str, Any]) -> bool:
        """Hand an immutable, bounded completed WAV to the non-capture worker."""
        payload = dict(captured or {})
        wav_bytes = payload.get("_submitted_wav_bytes", b"") or b""
        payload["_submitted_wav_bytes"] = bytes(wav_bytes)
        try:
            self.voice_stt_queue.put_nowait(payload)
        except queue.Full:
            self.set_voice_runtime("busy", "Speech worker busy; one utterance was dropped.", loop_active=True,
                                   last_error="STT worker queue full; utterance dropped")
            return False
        self.set_voice_runtime("recognising", "Speech queued for non-blocking recognition.", loop_active=True, last_error="")
        return True

    def _voice_stt_worker_loop(self) -> None:
        """Run desktop STT/Vosk fallback away from the sole ALSA capture loop."""
        while not self.stop_event.is_set():
            try:
                captured = self.voice_stt_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                suppression = self.speaker_suppression_snapshot()
                if suppression["suppressed"]:
                    state = "speaking" if suppression["playback_active"] else "echo_suppressed"
                    self.set_voice_runtime(state, "Queued microphone audio suppressed during speaker playback.", loop_active=True,
                                           speaker_playback_active=bool(suppression["playback_active"]),
                                           echo_tail_remaining_s=suppression["echo_tail_remaining_s"])
                    continue
                self.set_voice_runtime("recognising", "Recognising queued speech…", loop_active=True, last_error="")
                resolved = self._apply_primary_stt(captured, source="live_voice", stt_engine=self.stt)
                self._process_voice_worker_result(resolved)
            except Exception as exc:
                resolved = dict(captured)
                resolved.update({"accepted": False, "text": "", "reason": "STT worker failed", "error": str(exc),
                                 "transcription_backend": "worker_failed"})
                self._process_voice_worker_result(resolved)
    def _process_voice_worker_result(self, stt_result: Dict[str, Any]) -> None:
        """Apply recognised voice text without returning to or blocking ALSA."""
        if stt_result.get("cancelled"):
            return
        if self.speaker_suppression_snapshot()["suppressed"]:
            self.set_voice_runtime("echo_suppressed", "Recognised audio suppressed during speaker playback; no Brain request sent.",
                                   loop_active=True)
            return
        text = str(stt_result.get("text") or "").strip()
        reason = str(stt_result.get("reason") or stt_result.get("error") or "speech rejected")[:240]
        metrics = {
            "confidence": stt_result.get("confidence"),
            "transcription_backend": stt_result.get("transcription_backend", "unknown"),
            "brain_stt_roundtrip_ms": stt_result.get("brain_stt_roundtrip_ms"),
            "primary_stt_error": stt_result.get("primary_stt_error", ""),
        }
        if not stt_result.get("accepted", False):
            self.set_voice_runtime("rejected", f"Rejected microphone input: {reason}", loop_active=True,
                                   last_rejected=text, last_rejection_reason=reason, last_stt_metrics=metrics)
            return
        wake_words = self.get_wake_words()
        low = self._normalise_spoken_text(text)
        matched_wake, wake_score, wake_method = self._match_wake_word_detailed(low, wake_words)
        awake = time.monotonic() < float(getattr(self, "conversation_active_until", 0.0) or 0.0)
        if wake_words and not matched_wake and not awake:
            self.set_voice_runtime("ignored", "Heard speech without a configured wake phrase.", loop_active=True,
                                   last_heard=text, last_rejected=text, last_rejection_reason="wake phrase required",
                                   last_stt_metrics=metrics)
            return
        cleaned = self._strip_wake_words(low, wake_words) if matched_wake else low
        if matched_wake and not cleaned:
            hold_s = max(3.0, min(60.0, float(self.cfg.get("wake_command_window_s", 12.0))))
            self.set_conversation_active_until(time.monotonic() + hold_s)
            self.set_voice_runtime("awake", f"Wake word detected: {matched_wake}. Listening for command…", loop_active=True,
                                   last_heard=text, last_wake_word=matched_wake, last_wake_at=now_iso(), last_stt_metrics=metrics)
            self.acknowledge_voice_event("wake")
            return
        if not cleaned:
            cleaned = text
        self.set_voice_runtime("processing", "Sending recognised command to Brain App…", loop_active=True,
                               last_heard=text, last_accepted=cleaned, last_stt_metrics=metrics)
        if self.speaker_suppression_snapshot()["suppressed"]:
            self.set_voice_runtime("echo_suppressed", "Speaker suppression started before Brain submission; request dropped.", loop_active=True)
            return
        event_id = self.new_input_event_id("voice")
        try:
            with self.command_lock:
                result = self.handle_user_text(cleaned, source="robot_microphone", trigger="voice_command",
                                               event_id=event_id, input_metadata=metrics)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        if result.get("ok", False):
            hold_s = max(5.0, min(600.0, float(self.cfg.get("conversation_followup_window_s", 90.0))))
            self.set_conversation_active_until(time.monotonic() + hold_s)
            self.set_voice_runtime("speaking" if self.speech_output_active() else "awake",
                                   "Reply is playing." if self.speech_output_active() else "Reply complete; listening for follow-up.",
                                   loop_active=True, last_heard=text, last_accepted=cleaned, last_stt_metrics=metrics)
        else:
            error = str(result.get("error") or "Brain request failed")[:240]
            self.set_voice_runtime("error", f"Voice command failed: {error}", loop_active=True, last_error=error,
                                   last_stt_metrics=metrics)
    def voice_loop(self) -> None:
        print("[audio] Voice loop active.")
        self._start_voice_stt_worker()
        self.set_voice_runtime("listening", "Listening for wake word...", loop_active=True, last_error="")
        awake_until = 0.0

        def clean_command_text(raw_text: str, wake_words: List[str]) -> str:
            return self._strip_wake_words(raw_text, wake_words)

        while not self.stop_event.is_set():
            input_mode = str(self.cfg.get("input_mode", "keyboard")).lower().strip()
            if not bool(self.cfg.get("voice_enabled", False)) or input_mode not in {"voice", "voice_or_keyboard", "both"}:
                self.set_voice_runtime("disabled", "Live microphone/STT loop is disabled.", loop_active=False)
                self.stop_event.wait(1)
                continue
            if self.stt is None or not getattr(self.stt, "ready", False):
                self.set_voice_runtime("starting", "Starting STT engine...", loop_active=False)
                self.stt = VoskSpeechToText(self.build_audio_config())
                if not self.stt.ready:
                    err = str(self.stt.error)
                    self.set_voice_runtime("error", f"STT not ready: {err}", loop_active=False, last_error=err)
                    self.web_log("error", f"voice disabled: {err}")
                    self.stop_event.wait(5)
                    continue

            # Let microphone diagnostics / Listen Once take ownership cleanly.
            if self.manual_audio_capture_requested.is_set():
                self.set_voice_runtime("paused", "Wake listener paused while microphone diagnostics use the mic.", loop_active=True)
                self.stop_event.wait(0.25)
                continue

            wake_words = self.get_wake_words()
            now_mono = time.monotonic()
            suppression = self.speaker_suppression_snapshot()
            # A person entering view can open the same follow-up window as a
            # spoken wake word. The global value is also used by idle-life.
            external_awake_until = float(getattr(self, "conversation_active_until", 0.0) or 0.0)
            if external_awake_until > awake_until:
                awake_until = external_awake_until
            is_awake_waiting = now_mono < awake_until
            if suppression["playback_active"]:
                self.set_voice_runtime("speaking", "Leo speaking — microphone wake detection temporarily suppressed.",
                                       loop_active=True, speaker_playback_active=True, echo_tail_remaining_s=0.0)
            elif suppression["echo_tail_remaining_s"] > 0:
                remain = float(suppression["echo_tail_remaining_s"])
                self.set_voice_runtime("echo_suppressed", f"Speaker playback finished — wake detection suppressed for {remain:.1f}s.",
                                       loop_active=True, speaker_playback_active=False, echo_tail_remaining_s=remain)
            elif is_awake_waiting:
                remain = max(0.0, awake_until - now_mono)
                self.set_voice_runtime(
                    "awake",
                    f"Awake. Listening for command for {remain:.0f}s...",
                    loop_active=True,
                    last_error="",
                )
            else:
                wake_text = ", ".join(wake_words[:5]) if wake_words else "any speech"
                self.set_voice_runtime(
                    "listening",
                    f"Listening for wake word: {wake_text}",
                    loop_active=True,
                    last_error="",
                )
            try:
                # Own the capture device while Vosk/ALSA listens.  This avoids
                # arecord/sounddevice fighting with the diagnostics page.
                got_lock = self.audio_capture_lock.acquire(timeout=1.0)
                if not got_lock:
                    self.set_voice_runtime("paused", "Wake listener waiting for microphone to become free...", loop_active=True)
                    self.stop_event.wait(0.25)
                    continue
                monitor_was_running = bool(self.mic_monitor.is_running())
                try:
                    if monitor_was_running:
                        self.mic_monitor.stop()
                        time.sleep(0.1)
                    stt_result = self.stt.listen_once_detailed(
                        float(self.cfg.get("record_seconds", 5)),
                        defer_local_recognition=self._defer_local_vosk_for_primary_stt(),
                        cancel_event=self.manual_audio_capture_requested,
                        level_observer=self.update_live_voice_observation,
                    )
                    if not stt_result.get("cancelled"):
                        suppression = self.speaker_suppression_snapshot()
                        if suppression["suppressed"]:
                            state = "speaking" if suppression["playback_active"] else "echo_suppressed"
                            self.set_voice_runtime(state, "Microphone suppressed during speaker playback; no wake/STT request accepted.",
                                                   loop_active=True, speaker_playback_active=bool(suppression["playback_active"]),
                                                   echo_tail_remaining_s=suppression["echo_tail_remaining_s"])
                            continue
                        self._queue_voice_stt(stt_result)
                        # The worker owns desktop STT/Vosk fallback and Brain
                        # dispatch. Do not make the ALSA capture thread wait.
                        continue
                    text = str(stt_result.get("text") or "").strip()
                finally:
                    # A manual Listen Once request may have interrupted this live
                    # capture. Do not reopen the level-meter arecord process while
                    # the manual request is waiting to take ownership.
                    if monitor_was_running and not self.manual_audio_capture_requested.is_set():
                        try:
                            self._refresh_mic_monitor_settings()
                            self.mic_monitor.start()
                        except Exception:
                            pass
                    self.audio_capture_lock.release()
            except Exception as exc:
                err = str(exc)
                self.set_voice_runtime("error", f"Listen failed: {err}", loop_active=True, last_error=err)
                self.web_log("error", f"voice listen failed: {err}")
                self.stop_event.wait(1)
                continue

            if stt_result.get("cancelled"):
                self.set_voice_runtime(
                    "paused",
                    "Live wake capture yielded to a manual microphone request.",
                    loop_active=True,
                    last_error="",
                )
                continue

            event_id = self.new_input_event_id("voice")
            # A manual request may have started while listen_once_detailed() owned
            # the ALSA device. Discard that overlapping capture rather than feeding
            # thinking cues or robot speech back into the Brain.
            if self.command_processing.is_set() or self.speech_output_active():
                self.record_input_event("microphone", "overlap_guard", text, False, "capture overlapped Brain/TTS activity", event_id, {})
                self.set_voice_runtime("processing", "Discarded microphone capture that overlapped Brain/TTS activity.", loop_active=True)
                continue
            metrics = {
                "confidence": stt_result.get("confidence"),
                "voice_activity": stt_result.get("voice_activity", {}),
                "audio": stt_result.get("audio", {}),
                "capture_method": stt_result.get("capture_method", ""),
                "transcription_backend": stt_result.get("transcription_backend", "local_vosk"),
                "local_vosk_text": stt_result.get("local_vosk_text", ""),
                "stt_model": stt_result.get("stt_model", ""),
                "stt_device": stt_result.get("stt_device", ""),
                "stt_compute_type": stt_result.get("stt_compute_type", ""),
                "stt_latency_ms": stt_result.get("stt_latency_ms"),
                "brain_stt_roundtrip_ms": stt_result.get("brain_stt_roundtrip_ms"),
                "local_recognition_ms": stt_result.get("local_recognition_ms"),
                "stt_pipeline_ms": stt_result.get("stt_pipeline_ms"),
                "primary_stt_error": stt_result.get("primary_stt_error", ""),
                "transcript_quality": stt_result.get("transcript_quality", {}),
                "duration_s": (stt_result.get("capture") or {}).get("duration_s"),
                "duration_after_vad_s": (stt_result.get("brain_stt") or {}).get("duration_after_vad_s") if isinstance(stt_result.get("brain_stt"), dict) else None,
            }
            if not stt_result.get("accepted", False):
                rejected_text = self._normalise_spoken_text(text)
                rejected_local_text = self._normalise_spoken_text(str(stt_result.get("local_vosk_text") or ""))
                rejected_wake, rejected_score, rejected_method = self._match_wake_word_detailed(rejected_text, wake_words)
                rejected_source = "primary" if rejected_wake else ""
                if not rejected_wake and rejected_local_text:
                    rejected_wake, rejected_score, rejected_method = self._match_wake_word_detailed(rejected_local_text, wake_words)
                    if rejected_wake:
                        rejected_source = "local_vosk_fallback"
                if rejected_wake:
                    metrics.update({
                        "stt_gate_override": "wake_phrase",
                        "wake_match": rejected_wake,
                        "wake_match_score": round(float(rejected_score or 0.0), 3),
                        "wake_match_method": rejected_method,
                        "wake_match_source": rejected_source or "primary",
                        "original_stt_rejection_reason": stt_result.get("reason") or stt_result.get("error") or "speech rejected",
                    })
                    stt_result["accepted"] = True
                    stt_result["reason"] = "configured wake phrase accepted despite STT gate"
                else:
                    pass
            if not stt_result.get("accepted", False):
                reason = str(stt_result.get("reason") or stt_result.get("error") or "speech rejected")
                if text or reason not in {"no recognised speech", ""}:
                    diagnostics = self.build_wake_diagnostics(
                        stt_result, metrics, event_id=event_id, decision="stt_rejected",
                        reason=reason, text=text, accepted=False,
                    )
                    metrics["wake_diagnostics"] = diagnostics
                    self.log_wake_diagnostics(diagnostics)
                    self.record_input_event("microphone", "stt_gate", text, False, reason, event_id, metrics)
                    self.set_voice_runtime("rejected", f"Rejected microphone input: {reason}", loop_active=True,
                                           last_rejected=text, last_rejection_reason=reason, last_stt_metrics=metrics,
                                           last_wake_diagnostics=diagnostics, last_event_id=event_id)
                continue
            low = self._normalise_spoken_text(text)
            echo, echo_score = self.is_likely_tts_echo(low)
            if echo:
                metrics["echo_similarity"] = round(echo_score, 3)
                diagnostics = self.build_wake_diagnostics(
                    stt_result, metrics, event_id=event_id, decision="echo_rejected",
                    reason="resembles recent robot speech", text=text, accepted=False,
                )
                metrics["wake_diagnostics"] = diagnostics
                self.log_wake_diagnostics(diagnostics)
                self.record_input_event("microphone", "echo_guard", text, False, "resembles recent robot speech", event_id, metrics)
                self.set_voice_runtime("rejected", f"Rejected likely speaker echo ({echo_score:.2f}): {text}", loop_active=True,
                                       last_rejected=text, last_rejection_reason="speaker echo", last_stt_metrics=metrics,
                                       last_wake_diagnostics=diagnostics, last_event_id=event_id)
                continue
            if self.is_duplicate_voice_transcript(low):
                diagnostics = self.build_wake_diagnostics(
                    stt_result, metrics, event_id=event_id, decision="duplicate_rejected",
                    reason="duplicate transcript", text=text, accepted=False,
                )
                metrics["wake_diagnostics"] = diagnostics
                self.log_wake_diagnostics(diagnostics)
                self.record_input_event("microphone", "duplicate_guard", text, False, "duplicate transcript", event_id, metrics)
                self.set_voice_runtime("rejected", f"Rejected duplicate transcript: {text}", loop_active=True,
                                       last_rejected=text, last_rejection_reason="duplicate transcript", last_stt_metrics=metrics,
                                       last_wake_diagnostics=diagnostics, last_event_id=event_id)
                continue
            self.set_voice_runtime("heard", f"Validated speech: {text}", loop_active=True, last_heard=text, last_stt_metrics=metrics, last_event_id=event_id)
            matched_wake, wake_score, wake_method = self._match_wake_word_detailed(low, wake_words)
            wake_match_source = "primary" if matched_wake else ""
            local_wake_text = self._normalise_spoken_text(str(stt_result.get("local_vosk_text") or ""))
            if not matched_wake and local_wake_text:
                matched_wake, wake_score, wake_method = self._match_wake_word_detailed(local_wake_text, wake_words)
                if matched_wake:
                    wake_match_source = "local_vosk_fallback"
            metrics.update({
                "wake_match": matched_wake,
                "wake_match_score": round(float(wake_score or 0.0), 3),
                "wake_match_method": wake_method,
                "wake_match_source": wake_match_source or "none",
            })

            if wake_words and not matched_wake and not is_awake_waiting:
                print(f"[audio] Heard but ignored: {text}")
                diagnostics = self.build_wake_diagnostics(
                    stt_result, metrics, event_id=event_id, decision="wake_rejected",
                    reason=f"no wake word while conversation inactive; closest score={wake_score:.2f}",
                    text=text, accepted=False,
                )
                metrics["wake_diagnostics"] = diagnostics
                self.log_wake_diagnostics(diagnostics)
                self.set_voice_runtime(
                    "ignored",
                    f"Heard but ignored because no wake word was found: {text}",
                    loop_active=True,
                    last_heard=text,
                    last_ignored=text,
                    wake_match_source="none",
                    wake_match_score=round(float(wake_score or 0.0), 3),
                    last_wake_diagnostics=diagnostics,
                )
                self.record_input_event("microphone", "wake_gate", text, False, f"no wake word while conversation inactive; closest score={wake_score:.2f}", event_id, metrics)
                continue

            cleaned = clean_command_text(low, wake_words)
            # Exact/alias stripping above cannot remove a slightly misspelled
            # wake token such as "helo". Fuzzy matching only examines the
            # beginning of the primary transcript, so remove the matched prefix
            # there. Do not alter a primary transcript when only Vosk found the
            # wake word; Whisper may already have omitted it.
            if matched_wake and wake_match_source == "primary" and str(wake_method).startswith("fuzzy:"):
                fuzzy_variant = str(wake_method).split(":", 1)[1].strip()
                prefix_width = max(1, len(fuzzy_variant.split()))
                cleaned_parts = cleaned.split()
                removed_prefix = " ".join(cleaned_parts[:prefix_width])
                cleaned = " ".join(cleaned_parts[prefix_width:])
                metrics["wake_fuzzy_removed_prefix"] = removed_prefix

            # Two-stage wake mode: saying only "BX1" wakes the robot and opens a
            # short command window.  The next phrase is accepted without needing
            # the wake word again.  This feels much more natural than requiring
            # "BX1, <command>" in the same recognition sample.
            if matched_wake and not cleaned:
                hold_s = max(3.0, min(60.0, float(self.cfg.get("wake_command_window_s", 12.0))))
                awake_until = time.monotonic() + hold_s
                self.set_conversation_active_until(awake_until)
                print(f"[audio] Wake word detected: {matched_wake}; waiting for command")
                diagnostics = self.build_wake_diagnostics(
                    stt_result, metrics, event_id=event_id, decision="wake_only_accepted",
                    reason="wake-only activation", text=text, accepted=True,
                )
                metrics["wake_diagnostics"] = diagnostics
                self.log_wake_diagnostics(diagnostics)
                self.record_input_event("microphone", "wake_word", text, True, "wake-only activation", event_id, metrics)
                self.set_voice_runtime(
                    "awake",
                    f"Wake word detected: {matched_wake}. Listening for command...",
                    loop_active=True,
                    last_heard=text,
                    last_accepted="",
                    last_wake_word=matched_wake,
                    last_wake_at=now_iso(),
                    wake_match_source=wake_match_source or "primary",
                    wake_match_score=round(float(wake_score or 1.0), 3),
                    last_wake_diagnostics=diagnostics,
                )
                self.acknowledge_voice_event("wake")
                if bool(self.cfg.get("wake_voice_ack_enabled", True)):
                    available = [(key, value) for key, value in self.get_local_voice_cue_texts().items() if key == "wake_ack" or key.startswith("wake_ack_")]
                    cue_key, phrase = random.choice(available) if available else ("wake_ack", "Yes John?")
                    if not self.play_local_voice_cue(cue_key, phrase, allow_main_tts_fallback=False):
                        # Do not call Brain/Dot.TTS live for the wake acknowledgement;
                        # it must be immediate. Generate the cache from Thinking Cues.
                        self.guard_stt_capture(self.estimate_speech_guard_s(phrase, 1.2), "wake_ack_uncached")
                continue

            if is_awake_waiting and not cleaned:
                cleaned = low
            if not cleaned:
                cleaned = text.strip()

            sleep_phrases = self.cfg.get("sleep_phrases", DEFAULT_SLEEP_PHRASES)
            if isinstance(sleep_phrases, str):
                sleep_phrases = [p.strip().lower() for p in sleep_phrases.replace(",", "\n").splitlines() if p.strip()]
            else:
                sleep_phrases = [str(p).strip().lower() for p in sleep_phrases if str(p).strip()]
            if cleaned.lower().strip() in set(sleep_phrases):
                awake_until = 0.0
                self.set_conversation_active_until(0.0)
                self.record_input_event("microphone", "sleep_phrase", cleaned, True, "conversation closed", event_id, metrics)
                self.set_voice_runtime("asleep", "Sleep command accepted. Listening for wake word only.", loop_active=True, last_accepted=cleaned)
                phrase = str(self.cfg.get("sleep_ack_phrase", "Going quiet.") or "Going quiet.")
                self.play_local_voice_cue_async("sleep_ack", phrase, allow_main_tts_fallback=False)
                continue

            print(f"[audio] Voice command accepted: wake={matched_wake or ('already awake' if is_awake_waiting else '[none required]')}; command: {cleaned}")
            diagnostics = self.build_wake_diagnostics(
                stt_result, metrics, event_id=event_id, decision="voice_command_accepted",
                reason="validated", text=text, accepted=True,
            )
            metrics["wake_diagnostics"] = diagnostics
            self.log_wake_diagnostics(diagnostics)
            self.record_input_event("microphone", "voice_command", cleaned, True, "validated", event_id,
                                    {**metrics, "raw_text": text, "wake_word": matched_wake, "already_awake": is_awake_waiting})
            if bool(self.cfg.get("voice_command_immediate_cue_enabled", True)):
                self.acknowledge_voice_event("heard")
            self.set_voice_runtime(
                "processing",
                "Awake. Sending command to Brain App...",
                loop_active=True,
                last_heard=text,
                last_accepted=cleaned,
                last_wake_word=matched_wake,
                last_wake_at=now_iso() if matched_wake else self.voice_runtime.get("last_wake_at", ""),
                wake_match_source=wake_match_source or ("session" if is_awake_waiting else "none"),
                wake_match_score=round(float(wake_score or (1.0 if is_awake_waiting else 0.0)), 3),
                last_wake_diagnostics=diagnostics,
            )
            if matched_wake:
                self.emit_voice_observer_event("WakeDetected", event_id, stage="wake_word")
            self.emit_voice_observer_event("ListeningStarted", event_id, stage="microphone")
            self.emit_voice_observer_event("SpeechRecognised", event_id, stage="stt")
            self.web_log("user", f"voice: {cleaned}")
            # The thinking-feedback worker owns chirps and spoken progress cues.
            # Keeping this route single avoids two overlapping acknowledgements.
            with self.command_lock:
                result = self.handle_user_text(cleaned, source="robot_microphone", trigger="voice_command",
                                               event_id=event_id, input_metadata=metrics)
            if result.get("ok", False):
                hold_s = max(5.0, min(600.0, float(self.cfg.get("conversation_followup_window_s", 90.0))))
                awake_until = time.monotonic() + hold_s
                self.set_conversation_active_until(awake_until)
                if self.speech_output_active():
                    self.set_voice_runtime("speechgen", "Reply ready; building or playing the voice. Microphone muted.", loop_active=True)
                else:
                    self.set_voice_runtime("awake", f"Reply complete. Staying awake for follow-up for {hold_s:.0f}s.", loop_active=True)
                # Brief guard period so the wake listener is less likely to catch
                # the robot speaker tail as the next command. The stronger
                # speech_output_active() gate above will continue muting while
                # Dot.TTS audio is queued/playing.
                self.stop_event.wait(float(self.cfg.get("wake_after_reply_guard_s", 1.25)))
            else:
                err = str(result.get("error") or result)
                self.set_voice_runtime("error", f"Voice command failed: {err}", loop_active=True, last_error=err)

    def _idle_life_phrases(self) -> List[str]:
        raw = self.cfg.get("idle_life_phrases", DEFAULT_IDLE_CHATTER_PHRASES)
        if isinstance(raw, str):
            phrases = [p.strip() for p in raw.splitlines() if p.strip()]
        else:
            phrases = [str(p).strip() for p in raw if str(p).strip()]
        return phrases or list(DEFAULT_IDLE_CHATTER_PHRASES)

    def _idle_life_recent_comment_count(self, now_mono: Optional[float] = None) -> int:
        now_mono = time.monotonic() if now_mono is None else float(now_mono)
        cutoff = now_mono - 3600.0
        while self.idle_life_comment_times and float(self.idle_life_comment_times[0]) < cutoff:
            self.idle_life_comment_times.popleft()
        return len(self.idle_life_comment_times)

    def _idle_life_visual_permission(self) -> tuple[bool, str]:
        """Return whether an idle response is appropriate for the current scene."""
        if not bool(self.cfg.get("idle_life_require_alone", True)):
            return True, "presence check disabled"
        visual = self.get_visual_awareness_snapshot()
        if not bool(visual.get("opencv_available", False)):
            return True, "OpenCV unavailable; time-only idle fallback"
        if visual.get("person_present") is True:
            return False, "a person is visible"
        return True, "no person visible"

    def _idle_life_micro_action(self) -> Dict[str, Any]:
        """Small non-verbal alive behaviour: a glance and a gentle LED pulse."""
        if not bool(self.cfg.get("idle_life_micro_actions_enabled", True)):
            return {"ok": False, "skipped": "micro actions disabled"}
        try:
            yaw_max = abs(float(self.cfg.get("idle_life_head_yaw_deg", 8.0)))
            pitch_max = abs(float(self.cfg.get("idle_life_head_pitch_deg", 4.0)))
            yaw = random.uniform(-yaw_max, yaw_max)
            pitch = random.uniform(-pitch_max, pitch_max)
            self.expression_send_head(yaw, pitch, 0.0)
            eye_colour = str(self.cfg.get("idle_life_eye_colour", "blue") or "blue")
            brightness = max(0.0, min(1.0, float(self.cfg.get("idle_life_eye_brightness", 0.14) or 0.14)))
            self.expression_send_led_zone(str(self.cfg.get("expression_eye_left_zone", "left_eye") or "left_eye"), eye_colour, brightness)
            self.expression_send_led_zone(str(self.cfg.get("expression_eye_right_zone", "right_eye") or "right_eye"), eye_colour, brightness)
            evidence = {"yaw": round(yaw, 2), "pitch": round(pitch, 2)}
            self.web_log("idle", "idle micro action: glance/eye pulse", evidence)
            self.set_idle_life_runtime("micro_action", "glance/eye pulse")
            self.touch_robot_activity("idle_micro_action")
            return {"ok": True, **evidence}
        except Exception as exc:
            self.set_idle_life_runtime("error", last_error=str(exc))
            self.web_log("error", f"idle micro action failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def _idle_life_speak_phrase(self, phrase: str, cue_index: int = 1) -> Dict[str, Any]:
        phrase = str(phrase or "").strip()
        if not phrase:
            return {"ok": False, "error": "empty idle phrase"}
        cue_key = f"idle_chatter_{max(1, min(20, int(cue_index))):02d}"
        self.web_log("idle", f"idle chatter: {phrase}", {"cue_key": cue_key, "mode": "local"})
        self.set_idle_life_runtime("chatter", phrase)
        self.touch_robot_activity("idle_chatter")
        self.play_local_voice_cue_async(cue_key, phrase, allow_main_tts_fallback=True)
        return {"ok": True, "phrase": phrase, "mode": "local"}

    def handle_idle_brain_response(self, kind: str = "comment") -> Dict[str, Any]:
        """Ask the desktop Brain to author a short autonomous idle response.

        The body owns the timer and presence gate; the desktop Brain still owns
        personality, model selection, memory policy and the words that are spoken.
        """
        visual = self.get_visual_awareness_snapshot()
        user_idle_s = max(0.0, time.monotonic() - float(self.last_user_activity_mono or time.monotonic()))
        custom = str(self.cfg.get("idle_life_brain_prompt", "") or "").strip()
        if custom:
            prompt = custom
        elif kind == "curiosity":
            prompt = (
                "AUTONOMOUS IDLE CURIOSITY EVENT. Nobody has asked a question. "
                "Speak as BX1 in your configured personality. Give one brief, natural observation, "
                "small interesting thought, or useful curiosity. Keep it under two sentences. "
                "Do not claim the user said anything and do not finish with a generic help question."
            )
        else:
            prompt = (
                "AUTONOMOUS IDLE-LIFE EVENT. Nobody has spoken recently. "
                "Speak as BX1 in your configured personality with one short, context-aware idle remark. "
                "It may sound mildly bored, curious, observant or playful, but not needy or repetitive. "
                "Keep it under two sentences. Do not pretend the user asked a question and do not end with "
                "'How can I help?'."
            )
        prompt += (
            f"\nBody context: idle for {user_idle_s:.0f} seconds; visual state={visual.get('state')}; "
            f"person_present={visual.get('person_present')}; motion={visual.get('motion_detected')}."
        )
        state = self.read_body_state()
        self.web_log("idle", f"idle {kind} request sent to Brain App", {"prompt": prompt, "visual": visual})
        self.set_idle_life_runtime("thinking", f"asking Brain App for idle {kind}")
        t0 = time.perf_counter()
        try:
            idle_event_id = self.new_input_event_id(f"idle_{kind}")
            result = self.brain.chat(
                robot_id=self.robot_id,
                message=prompt,
                body_state=state,
                use_web=bool(kind == "curiosity" and self.cfg.get("idle_life_internet_curiosity_enabled", False)),
                use_memory=bool(self.cfg.get("use_memory", True)),
                robot_profile={},
                source="idle_life",
                trigger=f"idle_{kind}",
                event_id=idle_event_id,
                input_metadata={
                    "display_text": f"Idle-life {kind} phase",
                    "idle_seconds": round(user_idle_s, 1),
                    "visual_state": visual.get("state"),
                    "person_present": visual.get("person_present"),
                },
                return_audio=bool(self.cfg.get("brain_response_audio_enabled", True)),
            )
            self.record_performance_sample("chat", (time.perf_counter() - t0) * 1000.0)
        except Exception as exc:
            self.record_performance_sample(
                "chat",
                (time.perf_counter() - t0) * 1000.0,
                error="brain_chat_failed" if privacy_mode else str(exc),
            )
            self.web_log("error", f"idle Brain response failed: {exc}")
            self.set_idle_life_runtime("error", last_error=str(exc))
            return {"ok": False, "error": str(exc)}
        self.touch_robot_activity(f"idle_{kind}")
        if bool(result.get("idle_silent")):
            # Idle personality generation is intentionally allowed to remain
            # silent.  Do not surface a desktop/tool failure as robot speech.
            self.set_idle_life_runtime("waiting", "idle remark withheld", last_error="")
            return {"ok": True, "silent": True, "reason": "Brain withheld idle remark"}
        response = self.handle_brain_result(result, original_message=f"autonomous idle {kind}")
        if response.get("ok"):
            self.set_idle_life_runtime("chatter", str(response.get("reply", "") or f"idle {kind}"))
        return response

    def handle_idle_curiosity(self) -> Dict[str, Any]:
        return self.handle_idle_brain_response("curiosity")

    def _run_idle_comment(self, force: bool = False) -> Dict[str, Any]:
        mode = str(self.cfg.get("idle_life_response_mode", "brain") or "brain").strip().lower()
        if mode == "off":
            return {"ok": False, "skipped": "idle responses disabled"}
        allowed, reason = self._idle_life_visual_permission()
        if not force and not allowed:
            self.set_idle_life_runtime("waiting", f"idle speech held: {reason}")
            return {"ok": False, "skipped": reason}
        if mode == "local":
            phrases = self._idle_life_phrases()
            idx = random.randrange(len(phrases))
            return self._idle_life_speak_phrase(phrases[idx], idx + 1)
        return self.handle_idle_brain_response("comment")

    def idle_life_loop(self) -> None:
        print("[idle] Idle-life routine active.")
        self.set_idle_life_runtime("waiting", "Idle-life routine started")
        while not self.stop_event.is_set():
            if not bool(self.cfg.get("idle_life_enabled", True)):
                self.set_idle_life_runtime("disabled")
                self.stop_event.wait(5.0)
                continue

            now_mono = time.monotonic()
            user_idle_s = max(0.0, now_mono - float(self.last_user_activity_mono or now_mono))
            comments_this_hour = self._idle_life_recent_comment_count(now_mono)
            self.set_idle_life_runtime("waiting", comments_this_hour=comments_this_hour, sleeping=False, user_idle_s=round(user_idle_s, 1))

            # Do not interrupt a user session, a reply, a cue, a mic capture, or a Brain call.
            if now_mono < float(self.conversation_active_until or 0.0):
                self.stop_event.wait(3.0)
                continue
            if self.speech_output_active() or self.manual_audio_capture_requested.is_set():
                self.stop_event.wait(2.0)
                continue
            try:
                if self.command_lock.locked():
                    self.stop_event.wait(2.0)
                    continue
            except Exception:
                pass

            sleep_after = max(60.0, float(self.cfg.get("idle_life_sleep_after_s", 1800.0)))
            if user_idle_s >= sleep_after:
                self.set_idle_life_runtime("sleeping", "Idle sleep threshold reached", sleeping=True, comments_this_hour=comments_this_hour)
                self.stop_event.wait(10.0)
                continue

            micro_delay = max(10.0, float(self.cfg.get("idle_life_micro_action_delay_s", 60.0)))
            micro_interval = max(20.0, float(self.cfg.get("idle_life_micro_action_interval_s", 90.0)))
            if user_idle_s >= micro_delay and (now_mono - float(self.idle_life_last_micro_action_mono or 0.0)) >= micro_interval:
                self.idle_life_last_micro_action_mono = now_mono
                self._idle_life_micro_action()

            max_comments = max(0, int(float(self.cfg.get("idle_life_max_comments_per_hour", 3) or 3)))
            comment_delay = max(30.0, float(self.cfg.get("idle_life_comment_delay_s", 180.0)))
            comment_interval = max(60.0, float(self.cfg.get("idle_life_min_comment_interval_s", 600.0)))
            if (
                str(self.cfg.get("idle_life_response_mode", "brain") or "brain").lower() != "off"
                and max_comments > 0
                and user_idle_s >= comment_delay
                and comments_this_hour < max_comments
                and (now_mono - float(self.idle_life_last_comment_mono or 0.0)) >= comment_interval
            ):
                with self.command_lock:
                    result = self._run_idle_comment()
                if result.get("ok"):
                    self.idle_life_last_comment_mono = now_mono
                    self.idle_life_comment_times.append(now_mono)
                    self.stop_event.wait(3.0)
                    continue

            curiosity_delay = max(comment_delay, float(self.cfg.get("idle_life_curiosity_delay_s", 900.0)))
            curiosity_interval = max(300.0, float(self.cfg.get("idle_life_curiosity_interval_s", 1800.0)))
            if (
                bool(self.cfg.get("idle_life_internet_curiosity_enabled", False))
                and user_idle_s >= curiosity_delay
                and (now_mono - float(self.idle_life_last_curiosity_mono or 0.0)) >= curiosity_interval
            ):
                allowed, reason = self._idle_life_visual_permission()
                if allowed:
                    self.idle_life_last_curiosity_mono = now_mono
                    self.set_idle_life_runtime("curious", "asking Brain App for an idle curiosity", comments_this_hour=comments_this_hour)
                    with self.command_lock:
                        self.handle_idle_curiosity()
                    self.stop_event.wait(5.0)
                    continue
                self.set_idle_life_runtime("waiting", f"idle curiosity held: {reason}")

            self.stop_event.wait(5.0)

    def get_idle_life_settings(self) -> Dict[str, Any]:
        mode = str(self.cfg.get("idle_life_response_mode", "brain") or "brain").strip().lower()
        if mode not in {"brain", "local", "off"}:
            mode = "brain"
        return {
            "dialogue_owner": "desktop_brain_app",
            "trigger_owner": "robot_body_idle_timer",
            "enabled": bool(self.cfg.get("idle_life_enabled", True)),
            "micro_actions_enabled": bool(self.cfg.get("idle_life_micro_actions_enabled", True)),
            "response_mode": mode,
            "require_alone": bool(self.cfg.get("idle_life_require_alone", True)),
            "internet_curiosity_enabled": bool(self.cfg.get("idle_life_internet_curiosity_enabled", False)),
            "micro_action_delay_s": float(self.cfg.get("idle_life_micro_action_delay_s", 60.0)),
            "micro_action_interval_s": float(self.cfg.get("idle_life_micro_action_interval_s", 90.0)),
            "comment_delay_s": float(self.cfg.get("idle_life_comment_delay_s", 180.0)),
            "min_comment_interval_s": float(self.cfg.get("idle_life_min_comment_interval_s", 600.0)),
            "curiosity_delay_s": float(self.cfg.get("idle_life_curiosity_delay_s", 900.0)),
            "curiosity_interval_s": float(self.cfg.get("idle_life_curiosity_interval_s", 1800.0)),
            "sleep_after_s": float(self.cfg.get("idle_life_sleep_after_s", 1800.0)),
            "max_comments_per_hour": int(self.cfg.get("idle_life_max_comments_per_hour", 3)),
            "head_yaw_deg": float(self.cfg.get("idle_life_head_yaw_deg", 8.0)),
            "head_pitch_deg": float(self.cfg.get("idle_life_head_pitch_deg", 4.0)),
            "eye_colour": str(self.cfg.get("idle_life_eye_colour", "blue")),
            "eye_brightness": float(self.cfg.get("idle_life_eye_brightness", 0.14)),
            "phrases": self._idle_life_phrases(),
            "brain_prompt": str(self.cfg.get("idle_life_brain_prompt", "")),
            "runtime": self.get_idle_life_snapshot(),
        }

    def web_update_idle_life_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raw_phrases = data.get("phrases", self.cfg.get("idle_life_phrases", DEFAULT_IDLE_CHATTER_PHRASES))
        if isinstance(raw_phrases, str):
            phrases = [p.strip() for p in raw_phrases.splitlines() if p.strip()]
        else:
            phrases = [str(p).strip() for p in raw_phrases if str(p).strip()]
        mode = str(data.get("response_mode", self.cfg.get("idle_life_response_mode", "brain")) or "brain").strip().lower()
        if mode not in {"brain", "local", "off"}:
            mode = "brain"
        self.cfg["idle_life_enabled"] = bool(data.get("enabled", self.cfg.get("idle_life_enabled", True)))
        self.cfg["idle_life_micro_actions_enabled"] = bool(data.get("micro_actions_enabled", self.cfg.get("idle_life_micro_actions_enabled", True)))
        self.cfg["idle_life_response_mode"] = mode
        self.cfg["idle_life_require_alone"] = bool(data.get("require_alone", self.cfg.get("idle_life_require_alone", True)))
        self.cfg["idle_life_internet_curiosity_enabled"] = bool(data.get("internet_curiosity_enabled", self.cfg.get("idle_life_internet_curiosity_enabled", False)))
        self.cfg["idle_life_micro_action_delay_s"] = clamp_float_value(data.get("micro_action_delay_s", self.cfg.get("idle_life_micro_action_delay_s", 60.0)), 10.0, 3600.0, 60.0)
        self.cfg["idle_life_micro_action_interval_s"] = clamp_float_value(data.get("micro_action_interval_s", self.cfg.get("idle_life_micro_action_interval_s", 90.0)), 20.0, 7200.0, 90.0)
        self.cfg["idle_life_comment_delay_s"] = clamp_float_value(data.get("comment_delay_s", self.cfg.get("idle_life_comment_delay_s", 180.0)), 30.0, 7200.0, 180.0)
        self.cfg["idle_life_min_comment_interval_s"] = clamp_float_value(data.get("min_comment_interval_s", self.cfg.get("idle_life_min_comment_interval_s", 600.0)), 60.0, 7200.0, 600.0)
        self.cfg["idle_life_curiosity_delay_s"] = clamp_float_value(data.get("curiosity_delay_s", self.cfg.get("idle_life_curiosity_delay_s", 900.0)), 60.0, 10800.0, 900.0)
        self.cfg["idle_life_curiosity_interval_s"] = clamp_float_value(data.get("curiosity_interval_s", self.cfg.get("idle_life_curiosity_interval_s", 1800.0)), 300.0, 21600.0, 1800.0)
        self.cfg["idle_life_sleep_after_s"] = clamp_float_value(data.get("sleep_after_s", self.cfg.get("idle_life_sleep_after_s", 1800.0)), 60.0, 43200.0, 1800.0)
        self.cfg["idle_life_max_comments_per_hour"] = clamp_int_value(data.get("max_comments_per_hour", self.cfg.get("idle_life_max_comments_per_hour", 3)), 0, 12, 3)
        self.cfg["idle_life_head_yaw_deg"] = clamp_float_value(data.get("head_yaw_deg", self.cfg.get("idle_life_head_yaw_deg", 8.0)), 0.0, 30.0, 8.0)
        self.cfg["idle_life_head_pitch_deg"] = clamp_float_value(data.get("head_pitch_deg", self.cfg.get("idle_life_head_pitch_deg", 4.0)), 0.0, 20.0, 4.0)
        self.cfg["idle_life_eye_colour"] = str(data.get("eye_colour", self.cfg.get("idle_life_eye_colour", "blue")) or "blue").strip()
        self.cfg["idle_life_eye_brightness"] = clamp_float_value(data.get("eye_brightness", self.cfg.get("idle_life_eye_brightness", 0.14)), 0.0, 1.0, 0.14)
        self.cfg["idle_life_phrases"] = phrases or list(DEFAULT_IDLE_CHATTER_PHRASES)
        self.cfg["idle_life_brain_prompt"] = str(data.get("brain_prompt", self.cfg.get("idle_life_brain_prompt", "")) or "").strip()
        self.save_config_file()
        self.set_idle_life_runtime("waiting", "Idle-life settings saved")
        self.web_log("system", "Idle-life settings saved", {"response_mode": mode})
        return {"ok": True, "idle_life": self.get_idle_life_settings(), "saved_to": str(CONFIG_PATH)}

    def web_test_idle_life_phrase(self) -> Dict[str, Any]:
        with self.command_lock:
            result = self._run_idle_comment(force=True)
        result["idle_life"] = self.get_idle_life_settings()
        return result

    def web_test_idle_life_action(self) -> Dict[str, Any]:
        result = self._idle_life_micro_action()
        result["idle_life"] = self.get_idle_life_settings()
        return result

    def web_reset_idle_life_timer(self) -> Dict[str, Any]:
        self.touch_user_activity("idle_timer_reset")
        self.idle_life_last_comment_mono = 0.0
        self.idle_life_last_curiosity_mono = 0.0
        self.idle_life_sleep_announced = False
        self.set_idle_life_runtime("waiting", "Idle timer reset")
        return {"ok": True, "idle_life": self.get_idle_life_settings()}

    def cache_camera_frame(self, jpeg: bytes, source: str = "camera") -> None:
        if not jpeg:
            return
        with self.camera_frame_lock:
            self.latest_camera_jpeg = bytes(jpeg)
            self.latest_camera_frame_at = now_iso()
            self.latest_camera_frame_mono = time.monotonic()
            self.latest_camera_frame_source = str(source or "camera")

    def get_camera_snapshot_jpeg(self, max_age_s: Optional[float] = None) -> bytes:
        """Return the cached camera frame, or capture a new frame when requested.

        ``max_age_s <= 0`` is an explicit fresh-capture request from the web UI.
        Normal live preview requests reuse the awareness-loop cache to avoid competing
        camera processes and unnecessary USB camera restarts.
        """
        max_age = float(self.cfg.get("camera_preview_max_age_s", 4.0) if max_age_s is None else max_age_s)
        with self.camera_frame_lock:
            cached = bytes(self.latest_camera_jpeg)
            age = time.monotonic() - float(self.latest_camera_frame_mono or 0.0)
        if max_age > 0.0 and cached and age <= max_age:
            return cached
        jpeg = self.camera.capture_jpeg()
        self.cache_camera_frame(jpeg, "web_preview_fresh" if max_age <= 0.0 else "web_preview")
        return jpeg

    def get_visual_awareness_snapshot(self) -> Dict[str, Any]:
        with self.visual_awareness_lock:
            runtime = dict(self.visual_awareness_runtime)
        runtime.update({
            "enabled": bool(self.cfg.get("visual_awareness_enabled", True)),
            "camera_enabled": bool(self.cfg.get("camera_enabled", True)),
            "send_periodic_camera_frames": bool(self.cfg.get("send_periodic_camera_frames", True)),
            "periodic_camera_frame_interval_s": float(self.cfg.get("periodic_camera_frame_interval_s", 5.0)),
            "interval_s": float(self.cfg.get("visual_awareness_interval_s", 2.0)),
            "motion_threshold": float(self.cfg.get("visual_motion_threshold", 0.035)),
            "presence_hold_s": float(self.cfg.get("visual_presence_hold_s", 4.0)),
            "alone_timeout_s": float(self.cfg.get("visual_alone_timeout_s", 20.0)),
            "wake_on_person": bool(self.cfg.get("visual_wake_on_person", True)),
            "wake_window_s": float(self.cfg.get("visual_wake_window_s", 20.0)),
            "send_event_frames": bool(self.cfg.get("visual_send_event_frames", True)),
            "auto_camera_on_vision_request": bool(self.cfg.get("auto_camera_on_vision_request", True)),
            "camera_live_preview_enabled": bool(self.cfg.get("camera_live_preview_enabled", True)),
            "camera_live_preview_interval_s": float(self.cfg.get("camera_live_preview_interval_s", 2.0)),
            "latest_cached_frame_at": self.latest_camera_frame_at,
            "latest_cached_frame_source": self.latest_camera_frame_source,
            "identity_recognition_available": False,
            "identity_note": "Known-person identity requires face enrolment in the desktop Brain App.",
            "gesture_recognition_mode": "semantic Brain vision after an explicit request or selected event",
        })
        return runtime

    def set_visual_awareness_runtime(self, **updates: Any) -> None:
        with self.visual_awareness_lock:
            self.visual_awareness_runtime.update(updates)
            self.visual_awareness_runtime["updated_at"] = now_iso()

    def get_visual_awareness_settings(self) -> Dict[str, Any]:
        configured = normalise_text_list(self.cfg.get("vision_trigger_phrases", []))
        phrases = list(DEFAULT_VISION_TRIGGER_PHRASES)
        for phrase in configured:
            low = str(phrase).lower().strip()
            if low and low not in phrases:
                phrases.append(low)
        return {
            "camera_enabled": bool(self.cfg.get("camera_enabled", True)),
            "camera_device": str(self.cfg.get("camera_device", "/dev/video0")),
            "camera_index": int(self.cfg.get("camera_index", 0)),
            "jpeg_quality": int(self.cfg.get("jpeg_quality", 85)),
            "auto_camera_on_vision_request": bool(self.cfg.get("auto_camera_on_vision_request", True)),
            "vision_trigger_phrases": phrases,
            "send_periodic_camera_frames": bool(self.cfg.get("send_periodic_camera_frames", True)),
            "periodic_camera_frame_interval_s": float(self.cfg.get("periodic_camera_frame_interval_s", 5.0)),
            "visual_awareness_enabled": bool(self.cfg.get("visual_awareness_enabled", True)),
            "visual_awareness_interval_s": float(self.cfg.get("visual_awareness_interval_s", 2.0)),
            "visual_motion_threshold": float(self.cfg.get("visual_motion_threshold", 0.035)),
            "visual_presence_hold_s": float(self.cfg.get("visual_presence_hold_s", 4.0)),
            "visual_alone_timeout_s": float(self.cfg.get("visual_alone_timeout_s", 20.0)),
            "visual_wake_on_person": bool(self.cfg.get("visual_wake_on_person", True)),
            "visual_wake_window_s": float(self.cfg.get("visual_wake_window_s", 20.0)),
            "visual_send_event_frames": bool(self.cfg.get("visual_send_event_frames", True)),
            "camera_live_preview_enabled": bool(self.cfg.get("camera_live_preview_enabled", True)),
            "camera_live_preview_interval_s": float(self.cfg.get("camera_live_preview_interval_s", 2.0)),
            "runtime": self.get_visual_awareness_snapshot(),
        }

    def web_update_visual_awareness_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.cfg["camera_enabled"] = bool(data.get("camera_enabled", self.cfg.get("camera_enabled", True)))
        self.cfg["camera_device"] = str(data.get("camera_device", self.cfg.get("camera_device", "/dev/video0")) or "/dev/video0").strip()
        self.cfg["camera_index"] = clamp_int_value(data.get("camera_index", self.cfg.get("camera_index", 0)), 0, 20, 0)
        self.cfg["jpeg_quality"] = clamp_int_value(data.get("jpeg_quality", self.cfg.get("jpeg_quality", 85)), 20, 100, 85)
        self.cfg["auto_camera_on_vision_request"] = bool(data.get("auto_camera_on_vision_request", self.cfg.get("auto_camera_on_vision_request", True)))
        phrases = normalise_text_list(data.get("vision_trigger_phrases", self.cfg.get("vision_trigger_phrases", DEFAULT_VISION_TRIGGER_PHRASES)))
        self.cfg["vision_trigger_phrases"] = phrases or list(DEFAULT_VISION_TRIGGER_PHRASES)
        self.cfg["send_periodic_camera_frames"] = bool(data.get("send_periodic_camera_frames", self.cfg.get("send_periodic_camera_frames", True)))
        self.cfg["periodic_camera_frame_interval_s"] = clamp_float_value(data.get("periodic_camera_frame_interval_s", self.cfg.get("periodic_camera_frame_interval_s", 5.0)), 2.0, 120.0, 5.0)
        self.cfg["visual_awareness_enabled"] = bool(data.get("visual_awareness_enabled", self.cfg.get("visual_awareness_enabled", True)))
        self.cfg["visual_awareness_interval_s"] = clamp_float_value(data.get("visual_awareness_interval_s", self.cfg.get("visual_awareness_interval_s", 2.0)), 0.75, 30.0, 2.0)
        self.cfg["visual_motion_threshold"] = clamp_float_value(data.get("visual_motion_threshold", self.cfg.get("visual_motion_threshold", 0.035)), 0.005, 0.30, 0.035)
        self.cfg["visual_presence_hold_s"] = clamp_float_value(data.get("visual_presence_hold_s", self.cfg.get("visual_presence_hold_s", 4.0)), 1.0, 30.0, 4.0)
        self.cfg["visual_alone_timeout_s"] = clamp_float_value(data.get("visual_alone_timeout_s", self.cfg.get("visual_alone_timeout_s", 20.0)), 5.0, 600.0, 20.0)
        self.cfg["visual_wake_on_person"] = bool(data.get("visual_wake_on_person", self.cfg.get("visual_wake_on_person", True)))
        self.cfg["visual_wake_window_s"] = clamp_float_value(data.get("visual_wake_window_s", self.cfg.get("visual_wake_window_s", 20.0)), 5.0, 120.0, 20.0)
        self.cfg["visual_send_event_frames"] = bool(data.get("visual_send_event_frames", self.cfg.get("visual_send_event_frames", True)))
        self.cfg["camera_live_preview_enabled"] = bool(data.get("camera_live_preview_enabled", self.cfg.get("camera_live_preview_enabled", True)))
        self.cfg["camera_live_preview_interval_s"] = clamp_float_value(data.get("camera_live_preview_interval_s", self.cfg.get("camera_live_preview_interval_s", 2.0)), 1.0, 30.0, 2.0)
        self.camera = CameraCapture(CameraConfig(
            camera_index=int(self.cfg.get("camera_index", 0)),
            camera_device=str(self.cfg.get("camera_device", "/dev/video0")),
            jpeg_quality=int(self.cfg.get("jpeg_quality", 85)),
        ))
        self.save_config_file()
        self.web_log("system", "Vision and awareness settings saved")
        return {"ok": True, "vision_awareness": self.get_visual_awareness_settings(), "saved_to": str(CONFIG_PATH), "restart_note": "Background-loop enable/disable changes take full effect after service restart."}

    def visual_awareness_sample(self, send_frame: bool = False, source: str = "awareness") -> Dict[str, Any]:
        if not bool(self.cfg.get("camera_enabled", True)):
            self.set_visual_awareness_runtime(state="disabled", camera_ok=False, last_error="camera_enabled=false")
            return {"ok": False, "error": "camera_enabled=false"}
        try:
            jpeg, analysis = self.camera.capture_analysis_jpeg(
                motion_threshold=float(self.cfg.get("visual_motion_threshold", 0.035)),
                detect_faces=True,
                analysis_width=int(self.cfg.get("visual_analysis_width", 320)),
            )
            self.cache_camera_frame(jpeg, source)
            now_mono = time.monotonic()

            # A snapshot is not evidence that the robot is alone. Without OpenCV,
            # face and motion values are unknown and must remain unknown.
            if not bool(analysis.get("opencv_available", False)):
                update = dict(analysis)
                update.update({
                    "state": "snapshot_only",
                    "camera_ok": True,
                    "person_present": None,
                    "alone": None,
                    "last_frame_at": now_iso(),
                    "last_error": "",
                    "last_transition": "",
                })
                self.visual_previous_present = None
                self.set_visual_awareness_runtime(**update)
                brain_result: Dict[str, Any] = {}
                if send_frame and self.brain.base_url:
                    brain_result = self.brain.vision_frame(
                        robot_id=self.robot_id,
                        image_bytes=jpeg,
                        body_state=self.read_body_state(),
                        metadata={"captured_at": now_iso(), "source": str(source or "awareness"), "awareness": self.get_visual_awareness_snapshot()},
                        robot_profile={},
                    )
                    self.set_visual_awareness_runtime(last_frame_sent_at=now_iso())
                return {"ok": True, "analysis": self.get_visual_awareness_snapshot(), "frame_bytes": len(jpeg), "brain_frame": brain_result}

            raw_face_present = bool(analysis.get("person_present", False))
            if raw_face_present:
                self.visual_last_face_seen_mono = now_mono
            hold_s = max(1.0, float(self.cfg.get("visual_presence_hold_s", 4.0)))
            person_present = raw_face_present or bool(self.visual_last_face_seen_mono and (now_mono - self.visual_last_face_seen_mono) <= hold_s)
            alone_timeout = max(5.0, float(self.cfg.get("visual_alone_timeout_s", 20.0)))
            alone = bool(self.visual_last_face_seen_mono and (now_mono - self.visual_last_face_seen_mono) >= alone_timeout)
            previous = self.visual_previous_present
            transition = ""
            if person_present and previous is not True:
                transition = "person_entered"
            elif previous is True and not person_present:
                transition = "person_left"
            self.visual_previous_present = person_present

            update = dict(analysis)
            update.update({
                "state": "person_present" if person_present else ("alone" if alone else "watching"),
                "camera_ok": True,
                "person_present": person_present,
                "alone": alone,
                "last_frame_at": now_iso(),
                "last_error": "",
            })
            if raw_face_present:
                update["last_person_seen_at"] = now_iso()
            if bool(analysis.get("motion_detected")):
                update["last_motion_at"] = now_iso()
            if transition:
                update["last_transition"] = transition
            self.set_visual_awareness_runtime(**update)

            should_send = bool(send_frame) or bool(transition and self.cfg.get("visual_send_event_frames", True))
            brain_result: Dict[str, Any] = {}
            if should_send and self.brain.base_url:
                metadata = {
                    "captured_at": now_iso(),
                    "source": str(source or "awareness"),
                    "transition": transition,
                    "awareness": self.get_visual_awareness_snapshot(),
                }
                brain_result = self.brain.vision_frame(
                    robot_id=self.robot_id,
                    image_bytes=jpeg,
                    body_state=self.read_body_state(),
                    metadata=metadata,
                    robot_profile={},
                )
                self.set_visual_awareness_runtime(last_frame_sent_at=now_iso())

            if transition == "person_entered" and bool(self.cfg.get("visual_wake_on_person", True)):
                window = max(5.0, float(self.cfg.get("visual_wake_window_s", 20.0)))
                awake_until = time.monotonic() + window
                self.set_conversation_active_until(awake_until)
                self.set_voice_runtime("awake", f"Person detected. Listening for a command for {window:.0f}s.", loop_active=bool(self.get_voice_runtime_snapshot().get("loop_active", False)), last_visual_wake_at=now_iso())
                self.apply_led_state("awake", source="visual_person_entered", force=True)
                self.touch_robot_activity("person_detected")
                self.web_log("vision", "Person entered camera view; conversation window opened.", self.get_visual_awareness_snapshot())
            elif transition == "person_left":
                self.web_log("vision", "Person left camera view.", self.get_visual_awareness_snapshot())

            return {"ok": True, "analysis": self.get_visual_awareness_snapshot(), "frame_bytes": len(jpeg), "brain_frame": brain_result}
        except Exception as exc:
            self.set_visual_awareness_runtime(state="error", camera_ok=False, last_error=str(exc))
            self.web_log("error", f"visual awareness failed: {exc}")
            return {"ok": False, "error": str(exc), "analysis": self.get_visual_awareness_snapshot()}

    def visual_awareness_loop(self) -> None:
        print("[vision] Lightweight face/motion awareness active.")
        while not self.stop_event.is_set():
            if not bool(self.cfg.get("visual_awareness_enabled", True)):
                self.set_visual_awareness_runtime(state="disabled")
                self.stop_event.wait(3.0)
                continue
            self.visual_awareness_sample(send_frame=False, source="background_awareness")
            self.stop_event.wait(max(0.75, float(self.cfg.get("visual_awareness_interval_s", 2.0))))

    def web_camera_probe(self) -> Dict[str, Any]:
        report = self.camera.probe()
        self.set_visual_awareness_runtime(camera_ok=bool(report.get("ok")), last_error=str(report.get("error", "")), state="ready" if report.get("ok") else "error")
        self.web_log("vision" if report.get("ok") else "error", "Camera probe completed.", report)
        return {"ok": bool(report.get("ok")), "probe": report, "vision_awareness": self.get_visual_awareness_snapshot()}

    def web_camera_frame(self) -> Dict[str, Any]:
        return self.visual_awareness_sample(send_frame=True, source="web_camera_frame")

    def web_camera_vision(self, prompt: str) -> Dict[str, Any]:
        text = str(prompt or "Describe what you can see and mention any person, object, movement or clear gesture.").strip()
        return self.handle_vision(text, source="body_web", trigger="web_camera_vision")

    def periodic_vision_loop(self) -> None:
        interval = float(self.cfg.get("periodic_vision_interval_s", 30))
        prompt = str(self.cfg.get("periodic_vision_prompt", "Describe what you can see."))
        while not self.stop_event.is_set():
            self.stop_event.wait(interval)
            if self.stop_event.is_set():
                break
            self.handle_vision(prompt)

    def periodic_camera_frame_loop(self) -> None:
        interval = float(self.cfg.get("periodic_camera_frame_interval_s", 5.0))
        while not self.stop_event.is_set():
            self.stop_event.wait(interval)
            if self.stop_event.is_set():
                break
            self.handle_camera_frame()

    def handle_camera_frame(self) -> Dict[str, Any]:
        """Send camera data to the Brain App without forcing an expensive LLM vision pass."""
        if not bool(self.cfg.get("camera_enabled", True)):
            msg = "camera_enabled=false"
            print(f"[camera] {msg}")
            self.web_log("error", f"camera frame skipped: {msg}")
            return {"ok": False, "error": msg}
        state = self.read_body_state()
        try:
            image_bytes = self.camera.capture_jpeg()
            self.cache_camera_frame(image_bytes, "periodic_brain_frame")
            metadata = {
                "camera": str(self.cfg.get("camera_device", "/dev/video0")),
                "camera_index": int(self.cfg.get("camera_index", 0)),
                "jpeg_quality": int(self.cfg.get("jpeg_quality", 85)),
                "captured_at": now_iso(),
                "awareness": self.get_visual_awareness_snapshot(),
            }
            result = self.brain.vision_frame(
                robot_id=self.robot_id,
                image_bytes=image_bytes,
                body_state=state,
                metadata=metadata,
                robot_profile={},
            )
            self.last_camera_frame_sent_at = now_iso()
            self.web_log("system", f"camera frame sent: {len(image_bytes)} bytes")
            if not self.console_quiet:
                print(f"[camera] frame sent: {len(image_bytes)} bytes -> {result}")
            return {"ok": True, "bytes": len(image_bytes), "result": result}
        except Exception as exc:
            print(f"[camera] frame send failed: {exc}")
            self.web_log("error", f"camera frame failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def is_vision_request(self, text: str) -> bool:
        raw = str(text or "").lower().strip()
        # Normalise the Vosk output so "what's", "what s" and punctuation variants
        # are treated the same.  Voice STT often drops apostrophes or small words.
        low = re.sub(r"[^a-z0-9 ]+", " ", raw)
        low = re.sub(r"\s+", " ", low).strip()
        configured = normalise_text_list(self.cfg.get("vision_trigger_phrases", []))
        phrases = list(DEFAULT_VISION_TRIGGER_PHRASES)
        for phrase in configured:
            plow = re.sub(r"[^a-z0-9 ]+", " ", str(phrase).lower()).strip()
            plow = re.sub(r"\s+", " ", plow)
            if plow and plow not in phrases:
                phrases.append(plow)
        normalised_phrases = [re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", p.lower())).strip() for p in phrases]
        if any(phrase and phrase in low for phrase in normalised_phrases):
            return True

        # More natural spoken requests often do not mention the word "camera":
        # "BX1, what am I holding in my hand?" should still trigger the eyes.
        question_words = ("what", "which", "identify", "recognise", "recognize", "tell me", "do you know")
        hand_object_words = ("holding", "hold", "hand", "hands", "showing", "show", "this", "that", "object", "thing", "item")
        if any(w in low for w in question_words) and any(w in low for w in hand_object_words):
            if any(w in low for w in ("holding", "hand", "hands", "showing", "object", "thing", "this", "that", "item")):
                return True

        camera_words = ("camera", "webcam", "look", "see", "watch", "vision", "photo", "picture", "eyes")
        object_words = ("object", "thing", "this", "that", "holding", "hand", "hands", "in front", "on the desk", "showing")
        return any(w in low for w in camera_words) and any(w in low for w in object_words)

    def remember_last_reply(self, reply: str, source: str = "brain") -> None:
        reply = str(reply or "").strip()
        if not reply:
            return
        self.last_reply_text = reply
        self.last_reply_at = now_iso()
        self.last_reply_source = str(source or "brain")
        self.recent_robot_speech.append((time.monotonic(), reply))

    def is_repeat_last_request(self, text: str) -> bool:
        low = re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()
        low = re.sub(r"\s+", " ", low)
        exact = {
            "repeat", "repeat that", "repeat it", "repeat last", "repeat last response",
            "repeat your last response", "repeat the last answer", "repeat the last reply",
            "say that again", "say it again", "what did you say", "can you repeat that",
            "can you say that again", "please repeat that",
        }
        if low in exact:
            return True
        return ("repeat" in low or "say" in low) and ("again" in low or "last" in low or "that" in low or "response" in low or "reply" in low)

    def repeat_last_response(self) -> Dict[str, Any]:
        reply = str(getattr(self, "last_reply_text", "") or "").strip()
        if not reply:
            msg = "I do not have a previous response to repeat yet."
            return self._local_reply(msg, kind="system")
        print(f"[voice] repeating last response from {self.last_reply_at or 'this session'}")
        self.web_log("system", "Repeating last response.", {"last_reply_at": self.last_reply_at, "source": self.last_reply_source})
        try:
            self.apply_expression_for_reply(reply, original_message="repeat last response", ai_expr=None)
        except Exception:
            pass
        try:
            self.tts.speak(reply, flush=True, tag="repeat")
        except Exception as exc:
            self.web_log("error", f"repeat TTS failed: {exc}")
            return {"ok": False, "error": str(exc), "reply": reply}
        return {"ok": True, "reply": reply, "repeated": True, "last_reply_at": self.last_reply_at, "source": self.last_reply_source}

    def _local_reply(self, reply: str, kind: str = "bx1") -> Dict[str, Any]:
        reply = str(reply or "").strip()
        if not reply:
            return {"ok": False, "error": "empty local reply"}
        print(f"\n{self.robot_name} says:\n{textwrap.fill(reply, width=90)}")
        self.web_log(kind, reply)
        self.remember_last_reply(reply, source=kind)
        try:
            self.tts.speak(reply, flush=True, tag="local")
        except Exception as exc:
            self.web_log("error", f"local TTS failed: {exc}")
        return {"ok": True, "reply": reply, "actions": [], "ack": {"actions_seen": 0}, "local": True}

    def handle_personality_command(self, text: str) -> Optional[Dict[str, Any]]:
        # Personality commands belong to the desktop Brain App. The Arduino body
        # should not change robot name, character or prompt state.
        return None

    def emit_voice_observer_event(self, event: str, session_id: str, **metadata: Any) -> None:
        """Best-effort metadata-only event delivery to local BX1 OS; never blocks voice."""
        endpoint = str(self.cfg.get("voice_observer_url", "") or "").strip()
        if not endpoint or not session_id:
            return
        try:
            parsed = urlparse(endpoint)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 8089 or parsed.path != "/api/voice/events":
                return
            payload = {"event": event, "session_id": str(session_id)[:96], "timestamp": time.time(), "source": "robot_body"}
            for key in ("reason", "stage", "transport", "duration_ms", "latency_ms"):
                if key in metadata:
                    value = metadata[key]
                    payload[key] = value if isinstance(value, (bool, int, float)) else str(value)[:240]
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(endpoint, data=body, method="POST", headers={"Content-Type": "application/json"})
            def deliver() -> None:
                try:
                    with urllib.request.urlopen(request, timeout=1.0) as response:
                        response.read(512)
                except Exception:
                    pass
            threading.Thread(target=deliver, name="bx1-voice-observer", daemon=True).start()
        except Exception:
            return

    def handle_user_text(self, text: str, use_web: Optional[bool] = None, use_memory: Optional[bool] = None,
                         allow_vision: Optional[bool] = None, source: str = "robot_body", trigger: str = "manual",
                         event_id: str = "", input_metadata: Optional[Dict[str, Any]] = None,
                         allow_actions: bool = True, privacy_mode: bool = False) -> Dict[str, Any]:
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "empty text"}
        self.touch_user_activity("user_text")
        if not event_id and not privacy_mode:
            event_id = self.record_input_event(source, trigger, text, True, "accepted", metadata=input_metadata)
        if not privacy_mode and self.is_repeat_last_request(text):
            return self.repeat_last_response()
        brain_owns_policy = bool(self.cfg.get("brain_controls_web_memory", True))
        web_allowed: Optional[bool] = None if (brain_owns_policy and use_web is None) else bool(self.cfg.get("use_web_for_robot_questions", False) if use_web is None else use_web)
        memory_allowed: Optional[bool] = None if (brain_owns_policy and use_memory is None) else bool(self.cfg.get("use_memory", True) if use_memory is None else use_memory)
        vision_allowed = bool(self.cfg.get("auto_camera_on_vision_request", True) if allow_vision is None else allow_vision)
        local_personality = None if privacy_mode else self.handle_personality_command(text)
        if local_personality is not None:
            return local_personality
        if vision_allowed and self.is_vision_request(text) and bool(self.cfg.get("camera_enabled", True)):
            return self.handle_vision(
                text,
                use_web=web_allowed,
                source=source,
                trigger="vision_from_" + str(trigger or "manual"),
                event_id=event_id,
                input_metadata=input_metadata or {},
            )
        state = self.read_body_state()
        if not privacy_mode:
            print(f"\nJohn: {text}")
            self.web_log("user", text)
        # Keyboard, web and microphone commands should all drive the same visible
        # robot state.  Previously only the microphone path updated the state
        # LEDs, making keyboard use feel much less interactive.
        self.command_processing.set()
        self.set_voice_runtime(
            "processing",
            "Sending command to Brain App...",
            loop_active=bool(self.get_voice_runtime_snapshot().get("loop_active", False)),
            last_accepted="" if privacy_mode else text,
        )
        if not privacy_mode:
            print("[brain] waiting for reply...")
        thinking_stop = self.start_thinking_cues("chat") if allow_actions else threading.Event()
        self.emit_voice_observer_event("BrainRequestSent", event_id, stage="chat")
        self.emit_voice_observer_event("ThinkingStarted", event_id, stage="llm")
        t0 = time.perf_counter()
        with self.metrics_lock:
            self.performance["last_chat_started_at"] = now_iso()
            self.performance["last_user_message_chars"] = len(text)
        watchdog_stop = threading.Event()
        def request_watchdog() -> None:
            delay = max(5.0, float(self.cfg.get("brain_request_watchdog_s", 50.0) or 50.0))
            if watchdog_stop.wait(delay):
                return
            self.set_voice_runtime("processing", f"Brain request still pending after {delay:.0f}s.", loop_active=True, last_error="")
            metadata = {"event_id": event_id}
            if not privacy_mode:
                metadata["message"] = text[:160]
            self.web_log("warning", f"Brain chat request exceeded {delay:.0f}s", metadata)
        threading.Thread(target=request_watchdog, name="bx1-brain-watchdog", daemon=True).start()
        try:
            result = self.brain.chat(
                robot_id=self.robot_id,
                message=text,
                body_state=state,
                use_web=web_allowed,
                use_memory=memory_allowed,
                robot_profile={},
                source=source,
                trigger=trigger,
                event_id=event_id,
                input_metadata=input_metadata or {},
                return_audio=bool(self.cfg.get("brain_response_audio_enabled", True)),
            )
            self.record_performance_sample("chat", (time.perf_counter() - t0) * 1000.0)
        except Exception as exc:
            self.record_performance_sample("chat", (time.perf_counter() - t0) * 1000.0, error=str(exc))
            if not privacy_mode:
                print(f"[brain] chat failed: {exc}")
                self.web_log("error", f"chat failed: {exc}")
            self.set_voice_runtime(
                "error",
                "Brain request failed." if privacy_mode else f"Brain request failed: {exc}",
                last_error="brain_chat_failed" if privacy_mode else str(exc),
            )
            self.emit_voice_observer_event("FaultRaised", event_id, reason="brain_chat_failed")
            thinking_stop.set()
            self.command_processing.clear()
            return {"ok": False, "error": "brain_chat_failed" if privacy_mode else str(exc)}
        finally:
            watchdog_stop.set()
            # Do not stop the feedback worker merely because the LLM returned.
            # Dot.TTS generation is usually the longest part of the pipeline.
            # It is stopped when physical reply playback actually begins.
            with self.metrics_lock:
                self.performance["last_chat_finished_at"] = now_iso()
        try:
            return self.handle_brain_result(
                result,
                original_message=text,
                thinking_stop=thinking_stop,
                session_id=event_id,
                allow_actions=allow_actions,
                privacy_mode=privacy_mode,
            )
        finally:
            # TTS has been queued before handle_brain_result returns. The wake
            # listener now hands protection over to speech_output_active().
            self.command_processing.clear()

    def handle_vision(self, prompt: str, use_web: Optional[bool] = None,
                      source: str = "robot_body", trigger: str = "vision_request",
                      event_id: str = "", input_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = self.read_body_state()
        self.web_log("user", f"/vision {prompt}")
        self.apply_led_state("vision", source="vision", force=True)
        thinking_stop = self.start_thinking_cues("vision")
        t0 = time.perf_counter()
        try:
            image_bytes = self.camera.capture_jpeg()
            self.cache_camera_frame(image_bytes, "explicit_vision")
            result = self.brain.vision(
                robot_id=self.robot_id,
                prompt=prompt,
                image_bytes=image_bytes,
                body_state=state,
                use_web=(None if bool(self.cfg.get("brain_controls_web_memory", True)) and use_web is None else bool(self.cfg.get("use_web_for_robot_questions", False) if use_web is None else use_web)),
                robot_profile={},
                source=source,
                trigger=trigger,
                event_id=event_id,
                input_metadata=input_metadata or {},
                return_audio=bool(self.cfg.get("brain_response_audio_enabled", True)),
            )
            self.record_performance_sample("vision", (time.perf_counter() - t0) * 1000.0)
        except Exception as exc:
            self.record_performance_sample("vision", (time.perf_counter() - t0) * 1000.0, error=str(exc))
            error = str(exc)
            hint = ""
            low_error = error.lower()
            if "400" in low_error and ("ollama" in low_error or "/api/chat" in low_error):
                hint = (
                    "The desktop Brain App rejected the image request at Ollama. Its active chat model appears not to accept images. "
                    "Select a vision-capable Ollama model for the Brain vision route, for example qwen2.5vl:7b, then retry."
                )
            visible = error + ((" | Hint: " + hint) if hint else "")
            print(f"[vision] failed: {visible}")
            self.web_log("error", f"vision failed: {visible}", {"error": error, "hint": hint})
            return {"ok": False, "error": error, "hint": hint}
        finally:
            # Keep progress cues alive through Dot.TTS generation. They stop
            # at actual reply playback, or immediately on an error/no-reply path.
            self.apply_led_state("awake", source="vision_complete", include_mouth=False, force=True)
        return self.handle_brain_result(result, original_message=prompt, thinking_stop=thinking_stop)

    def handle_brain_result(self, result: Dict[str, Any], original_message: str,
                            thinking_stop: Optional[threading.Event] = None,
                            session_id: str = "", allow_actions: bool = True,
                            privacy_mode: bool = False) -> Dict[str, Any]:
        if not result.get("ok", False):
            err = str(result.get("error") or result.get("detail") or result.get("message") or "brain returned error")
            hint = str(result.get("hint") or "")
            visible = (err + ((" | Hint: " + hint) if hint else "")).strip()
            if not privacy_mode:
                print(f"[brain] error: {visible}")
                self.web_log("error", f"brain returned error: {visible}", result)
            self.set_voice_runtime("error", "Brain returned an error." if privacy_mode else f"Brain returned an error: {visible}", last_error="brain_response_invalid" if privacy_mode else visible)
            self.emit_voice_observer_event("FaultRaised", session_id, reason="brain_response_invalid")
            if thinking_stop is not None:
                thinking_stop.set()
            self.stop_active_thinking_cues("brain_error")
            return {"ok": False, "error": "brain_response_invalid" if privacy_mode else visible, "raw": {} if privacy_mode else result}

        live_tool = result.get("live_tool") if isinstance(result.get("live_tool"), dict) else {}
        if live_tool and not privacy_mode and str(live_tool.get("route") or "") != "idle_local":
            route = str(live_tool.get("route") or "none")
            query = str(live_tool.get("query") or "")
            verified = bool(live_tool.get("verified"))
            sources = [str(item) for item in (live_tool.get("sources") or []) if str(item).strip()]
            try:
                result_count = int(live_tool.get("result_count") or 0)
            except Exception:
                result_count = 0
            with self.metrics_lock:
                self.performance.update({"last_live_tool_route": route, "last_live_tool_verified": verified, "last_live_tool_query": query, "last_live_tool_sources": sources, "last_live_tool_result_count": result_count})
            status = "verified" if verified else "failed"
            source_text = ", ".join(sources) if sources else "no named source"
            self.web_log("system" if verified else "warning", f"Live tool {route}: {status}; {result_count} result(s); {source_text}", live_tool)

        reply = str(result.get("speech") or result.get("reply") or "").strip()
        if not reply:
            if thinking_stop is not None:
                thinking_stop.set()
            self.stop_active_thinking_cues("no_spoken_reply")
            self.set_voice_runtime("idle", "Brain returned no spoken reply.")
            if privacy_mode:
                self.emit_voice_observer_event("FaultRaised", session_id, reason="brain_reply_missing")
                return {"ok": False, "error": "brain_reply_missing", "raw": {}}
        else:
            if not privacy_mode:
                self.remember_last_reply(reply, source="brain")
                width = max(70, min(110, shutil.get_terminal_size((100, 24)).columns - 8))
                wrapped = textwrap.fill(reply, width=width, subsequent_indent="    ")
                print("\n" + "-" * 72)
                print(f"{self.robot_name} says:\n{wrapped}")
                print("-" * 72)
                self.web_log("bx1", reply)
            with self.metrics_lock:
                self.performance["last_reply_chars"] = len(reply)

            ai_expr = result.get("expression") if isinstance(result.get("expression"), dict) else None
            if allow_actions:
                self.apply_expression_for_reply(reply, original_message=original_message, ai_expr=ai_expr)
            nested_audio = result.get("audio") if isinstance(result.get("audio"), dict) else {}
            brain_audio_present = bool(result.get("audio_url") or nested_audio.get("audio_url") or nested_audio.get("relative_audio_url"))
            audio_already_played_on_robot = bool(result.get("audio_played_on_robot") or result.get("played_on_body"))
            if audio_already_played_on_robot:
                if privacy_mode:
                    self.emit_voice_observer_event("FaultRaised", session_id, reason="brain_audio_not_body_owned")
                    return {"ok": False, "error": "brain_audio_not_body_owned", "raw": {}}
                if thinking_stop is not None:
                    thinking_stop.set()
                self.stop_active_thinking_cues("remote_playback_confirmed")
                self.web_log("system", "body TTS skipped because the response explicitly confirms robot-side playback")
                self.start_estimated_remote_speech_animation(reply)
            elif brain_audio_present:
                if thinking_stop is not None:
                    thinking_stop.set()
                self.stop_active_thinking_cues("brain_audio_ready")
                self.set_voice_runtime("processing", "Reply audio ready; downloading from the Brain API...", loop_active=bool(self.get_voice_runtime_snapshot().get("loop_active", False)), thinking_phase="audio_download")
                played = self.play_brain_response_audio(result, reply, session_id=session_id, fallback_on_failure=allow_actions, privacy_mode=privacy_mode)
                if played:
                    if not privacy_mode:
                        self.web_log("system", "Playing the Brain-published Dot.TTS reply on the robot speaker.")
                else:
                    if not privacy_mode:
                        self.web_log("warning", "Brain reply audio could not be downloaded.")
                    self.emit_voice_observer_event("FaultRaised", session_id, reason="brain_tts_download_failed")
                    if privacy_mode:
                        return {"ok": False, "error": "brain_tts_download_failed", "raw": {}}
                    if allow_actions:
                        self.tts.speak(reply, flush=True, tag="reply_fallback")
            else:
                if thinking_stop is not None:
                    thinking_stop.set()
                self.stop_active_thinking_cues("reply_without_audio")
                if not privacy_mode:
                    self.web_log("warning", "Brain returned text without audio; using the local speech fallback.")
                self.emit_voice_observer_event("FaultRaised", session_id, reason="brain_tts_missing")
                if privacy_mode:
                    return {"ok": False, "error": "brain_tts_missing", "raw": {}}
                if allow_actions:
                    self.tts.speak(reply, flush=True, tag="reply_fallback")

        actions = result.get("actions") or []
        ack = self.execute_actions(actions, original_message=original_message) if allow_actions else {"actions_seen": 0, "blocked": "voice_vertical_slice"}
        if ack["actions_seen"]:
            try:
                self.brain.command_ack(ack)
            except Exception as exc:
                print(f"[brain] command ack failed: {exc}")
                self.web_log("error", f"command ack failed: {exc}")
        return {"ok": True, "reply": "" if privacy_mode else reply, "actions": [] if privacy_mode else actions, "ack": ack, "raw": {} if privacy_mode else result}

    def play_brain_response_audio(self, result: Dict[str, Any], reply: str, *, session_id: str = "", fallback_on_failure: bool = True, privacy_mode: bool = False) -> bool:
        """Download one API reply file, then play it asynchronously with mouth events."""
        download_started = time.perf_counter()
        try:
            filename = self.brain.download_response_audio(result)
        except Exception as exc:
            if not privacy_mode:
                self.web_log("error", f"Brain reply audio download failed: {exc}")
            return False
        nested = result.get("audio") if isinstance(result.get("audio"), dict) else {}
        timing = {
            "service_generation_s": nested.get("elapsed_sec"),
            "download_s": round(time.perf_counter() - download_started, 3),
            "total_generation_download_s": round(
                float(nested.get("elapsed_sec") or 0.0) + (time.perf_counter() - download_started),
                3,
            ),
            "transport": str(nested.get("transport") or "brain_api_proxy"),
        }

        def worker() -> None:
            playback_started_at = [0.0]

            def playback_started() -> None:
                playback_started_at[0] = time.perf_counter()
                self.emit_voice_observer_event("SpeechStarted", session_id, transport="brain_api_audio")

            playback = self.tts.play_response_audio_file(
                filename,
                "" if privacy_mode else reply,
                tag="dottts_reply",
                delete_after=True,
                timing=timing,
                emit_mouth_events=not privacy_mode,
                on_playback_started=playback_started,
            )
            if not playback.get("ok"):
                if not privacy_mode:
                    self.web_log("error", f"Brain reply audio playback failed: {playback}")
                self.emit_voice_observer_event("FaultRaised", session_id, reason="body_playback_failed")
                if fallback_on_failure:
                    self.tts.speak(reply, flush=True, tag="reply_fallback")
            else:
                duration_ms = round(max(0.0, time.perf_counter() - playback_started_at[0]) * 1000, 2) if playback_started_at[0] else None
                self.emit_voice_observer_event("SpeechFinished", session_id, transport="brain_api_audio", duration_ms=duration_ms)

        threading.Thread(target=worker, name="bx1-brain-reply-audio", daemon=True).start()
        return True

    def start_estimated_remote_speech_animation(self, text: str) -> None:
        """Animate the mouth/state LEDs when remote playback supplies no callbacks."""
        duration = self.expression_estimated_duration(text)

        def worker() -> None:
            before = self.get_voice_runtime_snapshot()
            loop_active = bool(before.get("loop_active", False))
            previous = str(before.get("state", "idle"))
            try:
                self.set_voice_runtime("speaking", "BX1 is speaking...", loop_active=loop_active, pre_speech_state=previous)
                self.apply_led_state("speaking", source="remote_audio", include_mouth=False, force=True)
                self.start_mouth_audio_animation({"text": text, "tag": "remote_audio", "backend": "brain_remote"})
                self.stop_event.wait(max(0.5, min(15.0, float(duration))))
            finally:
                self.stop_mouth_audio_animation()
                restore = "awake" if previous == "awake" else ("listening" if loop_active else "idle")
                label = "Conversation active; listening for follow-up." if restore == "awake" else ("Listening for Hello, Hey or Robot." if restore == "listening" else "Ready.")
                self.set_voice_runtime(restore, label, loop_active=loop_active)
                self.apply_led_state(restore, source="remote_audio_complete", include_mouth=False, force=True)

        threading.Thread(target=worker, name="bx1-remote-speech-led", daemon=True).start()

    def execute_actions(self, actions: List[Dict[str, Any]], original_message: str) -> Dict[str, Any]:
        ack_items = []
        for action in actions:
            validated = self.validate_action(action)
            if not validated["ok"]:
                ack_items.append(validated)
                continue
            if bool(action.get("dry_run", False)):
                validated.update({"executed": False, "skipped": True, "reason": "Brain App returned dry_run=true."})
                ack_items.append(validated)
                continue
            res = self.hardware.send_action(action)
            validated.update({
                "executed": bool(res.ok),
                "bridge_ok": bool(res.ok),
                "bridge_value": res.value,
                "bridge_error": res.error,
            })
            ack_items.append(validated)
        return {
            "robot_id": self.robot_id,
            "actions_seen": len(actions),
            "items": ack_items,
            "original_message": original_message,
            "timestamp": now_iso(),
        }

    def validate_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        action_type = str(action.get("type", ""))
        args = action.get("args") or {}
        ack = {"action_id": action.get("id"), "type": action_type, "ok": False, "executed": False}
        state = self.latest_state or self.read_body_state()
        safety_ok = bool(state.get("safety_ok", True)) and not bool(state.get("fallen", False))

        if action_type == "drive":
            if not bool(self.cfg.get("motor_armed", False)):
                ack.update({"skipped": True, "reason": "motor_armed=false in UNO Q config.json."})
                return ack
            if not safety_ok:
                ack.update({"skipped": True, "reason": "body safety state blocks drive action."})
                return ack
            speed = float(args.get("linear_mps", 0.0) or 0.0)
            duration = float(args.get("duration_s", 0.0) or 0.0)
            if abs(speed) > float(self.cfg.get("max_drive_speed_mps", 0.25)) + 1e-6:
                ack.update({"skipped": True, "reason": "drive speed exceeds UNO Q limit."})
                return ack
            if duration > float(self.cfg.get("max_drive_duration_s", 1.5)) + 1e-6:
                ack.update({"skipped": True, "reason": "drive duration exceeds UNO Q limit."})
                return ack

        if action_type == "set_head_pose" and not bool(self.cfg.get("allow_head_servo", True)):
            ack.update({"skipped": True, "reason": "head servo disabled in UNO Q config.json."})
            return ack

        if action_type in {"set_eye_led", "set_led", "set_device_led", "set_led_zone", "set_led_range", "set_led_pixel", "paint_led"} and not bool(self.cfg.get("allow_leds", True)):
            ack.update({"skipped": True, "reason": "LED output disabled in UNO Q config.json."})
            return ack

        if action_type in {"configure_hardware", "configure_hardware_v2"}:
            # Only allow explicit local/web configuration packets. This prevents
            # the LLM from casually rewriting GPIO assignments during conversation.
            source = str(action.get("source", ""))
            if source not in {"web_hardware_settings", "local_config"}:
                ack.update({"skipped": True, "reason": "configure_hardware is only accepted from the local web hardware settings page."})
                return ack

        if action_type not in {"stop_motion", "drive", "drive_wheels", "set_head_pose", "set_eye_led", "set_led", "set_device_led", "set_led_zone", "set_led_range", "set_led_pixel", "paint_led", "play_tone", "configure_hardware", "configure_hardware_v2"}:
            ack.update({"skipped": True, "reason": "unsupported action type."})
            return ack

        ack["ok"] = True
        return ack

    def record_performance_sample(self, name: str, ms: float, error: str = "") -> None:
        ms = round(float(ms), 1)
        with self.metrics_lock:
            count_key = f"{name}_count"
            last_key = f"last_{name}_ms"
            avg_key = f"avg_{name}_ms"
            count = int(self.performance.get(count_key, 0) or 0) + 1
            old_avg = self.performance.get(avg_key)
            if old_avg is None:
                avg = ms
            else:
                avg = ((float(old_avg) * (count - 1)) + ms) / count
            self.performance[count_key] = count
            self.performance[last_key] = ms
            self.performance[avg_key] = round(avg, 1)
            if error:
                self.performance["last_error"] = str(error)[:300]

    def get_wake_words(self) -> List[str]:
        words = [str(w).strip().lower() for w in self.cfg.get("wake_words", ["hello", "hey", "robot"]) if str(w).strip()]
        return words or ["hello", "hey", "robot"]

    def _load_local_cue_manifest(self) -> Dict[str, Any]:
        try:
            if LOCAL_CUE_MANIFEST.exists():
                data = json.loads(LOCAL_CUE_MANIFEST.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {"schema": "bx1.local_voice_cues.v1", "generated_at": "", "cues": {}}

    def _save_local_cue_manifest(self, manifest: Dict[str, Any]) -> None:
        LOCAL_CUE_DIR.mkdir(parents=True, exist_ok=True)
        LOCAL_CUE_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def get_local_voice_cue_texts(self) -> Dict[str, str]:
        cues: Dict[str, str] = dict(DEFAULT_LOCAL_VOICE_CUES)
        wake_ack = str(self.cfg.get("wake_ack_phrase", cues.get("wake_ack", "Yes John?")) or "Yes John?").strip()
        if wake_ack:
            cues["wake_ack"] = wake_ack
        wake_variants = self.cfg.get("wake_ack_phrases", [])
        if isinstance(wake_variants, str):
            wake_variants = [line.strip() for line in wake_variants.replace(",", "\n").splitlines() if line.strip()]
        if isinstance(wake_variants, list):
            for idx, value in enumerate((str(item).strip() for item in wake_variants if str(item).strip()), start=1):
                cues["wake_ack" if idx == 1 else f"wake_ack_{idx:02d}"] = value
        sleep_ack = str(self.cfg.get("sleep_ack_phrase", cues.get("sleep_ack", "Going quiet.")) or "Going quiet.").strip()
        if sleep_ack:
            cues["sleep_ack"] = sleep_ack
        # Use the configured thinking cues as the voice-cache source so the
        # Dot.TTS filler phrases match the current robot personality.
        for idx, cue in enumerate(self.get_thinking_cues()[:20], start=1):
            cues[f"thinking_{idx:02d}"] = cue
        for idx, cue in enumerate(self._idle_life_phrases()[:20], start=1):
            cues[f"idle_chatter_{idx:02d}"] = cue
        extra = self.cfg.get("local_voice_cues", {})
        if isinstance(extra, dict):
            for key, text in extra.items():
                k = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(key).strip().lower()).strip("_")
                v = str(text or "").strip()
                if k and v:
                    cues[k] = v
        return cues

    def local_voice_cue_status(self) -> Dict[str, Any]:
        manifest = self._load_local_cue_manifest()
        cue_items = manifest.get("cues", {}) if isinstance(manifest.get("cues"), dict) else {}
        files = []
        for key, item in cue_items.items():
            if not isinstance(item, dict):
                continue
            path = LOCAL_CUE_DIR / Path(str(item.get("filename", ""))).name
            files.append({
                "key": key,
                "text": str(item.get("text", "")),
                "filename": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "generated_at": str(item.get("generated_at", "")),
            })
        return {
            "ok": True,
            "enabled": bool(self.cfg.get("local_voice_cue_cache_enabled", True)),
            "cache_dir": str(LOCAL_CUE_DIR),
            "manifest": str(LOCAL_CUE_MANIFEST),
            "generated_at": str(manifest.get("generated_at", "")),
            "count": sum(1 for f in files if f.get("exists")),
            "expected_count": len(self.get_local_voice_cue_texts()),
            "files": files,
        }

    def _cached_voice_cue_path(self, cue_key: str) -> Optional[Path]:
        if not bool(self.cfg.get("local_voice_cue_cache_enabled", True)):
            return None
        manifest = self._load_local_cue_manifest()
        cues = manifest.get("cues", {}) if isinstance(manifest.get("cues"), dict) else {}
        item = cues.get(cue_key) if isinstance(cues, dict) else None
        if not isinstance(item, dict):
            return None
        path = LOCAL_CUE_DIR / Path(str(item.get("filename", ""))).name
        if path.exists() and path.is_file():
            return path
        return None

    def play_local_voice_cue(self, cue_key: str, fallback_text: str = "", allow_main_tts_fallback: bool = False) -> bool:
        text = fallback_text or self.get_local_voice_cue_texts().get(cue_key, "")
        path = self._cached_voice_cue_path(cue_key)
        if path is not None:
            with self.local_cue_lock:
                self.local_cue_playing.set()
                self.guard_stt_capture(self.estimate_speech_guard_s(text, 1.2), "local_voice_cue")
                self.web_log("thinking" if cue_key.startswith("thinking") else "voice", f"local cue: {text}", {"cue_key": cue_key, "filename": str(path)})
                try:
                    report = self.play_body_audio_file(
                        path, device=str(self.cfg.get("tts_playback_device", "default")),
                        text=text, tag="local-cue", backend="local-cue",
                    )
                    if not report.get("ok"):
                        self.web_log("error", f"local cue playback failed: {report.get('error') or report}", report)
                        return False
                    return True
                finally:
                    self.local_cue_playing.clear()
        if allow_main_tts_fallback and text:
            self.guard_stt_capture(self.estimate_speech_guard_s(text, 1.2), "main_tts_cue_fallback")
            self.tts.speak(text, flush=False, tag="local-cue-fallback")
            return True
        if bool(self.cfg.get("local_cue_fallback_espeak_enabled", True)) and text:
            # Emergency only: instant feedback is more important than voice quality
            # when the Dot.TTS cue cache has not been generated yet.
            try:
                cfg = self.build_audio_config()
                cfg.tts_backend = "espeak-ng"
                cfg.tts_fallback_to_espeak = True
                tmp_tts = TextToSpeech(cfg)
                tmp_tts.set_mouth_event_handler(self.handle_mouth_audio_event)
                self.guard_stt_capture(self.estimate_speech_guard_s(text, 1.2), "espeak_cue_fallback")
                tmp_tts.speak(text, flush=True, tag="local-cue-espeak")
                return True
            except Exception:
                return False
        return False

    def play_local_voice_cue_async(self, cue_key: str, fallback_text: str = "", allow_main_tts_fallback: bool = False) -> None:
        threading.Thread(
            target=lambda: self.play_local_voice_cue(cue_key, fallback_text, allow_main_tts_fallback),
            name=f"bx1-local-cue-{cue_key}",
            daemon=True,
        ).start()

    def web_regenerate_local_voice_cues(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = data or {}
        try:
            self.resolve_brain_tts_base_url(update_config=True)
            self.tts.update_config(self.build_audio_config())
        except Exception as exc:
            return {"ok": False, "error": "Brain voice URL could not be derived from the Brain App URL: " + str(exc)}
        LOCAL_CUE_DIR.mkdir(parents=True, exist_ok=True)
        all_cues = self.get_local_voice_cue_texts()
        selected_raw = data.get("keys") or []
        selected = [str(x).strip() for x in selected_raw if str(x).strip()] if isinstance(selected_raw, list) else []
        cue_map = {k: v for k, v in all_cues.items() if (not selected or k in selected)}
        max_items = max(1, min(50, int(float(data.get("max_items", len(cue_map)) or len(cue_map)))))
        cue_map = dict(list(cue_map.items())[:max_items])
        manifest = {
            "schema": "bx1.local_voice_cues.v1",
            "generated_at": now_iso(),
            "voice": str(self.cfg.get("brain_tts_voice", "active_profile")),
            "engine": str(self.cfg.get("brain_tts_engine", "dottts")),
            "cues": {},
        }
        results: List[Dict[str, Any]] = []
        old_tts_cfg = self.tts.cfg
        self.tts.update_config(self.build_audio_config())
        try:
            for key, text in cue_map.items():
                safe_key = re.sub(r"[^a-zA-Z0-9_\-]+", "_", key).strip("_") or "cue"
                try:
                    report = self.tts._request_brain_tts_audio(text)  # type: ignore[attr-defined]
                    item: Dict[str, Any] = {"key": safe_key, "text": text, "ok": bool(report.get("ok")), "elapsed": report.get("elapsed_sec")}
                    if report.get("ok") and report.get("filename"):
                        src = Path(str(report.get("filename")))
                        suffix = src.suffix.lower() or ".wav"
                        dst = LOCAL_CUE_DIR / f"{safe_key}{suffix}"
                        shutil.copyfile(src, dst)
                        item.update({"filename": dst.name, "size_bytes": dst.stat().st_size})
                        manifest["cues"][safe_key] = {
                            "text": text,
                            "filename": dst.name,
                            "generated_at": now_iso(),
                            "size_bytes": dst.stat().st_size,
                        }
                    else:
                        item["error"] = str(report.get("error") or report)[:600]
                    results.append(item)
                    self.web_log("system" if item.get("ok") else "error", f"voice cue {safe_key}: {'ok' if item.get('ok') else item.get('error')}")
                except Exception as exc:
                    results.append({"key": key, "text": text, "ok": False, "error": str(exc)[:600]})
        finally:
            self.tts.update_config(old_tts_cfg)
        # Preserve old valid cue files if a regeneration item failed.
        old_manifest = self._load_local_cue_manifest()
        old_cues = old_manifest.get("cues", {}) if isinstance(old_manifest.get("cues"), dict) else {}
        for key in all_cues:
            if key not in manifest["cues"] and isinstance(old_cues, dict) and key in old_cues:
                manifest["cues"][key] = old_cues[key]
        self._save_local_cue_manifest(manifest)
        ok_count = sum(1 for item in results if item.get("ok"))
        return {"ok": ok_count > 0, "generated": ok_count, "requested": len(results), "results": results, "status": self.local_voice_cue_status()}

    def register_active_thinking_cues(self, stop: threading.Event) -> None:
        """Remember the current progress-cue worker until real reply audio begins."""
        with self.active_thinking_lock:
            previous = self.active_thinking_stop
            if previous is not None and previous is not stop:
                previous.set()
            self.active_thinking_stop = stop
            self.active_thinking_started_mono = time.monotonic()

    def stop_active_thinking_cues(self, reason: str = "") -> None:
        with self.active_thinking_lock:
            stop = self.active_thinking_stop
            self.active_thinking_stop = None
            self.active_thinking_started_mono = 0.0
        if stop is not None:
            stop.set()
            if reason:
                self.web_log("thinking", f"progress cues stopped: {reason}")

    def start_thinking_cues(self, reason: str = "chat") -> threading.Event:
        """Give immediate, then progressively richer feedback while Brain works.

        Phase 1 is the short non-verbal chirp the operator already likes.  If the
        request is still pending, phase 2 speaks a short locally rendered phrase
        such as "Let me check that."  A later phase can speak one more phrase for
        genuinely slow web, weather or vision requests.  The worker stops as soon
        as the synchronous Brain request returns.
        """
        stop = threading.Event()
        nonverbal_enabled = bool(self.cfg.get("thinking_feedback_enabled", True))
        spoken_enabled = bool(self.cfg.get("thinking_cues_enabled", True)) and bool(
            self.cfg.get("thinking_cue_speak", True)
        )
        if not nonverbal_enabled and not spoken_enabled:
            return stop

        def set_phase(phase: str, cue: str = "") -> None:
            self.set_voice_runtime(
                "processing",
                cue or "Thinking…",
                loop_active=True,
                thinking_phase=phase,
                last_thinking_cue=cue,
            )

        def speak_cue(index: int) -> None:
            # Use a stable sequence rather than random repetition. The first cue
            # is deliberately conversational; later cues reassure the user that
            # BX1 has not stalled while Dot.TTS renders the final voice.
            cues = self.get_thinking_cues()
            cue = cues[index % len(cues)] if cues else "One moment."
            cue_key = ""
            for key, cue_text in self.get_local_voice_cue_texts().items():
                if str(cue_text).strip() == cue:
                    cue_key = key
                    break
            if not cue_key:
                cue_key = f"thinking_{(index % 20) + 1:02d}"
            set_phase("spoken", cue)
            self.web_log("thinking", cue, {"reason": reason, "phase": index + 1})
            self.play_local_voice_cue(
                cue_key,
                cue,
                allow_main_tts_fallback=bool(self.cfg.get("thinking_cue_use_main_tts_when_uncached", False)),
            )

        def worker() -> None:
            started = time.monotonic()
            try:
                chirp_delay = max(0.05, float(self.cfg.get("thinking_feedback_delay_s", 0.18)))
                spoken_delay = max(chirp_delay + 0.20, float(self.cfg.get("thinking_cue_delay_s", 1.1)))
                spoken_repeat = max(3.0, float(self.cfg.get("thinking_cue_repeat_s", 8.0)))
                max_spoken = max(0, min(8, int(self.cfg.get("thinking_cue_max_per_reply", 5)))) if spoken_enabled else 0
                total_timeout = max(10.0, min(120.0, float(self.cfg.get("thinking_cue_total_timeout_s", 65.0))))

                if stop.wait(chirp_delay):
                    return
                self.apply_led_state("thinking", source=f"thinking_feedback_{reason}", force=True)
                set_phase("chirp")
                if nonverbal_enabled:
                    self.web_log("thinking", "thinking progress tone", {"reason": reason, "phase": 1})
                    self.play_voice_feedback("thinking", blocking=False)

                remaining = max(0.0, spoken_delay - chirp_delay)
                if max_spoken <= 0 or stop.wait(remaining):
                    return
                for index in range(max_spoken):
                    if stop.is_set() or (time.monotonic() - started) >= total_timeout:
                        return
                    speak_cue(index)
                    if index >= max_spoken - 1 or stop.wait(spoken_repeat):
                        return
            except Exception as exc:
                self.web_log("error", f"thinking feedback failed: {exc}")

        self.register_active_thinking_cues(stop)
        threading.Thread(target=worker, name="bx1-thinking-feedback", daemon=True).start()
        return stop

    def get_thinking_cues(self) -> List[str]:
        cues = self.cfg.get("thinking_cues", [])
        if isinstance(cues, str):
            cues = [line.strip() for line in cues.replace(",", "\n").splitlines() if line.strip()]
        clean = [str(c).strip() for c in cues if str(c).strip()]
        return clean or ["Hmm.", "Let me think.", "One moment.", "Processing that.", "I am checking."]

    def play_one_thinking_cue(self) -> Dict[str, Any]:
        cue = random.choice(self.get_thinking_cues())
        cue_key = ""
        for key, text in self.get_local_voice_cue_texts().items():
            if str(text).strip() == cue:
                cue_key = key
                break
        cue_key = cue_key or "thinking_01"
        self.web_log("thinking", cue, {"manual_test": True, "cue_key": cue_key})
        spoken = False
        if bool(self.cfg.get("thinking_cue_speak", True)):
            spoken = self.play_local_voice_cue(cue_key, cue, allow_main_tts_fallback=bool(self.cfg.get("thinking_cue_use_main_tts_when_uncached", False)))
        return {"ok": True, "cue": cue, "cue_key": cue_key, "spoken": spoken, "local_voice_cues": self.local_voice_cue_status()}

    def web_log(self, kind: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.web_events.append({
            "timestamp": now_iso(),
            "kind": kind,
            "message": str(message),
            "data": data or {},
        })

    def normalise_brain_base_url(self, value: str) -> str:
        """Accept either a full URL or a bare IP/hostname and return a clean Brain API base URL."""
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Brain App URL/IP cannot be empty. Open Brain Connection and use 'Use This Browser PC'.")

        if "://" not in raw:
            raw = "http://" + raw

        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Brain App URL must start with http:// or https://")
        if not parsed.hostname:
            raise ValueError("Brain App URL must include an IP address or hostname.")

        # If John types only an IP/host, default to the Brain App robot API port.
        port = parsed.port or 8765
        host = parsed.hostname
        return f"{parsed.scheme}://{host}:{port}"

    def normalise_brain_tts_base_url(self, value: str) -> str:
        """Return the shared Brain API URL used by compatibility TTS requests."""
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Brain voice URL/IP cannot be empty.")
        if "://" not in raw:
            raw = "http://" + raw
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Brain voice URL must start with http:// or https://")
        if not parsed.hostname:
            raise ValueError("Brain voice URL must include an IP address or hostname.")
        port = parsed.port or 8765
        return f"{parsed.scheme}://{parsed.hostname}:{port}"

    def make_same_host_url(self, base_url: str, port: int) -> str:
        """Reuse the host/scheme from one Brain URL with another port."""
        raw = str(base_url or "").strip()
        if "://" not in raw:
            raw = "http://" + raw
        parsed = urlparse(raw)
        if not parsed.hostname:
            raise ValueError("Cannot derive host from Brain URL.")
        scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "http"
        return f"{scheme}://{parsed.hostname}:{int(port)}"

    def _is_placeholder_url(self, value: str) -> bool:
        raw = str(value or "").strip().lower()
        return (not raw) or "your_pc" in raw or "<brain_pc" in raw or "<pc" in raw or raw in {"http://", "https://"}

    def derive_brain_tts_base_url(self, port: int = 8765) -> str:
        """Derive the compatibility TTS URL from the saved Brain API URL."""
        brain_url = str(self.cfg.get("brain_base_url", getattr(self.brain, "base_url", "")) or "").strip()
        if self._is_placeholder_url(brain_url):
            return ""
        try:
            return self.normalise_brain_tts_base_url(self.make_same_host_url(brain_url, int(port)))
        except Exception:
            return ""

    def resolve_brain_tts_base_url(self, update_config: bool = True) -> str:
        """Return the active Brain voice URL, deriving it from Brain App URL by default."""
        follow_brain_host = bool(self.cfg.get("brain_tts_follow_brain_host", True))
        current = str(self.cfg.get("brain_tts_base_url", "") or "").strip()
        if follow_brain_host or self._is_placeholder_url(current):
            derived = self.derive_brain_tts_base_url(8765)
            if derived:
                if update_config:
                    self.cfg["brain_tts_base_url"] = derived
                    self.cfg["brain_tts_follow_brain_host"] = True
                return derived
            if not self._is_placeholder_url(current):
                try:
                    return self.normalise_brain_tts_base_url(current)
                except Exception:
                    pass
            return ""
        try:
            clean = self.normalise_brain_tts_base_url(current)
            if update_config and clean != current:
                self.cfg["brain_tts_base_url"] = clean
            return clean
        except Exception:
            derived = self.derive_brain_tts_base_url(8765)
            if derived:
                if update_config:
                    self.cfg["brain_tts_base_url"] = derived
                    self.cfg["brain_tts_follow_brain_host"] = True
                return derived
            return ""

    def sync_brain_tts_to_brain_host(self, save: bool = False) -> Dict[str, Any]:
        """Point the compatibility TTS route at the shared Brain API."""
        url = self.derive_brain_tts_base_url(8765)
        if not url:
            return {"ok": False, "error": "Brain App URL is not configured yet. Open Brain Connection and save/test the Brain PC URL first.", "brain_tts_base_url": "", "audio": self.get_audio_settings()}
        self.cfg["brain_tts_base_url"] = url
        self.cfg["brain_tts_follow_brain_host"] = True
        self.cfg["brain_tts_engine"] = "dottts"
        self.cfg["brain_tts_voice"] = "active_profile"
        self.cfg["brain_tts_endpoint"] = "/api/tts"
        self.cfg["brain_tts_status_endpoint"] = "/api/tts/status"
        self.sync_voice_profile_from_audio_config()
        self.tts.update_config(self.build_audio_config())
        if save:
            self.save_robot_profile_file()
            self.save_config_file()
        return {"ok": True, "brain_tts_base_url": url, "audio": self.get_audio_settings()}

    def save_config_file(self) -> None:
        """Persist the current runtime config back to python/config.json."""
        previous = CONFIG_PATH.stat() if CONFIG_PATH.exists() else None
        tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(self.cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if previous is not None:
            os.chmod(tmp_path, previous.st_mode & 0o777)
            try:
                if hasattr(os, "chown"):
                    os.chown(tmp_path, previous.st_uid, previous.st_gid)
            except PermissionError:
                # The normal service account already owns the machine-local file.
                pass
        tmp_path.replace(CONFIG_PATH)

    def save_robot_profile_file(self) -> None:
        # Deprecated: do not persist robot name/personality on the Arduino body.
        # Kept as a compatibility no-op for older web/API flows.
        return

    def apply_robot_profile_to_config(self, save: bool = False) -> None:
        profile = normalise_robot_profile(self.robot_profile, self.cfg)
        self.robot_profile = profile
        self.robot_id = str(profile.get("body_id", profile.get("robot_id", "UNO_Q_BODY"))).strip() or "UNO_Q_BODY"
        self.robot_name = "Robot Body"
        self.cfg["robot_id"] = self.robot_id
        self.cfg["brain_owns_identity"] = True
        # Wake words are local STT routing only now. They do not define the
        # robot's character or Brain identity.
        self.cfg["wake_words"] = list(profile.get("wake_words", self.cfg.get("wake_words", ["hello", "hey", "robot"])))
        ui = dict(profile.get("ui") or {})
        self.cfg["ui_theme"] = str(ui.get("theme", self.cfg.get("ui_theme", "dark-blue")))
        voice = dict(profile.get("voice_profile") or {})
        if voice.get("playback_device"):
            self.cfg["tts_playback_device"] = str(voice.get("playback_device"))
        if str(voice.get("engine", "")).lower() in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}:
            self.cfg["tts_backend"] = "edge-tts"
        if voice.get("brain_tts_base_url"):
            self.cfg["brain_tts_base_url"] = str(voice.get("brain_tts_base_url"))
        if voice.get("voice") and str(voice.get("engine", "")).lower() in {"brain-tts", "brain_tts"}:
            self.cfg["brain_tts_voice"] = str(voice.get("voice"))
        if voice.get("fallback_voice_allowed") is not None:
            self.cfg["tts_fallback_to_espeak"] = bool(voice.get("fallback_voice_allowed"))
        if save:
            self.save_config_file()

    def sync_voice_profile_from_audio_config(self) -> None:
        voice = dict(self.robot_profile.get("voice_profile") or {})
        voice["engine"] = str(self.cfg.get("tts_backend", voice.get("engine", "edge-tts")))
        backend = str(self.cfg.get("tts_backend", "edge-tts"))
        if backend == "edge-tts":
            voice["voice"] = str(self.cfg.get("tts_edge_voice", "en-GB-SoniaNeural"))
        elif backend == "elevenlabs":
            voice["voice"] = str(self.cfg.get("tts_elevenlabs_voice_id", ""))
        elif backend == "piper":
            voice["voice"] = str(self.cfg.get("tts_piper_model", ""))
        else:
            voice["voice"] = str(self.cfg.get("tts_voice", "en-gb"))
        voice["playback_device"] = str(self.cfg.get("tts_playback_device", "default"))
        voice["fallback_voice_allowed"] = bool(self.cfg.get("tts_fallback_to_espeak", False))
        self.robot_profile["voice_profile"] = voice

    def get_robot_profile_payload(self) -> Dict[str, Any]:
        profile = normalise_robot_profile(self.robot_profile, self.cfg)
        # Name/personality deliberately excluded. The Brain instance owns those.
        return {
            "schema_version": 2,
            "body_id": self.robot_id,
            "robot_id": self.robot_id,
            "brain_owns_identity": True,
            "wake_words": list(self.cfg.get("wake_words", profile.get("wake_words", []))),
            "capabilities": dict(profile.get("capabilities") or {}),
            "physical_description": dict(profile.get("physical_description") or {}),
            "ui": dict(profile.get("ui") or {}),
            "hardware_map": self.get_hardware_settings()["hardware_map"] if hasattr(self, "hardware_map") else {},
        }

    def get_theme_settings(self) -> Dict[str, Any]:
        themes = [
            {"id": "dark-blue", "label": "Dark Blue / BX1"},
            {"id": "graphite", "label": "Graphite"},
            {"id": "green", "label": "Workshop Green"},
            {"id": "amber", "label": "Amber Console"},
            {"id": "purple", "label": "Purple Lab"},
            {"id": "light", "label": "Light"},
        ]
        current = str(self.cfg.get("ui_theme", "dark-blue"))
        if current not in {t["id"] for t in themes}:
            current = "dark-blue"
        return {"ui_theme": current, "themes": themes}

    def web_update_theme_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        valid = {t["id"] for t in self.get_theme_settings()["themes"]}
        theme = str(data.get("ui_theme", self.cfg.get("ui_theme", "dark-blue"))).strip() or "dark-blue"
        if theme not in valid:
            theme = "dark-blue"
        self.cfg["ui_theme"] = theme
        ui = dict(self.robot_profile.get("ui") or {})
        ui["theme"] = theme
        self.robot_profile["ui"] = ui
        self.save_robot_profile_file()
        self.save_config_file()
        self.web_log("system", f"UI theme saved: {theme}")
        return {"ok": True, "theme": self.get_theme_settings(), "saved_to": str(CONFIG_PATH)}

    def apply_brain_connection(self, base_url: str, api_key: Optional[str] = None, save: bool = True) -> Dict[str, Any]:
        clean_url = self.normalise_brain_base_url(base_url)
        clean_key = str(self.cfg.get("api_key", "") if api_key is None else api_key)

        self.cfg["brain_base_url"] = clean_url
        self.cfg["api_key"] = clean_key
        self.brain.base_url = clean_url.rstrip("/")
        self.brain.cfg.base_url = clean_url.rstrip("/")
        self.brain.cfg.api_key = clean_key

        if save:
            self.save_config_file()

        self.web_log("system", f"Brain App URL saved: {clean_url}")
        return self.get_brain_settings()

    def get_brain_settings(self) -> Dict[str, Any]:
        try:
            active_tts_url = self.resolve_brain_tts_base_url(update_config=False)
        except Exception:
            active_tts_url = str(self.cfg.get("brain_tts_base_url", ""))
        return {
            "base_url": str(self.cfg.get("brain_base_url", self.brain.base_url)),
            "brain_tts_base_url": active_tts_url,
            "api_key_set": bool(str(self.cfg.get("api_key", "")).strip()),
            "chat_timeout_s": int(self.cfg.get("chat_timeout_s", 180)),
            "vision_timeout_s": int(self.cfg.get("vision_timeout_s", 180)),
            "command_ack_timeout_s": int(self.cfg.get("command_ack_timeout_s", 10)),
            "portable_hint": "If you move network, open this page from the Brain PC and press Use This Browser PC.",
        }

    def get_control_ownership(self) -> Dict[str, Any]:
        """Describe the hard boundary between the desktop Brain and robot body.

        The web console uses this contract to avoid presenting duplicate controls.
        Compatibility endpoints remain available for older tools, but the normal UI
        only edits body-owned settings.
        """
        return {
            "schema": "bx1.control_ownership.v1",
            "brain_app": [
                "robot name and personality",
                "LLM/model selection and prompts",
                "memory and internet policy",
                "TTS engine, voice model and emotion",
                "thinking cue wording and timing",
                "autonomous spoken idle dialogue",
                "semantic vision reasoning",
            ],
            "body_client": [
                "microphone device, gain and DSP",
                "speech endpointing and acceptance gates",
                "local wake words and conversation session",
                "speaker output device and volume",
                "camera capture hardware",
                "MCU bridge, GPIO and hardware registry",
                "servo limits, trim and safety enforcement",
                "LED zones, state indication and mouth audio envelope",
            ],
            "shared_contract": [
                "Brain sends reply, expression and bounded action packets",
                "Body returns telemetry, provenance and command acknowledgements",
                "Body may use explicit local camera phrases as a capture routing fallback",
            ],
            "flags": {
                "brain_controls_web_memory": bool(self.cfg.get("brain_controls_web_memory", True)),
                "brain_controls_tts_voice": bool(self.cfg.get("brain_tts_use_brain_defaults", True)),
                "brain_controls_thinking_cues": bool(self.cfg.get("brain_controls_thinking_cues", True)),
                "brain_controls_idle_dialogue": bool(self.cfg.get("brain_controls_idle_dialogue", True)),
            },
        }

    def get_audio_settings(self) -> Dict[str, Any]:
        try:
            active_tts_url = self.resolve_brain_tts_base_url(update_config=False)
        except Exception:
            active_tts_url = str(self.cfg.get("brain_tts_base_url", ""))
        return {
            "tts_enabled": bool(self.cfg.get("tts_enabled", True)),
            "tts_backend": str(self.cfg.get("tts_backend", "espeak-ng")),
            "tts_voice": str(self.cfg.get("tts_voice", "en-gb")),
            "tts_rate": int(self.cfg.get("tts_rate", 155)),
            "tts_pitch": int(self.cfg.get("tts_pitch", 35)),
            "tts_volume": int(self.cfg.get("tts_volume", 80)),
            "tts_playback_device": str(self.cfg.get("tts_playback_device", "default")),
            "brain_tts_base_url": active_tts_url,
            "brain_tts_derived_from_brain_url": bool(self.cfg.get("brain_tts_follow_brain_host", True)) or self._is_placeholder_url(str(self.cfg.get("brain_tts_base_url", "") or "")),
            "brain_tts_follow_brain_host": bool(self.cfg.get("brain_tts_follow_brain_host", True)),
            "brain_tts_engine": str(self.cfg.get("brain_tts_engine", "dottts")),
            "brain_tts_voice": str(self.cfg.get("brain_tts_voice", "active_profile")),
            "brain_tts_use_brain_defaults": bool(self.cfg.get("brain_tts_use_brain_defaults", True)),
            "voice_owner": "desktop_brain_app" if bool(self.cfg.get("brain_tts_use_brain_defaults", True)) else "body_compatibility_override",
            "brain_tts_format": str(self.cfg.get("brain_tts_format", "wav")),
            "brain_tts_timeout_s": int(self.cfg.get("brain_tts_timeout_s", 240)),
            "brain_tts_endpoint": str(self.cfg.get("brain_tts_endpoint", "/api/tts")),
            "brain_tts_status_endpoint": str(self.cfg.get("brain_tts_status_endpoint", "/api/tts/status")),
            "brain_response_audio_enabled": bool(self.cfg.get("brain_response_audio_enabled", True)),
            "tts_command": str(self.cfg.get("tts_command", "espeak-ng -ven-gb -s 155 -p 35")),
            "tts_piper_model": str(self.cfg.get("tts_piper_model", "models/piper/en_GB-alan-medium.onnx")),
            "tts_piper_config": str(self.cfg.get("tts_piper_config", "")),
            "tts_edge_voice": str(self.cfg.get("tts_edge_voice", "en-GB-SoniaNeural")),
            "tts_queue_enabled": bool(self.cfg.get("tts_queue_enabled", True)),
            "tts_chunking_enabled": bool(self.cfg.get("tts_chunking_enabled", True)),
            "tts_chunk_max_chars": int(self.cfg.get("tts_chunk_max_chars", 650)),
            "tts_fallback_to_espeak": bool(self.cfg.get("tts_fallback_to_espeak", False)),
        }

    def apply_audio_settings(self, data: Dict[str, Any], save: bool = True) -> Dict[str, Any]:
        def clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
            try:
                return max(lo, min(hi, int(float(value))))
            except Exception:
                return default

        # The desktop Brain App owns reply-voice generation. The local backend
        # handles short acknowledgements and emergency text-only fallback.
        backend = str(data.get("tts_backend", self.cfg.get("tts_backend", "edge-tts")) or "edge-tts")
        if backend.strip().lower() in {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}:
            backend = "edge-tts"
        self.cfg["brain_tts_use_brain_defaults"] = True

        self.cfg["tts_enabled"] = bool(data.get("tts_enabled", self.cfg.get("tts_enabled", True)))
        self.cfg["tts_backend"] = backend
        # Legacy local voice/rate/pitch values are retained for emergency fallback
        # but ignored when the Brain-owned voice route is active.
        self.cfg.setdefault("tts_voice", "en-gb")
        self.cfg.setdefault("tts_rate", 155)
        self.cfg.setdefault("tts_pitch", 35)
        self.cfg["tts_volume"] = clamp_int(data.get("tts_volume", self.cfg.get("tts_volume", 80)), 0, 100, 80)
        self.cfg["tts_playback_device"] = str(data.get("tts_playback_device", self.cfg.get("tts_playback_device", "default"))).strip() or "default"
        requested_tts_url = str(data.get("brain_tts_base_url", self.cfg.get("brain_tts_base_url", ""))).strip()
        follow_brain_host = True
        self.cfg["brain_tts_follow_brain_host"] = follow_brain_host
        self.cfg["brain_tts_base_url"] = self.resolve_brain_tts_base_url(update_config=True)
        self.cfg["brain_tts_use_brain_defaults"] = True
        # Explicit Brain engine/voice fields are compatibility metadata only.
        # The request payload omits them so the desktop Brain's live selection wins.
        self.cfg["brain_tts_format"] = str(data.get("brain_tts_format", self.cfg.get("brain_tts_format", "wav"))).strip().lower() or "wav"
        self.cfg["brain_tts_timeout_s"] = clamp_int(data.get("brain_tts_timeout_s", self.cfg.get("brain_tts_timeout_s", 240)), 20, 600, 240)
        endpoint = str(data.get("brain_tts_endpoint", self.cfg.get("brain_tts_endpoint", "/api/tts"))).strip() or "/api/tts"
        status_endpoint = str(data.get("brain_tts_status_endpoint", self.cfg.get("brain_tts_status_endpoint", "/api/tts/status"))).strip() or "/api/tts/status"
        self.cfg["brain_tts_endpoint"] = endpoint if endpoint.startswith("/") else "/" + endpoint
        self.cfg["brain_tts_status_endpoint"] = status_endpoint if status_endpoint.startswith("/") else "/" + status_endpoint
        self.cfg.setdefault("tts_command", "espeak-ng -ven-gb -s 155 -p 35")
        self.cfg.setdefault("tts_piper_model", "models/piper/en_GB-alan-medium.onnx")
        self.cfg.setdefault("tts_piper_config", "")
        self.cfg.setdefault("tts_edge_voice", "en-GB-SoniaNeural")
        self.cfg["tts_queue_enabled"] = bool(data.get("tts_queue_enabled", self.cfg.get("tts_queue_enabled", True)))
        self.cfg["tts_chunking_enabled"] = bool(data.get("tts_chunking_enabled", self.cfg.get("tts_chunking_enabled", True)))
        self.cfg["tts_chunk_max_chars"] = clamp_int(data.get("tts_chunk_max_chars", self.cfg.get("tts_chunk_max_chars", 650)), 120, 1400, 650)
        self.cfg["tts_fallback_to_espeak"] = bool(data.get("tts_fallback_to_espeak", self.cfg.get("tts_fallback_to_espeak", False)))

        self.sync_voice_profile_from_audio_config()
        self.tts.update_config(self.build_audio_config())
        if save:
            self.save_robot_profile_file()
            self.save_config_file()
        self.web_log("system", f"Body playback settings saved: reply_voice=desktop_brain_app, fallback={backend}, volume={self.cfg['tts_volume']}%")
        return self.get_audio_settings()

    def web_update_audio_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            settings = self.apply_audio_settings(data, save=True)
            return {"ok": True, "audio": settings, "saved_to": str(CONFIG_PATH)}
        except Exception as exc:
            self.web_log("error", f"Speech settings save failed: {exc}")
            return {"ok": False, "error": str(exc)}


    def web_list_elevenlabs_voices(self, api_key: str = "") -> Dict[str, Any]:
        """Fetch voices available to the configured ElevenLabs API key."""
        key = str(api_key or "").strip() or str(self.cfg.get("tts_elevenlabs_api_key", "")).strip()
        try:
            voices = list_elevenlabs_voices(key, show_legacy=True)
            self.web_log("system", f"ElevenLabs voices fetched: {len(voices)}")
            return {"ok": True, "voices": voices}
        except Exception as exc:
            self.web_log("error", f"ElevenLabs voice fetch failed: {exc}")
            return {"ok": False, "error": str(exc), "voices": []}


    def web_robot_brain_tts_status(self) -> Dict[str, Any]:
        """Check the shared Brain API route used for Dot.TTS robot voice."""
        import urllib.error
        import urllib.request

        try:
            base = self.resolve_brain_tts_base_url(update_config=True).rstrip("/")
        except Exception as exc:
            return {"ok": False, "error": str(exc), "audio": self.get_audio_settings()}
        endpoint = str(self.cfg.get("brain_tts_status_endpoint", "/api/tts/status") or "/api/tts/status").strip()
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        if not base:
            return {
                "ok": False,
                "error": "Brain API URL is not set. Open Brain Connection and press Use This Browser PC.",
                "audio": self.get_audio_settings(),
            }
        url = base + endpoint
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:1200]}
            ok = bool(isinstance(data, dict) and data.get("ok", False))
            msg = "Robot Brain Dot.TTS route is reachable." if ok else "Robot Brain voice route replied but did not report ok=true."
            self.web_log("system" if ok else "error", msg, {"url": url, "response": data})
            return {"ok": ok, "url": url, "response": data, "audio": self.get_audio_settings(), "message": msg}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:1200]
            except Exception:
                detail = str(exc)
            result = {"ok": False, "url": url, "error": f"HTTP {exc.code}: {detail}", "audio": self.get_audio_settings()}
            self.web_log("error", "Robot Brain voice status failed: " + result["error"], result)
            return result
        except Exception as exc:
            result = {"ok": False, "url": url, "error": str(exc), "audio": self.get_audio_settings()}
            self.web_log("error", "Robot Brain voice status failed: " + str(exc), result)
            return result

    def web_tts_diagnostics(self) -> Dict[str, Any]:
        """Return a web-visible diagnostic report for natural TTS backends."""
        try:
            diagnostics = self.tts.diagnostics()  # type: ignore[attr-defined]
            problems = diagnostics.get("problems") or []
            if problems:
                self.web_log("error", "TTS diagnostics found problems: " + "; ".join(map(str, problems)))
            else:
                self.web_log("system", "TTS diagnostics OK for selected backend.")
            return {"ok": True, "diagnostics": diagnostics}
        except Exception as exc:
            self.web_log("error", f"TTS diagnostics failed: {exc}")
            return {"ok": False, "error": str(exc)}

    def web_test_speech(self, text: str = "") -> Dict[str, Any]:
        test_text = str(text or f"Speech test. {self.robot_name} voice system online. Gravity remains suspicious.").strip()
        forced_brain_defaults = False
        old_tts_cfg = getattr(self.tts, "cfg", None)
        try:
            if str(self.resolve_brain_tts_base_url(update_config=False) or "").strip():
                tts_cfg = self.build_audio_config()
                tts_cfg.tts_backend = "brain-tts"
                tts_cfg.brain_tts_use_brain_defaults = True
                self.tts.update_config(tts_cfg)
                forced_brain_defaults = True
            report = self.tts.test_speech_blocking(test_text)  # type: ignore[attr-defined]
        except AttributeError:
            self.tts.speak(test_text)
            report = {"ok": True, "message": "speech test sent", "backend_requested": self.cfg.get("tts_backend", "unknown")}
        except Exception as exc:
            report = {"ok": False, "message": str(exc)}
        finally:
            if forced_brain_defaults and old_tts_cfg is not None:
                try:
                    self.tts.update_config(old_tts_cfg)
                except Exception:
                    pass
        if isinstance(report, dict):
            report["request_source"] = "robot_web_speech_test"
            report["forced_brain_voice_defaults"] = forced_brain_defaults
        kind = "system" if report.get("ok") else "error"
        self.web_log(kind, "Speech test: " + str(report.get("message", "sent")), {
            "request_source": "robot_web_speech_test",
            "backend_requested": report.get("backend_requested"),
            "voice": report.get("voice"),
            "forced_brain_voice_defaults": forced_brain_defaults,
            "brain_tts": report.get("brain_tts", {}),
            "playback_device": self.cfg.get("tts_playback_device", "default"),
        })
        return {"ok": bool(report.get("ok")), "text": test_text, "audio": self.get_audio_settings(), "report": report}

    def web_snapshot(self) -> Dict[str, Any]:
        state = self.latest_state or self.read_body_state()
        return {
            "ok": True,
            "state": state,
            "events": list(self.web_events),
            "input_events": list(self.input_events),
            "hardware_doctor": self.hardware_doctor.snapshot(),
            "brain": self.get_brain_settings(),
            "ownership": self.get_control_ownership(),
            "audio": self.get_audio_settings(),
            "identity": self.get_identity_settings(),
            "robot_profile": self.get_robot_profile_payload(),
            "theme": self.get_theme_settings(),
            "voice": self.get_voice_settings(),
            "voice_runtime": self.get_voice_runtime_snapshot(),
            "mic": self.get_mic_settings(),
            "mic_level": self.web_mic_level(),
            "thinking_cues": self.get_thinking_cue_settings(),
            "idle_life": self.get_idle_life_settings(),
            "hardware": self.get_hardware_settings(),
            "led_states": self.get_led_state_settings(),
            "mouth_audio": dict(self.mouth_audio_runtime),
            "chat_bridge": self.get_chat_bridge_settings(),
            "vision_awareness": self.get_visual_awareness_settings(),
            "performance": self.get_performance_snapshot(),
            "last_reply": {
                "available": bool(self.last_reply_text),
                "chars": len(self.last_reply_text or ""),
                "updated_at": self.last_reply_at,
                "source": self.last_reply_source,
            },
            "web": {
                "host": str(self.cfg.get("web_host", "0.0.0.0")),
                "port": int(self.cfg.get("web_port", 8088)),
            },
        }

    def web_update_brain_settings(self, data: Dict[str, Any], client_ip: Optional[str] = None) -> Dict[str, Any]:
        """Update and save the Brain App connection from the web UI without restarting.

        Portable-network rule: when the web page is opened from the Windows Brain PC,
        'Use This Browser PC' saves that browser machine as the one Brain API host.
        """
        use_browser_ip = bool(data.get("use_browser_client_ip", False))
        sync_tts = bool(data.get("sync_tts_to_brain_host", use_browser_ip))
        api_key = str(data.get("api_key", self.cfg.get("api_key", "")))

        if use_browser_ip:
            if not client_ip:
                return {"ok": False, "error": "Browser client IP was not available."}
            port = str(data.get("brain_port", "8765") or "8765").strip()
            base_url = f"http://{client_ip}:{port}"
        else:
            base_url = str(data.get("brain_base_url", "") or data.get("base_url", "")).strip()

        try:
            settings = self.apply_brain_connection(base_url, api_key=api_key, save=False)
            if sync_tts:
                self.cfg["brain_tts_base_url"] = self.normalise_brain_tts_base_url(settings["base_url"])
                self.cfg["brain_tts_follow_brain_host"] = True
                self.cfg["brain_tts_engine"] = "dottts"
                self.cfg["brain_tts_voice"] = "active_profile"
                self.cfg["brain_tts_endpoint"] = "/api/tts"
                self.cfg["brain_tts_status_endpoint"] = "/api/tts/status"
                self.sync_voice_profile_from_audio_config()
                self.tts.update_config(self.build_audio_config())
            self.save_robot_profile_file()
            self.save_config_file()
            settings = self.get_brain_settings()
        except Exception as exc:
            failure = {
                "requested_base_url": base_url,
                "use_browser_client_ip": use_browser_ip,
                "config_path": str(CONFIG_PATH),
                "error": str(exc),
            }
            self.web_log("error", f"Brain App URL save failed for {base_url or '[empty]'}: {exc}", failure)
            return {"ok": False, **failure}

        msg = f"Brain App URL saved: {settings.get('base_url')}"
        if sync_tts:
            msg += "; Dot.TTS reply audio enabled through the Brain API"
        self.web_log("system", msg)
        return {"ok": True, "brain": settings, "audio": self.get_audio_settings(), "saved_to": str(CONFIG_PATH)}

    def web_test_brain_connection(self) -> Dict[str, Any]:
        """Check that the Brain App API is reachable from BX1."""
        t0 = time.perf_counter()
        try:
            status = self.brain.status()
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            with self.metrics_lock:
                self.performance["last_brain_latency_ms"] = latency_ms
            self.web_log("system", f"Brain App connection OK: {self.brain.base_url} ({latency_ms} ms)")
            return {"ok": True, "base_url": self.brain.base_url, "latency_ms": latency_ms, "status": status}
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            with self.metrics_lock:
                self.performance["last_brain_latency_ms"] = latency_ms
                self.performance["last_error"] = str(exc)[:300]
            self.web_log("error", f"Brain App connection test failed: {exc}")
            return {"ok": False, "base_url": self.brain.base_url, "latency_ms": latency_ms, "error": str(exc)}

    def get_chat_bridge_settings(self) -> Dict[str, Any]:
        configured = normalise_text_list(self.cfg.get("vision_trigger_phrases", []))
        phrases = list(DEFAULT_VISION_TRIGGER_PHRASES)
        for phrase in configured:
            low = str(phrase).lower().strip()
            if low and low not in phrases:
                phrases.append(low)
        brain_owns_policy = bool(self.cfg.get("brain_controls_web_memory", True))
        return {
            "policy_owner": "desktop_brain_app" if brain_owns_policy else "body_compatibility_mode",
            "use_web_for_robot_questions": None if brain_owns_policy else bool(self.cfg.get("use_web_for_robot_questions", False)),
            "use_memory": None if brain_owns_policy else bool(self.cfg.get("use_memory", True)),
            "auto_camera_on_vision_request": bool(self.cfg.get("auto_camera_on_vision_request", True)),
            "vision_trigger_phrases": phrases,
            "camera_enabled": bool(self.cfg.get("camera_enabled", True)),
            "robot_direct_internet_required": False,
            "internet_route": "laptop_brain_app",
            "brain_app_base_url": str(self.cfg.get("brain_base_url", self.brain.base_url)),
        }

    def web_update_chat_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(self.cfg.get("brain_controls_web_memory", True)):
            self.cfg["use_web_for_robot_questions"] = bool(data.get("use_web_for_robot_questions", self.cfg.get("use_web_for_robot_questions", False)))
            self.cfg["use_memory"] = bool(data.get("use_memory", self.cfg.get("use_memory", True)))
        self.cfg["auto_camera_on_vision_request"] = bool(data.get("auto_camera_on_vision_request", self.cfg.get("auto_camera_on_vision_request", True)))
        raw_phrases = data.get("vision_trigger_phrases", self.cfg.get("vision_trigger_phrases", DEFAULT_VISION_TRIGGER_PHRASES))
        phrases = normalise_text_list(raw_phrases)
        if not phrases:
            phrases = list(DEFAULT_VISION_TRIGGER_PHRASES)
        self.cfg["vision_trigger_phrases"] = phrases
        self.save_config_file()
        self.web_log("system", "Chat bridge settings saved")
        return {"ok": True, "chat_bridge": self.get_chat_bridge_settings(), "saved_to": str(CONFIG_PATH)}

    def web_stt_once(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Exercise the exact production STT path once, with optional Brain send."""
        send_to_brain = bool(data.get("send", False))
        self.manual_audio_capture_requested.set()
        got_lock = False
        monitor_was_running = bool(self.mic_monitor.is_running())
        result: Dict[str, Any] = {}
        self.last_stt_capture_id = ""
        self.last_stt_debug_audio_urls = {}
        try:
            # The live wake capture cooperatively exits when the handover event is
            # set, normally within one 20 ms audio frame. Keep a bounded fallback
            # wait in case ALSA itself is stalled.
            got_lock = self.audio_capture_lock.acquire(timeout=4.0)
            if not got_lock:
                return {
                    "ok": False, "stage": "capture",
                    "error": "microphone handover timed out",
                    "hint": "The live arecord process did not release within four seconds.",
                }
            if monitor_was_running:
                self.mic_monitor.stop()
                time.sleep(0.15)
            self.set_voice_runtime("recording", "Diagnostic listen: waiting for a complete utterance...", loop_active=bool(self.voice_runtime.get("loop_active", False)))
            # Reuse the already-loaded Vosk model. The old diagnostic path
            # rebuilt the model for every button press, which could add several
            # seconds before transcription even started.
            stt = self.stt
            if stt is None or not stt.ready:
                stt = VoskSpeechToText(self.build_audio_config())
                self.stt = stt
            if not stt.ready:
                return {"ok": False, "stage": "initialise", "error": stt.error}
            result = stt.listen_once_detailed(
                float(self.cfg.get("stt_start_timeout_s", self.cfg.get("record_seconds", 8))),
                defer_local_recognition=self._defer_local_vosk_for_primary_stt(),
            )
            result = self._apply_primary_stt(result, source="web_stt_diagnostic", stt_engine=stt)
        finally:
            if got_lock:
                try:
                    self.audio_capture_lock.release()
                except RuntimeError:
                    pass
            self.manual_audio_capture_requested.clear()
            if monitor_was_running:
                try:
                    self._refresh_mic_monitor_settings()
                    self.mic_monitor.start()
                except Exception:
                    pass

        debug_paths = result.get("debug_audio") if isinstance(result.get("debug_audio"), dict) else {}
        # The touchscreen calibration route reports bounded metadata only.
        # Remove temporary debug WAVs before returning so neither raw nor
        # submitted speech is retained or exported through the OS bridge.
        for path_value in debug_paths.values():
            try:
                Path(str(path_value)).unlink(missing_ok=True)
            except OSError:
                pass
        result.pop("debug_audio", None)
        result.pop("capture_id", None)
        result["debug_audio_urls"] = {}

        text = str(result.get("text") or "").strip()
        metrics = {
            "confidence": result.get("confidence"),
            "capture_method": result.get("capture_method"),
            "capture": result.get("capture", {}),
            "voice_activity": result.get("voice_activity", {}),
            "debug_audio": result.get("debug_audio", {}),
            "debug_audio_urls": result.get("debug_audio_urls", {}),
            "capture_id": result.get("capture_id", ""),
            "transcription_backend": result.get("transcription_backend", "local_vosk"),
            "local_vosk_text": result.get("local_vosk_text", ""),
            "stt_model": result.get("stt_model", ""),
            "stt_device": result.get("stt_device", ""),
            "stt_compute_type": result.get("stt_compute_type", ""),
            "stt_latency_ms": result.get("stt_latency_ms"),
            "brain_stt_roundtrip_ms": result.get("brain_stt_roundtrip_ms"),
            "local_recognition_ms": result.get("local_recognition_ms"),
            "stt_pipeline_ms": result.get("stt_pipeline_ms"),
            "primary_stt_error": result.get("primary_stt_error", ""),
            "primary_stt_handoff": result.get("primary_stt_handoff", {}),
        }
        if not result.get("accepted", False):
            reason = str(result.get("reason") or result.get("error") or "speech rejected")
            self.set_voice_runtime("rejected", f"Diagnostic STT rejected input: {reason}", last_rejected=text, last_rejection_reason=reason, last_stt_metrics=metrics)
            self.web_log("rejected_input", f"Diagnostic STT: {reason}", {"text": text, **metrics})
            return {"ok": False, "stage": "stt", "text": text, "stt": result, "error": reason}

        self.set_voice_runtime("heard", f"Diagnostic STT heard: {text}", last_heard=text, last_stt_metrics=metrics)
        self.web_log("input", f"Diagnostic STT heard: {text}", metrics)
        response: Optional[Dict[str, Any]] = None
        if send_to_brain:
            self.set_voice_runtime("processing", "Diagnostic STT sending recognised text to Brain App...", last_accepted=text)
            with self.command_lock:
                response = self.handle_user_text(text, source="web_stt_diagnostic", trigger="listen_once", input_metadata=metrics)
        ok = bool(text) if not send_to_brain else bool(response and response.get("ok"))
        return {
            "ok": ok,
            "stage": "sent" if send_to_brain else "stt",
            "text": text,
            "stt": result,
            "brain_response": response,
        }

    def web_repeat_last_response(self) -> Dict[str, Any]:
        with self.command_lock:
            return self.repeat_last_response()

    def web_send_text(self, text: str, use_web: Optional[bool] = None, use_memory: Optional[bool] = None, allow_vision: Optional[bool] = None) -> Dict[str, Any]:
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "empty text"}
        with self.command_lock:
            return self.handle_user_text(text, use_web=use_web, use_memory=use_memory, allow_vision=allow_vision)

    def web_voice_vertical_slice(self, text: str, session_id: str) -> Dict[str, Any]:
        """Run the Body-owned Brain/TTS path with actions and local fallback disabled."""
        question = str(text or "").strip()
        correlation = str(session_id or "").strip()
        if not question or len(question) > 1000 or not re.fullmatch(r"voice-[a-f0-9]{32}", correlation):
            return {"ok": False, "error": "invalid_voice_vertical_slice_request"}
        for event in ("WakeDetected", "ListeningStarted", "SpeechRecognised"):
            self.emit_voice_observer_event(event, correlation, stage="typed_test")
        with self.command_lock:
            self._voice_vertical_slice_no_actuators = True
            try:
                result = self.handle_user_text(
                    question, allow_vision=False, source="bx1_os_voice_vertical_slice", trigger="typed_test",
                    event_id=correlation, input_metadata={"kind": "typed_test"}, allow_actions=False,
                    privacy_mode=True,
                )
            finally:
                self._voice_vertical_slice_no_actuators = False
        if not result.get("ok"):
            # The precise Body/Brain/TTS fault was already emitted by the owning
            # stage; do not duplicate it with a generic wrapper event.
            return {"ok": False, "session_id": correlation, "failure_stage": str(result.get("error") or "brain_request_failed")}
        # This immediate response is rendered only in BX1 OS's RAM-only shared
        # console; it is not sent to the observer timeline or any persistent log.
        return {"ok": True, "session_id": correlation, "playback_owner": "robot_body", "stage": "playback_pending", "reply": str(result.get("reply") or "")[:4000]}

    def web_voice_vertical_probe(self) -> Dict[str, Any]:
        """Read only the configured Body-to-Brain status and TTS readiness routes."""
        if not str(self.brain.base_url or "").strip():
            return {"ok": False, "state": "not_connected", "reason": "brain_not_configured"}
        try:
            self.brain.status()
        except Exception:
            return {"ok": False, "state": "not_connected", "reason": "brain_status_unavailable"}
        try:
            # Keep the deployed Body patch to its three approved files.  Older
            # Brain clients already expose the same authenticated GET transport.
            self.brain._get_json("/api/tts/status", timeout=10)
        except Exception:
            return {"ok": False, "state": "degraded", "reason": "brain_tts_unavailable"}
        return {"ok": True, "state": "connected", "reason": "brain_and_tts_ready"}

    def get_identity_settings(self) -> Dict[str, Any]:
        profile = self.get_robot_profile_payload()
        caps = dict(profile.get("capabilities") or {})
        physical = dict(profile.get("physical_description") or {})
        return {
            "brain_owns_identity": True,
            "message": "Robot name, character and personality are now configured in the desktop Robot Brain instance, not on the Arduino body client.",
            "body_id": self.robot_id,
            "robot_id": self.robot_id,
            "robot_name": "",
            "display_name": "",
            "wake_words": self.get_wake_words(),
            "personality_summary": "",
            "personality_tone": "",
            "personality_verbosity": "brain-managed",
            "personality_humour_level": 0.0,
            "personality_confidence_level": 0.0,
            "personality_controls": {},
            "personality_control_labels": [],
            "personality_presets": {},
            "personality_style_strength": 0,
            "personality_rules": [],
            "capabilities": caps,
            "robot_type": str(physical.get("robot_type", "")),
            "robot_location": str(physical.get("location", "")),
            "profile_path": "Brain-managed; Arduino robot_profile.json is deprecated",
        }

    def web_update_identity_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Compatibility endpoint: only save body ID, wake words and physical capability
        # metadata. Ignore name/personality fields from older pages.
        body_id = str(data.get("body_id") or data.get("robot_id") or self.robot_id).strip() or "UNO_Q_BODY"
        self.robot_id = body_id
        self.cfg["robot_id"] = body_id
        raw_wake = data.get("wake_words", self.cfg.get("wake_words", ["hello", "hey", "robot"]))
        self.cfg["wake_words"] = normalise_text_list(raw_wake) or ["hello", "hey", "robot"]
        caps_in = data.get("capabilities", {}) if isinstance(data.get("capabilities", {}), dict) else {}
        old_caps = dict(self.robot_profile.get("capabilities") or {})
        capabilities = {
            "has_microphone": bool(caps_in.get("has_microphone", old_caps.get("has_microphone", True))),
            "has_speaker": bool(caps_in.get("has_speaker", old_caps.get("has_speaker", True))),
            "has_camera": bool(caps_in.get("has_camera", old_caps.get("has_camera", True))),
            "has_head_servo": bool(caps_in.get("has_head_servo", old_caps.get("has_head_servo", True))),
            "has_drive_motors": bool(caps_in.get("has_drive_motors", old_caps.get("has_drive_motors", False))),
            "has_lidar": bool(caps_in.get("has_lidar", old_caps.get("has_lidar", False))),
        }
        physical = dict(self.robot_profile.get("physical_description") or {})
        physical["robot_type"] = str(data.get("robot_type", physical.get("robot_type", "generic robot body client"))).strip()
        physical["location"] = str(data.get("robot_location", physical.get("location", "workshop or test environment"))).strip()
        self.robot_profile.update({
            "body_id": body_id,
            "robot_id": body_id,
            "brain_owns_identity": True,
            "wake_words": list(self.cfg.get("wake_words", ["hello", "hey", "robot"])),
            "capabilities": capabilities,
            "physical_description": physical,
        })
        self.apply_robot_profile_to_config(save=True)
        self.web_log("system", f"Body settings saved: {body_id}. Personality remains Brain-managed.")
        return {"ok": True, "identity": self.get_identity_settings(), "robot_profile": self.get_robot_profile_payload(), "saved_to": str(CONFIG_PATH)}

    def get_hardware_doctor_settings(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.cfg.get("hardware_doctor_enabled", True)),
            "auto_recovery_enabled": bool(self.cfg.get("hardware_doctor_auto_recovery_enabled", True)),
            "interval_s": float(self.cfg.get("hardware_doctor_interval_s", 15.0)),
            "failure_threshold": int(self.cfg.get("hardware_doctor_failure_threshold", 3)),
            "recovery_cooldown_s": float(self.cfg.get("hardware_doctor_recovery_cooldown_s", 90.0)),
            "automatic_flashing": False,
            "snapshot": self.hardware_doctor.snapshot(),
        }

    def web_run_hardware_diagnosis(self) -> Dict[str, Any]:
        self.apply_led_state("diagnostic", source="hardware_doctor", force=True)
        diagnosis = self.hardware_doctor.diagnose(self.latest_state or None)
        return {"ok": True, "diagnosis": diagnosis, "automatic_flashing": False}

    def web_hardware_doctor_recover(self) -> Dict[str, Any]:
        self.apply_led_state("diagnostic", source="hardware_doctor_recovery", force=True)
        result = self.hardware_doctor.safe_recover(reason="manual web request", force=True)
        self.apply_led_state("success" if result.get("ok") else "error", source="hardware_doctor_result", force=True)
        return result

    def web_generate_diagnostic_sketch(self, template: str, note: str = "") -> Dict[str, Any]:
        return self.hardware_doctor.generate_sketch(template, note)

    def _get_cached_mic_devices(self, force: bool = False) -> Dict[str, Any]:
        now = time.monotonic()
        if force or not self._mic_devices_cache or (now - float(self._mic_devices_cache_time or 0.0)) > 15.0:
            try:
                self._mic_devices_cache = list_audio_capture_devices()
            except Exception as exc:
                self._mic_devices_cache = {"ok": False, "error": str(exc), "devices": []}
            self._mic_devices_cache_time = now
        return dict(self._mic_devices_cache)

    def get_mic_settings(self) -> Dict[str, Any]:
        devices = self._get_cached_mic_devices(force=False)
        return {
            "mic_device": str(self.cfg.get("mic_device", "default")),
            "mic_channels": int(self.cfg.get("mic_channels", 1)),
            "sample_rate": int(self.cfg.get("sample_rate", 16000)),
            "record_seconds": int(self.cfg.get("record_seconds", 5)),
            "mic_capture_volume": int(self.cfg.get("mic_capture_volume", 70)),
            "mic_capture_control": str(self.cfg.get("mic_capture_control", "Capture")),
            "mic_software_gain_db": float(self.cfg.get("mic_software_gain_db", 0.0)),
            "mic_noise_gate_dbfs": float(self.cfg.get("mic_noise_gate_dbfs", -45.0)),
            "mic_highpass_enabled": bool(self.cfg.get("audio_highpass_enabled", self.cfg.get("mic_highpass_enabled", True))),
            "audio_filter_enabled": bool(self.cfg.get("audio_filter_enabled", True)),
            "audio_highpass_enabled": bool(self.cfg.get("audio_highpass_enabled", True)),
            "audio_highpass_hz": float(self.cfg.get("audio_highpass_hz", 90.0)),
            "audio_notch_enabled": bool(self.cfg.get("audio_notch_enabled", True)),
            "audio_notch_hz": float(self.cfg.get("audio_notch_hz", 50.0)),
            "audio_notch_q": float(self.cfg.get("audio_notch_q", 25.0)),
            "audio_notch_harmonics": int(self.cfg.get("audio_notch_harmonics", 2)),
            "audio_noise_reduction_enabled": bool(self.cfg.get("audio_noise_reduction_enabled", True)),
            "audio_noise_reduction_strength": float(self.cfg.get("audio_noise_reduction_strength", 0.20)),
            "audio_noise_gate_knee_db": float(self.cfg.get("audio_noise_gate_knee_db", 10.0)),
            "audio_live_fft_bins": int(self.cfg.get("audio_live_fft_bins", 48)),
            "stt_validation_enabled": bool(self.cfg.get("stt_validation_enabled", True)),
            "stt_min_confidence": float(self.cfg.get("stt_min_confidence", 0.40)),
            "stt_min_voiced_ms": int(self.cfg.get("stt_min_voiced_ms", 280)),
            "stt_min_longest_voiced_ms": int(self.cfg.get("stt_min_longest_voiced_ms", 160)),
            "stt_noise_margin_db": float(self.cfg.get("stt_noise_margin_db", 6.0)),
            "stt_capture_method": str(self.cfg.get("stt_capture_method", "alsa")),
            "stt_endpointing_enabled": bool(self.cfg.get("stt_endpointing_enabled", True)),
            "stt_start_timeout_s": float(self.cfg.get("stt_start_timeout_s", 8.0)),
            "stt_max_utterance_s": float(self.cfg.get("stt_max_utterance_s", 20.0)),
            "stt_pre_roll_ms": int(self.cfg.get("stt_pre_roll_ms", 700)),
            "stt_end_silence_ms": int(self.cfg.get("stt_end_silence_ms", 1350)),
            "stt_post_roll_ms": int(self.cfg.get("stt_post_roll_ms", 300)),
            "stt_start_trigger_ms": int(self.cfg.get("stt_start_trigger_ms", 80)),
            "stt_speech_resume_trigger_ms": int(self.cfg.get("stt_speech_resume_trigger_ms", 140)),
            "stt_transient_guard_after_ms": int(self.cfg.get("stt_transient_guard_after_ms", 220)),
            "stt_endpoint_hysteresis_db": float(self.cfg.get("stt_endpoint_hysteresis_db", 3.0)),
            "stt_adaptive_threshold_enabled": bool(self.cfg.get("stt_adaptive_threshold_enabled", True)),
            "stt_adaptive_margin_db": float(self.cfg.get("stt_adaptive_margin_db", 8.0)),
            "stt_debug_keep_audio": bool(self.cfg.get("stt_debug_keep_audio", True)),
            "stt_debug_audio": {
                "raw": str(Path(tempfile.gettempdir()) / "bx1_stt_last_raw.wav"),
                "filtered": str(Path(tempfile.gettempdir()) / "bx1_stt_last_filtered.wav"),
                "submitted": str(Path(tempfile.gettempdir()) / "bx1_stt_last_submitted.wav"),
            },
            "stt_last_capture_id": self.last_stt_capture_id,
            "stt_debug_audio_urls": dict(self.last_stt_debug_audio_urls),
            "stt_duplicate_window_s": float(self.cfg.get("stt_duplicate_window_s", 12.0)),
            "stt_echo_similarity_threshold": float(self.cfg.get("stt_echo_similarity_threshold", 0.78)),
            "mic_playback_device": str(self.cfg.get("mic_playback_device", "default")),
            "mic_monitor_running": bool(self.mic_monitor.is_running()),
            "capture_busy": bool(self.audio_capture_lock.locked()),
            "manual_capture_requested": bool(self.manual_audio_capture_requested.is_set()),
            "capture_handover": "cooperative_v10_39",
            "last_mic_test_wav": self.last_mic_test_wav,
            "devices": devices.get("devices", []),
            "devices_raw": devices.get("raw", ""),
            "devices_ok": bool(devices.get("ok", False)),
            "devices_error": str(devices.get("error", "")),
        }

    def _refresh_mic_monitor_settings(self) -> None:
        self.mic_monitor.update_settings(
            device=str(self.cfg.get("mic_device", "default")),
            sample_rate=int(self.cfg.get("sample_rate", 16000)),
            channels=int(self.cfg.get("mic_channels", 1)),
            noise_gate_dbfs=float(self.cfg.get("mic_noise_gate_dbfs", -48.0)),
            software_gain_db=float(self.cfg.get("mic_software_gain_db", 0.0)),
            dsp_settings=build_audio_dsp_settings(self.cfg),
            fft_bins=int(self.cfg.get("audio_live_fft_bins", 48)),
        )

    def web_update_mic_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
            try:
                return max(lo, min(hi, float(value)))
            except Exception:
                return default

        def clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
            try:
                return max(lo, min(hi, int(float(value))))
            except Exception:
                return default

        self.cfg["mic_device"] = str(data.get("mic_device", self.cfg.get("mic_device", "default"))).strip() or "default"
        self.cfg["mic_channels"] = clamp_int(data.get("mic_channels", self.cfg.get("mic_channels", 1)), 1, 2, 1)
        self.cfg["sample_rate"] = clamp_int(data.get("sample_rate", self.cfg.get("sample_rate", 16000)), 8000, 48000, 16000)
        self.cfg["record_seconds"] = clamp_int(data.get("record_seconds", self.cfg.get("record_seconds", 5)), 1, 30, 5)
        self.cfg["mic_capture_volume"] = clamp_int(data.get("mic_capture_volume", self.cfg.get("mic_capture_volume", 70)), 0, 100, 70)
        self.cfg["mic_capture_control"] = str(data.get("mic_capture_control", self.cfg.get("mic_capture_control", "Capture"))).strip() or "Capture"
        self.cfg["mic_software_gain_db"] = clamp_float(data.get("mic_software_gain_db", self.cfg.get("mic_software_gain_db", 0.0)), -24.0, 36.0, 0.0)
        self.cfg["mic_noise_gate_dbfs"] = clamp_float(data.get("mic_noise_gate_dbfs", self.cfg.get("mic_noise_gate_dbfs", -48.0)), -90.0, -5.0, -48.0)
        self.cfg["audio_filter_enabled"] = bool(data.get("audio_filter_enabled", self.cfg.get("audio_filter_enabled", True)))
        self.cfg["audio_highpass_enabled"] = bool(data.get("audio_highpass_enabled", data.get("mic_highpass_enabled", self.cfg.get("audio_highpass_enabled", True))))
        self.cfg["mic_highpass_enabled"] = self.cfg["audio_highpass_enabled"]
        self.cfg["audio_highpass_hz"] = clamp_float(data.get("audio_highpass_hz", self.cfg.get("audio_highpass_hz", 90.0)), 20.0, 300.0, 90.0)
        self.cfg["audio_notch_enabled"] = bool(data.get("audio_notch_enabled", self.cfg.get("audio_notch_enabled", True)))
        self.cfg["audio_notch_hz"] = clamp_float(data.get("audio_notch_hz", self.cfg.get("audio_notch_hz", 50.0)), 40.0, 70.0, 50.0)
        self.cfg["audio_notch_q"] = clamp_float(data.get("audio_notch_q", self.cfg.get("audio_notch_q", 25.0)), 2.0, 80.0, 25.0)
        self.cfg["audio_notch_harmonics"] = clamp_int(data.get("audio_notch_harmonics", self.cfg.get("audio_notch_harmonics", 2)), 1, 4, 2)
        self.cfg["audio_noise_reduction_enabled"] = bool(data.get("audio_noise_reduction_enabled", self.cfg.get("audio_noise_reduction_enabled", True)))
        self.cfg["audio_noise_reduction_strength"] = clamp_float(data.get("audio_noise_reduction_strength", self.cfg.get("audio_noise_reduction_strength", 0.20)), 0.0, 1.0, 0.20)
        self.cfg["audio_noise_gate_knee_db"] = clamp_float(data.get("audio_noise_gate_knee_db", self.cfg.get("audio_noise_gate_knee_db", 10.0)), 2.0, 24.0, 10.0)
        self.cfg["audio_live_fft_bins"] = clamp_int(data.get("audio_live_fft_bins", self.cfg.get("audio_live_fft_bins", 48)), 16, 80, 48)
        self.cfg["stt_validation_enabled"] = bool(data.get("stt_validation_enabled", self.cfg.get("stt_validation_enabled", True)))
        self.cfg["stt_min_confidence"] = clamp_float(data.get("stt_min_confidence", self.cfg.get("stt_min_confidence", 0.40)), 0.0, 1.0, 0.40)
        self.cfg["stt_min_voiced_ms"] = clamp_int(data.get("stt_min_voiced_ms", self.cfg.get("stt_min_voiced_ms", 280)), 80, 3000, 280)
        self.cfg["stt_min_longest_voiced_ms"] = clamp_int(data.get("stt_min_longest_voiced_ms", self.cfg.get("stt_min_longest_voiced_ms", 160)), 40, 1500, 160)
        self.cfg["stt_noise_margin_db"] = clamp_float(data.get("stt_noise_margin_db", self.cfg.get("stt_noise_margin_db", 6.0)), 0.0, 24.0, 6.0)
        capture_method = str(data.get("stt_capture_method", self.cfg.get("stt_capture_method", "alsa"))).strip().lower()
        self.cfg["stt_capture_method"] = capture_method if capture_method in {"alsa", "arecord", "auto", "sounddevice"} else "alsa"
        self.cfg["stt_endpointing_enabled"] = bool(data.get("stt_endpointing_enabled", self.cfg.get("stt_endpointing_enabled", True)))
        self.cfg["stt_start_timeout_s"] = clamp_float(data.get("stt_start_timeout_s", self.cfg.get("stt_start_timeout_s", 8.0)), 1.0, 60.0, 8.0)
        self.cfg["stt_max_utterance_s"] = clamp_float(data.get("stt_max_utterance_s", self.cfg.get("stt_max_utterance_s", 20.0)), 2.0, 120.0, 20.0)
        self.cfg["stt_pre_roll_ms"] = clamp_int(data.get("stt_pre_roll_ms", self.cfg.get("stt_pre_roll_ms", 700)), 0, 2000, 700)
        self.cfg["stt_end_silence_ms"] = clamp_int(data.get("stt_end_silence_ms", self.cfg.get("stt_end_silence_ms", 1350)), 250, 4000, 1350)
        self.cfg["stt_post_roll_ms"] = clamp_int(data.get("stt_post_roll_ms", self.cfg.get("stt_post_roll_ms", 300)), 0, 1500, 300)
        self.cfg["stt_start_trigger_ms"] = clamp_int(data.get("stt_start_trigger_ms", self.cfg.get("stt_start_trigger_ms", 80)), 20, 600, 80)
        self.cfg["stt_speech_resume_trigger_ms"] = clamp_int(data.get("stt_speech_resume_trigger_ms", self.cfg.get("stt_speech_resume_trigger_ms", 140)), 40, 600, 140)
        self.cfg["stt_transient_guard_after_ms"] = clamp_int(data.get("stt_transient_guard_after_ms", self.cfg.get("stt_transient_guard_after_ms", 220)), 0, 1200, 220)
        self.cfg["stt_endpoint_hysteresis_db"] = clamp_float(data.get("stt_endpoint_hysteresis_db", self.cfg.get("stt_endpoint_hysteresis_db", 3.0)), 0.0, 12.0, 3.0)
        self.cfg["stt_adaptive_threshold_enabled"] = bool(data.get("stt_adaptive_threshold_enabled", self.cfg.get("stt_adaptive_threshold_enabled", True)))
        self.cfg["stt_adaptive_margin_db"] = clamp_float(data.get("stt_adaptive_margin_db", self.cfg.get("stt_adaptive_margin_db", 8.0)), 0.0, 30.0, 8.0)
        self.cfg["stt_debug_keep_audio"] = bool(data.get("stt_debug_keep_audio", self.cfg.get("stt_debug_keep_audio", True)))
        self.cfg["stt_duplicate_window_s"] = clamp_float(data.get("stt_duplicate_window_s", self.cfg.get("stt_duplicate_window_s", 12.0)), 1.0, 120.0, 12.0)
        self.cfg["stt_echo_similarity_threshold"] = clamp_float(data.get("stt_echo_similarity_threshold", self.cfg.get("stt_echo_similarity_threshold", 0.78)), 0.55, 0.98, 0.78)
        volume_report = set_alsa_capture_volume(self.cfg["mic_capture_volume"], self.cfg["mic_capture_control"])
        self._refresh_mic_monitor_settings()
        # Force the wake-word STT helper to rebuild so it picks up a newly
        # selected plughw microphone device.
        self.stt = None
        self.save_config_file()
        self.web_log("system", f"Microphone settings saved: device={self.cfg['mic_device']}")
        return {"ok": True, "mic": self.get_mic_settings(), "volume_report": volume_report, "saved_to": str(CONFIG_PATH)}

    def web_start_mic_monitor(self) -> Dict[str, Any]:
        # The live wake listener and level meter cannot own the same ALSA device
        # simultaneously. Pause the wake loop while the diagnostic meter is open.
        self.manual_audio_capture_requested.set()
        self._refresh_mic_monitor_settings()
        result = self.mic_monitor.start()
        if not result.get("ok"):
            self.manual_audio_capture_requested.clear()
        self.web_log("system" if result.get("ok") else "error", str(result.get("message") or result.get("error") or "mic monitor"))
        return result

    def web_stop_mic_monitor(self) -> Dict[str, Any]:
        result = self.mic_monitor.stop()
        self.manual_audio_capture_requested.clear()
        self.web_log("system", "Microphone monitor stopped")
        return result

    def web_mic_level(self) -> Dict[str, Any]:
        level = self.mic_monitor.snapshot()
        return {"ok": True, "level": level, "mic": self.get_mic_settings() if False else None}

    def web_bx1_audio_bridge(self) -> Dict[str, Any]:
        """Metadata-only live voice projection; it never transfers raw audio."""
        runtime = self.get_voice_runtime_snapshot()
        metrics = runtime.get("last_stt_metrics", {}) if isinstance(runtime.get("last_stt_metrics"), dict) else {}
        activity = metrics.get("voice_activity", {}) if isinstance(metrics.get("voice_activity"), dict) else {}
        live = runtime.get("live_audio", {}) if isinstance(runtime.get("live_audio"), dict) else {}
        def number(value: Any) -> Optional[float]:
            try:
                parsed = float(value)
                return parsed if math.isfinite(parsed) else None
            except (TypeError, ValueError):
                return None
        sample_at = live.get("captured_at")
        now = time.time()
        age = max(0.0, now - float(sample_at)) if isinstance(sample_at, (int, float)) else None
        rms, peak = number(live.get("rms_dbfs")), number(live.get("peak_dbfs"))
        noise = number(live.get("noise_floor_dbfs"))
        threshold = number(live.get("threshold_dbfs"))
        live_available = age is not None and age <= 2.5 and all(value is not None for value in (rms, peak, noise, threshold))
        if noise is None: noise = number(activity.get("noise_floor_dbfs"))
        if threshold is None: threshold = number(activity.get("threshold_dbfs")) or float(self.cfg.get("mic_noise_gate_dbfs", -48.0))
        if noise is None: noise = float(self.cfg.get("mic_noise_gate_dbfs", -48.0))
        raw_state = str(runtime.get("state", "idle")).lower()
        state_map = {"starting": "idle", "awake": "wake detected", "wake_detected": "wake detected", "listening": "listening", "recording": "speech detected", "heard": "speech detected", "recognising": "recognising", "transcribing": "recognising", "processing": "Brain request", "speechgen": "Brain request", "speaking": "speaking", "echo_suppressed": "echo suppressed", "error": "failed", "rejected": "failed", "disabled": "idle"}
        state = state_map.get(raw_state, raw_state if raw_state in {"idle", "failed"} else "idle")
        suppression = runtime.get("speaker_suppression", {}) if isinstance(runtime.get("speaker_suppression"), dict) else {}
        if suppression.get("playback_active"):
            state = "speaking"
        elif float(suppression.get("echo_tail_remaining_s") or 0.0) > 0:
            state = "echo suppressed"
        if live_available and bool(live.get("speech_detected")) and state == "listening": state = "speech detected"
        display_state = state if live_available else ("stale" if age is not None else "unavailable")
        latest_text = str(runtime.get("last_heard") or runtime.get("last_rejected") or "").strip()[:240]
        accepted_request = str(runtime.get("last_accepted") or "").strip()[:240]
        discarded_audio = str(runtime.get("last_rejected") or runtime.get("last_ignored") or "").strip()[:240]
        latest_reply = str(getattr(self, "last_reply_text", "") or "").strip()[:400]
        rejection = str(runtime.get("last_rejection_reason") or runtime.get("last_error") or "").strip()[:240]
        engine = str(metrics.get("transcription_backend") or self.cfg.get("voice_backend", "unknown"))[:80]
        reason = "" if live_available else ("Active ALSA capture heartbeat is stale." if age is not None else "Active ALSA capture has not published a valid heartbeat.")
        heartbeat = {"publisher": str(live.get("publisher") or "none"), "sequence": int(live.get("sequence") or 0), "target_hz": int(live.get("target_hz") or 6), "last_callback_at": sample_at, "age_seconds": age, "fresh": live_available}
        wake_remaining = max(0.0, float(runtime.get("conversation_awake_remaining_s") or 0.0))
        state_detail = str(runtime.get("label") or state)
        if state == "wake detected" and wake_remaining > 0:
            state_detail = f"Wake detected — listening for your request ({wake_remaining:.0f} s remaining)"
        elif state == "speaking":
            state_detail = "Leo speaking — microphone wake detection temporarily suppressed"
        elif state == "echo suppressed":
            state_detail = f"Speaker echo tail — wake detection suppressed ({float(suppression.get('echo_tail_remaining_s') or 0):.1f} s remaining)"
        return {"ok": True, "schema": "bx1.body.live_voice_observation.v2", "audio": {"available": live_available, "unavailable_reason": reason, "rms_dbfs": rms if live_available else None, "peak_dbfs": peak if live_available else None, "noise_floor_dbfs": noise, "threshold_dbfs": threshold, "gate_open": bool(live.get("gate_open")) if live_available else None, "state": display_state, "state_detail": state_detail[:240], "pipeline_state": state, "wake_phrase": str(runtime.get("last_wake_word") or "")[:48], "wake_timestamp": runtime.get("last_wake_at"), "wake_remaining_s": wake_remaining, "speaker_playback_active": bool(suppression.get("playback_active")), "echo_tail_remaining_s": suppression.get("echo_tail_remaining_s"), "last_failure_reason": rejection, "device": str(self.cfg.get("mic_device", "default")), "gain_db": float(self.cfg.get("mic_software_gain_db", 0.0)), "timestamp": sample_at, "age_seconds": age, "last_successful_update": sample_at}, "heartbeat": heartbeat, "recognition": {"latest_text": latest_text, "last_accepted_request": accepted_request, "last_discarded_audio": discarded_audio, "latest_reply": latest_reply, "engine": engine, "confidence": metrics.get("confidence"), "rejection_reason": rejection, "handoff": metrics.get("primary_stt_handoff", {}), "timestamp": runtime.get("updated_at")}, "settings": self._bx1_audio_bridge_settings(), "voice_settings": self.web_bx1_voice_settings(), "boundary": "Robot Body owns microphone capture, STT and speaker playback; BX1 OS receives bounded metadata only and never opens a device."}

    def _bx1_audio_bridge_settings(self) -> Dict[str, Any]:
        specs = {"mic_gain_db": ("mic_software_gain_db", -24.0, 36.0, 0.0, "dB"), "vad_threshold_dbfs": ("mic_noise_gate_dbfs", -90.0, -5.0, -48.0, "dBFS"), "minimum_speech_ms": ("stt_min_voiced_ms", 80, 3000, 280, "ms"), "end_silence_ms": ("stt_end_silence_ms", 250, 4000, 1350, "ms"), "wake_listen_timeout_s": ("wake_command_window_s", 3.0, 60.0, 12.0, "s")}
        return {name: {"current": self.cfg.get(key, default), "effective": self.cfg.get(key, default), "default": default, "minimum": low, "maximum": high, "unit": unit} for name, (key, low, high, default, unit) in specs.items()}

    def web_bx1_voice_settings(self) -> Dict[str, Any]:
        """Versioned, allowlisted voice configuration for BX1 OS only."""
        values = {
            "wake_phrases": self.get_wake_words(),
            "wake_listen_timeout_s": float(self.cfg.get("wake_command_window_s", 12.0)),
            "speech_end_timeout_ms": int(self.cfg.get("stt_end_silence_ms", 1350)),
            "noise_gate_dbfs": float(self.cfg.get("mic_noise_gate_dbfs", -48.0)),
            "noise_margin_db": float(self.cfg.get("stt_noise_margin_db", 6.0)),
            "adaptive_margin_db": float(self.cfg.get("stt_adaptive_margin_db", 8.0)),
            "speaker_echo_tail_ms": int(self.cfg.get("speaker_echo_tail_ms", 1500)),
            "stt_policy": str(self.cfg.get("stt_transcription_backend", "brain_faster_whisper")),
        }
        revision = hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return {
            "ok": True, "schema": "bx1.body.voice_settings.v1", "revision": revision,
            "updated_at": now_iso(), "effective": values,
            "limits": {
                "wake_phrases": {"minimum_count": 1, "maximum_count": 8, "maximum_length": 48},
                "wake_listen_timeout_s": {"minimum": 3.0, "maximum": 60.0},
                "speech_end_timeout_ms": {"minimum": 250, "maximum": 4000},
                "noise_gate_dbfs": {"minimum": -90.0, "maximum": -5.0},
                "noise_margin_db": {"minimum": 0.0, "maximum": 30.0},
                "adaptive_margin_db": {"minimum": 0.0, "maximum": 30.0},
                "speaker_echo_tail_ms": {"minimum": 250, "maximum": 5000},
                "stt_policy": {"allowed": ["brain_faster_whisper", "vosk"]},
            },
            "ownership": "Robot Body validates and atomically saves only these voice settings; BX1 OS never edits arbitrary configuration.",
        }

    def web_update_bx1_voice_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        requested = data.get("settings", data)
        if not isinstance(requested, dict):
            return {"ok": False, "error": "settings must be an object"}
        allowed = {"wake_phrases", "wake_listen_timeout_s", "speech_end_timeout_ms", "noise_gate_dbfs", "noise_margin_db", "adaptive_margin_db", "speaker_echo_tail_ms", "stt_policy"}
        unknown = set(requested) - allowed
        if unknown:
            return {"ok": False, "error": "unsupported voice setting: " + ", ".join(sorted(unknown))}
        candidate = self.web_bx1_voice_settings()["effective"]
        candidate.update({key: requested[key] for key in requested})
        phrases = candidate.get("wake_phrases")
        if not isinstance(phrases, list) or not (1 <= len(phrases) <= 8):
            return {"ok": False, "error": "wake_phrases must contain 1 to 8 phrases"}
        normalised: List[str] = []
        for phrase in phrases:
            if not isinstance(phrase, str):
                return {"ok": False, "error": "wake phrases must be text"}
            clean = " ".join(phrase.strip().lower().split())
            if not clean or len(clean) > 48:
                return {"ok": False, "error": "each wake phrase must contain 1 to 48 characters"}
            if clean not in normalised:
                normalised.append(clean)
        if not normalised:
            return {"ok": False, "error": "at least one distinct wake phrase is required"}
        numeric = {
            "wake_listen_timeout_s": (3.0, 60.0, float), "speech_end_timeout_ms": (250, 4000, int),
            "noise_gate_dbfs": (-90.0, -5.0, float), "noise_margin_db": (0.0, 30.0, float),
            "adaptive_margin_db": (0.0, 30.0, float), "speaker_echo_tail_ms": (250, 5000, int),
        }
        parsed: Dict[str, Any] = {"wake_phrases": normalised}
        for name, (low, high, convert) in numeric.items():
            try:
                value = convert(float(candidate[name]))
            except (TypeError, ValueError):
                return {"ok": False, "error": f"{name} must be numeric"}
            if not low <= value <= high:
                return {"ok": False, "error": f"{name} must be between {low} and {high}"}
            parsed[name] = value
        policy = str(candidate.get("stt_policy") or "").strip().lower()
        if policy not in {"brain_faster_whisper", "vosk"}:
            return {"ok": False, "error": "stt_policy is not supported by this Robot Body"}
        self.cfg.update({"wake_words": parsed["wake_phrases"], "wake_command_window_s": parsed["wake_listen_timeout_s"],
                         "stt_end_silence_ms": parsed["speech_end_timeout_ms"], "mic_noise_gate_dbfs": parsed["noise_gate_dbfs"],
                         "stt_noise_margin_db": parsed["noise_margin_db"], "stt_adaptive_margin_db": parsed["adaptive_margin_db"],
                         "speaker_echo_tail_ms": parsed["speaker_echo_tail_ms"], "stt_transcription_backend": policy})
        self._refresh_mic_monitor_settings()
        self.save_config_file()
        result = self.web_bx1_voice_settings()
        result["message"] = "Settings saved atomically by Robot Body. Active capture applies them on its next utterance."
        return result

    def web_update_bx1_audio_bridge_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Allowlisted, atomic configuration update for the OS audio bridge."""
        mapping = {"mic_gain_db": ("mic_software_gain_db", -24.0, 36.0, 0.0, float), "vad_threshold_dbfs": ("mic_noise_gate_dbfs", -90.0, -5.0, -48.0, float), "minimum_speech_ms": ("stt_min_voiced_ms", 80, 3000, 280, int), "end_silence_ms": ("stt_end_silence_ms", 250, 4000, 1350, int), "wake_listen_timeout_s": ("wake_command_window_s", 3.0, 60.0, 12.0, float)}
        requested = data.get("settings", data)
        if not isinstance(requested, dict): return {"ok": False, "error": "settings must be an object"}
        for name, (key, low, high, default, converter) in mapping.items():
            if name not in requested: continue
            try: value = converter(float(requested[name]))
            except (TypeError, ValueError): return {"ok": False, "error": f"{name} must be numeric"}
            self.cfg[key] = max(low, min(high, value))
        self._refresh_mic_monitor_settings()
        self.save_config_file()  # write/replace: configuration is never partially written
        restart_required = bool(self.get_voice_runtime_snapshot().get("loop_active"))
        return {"ok": True, "settings": self._bx1_audio_bridge_settings(), "restart_required": restart_required, "restart_route": "Robot Body management service restart" if restart_required else "not required", "message": "Saved atomically. Active voice capture uses these values after the approved Robot Body restart when one is required."}

    def web_list_mic_devices(self) -> Dict[str, Any]:
        return self._get_cached_mic_devices(force=True)

    def web_list_playback_devices(self) -> Dict[str, Any]:
        try:
            return list_audio_playback_devices()
        except Exception as exc:
            return {"ok": False, "error": str(exc), "devices": []}

    def web_mic_sample_info(self) -> Dict[str, Any]:
        wav_path = str(self.last_mic_test_wav or "")
        path = Path(wav_path)
        exists = bool(wav_path and path.exists())
        analysis = analyse_wav_file(path, float(self.cfg.get("mic_software_gain_db", 0.0))) if exists else {"ok": False, "error": "No sample recorded yet"}
        diagnostics = analyse_wav_diagnostics(path, float(self.cfg.get("mic_software_gain_db", 0.0))) if exists else {"ok": False, "error": "No sample recorded yet"}
        return {
            "ok": True,
            "filename": wav_path,
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else 0,
            "analysis": analysis,
            "diagnostics": diagnostics,
            "mic": self.get_mic_settings(),
            "capture_devices": self._get_cached_mic_devices(force=False),
            "playback_devices": self.web_list_playback_devices(),
        }

    def web_record_mic_test(self, data: Dict[str, Any]) -> Dict[str, Any]:
        seconds = data.get("seconds", self.cfg.get("record_seconds", 5))
        device = str(data.get("mic_device", self.cfg.get("mic_device", "default"))).strip() or "default"
        sample_rate = int(self.cfg.get("sample_rate", 16000))
        try:
            sample_rate = int(float(data.get("sample_rate", sample_rate)))
        except Exception:
            pass
        path = str(Path(tempfile.gettempdir()) / "bx1_mic_test.wav")
        self.last_mic_test_wav = path
        self.web_log("system", f"Recording microphone test sample: {seconds}s from {device}")
        t0 = time.perf_counter()
        started_at = now_iso()
        report: Dict[str, Any]
        self.manual_audio_capture_requested.set()
        got_lock = False
        monitor_was_running = bool(self.mic_monitor.is_running())
        try:
            got_lock = self.audio_capture_lock.acquire(timeout=max(2.0, float(seconds) + 2.0))
            if not got_lock:
                report = {
                    "ok": False,
                    "error": "microphone is busy - live wake listener or another diagnostic is using the capture device",
                    "hint": "Disable live microphone/STT briefly, or wait for the current wake-listen sample to finish.",
                }
            else:
                if monitor_was_running:
                    self.mic_monitor.stop()
                    time.sleep(0.2)
                report = record_microphone_sample(
                    path,
                    device=device,
                    sample_rate=sample_rate,
                    seconds=float(seconds),
                    channels=int(self.cfg.get("mic_channels", 1)),
                )
        finally:
            if got_lock:
                try:
                    self.audio_capture_lock.release()
                except RuntimeError:
                    pass
            self.manual_audio_capture_requested.clear()
            if monitor_was_running:
                try:
                    self._refresh_mic_monitor_settings()
                    self.mic_monitor.start()
                except Exception:
                    pass
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        report["started_at"] = started_at
        report["completed_at"] = now_iso()
        report["elapsed_ms"] = elapsed_ms
        if report.get("ok"):
            # Re-run analysis with the configured software gain so the diagnostic
            # level matches the live level meter the user sees in the web page.
            report["analysis_gain_adjusted"] = analyse_wav_file(path, float(self.cfg.get("mic_software_gain_db", 0.0)))
            analysis = report.get("analysis_gain_adjusted") or report.get("analysis") or {}
            self.web_log("system", f"Mic sample recorded. RMS {analysis.get('rms_dbfs')} dBFS, peak {analysis.get('peak_dbfs')} dBFS")
        else:
            self.web_log("error", f"Mic sample failed: {report.get('error') or report.get('stderr')}")
        return {"ok": bool(report.get("ok")), "recording": report, "filename": path, "sample_info": self.web_mic_sample_info()}

    def web_play_mic_test(self, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = data or {}
        device = str(data.get("playback_device", self.cfg.get("mic_playback_device", "default"))).strip() or "default"
        self.cfg["mic_playback_device"] = device
        report = self.play_body_audio_file(
            self.last_mic_test_wav, device=device, text="microphone test playback",
            tag="mic-test", backend="mic-test",
        )
        self.web_log("system" if report.get("ok") else "error", "Mic test playback " + ("complete" if report.get("ok") else "failed"))
        return {"ok": bool(report.get("ok")), "playback": report, "filename": self.last_mic_test_wav, "sample_info": self.web_mic_sample_info()}

    def web_mic_stt_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        model_path = str(data.get("vosk_model_path", self.cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15"))).strip()
        wav_path = str(self.last_mic_test_wav or "")
        vosk_import_ok = importlib.util.find_spec("vosk") is not None
        model_exists = bool(model_path and Path(model_path).is_dir())
        wav_exists = bool(wav_path and Path(wav_path).exists())
        wav_size = Path(wav_path).stat().st_size if wav_exists else 0
        error = ""
        if not vosk_import_ok:
            error = "Vosk Python module is not installed in the Python environment running BX1."
        elif not model_exists:
            error = f"Vosk model folder not found: {model_path}"
        elif not wav_exists:
            error = "No recorded WAV sample found yet. Press Record Test Sample first."
        wav_analysis = analyse_wav_file(wav_path, float(self.cfg.get("mic_software_gain_db", 0.0))) if wav_exists else {"ok": False, "error": "sample missing"}
        return {
            "ok": True,
            "status": {
                "vosk_import_ok": vosk_import_ok,
                "model_exists": model_exists,
                "model_path": model_path,
                "wav_exists": wav_exists,
                "wav_path": wav_path,
                "wav_size_bytes": wav_size,
                "wav_analysis": wav_analysis,
                "python_executable": sys.executable,
                "ready": bool(vosk_import_ok and model_exists and wav_exists),
                "error": error,
            },
        }

    def web_stt_mic_test(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Transcribe the most recent web-recorded sample. This needs the vosk
        # Python module and a model folder, but does not need sounddevice.
        model_path = str(data.get("vosk_model_path", self.cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15"))).strip()
        status = self.web_mic_stt_status({"vosk_model_path": model_path}).get("status", {})
        if not bool(status.get("ready")):
            result = {"ok": False, "error": str(status.get("error") or "STT is not ready"), "text": ""}
            self.web_log("error", f"STT test failed: {result.get('error')}")
            return {"ok": False, "stt": result, "status": status, "filename": self.last_mic_test_wav, "sample_info": self.web_mic_sample_info()}
        result = transcribe_wav_with_vosk(self.last_mic_test_wav, model_path, int(self.cfg.get("sample_rate", 16000)))
        if result.get("ok"):
            text = str(result.get("text", "")).strip()
            self.web_log("user" if text else "system", f"STT test: {text or '[no speech recognised]'}")
        else:
            self.web_log("error", f"STT test failed: {result.get('error')}")
        return {"ok": bool(result.get("ok")), "stt": result, "status": status, "filename": self.last_mic_test_wav, "sample_info": self.web_mic_sample_info()}

    def get_voice_settings(self) -> Dict[str, Any]:
        return {
            "voice_enabled": bool(self.cfg.get("voice_enabled", False)),
            "input_mode": str(self.cfg.get("input_mode", "keyboard")),
            "voice_backend": str(self.cfg.get("voice_backend", "vosk")),
            "stt_transcription_backend": str(self.cfg.get("stt_transcription_backend", "brain_faster_whisper")),
            "brain_stt_enabled": bool(self.cfg.get("brain_stt_enabled", True)),
            "brain_stt_timeout_s": int(self.cfg.get("brain_stt_timeout_s", 12)),
            "brain_stt_fallback_to_vosk": bool(self.cfg.get("brain_stt_fallback_to_vosk", True)),
            "defer_local_vosk_when_brain_enabled": bool(self.cfg.get("stt_defer_local_vosk_when_brain_enabled", True)),
            "brain_stt_language": str(self.cfg.get("brain_stt_language", "en")),
            "vosk_model_path": str(self.cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15")),
            "vosk_model_tier": "improved" if "0.22-lgraph" in str(self.cfg.get("vosk_model_path", "")) else "small",
            "better_model_installer": "INSTALL_BX1_BETTER_STT_MODEL.sh",
            "record_seconds": int(self.cfg.get("record_seconds", 5)),
            "sample_rate": int(self.cfg.get("sample_rate", 16000)),
            "capture_method": str(self.cfg.get("stt_capture_method", "alsa")),
            "endpointing_enabled": bool(self.cfg.get("stt_endpointing_enabled", True)),
            "start_timeout_s": float(self.cfg.get("stt_start_timeout_s", 8.0)),
            "max_utterance_s": float(self.cfg.get("stt_max_utterance_s", 20.0)),
            "end_silence_ms": int(self.cfg.get("stt_end_silence_ms", 1350)),
            "pre_roll_ms": int(self.cfg.get("stt_pre_roll_ms", 700)),
            "wake_words": self.get_wake_words(),
            "stt_ready": bool(getattr(self.stt, "ready", False)) if self.stt is not None else False,
            "local_vosk_ready": bool(getattr(self.stt, "vosk_ready", False)) if self.stt is not None else False,
            "stt_error": (str(getattr(self.stt, "error", "")) if self.stt is not None and not bool(getattr(self.stt, "ready", False)) else ""),
            "local_vosk_error": (str(getattr(self.stt, "error", "")) if self.stt is not None and not bool(getattr(self.stt, "vosk_ready", False)) else ""),
            "runtime": self.get_voice_runtime_snapshot(),
        }

    def web_update_voice_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
            try:
                return max(lo, min(hi, int(float(value))))
            except Exception:
                return default

        input_mode = str(data.get("input_mode", self.cfg.get("input_mode", "keyboard"))).strip().lower()
        if input_mode not in {"keyboard", "voice", "voice_or_keyboard", "both"}:
            input_mode = "keyboard"
        self.cfg["voice_enabled"] = bool(data.get("voice_enabled", self.cfg.get("voice_enabled", False)))
        self.cfg["input_mode"] = input_mode
        self.cfg["voice_backend"] = str(data.get("voice_backend", self.cfg.get("voice_backend", "vosk"))).strip() or "vosk"
        self.cfg["vosk_model_path"] = str(data.get("vosk_model_path", self.cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15"))).strip()
        self.cfg["record_seconds"] = clamp_int(data.get("record_seconds", self.cfg.get("record_seconds", 5)), 2, 20, 5)
        self.cfg["sample_rate"] = clamp_int(data.get("sample_rate", self.cfg.get("sample_rate", 16000)), 8000, 48000, 16000)
        raw_wake = data.get("wake_words", self.cfg.get("wake_words", []))
        if isinstance(raw_wake, str):
            wake_words = [w.strip().lower() for w in raw_wake.replace(",", "\n").splitlines() if w.strip()]
        else:
            wake_words = [str(w).strip().lower() for w in raw_wake if str(w).strip()]
        # Wake words are local STT routing only. Do not automatically inject the
        # Brain robot name or body ID here.
        self.cfg["wake_words"] = wake_words or ["hello", "hey", "robot"]
        self.robot_profile["wake_words"] = list(self.cfg["wake_words"])
        self.save_robot_profile_file()
        self.save_config_file()
        if self.cfg["voice_enabled"] and input_mode in {"voice", "voice_or_keyboard", "both"}:
            # A running diagnostic level meter holds the ALSA device open. Stop it
            # automatically when the user enables normal always-listening mode.
            try:
                if self.mic_monitor.is_running():
                    self.mic_monitor.stop()
            finally:
                self.manual_audio_capture_requested.clear()
            self.stt = VoskSpeechToText(self.build_audio_config())
            if self.stt.ready:
                if not any(t.name == "bx1-voice" and t.is_alive() for t in self.threads):
                    self.set_voice_runtime("starting", "Starting live microphone/STT loop...", loop_active=False, last_error="")
                    self._start_thread("voice", self.voice_loop)
                else:
                    self.set_voice_runtime("listening", "Listening for wake word...", loop_active=True, last_error="")
            else:
                self.set_voice_runtime("error", f"STT not ready: {self.stt.error}", loop_active=False, last_error=str(self.stt.error))
        else:
            self.set_voice_runtime("disabled", "Live microphone/STT loop is disabled.", loop_active=False)
        self.web_log("system", "Voice/STT settings saved")
        return {"ok": True, "voice": self.get_voice_settings(), "saved_to": str(CONFIG_PATH)}

    def get_thinking_cue_settings(self) -> Dict[str, Any]:
        # The Brain owns reply wording/personality; the robot body owns immediate
        # local feedback because only it knows exactly when the microphone, TTS
        # generation and physical speaker are active.
        return {
            "owner": "robot_body_runtime",
            "thinking_cues_enabled": bool(self.cfg.get("thinking_cues_enabled", True)),
            "thinking_cue_speak": bool(self.cfg.get("thinking_cue_speak", True)),
            "thinking_feedback_enabled": bool(self.cfg.get("thinking_feedback_enabled", True)),
            "thinking_feedback_delay_s": float(self.cfg.get("thinking_feedback_delay_s", 0.18)),
            "thinking_cue_delay_s": float(self.cfg.get("thinking_cue_delay_s", 1.1)),
            "thinking_cue_repeat_s": float(self.cfg.get("thinking_cue_repeat_s", 8.0)),
            "thinking_cue_max_per_reply": int(self.cfg.get("thinking_cue_max_per_reply", 5)),
            "thinking_cue_total_timeout_s": float(self.cfg.get("thinking_cue_total_timeout_s", 65.0)),
            "thinking_cue_use_main_tts_when_uncached": bool(self.cfg.get("thinking_cue_use_main_tts_when_uncached", False)),
            "voice_command_immediate_cue_enabled": bool(self.cfg.get("voice_command_immediate_cue_enabled", True)),
            "local_voice_cue_cache_enabled": bool(self.cfg.get("local_voice_cue_cache_enabled", True)),
            "local_cue_fallback_espeak_enabled": bool(self.cfg.get("local_cue_fallback_espeak_enabled", True)),
            "stt_pause_during_tts": bool(self.cfg.get("stt_pause_during_tts", True)),
            "stt_post_tts_guard_s": float(self.cfg.get("stt_post_tts_guard_s", 1.25)),
            "conversation_followup_window_s": float(self.cfg.get("conversation_followup_window_s", 45.0)),
            "wake_command_window_s": float(self.cfg.get("wake_command_window_s", 12.0)),
            "wake_voice_ack_enabled": bool(self.cfg.get("wake_voice_ack_enabled", True)),
            "voice_feedback_audio_enabled": bool(self.cfg.get("voice_feedback_audio_enabled", True)),
            "voice_feedback_led_enabled": bool(self.cfg.get("voice_feedback_led_enabled", True)),
            "voice_feedback_tone_level": float(self.cfg.get("voice_feedback_tone_level", 0.30)),
            "wake_ack_phrase": str(self.cfg.get("wake_ack_phrase", "Yes John?")),
            "sleep_ack_phrase": str(self.cfg.get("sleep_ack_phrase", "Going quiet.")),
            "sleep_phrases": self.cfg.get("sleep_phrases", DEFAULT_SLEEP_PHRASES),
            "thinking_cues": self.get_thinking_cues(),
            "local_voice_cues": self.local_voice_cue_status(),
        }

    def web_update_thinking_cue_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
            try:
                return max(lo, min(hi, float(value)))
            except Exception:
                return default
        def clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
            try:
                return max(lo, min(hi, int(float(value))))
            except Exception:
                return default
        raw_cues = data.get("thinking_cues", self.cfg.get("thinking_cues", []))
        if isinstance(raw_cues, str):
            cues = [c.strip() for c in raw_cues.splitlines() if c.strip()]
        else:
            cues = [str(c).strip() for c in raw_cues if str(c).strip()]

        # v10.35 keeps local acknowledgement/progress timing as a body responsibility.
        # This removes the previous ownership branch that silently forced every
        # audible cue off whenever the desktop Brain owned personality wording.
        self.cfg["brain_controls_thinking_cues"] = False
        self.cfg["thinking_cues_enabled"] = bool(data.get("thinking_cues_enabled", self.cfg.get("thinking_cues_enabled", True)))
        self.cfg["thinking_cue_speak"] = bool(data.get("thinking_cue_speak", self.cfg.get("thinking_cue_speak", True)))
        self.cfg["thinking_cue_delay_s"] = clamp_float(data.get("thinking_cue_delay_s", self.cfg.get("thinking_cue_delay_s", 1.1)), 0.4, 30.0, 1.1)
        self.cfg["thinking_cue_repeat_s"] = clamp_float(data.get("thinking_cue_repeat_s", self.cfg.get("thinking_cue_repeat_s", 8.0)), 3.0, 60.0, 8.0)
        self.cfg["thinking_cue_max_per_reply"] = clamp_int(data.get("thinking_cue_max_per_reply", self.cfg.get("thinking_cue_max_per_reply", 5)), 0, 8, 5)
        self.cfg["thinking_cue_total_timeout_s"] = clamp_float(data.get("thinking_cue_total_timeout_s", self.cfg.get("thinking_cue_total_timeout_s", 65.0)), 10.0, 120.0, 65.0)
        self.cfg["thinking_cue_use_main_tts_when_uncached"] = bool(data.get("thinking_cue_use_main_tts_when_uncached", self.cfg.get("thinking_cue_use_main_tts_when_uncached", False)))
        self.cfg["voice_command_immediate_cue_enabled"] = bool(data.get("voice_command_immediate_cue_enabled", self.cfg.get("voice_command_immediate_cue_enabled", True)))
        self.cfg["thinking_feedback_enabled"] = bool(data.get("thinking_feedback_enabled", self.cfg.get("thinking_feedback_enabled", True)))
        self.cfg["thinking_feedback_delay_s"] = clamp_float(data.get("thinking_feedback_delay_s", self.cfg.get("thinking_feedback_delay_s", 0.18)), 0.05, 5.0, 0.18)
        self.cfg["local_voice_cue_cache_enabled"] = bool(data.get("local_voice_cue_cache_enabled", self.cfg.get("local_voice_cue_cache_enabled", True)))
        self.cfg["local_cue_fallback_espeak_enabled"] = bool(data.get("local_cue_fallback_espeak_enabled", self.cfg.get("local_cue_fallback_espeak_enabled", True)))
        self.cfg["stt_pause_during_tts"] = bool(data.get("stt_pause_during_tts", self.cfg.get("stt_pause_during_tts", True)))
        self.cfg["stt_post_tts_guard_s"] = clamp_float(data.get("stt_post_tts_guard_s", self.cfg.get("stt_post_tts_guard_s", 1.25)), 0.0, 10.0, 1.25)
        self.cfg["conversation_followup_window_s"] = clamp_float(data.get("conversation_followup_window_s", self.cfg.get("conversation_followup_window_s", 45.0)), 5.0, 600.0, 45.0)
        self.cfg["wake_command_window_s"] = clamp_float(data.get("wake_command_window_s", self.cfg.get("wake_command_window_s", 12.0)), 3.0, 60.0, 12.0)
        self.cfg["wake_voice_ack_enabled"] = bool(data.get("wake_voice_ack_enabled", self.cfg.get("wake_voice_ack_enabled", True)))
        self.cfg["voice_feedback_audio_enabled"] = bool(data.get("voice_feedback_audio_enabled", self.cfg.get("voice_feedback_audio_enabled", True)))
        self.cfg["voice_feedback_led_enabled"] = bool(data.get("voice_feedback_led_enabled", self.cfg.get("voice_feedback_led_enabled", True)))
        self.cfg["voice_feedback_tone_level"] = clamp_float(data.get("voice_feedback_tone_level", self.cfg.get("voice_feedback_tone_level", 0.30)), 0.02, 0.50, 0.30)
        self.cfg["wake_ack_phrase"] = str(data.get("wake_ack_phrase", self.cfg.get("wake_ack_phrase", "Yes John?")) or "Yes John?").strip()
        self.cfg["sleep_ack_phrase"] = str(data.get("sleep_ack_phrase", self.cfg.get("sleep_ack_phrase", "Going quiet.")) or "Going quiet.").strip()
        self.cfg["thinking_cues"] = cues or self.get_thinking_cues()
        self.save_config_file()
        self.web_log("system", "Local acknowledgement and thinking cue settings saved")
        return {"ok": True, "thinking_cues": self.get_thinking_cue_settings(), "saved_to": str(CONFIG_PATH)}

    def get_performance_snapshot(self) -> Dict[str, Any]:
        with self.metrics_lock:
            perf = dict(self.performance)
        perf["tts_queue_pending"] = int(getattr(self.tts, "_speak_queue").qsize()) if hasattr(self.tts, "_speak_queue") else None
        perf["brain_base_url"] = self.brain.base_url
        perf["telemetry_interval_s"] = float(self.cfg.get("telemetry_interval_s", 1.0))
        perf["chat_timeout_s"] = int(self.cfg.get("chat_timeout_s", 180))
        return perf


    def get_hardware_settings(self) -> Dict[str, Any]:
        self.hardware_registry = normalise_hardware_registry(getattr(self, "hardware_registry", self.cfg.get("hardware_registry", self.cfg.get("hardware_map", {}))))
        self.hardware_map = legacy_hardware_map_from_registry(self.hardware_registry)
        self.cfg["hardware_registry"] = self.hardware_registry
        self.cfg["hardware_map"] = self.hardware_map
        return {
            "hardware_registry": self.hardware_registry,
            "hardware_map": self.hardware_map,
            "mcu_config_packet": flatten_hardware_registry_for_mcu(self.hardware_registry),
            "notes": [
                "v10 hardware registry: one addressable LED bus can serve many logical zones.",
                "LED zone addresses are human-friendly: LED 1 means first physical pixel; firmware converts to zero-based.",
                "Yaw uses one servo. Pitch and roll are mixed into the left/right push-pull gimbal servos with configurable gains and signs.",
                "Modulino Movement is treated as I2C/Qwiic sensor. RS485 wheels are reserved for a future drive bus.",
            ],
        }

    def web_update_hardware_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        raw = data.get("hardware_registry", data.get("hardware_map", data))
        self.hardware_registry = normalise_hardware_registry(raw)
        self.hardware_map = legacy_hardware_map_from_registry(self.hardware_registry)
        self.cfg["hardware_registry"] = self.hardware_registry
        self.cfg["hardware_map"] = self.hardware_map
        self.save_config_file()
        self.web_log("system", "hardware registry saved", {"hardware_registry": self.hardware_registry})
        return {"ok": True, "hardware": self.get_hardware_settings(), "saved_to": str(CONFIG_PATH)}

    def web_apply_hardware_to_mcu(self) -> Dict[str, Any]:
        action = flatten_hardware_registry_for_mcu(self.hardware_registry)
        action["source"] = "web_hardware_settings"
        res = self.hardware.send_action(action)
        self.web_log("system", "hardware registry applied to MCU", {"ok": res.ok, "value": res.value, "error": res.error, "action": action})
        return {
            "ok": bool(res.ok),
            "action": action,
            "bridge_ok": bool(res.ok),
            "bridge_value": res.value,
            "bridge_error": res.error,
        }

    def web_test_hardware_device(self, data: Dict[str, Any]) -> Dict[str, Any]:
        role = str(data.get("role", "") or data.get("device", "") or data.get("zone", "")).strip().lower()
        value = data.get("value")

        # Local bounded integer parser for LED address fields. v10.22 called a
        # helper that only existed inside other methods, causing /api/hardware_test
        # to return HTTP 500 for led_range and preventing the colour picker from
        # physically changing the selected LEDs.
        def bounded_int(raw: Any, lo: int, hi: int, default: int) -> int:
            try:
                parsed = int(float(raw))
            except Exception:
                parsed = int(default)
            return max(int(lo), min(int(hi), parsed))

        settings = self.get_hardware_settings()
        reg = settings["hardware_registry"]
        servos = reg.get("servos", {})
        def servo_value(key: str, raw: Any) -> float:
            cfg = servos.get(key, {})
            try:
                val = float(raw if raw is not None else cfg.get("home_deg", 0))
            except Exception:
                val = float(cfg.get("home_deg", 0))
            lo = float(cfg.get("min_deg", -45))
            hi = float(cfg.get("max_deg", 45))
            if hi < lo:
                lo, hi = hi, lo
            return max(lo, min(hi, val))

        yaw_home = servo_value("head_yaw", servos.get("head_yaw", {}).get("home_deg", 0))
        kin = reg.get("head_kinematics", {}) if isinstance(reg.get("head_kinematics"), dict) else {}
        pitch_home = float(kin.get("pitch_home_deg", 0.0))
        roll_home = float(kin.get("roll_home_deg", 0.0))

        def parse_hex_rgb(value: Any) -> tuple[int, int, int]:
            raw = str(value or "").strip()
            if raw.startswith("#"):
                raw = raw[1:]
            if len(raw) == 3:
                raw = "".join(ch * 2 for ch in raw)
            if len(raw) == 6:
                try:
                    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
                except Exception:
                    pass
            named = {
                "off": (0, 0, 0),
                "red": (255, 0, 0),
                "green": (0, 255, 0),
                "blue": (0, 0, 255),
                "cyan": (0, 255, 255),
                "amber": (255, 128, 0),
                "yellow": (255, 180, 0),
                "orange": (255, 90, 0),
                "purple": (128, 0, 255),
                "pink": (255, 0, 128),
                "white": (255, 255, 255),
                "soft_white": (255, 220, 120),
            }
            return named.get(raw.lower(), (0, 255, 255))


        if role in {"head_yaw", "yaw"}:
            action = {"type": "set_head_pose", "args": {"yaw_deg": servo_value("head_yaw", value), "pitch_deg": pitch_home, "roll_deg": roll_home}}
        elif role in {"head_pitch", "pitch"}:
            try:
                logical = float(value if value is not None else pitch_home)
            except Exception:
                logical = pitch_home
            logical = max(float(kin.get("pitch_min_deg", -10.0)), min(float(kin.get("pitch_max_deg", 10.0)), logical))
            action = {"type": "set_head_pose", "args": {"yaw_deg": yaw_home, "pitch_deg": logical, "roll_deg": roll_home}}
        elif role in {"head_roll", "roll", "tilt"}:
            try:
                logical = float(value if value is not None else roll_home)
            except Exception:
                logical = roll_home
            logical = max(float(kin.get("roll_min_deg", -10.0)), min(float(kin.get("roll_max_deg", 10.0)), logical))
            action = {"type": "set_head_pose", "args": {"yaw_deg": yaw_home, "pitch_deg": pitch_home, "roll_deg": logical}}
        elif role in {"mouth_speech_test", "talking_led_test", "mouth_talking"}:
            self.apply_led_state("speaking", source="web_mouth_test", include_mouth=False, force=True)
            self.start_mouth_audio_animation({"text": "BX1 mouth LED talking animation test", "audio_profile": {}})
            def stop_test() -> None:
                time.sleep(4.0)
                self.stop_mouth_audio_animation()
                self.apply_led_state("idle", source="web_mouth_test_complete", include_mouth=False, force=True)
            threading.Thread(target=stop_test, name="bx1-mouth-test", daemon=True).start()
            return {"ok": True, "role": role, "message": "Mouth talking animation running for four seconds."}
        elif role in {"led_range", "led_pixel", "pixel", "paint_led"}:
            start_led = bounded_int(data.get("start_led", data.get("led", 1)), 1, 500, 1)
            end_led = bounded_int(data.get("end_led", start_led), 1, 500, start_led)
            if end_led < start_led:
                start_led, end_led = end_led, start_led
            r, g, b = parse_hex_rgb(data.get("colour_hex", data.get("color_hex", data.get("colour", data.get("color", "#00ffff")))))
            brightness = clamp_float_value(data.get("brightness", 0.25), 0.0, 1.0, 0.25)
            action = {"type": "set_led_range", "args": {"start_led": start_led, "end_led": end_led, "r": r, "g": g, "b": b, "brightness": brightness}}
        elif role in {"eyes", "eye"}:
            colour = str(data.get("colour", "blue"))
            action = {"type": "set_led_zone", "args": {"zone": "left_eye", "secondary_zone": "right_eye", "colour": colour, "brightness": float(data.get("brightness", 0.25))}}
        elif role in {"mouth", "left_eye", "right_eye", "chest", "status"}:
            action = {"type": "set_led_zone", "args": {"zone": role, "colour": str(data.get("colour", "cyan")), "brightness": float(data.get("brightness", 0.25))}}
        elif role in {"all_leds", "all"}:
            action = {"type": "set_led_zone", "args": {"zone": "all", "colour": str(data.get("colour", "cyan")), "brightness": float(data.get("brightness", 0.20))}}
        elif role in {"stop", "centre", "center"}:
            action = {"type": "set_head_pose", "args": {"yaw_deg": yaw_home, "pitch_deg": pitch_home, "roll_deg": roll_home}}
        else:
            return {"ok": False, "error": f"unknown hardware role: {role}"}

        with self.command_lock:
            ack = self.execute_actions([action], original_message="web_hardware_test")
        items = ack.get("items", []) if isinstance(ack, dict) else []
        command_ok = bool(items) and all(bool(item.get("ok")) and bool(item.get("executed")) for item in items if isinstance(item, dict))
        errors = []
        for item in items:
            if not isinstance(item, dict) or (bool(item.get("ok")) and bool(item.get("executed"))):
                continue
            errors.append(str(item.get("bridge_error") or item.get("reason") or "hardware command was not executed"))
        self.web_log("system" if command_ok else "error", f"hardware test: {role}", {"action": action, "ack": ack, "errors": errors})
        return {"ok": command_ok, "action": action, "ack": ack, "errors": errors}

    def web_update_manual_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if bool(data.get("clear", False)):
            self.manual_debug_state = {"enabled": False}
            self.web_log("system", "manual debug context cleared")
            return {"ok": True, "manual_debug_state": self.manual_debug_state}
        allowed = {
            "enabled", "pitch_deg", "roll_deg", "yaw_deg", "front_distance_mm",
            "battery_v", "location_label", "visual_context",
        }
        self.manual_debug_state = {k: data.get(k) for k in allowed if k in data}
        self.manual_debug_state["enabled"] = bool(data.get("enabled", True))
        self.web_log("system", "manual debug context updated")
        return {"ok": True, "manual_debug_state": self.manual_debug_state}

    def web_manual_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(action, dict):
            return {"ok": False, "error": "action must be a JSON object"}
        with self.command_lock:
            ack = self.execute_actions([action], original_message="web_manual_action")
            if ack["actions_seen"]:
                try:
                    self.brain.command_ack(ack)
                except Exception as exc:
                    self.web_log("error", f"manual action ack failed: {exc}")
            self.web_log("system", f"manual action: {action.get('type', 'unknown')}")
            return {"ok": True, "ack": ack}

    def web_console_command(self, command: str) -> Dict[str, Any]:
        command = str(command or "").strip()
        if not command:
            return {"ok": False, "error": "empty command"}
        with self.command_lock:
            handled = self.handle_console_command(command)
        self.web_log("system", f"console command: {command}")
        return {"ok": bool(handled), "handled": bool(handled), "command": command}

    def tick(self) -> None:
        time.sleep(0.25)

    def stop(self) -> None:
        self.stop_event.set()
        if self.web_server is not None:
            try:
                self.web_server.stop()
            except Exception:
                pass


SERVICE: Optional[BX1RobotBodyService] = None


def run_service_standalone() -> None:
    global SERVICE
    cfg = load_config()
    print(f"[body] config: {CONFIG_PATH}")
    print(f"[body] web: {cfg.get('web_host', '0.0.0.0')}:{cfg.get('web_port', 8088)}")
    if cfg.get("brain_base_url"):
        print(f"[body] brain: {cfg.get('brain_base_url')}")
    print("[body] identity/personality: managed by Robot Brain, not Arduino body client")
    SERVICE = BX1RobotBodyService(cfg)

    def handle_signal(signum, frame):  # type: ignore[no-untyped-def]
        print(f"[bx1] signal {signum}; stopping")
        if SERVICE:
            SERVICE.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    SERVICE.start()
    while SERVICE and not SERVICE.stop_event.is_set():
        SERVICE.tick()


def app_lab_loop() -> None:
    global SERVICE
    if SERVICE is None:
        SERVICE = BX1RobotBodyService(load_config())
        SERVICE.start()
    SERVICE.tick()


if __name__ == "__main__":
    # In App Lab, App.run keeps the Python side integrated with Bridge.
    # Over SSH/standalone, we simply run the same service directly.
    if APP_LAB_AVAILABLE and App is not None and "--standalone" not in sys.argv:
        App.run(user_loop=app_lab_loop)
    else:
        run_service_standalone()
