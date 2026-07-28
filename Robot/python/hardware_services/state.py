from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class HardwareState(str, Enum):
    NOT_FITTED = "NOT_FITTED"
    DISABLED = "DISABLED"
    INITIALISING = "INITIALISING"
    READY = "READY"
    STALE = "STALE"
    FAULT = "FAULT"


_ALLOWED_TRANSITIONS: Dict[HardwareState, Set[HardwareState]] = {
    HardwareState.NOT_FITTED: {HardwareState.DISABLED, HardwareState.INITIALISING},
    HardwareState.DISABLED: {HardwareState.NOT_FITTED, HardwareState.INITIALISING},
    HardwareState.INITIALISING: {
        HardwareState.DISABLED,
        HardwareState.READY,
        HardwareState.FAULT,
    },
    HardwareState.READY: {
        HardwareState.DISABLED,
        HardwareState.STALE,
        HardwareState.FAULT,
    },
    HardwareState.STALE: {
        HardwareState.DISABLED,
        HardwareState.READY,
        HardwareState.FAULT,
    },
    HardwareState.FAULT: {
        HardwareState.DISABLED,
        HardwareState.INITIALISING,
    },
}


@dataclass(frozen=True)
class StateTransition:
    device: str
    previous: HardwareState
    current: HardwareState
    reason: str
    timestamp: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "previous": self.previous.value,
            "current": self.current.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class _DeviceRecord:
    state: HardwareState
    reason: str
    changed_at: float


class HardwareStateManager:
    """Thread-safe lifecycle authority for hardware devices and simulations."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        history_limit: int = 100,
    ) -> None:
        self._clock = clock
        self._history_limit = max(1, int(history_limit))
        self._records: Dict[str, _DeviceRecord] = {}
        self._history: List[StateTransition] = []
        self._lock = threading.RLock()

    def register(
        self,
        device: str,
        *,
        fitted: bool = True,
        enabled: bool = True,
        reason: str = "",
    ) -> HardwareState:
        name = self._normalise_name(device)
        state = (
            HardwareState.NOT_FITTED
            if not fitted
            else HardwareState.INITIALISING
            if enabled
            else HardwareState.DISABLED
        )
        with self._lock:
            if name in self._records:
                raise ValueError("device is already registered: %s" % name)
            self._records[name] = _DeviceRecord(
                state=state,
                reason=reason or self._default_reason(state),
                changed_at=self._clock(),
            )
        return state

    def transition(
        self,
        device: str,
        state: HardwareState,
        *,
        reason: str = "",
    ) -> StateTransition:
        name = self._normalise_name(device)
        target = HardwareState(state)
        with self._lock:
            record = self._require(name)
            previous = record.state
            if target != previous and target not in _ALLOWED_TRANSITIONS[previous]:
                raise ValueError(
                    "invalid hardware state transition for %s: %s -> %s"
                    % (name, previous.value, target.value)
                )
            now = self._clock()
            transition = StateTransition(
                name,
                previous,
                target,
                reason or self._default_reason(target),
                now,
            )
            record.state = target
            record.reason = transition.reason
            record.changed_at = now
            self._history.append(transition)
            del self._history[:-self._history_limit]
            return transition

    def status(self, device: str) -> Dict[str, Any]:
        name = self._normalise_name(device)
        with self._lock:
            record = self._require(name)
            return {
                "device": name,
                "state": record.state.value,
                "reason": record.reason,
                "changed_at": record.changed_at,
                "state_age_ms": round(max(0.0, self._clock() - record.changed_at) * 1000.0, 1),
            }

    def health(self, device: str) -> Dict[str, Any]:
        status = self.status(device)
        state = HardwareState(status["state"])
        return {
            "healthy": state == HardwareState.READY,
            "available": state in {
                HardwareState.INITIALISING,
                HardwareState.READY,
                HardwareState.STALE,
            },
            "state": state.value,
            "reason": status["reason"],
        }

    def diagnostics(self, device: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if device is not None:
                name = self._normalise_name(device)
                devices = {name: self.status(name)}
                history = [item.as_dict() for item in self._history if item.device == name]
            else:
                devices = {name: self.status(name) for name in sorted(self._records)}
                history = [item.as_dict() for item in self._history]
            return {"devices": devices, "transitions": history}

    def state(self, device: str) -> HardwareState:
        with self._lock:
            return self._require(self._normalise_name(device)).state

    @staticmethod
    def _normalise_name(device: str) -> str:
        name = str(device).strip()
        if not name:
            raise ValueError("device name must not be empty")
        return name

    def _require(self, device: str) -> _DeviceRecord:
        try:
            return self._records[device]
        except KeyError as exc:
            raise KeyError("device is not registered: %s" % device) from exc

    @staticmethod
    def _default_reason(state: HardwareState) -> str:
        return state.value.replace("_", " ").title()


class HardwareServiceBase:
    """Common introspection contract used by every BX1 hardware service."""

    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        fitted: bool = True,
        enabled: bool = True,
    ) -> None:
        self.name = str(name)
        self._config = dict(config or {})
        self._state_manager = state_manager or HardwareStateManager()
        self._state_manager.register(self.name, fitted=fitted, enabled=enabled)

    def status(self) -> Dict[str, Any]:
        return self._state_manager.status(self.name)

    def health(self) -> Dict[str, Any]:
        return self._state_manager.health(self.name)

    def diagnostics(self) -> Dict[str, Any]:
        return {"service": self.name, **self._state_manager.diagnostics(self.name)}

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _transition(self, state: HardwareState, reason: str) -> StateTransition:
        return self._state_manager.transition(self.name, state, reason=reason)
