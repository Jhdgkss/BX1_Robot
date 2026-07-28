from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, Optional


def _number(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0.0 else None


class HardwareFreshnessTracker:
    """Stateful MCU/IMU freshness validation using genuinely advancing frames."""

    def __init__(
        self,
        *,
        warning_ms: float = 250.0,
        stale_ms: float = 1000.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.warning_ms = max(20.0, float(warning_ms))
        self.stale_ms = max(self.warning_ms, float(stale_ms))
        self.clock = clock
        self.last_mcu_token: Any = None
        self.last_imu_token: Any = None
        self.last_mcu_new_mono: Optional[float] = None
        self.last_imu_new_mono: Optional[float] = None

    @staticmethod
    def _mcu_token(state: Dict[str, Any]) -> Any:
        for key in ("heartbeat_sequence", "mcu_uptime_ms", "uptime_ms", "telemetry_sequence"):
            value = state.get(key)
            if value is not None:
                return (key, value)
        # No protocol counter: only a changing sensor/status fingerprint is evidence.
        return ("fingerprint", repr((
            state.get("accel_g"), state.get("gyro_dps"), state.get("mode"),
            state.get("imu_last_update_age_ms"), state.get("last_command_age_ms"),
        )))

    @staticmethod
    def _imu_token(state: Dict[str, Any]) -> Any:
        if state.get("imu_sample_sequence") is not None:
            return ("imu_sample_sequence", state.get("imu_sample_sequence"))
        # A lower MCU-reported age proves a newer sensor sample. Changing readings
        # are secondary evidence for older firmware without a sample counter.
        return ("legacy", state.get("imu_last_update_age_ms"), repr(state.get("accel_g")),
                repr(state.get("gyro_dps")))

    def evaluate(self, raw: Dict[str, Any], *, transport_connected: bool) -> Dict[str, Any]:
        now = self.clock()
        state = dict(raw)
        mcu_token = self._mcu_token(state)
        if transport_connected and (self.last_mcu_new_mono is None or mcu_token != self.last_mcu_token):
            self.last_mcu_token = mcu_token
            self.last_mcu_new_mono = now

        mcu_age = None if self.last_mcu_new_mono is None else max(0.0, (now - self.last_mcu_new_mono) * 1000.0)
        mcu_fresh = bool(transport_connected and mcu_age is not None and mcu_age <= self.stale_ms)
        mcu_stale = bool(transport_connected and not mcu_fresh)
        if not transport_connected:
            mcu_reason = "MCU transport is disconnected"
        elif mcu_age is None:
            mcu_reason = "No MCU heartbeat or telemetry frame has been received"
        elif mcu_stale:
            mcu_reason = f"MCU heartbeat stale for {mcu_age:.0f} ms"
        elif mcu_age > self.warning_ms:
            mcu_reason = f"MCU heartbeat delayed; age {mcu_age:.0f} ms"
        else:
            mcu_reason = f"MCU heartbeat fresh; age {mcu_age:.0f} ms"

        address = str(state.get("imu_address") or "").strip().lower()
        imu_present = address not in {"", "unknown", "not_detected", "none"} or bool(state.get("imu_present"))
        legacy_initialised = bool(state.get("imu_ok", False))
        imu_initialised = bool(state.get("imu_initialised", legacy_initialised))
        explicit_fault = bool(state.get("imu_error")) or int(_number(state.get("imu_read_failures")) or 0) > 0
        reported_age = _number(state.get("imu_sample_age_ms", state.get("imu_last_update_age_ms")))
        imu_token = self._imu_token(state)
        if (
            transport_connected and imu_present and imu_initialised and not explicit_fault
            and reported_age is not None and reported_age <= self.stale_ms
            and (self.last_imu_new_mono is None or imu_token != self.last_imu_token)
        ):
            self.last_imu_token = imu_token
            self.last_imu_new_mono = now

        local_imu_age = None if self.last_imu_new_mono is None else max(0.0, (now - self.last_imu_new_mono) * 1000.0)
        # MCU-reported sample age catches cached data on the first observation;
        # local age catches unchanged payloads whose embedded age is also cached.
        ages = [age for age in (reported_age, local_imu_age) if age is not None]
        imu_age = max(ages) if ages else None
        imu_sample_fresh = bool(imu_age is not None and imu_age <= self.stale_ms)
        imu_stale = not imu_sample_fresh
        imu_healthy = bool(
            transport_connected and mcu_fresh and imu_present and imu_initialised
            and imu_sample_fresh and not explicit_fault
        )
        if not transport_connected:
            imu_reason = "MCU transport is disconnected"
        elif not mcu_fresh:
            imu_reason = "MCU heartbeat stale"
        elif not imu_present:
            imu_reason = "IMU not detected"
        elif not imu_initialised:
            imu_reason = "IMU not initialised"
        elif explicit_fault:
            imu_reason = str(state.get("imu_error") or "IMU read fault active")
        elif imu_age is None:
            imu_reason = "IMU sample age is missing or malformed"
        elif imu_stale:
            imu_reason = f"IMU sample stale for {imu_age:.0f} ms"
        elif imu_age > self.warning_ms:
            imu_reason = f"IMU sample delayed; age {imu_age:.0f} ms"
        else:
            imu_reason = f"IMU sample fresh; age {imu_age:.0f} ms"

        state.update({
            "mcu_transport_connected": bool(transport_connected),
            "mcu_heartbeat_fresh": mcu_fresh,
            "mcu_last_update_age_ms": None if mcu_age is None else round(mcu_age, 1),
            "mcu_data_stale": mcu_stale,
            "mcu_health_reason": mcu_reason,
            "mcu_ok": bool(transport_connected and mcu_fresh),
            "imu_present": imu_present,
            "imu_initialised": imu_initialised,
            "imu_sample_fresh": imu_sample_fresh,
            "imu_sample_age_ms": None if imu_age is None else round(imu_age, 1),
            "imu_data_stale": imu_stale,
            "imu_healthy": imu_healthy,
            "imu_health_reason": imu_reason,
            "imu_ok": imu_healthy,  # compatibility field now means validated health
            "balance_ready": False,  # Phase 1A: balance remains explicitly disabled
        })
        return state
