from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .events import CoreEventBus
from .health import aggregate_plugin_health
from .plugins.base import PluginContext
from .plugins.registry import PluginRegistry
from .registry import CoreServiceRegistry, ServiceProvider
from .scheduler import SchedulerService
from .state import StateStore
from .telemetry import TelemetryPublisher


class BX1Core:
    """Observer-only telemetry composition root and single state authority."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        install_root: Optional[Path] = None,
        service_provider: Optional[ServiceProvider] = None,
        plugin_metadata: Optional[Mapping[str, Any]] = None,
        update_interval: Optional[float] = None,
        clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = copy.deepcopy(dict(config or {}))
        self.clock = clock
        self.monotonic_clock = monotonic_clock
        self.started_at = clock()
        configured_root = self.config.get(
            "install_root", "/home/arduino/BX1_OS"
        )
        self.install_root = Path(
            configured_root if install_root is None else install_root
        )
        telemetry_config = self.config.get("core_telemetry", {})
        interval = (
            telemetry_config.get("update_interval_seconds", 2.0)
            if isinstance(telemetry_config, Mapping)
            else 2.0
        )
        self.update_interval = max(
            0.1,
            float(interval if update_interval is None else update_interval),
        )
        self.events = CoreEventBus(clock=clock)
        self.state = StateStore(events=self.events, clock=clock)
        self.telemetry = TelemetryPublisher(
            self.state, self.events, clock=clock
        )
        context = PluginContext(
            state=self.state,
            events=self.events,
            config=self.config,
            install_root=self.install_root,
            started_at=self.started_at,
            clock=clock,
            monotonic_clock=monotonic_clock,
            metadata=dict(plugin_metadata or {}),
        )
        self.plugins = PluginRegistry(context)
        self.services = CoreServiceRegistry(
            self.state, service_provider, events=self.events
        )
        self.scheduler = SchedulerService(clock=monotonic_clock)
        self._running = False
        self._update_lock = threading.Lock()
        self._scheduler_lock = threading.Lock()
        self.plugins.discover()
        self.update()
        self._scheduled_update = self.scheduler.schedule_periodic(
            self.update_interval,
            self.update,
            name="bx1_core_telemetry_update",
        )

    def start(self) -> None:
        self._running = True
        self.state.set(
            "core.running",
            True,
            source="core.runtime",
        )

    def stop(self) -> Dict[str, str]:
        self._running = False
        self.scheduler.cancel(self._scheduled_update)
        self.state.set("core.running", False, source="core.runtime")
        return self.plugins.shutdown()

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Run due telemetry work cooperatively; no worker thread is created."""
        with self._scheduler_lock:
            return self.scheduler.tick(now)

    def update(self) -> Dict[str, Any]:
        if not self._update_lock.acquire(blocking=False):
            return {"updated": [], "faults": {}, "skipped": "update_in_progress"}
        try:
            result = self.plugins.update()
            try:
                services = self.services.update()
            except Exception as exc:
                services = []
                result["faults"]["services"] = str(exc)
            self.state.set_many(
                {
                    "core.running": self._running,
                    "core.updated_at": self.clock(),
                    "core.update_interval_seconds": self.update_interval,
                    "core.plugin_count": len(self.plugins.names()),
                    "core.service_count": len(services),
                },
                source="core.runtime",
            )
            return result
        finally:
            self._update_lock.release()

    def state_snapshot(self) -> Dict[str, Any]:
        self.tick()
        return self.telemetry.snapshot()

    def health_snapshot(self) -> Dict[str, Any]:
        return aggregate_plugin_health(
            self.plugins.health(), timestamp=self.clock()
        )

    def plugin_snapshot(self) -> Dict[str, Any]:
        return self.plugins.snapshot()

    def service_snapshot(self) -> Dict[str, Any]:
        return self.services.snapshot()

    def system_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.system.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "system": self.state.snapshot("system"),
            "network": self.state.snapshot("network"),
            "robot": self.state.snapshot("robot"),
        }

    def hardware_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.hardware.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "hardware": self.state.snapshot("hardware"),
        }

    def hardware_inventory_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.hardware.inventory.api.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "inventory": self.state.get("hardware.inventory", {}),
            "diagnostics": self.state.get("hardware.diagnostics", {}),
        }

    def audio_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.audio.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "audio": self.state.snapshot("audio"),
            "devices": self.state.snapshot("hardware.audio"),
        }

    def audio_devices_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.audio.devices.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "microphones": self.state.get(
                "hardware.audio.microphones", {}
            ),
            "speakers": self.state.get("hardware.audio.speakers", {}),
        }

    def robot_body_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.robot_body.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "robot_body": self.state.snapshot("robot_body"),
        }

    def robot_body_health_snapshot(self) -> Dict[str, Any]:
        return {
            "schema": "bx1.core.robot_body.health.v1",
            "generated_at": self.clock(),
            "revision": self.state.revision,
            "connected": self.state.get("robot_body.connected", {}),
            "health": self.state.get("robot_body.health", {}),
            "active_faults": self.state.get(
                "robot_body.active_faults", {}
            ),
        }

__all__ = ["BX1Core"]
