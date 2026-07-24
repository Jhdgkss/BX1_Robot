"""Safe behaviour scripting for the BX1 Robot Brain Workshop.

The behaviour format is deliberately declarative.  It can describe approved
head and LED actions, pauses and local speech cues, but it cannot import Python,
run shell commands, install packages or address hardware directly.  The body
controller remains responsible for servo limits, balance and final execution.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BEHAVIOUR_FORMAT = "bx1.behaviour.v1"
ALLOWED_STEP_TYPES = {"head_pose", "led_range", "wait", "speech"}
ALLOWED_PERMISSIONS = {"head.move", "leds.mouth", "speech.say"}
STEP_PERMISSION = {
    "head_pose": "head.move",
    "led_range": "leds.mouth",
    "speech": "speech.say",
}

DEFAULT_LIMITS: Dict[str, Any] = {
    "max_steps": 40,
    "max_total_duration_ms": 15000,
    "max_step_duration_ms": 3000,
    "max_head_yaw_deg": 20.0,
    "max_head_pitch_deg": 12.0,
    "max_head_roll_deg": 10.0,
    "max_led_index": 99,
    "max_led_brightness": 0.25,
    "max_speech_chars": 220,
}


class BehaviourValidationError(ValueError):
    """Raised when a behaviour cannot be safely normalised."""

    def __init__(self, errors: Iterable[str], warnings: Optional[Iterable[str]] = None) -> None:
        self.errors = [str(item) for item in errors if str(item).strip()]
        self.warnings = [str(item) for item in (warnings or []) if str(item).strip()]
        super().__init__("; ".join(self.errors) or "Behaviour validation failed.")


@dataclass(frozen=True)
class BehaviourValidationResult:
    behaviour: Dict[str, Any]
    warnings: List[str]
    total_duration_ms: int
    action_count: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    return slug[:64]


def _as_number(value: Any, label: str, errors: List[str]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be a number.")
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        errors.append(f"{label} must be finite.")
        return 0.0
    return number


def _as_int(value: Any, label: str, errors: List[str]) -> int:
    number = _as_number(value, label, errors)
    if int(number) != number:
        errors.append(f"{label} must be a whole number.")
    return int(number)


def _bounded(number: float, low: float, high: float, label: str, errors: List[str]) -> float:
    if number < low or number > high:
        errors.append(f"{label} must be between {low:g} and {high:g}; received {number:g}.")
    return max(low, min(high, number))


def normalise_colour(value: Any) -> Tuple[str, int, int, int]:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        raise ValueError("colour_hex must be in #RRGGBB format.")
    text = text.upper()
    return text, int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)


def extract_behaviour_json(text: str) -> Dict[str, Any]:
    """Extract one JSON object from raw text or a fenced JSON block."""
    raw = str(text or "").strip()
    if not raw:
        raise BehaviourValidationError(["The behaviour editor is empty."])

    fenced = re.findall(r"```(?:json|javascript|js)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    candidates = fenced + [raw]
    decoder = json.JSONDecoder()
    parse_errors: List[str] = []

    for candidate in candidates:
        candidate = candidate.strip()
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
            parse_errors.append("The decoded JSON value was not an object.")
            continue
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {exc.lineno}, column {exc.colno}: {exc.msg}")

        # Models sometimes add prose before/after an otherwise valid object.
        start = candidate.find("{")
        while start >= 0:
            try:
                value, _ = decoder.raw_decode(candidate[start:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
            start = candidate.find("{", start + 1)

    detail = parse_errors[-1] if parse_errors else "No JSON object was found."
    raise BehaviourValidationError([f"Could not read a behaviour JSON object: {detail}"])


def limits_from_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    limits = dict(DEFAULT_LIMITS)
    cfg = cfg or {}
    mapping = {
        "workshop_behaviour_max_steps": "max_steps",
        "workshop_behaviour_max_total_duration_ms": "max_total_duration_ms",
        "workshop_behaviour_max_step_duration_ms": "max_step_duration_ms",
        "workshop_behaviour_max_head_yaw_deg": "max_head_yaw_deg",
        "workshop_behaviour_max_head_pitch_deg": "max_head_pitch_deg",
        "workshop_behaviour_max_head_roll_deg": "max_head_roll_deg",
        "workshop_behaviour_max_led_index": "max_led_index",
        "workshop_behaviour_max_led_brightness": "max_led_brightness",
        "workshop_behaviour_max_speech_chars": "max_speech_chars",
    }
    for cfg_key, limit_key in mapping.items():
        if cfg_key in cfg and cfg[cfg_key] not in (None, ""):
            limits[limit_key] = cfg[cfg_key]
    return limits


def validate_behaviour(data: Dict[str, Any], limits: Optional[Dict[str, Any]] = None) -> BehaviourValidationResult:
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(data, dict):
        raise BehaviourValidationError(["A behaviour must be a JSON object."])

    fmt = str(data.get("format") or BEHAVIOUR_FORMAT).strip()
    if fmt != BEHAVIOUR_FORMAT:
        errors.append(f"format must be {BEHAVIOUR_FORMAT!r}.")

    display_name = str(data.get("name") or "").strip()
    slug = slugify_name(display_name)
    if not display_name:
        errors.append("name is required.")
    elif not slug:
        errors.append("name must contain at least one letter or number.")

    description = re.sub(r"\s+", " ", str(data.get("description") or "").strip())[:500]
    if not description:
        errors.append("description is required.")

    level = _as_int(data.get("permission_level", 2), "permission_level", errors)
    if level not in (1, 2):
        errors.append("permission_level must be 1 or 2 in behaviour format v1.")
        level = 2

    raw_permissions = data.get("permissions") or []
    if not isinstance(raw_permissions, list):
        errors.append("permissions must be a JSON list.")
        raw_permissions = []
    permissions = []
    for item in raw_permissions:
        permission = str(item or "").strip()
        if not permission:
            continue
        if permission not in ALLOWED_PERMISSIONS:
            errors.append(f"Unsupported permission {permission!r}.")
            continue
        if permission not in permissions:
            permissions.append(permission)

    raw_triggers = data.get("trigger_phrases") or []
    if not isinstance(raw_triggers, list):
        errors.append("trigger_phrases must be a JSON list.")
        raw_triggers = []
    trigger_phrases = []
    for item in raw_triggers[:12]:
        phrase = re.sub(r"\s+", " ", str(item or "").strip())[:100]
        if phrase and phrase.lower() not in {p.lower() for p in trigger_phrases}:
            trigger_phrases.append(phrase)

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        errors.append("steps must be a non-empty JSON list.")
        raw_steps = []
    max_steps = int(limits["max_steps"])
    if len(raw_steps) > max_steps:
        errors.append(f"A behaviour may contain at most {max_steps} steps.")

    steps: List[Dict[str, Any]] = []
    total_duration = 0
    action_count = 0
    required_permissions: List[str] = []

    for index, raw_step in enumerate(raw_steps[:max_steps], start=1):
        prefix = f"steps[{index - 1}]"
        if not isinstance(raw_step, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        kind = str(raw_step.get("type") or "").strip().lower()
        if kind not in ALLOWED_STEP_TYPES:
            errors.append(f"{prefix}.type {kind!r} is not supported. Allowed: {', '.join(sorted(ALLOWED_STEP_TYPES))}.")
            continue

        permission = STEP_PERMISSION.get(kind)
        if permission and permission not in required_permissions:
            required_permissions.append(permission)

        note = re.sub(r"\s+", " ", str(raw_step.get("note") or "").strip())[:180]
        step: Dict[str, Any] = {"type": kind}
        if note:
            step["note"] = note

        if kind == "head_pose":
            yaw = _bounded(
                _as_number(raw_step.get("yaw_deg", 0.0), f"{prefix}.yaw_deg", errors),
                -float(limits["max_head_yaw_deg"]),
                float(limits["max_head_yaw_deg"]),
                f"{prefix}.yaw_deg",
                errors,
            )
            pitch = _bounded(
                _as_number(raw_step.get("pitch_deg", 0.0), f"{prefix}.pitch_deg", errors),
                -float(limits["max_head_pitch_deg"]),
                float(limits["max_head_pitch_deg"]),
                f"{prefix}.pitch_deg",
                errors,
            )
            roll = _bounded(
                _as_number(raw_step.get("roll_deg", 0.0), f"{prefix}.roll_deg", errors),
                -float(limits["max_head_roll_deg"]),
                float(limits["max_head_roll_deg"]),
                f"{prefix}.roll_deg",
                errors,
            )
            duration = _as_int(raw_step.get("duration_ms", 500), f"{prefix}.duration_ms", errors)
            duration = int(_bounded(duration, 100, int(limits["max_step_duration_ms"]), f"{prefix}.duration_ms", errors))
            step.update({"yaw_deg": round(yaw, 3), "pitch_deg": round(pitch, 3), "roll_deg": round(roll, 3), "duration_ms": duration})
            total_duration += duration
            action_count += 1

        elif kind == "led_range":
            start_led = _as_int(raw_step.get("start_led", 1), f"{prefix}.start_led", errors)
            end_led = _as_int(raw_step.get("end_led", start_led), f"{prefix}.end_led", errors)
            max_led = int(limits["max_led_index"])
            start_led = int(_bounded(start_led, 0, max_led, f"{prefix}.start_led", errors))
            end_led = int(_bounded(end_led, 0, max_led, f"{prefix}.end_led", errors))
            if end_led < start_led:
                errors.append(f"{prefix}.end_led must be greater than or equal to start_led.")
                start_led, end_led = min(start_led, end_led), max(start_led, end_led)
            try:
                colour_hex, _, _, _ = normalise_colour(raw_step.get("colour_hex", "#00D9FF"))
            except ValueError as exc:
                errors.append(f"{prefix}.{exc}")
                colour_hex = "#00D9FF"
            brightness = _bounded(
                _as_number(raw_step.get("brightness", 0.15), f"{prefix}.brightness", errors),
                0.0,
                float(limits["max_led_brightness"]),
                f"{prefix}.brightness",
                errors,
            )
            duration = _as_int(raw_step.get("duration_ms", 400), f"{prefix}.duration_ms", errors)
            duration = int(_bounded(duration, 0, int(limits["max_step_duration_ms"]), f"{prefix}.duration_ms", errors))
            step.update({
                "start_led": start_led,
                "end_led": end_led,
                "colour_hex": colour_hex,
                "brightness": round(brightness, 3),
                "duration_ms": duration,
            })
            total_duration += duration
            action_count += 1

        elif kind == "wait":
            duration = _as_int(raw_step.get("duration_ms", 500), f"{prefix}.duration_ms", errors)
            duration = int(_bounded(duration, 50, int(limits["max_step_duration_ms"]), f"{prefix}.duration_ms", errors))
            step["duration_ms"] = duration
            total_duration += duration

        elif kind == "speech":
            text = re.sub(r"\s+", " ", str(raw_step.get("text") or "").strip())
            if not text:
                errors.append(f"{prefix}.text is required.")
            max_chars = int(limits["max_speech_chars"])
            if len(text) > max_chars:
                errors.append(f"{prefix}.text may contain at most {max_chars} characters.")
                text = text[:max_chars]
            step["text"] = text
            # Speech time is estimated for preview only. The Brain's TTS owns playback.
            estimated = max(400, min(5000, int(len(text.split()) * 360))) if text else 0
            step["estimated_duration_ms"] = estimated
            total_duration += estimated

        steps.append(step)

    for permission in required_permissions:
        if permission not in permissions:
            errors.append(f"Permission {permission!r} is required by the selected steps.")
    for permission in permissions:
        if permission not in required_permissions:
            warnings.append(f"Permission {permission!r} is declared but not used by any step.")

    max_total = int(limits["max_total_duration_ms"])
    if total_duration > max_total:
        errors.append(f"Estimated behaviour duration is {total_duration} ms; the limit is {max_total} ms.")

    if level == 1 and "head.move" in permissions:
        # Autonomous level remains deliberately conservative.
        max_yaw = max((abs(float(step.get("yaw_deg", 0))) for step in steps if step.get("type") == "head_pose"), default=0)
        max_pitch = max((abs(float(step.get("pitch_deg", 0))) for step in steps if step.get("type") == "head_pose"), default=0)
        max_roll = max((abs(float(step.get("roll_deg", 0))) for step in steps if step.get("type") == "head_pose"), default=0)
        if max_yaw > 8 or max_pitch > 6 or max_roll > 5:
            errors.append("permission_level 1 head movements are limited to yaw ±8°, pitch ±6° and roll ±5°. Use level 2 for larger supervised motion.")

    if errors:
        raise BehaviourValidationError(errors, warnings)

    normalised = {
        "format": BEHAVIOUR_FORMAT,
        "name": slug,
        "display_name": display_name[:100],
        "description": description,
        "permission_level": level,
        "permissions": permissions,
        "trigger_phrases": trigger_phrases,
        "steps": steps,
        "estimated_duration_ms": int(total_duration),
        "action_count": int(action_count),
    }
    return BehaviourValidationResult(normalised, warnings, int(total_duration), int(action_count))


def compile_behaviour_actions(behaviour: Dict[str, Any], *, dry_run: bool = False, limits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compile safe steps into the existing BX1 action packet vocabulary.

    ``wait`` and ``speech`` remain runner instructions.  Motion and LED actions
    include sequencing metadata.  Older body clients may ignore that metadata,
    but will still receive only familiar, bounded action types.
    """
    result = validate_behaviour(behaviour, limits=limits)
    normalised = result.behaviour
    actions: List[Dict[str, Any]] = []
    runner_steps: List[Dict[str, Any]] = []
    elapsed_before_ms = 0

    for sequence, step in enumerate(normalised["steps"], start=1):
        kind = step["type"]
        runner_step = {**step, "sequence": sequence, "offset_ms": elapsed_before_ms}
        runner_steps.append(runner_step)
        if kind == "head_pose":
            actions.append({
                "action_id": uuid.uuid4().hex,
                "type": "set_head_pose",
                "args": {
                    "yaw_deg": step["yaw_deg"],
                    "pitch_deg": step["pitch_deg"],
                    "roll_deg": step["roll_deg"],
                },
                "source": "bx1_behaviour",
                "behaviour": normalised["name"],
                "sequence": sequence,
                "offset_ms": elapsed_before_ms,
                "delay_after_ms": int(step.get("duration_ms", 0)),
                "dry_run": bool(dry_run),
            })
        elif kind == "led_range":
            _, red, green, blue = normalise_colour(step["colour_hex"])
            actions.append({
                "action_id": uuid.uuid4().hex,
                "type": "set_led_range",
                "args": {
                    "start_led": step["start_led"],
                    "end_led": step["end_led"],
                    "r": red,
                    "g": green,
                    "b": blue,
                    "brightness": step["brightness"],
                },
                "source": "bx1_behaviour",
                "behaviour": normalised["name"],
                "sequence": sequence,
                "offset_ms": elapsed_before_ms,
                "delay_after_ms": int(step.get("duration_ms", 0)),
                "dry_run": bool(dry_run),
            })
        if kind in {"head_pose", "led_range", "wait"}:
            elapsed_before_ms += int(step.get("duration_ms", 0))
        elif kind == "speech":
            elapsed_before_ms += int(step.get("estimated_duration_ms", 0))

    return {
        "ok": True,
        "format": BEHAVIOUR_FORMAT,
        "behaviour": normalised,
        "actions": actions,
        "runner_steps": runner_steps,
        "dry_run": bool(dry_run),
        "estimated_duration_ms": result.total_duration_ms,
        "warnings": result.warnings,
        "sequencing_note": (
            "offset_ms and delay_after_ms are supplied for paced execution. "
            "A body client that does not yet implement behaviour timing may execute compatible actions immediately."
        ),
    }


def format_behaviour_preview(behaviour: Dict[str, Any], warnings: Optional[Iterable[str]] = None) -> str:
    result = validate_behaviour(behaviour)
    item = result.behaviour
    lines = [
        f"VALID · {item['display_name']} ({item['name']})",
        f"Format: {item['format']}",
        f"Permission level: {item['permission_level']}",
        f"Permissions: {', '.join(item['permissions']) or 'none'}",
        f"Steps: {len(item['steps'])} · Body actions: {item['action_count']} · Estimated duration: {item['estimated_duration_ms'] / 1000:.2f} s",
        "",
    ]
    for index, step in enumerate(item["steps"], start=1):
        kind = step["type"]
        if kind == "head_pose":
            detail = f"head yaw={step['yaw_deg']:+g}° pitch={step['pitch_deg']:+g}° roll={step['roll_deg']:+g}° over {step['duration_ms']} ms"
        elif kind == "led_range":
            detail = f"LED {step['start_led']}–{step['end_led']} {step['colour_hex']} brightness={step['brightness']:.2f} for {step['duration_ms']} ms"
        elif kind == "wait":
            detail = f"wait {step['duration_ms']} ms"
        else:
            detail = f"say: {step['text']}"
        lines.append(f"{index:02d}. {detail}")
    all_warnings = [*result.warnings, *list(warnings or [])]
    if all_warnings:
        lines.extend(["", "WARNINGS:"])
        lines.extend(f"• {warning}" for warning in all_warnings)
    lines.extend([
        "",
        "Safety: declarative script only; no Python, shell, package install or direct hardware access.",
        "The body controller retains balance, range, emergency-stop and final execution authority.",
    ])
    return "\n".join(lines)


def example_behaviour() -> Dict[str, Any]:
    return {
        "format": BEHAVIOUR_FORMAT,
        "name": "curious_look",
        "description": "A small curious head tilt with a cyan mouth-light cue, followed by a return to centre.",
        "permission_level": 2,
        "permissions": ["head.move", "leds.mouth", "speech.say"],
        "trigger_phrases": ["show me your curious look", "run curious look"],
        "steps": [
            {"type": "led_range", "start_led": 1, "end_led": 1, "colour_hex": "#00D9FF", "brightness": 0.15, "duration_ms": 350},
            {"type": "head_pose", "yaw_deg": 7, "pitch_deg": -3, "roll_deg": 4, "duration_ms": 650},
            {"type": "wait", "duration_ms": 500},
            {"type": "speech", "text": "Hmm. Interesting."},
            {"type": "head_pose", "yaw_deg": 0, "pitch_deg": 0, "roll_deg": 0, "duration_ms": 650},
            {"type": "led_range", "start_led": 1, "end_led": 1, "colour_hex": "#000000", "brightness": 0.0, "duration_ms": 0},
        ],
    }


class BehaviourStore:
    """Profile-local installed behaviour store with revision backups."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.installed_dir = self.root / "installed"
        self.revisions_dir = self.root / "revisions"
        self.drafts_dir = self.root / "drafts"
        for folder in (self.root, self.installed_dir, self.revisions_dir, self.drafts_dir):
            folder.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        slug = slugify_name(name)
        if not slug:
            raise ValueError("Invalid behaviour name.")
        return self.installed_dir / f"{slug}.json"

    def list_installed(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for path in sorted(self.installed_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                result = validate_behaviour(payload)
                item = dict(result.behaviour)
                item.update({
                    "path": str(path),
                    "installed_at": str(payload.get("installed_at") or ""),
                    "updated_at": str(payload.get("updated_at") or ""),
                    "source_model": str(payload.get("source_model") or ""),
                })
                items.append(item)
            except Exception as exc:
                items.append({"name": path.stem, "display_name": path.stem, "path": str(path), "invalid": True, "error": str(exc)})
        return items

    def status(self) -> Dict[str, Any]:
        items = self.list_installed()
        return {
            "format": BEHAVIOUR_FORMAT,
            "root": str(self.root),
            "installed_count": len([item for item in items if not item.get("invalid")]),
            "invalid_count": len([item for item in items if item.get("invalid")]),
            "installed": items,
        }

    def load(self, name: str) -> Dict[str, Any]:
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Behaviour {slugify_name(name)!r} is not installed.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return validate_behaviour(payload).behaviour

    def install(
        self,
        behaviour: Dict[str, Any],
        *,
        source_model: str = "",
        source_task: str = "",
        approved_by: str = "John",
    ) -> Dict[str, Any]:
        result = validate_behaviour(behaviour)
        normalised = dict(result.behaviour)
        path = self._path(normalised["name"])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if path.exists():
            revision_folder = self.revisions_dir / normalised["name"]
            revision_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, revision_folder / f"{stamp}.json")
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                installed_at = str(previous.get("installed_at") or utc_now_iso())
            except Exception:
                installed_at = utc_now_iso()
        else:
            installed_at = utc_now_iso()

        stored = {
            **normalised,
            "installed_at": installed_at,
            "updated_at": utc_now_iso(),
            "source_model": str(source_model or ""),
            "source_task": str(source_task or "")[:2000],
            "approved_by": str(approved_by or "")[:100],
        }
        temporary = path.with_suffix(f".tmp.{uuid.uuid4().hex}.json")
        temporary.write_text(json.dumps(stored, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        return {"ok": True, "path": str(path), "behaviour": normalised, "warnings": result.warnings}

    def remove(self, name: str) -> Dict[str, Any]:
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(f"Behaviour {slugify_name(name)!r} is not installed.")
        archive_dir = self.revisions_dir / slugify_name(name)
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"removed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        shutil.copy2(path, archive_path)
        path.unlink()
        return {"ok": True, "removed": slugify_name(name), "archive_path": str(archive_path)}

    def save_draft(self, behaviour: Dict[str, Any], *, source_text: str = "") -> Path:
        result = validate_behaviour(behaviour)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.drafts_dir / f"{result.behaviour['name']}_{stamp}.json"
        payload = {**result.behaviour, "saved_at": utc_now_iso(), "source_text": source_text[:12000]}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def match_explicit_request(self, message: str) -> Optional[str]:
        text = re.sub(r"\s+", " ", str(message or "").strip())
        if not text:
            return None
        patterns = (
            (r"^/behaviou?r\s+(.+)$", False),
            (r"^(?:please\s+)?(?:run|perform|start|play|execute)\s+(?:the\s+)?behaviou?r\s+(.+?)[.!?]*$", False),
            (r"^(?:please\s+)?show\s+(?:me\s+)?(?:the\s+)?behaviou?r\s+(.+?)[.!?]*$", False),
            (r"^(?:please\s+)?(?:run|perform|start|play|execute|do|show\s+me)\s+(?:the\s+)?(.+?)(?:\s+(?:behaviou?r|routine|cue))?[.!?]*$", True),
        )
        requested = ""
        broad_request = False
        for pattern, is_broad in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if match:
                requested = match.group(1).strip(" .!?\t\r\n")
                broad_request = is_broad
                break
        if not requested:
            return None
        request_slug = slugify_name(requested)
        if self._path(request_slug).exists():
            return request_slug
        # Also permit the human-facing display name.
        for item in self.list_installed():
            if item.get("invalid"):
                continue
            if str(item.get("display_name") or "").strip().lower() == requested.lower():
                return str(item["name"])
            for phrase in item.get("trigger_phrases") or []:
                if str(phrase or "").strip().lower() == text.lower():
                    return str(item["name"])
                if requested and str(phrase or "").strip().lower() == requested.lower():
                    return str(item["name"])
        return None if broad_request else request_slug
