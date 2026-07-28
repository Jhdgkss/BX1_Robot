"""Copyable built-in integration example; it is not registered automatically."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult, IntegrationSettings


class ExampleIntegration(BaseIntegration):
    integration_id = "example"
    display_name = "Example"
    description = "Minimal read-only integration template."
    version = "1.0"

    def __init__(self, settings: Optional[IntegrationSettings] = None) -> None:
        super().__init__(settings)

    @property
    def configuration_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": "enabled", "type": "bool", "default": False},
            {"key": "service_url", "type": "string", "required": True},
            {"key": "api_key", "type": "secret", "secret": True},
        ]

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return [IntegrationCapability("status", "Get status")]

    def validate_configuration(self) -> List[str]:
        return [] if self.settings.values.get("service_url") else ["Service URL is required"]

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, **_: Any) -> IntegrationResult:
        if action_id != "status":
            return IntegrationResult(False, action_id, error_code="unknown_action", message="Unknown action")
        # Use an explicit timeout for real network work. Never return raw secrets or HTML.
        return IntegrationResult(True, action_id, {"state": "ready"}, "Example is ready",
                                 summary="Example service is ready.", speakable="The example service is ready.")
