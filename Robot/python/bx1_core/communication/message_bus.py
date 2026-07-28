from __future__ import annotations

import copy
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Mapping, Optional


@dataclass(frozen=True)
class MessageEnvelope:
    destination: str
    encoded: str
    queued_at: float


class MessageBus:
    """Bounded in-memory transport. It performs no network or filesystem I/O."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = {
            "mode": "in_memory",
            "maximum_queued_messages": 1000,
            **dict(config or {}),
        }
        if str(self._config["mode"]).lower() != "in_memory":
            raise ValueError("Phase 4 MessageBus supports in_memory mode only")
        self._clock = clock
        self._queue: Deque[MessageEnvelope] = deque(
            maxlen=max(1, int(self._config["maximum_queued_messages"]))
        )
        self._sent_count = 0
        self._received_count = 0
        self._dropped_count = 0

    def send(self, destination: str, encoded: str) -> None:
        if len(self._queue) == self._queue.maxlen:
            self._dropped_count += 1
        self._queue.append(
            MessageEnvelope(str(destination), str(encoded), self._clock())
        )
        self._sent_count += 1

    def publish(self, destination: str, encoded: str) -> None:
        self.send(destination, encoded)

    def receive(self, destination: Optional[str] = None) -> Optional[str]:
        if not self._queue:
            return None
        if destination is None:
            item = self._queue.popleft()
            self._received_count += 1
            return item.encoded
        target = str(destination)
        count = len(self._queue)
        found: Optional[MessageEnvelope] = None
        for _ in range(count):
            item = self._queue.popleft()
            if found is None and item.destination == target:
                found = item
            else:
                self._queue.append(item)
        if found is not None:
            self._received_count += 1
            return found.encoded
        return None

    def pending(self, destination: Optional[str] = None) -> int:
        if destination is None:
            return len(self._queue)
        return sum(item.destination == str(destination) for item in self._queue)

    def status(self) -> Dict[str, Any]:
        return {
            "service": "message_bus",
            "state": "READY",
            "mode": "in_memory",
            "pending": len(self._queue),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "available": True,
            "state": "READY",
            "reason": "In-memory message bus ready",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "mode": "in_memory",
            "pending": len(self._queue),
            "sent_count": self._sent_count,
            "received_count": self._received_count,
            "dropped_count": self._dropped_count,
            "network_used": False,
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)
