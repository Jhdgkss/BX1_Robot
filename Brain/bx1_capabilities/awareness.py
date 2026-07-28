from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


REMINDER_ACTIONS = {"create_reminder", "create_alarm", "set_reminder", "set_alarm"}


@dataclass(frozen=True)
class CapabilityAvailability:
    capability_id: str
    state: str
    record: Any = None


@dataclass(frozen=True)
class ReminderRequest:
    trigger_text: str
    reminder_text: str

    @property
    def complete(self) -> bool:
        return bool(self.trigger_text and self.reminder_text)


class PendingReminderState:
    def __init__(self, timeout_seconds: float = 180.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.trigger_text = ""
        self.created_at = 0.0

    def set(self, trigger_text: str) -> None:
        self.trigger_text = trigger_text
        self.created_at = time.time()

    def get(self) -> str:
        if self.trigger_text and time.time() - self.created_at <= self.timeout_seconds:
            return self.trigger_text
        self.clear()
        return ""

    def clear(self) -> None:
        self.trigger_text = ""
        self.created_at = 0.0


def reminder_availability(records: list[Any]) -> CapabilityAvailability:
    for record in records:
        actions = {action.action_id for action in record.manifest.actions}
        if actions & REMINDER_ACTIONS:
            state = "enabled" if record.state == "installed" else "disabled"
            return CapabilityAvailability(record.manifest.capability_id, state, record)
    return CapabilityAvailability("reminder_clock", "missing")


def capability_status_target(message: str) -> str:
    text = " ".join(str(message or "").lower().split())
    if not text:
        return ""
    if re.search(r"\b(what|which) capabilities do you have\b|\bwhat can you do\b", text):
        return "all"
    status_lead = re.search(r"\b(are you capable of|can you|do you have|are you connected to|do you support)\b", text)
    if not status_lead:
        return ""
    if re.search(r"\b(?:remind|alert|notify) me (?:to|at|in)\b|\bwake me (?:at|in)\b", text):
        return ""
    # A concrete time or reminder payload makes this an action request, not a status question.
    if re.search(r"\b\d{1,2}:\d{2}\b|\b(?:in|at|tomorrow|today)\s+\w+", text) and re.search(r"\b(remind|reminder|alarm|alert|notify)\b", text):
        return ""
    if re.search(r"\b(remind|reminders?|alarms?|wake me|alert|notify)\b", text):
        return "reminder_clock"
    if "spotify" in text or re.search(r"\b(control|play).*(music|song)\b", text):
        return "spotify"
    if "octoprint" in text or "printer" in text:
        return "octoprint"
    if re.search(r"\b(move|turn).*(head)\b", text):
        return "head_movement"
    if "temperature sensor" in text:
        return "temperature_sensor"
    return ""


_REMINDER_REQUEST = re.compile(
    r"\b(remind me|set (?:me )?(?:an? )?reminder|create (?:me )?(?:an? )?reminder|"
    r"set (?:me )?(?:an? )?alarm|wake me|alert me|notify me|can you remind me|can you set (?:an? )?(?:reminder|alarm))\b",
    re.I,
)


def parse_reminder_request(message: str) -> Optional[ReminderRequest]:
    text = " ".join(str(message or "").strip().split())
    if not _REMINDER_REQUEST.search(text):
        return None
    trigger = ""
    for pattern in (
        r"\b(?:at|for)\s+(\d{1,2}:\d{2})\b",
        r"\b(in\s+\d+\s+(?:minute|minutes|hour|hours|day|days))\b",
        r"\b(tomorrow(?:\s+at\s+\d{1,2}(?::\d{2})?)?)\b",
        r"\b(today(?:\s+at\s+\d{1,2}(?::\d{2})?)?)\b",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            trigger = match.group(1).strip()
            break
    reminder_text = ""
    content = re.search(r"\bto\s+(.+)$", text, re.I)
    if content:
        reminder_text = content.group(1).strip(" .?!")
    return ReminderRequest(trigger, reminder_text)


def reminder_management_request(message: str) -> tuple[str, Dict[str, Any]]:
    text = " ".join(str(message or "").strip().lower().split())
    if re.search(r"\b(what|which|list|show).*(reminders?|alarms?)\b|\bdo i have any reminders\b", text):
        return "list_reminders", {}
    identifier = re.search(r"\b([a-f0-9]{12,64})\b", text)
    reminder_id = identifier.group(1) if identifier else ""
    if reminder_id and re.search(r"\bcancel\b", text):
        return "cancel_reminder", {"reminder_id": reminder_id}
    if reminder_id and re.search(r"\bsnooze\b", text):
        minutes = re.search(r"\b(\d+)\s+minutes?\b", text)
        return "snooze_reminder", {"reminder_id": reminder_id, "minutes": int(minutes.group(1)) if minutes else 10}
    if reminder_id and re.search(r"\bdismiss\b", text):
        return "dismiss_reminder", {"reminder_id": reminder_id}
    return "", {}


def confirmed_reminder_result(result: Any) -> bool:
    if not bool(getattr(result, "ok", False)):
        return False
    data = getattr(result, "data", {}) or {}
    reminder_id = data.get("reminder_id") or data.get("id")
    trigger = data.get("trigger_datetime") or data.get("confirmed_trigger_datetime") or data.get("scheduled_for")
    if not reminder_id or not trigger:
        return False
    try:
        datetime.fromisoformat(str(trigger).replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def safe_capability_summary(capability_manager: Any, integration_manager: Any, body_state: Any = None) -> Dict[str, Any]:
    reminder = reminder_availability(capability_manager.list_records())
    integrations: Dict[str, Any] = {}
    for item in integration_manager.all():
        integrations[item.integration_id] = {
            "installed": True,
            "enabled": bool(item.enabled),
            "status": item.status.value,
        }
    return {
        "reminder_clock": {"installed": reminder.state != "missing", "enabled": reminder.state == "enabled"},
        "spotify": integrations.get("spotify", {"installed": False, "enabled": False, "status": "unavailable"}),
        "octoprint": integrations.get("octoprint", {"installed": False, "enabled": False, "status": "unavailable"}),
        "robot_body": {"connected": bool(body_state)},
    }


_REMINDER_SUCCESS_CLAIM = re.compile(
    r"\b(i can (?:do that|set|create)|i support|i(?:'ll| will) remind|reminder (?:is )?set|"
    r"i(?:'ll| will) set (?:the|a) reminder|alarm (?:is )?set|scheduled|i(?:'ve| have) set (?:the|a) reminder)\b",
    re.I,
)


def guard_capability_claims(message: str, reply: str, summary: Dict[str, Any], *, verified_action: bool = False) -> str:
    text = str(reply or "")
    reminder_related = bool(re.search(r"\b(remind|reminders?|alarms?|wake me|alert|notify)\b", str(message or ""), re.I))
    reminder_enabled = bool((summary.get("reminder_clock") or {}).get("enabled"))
    if reminder_related and _REMINDER_SUCCESS_CLAIM.search(text) and not (reminder_enabled and verified_action):
        if (summary.get("reminder_clock") or {}).get("installed"):
            return "I have a Reminder Clock capability, but it is disabled. Shall I enable it?"
        return "Not currently. I don't have an enabled reminder capability. I can design a Reminder Clock tool for you. Shall I prepare it?"
    if re.search(r"\b(playback|music) (?:has )?(?:started|is playing)|\bi started playback\b", text, re.I) and not verified_action:
        return "I don't have a confirmed Spotify playback result, so I shouldn't claim that playback started."
    if re.search(r"\bprinter (?:is )?paused|\bi paused the print\b", text, re.I) and not verified_action:
        return "I don't have a confirmed OctoPrint result, so I shouldn't claim that the printer was paused."
    return text
