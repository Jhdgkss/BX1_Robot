from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from bx1_integrations.base import BaseIntegration, IntegrationResult
from bx1_integrations.events import mask_secret_text
from bx1_integrations.registry import IntegrationRegistry


LOG = logging.getLogger(__name__)


class IntegrationManager:
    """Fault boundary and lifecycle owner for all Brain integrations."""

    def __init__(self, integrations: Iterable[BaseIntegration] = ()) -> None:
        self.registry = IntegrationRegistry()
        self.discovery_errors: Dict[str, str] = {}
        for integration in integrations:
            try:
                self.registry.register(integration)
                LOG.info("Discovered integration %s (enabled=%s)", integration.integration_id, integration.enabled)
            except Exception as exc:
                key = getattr(integration, "integration_id", type(integration).__name__)
                self.discovery_errors[str(key)] = mask_secret_text(str(exc))
                LOG.exception("Integration registration failed for %s", key)

    @classmethod
    def builtins(cls, settings: Optional[Dict[str, Any]] = None, *, secret_store: Any = None) -> "IntegrationManager":
        """Controlled discovery: imports only the built-in package modules."""
        settings = settings or {}
        integrations: List[BaseIntegration] = []
        specs = (
            ("octoprint", "bx1_integrations.octoprint_connector", "OctoPrintConnector"),
            ("spotify", "bx1_integrations.spotify_connector", "SpotifyConnector"),
        )
        for integration_id, module_name, class_name in specs:
            try:
                module = __import__(module_name, fromlist=[class_name])
                cls_type = getattr(module, class_name)
                values = dict(settings.get(integration_id) or {})
                secrets: Dict[str, str] = {}
                if secret_store is not None:
                    names = ("api_key",) if integration_id == "octoprint" else ("client_secret", "access_token", "refresh_token", "expires_at")
                    secrets = {name: secret_store.get_secret(integration_id, name) for name in names}
                from bx1_integrations.base import IntegrationSettings
                integrations.append(cls_type(IntegrationSettings(values, secrets, bool(values.get("mock_mode", False)))))
            except Exception as exc:
                LOG.exception("Built-in integration import failed: %s", integration_id)
                manager = cls(integrations)
                manager.discovery_errors[integration_id] = mask_secret_text(str(exc))
                return manager
        return cls(integrations)

    def initialise_enabled(self) -> Dict[str, IntegrationResult]:
        results: Dict[str, IntegrationResult] = {}
        for integration in self.registry.all():
            if not integration.enabled:
                LOG.info("Integration %s disabled; not initialising", integration.integration_id)
                continue
            try:
                results[integration.integration_id] = integration.initialise()
            except Exception as exc:
                message = mask_secret_text(str(exc), integration.settings.session_secrets.values())
                results[integration.integration_id] = IntegrationResult(
                    False, "initialise", error_code="initialisation_failed", message=message, integration=integration.integration_id
                )
                LOG.exception("Integration %s initialisation failed", integration.integration_id)
        return results

    def invoke(self, integration_id: str, action_id: str, params: Optional[Dict[str, Any]] = None, **permission: Any) -> IntegrationResult:
        try:
            result = self.registry.execute(integration_id, action_id, params or {}, **permission)
        except KeyError:
            result = IntegrationResult(False, action_id, error_code="integration_unavailable", message="Integration is unavailable")
        except Exception as exc:
            result = IntegrationResult(False, action_id, error_code="integration_failure", message=mask_secret_text(str(exc)))
            LOG.exception("Integration action failed: %s.%s", integration_id, action_id)
        result.integration = result.integration or integration_id
        return result

    # Compatibility façade used by the existing Workshop while it moves from the
    # first-generation registry API to manager-native cards.
    def get(self, integration_id: str) -> BaseIntegration:
        return self.registry.get(integration_id)

    def all(self) -> List[BaseIntegration]:
        return self.registry.all()

    def execute(self, integration_id: str, action_id: str, params: Optional[Dict[str, Any]] = None, **permission: Any) -> IntegrationResult:
        return self.invoke(integration_id, action_id, params, **permission)

    def result_for_llm(self, result: IntegrationResult) -> Dict[str, Any]:
        safe = result.normalised(result.integration)
        safe["data"] = _sanitise_data(safe["data"])
        return safe

    def health(self) -> Dict[str, Dict[str, Any]]:
        return {
            item.integration_id: {
                "enabled": item.enabled,
                "configured": not item.validate_configuration(),
                "status": item.status.value,
                "last_successful_connection": item.last_successful_connection or None,
                "last_error": item.last_error or None,
            }
            for item in self.registry.all()
        }

    def shutdown(self) -> None:
        for integration in self.registry.all():
            try:
                integration.shutdown()
            except Exception:
                LOG.exception("Integration %s shutdown failed", integration.integration_id)


def _sanitise_data(value: Any) -> Any:
    blocked = ("secret", "token", "api_key", "authorization", "base_url", "endpoint", "redirect_uri")
    if isinstance(value, dict):
        return {key: _sanitise_data(item) for key, item in value.items() if not any(part in str(key).lower() for part in blocked)}
    if isinstance(value, list):
        return [_sanitise_data(item) for item in value]
    if isinstance(value, str):
        return mask_secret_text(value)
    return value
