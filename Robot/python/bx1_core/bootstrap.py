from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Set

from .root import BX1, create_bx1
from .service_registry import ServiceLifecycleState


ALPHA_REQUIRED_SERVICES = {
    "events",
    "capabilities",
    "logging",
    "scheduler",
    "led",
    "drive",
    "range",
    "battery",
    "power",
    "diagnostics",
    "health",
    "communication",
}

ServiceFactory = Callable[[BX1, Mapping[str, Any]], Any]


class BootstrapError(RuntimeError):
    """Raised when BX1 cannot establish a complete, safe runtime graph."""

    def __init__(self, message: str, report: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.report = copy.deepcopy(dict(report))


@dataclass(frozen=True)
class BootstrapResult:
    bx1: BX1
    configuration: Dict[str, Any]
    report: Dict[str, Any]


class CompatibilityServiceAdapter:
    """Adds BX1 lifecycle/introspection without changing a legacy interface."""

    def __init__(self, name: str, delegate: Any) -> None:
        self.name = str(name).strip().lower()
        if not self.name:
            raise ValueError("compatibility service name must not be empty")
        self.delegate = delegate
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def status(self) -> Dict[str, Any]:
        return {
            "service": self.name,
            "state": "READY" if self._running else "INITIALISING",
            "adapter": "compatibility",
            "delegate_type": type(self.delegate).__name__,
        }

    def health(self) -> Dict[str, Any]:
        return {
            "healthy": self._running,
            "available": self._running,
            "state": "READY" if self._running else "INITIALISING",
            "reason": (
                "Legacy runtime interface is owned by BX1"
                if self._running
                else "Compatibility service has not started"
            ),
        }

    def diagnostics(self) -> Dict[str, Any]:
        last_state = getattr(self.delegate, "last_state", {})
        return {
            "adapter": "compatibility",
            "running": self._running,
            "delegate_type": type(self.delegate).__name__,
            "delegate_available": bool(getattr(self.delegate, "available", True)),
            "bridge_mode": (
                last_state.get("bridge_mode")
                if isinstance(last_state, Mapping)
                else None
            ),
            "hardware_polled": False,
        }

    def configuration(self) -> Dict[str, Any]:
        return {
            "adapter": "compatibility",
            "delegate_type": type(self.delegate).__name__,
            "behaviour_preserved": True,
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def bootstrap_runtime(
    config: Optional[Mapping[str, Any]] = None,
    *,
    config_loader: Optional[Callable[[], Mapping[str, Any]]] = None,
    config_source: str = "mapping",
    service_factories: Optional[Mapping[str, ServiceFactory]] = None,
    service_dependencies: Optional[Mapping[str, Iterable[str]]] = None,
    required_services: Optional[Iterable[str]] = None,
    root_factory: Callable[..., BX1] = create_bx1,
    monotonic_clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
) -> BootstrapResult:
    """Load, compose, start and validate the BX1 OS Alpha service graph."""

    started_mono = monotonic_clock()
    started_at = wall_clock()
    root: Optional[BX1] = None
    loaded: Dict[str, Any] = {}
    errors = []
    required = set(ALPHA_REQUIRED_SERVICES)
    required.update(_normalise_names(required_services or []))

    try:
        if config_loader is not None:
            candidate = config_loader()
        else:
            candidate = config or {}
        if not isinstance(candidate, Mapping):
            raise TypeError("runtime configuration loader must return a mapping")
        loaded = copy.deepcopy(dict(candidate))

        root = root_factory(
            loaded,
            monotonic_clock=monotonic_clock,
            wall_clock=wall_clock,
        )
        dependencies = service_dependencies or {}
        for name, factory in sorted((service_factories or {}).items()):
            if not callable(factory):
                raise TypeError("service factory is not callable: %s" % name)
            key = str(name).strip().lower()
            service = factory(root, loaded)
            root.attach(
                key,
                service,
                dependencies=set(dependencies.get(key, [])),
                start=False,
            )

        graph_validation = root.services.validate_dependencies()
        if not graph_validation["valid"]:
            raise RuntimeError("; ".join(graph_validation["errors"]))

        root.services.start_all()
        scheduler_tick = root.tick()
        health_report = root.health.check()

        names = set(root.services.names())
        missing = sorted(required - names)
        not_running = sorted(
            name
            for name in required & names
            if root.services.registration(name).state
            != ServiceLifecycleState.RUNNING
        )
        scheduler = {
            "status": root.scheduler.status(),
            "heartbeat": root.scheduler.heartbeat(),
            "initial_tick": scheduler_tick,
        }
        communication = {
            "status": root.communication.status(),
            "health": root.communication.health(),
        }
        validation_errors = []
        if missing:
            validation_errors.append(
                "missing required services: %s" % ", ".join(missing)
            )
        if not_running:
            validation_errors.append(
                "services not running: %s" % ", ".join(not_running)
            )
        if scheduler["status"].get("state") != "READY":
            validation_errors.append("scheduler is not ready")
        if not scheduler["heartbeat"].get("alive"):
            validation_errors.append("scheduler heartbeat is not operational")
        if not communication["health"].get("healthy"):
            validation_errors.append("communication service is not healthy")
        if root.health.status().get("state") != "READY":
            validation_errors.append("health monitor is not operational")
        if validation_errors:
            raise RuntimeError("; ".join(validation_errors))

        report = _build_report(
            success=True,
            root=root,
            configuration=loaded,
            required=required,
            started_at=started_at,
            completed_at=wall_clock(),
            duration_ms=(monotonic_clock() - started_mono) * 1000.0,
            config_source=config_source,
            health_report=health_report,
            scheduler=scheduler,
            communication=communication,
            errors=[],
        )
        root.set_startup_report(report)
        root.diagnostics.set_runtime_context(
            startup_time=started_at,
            configuration_summary=report["configuration_summary"],
            startup_report=report,
        )
        return BootstrapResult(root, copy.deepcopy(loaded), report)
    except Exception as exc:
        errors.append(str(exc))
        report = _build_report(
            success=False,
            root=root,
            configuration=loaded,
            required=required,
            started_at=started_at,
            completed_at=wall_clock(),
            duration_ms=(monotonic_clock() - started_mono) * 1000.0,
            config_source=config_source,
            health_report={},
            scheduler={},
            communication={},
            errors=errors,
        )
        if root is not None:
            shutdown_errors = _stop_safely(root)
            report["errors"].extend(shutdown_errors)
        raise BootstrapError("BX1 OS Alpha bootstrap failed: %s" % exc, report) from exc


def _build_report(
    *,
    success: bool,
    root: Optional[BX1],
    configuration: Mapping[str, Any],
    required: Set[str],
    started_at: float,
    completed_at: float,
    duration_ms: float,
    config_source: str,
    health_report: Mapping[str, Any],
    scheduler: Mapping[str, Any],
    communication: Mapping[str, Any],
    errors: Iterable[str],
) -> Dict[str, Any]:
    names = [] if root is None else root.services.names()
    states = (
        {}
        if root is None
        else {
            name: root.services.registration(name).state.value
            for name in names
        }
    )
    dependency_validation = (
        {"valid": False, "order": [], "graph": {}, "errors": ["root unavailable"]}
        if root is None
        else root.services.validate_dependencies()
    )
    return {
        "schema": "bx1.runtime.startup.v1",
        "milestone": "BX1 OS Alpha",
        "success": bool(success),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": round(max(0.0, duration_ms), 3),
        "config_source": str(config_source),
        "required_services": sorted(required),
        "registered_services": names,
        "service_states": states,
        "missing_services": sorted(required - set(names)),
        "dependency_graph": dependency_validation["graph"],
        "dependency_order": dependency_validation["order"],
        "dependency_valid": dependency_validation["valid"],
        "dependency_errors": dependency_validation["errors"],
        "scheduler": copy.deepcopy(dict(scheduler)),
        "communication": copy.deepcopy(dict(communication)),
        "health": copy.deepcopy(dict(health_report)),
        "configuration_summary": _configuration_summary(configuration),
        "errors": list(errors),
        "failed_safe": not success,
        "hardware_changes_requested": False,
    }


def _configuration_summary(config: Mapping[str, Any]) -> Dict[str, Any]:
    core = config.get("core_services", {})
    hardware = config.get("hardware_services", {})
    return {
        "top_level_key_count": len(config),
        "application_version": str(
            config.get("app_version", config.get("version", ""))
        ),
        "core_sections": (
            sorted(str(name) for name in core)
            if isinstance(core, Mapping)
            else []
        ),
        "hardware_services_configured": isinstance(hardware, Mapping),
        "communication_transport": (
            str(core.get("communication", {}).get("transport", "in_memory"))
            if isinstance(core, Mapping)
            and isinstance(core.get("communication"), Mapping)
            else "in_memory"
        ),
        "secrets_included": False,
    }


def _normalise_names(names: Iterable[str]) -> Set[str]:
    return {
        str(name).strip().lower()
        for name in names
        if str(name).strip()
    }


def _stop_safely(root: BX1) -> list[str]:
    try:
        root.services.stop_all()
        return []
    except Exception:
        errors = []
        for name in reversed(root.services.names()):
            try:
                root.services.stop(name, cascade=True)
            except Exception as exc:
                errors.append(
                    "safe shutdown could not stop %s: %s" % (name, exc)
                )
        return errors
