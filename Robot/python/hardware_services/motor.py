from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Callable, Deque, Dict, List, Optional

from .state import HardwareServiceBase, HardwareState, HardwareStateManager

LOG = logging.getLogger(__name__)

DEFAULT_MOTOR_CONFIG: Dict[str, Any] = {
    "drive_enabled": False,
    "drive_dry_run": True,
    "rs485_enabled": False,
    "serial_port": "",
    "baud_rate": 115200,
    "addresses": {"left": 1, "right": 2},
    "inversion": {"left": False, "right": True},
    "acceleration": 0.5,
    "limits": {
        "max_speed": 1.0,
        "max_acceleration": 1.0,
        "max_duration_s": 5.0,
    },
    "timeout_s": 1.0,
}


@dataclass
class MotorState:
    sequence: int = 0
    left_requested: float = 0.0
    right_requested: float = 0.0
    left_applied: float = 0.0
    right_applied: float = 0.0
    acceleration: float = 0.0
    duration_s: float = 0.0
    stopped: bool = True
    dry_run: bool = True
    updated_at: float = 0.0
    reason: str = "No command received"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CommandValidator:
    """Pure validation for wheel commands; it performs no transport work."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = _motor_config(config)

    def validate(
        self,
        left_speed: Any,
        right_speed: Any,
        duration_s: Any,
        acceleration: Any = None,
    ) -> Dict[str, Any]:
        errors: List[str] = []
        left = self._finite(left_speed, "left_speed", errors)
        right = self._finite(right_speed, "right_speed", errors)
        duration = self._finite(duration_s, "duration_s", errors)
        accel_raw = self._config["acceleration"] if acceleration is None else acceleration
        accel = self._finite(accel_raw, "acceleration", errors)
        limits = self._config["limits"]

        if abs(left) > limits["max_speed"]:
            errors.append("left_speed exceeds max_speed")
        if abs(right) > limits["max_speed"]:
            errors.append("right_speed exceeds max_speed")
        if duration <= 0.0:
            errors.append("duration_s must be greater than zero")
        elif duration > limits["max_duration_s"]:
            errors.append("duration_s exceeds max_duration_s")
        if accel <= 0.0:
            errors.append("acceleration must be greater than zero")
        elif accel > limits["max_acceleration"]:
            errors.append("acceleration exceeds max_acceleration")

        command = {
            "left_speed": left,
            "right_speed": right,
            "duration_s": duration,
            "acceleration": accel,
        }
        return {"valid": not errors, "errors": errors, "command": command}

    def configuration(self) -> Dict[str, Any]:
        return _copy_config(self._config)

    @staticmethod
    def _finite(value: Any, label: str, errors: List[str]) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError):
            errors.append("%s must be numeric" % label)
            return 0.0
        if not math.isfinite(result):
            errors.append("%s must be finite" % label)
            return 0.0
        return result


class RS485Transport(HardwareServiceBase):
    """Phase 1B RS485 shape with a non-bypassable no-I/O interlock."""

    HARDWARE_IO_PERMITTED = False

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = _motor_config(config)
        enabled = bool(cfg["rs485_enabled"])
        super().__init__(
            "rs485_transport",
            cfg,
            state_manager=state_manager,
            fitted=True,
            enabled=enabled,
        )
        self._clock = clock
        self._transmissions: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._lock = threading.Lock()
        if enabled:
            self._transition(
                HardwareState.FAULT,
                "RS485 hardware I/O is locked out in Phase 1B",
            )

    @property
    def is_open(self) -> bool:
        return False

    def open(self) -> None:
        raise RuntimeError("RS485 serial opening is prohibited in Phase 1B")

    def transmit(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """Record a dry-run packet. No serial module is imported or port opened."""
        entry = {
            "timestamp": self._clock(),
            "packet": dict(packet),
            "dry_run": True,
            "transmitted": False,
            "reason": "Phase 1B dry-run: RS485 transmission suppressed",
        }
        with self._lock:
            self._transmissions.append(entry)
        LOG.info("BX1 motor dry-run packet: %s", entry["packet"])
        return dict(entry)

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        with self._lock:
            base.update(
                {
                    "is_open": False,
                    "hardware_io_permitted": self.HARDWARE_IO_PERMITTED,
                    "recorded_transmissions": len(self._transmissions),
                    "transmissions": list(self._transmissions),
                }
            )
        return base


class MotorController(HardwareServiceBase):
    """Address/inversion layer above the dry-run RS485 transport."""

    def __init__(
        self,
        transport: RS485Transport,
        config: Optional[Dict[str, Any]] = None,
        *,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = _motor_config(config)
        enabled = bool(cfg["drive_enabled"])
        super().__init__(
            "motor_controller",
            cfg,
            state_manager=state_manager,
            fitted=True,
            enabled=enabled,
        )
        self.transport = transport
        self._clock = clock
        self._state = MotorState(dry_run=True)
        self._lock = threading.Lock()
        if enabled:
            if cfg["drive_dry_run"]:
                self._transition(HardwareState.READY, "Motor controller ready in dry-run mode")
            else:
                self._transition(
                    HardwareState.FAULT,
                    "Non-dry-run motor control is prohibited in Phase 1B",
                )

    def apply(self, command: Dict[str, float]) -> Dict[str, Any]:
        left = float(command["left_speed"])
        right = float(command["right_speed"])
        inversion = self._config["inversion"]
        applied_left = -left if inversion["left"] else left
        applied_right = -right if inversion["right"] else right
        packet = {
            "addresses": dict(self._config["addresses"]),
            "left_speed": applied_left,
            "right_speed": applied_right,
            "acceleration": float(command["acceleration"]),
            "duration_s": float(command["duration_s"]),
            "timeout_s": float(self._config["timeout_s"]),
        }
        result = self.transport.transmit(packet)
        with self._lock:
            self._state.sequence += 1
            self._state.left_requested = left
            self._state.right_requested = right
            self._state.left_applied = applied_left
            self._state.right_applied = applied_right
            self._state.acceleration = packet["acceleration"]
            self._state.duration_s = packet["duration_s"]
            self._state.stopped = left == 0.0 and right == 0.0
            self._state.dry_run = True
            self._state.updated_at = self._clock()
            self._state.reason = result["reason"]
            state = self._state.as_dict()
        return {"accepted": True, "state": state, "transport": result}

    def motor_state(self) -> MotorState:
        with self._lock:
            return MotorState(**self._state.as_dict())

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        base.update({"motor_state": self.motor_state().as_dict()})
        return base


class DriveService(HardwareServiceBase):
    """Validated public motion API. Phase 1B accepts dry-run commands only."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        transport: Optional[RS485Transport] = None,
        controller: Optional[MotorController] = None,
        state_manager: Optional[HardwareStateManager] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        cfg = _motor_config(config)
        manager = state_manager or HardwareStateManager(clock=clock)
        enabled = bool(cfg["drive_enabled"])
        super().__init__(
            "drive_service",
            cfg,
            state_manager=manager,
            fitted=True,
            enabled=enabled,
        )
        self._clock = clock
        self.validator = CommandValidator(cfg)
        self.transport = transport or RS485Transport(cfg, state_manager=manager, clock=clock)
        self.controller = controller or MotorController(
            self.transport, cfg, state_manager=manager, clock=clock
        )
        self._command_log: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._lock = threading.Lock()
        if enabled:
            if cfg["rs485_enabled"]:
                self._transition(
                    HardwareState.FAULT,
                    "RS485 must remain disabled in Phase 1B",
                )
            elif not cfg["drive_dry_run"]:
                self._transition(
                    HardwareState.FAULT,
                    "Non-dry-run drive is prohibited in Phase 1B",
                )
            else:
                self._transition(HardwareState.READY, "Drive ready for validated dry-run commands")

    def drive_wheels(
        self,
        left_speed: Any,
        right_speed: Any,
        *,
        duration_s: Any,
        acceleration: Any = None,
    ) -> Dict[str, Any]:
        validation = self.validator.validate(
            left_speed, right_speed, duration_s, acceleration
        )
        entry: Dict[str, Any] = {
            "timestamp": self._clock(),
            "validation": validation,
            "accepted": False,
            "dry_run": True,
        }
        if not self._config["drive_enabled"]:
            entry["errors"] = ["drive service is disabled"]
        elif self._config["rs485_enabled"]:
            entry["errors"] = ["RS485 must remain disabled in Phase 1B"]
        elif not self._config["drive_dry_run"]:
            entry["errors"] = ["non-dry-run drive is prohibited in Phase 1B"]
        elif not validation["valid"]:
            entry["errors"] = list(validation["errors"])
        else:
            result = self.controller.apply(validation["command"])
            entry.update(result)
            entry["accepted"] = True
            entry["errors"] = []

        self._record(entry)
        return dict(entry)

    def drive(
        self,
        linear_speed: Any,
        angular_speed: Any,
        *,
        duration_s: Any,
        acceleration: Any = None,
    ) -> Dict[str, Any]:
        """Convert a differential-drive request into validated wheel speeds."""
        try:
            linear = float(linear_speed)
            angular = float(angular_speed)
            left = linear - angular
            right = linear + angular
        except (TypeError, ValueError):
            # Route malformed inputs through the same validator and audit log.
            return self.drive_wheels(
                linear_speed,
                angular_speed,
                duration_s=duration_s,
                acceleration=acceleration,
            )
        result = self.drive_wheels(
            left,
            right,
            duration_s=duration_s,
            acceleration=acceleration,
        )
        result["drive_request"] = {
            "linear_speed": linear,
            "angular_speed": angular,
        }
        return result

    def stop(self) -> Dict[str, Any]:
        """Validate and record a zero-speed dry-run command."""
        return self.drive_wheels(0.0, 0.0, duration_s=0.001, acceleration=0.001)

    def motor_state(self) -> MotorState:
        return self.controller.motor_state()

    def diagnostics(self) -> Dict[str, Any]:
        base = super().diagnostics()
        with self._lock:
            command_log = list(self._command_log)
        base.update(
            {
                "dry_run": True,
                "command_count": len(command_log),
                "commands": command_log,
                "motor_state": self.motor_state().as_dict(),
                "transport": self.transport.diagnostics(),
                "controller": self.controller.diagnostics(),
            }
        )
        return base

    def _record(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            self._command_log.append(entry)
        if entry["accepted"]:
            LOG.info("BX1 validated motor command (dry-run): %s", entry)
        else:
            LOG.warning("BX1 rejected motor command: %s", entry)


def _motor_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    incoming = dict(config or {})
    limits = {**DEFAULT_MOTOR_CONFIG["limits"], **dict(incoming.get("limits") or {})}
    addresses = {
        **DEFAULT_MOTOR_CONFIG["addresses"],
        **dict(incoming.get("addresses") or {}),
    }
    inversion = {
        **DEFAULT_MOTOR_CONFIG["inversion"],
        **dict(incoming.get("inversion") or {}),
    }
    result = {
        **DEFAULT_MOTOR_CONFIG,
        **incoming,
        "limits": limits,
        "addresses": addresses,
        "inversion": inversion,
    }
    result["baud_rate"] = int(result["baud_rate"])
    result["acceleration"] = float(result["acceleration"])
    result["timeout_s"] = float(result["timeout_s"])
    result["limits"] = {key: float(value) for key, value in limits.items()}
    result["addresses"] = {key: int(value) for key, value in addresses.items()}
    result["inversion"] = {key: bool(value) for key, value in inversion.items()}
    return result


def _copy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **config,
        "limits": dict(config["limits"]),
        "addresses": dict(config["addresses"]),
        "inversion": dict(config["inversion"]),
    }
