from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult, IntegrationSettings, SafetyLevel
from bx1_integrations.events import mask_secret_text


@dataclass(frozen=True)
class SupportMessage:
    message_id: str
    group_id: str
    group_name: str
    sender: str
    text: str
    timestamp: str


@dataclass(frozen=True)
class SupportDraft:
    draft_id: str
    message: SupportMessage
    reply_text: str
    confidence: str
    notes: List[str]


def parse_group_list(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\n,;]+", str(value or ""))
    groups: List[str] = []
    for item in raw_items:
        group = re.sub(r"\s+", " ", str(item or "").strip())
        if group and group.lower() not in {existing.lower() for existing in groups}:
            groups.append(group)
    return groups


def message_mentions_trigger(text: str, trigger: str) -> bool:
    needle = str(trigger or "@John_Support").strip()
    if not needle:
        return False
    return needle.lower() in str(text or "").lower()


class SupportAssistantConnector(BaseIntegration):
    integration_id = "support_mentions"
    display_name = "Support Mention Responder"

    def __init__(self, settings: Optional[IntegrationSettings] = None, message_source: Any = None, send_sink: Any = None) -> None:
        super().__init__(settings)
        self.message_source = message_source
        self.send_sink = send_sink
        self.pending_drafts: Dict[str, SupportDraft] = {}

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return [
            IntegrationCapability("scan_mentions", "Scan approved support groups"),
            IntegrationCapability("draft_reply", "Draft support reply"),
            IntegrationCapability("send_approved_reply", "Send approved reply", SafetyLevel.CONTROL),
        ]

    def trigger(self) -> str:
        return str(self.settings.values.get("trigger") or "@John_Support").strip() or "@John_Support"

    def approved_groups(self) -> List[str]:
        return parse_group_list(self.settings.values.get("approved_groups") or [])

    def draft_only(self) -> bool:
        return bool(self.settings.values.get("draft_only", True))

    def _mock_messages(self) -> List[SupportMessage]:
        trigger = self.trigger()
        approved = self.approved_groups() or ["Field Tech Support"]
        return [
            SupportMessage(
                "mock-1",
                approved[0],
                approved[0],
                "Sarah",
                f"{trigger} The printer reports thermal runaway after a nozzle change. What should I check first?",
                datetime.now().isoformat(timespec="seconds"),
            ),
            SupportMessage(
                "mock-2",
                "Random Chat",
                "Random Chat",
                "Alex",
                f"{trigger} Can someone recommend lunch?",
                datetime.now().isoformat(timespec="seconds"),
            ),
        ]

    def fetch_messages(self) -> List[SupportMessage]:
        if self.settings.mock_mode or self.message_source is None:
            return self._mock_messages()
        payload = self.message_source()
        messages: List[SupportMessage] = []
        for item in payload or []:
            messages.append(
                SupportMessage(
                    str(item.get("message_id") or item.get("id") or uuid.uuid4().hex),
                    str(item.get("group_id") or item.get("group_name") or ""),
                    str(item.get("group_name") or item.get("group_id") or ""),
                    str(item.get("sender") or ""),
                    str(item.get("text") or ""),
                    str(item.get("timestamp") or datetime.now().isoformat(timespec="seconds")),
                )
            )
        return messages

    def scan_mentions(self) -> List[SupportMessage]:
        approved = {group.lower() for group in self.approved_groups()}
        if not approved:
            return []
        trigger = self.trigger()
        matches: List[SupportMessage] = []
        for message in self.fetch_messages():
            group_keys = {message.group_id.lower(), message.group_name.lower()}
            if not approved.intersection(group_keys):
                continue
            if message_mentions_trigger(message.text, trigger):
                matches.append(message)
        return matches

    def draft_reply(self, message: SupportMessage) -> SupportDraft:
        clean_text = re.sub(re.escape(self.trigger()), "", message.text, flags=re.IGNORECASE).strip()
        reply = (
            "Thanks for the tag. First, treat it as a safety fault and do not keep the machine heating unattended. "
            "Check the sensor and wiring connected to the changed part, confirm the thermistor is seated correctly, "
            "then compare the live temperature reading with room temperature before reheating. "
            "If the reading jumps, drops out, or looks implausible, stop and replace or reseat the sensor before continuing."
        )
        lower = clean_text.lower()
        notes = ["Draft only by default; review before sending."]
        confidence = "medium"
        if "thermal" in lower or "temperature" in lower or "nozzle" in lower:
            confidence = "high"
            notes.append("Detected a temperature/nozzle support topic.")
        if "password" in lower or "token" in lower or "api key" in lower:
            confidence = "low"
            notes.append("Sensitive credential topic detected; avoid sharing secrets in the group.")
            reply = "Thanks for the tag. This sounds credential-related, so please avoid posting keys or passwords in the group. I would rotate any exposed secret, check the service logs, and move the rest of the troubleshooting to a private secure channel."
        draft = SupportDraft(uuid.uuid4().hex, message, reply, confidence, notes)
        self.pending_drafts[draft.draft_id] = draft
        return draft

    def send_reply(self, draft_id: str, reply_text: str = "") -> IntegrationResult:
        if self.draft_only():
            return IntegrationResult(False, "send_approved_reply", error_code="draft_only", message="Draft-only mode is enabled; sending is blocked.")
        draft = self.pending_drafts.get(draft_id)
        if draft is None:
            return IntegrationResult(False, "send_approved_reply", error_code="missing_draft", message="Draft not found.")
        text = reply_text.strip() or draft.reply_text
        if self.settings.mock_mode or self.send_sink is None:
            return IntegrationResult(True, "send_approved_reply", {"mock": True, "group": draft.message.group_name, "reply": text}, "Mock send completed.")
        try:
            self.send_sink({"group_id": draft.message.group_id, "message_id": draft.message.message_id, "reply": text})
            return IntegrationResult(True, "send_approved_reply", {"group": draft.message.group_name}, "Reply sent.")
        except Exception as exc:
            return IntegrationResult(False, "send_approved_reply", error_code="send_failed", message=mask_secret_text(str(exc), self.settings.session_secrets.values()))

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        params = params or {}
        if action_id == "scan_mentions":
            matches = self.scan_mentions()
            return IntegrationResult(True, action_id, {"matches": [message.__dict__ for message in matches]}, f"{len(matches)} support mention(s) found.")
        if action_id == "draft_reply":
            message_payload = params.get("message")
            if isinstance(message_payload, dict):
                message = SupportMessage(
                    str(message_payload.get("message_id") or message_payload.get("id") or uuid.uuid4().hex),
                    str(message_payload.get("group_id") or message_payload.get("group_name") or ""),
                    str(message_payload.get("group_name") or message_payload.get("group_id") or ""),
                    str(message_payload.get("sender") or ""),
                    str(message_payload.get("text") or ""),
                    str(message_payload.get("timestamp") or datetime.now().isoformat(timespec="seconds")),
                )
            else:
                matches = self.scan_mentions()
                if not matches:
                    return IntegrationResult(False, action_id, error_code="no_mentions", message="No approved support mentions found.")
                message = matches[0]
            draft = self.draft_reply(message)
            return IntegrationResult(True, action_id, {"draft": {"draft_id": draft.draft_id, "reply_text": draft.reply_text, "confidence": draft.confidence, "notes": draft.notes, "message": draft.message.__dict__}}, "Support reply drafted.")
        if action_id == "send_approved_reply":
            return self.send_reply(str(params.get("draft_id") or ""), str(params.get("reply_text") or ""))
        return IntegrationResult(False, action_id, error_code="unknown_action", message=f"Unknown action: {action_id}")
