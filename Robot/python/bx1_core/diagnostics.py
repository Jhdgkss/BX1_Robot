from __future__ import annotations

import copy
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional

from .service_registry import ServiceLifecycleState, ServiceRegistry


class DiagnosticsService:
    """Aggregates introspection from every registered service."""

    INACTIVE_STATES = {"DISABLED", "NOT_FITTED", "STOPPED"}

    def __init__(
        self,
        registry: ServiceRegistry,
        config: Optional[Mapping[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.registry = registry
        self._config = {
            "enabled": True,
            "include_service_diagnostics": True,
            "include_configuration": False,
            "history_limit": 20,
            "required_services": [],
            **dict(config or {}),
        }
        self._clock = clock
        self._created_at = self._clock()
        self._runtime_context: Dict[str, Any] = {
            "startup_time": self._created_at,
            "configuration_summary": {},
            "startup_report": {},
        }
        self._history: Deque[Dict[str, Any]] = deque(
            maxlen=max(1, int(self._config["history_limit"]))
        )
        self._last_summary: Dict[str, Any] = {
            "overall_state": "UNKNOWN",
            "service_count": 0,
            "faulted": [],
            "stale": [],
            "missing": [],
        }

    def report(self) -> Dict[str, Any]:
        services: Dict[str, Any] = {}
        faulted: List[str] = []
        stale: List[str] = []
        degraded: List[str] = []
        required = {
            str(name).strip().lower()
            for name in self._config.get("required_services", [])
        }
        missing = sorted(required - set(self.registry.names()))

        for name in self.registry.names():
            registration = self.registry.registration(name)
            service = registration.service
            entry: Dict[str, Any] = {
                "lifecycle": registration.state.value,
                "service_type": type(service).__name__,
            }
            errors: List[str] = []
            status = self._call(service, "status", errors)
            health = self._call(service, "health", errors)
            entry["status"] = status
            entry["health"] = health
            if self._config["include_service_diagnostics"]:
                entry["diagnostics"] = self._call(
                    service, "diagnostics", errors
                )
            if self._config["include_configuration"]:
                entry["configuration"] = self._call(
                    service, "configuration", errors
                )
            if errors:
                entry["errors"] = errors

            state = str(
                status.get("state", health.get("state", registration.state.value))
            ).upper()
            healthy = bool(health.get("healthy", not errors))
            if (
                errors
                or registration.state == ServiceLifecycleState.FAULT
                or state in {"FAULT", "ERROR"}
            ):
                faulted.append(name)
            elif state == "STALE":
                stale.append(name)
            elif not healthy and state not in self.INACTIVE_STATES:
                degraded.append(name)
            services[name] = entry

        overall = (
            "FAULT"
            if faulted or missing
            else "DEGRADED"
            if stale or degraded
            else "HEALTHY"
        )
        report = {
            "schema": "bx1.diagnostics.v1",
            "timestamp": self._clock(),
            "overall_state": overall,
            "service_count": len(services),
            "faulted": sorted(faulted),
            "stale": sorted(stale),
            "degraded": sorted(degraded),
            "missing": missing,
            "services": services,
            "registry": self.registry.status(),
            "runtime": self._runtime_diagnostics(),
        }
        self._last_summary = {
            key: copy.deepcopy(report[key])
            for key in (
                "overall_state",
                "service_count",
                "faulted",
                "stale",
                "degraded",
                "missing",
            )
        }
        self._history.append(copy.deepcopy(self._last_summary))
        return report

    def status(self) -> Dict[str, Any]:
        return {
            "service": "diagnostics",
            "state": "READY" if self._config["enabled"] else "DISABLED",
            **copy.deepcopy(self._last_summary),
        }

    def health(self) -> Dict[str, Any]:
        enabled = bool(self._config["enabled"])
        return {
            "healthy": enabled,
            "available": enabled,
            "state": "READY" if enabled else "DISABLED",
            "reason": "Diagnostics collector ready" if enabled else "Diagnostics disabled",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "last_summary": copy.deepcopy(self._last_summary),
            "report_count": len(self._history),
            "history": list(self._history),
            "runtime": self._runtime_diagnostics(),
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def set_runtime_context(
        self,
        *,
        startup_time: Optional[float] = None,
        configuration_summary: Optional[Mapping[str, Any]] = None,
        startup_report: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if startup_time is not None:
            self._runtime_context["startup_time"] = float(startup_time)
        if configuration_summary is not None:
            self._runtime_context["configuration_summary"] = copy.deepcopy(
                dict(configuration_summary)
            )
        if startup_report is not None:
            self._runtime_context["startup_report"] = copy.deepcopy(
                dict(startup_report)
            )

    def _runtime_diagnostics(self) -> Dict[str, Any]:
        now = self._clock()
        startup_time = float(
            self._runtime_context.get("startup_time", self._created_at)
        )
        communication: Dict[str, Any] = {"registered": False}
        if self.registry.has("communication"):
            service = self.registry.service("communication")
            errors: List[str] = []
            communication = {
                "registered": True,
                "status": self._call(service, "status", errors),
                "health": self._call(service, "health", errors),
            }
            if errors:
                communication["errors"] = errors
        return {
            "startup_time": startup_time,
            "uptime_s": round(max(0.0, now - startup_time), 3),
            "registered_services": self.registry.names(),
            "service_states": {
                name: self.registry.registration(name).state.value
                for name in self.registry.names()
            },
            "dependency_graph": self.registry.dependency_graph(),
            "dependency_validation": self.registry.validate_dependencies(),
            "configuration_summary": copy.deepcopy(
                self._runtime_context.get("configuration_summary", {})
            ),
            "communication": communication,
            "startup_report": copy.deepcopy(
                self._runtime_context.get("startup_report", {})
            ),
        }

    @staticmethod
    def _call(service: Any, method: str, errors: List[str]) -> Dict[str, Any]:
        callback = getattr(service, method, None)
        if not callable(callback):
            errors.append("%s() is not implemented" % method)
            return {}
        try:
            value = callback()
            return value if isinstance(value, dict) else {"value": value}
        except Exception as exc:
            errors.append("%s(): %s" % (method, exc))
            return {}
