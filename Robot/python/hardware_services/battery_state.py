from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class BatteryState(str, Enum):
    NOT_FITTED = "NOT_FITTED"
    INITIALISING = "INITIALISING"
    READY = "READY"
    LOW = "LOW"
    CRITICAL = "CRITICAL"
    CHARGING = "CHARGING"
    FULL = "FULL"
    FAULT = "FAULT"
    SHUTDOWN_PENDING = "SHUTDOWN_PENDING"


_TRANSITIONS: Dict[BatteryState, Set[BatteryState]] = {
    BatteryState.NOT_FITTED: {BatteryState.INITIALISING},
    BatteryState.INITIALISING: {
        BatteryState.NOT_FITTED,
        BatteryState.READY,
        BatteryState.LOW,
        BatteryState.CRITICAL,
        BatteryState.CHARGING,
        BatteryState.FULL,
        BatteryState.FAULT,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.READY: {
        BatteryState.NOT_FITTED,
        BatteryState.LOW,
        BatteryState.CRITICAL,
        BatteryState.CHARGING,
        BatteryState.FULL,
        BatteryState.FAULT,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.LOW: {
        BatteryState.NOT_FITTED,
        BatteryState.READY,
        BatteryState.CRITICAL,
        BatteryState.CHARGING,
        BatteryState.FULL,
        BatteryState.FAULT,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.CRITICAL: {
        BatteryState.NOT_FITTED,
        BatteryState.READY,
        BatteryState.LOW,
        BatteryState.CHARGING,
        BatteryState.FULL,
        BatteryState.FAULT,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.CHARGING: {
        BatteryState.NOT_FITTED,
        BatteryState.READY,
        BatteryState.LOW,
        BatteryState.CRITICAL,
        BatteryState.FULL,
        BatteryState.FAULT,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.FULL: {
        BatteryState.NOT_FITTED,
        BatteryState.READY,
        BatteryState.LOW,
        BatteryState.CRITICAL,
        BatteryState.CHARGING,
        BatteryState.FAULT,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.FAULT: {
        BatteryState.NOT_FITTED,
        BatteryState.INITIALISING,
        BatteryState.SHUTDOWN_PENDING,
    },
    BatteryState.SHUTDOWN_PENDING: {
        BatteryState.NOT_FITTED,
        BatteryState.INITIALISING,
        BatteryState.READY,
        BatteryState.LOW,
        BatteryState.CRITICAL,
        BatteryState.CHARGING,
        BatteryState.FULL,
        BatteryState.FAULT,
    },
}


@dataclass(frozen=True)
class BatteryTransition:
    previous: BatteryState
    current: BatteryState
    reason: str
    timestamp: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "previous": self.previous.value,
            "current": self.current.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class BatteryStateMachine:
    """Battery-specific lifecycle; deliberately independent of hardware state."""

    def __init__(
        self,
        *,
        fitted: bool = True,
        clock: Callable[[], float] = time.monotonic,
        history_limit: int = 100,
    ) -> None:
        self._clock = clock
        self._history_limit = max(1, int(history_limit))
        self._state = (
            BatteryState.INITIALISING if fitted else BatteryState.NOT_FITTED
        )
        self._reason = "Battery initialising" if fitted else "Battery not fitted"
        self._changed_at = self._clock()
        self._history: List[BatteryTransition] = []

    @property
    def state(self) -> BatteryState:
        return self._state

    def transition(self, state: BatteryState, reason: str = "") -> BatteryTransition:
        target = BatteryState(state)
        previous = self._state
        if target != previous and target not in _TRANSITIONS[previous]:
            raise ValueError(
                "invalid battery state transition: %s -> %s"
                % (previous.value, target.value)
            )
        now = self._clock()
        item = BatteryTransition(
            previous,
            target,
            str(reason).strip() or target.value.replace("_", " ").title(),
            now,
        )
        self._state = target
        self._reason = item.reason
        self._changed_at = now
        self._history.append(item)
        del self._history[:-self._history_limit]
        return item

    def status(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "reason": self._reason,
            "changed_at": self._changed_at,
            "state_age_ms": round(max(0.0, self._clock() - self._changed_at) * 1000.0, 1),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "healthy": self._state in {
                BatteryState.READY,
                BatteryState.CHARGING,
                BatteryState.FULL,
            },
            "available": self._state != BatteryState.NOT_FITTED,
            "state": self._state.value,
            "reason": self._reason,
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            **self.status(),
            "transitions": [item.as_dict() for item in self._history],
        }

    def configuration(self) -> Dict[str, Any]:
        return {
            "history_limit": self._history_limit,
            "legal_transitions": {
                state.value: sorted(target.value for target in targets)
                for state, targets in _TRANSITIONS.items()
            },
        }
