from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


TYPE_DEFINITIONS = {
    "tool": "A Brain-local function for scheduling, calculations, notes, or local data processing.",
    "integration": "A connection to an external service, API, calendar, database, or network system.",
    "behaviour": "A bounded robot character routine using movement, lights, pose, or speech.",
    "hardware": "A driver or interface for a physical sensor, motor, camera, microphone, display, or serial device.",
}


@dataclass(frozen=True)
class Classification:
    capability_type: str
    confidence: float
    explanation: str


@dataclass
class CapabilityProposal:
    capability_name: str
    capability_id: str
    capability_type: str
    purpose: str
    example_user_phrases: List[str]
    actions: List[str]
    required_permissions: List[str]
    forbidden_permissions: List[str]
    persistence_requirements: List[str]
    background_processing_requirements: List[str]
    ui_requirements: List[str]
    test_requirements: List[str]
    safety_constraints: List[str]
    reason_needed: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_capability(description: str) -> Classification:
    text = str(description or "").lower()
    scores = {"tool": 0, "integration": 0, "behaviour": 0, "hardware": 0}
    keywords = {
        "tool": ("remind", "reminder", "alarm", "timer", "calculate", "note", "schedule", "local data"),
        "integration": ("spotify", "octoprint", "api", "calendar", "home assistant", "database", "weather service", "external"),
        "behaviour": ("head movement", "dance", "celebrat", "greeting", "listening pose", "mouth light", "character routine"),
        "hardware": ("sensor", "motor", "servo", "camera", "microphone", "display", "serial", "driver", "gpio"),
    }
    for kind, words in keywords.items():
        scores[kind] = sum(2 if phrase in text else 0 for phrase in words)
    selected = max(scores, key=scores.get)
    maximum = scores[selected]
    if maximum == 0:
        selected, maximum = "tool", 1
    confidence = min(.98, .55 + maximum * .06)
    return Classification(selected, confidence, TYPE_DEFINITIONS[selected])


def slugify_capability_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    if len(value) < 3:
        value = "new_capability"
    return value[:64]


def reminder_proposal(request: str) -> CapabilityProposal:
    return CapabilityProposal(
        "Reminder Clock", "reminder_clock", "tool",
        "Store reminders and alarms locally and announce them at their requested time.",
        ["remind me in ten minutes to check the printer", "set an alarm for four", "list my reminders"],
        ["create_reminder", "create_alarm", "list_reminders", "cancel_reminder", "snooze_reminder", "dismiss_reminder"],
        ["WRITE_LOCAL_DATA"], ["unrestricted_python", "shell_execution", "arbitrary_network", "unrestricted_filesystem", "credential_access"],
        ["Profile-local reminder records must survive Brain restarts."],
        ["A bounded scheduler checks only the next due reminder."],
        ["Workshop configuration and reminder status; Brain notification and TTS when due."],
        ["Parsing, persistence, restart, due-time, cancellation, snooze, and duplicate-delivery tests."],
        ["No shell, arbitrary network, credentials, or unrestricted files; installation always requires user approval."],
        f"The user asked Brain to perform an unsupported reminder action: {request}",
    )


def proposal_from_description(description: str, *, override_type: str = "") -> CapabilityProposal:
    if any(pattern.search(str(description or "")) for pattern in _ACTION_PATTERNS):
        proposal = reminder_proposal(description)
        if override_type:
            proposal.capability_type = override_type
        return proposal
    classification = classify_capability(description)
    kind = override_type or classification.capability_type
    words = re.findall(r"[A-Za-z0-9]+", str(description or ""))[:5]
    name = " ".join(word.title() for word in words) or "New Capability"
    capability_id = slugify_capability_id(name)
    return CapabilityProposal(
        name, capability_id, kind, str(description or "").strip(),
        [f"use {name.lower()} for this request"], ["run"],
        ["NONE"], ["unrestricted_python", "shell_execution", "arbitrary_network", "credential_access"],
        ["No persistence unless approved during review."], ["No background work in the initial design."],
        ["Workshop status and configuration only."], ["Validation, safety scan, mock execution, and unknown-action rejection."],
        ["Generated package remains mock-only until reviewed and explicitly installed."],
        "The user explicitly requested a capability design.",
    )


_ACTION_PATTERNS = (
    re.compile(r"\bremind me\b", re.I),
    re.compile(r"\bset (?:an?|the) (?:alarm|timer)\b", re.I),
    re.compile(r"\bcreate (?:an? )?(?:alarm|reminder)\b", re.I),
)
_INFORMATIONAL = re.compile(r"\b(what is|explain|how does|theoretically|write (?:a )?story)\b", re.I)


def detect_capability_gap(request: str, records: List[Any]) -> tuple[str, Optional[CapabilityProposal]]:
    text = str(request or "").strip()
    if not text or _INFORMATIONAL.search(text) or not any(pattern.search(text) for pattern in _ACTION_PATTERNS):
        return "none", None
    reminder_actions = {"create_reminder", "create_alarm", "set_reminder", "set_alarm"}
    for record in records:
        actions = {action.action_id for action in record.manifest.actions}
        if actions & reminder_actions:
            return ("disabled" if record.state == "disabled" else "existing"), reminder_proposal(text)
    return "missing", reminder_proposal(text)


class PendingProposalState:
    def __init__(self, timeout_seconds: float = 300.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.proposal: Optional[CapabilityProposal] = None
        self.topic_marker = ""

    def set(self, proposal: CapabilityProposal) -> None:
        self.proposal = proposal
        self.topic_marker = proposal.capability_id

    def get(self) -> Optional[CapabilityProposal]:
        if self.proposal and time.time() - self.proposal.created_at <= self.timeout_seconds:
            return self.proposal
        self.clear()
        return None

    def clear(self) -> None:
        self.proposal = None
        self.topic_marker = ""

    def interpret_followup(self, text: str) -> str:
        if self.get() is None:
            return "none"
        low = " ".join(str(text or "").lower().split())
        if re.fullmatch(r"(yes|yes please|yes,? create it|create it|design it|go ahead)", low):
            return "approve_design"
        if re.fullmatch(r"(no|no thanks|cancel|forget it)", low):
            return "reject"
        if low in {"tell me more", "what would it do", "explain it"}:
            return "explain"
        if any(word in low for word in ("reminder", "alarm", "capability", "call it", "repeat", "behaviour")):
            return "modify"
        # An unrelated bare yes must not approve after topic has moved.
        if low == "yes":
            return "none"
        return "topic_changed"
