from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from bx1_integrations.base import IntegrationCapability, SafetyLevel


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_confirmation: bool
    reason: str = ""


class PermissionManager:
    def decide(self, capability: IntegrationCapability, *, initiated_by_ai: bool = False, confirmed: bool = False) -> PermissionDecision:
        if capability.safety_level == SafetyLevel.READ_ONLY:
            return PermissionDecision(True, False, "read-only action")
        if capability.safety_level == SafetyLevel.CONTROL:
            if initiated_by_ai and not confirmed:
                return PermissionDecision(False, True, "AI-initiated control action requires confirmation")
            return PermissionDecision(True, False, "control action allowed")
        if capability.safety_level == SafetyLevel.SAFETY_CRITICAL:
            if not confirmed:
                return PermissionDecision(False, True, "safety-critical action requires explicit confirmation every time")
            return PermissionDecision(True, False, "safety-critical action confirmed")
        return PermissionDecision(False, False, "unknown safety level")


class SecretStore:
    """Prefer OS credential storage, with an explicit session-only fallback."""

    def __init__(self, namespace: str = "BX1RobotBrain") -> None:
        self.namespace = namespace
        self.session_secrets: Dict[Tuple[str, str], str] = {}
        try:
            import keyring  # type: ignore
        except Exception:
            keyring = None  # type: ignore
        self.keyring = keyring

    @property
    def persistent_available(self) -> bool:
        return self.keyring is not None

    def set_secret(self, integration_id: str, key: str, value: str, *, session_only: bool = False) -> None:
        if self.keyring is not None and not session_only:
            self.keyring.set_password(f"{self.namespace}.{integration_id}", key, value)
            return
        self.session_secrets[(integration_id, key)] = value

    def get_secret(self, integration_id: str, key: str) -> str:
        if self.keyring is not None:
            value = self.keyring.get_password(f"{self.namespace}.{integration_id}", key)
            if value:
                return str(value)
        return self.session_secrets.get((integration_id, key), "")
