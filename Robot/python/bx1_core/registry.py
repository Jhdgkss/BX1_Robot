from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Mapping, Optional

from .events import CoreEventBus, CoreEventType
from .state import StateStore


ServiceProvider = Callable[[], Any]


class CoreServiceRegistry:
    """Read-only projection of services into the central state database."""

    def __init__(
        self,
        state: StateStore,
        provider: Optional[ServiceProvider] = None,
        events: Optional[CoreEventBus] = None,
    ) -> None:
        self.state = state
        self.provider = provider
        self.events = events
        self._previous: Dict[str, str] = {}

    def update(self) -> List[Dict[str, Any]]:
        raw = [] if self.provider is None else self.provider()
        if isinstance(raw, Mapping):
            raw = [
                {"name": str(name), **dict(value)}
                if isinstance(value, Mapping)
                else {"name": str(name), "state": str(value)}
                for name, value in sorted(raw.items())
            ]
        if not isinstance(raw, list):
            raise TypeError("Core service provider must return a list or mapping")
        services: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            value = copy.deepcopy(dict(item))
            value["name"] = str(value.get("name", "")).strip()
            if not value["name"]:
                continue
            value.setdefault("description", "")
            value.setdefault("state", "unknown")
            value.setdefault("managed", False)
            services.append(value)
        services.sort(key=lambda item: item["name"])
        self.state.set("services.items", services, source="core.services")
        current = {
            item["name"]: str(item.get("state", "unknown")).lower()
            for item in services
        }
        if self.events is not None:
            for name, service_state in current.items():
                previous = self._previous.get(name)
                if service_state == "running" and previous != "running":
                    self.events.publish(
                        CoreEventType.SERVICE_STARTED,
                        {
                            "name": name,
                            "state": service_state,
                            "previous_state": previous,
                        },
                        source="core.services",
                    )
                elif previous == "running" and service_state != "running":
                    self.events.publish(
                        CoreEventType.SERVICE_STOPPED,
                        {
                            "name": name,
                            "state": service_state,
                            "previous_state": previous,
                        },
                        source="core.services",
                    )
            for name, previous in self._previous.items():
                if name not in current and previous == "running":
                    self.events.publish(
                        CoreEventType.SERVICE_STOPPED,
                        {
                            "name": name,
                            "state": "removed",
                            "previous_state": previous,
                        },
                        source="core.services",
                    )
        self._previous = current
        return copy.deepcopy(services)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.services.v1",
            "services": self.state.get("services.items", []),
        }


from .plugins.registry import PluginRegistry  # noqa: E402

__all__ = ["CoreServiceRegistry", "PluginRegistry", "ServiceProvider"]
