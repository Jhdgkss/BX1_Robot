from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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

    def __init__(self, settings: Optional[IntegrationSettings] = None) -> None:
        self.settings = settings or IntegrationSettings()
        self.status = ConnectionStatus.MOCK if self.settings.mock_mode else ConnectionStatus.DISCONNECTED
        self.activity_log: List[str] = []

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return []

    def log(self, message: str) -> None:
        self.activity_log.append(str(message))

    def health_check(self) -> IntegrationResult:
        return IntegrationResult(True, "health_check", {"status": self.status.value}, "OK")

    def connect(self) -> IntegrationResult:
        self.status = ConnectionStatus.MOCK if self.settings.mock_mode else ConnectionStatus.CONNECTED
        return IntegrationResult(True, "connect", {"status": self.status.value}, "Connected")

    def disconnect(self) -> IntegrationResult:
        self.status = ConnectionStatus.DISCONNECTED
        return IntegrationResult(True, "disconnect", {"status": self.status.value}, "Disconnected")

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        raise IntegrationError(f"Unknown action: {action_id}", code="unknown_action")

