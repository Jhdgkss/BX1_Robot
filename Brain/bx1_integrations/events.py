from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List


SECRET_PATTERNS = [
    re.compile(r"(X-Api-Key\s*[:=]\s*)([A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(Authorization\s*[:=]\s*Bearer\s+)([A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(api[_ -]?key\s*[:=]\s*)([A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(access[_ -]?token\s*[:=]\s*)([A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(refresh[_ -]?token\s*[:=]\s*)([A-Za-z0-9._\-]+)", re.IGNORECASE),
]


def mask_secret_text(text: str, extra_secrets: Iterable[str] = ()) -> str:
    safe = str(text or "")
    for pattern in SECRET_PATTERNS:
        safe = pattern.sub(r"\1****", safe)
    for secret in extra_secrets:
        if secret:
            safe = safe.replace(secret, "****")
    return safe


@dataclass(frozen=True)
class IntegrationEvent:
    timestamp: str
    integration_id: str
    level: str
    message: str


class IntegrationEventLog:
    def __init__(self, max_events: int = 500) -> None:
        self.max_events = max_events
        self.events: List[IntegrationEvent] = []

    def add(self, integration_id: str, level: str, message: str, *, secrets: Iterable[str] = ()) -> IntegrationEvent:
        event = IntegrationEvent(
            datetime.now().strftime("%H:%M:%S"),
            integration_id,
            level,
            mask_secret_text(message, secrets),
        )
        self.events.append(event)
        self.events = self.events[-self.max_events :]
        return event

    def text(self) -> str:
        return "\n".join(f"[{event.timestamp}] {event.integration_id} {event.level}: {event.message}" for event in self.events)

