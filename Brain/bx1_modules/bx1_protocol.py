"""BX1 protocol helpers.

This module defines the high-level contract between the desktop Brain App and the
physical BX1 body.  It deliberately keeps motor/servo details behind safe action
packets so an LLM never gets direct real-time control of balance or wheel torque.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

TELEMETRY_SCHEMA = "bx1.telemetry.v1"
VISION_FRAME_SCHEMA = "bx1.vision_frame.v1"
ACTION_SCHEMA = "bx1.actions.v1"
LOCATION_SCHEMA = "bx1.location.v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "ok"}:
        return True
    if text in {"0", "false", "no", "n", "off", "fault", "bad"}:
        return False
    return default


def normalise_location(raw: Any = None) -> Dict[str, Any]:
    """Return a stable location object without assuming GPS is fitted."""
    if not isinstance(raw, Mapping):
        raw = {}
    loc = dict(raw)
    loc.setdefault("schema", LOCATION_SCHEMA)
    loc.setdefault("mode", loc.get("source", "unknown"))
    loc.setdefault("updated_at", now_iso())
    # Keep common values if present; do not invent coordinates.
    for key in ("site", "room", "zone", "dock", "map", "source"):
        if key in raw and raw[key] is not None:
            loc[key] = raw[key]
    for key in ("lat", "latitude", "lon", "longitude", "alt_m", "map_x_m", "map_y_m", "heading_deg"):
        if key in raw:
            loc[key] = _as_float(raw.get(key), None)
    return loc


def normalise_body_state(raw_state: Any, source: str = "api") -> Dict[str, Any]:
    """Convert arbitrary robot telemetry into the BX1 v1 telemetry envelope."""
    if isinstance(raw_state, Mapping):
        raw = dict(raw_state)
    else:
        raw = {"value": raw_state}

    pitch = _as_float(raw.get("pitch_deg", raw.get("pitch")), 0.0)
    roll = _as_float(raw.get("roll_deg", raw.get("roll")), 0.0)
    yaw = _as_float(raw.get("yaw_deg", raw.get("yaw")), None)

    fallen = _as_bool(raw.get("fallen", raw.get("fall_detected")), False)
    estop = _as_bool(raw.get("estop", raw.get("e_stop", raw.get("emergency_stop"))), False)
    safety_ok = _as_bool(raw.get("safety_ok", raw.get("safe")), True) and not fallen and not estop

    location = raw.get("location") if isinstance(raw.get("location"), Mapping) else {}
    state: Dict[str, Any] = {
        "schema": TELEMETRY_SCHEMA,
        "robot_id": str(raw.get("robot_id") or raw.get("id") or "BX1"),
        "source": source or str(raw.get("source") or "api"),
        "received_at": raw.get("received_at") or now_iso(),
        "timestamp_robot": raw.get("timestamp") or raw.get("timestamp_linux") or raw.get("received_at_robot"),
        "safety": {
            "ok": bool(safety_ok),
            "fallen": bool(fallen),
            "estop": bool(estop),
            "mode": raw.get("mode", raw.get("state", "unknown")),
        },
        "power": {
            "battery_v": _as_float(raw.get("battery_v", raw.get("battery")), None),
            "battery_percent": _as_float(raw.get("battery_percent", raw.get("battery_pct")), None),
            "charging": raw.get("charging"),
        },
        "pose": {
            "pitch_deg": pitch,
            "roll_deg": roll,
            "yaw_deg": yaw,
        },
        "motion": {
            "left_speed": _as_float(raw.get("left_speed", raw.get("wheel_left")), None),
            "right_speed": _as_float(raw.get("right_speed", raw.get("wheel_right")), None),
            "linear_mps": _as_float(raw.get("linear_mps"), None),
            "angular_dps": _as_float(raw.get("angular_dps"), None),
        },
        "sensors": {
            "imu_ok": _as_bool(raw.get("imu_ok", raw.get("imu")), bool(raw.get("mcu_ok", False))),
            "mcu_ok": _as_bool(raw.get("mcu_ok"), False),
            "front_distance_mm": _as_float(raw.get("front_distance_mm", raw.get("distance_front_mm", raw.get("distance_mm"))), None),
            "obstacle": _as_bool(raw.get("obstacle"), False),
            "camera": raw.get("camera") or raw.get("camera_status"),
            "mic": raw.get("mic") or raw.get("microphone"),
            "temperature_c": _as_float(raw.get("temperature_c", raw.get("temperature")), None),
        },
        "location": normalise_location(location),
        "raw": raw,
    }

    # Backwards-compatible top-level fields used by the earlier Tk/ttk app and
    # the UNO Q validator.
    state["safety_ok"] = state["safety"]["ok"]
    state["fallen"] = state["safety"]["fallen"]
    state["mode"] = state["safety"].get("mode")
    state["pitch_deg"] = state["pose"].get("pitch_deg")
    state["roll_deg"] = state["pose"].get("roll_deg")
    state["yaw_deg"] = state["pose"].get("yaw_deg")
    if state["sensors"].get("front_distance_mm") is not None:
        state["front_distance_mm"] = state["sensors"].get("front_distance_mm")
    return state


def summarise_body_state(state: Any) -> str:
    if not state:
        return "No BX1 body telemetry received yet."
    if not isinstance(state, Mapping):
        return str(state)[:900]
    s = normalise_body_state(state, source=str(state.get("source", "summary"))) if state.get("schema") != TELEMETRY_SCHEMA else dict(state)
    parts: List[str] = []
    safety = s.get("safety", {}) if isinstance(s.get("safety"), Mapping) else {}
    pose = s.get("pose", {}) if isinstance(s.get("pose"), Mapping) else {}
    sensors = s.get("sensors", {}) if isinstance(s.get("sensors"), Mapping) else {}
    power = s.get("power", {}) if isinstance(s.get("power"), Mapping) else {}
    loc = s.get("location", {}) if isinstance(s.get("location"), Mapping) else {}
    parts.append(f"safe={safety.get('ok')}")
    if safety.get("fallen"):
        parts.append("fallen=True")
    if safety.get("estop"):
        parts.append("estop=True")
    for key, label in (("pitch_deg", "pitch"), ("roll_deg", "roll"), ("yaw_deg", "yaw")):
        if pose.get(key) is not None:
            parts.append(f"{label}={pose.get(key)}°")
    if power.get("battery_v") is not None:
        parts.append(f"battery={power.get('battery_v')}V")
    if power.get("battery_percent") is not None:
        parts.append(f"battery={power.get('battery_percent')}%")
    if sensors.get("front_distance_mm") is not None:
        parts.append(f"front={sensors.get('front_distance_mm')}mm")
    if sensors.get("camera") is not None:
        parts.append(f"camera={sensors.get('camera')}")
    if loc:
        loc_text = loc.get("room") or loc.get("zone") or loc.get("site") or loc.get("mode")
        if loc_text:
            parts.append(f"location={loc_text}")
    return "; ".join(parts)[:900]


def body_state_prompt_context(state: Any) -> str:
    if not state:
        return ""
    s = normalise_body_state(state, source="prompt") if not (isinstance(state, Mapping) and state.get("schema") == TELEMETRY_SCHEMA) else dict(state)
    return (
        "BX1 BODY TELEMETRY - use this as current physical context, do not invent missing sensor values.\n"
        f"Summary: {summarise_body_state(s)}\n"
        "Full packet:\n" + json.dumps(s, ensure_ascii=False, indent=2)[:5000]
    )


def build_action_schema(max_drive_speed_mps: float = 0.25, max_drive_duration_s: float = 1.5) -> Dict[str, Any]:
    return {
        "version": ACTION_SCHEMA,
        "execute_only_if_ok": True,
        "supported_actions": {
            "stop_motion": {"description": "Immediately stop wheel motion."},
            "drive": {"description": "Short guarded wheel movement.", "args": {"linear_mps": "float", "angular_dps": "float", "duration_s": "float"}},
            "set_head_pose": {"description": "Set logical camera/head yaw, pitch and roll in degrees. The body mixes pitch/roll into the two physical gimbal servos.", "args": {"yaw_deg": "float", "pitch_deg": "float", "roll_deg": "float"}},
            "set_eye_led": {"description": "Set both eye LED zones.", "args": {"colour": "colour name or #RRGGBB", "brightness": "0..1", "duration_s": "float"}},
            "set_led_zone": {"description": "Set a named addressable LED zone.", "args": {"zone": "mouth|left_eye|right_eye|eyes|chest|status|all", "colour": "colour name or #RRGGBB", "brightness": "0..1"}},
            "play_tone": {"description": "Small acknowledgement chirp.", "args": {"tone": "string", "duration_s": "float"}},
        },
        "limits": {
            "max_drive_speed_mps": float(max_drive_speed_mps),
            "max_drive_duration_s": float(max_drive_duration_s),
            "head_yaw_deg": [-60, 60],
            "head_pitch_deg": [-20, 20],
            "head_roll_deg": [-20, 20],
        },
    }


def body_state_allows_motion(body_state: Any) -> bool:
    if not isinstance(body_state, Mapping):
        return True
    s = normalise_body_state(body_state, source="safety") if body_state.get("schema") != TELEMETRY_SCHEMA else body_state
    safety = s.get("safety", {}) if isinstance(s.get("safety"), Mapping) else {}
    sensors = s.get("sensors", {}) if isinstance(s.get("sensors"), Mapping) else {}
    if safety.get("ok") is False or safety.get("fallen") or safety.get("estop"):
        return False
    if sensors.get("obstacle"):
        return False
    dist = sensors.get("front_distance_mm")
    try:
        if dist is not None and float(dist) < 220:
            return False
    except Exception:
        pass
    return True


def suggest_safe_actions(
    user_message: str,
    body_state: Any,
    *,
    max_drive_speed_mps: float = 0.25,
    max_drive_duration_s: float = 1.5,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Deterministic high-level action generation.

    This is intentionally simple.  It translates obvious human requests into a
    bounded packet and lets the body service validate again before execution.
    """
    msg = (user_message or "").lower()
    actions: List[Dict[str, Any]] = []
    now_id = datetime.now().strftime("%Y%m%d%H%M%S")

    def add(action_type: str, args: Dict[str, Any], reason: str) -> None:
        actions.append({
            "id": f"act_{now_id}_{len(actions)+1}",
            "schema": ACTION_SCHEMA,
            "type": action_type,
            "args": args,
            "reason": reason,
            "dry_run": bool(dry_run),
            "created_at": now_iso(),
        })

    if any(term in msg for term in ("stop", "freeze", "hold position", "do not move")):
        add("stop_motion", {}, "Stop or hold-position requested.")
        return actions

    motion_requested = any(term in msg for term in ("drive", "move", "roll", "forward", "backward", "reverse", "turn", "spin", "come here"))
    if motion_requested and not body_state_allows_motion(body_state):
        add("stop_motion", {}, "Wheel motion blocked by current body safety state, obstacle, or fall flag.")
        return actions

    max_speed = max(0.01, min(1.0, float(max_drive_speed_mps)))
    max_duration = max(0.1, min(10.0, float(max_drive_duration_s)))
    if any(term in msg for term in ("forward", "come here", "move ahead", "drive ahead", "roll ahead")):
        add("drive", {"linear_mps": max_speed, "angular_dps": 0.0, "duration_s": max_duration}, "Short forward movement requested.")
    elif any(term in msg for term in ("backward", "reverse", "back up", "move back")):
        add("drive", {"linear_mps": -max_speed * 0.7, "angular_dps": 0.0, "duration_s": min(max_duration, 1.0)}, "Short reverse movement requested.")
    elif "turn left" in msg:
        add("drive", {"linear_mps": 0.0, "angular_dps": -35.0, "duration_s": min(max_duration, 0.8)}, "Guarded left turn requested.")
    elif "turn right" in msg:
        add("drive", {"linear_mps": 0.0, "angular_dps": 35.0, "duration_s": min(max_duration, 0.8)}, "Guarded right turn requested.")

    if ("look left" in msg or "head left" in msg) and "tilt" not in msg and "cock" not in msg:
        add("set_head_pose", {"yaw_deg": -35.0, "pitch_deg": 0.0, "roll_deg": 0.0}, "Camera/head look-left requested.")
    elif ("look right" in msg or "head right" in msg) and "tilt" not in msg and "cock" not in msg:
        add("set_head_pose", {"yaw_deg": 35.0, "pitch_deg": 0.0, "roll_deg": 0.0}, "Camera/head look-right requested.")
    elif "look up" in msg or "head up" in msg:
        add("set_head_pose", {"yaw_deg": 0.0, "pitch_deg": -10.0, "roll_deg": 0.0}, "Camera/head look-up requested.")
    elif "look down" in msg or "head down" in msg:
        add("set_head_pose", {"yaw_deg": 0.0, "pitch_deg": 10.0, "roll_deg": 0.0}, "Camera/head look-down requested.")
    elif "look at me" in msg or "look forward" in msg or "face me" in msg:
        add("set_head_pose", {"yaw_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0}, "Camera/head centre requested.")

    if "tilt left" in msg or "cock your head left" in msg or ("tilt" in msg and "left" in msg and ("head" in msg or "neck" in msg)):
        add("set_head_pose", {"yaw_deg": 0.0, "pitch_deg": 0.0, "roll_deg": -10.0}, "Logical head roll-left requested; the body will mix both gimbal servos.")
    elif "tilt right" in msg or "cock your head right" in msg or ("tilt" in msg and "right" in msg and ("head" in msg or "neck" in msg)):
        add("set_head_pose", {"yaw_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 10.0}, "Logical head roll-right requested; the body will mix both gimbal servos.")

    # LED requests accept both common names and an exact web-style #RRGGBB value.
    # The body owns the physical LED map, so the Brain only selects a logical zone.
    colour_map = {
        "blue": "blue", "red": "red", "green": "green", "white": "white", "amber": "amber",
        "yellow": "yellow", "orange": "orange", "purple": "purple", "cyan": "cyan", "off": "off",
    }
    colour_match = re.search(r"#[0-9a-f]{6}\b", msg, flags=re.IGNORECASE)
    requested_colour: Optional[str] = colour_match.group(0).upper() if colour_match else None
    if requested_colour is None:
        for word, colour in colour_map.items():
            if re.search(rf"\b{re.escape(word)}\b", msg):
                requested_colour = colour
                break

    requested_zone: Optional[str] = None
    if "left eye" in msg:
        requested_zone = "left_eye"
    elif "right eye" in msg:
        requested_zone = "right_eye"
    elif "mouth" in msg:
        requested_zone = "mouth"
    elif "chest" in msg:
        requested_zone = "chest"
    elif "status" in msg:
        requested_zone = "status"
    elif "all lights" in msg or "all leds" in msg or "all led" in msg:
        requested_zone = "all"
    elif "eyes" in msg or "eye" in msg or "lights" in msg or "led" in msg:
        requested_zone = "eyes"

    if requested_colour is not None and requested_zone is not None:
        brightness = 0.45 if requested_zone == "mouth" else 0.55 if requested_zone in {"eyes", "left_eye", "right_eye"} else 0.40
        add(
            "set_led_zone",
            {"zone": requested_zone, "colour": requested_colour, "brightness": brightness},
            f"{requested_zone.replace('_', ' ').title()} LED colour requested: {requested_colour}.",
        )

    if "chirp" in msg or "beep" in msg:
        add("play_tone", {"tone": "ack", "duration_s": 0.25}, "Tone requested.")

    return actions
