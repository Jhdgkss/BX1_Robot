from __future__ import annotations

import copy
import threading
from enum import Enum
from typing import Any, Dict, Optional

from .battery import BatteryService
from .battery_state import BatteryState
from .capability import CapabilityRegistry
from .event_bus import EventBus, EventType


class SystemPowerState(str, Enum):
    READY = "READY"
    CONSERVATION = "CONSERVATION"
    CRITICAL = "CRITICAL"
    CHARGING = "CHARGING"
    FULL = "FULL"
    FAULT = "FAULT"
    SHUTDOWN_PENDING = "SHUTDOWN_PENDING"


class PowerService:
    """System power budget, rails, runtime, charging and shutdown policy."""

    def __init__(
        self,
        battery: BatteryService,
        capabilities: CapabilityRegistry,
        config: Dict[str, Any],
        *,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.battery = battery
        self.capabilities = capabilities
        self._config = copy.deepcopy(config)
        self._event_bus = event_bus or EventBus()
        self._loads: Dict[str, Dict[str, Any]] = {}
        self._rails: Dict[str, Dict[str, Any]] = copy.deepcopy(
            self._config.get("rails") or {}
        )
        self._shutdown_requested = False
        self._shutdown_reason = ""
        self._state = SystemPowerState.READY
        self._lock = threading.RLock()
        self._refresh_count = 0
        self._evaluate_state()

    def refresh(self) -> Dict[str, Any]:
        self.battery.refresh()
        with self._lock:
            self._refresh_count += 1
            self._evaluate_state()
        return self.status()

    def set_load(self, name: str, watts: Any, *, essential: bool = False) -> None:
        key = str(name).strip()
        value = float(watts)
        if not key:
            raise ValueError("power load name must not be empty")
        if value < 0.0:
            raise ValueError("power load must not be negative")
        with self._lock:
            self._loads[key] = {"watts": value, "essential": bool(essential)}

    def remove_load(self, name: str) -> bool:
        with self._lock:
            return self._loads.pop(str(name).strip(), None) is not None

    def set_rail(
        self,
        name: str,
        healthy: bool,
        *,
        voltage_v: Optional[float] = None,
        reason: str = "",
    ) -> None:
        key = str(name).strip()
        if not key:
            raise ValueError("power rail name must not be empty")
        with self._lock:
            previous = bool(self._rails.get(key, {}).get("healthy", True))
            rail = dict(self._rails.get(key) or {})
            rail.update(
                {
                    "healthy": bool(healthy),
                    "voltage_v": None if voltage_v is None else float(voltage_v),
                    "reason": str(reason),
                }
            )
            rail.setdefault("required", False)
            self._rails[key] = rail
            self._evaluate_state()
        if previous and not healthy:
            self._event_bus.publish(
                EventType.POWER_RAIL_FAULT,
                {"rail": key, "reason": reason or "Power rail fault"},
                source="power_service",
            )
        elif not previous and healthy:
            self._event_bus.publish(
                EventType.POWER_RESTORED,
                {"rail": key},
                source="power_service",
            )

    def request_shutdown(self, reason: str) -> None:
        self._shutdown_requested = True
        self._shutdown_reason = str(reason).strip() or "Power service requested shutdown"
        self.battery.request_shutdown(self._shutdown_reason)
        self._evaluate_state()

    def cancel_shutdown(self) -> bool:
        if not self._shutdown_requested:
            return False
        if not self.battery.cancel_shutdown():
            return False
        self._shutdown_requested = False
        self._shutdown_reason = ""
        self._evaluate_state()
        self._event_bus.publish(
            EventType.SHUTDOWN_CANCELLED,
            {"reason": "Power conditions recovered"},
            source="power_service",
        )
        return True

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "service": "power_service",
                "state": self._state.value,
                "available_power_w": self.available_power(),
                "remaining_runtime_s": self.remaining_runtime(),
                "shutdown_required": self.shutdown_required(),
            }

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "healthy": self._state
                in {
                    SystemPowerState.READY,
                    SystemPowerState.CHARGING,
                    SystemPowerState.FULL,
                },
                "available": self._state != SystemPowerState.FAULT,
                "state": self._state.value,
                "reason": self._reason(),
            }

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "service": "power_service",
                "state": self._state.value,
                "health": self.health(),
                "budget": {
                    "system_power_budget_w": float(
                        self._config["system_power_budget_w"]
                    ),
                    "reserved_power_w": float(self._config["reserved_power_w"]),
                    "loads": copy.deepcopy(self._loads),
                    "available_power_w": self.available_power(),
                },
                "rails": copy.deepcopy(self._rails),
                "battery": self.battery.status(),
                "shutdown_requested": self._shutdown_requested,
                "shutdown_reason": self._shutdown_reason,
                "refresh_count": self._refresh_count,
            }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def available_power(self) -> float:
        with self._lock:
            budget = float(self._config["system_power_budget_w"])
            reserved = float(self._config["reserved_power_w"])
            allocated = sum(float(item["watts"]) for item in self._loads.values())
            return max(0.0, budget - reserved - allocated)

    def remaining_runtime(self) -> Optional[float]:
        return self.battery.estimated_runtime()

    def can_move(self) -> bool:
        if not bool(self._config.get("enabled", True)):
            return False
        if self.battery.state_machine.state not in {
            BatteryState.READY,
            BatteryState.FULL,
        }:
            return False
        if not self.battery.bms.output_enabled():
            return False
        if self._required_rail_faults():
            return False
        return self.available_power() >= float(
            self._config["movement_min_available_w"]
        )

    def can_charge(self) -> bool:
        if not bool(self._config.get("charging_enabled", True)):
            return False
        if not self.capabilities.has("battery_monitor"):
            return False
        return self.battery.state_machine.state not in {
            BatteryState.NOT_FITTED,
            BatteryState.FULL,
            BatteryState.FAULT,
            BatteryState.SHUTDOWN_PENDING,
        }

    def shutdown_required(self) -> bool:
        if self._shutdown_requested:
            return True
        state = self.battery.state_machine.state
        if state == BatteryState.SHUTDOWN_PENDING:
            return True
        if state == BatteryState.FAULT and bool(
            self._config.get("shutdown_on_battery_fault", True)
        ):
            return True
        return bool(self._required_rail_faults())

    def _required_rail_faults(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: rail
            for name, rail in self._rails.items()
            if bool(rail.get("required", False)) and not bool(rail.get("healthy", False))
        }

    def _evaluate_state(self) -> None:
        battery_state = self.battery.state_machine.state
        if self._shutdown_requested or battery_state == BatteryState.SHUTDOWN_PENDING:
            self._state = SystemPowerState.SHUTDOWN_PENDING
        elif self._required_rail_faults() or battery_state == BatteryState.FAULT:
            self._state = SystemPowerState.FAULT
        elif battery_state == BatteryState.CRITICAL:
            self._state = SystemPowerState.CRITICAL
        elif battery_state == BatteryState.LOW:
            self._state = SystemPowerState.CONSERVATION
        elif battery_state == BatteryState.CHARGING:
            self._state = SystemPowerState.CHARGING
        elif battery_state == BatteryState.FULL:
            self._state = SystemPowerState.FULL
        else:
            self._state = SystemPowerState.READY

    def _reason(self) -> str:
        rail_faults = self._required_rail_faults()
        if rail_faults:
            return "Required rail fault: %s" % ", ".join(sorted(rail_faults))
        if self._shutdown_reason:
            return self._shutdown_reason
        return self.battery.status()["reason"]
