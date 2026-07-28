from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Tuple, Union


class EventType(str, Enum):
    WAKE_DETECTED = "WakeDetected"
    SPEECH_STARTED = "SpeechStarted"
    SPEECH_FINISHED = "SpeechFinished"
    THINKING_STARTED = "ThinkingStarted"
    THINKING_FINISHED = "ThinkingFinished"
    HARDWARE_FAULT = "HardwareFault"
    BATTERY_LOW = "BatteryLow"
    BATTERY_CRITICAL = "BatteryCritical"
    BATTERY_CHARGING = "BatteryCharging"
    BATTERY_FULL = "BatteryFull"
    BATTERY_FAULT = "BatteryFault"
    POWER_RAIL_FAULT = "PowerRailFault"
    POWER_RESTORED = "PowerRestored"
    SHUTDOWN_REQUESTED = "ShutdownRequested"
    SHUTDOWN_CANCELLED = "ShutdownCancelled"
    BATTERY_REMOVED = "BatteryRemoved"
    BATTERY_INSERTED = "BatteryInserted"
    SERVICE_HEALTH_CHANGED = "ServiceHealthChanged"
    SERVICE_FAULT = "ServiceFault"
    SERVICE_RECOVERED = "ServiceRecovered"
    SERVICE_MISSING = "ServiceMissing"
    SERVICE_STALE = "ServiceStale"
    CLIENT_CONNECTED = "ClientConnected"
    CLIENT_DISCONNECTED = "ClientDisconnected"
    HEARTBEAT_TIMEOUT = "HeartbeatTimeout"
    MESSAGE_RECEIVED = "MessageReceived"
    MESSAGE_SENT = "MessageSent"
    INVALID_MESSAGE = "InvalidMessage"
    PROTOCOL_MISMATCH = "ProtocolMismatch"
    OBSTACLE_DETECTED = "ObstacleDetected"
    ROBOT_READY = "RobotReady"
    ROBOT_SLEEPING = "RobotSleeping"


@dataclass(frozen=True)
class Event:
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: float = field(default_factory=time.time)


EventName = Union[str, EventType]
EventCallback = Callable[[Event], None]


class EventBus:
    """Synchronous, thread-safe event bus with isolated subscriber failures."""

    WILDCARD = "*"

    def __init__(self, *, history_limit: int = 100) -> None:
        self._history_limit = max(1, int(history_limit))
        self._subscriptions: Dict[str, Dict[str, EventCallback]] = defaultdict(dict)
        self._tokens: Dict[str, Tuple[str, EventCallback]] = {}
        self._published: Dict[str, int] = defaultdict(int)
        self._delivery_count = 0
        self._failure_count = 0
        self._history: Deque[Dict[str, Any]] = deque(maxlen=self._history_limit)
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
        """Remove a token, or remove a callback from a named event."""
        with self._lock:
            if callback is None and subscription in self._tokens:
                event_type, _ = self._tokens.pop(subscription)
                self._subscriptions[event_type].pop(subscription, None)
                return True

            name = self._normalise(subscription)
            removed = False
            for token, registered in list(self._subscriptions.get(name, {}).items()):
                if registered is callback:
                    self._subscriptions[name].pop(token, None)
                    self._tokens.pop(token, None)
                    removed = True
            return removed

    def publish(
        self,
        event: Union[Event, EventName],
        payload: Optional[Mapping[str, Any]] = None,
        *,
        source: str = "",
    ) -> Event:
        item = (
            event
            if isinstance(event, Event)
            else Event(self._normalise(event), dict(payload or {}), str(source))
        )
        with self._lock:
            callbacks: List[Tuple[str, EventCallback]] = list(
                self._subscriptions.get(item.type, {}).items()
            )
            callbacks.extend(self._subscriptions.get(self.WILDCARD, {}).items())
            self._published[item.type] += 1

        errors: List[str] = []
        delivered = 0
        for token, callback in callbacks:
            try:
                callback(item)
                delivered += 1
            except Exception as exc:
                errors.append("%s: %s" % (token, exc))

        with self._lock:
            self._delivery_count += delivered
            self._failure_count += len(errors)
            self._history.append(
                {
                    "type": item.type,
                    "source": item.source,
                    "timestamp": item.timestamp,
                    "delivered": delivered,
                    "failures": errors,
                }
            )
        return item

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "subscriber_count": len(self._tokens),
                "subscriptions": {
                    name: len(callbacks)
                    for name, callbacks in sorted(self._subscriptions.items())
                    if callbacks
                },
                "published": dict(sorted(self._published.items())),
                "deliveries": self._delivery_count,
                "subscriber_failures": self._failure_count,
                "history": list(self._history),
            }

    def status(self) -> Dict[str, Any]:
        return {"service": "event_bus", "state": "READY", "reason": "Event bus available"}

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "healthy": True,
                "available": True,
                "state": "READY",
                "subscriber_failures": self._failure_count,
            }

    def configuration(self) -> Dict[str, Any]:
        return {"history_limit": self._history_limit, "synchronous_delivery": True}

    @classmethod
    def _normalise(cls, event_type: EventName) -> str:
        if isinstance(event_type, EventType):
            return event_type.value
        name = str(event_type).strip()
        if not name:
            raise ValueError("event type must not be empty")
        return name
