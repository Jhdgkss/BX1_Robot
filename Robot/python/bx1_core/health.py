from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from hardware_services import EventBus, EventType

from .service_registry import ServiceLifecycleState, ServiceRegistry


class HealthState(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    FAULT = "fault"


@dataclass(frozen=True)
class PluginHealth:
    """Common health contract returned by every Core telemetry plugin."""

    state: HealthState
    timestamp: float
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return self.state == HealthState.HEALTHY

    @property
    def warning(self) -> bool:
        return self.state == HealthState.WARNING

    @property
    def fault(self) -> bool:
        return self.state == HealthState.FAULT

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "healthy": self.healthy,
            "warning": self.warning,
            "fault": self.fault,
            "timestamp": self.timestamp,
            "details": copy.deepcopy(dict(self.details)),
        }


def aggregate_plugin_health(
    plugins: Mapping[str, Mapping[str, Any]],
    *,
    timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    states = {
        str(item.get("state", HealthState.FAULT.value))
        for item in plugins.values()
    }
    overall = (
        HealthState.FAULT
        if HealthState.FAULT.value in states
        else HealthState.WARNING
        if HealthState.WARNING.value in states
        else HealthState.HEALTHY
    )
    return {
        "schema": "bx1.core.health.v1",
        "state": overall.value,
        "healthy": overall == HealthState.HEALTHY,
        "warning": overall == HealthState.WARNING,
        "fault": overall == HealthState.FAULT,
        "timestamp": time.time() if timestamp is None else float(timestamp),
        "plugins": copy.deepcopy(dict(plugins)),
    }


class HealthMonitor:
    """Detects missing, stale and faulted services and emits state changes."""

    def __init__(
        self,
        registry: ServiceRegistry,
        event_bus: EventBus,
        config: Optional[Mapping[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.registry = registry
        self.events = event_bus
        self._config = {
            "enabled": True,
            "interval_s": 1.0,
            "publish_initial": False,
            "required_services": [],
            **dict(config or {}),
        }
        self._clock = clock
        self._previous: Dict[str, Tuple[str, str, bool]] = {}
        self._last: Dict[str, Any] = {
            "overall_state": "UNKNOWN",
            "missing": [],
            "faulted": [],
            "stale": [],
            "unhealthy": [],
            "services": {},
        }
        self._check_count = 0

    def check(self) -> Dict[str, Any]:
        required = {
            str(name).strip().lower()
            for name in self._config.get("required_services", [])
        }
        names = sorted(required | set(self.registry.names()))
        services: Dict[str, Any] = {}
        missing: List[str] = []
        faulted: List[str] = []
        stale: List[str] = []
        unhealthy: List[str] = []

        for name in names:
            if not self.registry.has(name):
                classification, state, healthy, reason = (
                    "missing",
                    "MISSING",
                    False,
                    "Required service is not registered",
                )
                missing.append(name)
            else:
                registration = self.registry.registration(name)
                try:
                    status = self._mapping(registration.service, "status")
                    health = self._mapping(registration.service, "health")
                    state = str(
                        status.get(
                            "state", health.get("state", registration.state.value)
                        )
                    ).upper()
                    healthy = bool(health.get("healthy", True))
                    reason = str(
                        health.get("reason", status.get("reason", ""))
                    )
                    if (
                        registration.state == ServiceLifecycleState.FAULT
                        or state in {"FAULT", "ERROR"}
                    ):
                        classification = "fault"
                        faulted.append(name)
                    elif state == "STALE":
                        classification = "stale"
                        stale.append(name)
                    elif not healthy and state not in {
                        "DISABLED",
                        "NOT_FITTED",
                        "STOPPED",
                    }:
                        classification = "unhealthy"
                        unhealthy.append(name)
                    else:
                        classification = "healthy"
                except Exception as exc:
                    classification, state, healthy, reason = (
                        "fault",
                        "FAULT",
                        False,
                        "Health inspection failed: %s" % exc,
                    )
                    faulted.append(name)

            current = (classification, state, healthy)
            previous = self._previous.get(name)
            services[name] = {
                "classification": classification,
                "state": state,
                "healthy": healthy,
                "reason": reason,
            }
            if previous is not None or self._config["publish_initial"]:
                if previous != current:
                    self._publish_change(name, previous, current, reason)
            self._previous[name] = current

        overall = (
            "FAULT"
            if missing or faulted
            else "DEGRADED"
            if stale or unhealthy
            else "HEALTHY"
        )
        self._check_count += 1
        self._last = {
            "timestamp": self._clock(),
            "overall_state": overall,
            "missing": sorted(missing),
            "faulted": sorted(faulted),
            "stale": sorted(stale),
            "unhealthy": sorted(unhealthy),
            "services": services,
        }
        return copy.deepcopy(self._last)

    def status(self) -> Dict[str, Any]:
        return {
            "service": "health_monitor",
            "state": "READY" if self._config["enabled"] else "DISABLED",
            "system_health": self._last["overall_state"],
            "check_count": self._check_count,
        }

    def health(self) -> Dict[str, Any]:
        enabled = bool(self._config["enabled"])
        return {
            "healthy": enabled,
            "available": enabled,
            "state": "READY" if enabled else "DISABLED",
            "reason": "Health monitor ready" if enabled else "Health monitor disabled",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {"check_count": self._check_count, "last_check": copy.deepcopy(self._last)}

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _publish_change(
        self,
        name: str,
        previous: Optional[Tuple[str, str, bool]],
        current: Tuple[str, str, bool],
        reason: str,
    ) -> None:
        classification, state, healthy = current
        payload = {
            "service": name,
            "previous": None
            if previous is None
            else {
                "classification": previous[0],
                "state": previous[1],
                "healthy": previous[2],
            },
            "classification": classification,
            "state": state,
            "healthy": healthy,
            "reason": reason,
        }
        self.events.publish(
            EventType.SERVICE_HEALTH_CHANGED,
            payload,
            source="health_monitor",
        )
        specialised = {
            "missing": EventType.SERVICE_MISSING,
            "fault": EventType.SERVICE_FAULT,
            "stale": EventType.SERVICE_STALE,
            "healthy": EventType.SERVICE_RECOVERED,
        }.get(classification)
        if specialised is not None:
            self.events.publish(specialised, payload, source="health_monitor")

    @staticmethod
    def _mapping(service: Any, method: str) -> Dict[str, Any]:
        callback = getattr(service, method, None)
        if not callable(callback):
            raise AttributeError("%s() is not implemented" % method)
        value = callback()
        return value if isinstance(value, dict) else {"value": value}
