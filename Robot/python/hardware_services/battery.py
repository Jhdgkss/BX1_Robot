from __future__ import annotations

import copy
import time
from typing import Any, Callable, Dict, List, Optional

from .battery_monitor import BatteryMeasurement, BatteryMonitorBase
from .battery_state import BatteryState, BatteryStateMachine, BatteryTransition
from .bms import BMSBase
from .capability import CapabilityRegistry
from .event_bus import EventBus, EventType


class BatteryService:
    """Normalized battery telemetry, health, state and event coordination."""

    def __init__(
        self,
        monitor: BatteryMonitorBase,
        bms: BMSBase,
        config: Dict[str, Any],
        *,
        event_bus: Optional[EventBus] = None,
        capabilities: Optional[CapabilityRegistry] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.monitor = monitor
        self.bms = bms
        self._config = copy.deepcopy(config)
        self._event_bus = event_bus or EventBus()
        self._capabilities = capabilities or CapabilityRegistry()
        self._clock = clock
        fitted = bool(self._config.get("enabled", True)) and bool(
            self._config.get("fitted", True)
        )
        self.state_machine = BatteryStateMachine(fitted=fitted, clock=clock)
        self._measurement: Optional[BatteryMeasurement] = None
        self._shutdown_requested = False
        self._shutdown_reason = ""
        self._refresh_count = 0
        if fitted:
            self.refresh()

    def refresh(self) -> Dict[str, Any]:
        self._refresh_count += 1
        if not bool(self._config.get("enabled", True)):
            self._set_state(BatteryState.NOT_FITTED, "Battery service is disabled")
            return self.status()
        try:
            sample = self.monitor.read()
        except Exception as exc:
            self._set_state(BatteryState.FAULT, "Battery monitor failed: %s" % exc)
            return self.status()
        self._measurement = sample

        if not sample.available:
            self._set_state(BatteryState.NOT_FITTED, sample.fault_reason or "Battery removed")
            return self.status()

        faults = self._combined_faults(sample)
        expected_cells = int(self._config["cell_count"])
        if len(sample.cell_voltages_v) != expected_cells:
            faults.append(
                "Expected %d battery cells, received %d"
                % (expected_cells, len(sample.cell_voltages_v))
            )
        balance_error = sample.balance_error_v
        temperature = self.battery_temperature()
        if faults:
            target = BatteryState.FAULT
            reason = "; ".join(faults)
        elif balance_error > float(self._config["cell_imbalance_fault_v"]):
            target = BatteryState.FAULT
            reason = "Cell imbalance %.3f V exceeds fault limit" % balance_error
        elif (
            temperature < float(self._config["minimum_temperature_c"])
            or temperature > float(self._config["maximum_temperature_c"])
        ):
            target = BatteryState.FAULT
            reason = "Battery temperature %.1f C outside safe range" % temperature
        elif self._shutdown_requested or sample.state_of_charge_pct <= float(
            self._config["shutdown_soc_pct"]
        ):
            target = BatteryState.SHUTDOWN_PENDING
            reason = self._shutdown_reason or "Battery reached shutdown threshold"
        elif sample.charging:
            if sample.state_of_charge_pct >= float(self._config["full_soc_pct"]):
                target = BatteryState.FULL
                reason = "Battery full while charging"
            else:
                target = BatteryState.CHARGING
                reason = "Battery charging"
        elif sample.state_of_charge_pct >= float(self._config["full_soc_pct"]):
            target = BatteryState.FULL
            reason = "Battery full"
        elif sample.state_of_charge_pct <= float(self._config["critical_soc_pct"]):
            target = BatteryState.CRITICAL
            reason = "Battery state of charge is critical"
        elif sample.state_of_charge_pct <= float(self._config["low_soc_pct"]):
            target = BatteryState.LOW
            reason = "Battery state of charge is low"
        else:
            target = BatteryState.READY
            reason = "Battery telemetry ready"
        self._set_state(target, reason)
        return self.status()

    def request_shutdown(self, reason: str) -> None:
        self._shutdown_requested = True
        self._shutdown_reason = str(reason).strip() or "Shutdown requested"
        self._set_state(BatteryState.SHUTDOWN_PENDING, self._shutdown_reason)

    def cancel_shutdown(self) -> bool:
        if not self._shutdown_requested and self.state_machine.state != BatteryState.SHUTDOWN_PENDING:
            return False
        sample = self._measurement
        if sample and sample.state_of_charge_pct <= float(self._config["shutdown_soc_pct"]):
            return False
        self._shutdown_requested = False
        self._shutdown_reason = ""
        self.refresh()
        return True

    def status(self) -> Dict[str, Any]:
        return {
            "service": "battery_service",
            **self.state_machine.status(),
            "charging_state": self.charging_state(),
            "state_of_charge_pct": self.state_of_charge(),
        }

    def health(self) -> Dict[str, Any]:
        detail = self.battery_health()
        return {
            "healthy": detail["healthy"],
            "available": detail["available"],
            "state": detail["state"],
            "reason": detail["reason"],
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "service": "battery_service",
            "state_machine": self.state_machine.diagnostics(),
            "measurement": None if self._measurement is None else self._measurement.as_dict(),
            "battery_health": self.battery_health(),
            "monitor": self.monitor.diagnostics(),
            "bms": self.bms.diagnostics(),
            "refresh_count": self._refresh_count,
            "shutdown_requested": self._shutdown_requested,
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def pack_voltage(self) -> Optional[float]:
        return None if self._measurement is None else self._measurement.pack_voltage_v

    def pack_current(self) -> Optional[float]:
        return None if self._measurement is None else self._measurement.pack_current_a

    def pack_power(self) -> Optional[float]:
        return None if self._measurement is None else self._measurement.pack_power_w

    def battery_temperature(self) -> Optional[float]:
        if self._measurement is not None:
            return self._measurement.temperature_c
        return self.bms.temperature()

    def state_of_charge(self) -> Optional[float]:
        return None if self._measurement is None else self._measurement.state_of_charge_pct

    def cell_voltages(self) -> List[float]:
        return [] if self._measurement is None else list(self._measurement.cell_voltages_v)

    def cell_voltage(self, cell: int) -> Optional[float]:
        index = int(cell) - 1
        cells = self.cell_voltages()
        if index < 0 or index >= len(cells):
            return None
        return cells[index]

    def balance_error(self) -> Optional[float]:
        return None if self._measurement is None else self._measurement.balance_error_v

    def estimated_runtime(self) -> Optional[float]:
        """Return estimated remaining runtime in seconds."""
        sample = self._measurement
        if sample is None or not sample.available:
            return None
        if sample.runtime_override_s is not None:
            return sample.runtime_override_s
        power_w = sample.pack_power_w
        if sample.charging or power_w <= 0.0:
            return None
        remaining_wh = (
            float(self._config["nominal_capacity_wh"])
            * sample.state_of_charge_pct
            / 100.0
        )
        return (remaining_wh / power_w) * 3600.0

    def charging_state(self) -> str:
        state = self.state_machine.state
        if state == BatteryState.CHARGING:
            return "charging"
        if state == BatteryState.FULL:
            return "full"
        if state == BatteryState.FAULT:
            return "fault"
        if state == BatteryState.NOT_FITTED:
            return "unavailable"
        return "not_charging"

    def battery_health(self) -> Dict[str, Any]:
        state = self.state_machine.state
        sample = self._measurement
        balance = self.balance_error()
        warning = (
            balance is not None
            and balance > float(self._config["cell_imbalance_warning_v"])
        )
        faults = [] if sample is None else self._combined_faults(sample)
        healthy = (
            sample is not None
            and sample.available
            and sample.healthy
            and not faults
            and not warning
            and state
            in {
                BatteryState.READY,
                BatteryState.CHARGING,
                BatteryState.FULL,
            }
        )
        return {
            "healthy": healthy,
            "available": bool(sample and sample.available),
            "state": state.value,
            "reason": self.state_machine.status()["reason"],
            "faults": faults,
            "cell_voltages_v": self.cell_voltages(),
            "balance_error_v": balance,
            "balance_warning": warning,
            "temperature_c": self.battery_temperature(),
            "bms_output_enabled": self.bms.output_enabled(),
        }

    def _combined_faults(self, sample: BatteryMeasurement) -> List[str]:
        faults = list(self.bms.faults())
        if not sample.healthy and sample.fault_reason:
            faults.append(sample.fault_reason)
        return list(dict.fromkeys(faults))

    def _set_state(self, target: BatteryState, reason: str) -> None:
        current = self.state_machine.state
        if current == target:
            return
        if current == BatteryState.NOT_FITTED and target != BatteryState.INITIALISING:
            self._transition(BatteryState.INITIALISING, "Battery inserted; validating telemetry")
            current = self.state_machine.state
        if current == BatteryState.FAULT and target not in {
            BatteryState.NOT_FITTED,
            BatteryState.SHUTDOWN_PENDING,
            BatteryState.INITIALISING,
        }:
            self._transition(BatteryState.INITIALISING, "Battery fault cleared; reinitialising")
        self._transition(target, reason)

    def _transition(self, target: BatteryState, reason: str) -> None:
        transition = self.state_machine.transition(target, reason)
        self._publish_transition(transition)

    def _publish_transition(self, transition: BatteryTransition) -> None:
        event_type = {
            BatteryState.LOW: EventType.BATTERY_LOW,
            BatteryState.CRITICAL: EventType.BATTERY_CRITICAL,
            BatteryState.CHARGING: EventType.BATTERY_CHARGING,
            BatteryState.FULL: EventType.BATTERY_FULL,
            BatteryState.FAULT: EventType.BATTERY_FAULT,
            BatteryState.SHUTDOWN_PENDING: EventType.SHUTDOWN_REQUESTED,
            BatteryState.NOT_FITTED: EventType.BATTERY_REMOVED,
        }.get(transition.current)
        if transition.previous == BatteryState.NOT_FITTED and transition.current == BatteryState.INITIALISING:
            event_type = EventType.BATTERY_INSERTED
        if event_type is not None:
            self._event_bus.publish(
                event_type,
                {
                    "previous_state": transition.previous.value,
                    "state": transition.current.value,
                    "reason": transition.reason,
                    "state_of_charge_pct": self.state_of_charge(),
                },
                source="battery_service",
            )
