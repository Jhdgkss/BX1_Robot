from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set


class ServiceLifecycleState(str, Enum):
    REGISTERED = "REGISTERED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAULT = "FAULT"


@dataclass
class ServiceRegistration:
    name: str
    service: Any
    dependencies: Set[str] = field(default_factory=set)
    state: ServiceLifecycleState = ServiceLifecycleState.REGISTERED
    registered_at: float = 0.0
    changed_at: float = 0.0
    error: str = ""

    def as_dict(self, *, include_service: bool = False) -> Dict[str, Any]:
        value = {
            "name": self.name,
            "dependencies": sorted(self.dependencies),
            "state": self.state.value,
            "registered_at": self.registered_at,
            "changed_at": self.changed_at,
            "error": self.error,
            "service_type": type(self.service).__name__,
        }
        if include_service:
            value["service"] = self.service
        return value


class ServiceRegistry:
    """Discovery, dependency and lifecycle authority for BX1 services."""

    def __init__(self, config: Optional[Mapping[str, Any]] = None) -> None:
        self._config = {
            "allow_replace": False,
            "auto_start": True,
            **dict(config or {}),
        }
        self._services: Dict[str, ServiceRegistration] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        service: Any,
        *,
        dependencies: Optional[Iterable[str]] = None,
        replace: Optional[bool] = None,
    ) -> Any:
        key = self._normalise(name)
        deps = {self._normalise(item) for item in (dependencies or [])}
        if key in deps:
            raise ValueError("service cannot depend on itself: %s" % key)
        allow_replace = (
            bool(self._config["allow_replace"]) if replace is None else bool(replace)
        )
        now = time.monotonic()
        with self._lock:
            if key in self._services and not allow_replace:
                raise ValueError("service is already registered: %s" % key)
            self._services[key] = ServiceRegistration(
                key,
                service,
                deps,
                ServiceLifecycleState.REGISTERED,
                now,
                now,
            )
        return service

    def unregister(self, name: str, *, force: bool = False) -> Any:
        key = self._normalise(name)
        with self._lock:
            registration = self._require(key)
            dependents = self.dependents(key)
            if dependents and not force:
                raise RuntimeError(
                    "cannot unregister %s; required by %s"
                    % (key, ", ".join(sorted(dependents)))
                )
            if registration.state == ServiceLifecycleState.RUNNING:
                self.stop(key, cascade=force)
            return self._services.pop(key).service

    def service(self, name: str) -> Any:
        return self.get(name)

    def get(self, name: str, default: Any = None, *, required: bool = True) -> Any:
        key = self._normalise(name)
        with self._lock:
            item = self._services.get(key)
            if item is None:
                if required:
                    raise KeyError("service is not registered: %s" % key)
                return default
            return item.service

    def has(self, name: str) -> bool:
        with self._lock:
            return self._normalise(name) in self._services

    def discover(self) -> Dict[str, Any]:
        with self._lock:
            return {
                name: registration.service
                for name, registration in sorted(self._services.items())
            }

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._services)

    def registration(self, name: str) -> ServiceRegistration:
        with self._lock:
            item = self._require(self._normalise(name))
            return ServiceRegistration(
                item.name,
                item.service,
                set(item.dependencies),
                item.state,
                item.registered_at,
                item.changed_at,
                item.error,
            )

    def dependencies(self, name: str) -> Set[str]:
        return set(self.registration(name).dependencies)

    def dependents(self, name: str) -> Set[str]:
        key = self._normalise(name)
        with self._lock:
            return {
                item.name
                for item in self._services.values()
                if key in item.dependencies
            }

    def start(self, name: str) -> Any:
        return self._start(self._normalise(name), stack=[])

    def _start(self, name: str, stack: List[str]) -> Any:
        with self._lock:
            item = self._require(name)
            if item.state == ServiceLifecycleState.RUNNING:
                return item.service
            if name in stack:
                raise RuntimeError("service dependency cycle: %s" % " -> ".join(stack + [name]))
            missing = [dependency for dependency in item.dependencies if dependency not in self._services]
            if missing:
                raise RuntimeError(
                    "service %s has missing dependencies: %s"
                    % (name, ", ".join(sorted(missing)))
                )
            dependencies = sorted(item.dependencies)

        for dependency in dependencies:
            self._start(dependency, stack + [name])

        with self._lock:
            item = self._require(name)
            item.state = ServiceLifecycleState.STARTING
            item.changed_at = time.monotonic()
            item.error = ""
            try:
                start = getattr(item.service, "start", None)
                if callable(start):
                    start()
                item.state = ServiceLifecycleState.RUNNING
            except Exception as exc:
                item.state = ServiceLifecycleState.FAULT
                item.error = str(exc)
                raise
            finally:
                item.changed_at = time.monotonic()
            return item.service

    def stop(self, name: str, *, cascade: bool = False) -> Any:
        key = self._normalise(name)
        with self._lock:
            active_dependents = {
                dependency
                for dependency in self.dependents(key)
                if self._services[dependency].state == ServiceLifecycleState.RUNNING
            }
            if active_dependents and not cascade:
                raise RuntimeError(
                    "cannot stop %s; running dependents: %s"
                    % (key, ", ".join(sorted(active_dependents)))
                )
        if cascade:
            for dependent in sorted(active_dependents):
                self.stop(dependent, cascade=True)

        with self._lock:
            item = self._require(key)
            if item.state in {
                ServiceLifecycleState.STOPPED,
                ServiceLifecycleState.REGISTERED,
            }:
                item.state = ServiceLifecycleState.STOPPED
                return item.service
            item.state = ServiceLifecycleState.STOPPING
            item.changed_at = time.monotonic()
            try:
                stop = getattr(item.service, "stop", None)
                if callable(stop):
                    stop()
                item.state = ServiceLifecycleState.STOPPED
                item.error = ""
            except Exception as exc:
                item.state = ServiceLifecycleState.FAULT
                item.error = str(exc)
                raise
            finally:
                item.changed_at = time.monotonic()
            return item.service

    def start_all(self) -> List[str]:
        order = self._topological_order()
        for name in order:
            self.start(name)
        return order

    def stop_all(self) -> List[str]:
        order = list(reversed(self._topological_order()))
        for name in order:
            self.stop(name, cascade=True)
        return order

    def status(self) -> Dict[str, Any]:
        with self._lock:
            faulted = [
                name
                for name, item in self._services.items()
                if item.state == ServiceLifecycleState.FAULT
            ]
            return {
                "service": "service_registry",
                "state": "FAULT" if faulted else "READY",
                "registered_count": len(self._services),
                "running_count": sum(
                    item.state == ServiceLifecycleState.RUNNING
                    for item in self._services.values()
                ),
                "faulted": sorted(faulted),
            }

    def health(self) -> Dict[str, Any]:
        status = self.status()
        return {
            "healthy": status["state"] == "READY",
            "available": True,
            "state": status["state"],
            "reason": (
                "Service registry ready"
                if status["state"] == "READY"
                else "Lifecycle faults: %s" % ", ".join(status["faulted"])
            ),
        }

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            missing = {
                name: sorted(
                    dependency
                    for dependency in item.dependencies
                    if dependency not in self._services
                )
                for name, item in self._services.items()
            }
            missing = {name: value for name, value in missing.items() if value}
            return {
                "services": {
                    name: item.as_dict()
                    for name, item in sorted(self._services.items())
                },
                "missing_dependencies": missing,
            }

    def dependency_graph(self) -> Dict[str, List[str]]:
        with self._lock:
            return {
                name: sorted(item.dependencies)
                for name, item in sorted(self._services.items())
            }

    def validate_dependencies(self) -> Dict[str, Any]:
        try:
            order = self._topological_order()
            return {
                "valid": True,
                "order": order,
                "graph": self.dependency_graph(),
                "errors": [],
            }
        except RuntimeError as exc:
            return {
                "valid": False,
                "order": [],
                "graph": self.dependency_graph(),
                "errors": [str(exc)],
            }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _topological_order(self) -> List[str]:
        with self._lock:
            unresolved = {
                name: set(item.dependencies)
                for name, item in self._services.items()
            }
        missing = sorted(
            {
                dependency
                for dependencies in unresolved.values()
                for dependency in dependencies
                if dependency not in unresolved
            }
        )
        if missing:
            raise RuntimeError("missing service dependencies: %s" % ", ".join(missing))
        order: List[str] = []
        while unresolved:
            ready = sorted(
                name for name, dependencies in unresolved.items() if not dependencies
            )
            if not ready:
                raise RuntimeError(
                    "service dependency cycle: %s" % ", ".join(sorted(unresolved))
                )
            for name in ready:
                order.append(name)
                unresolved.pop(name)
            for dependencies in unresolved.values():
                dependencies.difference_update(ready)
        return order

    def _require(self, name: str) -> ServiceRegistration:
        try:
            return self._services[name]
        except KeyError as exc:
            raise KeyError("service is not registered: %s" % name) from exc

    @staticmethod
    def _normalise(name: str) -> str:
        key = str(name).strip().lower()
        if not key:
            raise ValueError("service name must not be empty")
        return key
