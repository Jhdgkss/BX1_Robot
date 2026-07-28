from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .state import HardwareServiceBase, HardwareState, HardwareStateManager


@dataclass(frozen=True)
class BatteryMeasurement:
    cell_voltages_v: Tuple[float, ...]
    pack_voltage_v: float
    pack_current_a: float
    temperature_c: float
    state_of_charge_pct: float
    available: bool
    healthy: bool
    fault_reason: str
    charging: bool
    runtime_override_s: Optional[float]
    sampled_at: float

    @property
    def pack_power_w(self) -> float:
        return self.pack_voltage_v * self.pack_current_a

    @property
    def balance_error_v(self) -> float:
        if not self.cell_voltages_v:
            return 0.0
        return max(self.cell_voltages_v) - min(self.cell_voltages_v)

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["pack_power_w"] = self.pack_power_w
        value["balance_error_v"] = self.balance_error_v
        return value


class BatteryMonitorBase(HardwareServiceBase, ABC):
    """Battery telemetry contract. Implementations return one coherent sample."""

    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        *,
        fitted: bool,
        enabled: bool,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            name,
            config,
            fitted=fitted,
            enabled=enabled,
            state_manager=state_manager,
        )
        self._clock = clock

    @abstractmethod
    def read(self) -> BatteryMeasurement:
        raise NotImplementedError


class MockBatteryMonitor(BatteryMonitorBase):
    """Mutable, coherent three-cell battery telemetry for the Digital Twin."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = {
            "enabled": True,
            "cell_count": 3,
            "cell_voltages_v": [4.0, 4.0, 4.0],
            "pack_current_a": 1.0,
            "temperature_c": 25.0,
            "state_of_charge_pct": 75.0,
            "charging": False,
            "runtime_override_s": None,
            **dict(config or {}),
        }
        cell_count = int(cfg["cell_count"])
        if cell_count < 1:
            raise ValueError("battery monitor cell_count must be positive")
        cells = self._cells(cfg.get("cell_voltages_v"), cell_count)
        cfg["cell_voltages_v"] = list(cells)
        enabled = bool(cfg["enabled"])
        super().__init__(
            "mock_battery_monitor",
            cfg,
            fitted=True,
            enabled=enabled,
            state_manager=state_manager,
            clock=clock,
        )
        self._cell_voltages = list(cells)
        self._current = self._finite(cfg["pack_current_a"], "pack_current_a")
        self._temperature = self._finite(cfg["temperature_c"], "temperature_c")
        self._soc = self._percentage(cfg["state_of_charge_pct"])
        self._charging = bool(cfg["charging"])
        runtime = cfg.get("runtime_override_s")
        self._runtime = None if runtime is None else max(0.0, self._finite(runtime, "runtime_override_s"))
        self._available = True
        self._fault = ""
        self._read_count = 0
        if enabled:
            self._transition(HardwareState.READY, "Mock battery monitor ready")

    def read(self) -> BatteryMeasurement:
        return self._sample(count=True)

    def _sample(self, *, count: bool) -> BatteryMeasurement:
        if self.status()["state"] == HardwareState.DISABLED.value:
            return BatteryMeasurement(
                tuple(),
                0.0,
                0.0,
                0.0,
                0.0,
                False,
                False,
                "Mock battery monitor is disabled",
                False,
                None,
                self._clock(),
            )
        if count:
            self._read_count += 1
        healthy = self._available and not self._fault
        return BatteryMeasurement(
            tuple(self._cell_voltages),
            sum(self._cell_voltages),
            self._current,
            self._temperature,
            self._soc,
            self._available,
            healthy,
            self._fault,
            self._charging,
            self._runtime,
            self._clock(),
        )

    def set_pack_voltage(self, voltage_v: Any) -> None:
        total = self._finite(voltage_v, "pack_voltage_v")
        if total < 0.0:
            raise ValueError("pack_voltage_v must not be negative")
        per_cell = total / len(self._cell_voltages)
        self._cell_voltages = [per_cell] * len(self._cell_voltages)

    def set_current(self, current_a: Any) -> None:
        self._current = self._finite(current_a, "pack_current_a")

    def set_temperature(self, temperature_c: Any) -> None:
        self._temperature = self._finite(temperature_c, "temperature_c")

    def set_capacity(self, state_of_charge: Any) -> None:
        value = self._finite(state_of_charge, "state_of_charge")
        if 0.0 <= value <= 1.0:
            value *= 100.0
        self._soc = self._percentage(value)

    def set_runtime(self, seconds: Optional[Any]) -> None:
        if seconds is None:
            self._runtime = None
            return
        value = self._finite(seconds, "runtime_s")
        if value < 0.0:
            raise ValueError("runtime_s must not be negative")
        self._runtime = value

    def set_cell_voltage(self, cell: int, voltage_v: Any) -> None:
        index = int(cell) - 1
        if index < 0 or index >= len(self._cell_voltages):
            raise IndexError("battery cell number is outside configured pack")
        voltage = self._finite(voltage_v, "cell_voltage_v")
        if voltage < 0.0:
            raise ValueError("cell_voltage_v must not be negative")
        self._cell_voltages[index] = voltage

    def set_fault(self, reason: Optional[str]) -> None:
        self._fault = str(reason or "").strip()

    def set_charging(self, charging: bool) -> None:
        self._charging = bool(charging)
        if self._charging and self._current > 0.0:
            self._current = -self._current
        elif not self._charging and self._current < 0.0:
            self._current = abs(self._current)

    def set_available(self, available: bool) -> None:
        self._available = bool(available)

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        base.update(
            {
                "read_count": self._read_count,
                "measurement": self._sample(count=False).as_dict(),
            }
        )
        return base

    @staticmethod
    def _cells(value: Any, count: int) -> Tuple[float, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError("cell_voltages_v must be a sequence")
        cells = tuple(float(item) for item in value)
        if len(cells) != count or any(not math.isfinite(item) or item < 0.0 for item in cells):
            raise ValueError("cell_voltages_v must contain one valid value per cell")
        return cells

    @staticmethod
    def _finite(value: Any, label: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("%s must be finite" % label)
        return result

    @staticmethod
    def _percentage(value: Any) -> float:
        result = MockBatteryMonitor._finite(value, "state_of_charge_pct")
        if result < 0.0 or result > 100.0:
            raise ValueError("state_of_charge_pct must be between 0 and 100")
        return result


class _PlaceholderMonitor(BatteryMonitorBase):
    MODEL = "future_monitor"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = {
            "enabled": False,
            "fitted": False,
            "model": self.MODEL,
            "bus": "",
            "address": None,
            **dict(config or {}),
        }
        super().__init__(
            self.MODEL.lower() + "_monitor",
            cfg,
            fitted=False,
            enabled=False,
            state_manager=state_manager,
            clock=clock,
        )

    def read(self) -> BatteryMeasurement:
        raise RuntimeError("%s is an interface placeholder; no hardware access is implemented" % self.MODEL)


class INA219Monitor(_PlaceholderMonitor):
    MODEL = "INA219"


class INA226Monitor(_PlaceholderMonitor):
    MODEL = "INA226"


class INA228Monitor(_PlaceholderMonitor):
    MODEL = "INA228"
