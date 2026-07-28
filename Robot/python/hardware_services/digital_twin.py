from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .event_bus import EventBus
from .led import CallbackLEDStrip, LEDService, LEDStripBase, SimulatedLEDStrip
from .motor import DriveService
from .range import DistanceSensorBase, FutureToFSensor, MockDistanceSensor, RangeService
from .state import HardwareStateManager


@dataclass
class HardwareServices:
    """The stable service surface consumed by higher-level robot code."""

    event_bus: EventBus
    leds: LEDService
    drive: DriveService
    range: RangeService
    state_manager: HardwareStateManager
    mode: str

    def status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "event_bus": self.event_bus.status(),
            "leds": self.leds.status(),
            "drive": self.drive.status(),
            "range": self.range.status(),
        }

    def health(self) -> Dict[str, Any]:
        services = {
            "event_bus": self.event_bus.health(),
            "leds": self.leds.health(),
            "drive": self.drive.health(),
            "range": self.range.health(),
        }
        return {
            "healthy": all(
                item["healthy"]
                or item["state"] in {"DISABLED", "NOT_FITTED"}
                for item in services.values()
            ),
            "services": services,
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "event_bus": self.event_bus.diagnostics(),
            "leds": self.leds.diagnostics(),
            "drive": self.drive.diagnostics(),
            "range": self.range.diagnostics(),
            "hardware_states": self.state_manager.diagnostics(),
        }

    def configuration(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "event_bus": self.event_bus.configuration(),
            "leds": self.leds.configuration(),
            "drive": self.drive.configuration(),
            "range": self.range.configuration(),
        }


class DigitalTwin(HardwareServices):
    """Convenience wrapper exposing controls specific to the simulated devices."""

    @property
    def simulated_leds(self) -> SimulatedLEDStrip:
        output = self.leds.output
        if not isinstance(output, SimulatedLEDStrip):
            raise TypeError("Digital Twin LED output is not simulated")
        return output

    @property
    def simulated_range(self) -> MockDistanceSensor:
        sensor = self.range.sensor
        if not isinstance(sensor, MockDistanceSensor):
            raise TypeError("Digital Twin range sensor is not mocked")
        return sensor

    def set_distance(
        self,
        distance_mm: Optional[float],
        *,
        signal_quality: float = 1.0,
        available: bool = True,
        healthy: bool = True,
        fault_reason: str = "",
    ) -> None:
        self.simulated_range.set_reading(
            distance_mm,
            signal_quality=signal_quality,
            available=available,
            healthy=healthy,
            fault_reason=fault_reason,
        )

    def step(self, elapsed_s: Optional[float] = None) -> Dict[str, Any]:
        self.leds.tick(elapsed_s)
        self.range.poll()
        return self.diagnostics()

    @classmethod
    def create(
        cls,
        config: Optional[Dict[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "DigitalTwin":
        raw = dict(config or {})
        if isinstance(raw.get("hardware_services"), dict):
            raw = dict(raw["hardware_services"])
        services = create_hardware_services(
            {**raw, "mode": "digital_twin"},
            clock=clock,
        )
        return cls(**services.__dict__)


def create_hardware_services(
    config: Optional[Dict[str, Any]] = None,
    *,
    led_output: Optional[LEDStripBase] = None,
    range_sensor: Optional[DistanceSensorBase] = None,
    physical_led_writer: Optional[Callable[[Any], None]] = None,
    clock: Callable[[], float] = time.monotonic,
) -> HardwareServices:
    """Create simulation or adapter-backed services without changing their APIs.

    Physical adapters must be injected explicitly. This factory never discovers,
    opens, or writes hardware on its own.
    """
    cfg = dict(config or {})
    if "mode" not in cfg and isinstance(cfg.get("hardware_services"), dict):
        cfg = dict(cfg["hardware_services"])
    mode = str(cfg.get("mode", "digital_twin")).strip().lower()
    if mode not in {"digital_twin", "physical"}:
        raise ValueError("hardware services mode must be digital_twin or physical")

    manager = HardwareStateManager(clock=clock)
    event_cfg = dict(cfg.get("event_bus") or {})
    event_bus = EventBus(history_limit=int(event_cfg.get("history_limit", 100)))

    led_cfg = dict(cfg.get("led") or {})
    if led_output is None:
        if mode == "digital_twin":
            led_output = SimulatedLEDStrip()
            led_cfg["backend"] = "simulation"
        elif physical_led_writer is not None:
            led_output = CallbackLEDStrip(physical_led_writer)
            led_cfg["backend"] = "physical_adapter"
        else:
            raise ValueError("physical mode requires an injected LED output adapter")
    leds = LEDService(led_output, led_cfg, state_manager=manager, clock=clock)

    range_cfg = dict(cfg.get("range") or {})
    sensor_cfg = dict(range_cfg.get("sensor") or {})
    if range_sensor is None:
        if mode == "digital_twin":
            range_sensor = MockDistanceSensor(
                sensor_cfg, state_manager=manager, clock=clock
            )
            range_cfg["backend"] = "mock"
        else:
            range_sensor = FutureToFSensor(
                sensor_cfg, state_manager=manager, clock=clock
            )
            range_cfg["backend"] = "future_tof"
    range_service = RangeService(
        range_sensor, range_cfg, state_manager=manager, clock=clock
    )

    drive = DriveService(
        dict(cfg.get("motor") or {}),
        state_manager=manager,
        clock=clock,
    )
    if bool(cfg.get("bind_default_events", True)):
        leds.bind_events(event_bus)

    services = HardwareServices(
        event_bus=event_bus,
        leds=leds,
        drive=drive,
        range=range_service,
        state_manager=manager,
        mode=mode,
    )
    if mode == "digital_twin":
        return DigitalTwin(**services.__dict__)
    return services
