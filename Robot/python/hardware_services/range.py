from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Dict, Iterable, List, Optional

from .state import HardwareServiceBase, HardwareState, HardwareStateManager


@dataclass(frozen=True)
class DistanceReading:
    distance_mm: Optional[float]
    signal_quality: float
    available: bool
    healthy: bool
    sample_age_ms: Optional[float]
    out_of_range: bool
    fault_reason: str
    sampled_at: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DistanceSensorBase(HardwareServiceBase, ABC):
    """Backend contract used by RangeService for real and simulated sensors."""

    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        fitted: bool,
        enabled: bool,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            name,
            config,
            state_manager=state_manager,
            fitted=fitted,
            enabled=enabled,
        )
        self._clock = clock
        self._reading = DistanceReading(
            None,
            0.0,
            False,
            False,
            None,
            True,
            "No sample available",
            None,
        )

    @abstractmethod
    def sample(self) -> DistanceReading:
        raise NotImplementedError

    def reading(self) -> DistanceReading:
        if self._reading.sampled_at is None:
            return self._reading
        age = max(0.0, (self._clock() - self._reading.sampled_at) * 1000.0)
        return replace(self._reading, sample_age_ms=round(age, 1))

    @property
    def distance_mm(self) -> Optional[float]:
        return self.reading().distance_mm

    @property
    def signal_quality(self) -> float:
        return self.reading().signal_quality

    @property
    def available(self) -> bool:
        return self.reading().available

    @property
    def healthy(self) -> bool:
        return self.reading().healthy

    @property
    def sample_age_ms(self) -> Optional[float]:
        return self.reading().sample_age_ms

    @property
    def out_of_range(self) -> bool:
        return self.reading().out_of_range

    @property
    def fault_reason(self) -> str:
        return self.reading().fault_reason

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        base["reading"] = self.reading().as_dict()
        return base


class MockDistanceSensor(DistanceSensorBase):
    """Configurable distance source for tests and the Digital Twin."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = {
            "enabled": True,
            "min_distance_mm": 20.0,
            "max_distance_mm": 4000.0,
            "default_distance_mm": 1000.0,
            "default_signal_quality": 1.0,
            "repeat_readings": True,
            **dict(config or {}),
        }
        enabled = bool(cfg["enabled"])
        super().__init__(
            "mock_range_sensor",
            cfg,
            state_manager=state_manager,
            fitted=True,
            enabled=enabled,
            clock=clock,
        )
        self._samples: List[Dict[str, Any]] = []
        self._sample_index = 0
        self.configure_readings(cfg.get("readings", []))
        if enabled:
            self._transition(HardwareState.READY, "Mock distance sensor ready")

    def configure_readings(self, readings: Iterable[Any]) -> None:
        samples: List[Dict[str, Any]] = []
        for item in readings:
            if isinstance(item, dict):
                samples.append(dict(item))
            else:
                samples.append({"distance_mm": item})
        self._samples = samples
        self._sample_index = 0

    def set_reading(
        self,
        distance_mm: Optional[float],
        *,
        signal_quality: float = 1.0,
        available: bool = True,
        healthy: bool = True,
        fault_reason: str = "",
    ) -> None:
        self.configure_readings(
            [
                {
                    "distance_mm": distance_mm,
                    "signal_quality": signal_quality,
                    "available": available,
                    "healthy": healthy,
                    "fault_reason": fault_reason,
                }
            ]
        )

    def sample(self) -> DistanceReading:
        if self.status()["state"] == HardwareState.DISABLED.value:
            self._reading = DistanceReading(
                None, 0.0, False, False, None, True, "Mock sensor is disabled", None
            )
            return self._reading

        if self._samples:
            index = min(self._sample_index, len(self._samples) - 1)
            data = dict(self._samples[index])
            if self._config["repeat_readings"]:
                self._sample_index = (self._sample_index + 1) % len(self._samples)
            else:
                self._sample_index += 1
        else:
            data = {
                "distance_mm": self._config["default_distance_mm"],
                "signal_quality": self._config["default_signal_quality"],
            }

        available = bool(data.get("available", True))
        healthy = bool(data.get("healthy", available))
        fault = str(data.get("fault_reason", ""))
        distance = data.get("distance_mm")
        try:
            distance_value = None if distance is None else float(distance)
        except (TypeError, ValueError):
            distance_value = None
            healthy = False
            fault = fault or "Distance reading is not numeric"
        quality = max(0.0, min(1.0, float(data.get("signal_quality", 1.0))))
        minimum = float(self._config["min_distance_mm"])
        maximum = float(self._config["max_distance_mm"])
        out_of_range = (
            distance_value is None
            or distance_value < minimum
            or distance_value > maximum
        )
        if not available:
            healthy = False
            fault = fault or "Distance sensor unavailable"
        elif not healthy:
            fault = fault or "Distance sensor reported a fault"
        elif out_of_range:
            fault = fault or "Distance is outside configured range"

        now = self._clock()
        self._reading = DistanceReading(
            distance_value,
            quality,
            available,
            healthy,
            0.0,
            out_of_range,
            fault,
            now,
        )
        if healthy:
            current = HardwareState(self.status()["state"])
            if current == HardwareState.STALE:
                self._transition(HardwareState.READY, "Fresh mock distance sample")
            elif current == HardwareState.FAULT:
                self._transition(HardwareState.INITIALISING, "Mock distance sensor recovering")
                self._transition(HardwareState.READY, "Mock distance sensor recovered")
        elif HardwareState(self.status()["state"]) != HardwareState.FAULT:
            self._transition(HardwareState.FAULT, fault)
        return self._reading


class FutureToFSensor(DistanceSensorBase):
    """Reserved physical ToF adapter. It deliberately performs no hardware I/O."""

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
            "driver": "",
            "bus": "",
            "address": None,
            **dict(config or {}),
        }
        super().__init__(
            "future_tof_sensor",
            cfg,
            state_manager=state_manager,
            fitted=False,
            enabled=False,
            clock=clock,
        )

    def sample(self) -> DistanceReading:
        self._reading = DistanceReading(
            None,
            0.0,
            False,
            False,
            None,
            True,
            "ToF hardware adapter is not implemented or fitted",
            None,
        )
        return self._reading


class RangeService(HardwareServiceBase):
    def __init__(
        self,
        sensor: DistanceSensorBase,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = {
            "enabled": True,
            "stale_after_ms": 1000.0,
            **dict(config or {}),
        }
        enabled = bool(cfg["enabled"])
        super().__init__(
            "range_service",
            cfg,
            state_manager=state_manager,
            fitted=True,
            enabled=enabled,
        )
        self.sensor = sensor
        self._clock = clock
        if enabled:
            if sensor.available or sensor.status()["state"] == HardwareState.READY.value:
                self._transition(HardwareState.READY, "Range sensor adapter ready")
            elif sensor.status()["state"] == HardwareState.NOT_FITTED.value:
                self._transition(HardwareState.FAULT, "No fitted range sensor")
            else:
                self._transition(HardwareState.READY, "Range service ready; awaiting first sample")

    def poll(self) -> DistanceReading:
        reading = self.sensor.sample()
        if self.status()["state"] == HardwareState.DISABLED.value:
            return reading
        if not reading.available or not reading.healthy:
            self._set_state(HardwareState.FAULT, reading.fault_reason or "Range sensor fault")
        else:
            self._set_state(HardwareState.READY, "Fresh distance sample")
        return reading

    def reading(self) -> DistanceReading:
        reading = self.sensor.reading()
        age = reading.sample_age_ms
        if (
            age is not None
            and age > float(self._config["stale_after_ms"])
            and self.status()["state"] == HardwareState.READY.value
        ):
            self._transition(
                HardwareState.STALE,
                "Distance sample stale for %.1f ms" % age,
            )
            return replace(reading, healthy=False, fault_reason="Distance sample is stale")
        return reading

    @property
    def distance_mm(self) -> Optional[float]:
        return self.reading().distance_mm

    @property
    def signal_quality(self) -> float:
        return self.reading().signal_quality

    @property
    def available(self) -> bool:
        return self.reading().available

    @property
    def healthy(self) -> bool:
        return self.reading().healthy and self.health()["healthy"]

    @property
    def sample_age_ms(self) -> Optional[float]:
        return self.reading().sample_age_ms

    @property
    def out_of_range(self) -> bool:
        return self.reading().out_of_range

    @property
    def fault_reason(self) -> str:
        reading = self.reading()
        return reading.fault_reason or self.status()["reason"]

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        base.update(
            {
                "reading": self.reading().as_dict(),
                "sensor": self.sensor.diagnostics(),
            }
        )
        return base

    def _set_state(self, target: HardwareState, reason: str) -> None:
        current = HardwareState(self.status()["state"])
        if current == target:
            return
        if current == HardwareState.FAULT and target == HardwareState.READY:
            self._transition(HardwareState.INITIALISING, "Range sensor recovering")
        self._transition(target, reason)
