from __future__ import annotations

import copy
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Tuple, Union


class CoreEventType(str, Enum):
    STATE_CHANGED = "STATE_CHANGED"
    SERVICE_STARTED = "SERVICE_STARTED"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    BRAIN_CONNECTED = "BRAIN_CONNECTED"
    BRAIN_DISCONNECTED = "BRAIN_DISCONNECTED"
    PLUGIN_LOADED = "PLUGIN_LOADED"
    PLUGIN_UPDATED = "PLUGIN_UPDATED"
    PLUGIN_FAULT = "PLUGIN_FAULT"
    TELEMETRY_PUBLISHED = "TELEMETRY_PUBLISHED"


@dataclass(frozen=True)
class CoreEvent:
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "payload": copy.deepcopy(dict(self.payload)),
            "source": self.source,
            "timestamp": self.timestamp,
        }


EventName = Union[str, CoreEventType]
EventCallback = Callable[[CoreEvent], None]


class CoreEventBus:
    """Synchronous thread-safe event bus for Core state and lifecycle events."""

    WILDCARD = "*"

    def __init__(
        self,
        *,
        history_limit: int = 256,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        self._history: Deque[Dict[str, Any]] = deque(
            maxlen=max(1, int(history_limit))
        )
        self._subscriptions: Dict[str, Dict[str, EventCallback]] = defaultdict(
            dict
        )
        self._tokens: Dict[str, Tuple[str, EventCallback]] = {}
        self._published: Dict[str, int] = defaultdict(int)
        self._deliveries = 0
        self._failures = 0
        self._lock = threading.RLock()

    def subscribe(self, event_type: EventName, callback: EventCallback) -> str:
        if not callable(callback):
            raise TypeError("event callback must be callable")
        name = self._normalise(event_type)
        token = uuid.uuid4().hex
        with self._lock:
            self._subscriptions[name][token] = callback
            self._tokens[token] = (name, callback)
        return token

    def unsubscribe(
        self,
        subscription: str,
        callback: Optional[EventCallback] = None,
    ) -> bool:
        with self._lock:
            if callback is None and subscription in self._tokens:
                event_type, _ = self._tokens.pop(subscription)
                self._subscriptions[event_type].pop(subscription, None)
                return True
            name = self._normalise(subscription)
            removed = False
            for token, registered in list(
                self._subscriptions.get(name, {}).items()
            ):
                if registered is callback:
                    self._subscriptions[name].pop(token, None)
                    self._tokens.pop(token, None)
                    removed = True
            return removed

    def publish(
        self,
        event: Union[CoreEvent, EventName],
        payload: Optional[Mapping[str, Any]] = None,
        *,
        source: str = "",
    ) -> CoreEvent:
        item = (
            event
            if isinstance(event, CoreEvent)
            else CoreEvent(
                type=self._normalise(event),
                payload=copy.deepcopy(dict(payload or {})),
                source=str(source),
                timestamp=self._clock(),
            )
        )
        with self._lock:
            callbacks: List[Tuple[str, EventCallback]] = list(
                self._subscriptions.get(item.type, {}).items()
            )
            callbacks.extend(self._subscriptions.get(self.WILDCARD, {}).items())
            self._published[item.type] += 1

        failures: List[Dict[str, str]] = []
        delivered = 0
        for token, callback in callbacks:
            try:
                callback(item)
                delivered += 1
            except Exception as exc:
                failures.append({"subscription": token, "error": str(exc)})

        with self._lock:
            self._deliveries += delivered
            self._failures += len(failures)
            self._history.append(
                {
                    "event": item.as_dict(),
                    "delivered": delivered,
                    "failures": failures,
                }
            )
        return item

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "subscriber_count": len(self._tokens),
                "published": dict(sorted(self._published.items())),
                "deliveries": self._deliveries,
                "subscriber_failures": self._failures,
                "history": copy.deepcopy(list(self._history)),
            }

    @classmethod
    def _normalise(cls, event_type: EventName) -> str:
        name = (
            event_type.value
            if isinstance(event_type, CoreEventType)
            else str(event_type).strip()
        )
        if not name:
            raise ValueError("event type must not be empty")
        return name
