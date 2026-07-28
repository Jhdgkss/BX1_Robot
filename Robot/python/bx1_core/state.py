from __future__ import annotations

import copy
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional

from .events import CoreEventBus, CoreEventType


DEFAULT_STATE: Dict[str, Any] = {
    "system.cpu": None,
    "system.memory": None,
    "system.disk": None,
    "system.temperature": None,
    "system.uptime": None,
    "system.python": None,
    "system.os": None,
    "system.kernel": None,
    "system.architecture": None,
    "system.hostname": None,
    "system.serial": None,
    "brain.connected": False,
    "brain.model": None,
    "brain.speaking": False,
    "brain.listening": False,
    "brain.thinking": False,
    "network.ip": None,
    "network.signal": None,
    "network.state": "unknown",
    "robot.mode": "observer_only",
    "robot.state": "qualification",
    "robot.enabled": False,
    "hardware.camera": "unavailable",
    "hardware.microphone": "unavailable",
    "hardware.speaker": "unavailable",
    "hardware.touchscreen": "unavailable",
    "hardware.imu": "unavailable",
    "hardware.servos": "blocked",
    "hardware.motors": "blocked",
    "deployment.version": None,
    "deployment.tag": None,
    "deployment.branch": None,
    "deployment.commit": None,
    "deployment.build_date": None,
}


@dataclass(frozen=True)
class StateChange:
    revision: int
    path: str
    old_value: Any
    value: Any
    source: str
    timestamp: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "revision": self.revision,
            "path": self.path,
            "old_value": copy.deepcopy(self.old_value),
            "value": copy.deepcopy(self.value),
            "source": self.source,
            "timestamp": self.timestamp,
        }


class StateStore:
    """Thread-safe single source of truth with revisioned change history."""

    def __init__(
        self,
        initial: Optional[Mapping[str, Any]] = None,
        *,
        events: Optional[CoreEventBus] = None,
        history_limit: int = 2048,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._values: Dict[str, Any] = {}
        self._revision = 0
        self._history: Deque[StateChange] = deque(
            maxlen=max(1, int(history_limit))
        )
        self._events = events
        self._clock = clock
        self._lock = threading.RLock()
        seed = dict(DEFAULT_STATE)
        seed.update(dict(initial or {}))
        self.set_many(seed, source="core.bootstrap")

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def set(self, path: str, value: Any, *, source: str) -> Optional[StateChange]:
        changes = self.set_many({path: value}, source=source)
        return changes[0] if changes else None

    def set_many(
        self,
        values: Mapping[str, Any],
        *,
        source: str,
    ) -> List[StateChange]:
        origin = str(source).strip()
        if not origin:
            raise ValueError("state source must not be empty")
        published: List[StateChange] = []
        with self._lock:
            for raw_path, raw_value in values.items():
                path = self._normalise_path(raw_path)
                value = copy.deepcopy(raw_value)
                old = self._values.get(path)
                if path in self._values and old == value:
                    continue
                self._revision += 1
                change = StateChange(
                    revision=self._revision,
                    path=path,
                    old_value=copy.deepcopy(old),
                    value=value,
                    source=origin,
                    timestamp=self._clock(),
                )
                self._values[path] = value
                self._history.append(change)
                published.append(change)
        if self._events is not None:
            for change in published:
                self._events.publish(
                    CoreEventType.STATE_CHANGED,
                    change.as_dict(),
                    source=origin,
                )
        return published

    def get(self, path: str, default: Any = None) -> Any:
        key = self._normalise_path(path)
        with self._lock:
            return copy.deepcopy(self._values.get(key, default))

    def flat_snapshot(self, prefix: Optional[str] = None) -> Dict[str, Any]:
        selected = None if prefix is None else self._normalise_path(prefix)
        with self._lock:
            return {
                path: copy.deepcopy(value)
                for path, value in sorted(self._values.items())
                if selected is None
                or path == selected
                or path.startswith(selected + ".")
            }

    def snapshot(self, prefix: Optional[str] = None) -> Dict[str, Any]:
        selected = None if prefix is None else self._normalise_path(prefix)
        flat = self.flat_snapshot(selected)
        result: Dict[str, Any] = {}
        for path, value in flat.items():
            parts = path.split(".")
            if selected is not None:
                selected_parts = selected.split(".")
                parts = parts[len(selected_parts) :]
                if not parts:
                    if isinstance(value, dict):
                        result.update(copy.deepcopy(value))
                    else:
                        result["value"] = copy.deepcopy(value)
                    continue
            cursor = result
            for part in parts[:-1]:
                existing = cursor.get(part)
                if not isinstance(existing, dict):
                    existing = {}
                    cursor[part] = existing
                cursor = existing
            cursor[parts[-1]] = copy.deepcopy(value)
        return result

    def changes_since(self, revision: int) -> Dict[str, Any]:
        requested = max(0, int(revision))
        with self._lock:
            current = self._revision
            first_available = (
                self._history[0].revision if self._history else current + 1
            )
            resync = requested < first_available - 1
            changes = (
                []
                if resync
                else [
                    item.as_dict()
                    for item in self._history
                    if item.revision > requested
                ]
            )
        return {
            "since_revision": requested,
            "revision": current,
            "first_available_revision": first_available,
            "resync_required": resync,
            "changes": changes,
        }

    @staticmethod
    def _normalise_path(path: Any) -> str:
        value = str(path).strip().strip(".")
        parts = value.split(".")
        if not value or any(not part.strip() for part in parts):
            raise ValueError("state path must be a non-empty dotted path")
        return ".".join(part.strip() for part in parts)
