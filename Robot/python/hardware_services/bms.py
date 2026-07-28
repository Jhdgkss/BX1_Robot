from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence

from .state import HardwareServiceBase, HardwareState, HardwareStateManager


class BMSBase(HardwareServiceBase, ABC):
    @abstractmethod
    def enable_output(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disable_output(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def faults(self) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def temperature(self) -> Optional[float]:
        raise NotImplementedError

    @abstractmethod
    def cell_voltages(self) -> List[float]:
        raise NotImplementedError

    @abstractmethod
    def balancing_state(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def reset_fault(self, fault: Optional[str] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def output_enabled(self) -> bool:
        raise NotImplementedError


class MockBMS(BMSBase):
    """In-memory BMS model. It controls no battery or output hardware."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
    ) -> None:
        cfg = {
            "enabled": True,
            "output_enabled": True,
            "temperature_c": 25.0,
            "cell_voltages_v": [4.0, 4.0, 4.0],
            "balancing": False,
            **dict(config or {}),
        }
        enabled = bool(cfg["enabled"])
        super().__init__(
            "mock_bms",
            cfg,
            fitted=True,
            enabled=enabled,
            state_manager=state_manager,
        )
        self._output = bool(cfg["output_enabled"])
        self._temperature = float(cfg["temperature_c"])
        self._cells = [float(value) for value in cfg["cell_voltages_v"]]
        self._balancing = bool(cfg["balancing"])
        self._faults: List[str] = []
        self._lock = threading.RLock()
        if enabled:
            self._transition(HardwareState.READY, "Mock BMS ready")

    def enable_output(self) -> bool:
        with self._lock:
            if self._faults:
                return False
            self._output = True
            return True

    def disable_output(self) -> bool:
        with self._lock:
            self._output = False
            return True

    def faults(self) -> List[str]:
        with self._lock:
            return list(self._faults)

    def temperature(self) -> Optional[float]:
        with self._lock:
            return self._temperature

    def cell_voltages(self) -> List[float]:
        with self._lock:
            return list(self._cells)

    def balancing_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active": self._balancing,
                "cells": [self._balancing] * len(self._cells),
                "simulated": True,
            }

    def reset_fault(self, fault: Optional[str] = None) -> bool:
        with self._lock:
            if fault is None:
                self._faults = []
                self._recover_state()
                return True
            target = str(fault)
            if target in self._faults:
                self._faults.remove(target)
                if not self._faults:
                    self._recover_state()
                return True
            return False

    def output_enabled(self) -> bool:
        with self._lock:
            return self._output

    def set_fault(self, fault: Optional[str]) -> None:
        with self._lock:
            value = str(fault or "").strip()
            self._faults = [value] if value else []
            if value:
                self._output = False
                if self.status()["state"] == HardwareState.READY.value:
                    self._transition(HardwareState.FAULT, value)
            else:
                self._recover_state()

    def set_temperature(self, temperature_c: Any) -> None:
        with self._lock:
            self._temperature = float(temperature_c)

    def set_cell_voltages(self, voltages_v: Sequence[Any]) -> None:
        with self._lock:
            self._cells = [float(value) for value in voltages_v]

    def set_balancing(self, active: bool) -> None:
        with self._lock:
            self._balancing = bool(active)

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        base.update(
            {
                "output_enabled": self.output_enabled(),
                "faults": self.faults(),
                "temperature_c": self.temperature(),
                "cell_voltages_v": self.cell_voltages(),
                "balancing": self.balancing_state(),
                "simulated": True,
            }
        )
        return base

    def _recover_state(self) -> None:
        if self.status()["state"] == HardwareState.FAULT.value:
            self._transition(HardwareState.INITIALISING, "Mock BMS fault cleared")
            self._transition(HardwareState.READY, "Mock BMS recovered")


class _PlaceholderBMS(BMSBase):
    MODEL = "future_bms"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
    ) -> None:
        cfg = {
            "enabled": False,
            "fitted": False,
            "model": self.MODEL,
            **dict(config or {}),
        }
        super().__init__(
            self.MODEL.lower(),
            cfg,
            fitted=False,
            enabled=False,
            state_manager=state_manager,
        )

    def enable_output(self) -> bool:
        raise RuntimeError("%s is an interface placeholder" % self.MODEL)

    def disable_output(self) -> bool:
        raise RuntimeError("%s is an interface placeholder" % self.MODEL)

    def faults(self) -> List[str]:
        return []

    def temperature(self) -> Optional[float]:
        return None

    def cell_voltages(self) -> List[float]:
        return []

    def balancing_state(self) -> Dict[str, Any]:
        return {"active": False, "cells": [], "available": False}

    def reset_fault(self, fault: Optional[str] = None) -> bool:
        return False

    def output_enabled(self) -> bool:
        return False


class SmartBMS(_PlaceholderBMS):
    MODEL = "SmartBMS"


class PassiveBMS(_PlaceholderBMS):
    MODEL = "PassiveBMS"


class HardwareOnlyBMS(_PlaceholderBMS):
    MODEL = "HardwareOnlyBMS"
