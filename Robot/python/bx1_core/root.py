from __future__ import annotations

import copy
import time
from typing import Any, Dict, Mapping, Optional

from hardware_services import create_hardware_services, create_power_services

from .config import load_core_configuration
from .communication import CommunicationService
from .diagnostics import DiagnosticsService
from .health import HealthMonitor
from .logging_service import LoggingService
from .scheduler import SchedulerService
from .service_registry import ServiceRegistry


class BX1:
    """Single public composition root for BX1 OS services."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        monotonic_clock=time.monotonic,
        wall_clock=time.time,
    ) -> None:
        self._wall_clock = wall_clock
        self._started_at = wall_clock()
        self._startup_report: Dict[str, Any] = {}
        self._source_config = copy.deepcopy(dict(config or {}))
        self._core_config = load_core_configuration(config)

        hardware = create_hardware_services(
            dict(config or {}),
            clock=monotonic_clock,
        )
        power_services = create_power_services(
            dict(config or {}),
            event_bus=hardware.event_bus,
            clock=monotonic_clock,
        )

        self.events = hardware.event_bus
        self.led = hardware.leds
        self.drive = hardware.drive
        self.range = hardware.range
        self.power = power_services.power
        self.battery = power_services.battery
        self.capabilities = power_services.capabilities
        self.scheduler = SchedulerService(
            self._core_config["scheduler"],
            clock=monotonic_clock,
        )
        self.logging = LoggingService(
            self._core_config["logging"],
            clock=wall_clock,
        )
        self.services = ServiceRegistry(self._core_config["service_registry"])

        self.services.register("events", self.events)
        self.services.register("capabilities", self.capabilities)
        self.services.register("logging", self.logging)
        self.services.register("scheduler", self.scheduler)
        self.services.register("led", self.led, dependencies={"events"})
        self.services.register("drive", self.drive, dependencies={"logging"})
        self.services.register("range", self.range)
        self.services.register(
            "battery",
            self.battery,
            dependencies={"events", "capabilities"},
        )
        self.services.register(
            "power",
            self.power,
            dependencies={"battery", "events", "capabilities"},
        )

        self.diagnostics = DiagnosticsService(
            self.services,
            self._core_config["diagnostics"],
            clock=wall_clock,
        )
        self.services.register("diagnostics", self.diagnostics)
        self.health = HealthMonitor(
            self.services,
            self.events,
            self._core_config["health_monitor"],
            clock=wall_clock,
        )
        self.services.register(
            "health",
            self.health,
            dependencies={"events", "diagnostics"},
        )
        self.communication = CommunicationService(
            self,
            self.events,
            self._core_config["communication"],
            monotonic_clock=monotonic_clock,
            wall_clock=wall_clock,
        )
        self.services.register(
            "communication",
            self.communication,
            dependencies={
                "events",
                "capabilities",
                "scheduler",
                "diagnostics",
                "health",
            },
        )
        self.diagnostics.set_runtime_context(
            startup_time=self._started_at,
            configuration_summary={
                "mode": "digital_twin",
                "core_sections": sorted(self._core_config),
                "communication_transport": self._core_config[
                    "communication"
                ]["transport"],
                "secrets_included": False,
            },
        )

        if bool(self._core_config["service_registry"]["auto_start"]):
            self.services.start_all()
        self.health.check()
        if bool(self._core_config["health_monitor"]["enabled"]):
            self.scheduler.schedule_periodic(
                self._core_config["health_monitor"]["interval_s"],
                self.health.check,
                name="bx1_health_monitor",
            )
        if bool(self._core_config["communication"]["enabled"]):
            self.scheduler.schedule_periodic(
                self._core_config["communication"]["state_sync_interval_s"],
                self.communication.tick,
                name="bx1_communication_tick",
            )
        self.logging.info(
            "BX1 core services ready in Digital Twin mode",
            service="bx1",
            service_count=len(self.services.names()),
        )

    def service(self, name: str) -> Any:
        return self.services.service(name)

    def attach(
        self,
        name: str,
        service: Any,
        *,
        dependencies: Optional[set[str]] = None,
        start: bool = True,
    ) -> Any:
        self.services.register(name, service, dependencies=dependencies)
        if start:
            self.services.start(name)
        self.logging.info(
            "Service attached",
            service="service_registry",
            attached_service=str(name).strip().lower(),
        )
        return service

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        return self.scheduler.tick(now)

    def set_startup_report(self, report: Mapping[str, Any]) -> None:
        self._startup_report = copy.deepcopy(dict(report))

    def startup_report(self) -> Dict[str, Any]:
        return copy.deepcopy(self._startup_report)

    def status(self) -> Dict[str, Any]:
        return {
            "service": "bx1",
            "state": self.health.status()["system_health"],
            "registry": self.services.status(),
            "scheduler": self.scheduler.status(),
            "milestone": (
                self._startup_report.get("milestone")
                if self._startup_report
                else "BX1 OS Digital Twin"
            ),
            "startup_validated": bool(
                self._startup_report.get("success", False)
            ),
        }

    def configuration(self) -> Dict[str, Any]:
        return {
            "core_services": copy.deepcopy(self._core_config),
            "hardware_services": {
                "hardware": {
                    "led": self.led.configuration(),
                    "drive": self.drive.configuration(),
                    "range": self.range.configuration(),
                },
                "power": {
                    "power_service": self.power.configuration(),
                    "battery_service": self.battery.configuration(),
                },
            },
        }

    def __getattr__(self, name: str) -> Any:
        registry = self.__dict__.get("services")
        if registry is not None and registry.has(name):
            return registry.service(name)
        raise AttributeError(name)


def create_bx1(
    config: Optional[Mapping[str, Any]] = None,
    *,
    monotonic_clock=time.monotonic,
    wall_clock=time.time,
) -> BX1:
    return BX1(
        config,
        monotonic_clock=monotonic_clock,
        wall_clock=wall_clock,
    )
