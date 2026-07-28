from __future__ import annotations

import copy
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional


DEFAULT_CAPABILITIES: Dict[str, bool] = {
    "imu": True,
    "range_sensor": False,
    "battery_monitor": True,
    "smart_bms": False,
    "wheel_encoders": False,
    "camera": True,
    "microphone": True,
    "speaker": True,
    "power_monitor": True,
}


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    simulated: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["metadata"] = dict(self.metadata)
        return value


class CapabilityRegistry:
    """Thread-safe discovery registry for optional BX1 hardware capabilities."""

    def __init__(
        self,
        capabilities: Optional[Mapping[str, Any]] = None,
        *,
        simulated: bool = False,
    ) -> None:
        self._items: Dict[str, Capability] = {}
        self._lock = threading.RLock()
        source = DEFAULT_CAPABILITIES if capabilities is None else capabilities
        for name, value in source.items():
            if isinstance(value, Mapping):
                self.register(
                    name,
                    bool(value.get("available", False)),
                    simulated=bool(value.get("simulated", simulated)),
                    metadata=dict(value.get("metadata") or {}),
                )
            else:
                self.register(name, bool(value), simulated=simulated)

    def register(
        self,
        name: str,
        available: bool,
        *,
        simulated: bool = False,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Capability:
        key = self._normalise(name)
        item = Capability(key, bool(available), bool(simulated), dict(metadata or {}))
        with self._lock:
            self._items[key] = item
        return item

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._items.pop(self._normalise(name), None) is not None

    def has(self, name: str) -> bool:
        with self._lock:
            item = self._items.get(self._normalise(name))
            return bool(item and item.available)

    def get(self, name: str) -> Optional[Capability]:
        with self._lock:
            return self._items.get(self._normalise(name))

    def query(self, **requirements: bool) -> bool:
        return all(self.has(name) == bool(required) for name, required in requirements.items())

    def capabilities(self) -> Dict[str, bool]:
        with self._lock:
            return {name: item.available for name, item in sorted(self._items.items())}

    def status(self) -> Dict[str, Any]:
        return {
            "service": "capability_registry",
            "state": "READY",
            "capability_count": len(self._items),
            "available_count": sum(self.capabilities().values()),
        }

    def health(self) -> Dict[str, Any]:
        return {"healthy": True, "available": True, "state": "READY"}

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "capabilities": {
                    name: item.as_dict() for name, item in sorted(self._items.items())
                }
            }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self.diagnostics()["capabilities"])

    @staticmethod
    def _normalise(name: str) -> str:
        key = str(name).strip().lower()
        if not key:
            raise ValueError("capability name must not be empty")
        return key
