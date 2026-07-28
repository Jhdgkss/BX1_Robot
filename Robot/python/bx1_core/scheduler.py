from __future__ import annotations

import copy
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional


@dataclass
class ScheduledTask:
    task_id: str
    name: str
    callback: Callable[[], Any]
    due_at: float
    interval_s: Optional[float]
    sequence: int = 0
    enabled: bool = True
    run_count: int = 0
    last_run_at: Optional[float] = None
    last_error: str = ""

    @property
    def periodic(self) -> bool:
        return self.interval_s is not None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "due_at": self.due_at,
            "interval_s": self.interval_s,
            "sequence": self.sequence,
            "periodic": self.periodic,
            "enabled": self.enabled,
            "run_count": self.run_count,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
        }


class SchedulerService:
    """Cooperative scheduler: callbacks run only when ``tick`` is called."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = {
            "enabled": True,
            "cooperative": True,
            "max_callbacks_per_tick": 100,
            "heartbeat_interval_s": 1.0,
            **dict(config or {}),
        }
        self._clock = clock
        self._tasks: Dict[str, ScheduledTask] = {}
        self._tick_callbacks: Dict[str, Callable[[float], Any]] = {}
        self._tick_count = 0
        self._callback_count = 0
        self._failure_count = 0
        self._schedule_sequence = 0
        self._last_tick_at: Optional[float] = None

    def schedule_periodic(
        self,
        interval_s: Any,
        callback: Callable[[], Any],
        *,
        name: str = "",
        delay_s: Optional[Any] = None,
    ) -> str:
        interval = self._positive(interval_s, "interval_s")
        delay = interval if delay_s is None else self._nonnegative(delay_s, "delay_s")
        return self._schedule(callback, delay, interval, name)

    def schedule_once(
        self,
        delay_s: Any,
        callback: Callable[[], Any],
        *,
        name: str = "",
    ) -> str:
        return self._schedule(
            callback,
            self._nonnegative(delay_s, "delay_s"),
            None,
            name,
        )

    def call_later(
        self,
        delay_s: Any,
        callback: Callable[[], Any],
        *,
        name: str = "",
    ) -> str:
        return self.schedule_once(delay_s, callback, name=name)

    def add_tick_callback(self, callback: Callable[[float], Any]) -> str:
        if not callable(callback):
            raise TypeError("tick callback must be callable")
        token = uuid.uuid4().hex
        self._tick_callbacks[token] = callback
        return token

    def remove_tick_callback(self, token: str) -> bool:
        return self._tick_callbacks.pop(str(token), None) is not None

    def cancel(self, task_id: str) -> bool:
        return self._tasks.pop(str(task_id), None) is not None

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        current = self._clock() if now is None else float(now)
        if not bool(self._config["enabled"]):
            return {
                "now": current,
                "tick": self._tick_count,
                "executed": [],
                "failures": [],
                "due_remaining": 0,
                "disabled": True,
            }
        self._tick_count += 1
        self._last_tick_at = current
        failures: List[str] = []
        executed: List[str] = []

        for token, callback in list(self._tick_callbacks.items()):
            try:
                callback(current)
                self._callback_count += 1
            except Exception as exc:
                failures.append("tick:%s: %s" % (token, exc))
                self._failure_count += 1

        limit = max(1, int(self._config["max_callbacks_per_tick"]))
        due = sorted(
            (
                task
                for task in self._tasks.values()
                if task.enabled and task.due_at <= current
            ),
            key=lambda item: (item.due_at, item.sequence),
        )
        for task in due[:limit]:
            try:
                task.callback()
                task.last_error = ""
            except Exception as exc:
                task.last_error = str(exc)
                failures.append("%s: %s" % (task.task_id, exc))
                self._failure_count += 1
            task.run_count += 1
            task.last_run_at = current
            self._callback_count += 1
            executed.append(task.task_id)
            if task.interval_s is None:
                self._tasks.pop(task.task_id, None)
            else:
                missed = max(1, int(math.floor((current - task.due_at) / task.interval_s)) + 1)
                task.due_at += missed * task.interval_s

        return {
            "now": current,
            "tick": self._tick_count,
            "executed": executed,
            "failures": failures,
            "due_remaining": max(0, len(due) - limit),
        }

    def run_pending(self, now: Optional[float] = None) -> Dict[str, Any]:
        return self.tick(now)

    def heartbeat(self) -> Dict[str, Any]:
        now = self._clock()
        age = (
            None
            if self._last_tick_at is None
            else max(0.0, (now - self._last_tick_at) * 1000.0)
        )
        interval = float(self._config["heartbeat_interval_s"])
        return {
            "tick_count": self._tick_count,
            "last_tick_at": self._last_tick_at,
            "age_ms": age,
            "alive": age is not None and age <= interval * 2000.0,
            "cooperative": True,
        }

    def status(self) -> Dict[str, Any]:
        return {
            "service": "scheduler",
            "state": "READY" if self._config["enabled"] else "DISABLED",
            "task_count": len(self._tasks),
            "tick_count": self._tick_count,
        }

    def health(self) -> Dict[str, Any]:
        state = self.status()["state"]
        return {
            "healthy": state == "READY",
            "available": state == "READY",
            "state": state,
            "reason": "Cooperative scheduler ready" if state == "READY" else "Scheduler disabled",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "tasks": {
                task_id: task.as_dict()
                for task_id, task in sorted(self._tasks.items())
            },
            "heartbeat": self.heartbeat(),
            "tick_callbacks": len(self._tick_callbacks),
            "callback_count": self._callback_count,
            "failure_count": self._failure_count,
            "threaded": False,
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _schedule(
        self,
        callback: Callable[[], Any],
        delay_s: float,
        interval_s: Optional[float],
        name: str,
    ) -> str:
        if not callable(callback):
            raise TypeError("scheduled callback must be callable")
        task_id = uuid.uuid4().hex
        self._schedule_sequence += 1
        self._tasks[task_id] = ScheduledTask(
            task_id,
            str(name).strip() or task_id,
            callback,
            self._clock() + delay_s,
            interval_s,
            self._schedule_sequence,
        )
        return task_id

    @staticmethod
    def _positive(value: Any, label: str) -> float:
        result = float(value)
        if not math.isfinite(result) or result <= 0.0:
            raise ValueError("%s must be finite and greater than zero" % label)
        return result

    @staticmethod
    def _nonnegative(value: Any, label: str) -> float:
        result = float(value)
        if not math.isfinite(result) or result < 0.0:
            raise ValueError("%s must be finite and non-negative" % label)
        return result
