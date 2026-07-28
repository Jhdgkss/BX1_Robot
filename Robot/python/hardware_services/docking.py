from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class DockInterface(ABC):
    """Future charging-dock contract. Phase 2 provides no implementation."""

    @abstractmethod
    def dock(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def undock(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def charging(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def charger_voltage(self) -> Optional[float]:
        raise NotImplementedError

    @abstractmethod
    def charger_current(self) -> Optional[float]:
        raise NotImplementedError

    @abstractmethod
    def dock_detected(self) -> bool:
        raise NotImplementedError
