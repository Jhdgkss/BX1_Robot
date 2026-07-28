from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult
from bx1_integrations.permissions import PermissionManager


class IntegrationRegistry:
    def __init__(self, permission_manager: Optional[PermissionManager] = None) -> None:
        self.permission_manager = permission_manager or PermissionManager()
        self._integrations: Dict[str, BaseIntegration] = {}

    def register(self, integration: BaseIntegration) -> None:
        if not integration.integration_id or integration.integration_id == "base":
            raise ValueError("Integration must have a stable integration_id")
        if integration.integration_id in self._integrations:
            raise ValueError(f"Duplicate integration ID: {integration.integration_id}")
        self._integrations[integration.integration_id] = integration

    def get(self, integration_id: str) -> BaseIntegration:
        return self._integrations[integration_id]

    def all(self) -> List[BaseIntegration]:
        return list(self._integrations.values())

    def capabilities(self) -> Dict[str, List[IntegrationCapability]]:
        return {integration.integration_id: integration.capabilities for integration in self.all()}

    def execute(self, integration_id: str, action_id: str, params: Optional[dict] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        integration = self.get(integration_id)
        capability = next((item for item in integration.capabilities if item.action_id == action_id), None)
        if capability is None:
            return IntegrationResult(False, action_id, message=f"Unknown action: {action_id}", error_code="unknown_action")
        decision = self.permission_manager.decide(capability, initiated_by_ai=initiated_by_ai, confirmed=confirmed)
        if not decision.allowed:
            return IntegrationResult(
                False,
                action_id,
                message=decision.reason,
                error_code="confirmation_required" if decision.requires_confirmation else "permission_denied",
                safety_level=capability.safety_level,
                requires_confirmation=decision.requires_confirmation,
            )
        return integration.execute_action(action_id, params or {}, initiated_by_ai=initiated_by_ai, confirmed=confirmed)

    @classmethod
    def load_defaults(cls, integrations: Iterable[BaseIntegration]) -> "IntegrationRegistry":
        registry = cls()
        for integration in integrations:
            registry.register(integration)
        return registry
