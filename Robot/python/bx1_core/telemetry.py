from __future__ import annotations

import copy
import time
from typing import Any, Callable, Dict, Optional

from .events import CoreEvent, CoreEventBus, CoreEventType
from .state import StateStore


class TelemetryPublisher:
    """Transport-neutral JSON telemetry for snapshots and incremental updates."""

    SNAPSHOT_SCHEMA = "bx1.core.telemetry.snapshot.v1"
    UPDATE_SCHEMA = "bx1.core.telemetry.update.v1"

    def __init__(
        self,
        state: StateStore,
        events: CoreEventBus,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.state = state
        self.events = events
        self._clock = clock

    def snapshot(self, prefix: Optional[str] = None) -> Dict[str, Any]:
        return {
            "schema": self.SNAPSHOT_SCHEMA,
            "generated_at": self._clock(),
            "revision": self.state.revision,
            "prefix": prefix,
            "state": self.state.snapshot(prefix),
        }

    def updates(
        self,
        since_revision: int,
        prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = self.state.changes_since(since_revision)
        if prefix is not None:
            key = str(prefix).strip().strip(".")
            result["changes"] = [
                item
                for item in result["changes"]
                if item["path"] == key or item["path"].startswith(key + ".")
            ]
        payload = {
            "schema": self.UPDATE_SCHEMA,
            "generated_at": self._clock(),
            "prefix": prefix,
            **result,
        }
        self.events.publish(
            CoreEventType.TELEMETRY_PUBLISHED,
            {
                "revision": payload["revision"],
                "since_revision": payload["since_revision"],
                "change_count": len(payload["changes"]),
                "resync_required": payload["resync_required"],
            },
            source="core.telemetry",
        )
        return payload

    def subscribe(self, callback: Callable[[CoreEvent], None]) -> str:
        """Subscribe a future transport adapter to state changes."""
        return self.events.subscribe(CoreEventType.STATE_CHANGED, callback)

    def unsubscribe(self, token: str) -> bool:
        return self.events.unsubscribe(token)

    @staticmethod
    def json_ready(value: Dict[str, Any]) -> Dict[str, Any]:
        """Return an isolated payload suitable for JSON encoders."""
        return copy.deepcopy(value)
