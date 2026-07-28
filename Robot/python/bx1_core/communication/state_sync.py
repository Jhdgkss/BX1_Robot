from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from hardware_services import Event, EventBus, EventType


@dataclass
class Subscription:
    subscription_id: str
    client_id: str
    topic: str
    callback: Optional[Callable[[Dict[str, Any]], None]]
    created_at: float
    update_count: int = 0
    last_error: str = ""
    last_value: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "client_id": self.client_id,
            "topic": self.topic,
            "created_at": self.created_at,
            "update_count": self.update_count,
            "last_error": self.last_error,
            "has_baseline": bool(self.last_value),
        }


class StateSynchronizer:
    TOPICS = {"battery", "health", "events", "diagnostics"}
    COMMUNICATION_EVENTS = {
        EventType.CLIENT_CONNECTED.value,
        EventType.CLIENT_DISCONNECTED.value,
        EventType.HEARTBEAT_TIMEOUT.value,
        EventType.MESSAGE_RECEIVED.value,
        EventType.MESSAGE_SENT.value,
        EventType.INVALID_MESSAGE.value,
        EventType.PROTOCOL_MISMATCH.value,
    }

    def __init__(
        self,
        bx1: Any,
        event_bus: EventBus,
        deliver: Callable[[str, str, Mapping[str, Any]], None],
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.bx1 = bx1
        self.events = event_bus
        self._deliver = deliver
        self._clock = clock
        self._subscriptions: Dict[str, Subscription] = {}
        self._last_values: Dict[str, str] = {}
        self._sequence = 0
        self._event_token = self.events.subscribe("*", self._on_event)

    def subscribe(
        self,
        topic: str,
        *,
        client_id: str = "local",
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        deliver_initial: bool = True,
    ) -> str:
        name = self._topic(topic)
        if callback is not None and not callable(callback):
            raise TypeError("subscription callback must be callable")
        subscription_id = uuid.uuid4().hex
        item = Subscription(
            subscription_id,
            str(client_id).strip() or "local",
            name,
            callback,
            self._clock(),
        )
        self._subscriptions[subscription_id] = item
        if deliver_initial and name != "events":
            value = self._snapshot(name)
            self._emit(item, value)
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        return self._subscriptions.pop(str(subscription_id), None) is not None

    def publish(self, topic: str, value: Mapping[str, Any]) -> int:
        return self._publish_topic(self._topic(topic), dict(value), changed_only=False)

    def sync(self) -> Dict[str, Any]:
        updates: Dict[str, int] = {}
        for topic in ("battery", "health", "diagnostics"):
            value = self._snapshot(topic)
            updates[topic] = self._publish_topic(
                topic,
                value,
                changed_only=True,
            )
        return {"updates": updates, "sequence": self._sequence}

    def status(self) -> Dict[str, Any]:
        return {
            "service": "state_synchronizer",
            "state": "READY",
            "subscription_count": len(self._subscriptions),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "available": True,
            "state": "READY",
            "reason": "State synchronizer ready",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "subscription_count": len(self._subscriptions),
            "sequence": self._sequence,
            "subscriptions": {
                key: value.as_dict()
                for key, value in sorted(self._subscriptions.items())
            },
        }

    def configuration(self) -> Dict[str, Any]:
        return {"topics": sorted(self.TOPICS), "event_delivery": True}

    def _snapshot(self, topic: str) -> Dict[str, Any]:
        if topic == "battery":
            return {
                "status": self.bx1.battery.status(),
                "health": self.bx1.battery.health(),
                "cells": self.bx1.battery.cell_voltages(),
            }
        if topic == "health":
            return {
                "status": self.bx1.health.status(),
                "diagnostics": self.bx1.health.diagnostics(),
            }
        if topic == "diagnostics":
            return self.bx1.diagnostics.report()
        raise ValueError("events are delivered from the Event Bus")

    def _on_event(self, event: Event) -> None:
        if event.type in self.COMMUNICATION_EVENTS:
            return
        self._publish_topic(
            "events",
            {
                "type": event.type,
                "payload": dict(event.payload),
                "source": event.source,
                "timestamp": event.timestamp,
            },
            changed_only=False,
        )

    def _publish_topic(
        self,
        topic: str,
        value: Mapping[str, Any],
        *,
        changed_only: bool,
    ) -> int:
        canonical = self._canonical(value)
        self._last_values[topic] = canonical
        delivered = 0
        for item in list(self._subscriptions.values()):
            if (
                item.topic == topic
                and (not changed_only or item.last_value != canonical)
            ):
                self._emit(item, value)
                delivered += 1
        return delivered

    def _emit(self, item: Subscription, value: Mapping[str, Any]) -> None:
        self._sequence += 1
        update = {
            "topic": item.topic,
            "sequence": self._sequence,
            "timestamp": self._clock(),
            "value": copy.deepcopy(dict(value)),
        }
        try:
            if item.callback is not None:
                item.callback(copy.deepcopy(update))
            if item.client_id != "local":
                self._deliver(item.client_id, item.topic, update)
            item.update_count += 1
            item.last_error = ""
            item.last_value = self._canonical(value)
        except Exception as exc:
            item.last_error = str(exc)

    @classmethod
    def _topic(cls, value: str) -> str:
        topic = str(value).strip().lower()
        aliases = {
            "subscribe battery": "battery",
            "subscribe health": "health",
            "subscribe events": "events",
            "subscribe diagnostics": "diagnostics",
        }
        topic = aliases.get(topic, topic)
        if topic not in cls.TOPICS:
            raise ValueError("unsupported state subscription topic: %s" % value)
        return topic

    @staticmethod
    def _canonical(value: Mapping[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
