from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .battery import BatteryService
from .battery_monitor import BatteryMonitorBase, MockBatteryMonitor
from .bms import BMSBase, MockBMS
from .capability import CapabilityRegistry
from .docking import DockInterface
from .event_bus import EventBus
from .power import PowerService
from .power_config import load_power_configuration
from .state import HardwareStateManager


@dataclass
class PowerServices:
    event_bus: EventBus
    battery: BatteryService
    power: PowerService
    capabilities: CapabilityRegistry
    monitor: BatteryMonitorBase
    bms: BMSBase
    dock: Optional[DockInterface]
    mode: str

    def status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "battery": self.battery.status(),
            "power": self.power.status(),
            "capabilities": self.capabilities.status(),
        }

    def health(self) -> Dict[str, Any]:
        battery = self.battery.health()
        power = self.power.health()
        return {
            "healthy": battery["healthy"] and power["healthy"],
            "battery": battery,
            "power": power,
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "battery": self.battery.diagnostics(),
            "power": self.power.diagnostics(),
            "capabilities": self.capabilities.diagnostics(),
            "event_bus": self.event_bus.diagnostics(),
            "dock_implemented": self.dock is not None,
        }

    def configuration(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "battery_service": self.battery.configuration(),
            "power_service": self.power.configuration(),
            "battery_monitor": self.monitor.configuration(),
            "bms": self.bms.configuration(),
            "capability_registry": self.capabilities.configuration(),
        }


class BatteryDigitalTwin(PowerServices):
    """Simulation controls over the same BatteryService/PowerService APIs."""

    @property
    def mock_monitor(self) -> MockBatteryMonitor:
        if not isinstance(self.monitor, MockBatteryMonitor):
            raise TypeError("Battery Digital Twin monitor is not simulated")
        return self.monitor

    @property
    def mock_bms(self) -> MockBMS:
        if not isinstance(self.bms, MockBMS):
            raise TypeError("Battery Digital Twin BMS is not simulated")
        return self.bms

    def set_voltage(self, voltage_v: Any) -> None:
        self.mock_monitor.set_pack_voltage(voltage_v)
        self.mock_bms.set_cell_voltages(self.mock_monitor.read().cell_voltages_v)
        self._refresh()

    def set_current(self, current_a: Any) -> None:
        self.mock_monitor.set_current(current_a)
        self._refresh()

    def set_temperature(self, temperature_c: Any) -> None:
        self.mock_monitor.set_temperature(temperature_c)
        self.mock_bms.set_temperature(temperature_c)
        self._refresh()

    def set_capacity(self, state_of_charge: Any) -> None:
        self.mock_monitor.set_capacity(state_of_charge)
        self._refresh()

    def set_runtime(self, seconds: Optional[Any]) -> None:
        self.mock_monitor.set_runtime(seconds)
        self._refresh()

    def set_cell_voltage(self, cell: int, voltage_v: Any) -> None:
        self.mock_monitor.set_cell_voltage(cell, voltage_v)
        self.mock_bms.set_cell_voltages(self.mock_monitor.read().cell_voltages_v)
        self._refresh()

    def set_fault(self, fault: Optional[str]) -> None:
        self.mock_monitor.set_fault(fault)
        self.mock_bms.set_fault(fault)
        if not fault:
            self.mock_bms.enable_output()
        self._refresh()

    def set_charging(self, charging: bool) -> None:
        self.mock_monitor.set_charging(charging)
        self._refresh()

    def set_fitted(self, fitted: bool) -> None:
        self.mock_monitor.set_available(fitted)
        self.capabilities.register(
            "battery_monitor", bool(fitted), simulated=True
        )
        self._refresh()

    def _refresh(self) -> None:
        self.power.refresh()

    @classmethod
    def create(
        cls,
        config: Optional[Dict[str, Any]] = None,
        *,
        event_bus: Optional[EventBus] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> "BatteryDigitalTwin":
        services = create_power_services(
            config,
            event_bus=event_bus,
            clock=clock,
        )
        if not isinstance(services, BatteryDigitalTwin):
            raise TypeError("configuration did not create a Battery Digital Twin")
        return services


def create_power_services(
    config: Optional[Dict[str, Any]] = None,
    *,
    event_bus: Optional[EventBus] = None,
    monitor: Optional[BatteryMonitorBase] = None,
    bms: Optional[BMSBase] = None,
    dock: Optional[DockInterface] = None,
    clock: Callable[[], float] = time.monotonic,
) -> PowerServices:
    sections = load_power_configuration(config)
    power_cfg = sections["power_service"]
    mode = str(power_cfg.get("mode", "digital_twin")).strip().lower()
    if mode not in {"digital_twin", "physical"}:
        raise ValueError("power_service mode must be digital_twin or physical")

    bus = event_bus or EventBus()
    capability_cfg = sections["capability_registry"]
    capabilities = CapabilityRegistry(
        capability_cfg.get("capabilities") or {},
        simulated=bool(capability_cfg.get("simulated", mode == "digital_twin")),
    )
    manager = HardwareStateManager(clock=clock)

    if monitor is None:
        if mode != "digital_twin":
            raise ValueError("physical power mode requires an injected battery monitor")
        if str(sections["battery_monitor"].get("backend", "mock")).lower() != "mock":
            raise ValueError("Phase 2 only permits the mock battery monitor backend")
        monitor = MockBatteryMonitor(
            sections["battery_monitor"],
            state_manager=manager,
            clock=clock,
        )
    if bms is None:
        if mode != "digital_twin":
            raise ValueError("physical power mode requires an injected BMS adapter")
        if str(sections["bms"].get("backend", "mock")).lower() != "mock":
            raise ValueError("Phase 2 only permits the mock BMS backend")
        bms = MockBMS(sections["bms"], state_manager=manager)

    battery = BatteryService(
        monitor,
        bms,
        sections["battery_service"],
        event_bus=bus,
        capabilities=capabilities,
        clock=clock,
    )
    power = PowerService(
        battery,
        capabilities,
        power_cfg,
        event_bus=bus,
    )
    services = PowerServices(
        bus,
        battery,
        power,
        capabilities,
        monitor,
        bms,
        dock,
        mode,
    )
    if mode == "digital_twin":
        return BatteryDigitalTwin(**services.__dict__)
    return services
