from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class SafetyLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    CONTROL = "CONTROL"
    SAFETY_CRITICAL = "SAFETY_CRITICAL"


class ConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    MOCK = "mock"


@dataclass(frozen=True)
class IntegrationCapability:
    action_id: str
    label: str
    safety_level: SafetyLevel = SafetyLevel.READ_ONLY
    ai_callable: bool = True


@dataclass
class IntegrationResult:
    ok: bool
    action_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error_code: str = ""
    safety_level: SafetyLevel = SafetyLevel.READ_ONLY
    requires_confirmation: bool = False
    integration: str = ""
    summary: str = ""
    speakable: str = ""
    sources: List[str] = field(default_factory=list)

    def normalised(self, integration_id: str = "") -> Dict[str, Any]:
        """Return the only representation that may be supplied to conversation code."""
        summary = self.summary or self.message
        speakable = self.speakable or summary
        return {
            "ok": bool(self.ok),
            "integration": self.integration or integration_id,
            "action": self.action_id,
            "summary": summary,
            "data": self.data if isinstance(self.data, dict) else {},
            "error_code": self.error_code or None,
            "error_message": None if self.ok else summary,
            "speakable": speakable,
            "sources": list(self.sources),
            "requires_confirmation": bool(self.requires_confirmation),
        }


@dataclass
class IntegrationSettings:
    values: Dict[str, Any] = field(default_factory=dict)
    session_secrets: Dict[str, str] = field(default_factory=dict)
    mock_mode: bool = True


class IntegrationError(Exception):
    def __init__(self, message: str, *, code: str = "integration_error") -> None:
        super().__init__(message)
        self.code = code


class BaseIntegration:
    integration_id = "base"
    display_name = "Base Integration"
    description = ""
    version = "1.0"

    def __init__(self, settings: Optional[IntegrationSettings] = None) -> None:
        self.settings = settings or IntegrationSettings()
        self.status = ConnectionStatus.MOCK if self.settings.mock_mode else ConnectionStatus.DISCONNECTED
        self.activity_log: List[str] = []
        self.last_successful_connection = ""
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return bool(self.settings.values.get("enabled", True))

    @property
    def configuration_schema(self) -> List[Dict[str, Any]]:
        return []

    def validate_configuration(self) -> List[str]:
        return []

    def initialise(self) -> IntegrationResult:
        if not self.enabled:
            return IntegrationResult(True, "initialise", {"enabled": False}, "Integration disabled")
        return self.connect()

    def shutdown(self) -> IntegrationResult:
        return self.disconnect()

    def _record_result(self, result: IntegrationResult) -> IntegrationResult:
        result.integration = result.integration or self.integration_id
        if result.ok:
            self.last_successful_connection = datetime.now(timezone.utc).isoformat()
            self.last_error = ""
        else:
            self.last_error = result.message
        return result

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return []

    def log(self, message: str) -> None:
        self.activity_log.append(str(message))

    def health_check(self) -> IntegrationResult:
        return self._record_result(IntegrationResult(True, "health_check", {"status": self.status.value}, "OK"))

    def test_connection(self) -> IntegrationResult:
        return self.health_check()

    def connect(self) -> IntegrationResult:
        self.status = ConnectionStatus.MOCK if self.settings.mock_mode else ConnectionStatus.CONNECTED
        return self._record_result(IntegrationResult(True, "connect", {"status": self.status.value}, "Connected"))

    def disconnect(self) -> IntegrationResult:
        self.status = ConnectionStatus.DISCONNECTED
        return IntegrationResult(True, "disconnect", {"status": self.status.value}, "Disconnected")

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        raise IntegrationError(f"Unknown action: {action_id}", code="unknown_action")
