from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .audio import AudioAdapter
from .camera import CameraAdapter
from .device import DeviceHealth, DeviceRecord, HardwareEnvironment
from .display import DisplayAdapter
from .health import observer_diagnostics
from .imu import ImuAdapter
from .input_devices import InputDeviceAdapter
from .motors import MotorAdapter
from .robot_body import RobotBodyClient
from .serial import SerialAdapter
from .servos import ServoAdapter


class ReadOnlyHardwareInventory:
    """Failure-isolated aggregation of metadata-only hardware adapters."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        environment: Optional[HardwareEnvironment] = None,
        robot_body_client: Optional[RobotBodyClient] = None,
    ) -> None:
        self.config = copy.deepcopy(dict(config or {}))
        self.environment = environment or HardwareEnvironment()
        adapter_config = self.config.get("hardware_observer", {})
        if not isinstance(adapter_config, Mapping):
            adapter_config = {}
        self.robot_body = robot_body_client or RobotBodyClient(
            str(
                adapter_config.get(
                    "robot_body_url", "http://127.0.0.1:8088"
                )
            ),
            timeout=float(adapter_config.get("timeout_seconds", 0.5)),
            clock=self.environment.clock,
        )
        self.audio = AudioAdapter(self.environment)
        self.camera = CameraAdapter(self.environment)
        self.serial = SerialAdapter(self.environment)
        self.inputs = InputDeviceAdapter(self.environment)
        self.display = DisplayAdapter(self.environment)
        self.imu = ImuAdapter()
        self.servos = ServoAdapter()
        self.motors = MotorAdapter()

    def collect(self) -> Dict[str, Any]:
        self._adapter_failures: Dict[str, str] = {}
        timestamp = self.environment.clock()
        failures: Dict[str, str] = {}
        try:
            body = self.robot_body.collect()
        except Exception as exc:
            body = {
                "connected": False,
                "version": "unknown",
                "health": "unavailable",
                "active_faults": [],
                "timestamp": timestamp,
                "source": "Existing Robot Body",
                "error": str(exc),
                "microphone": {},
                "speaker": {},
                "stt": {"state": "unknown"},
                "tts": {"state": "unknown"},
                "mcu": {"state": "unknown"},
                "imu": {"state": "unknown"},
                "camera": {"state": "unknown"},
                "hardware": {},
            }
            failures["robot_body"] = str(exc)

        microphones, speakers, audio_telemetry = self._safe(
            "audio", lambda: self.audio.discover(body), ([], [], {})
        )
        cameras = self._safe(
            "camera", lambda: self.camera.discover(body), []
        )
        serial = self._safe(
            "serial", lambda: self.serial.discover(body), []
        )
        inputs = self._safe("input_devices", self.inputs.discover, [])
        displays = self._safe("display", self.display.discover, [])
        imu = self._safe(
            "imu", lambda: self.imu.discover(body, timestamp), None
        )
        servos = self._safe(
            "servos", lambda: self.servos.discover(body, timestamp), None
        )
        motors = self._safe(
            "motors", lambda: self.motors.discover(body, timestamp), None
        )
        network = self._safe(
            "network", lambda: self._network(timestamp), []
        )
        battery = self._safe(
            "battery", lambda: self._battery(timestamp), []
        )
        mcu = self._safe(
            "mcu", lambda: self._mcu(body, serial, timestamp), None
        )

        records: List[DeviceRecord] = [
            *microphones,
            *speakers,
            *cameras,
            *serial,
            *inputs,
            *displays,
            *network,
            *battery,
        ]
        records.extend(item for item in (mcu, imu, servos, motors) if item)
        values = [item.as_dict() for item in records]
        diagnostics = self._safe(
            "diagnostics",
            lambda: observer_diagnostics(values, body),
            {
                "checks": [],
                "required_failures": ["observer diagnostics unavailable"],
                "healthy": False,
                "optional_absence_is_fault": False,
            },
        )
        failures.update(getattr(self, "_adapter_failures", {}))
        return {
            "schema": "bx1.core.hardware.inventory.v1",
            "timestamp": timestamp,
            "source": "BX1 OS read-only hardware observers",
            "quality": (
                "observed"
                if body.get("connected") and not failures
                else "degraded"
                if values
                else "unavailable"
            ),
            "stale": False,
            "observer_only": True,
            "ownership_taken": False,
            "hardware_actions_requested": False,
            "devices_opened": False,
            "inventory": values,
            "categories": self._categories(values),
            "audio": {
                "microphones": [item.as_dict() for item in microphones],
                "speakers": [item.as_dict() for item in speakers],
                "telemetry": audio_telemetry,
            },
            "camera": [item.as_dict() for item in cameras],
            "serial": [item.as_dict() for item in serial],
            "mcu": mcu.as_dict() if mcu else {},
            "imu": imu.as_dict() if imu else {},
            "servos": servos.as_dict() if servos else {},
            "motors": motors.as_dict() if motors else {},
            "touchscreen": [
                item.as_dict()
                for item in inputs
                if item.category == "touchscreen"
            ],
            "display": [item.as_dict() for item in displays],
            "network": [item.as_dict() for item in network],
            "battery": [item.as_dict() for item in battery],
            "robot_body": body,
            "diagnostics": diagnostics,
            "adapter_failures": failures,
        }

    def _safe(self, name: str, callback: Any, fallback: Any) -> Any:
        try:
            return callback()
        except Exception as exc:
            if not hasattr(self, "_adapter_failures"):
                self._adapter_failures: Dict[str, str] = {}
            self._adapter_failures[name] = str(exc)
            return copy.deepcopy(fallback)

    def _network(self, timestamp: float) -> List[DeviceRecord]:
        interfaces, error = self.environment.glob(
            self.environment.sys_root / "class" / "net", "*"
        )
        records = []
        for interface in interfaces:
            operstate, _ = self.environment.read_text(interface / "operstate")
            address, _ = self.environment.read_text(interface / "address")
            wireless, _ = self.environment.exists(interface / "wireless")
            state = operstate.strip().lower() or "unknown"
            records.append(
                DeviceRecord(
                    device_id="network:%s" % interface.name,
                    name=interface.name,
                    category="network_adapter",
                    present=True,
                    available=state == "up",
                    ownership="kernel",
                    health=DeviceHealth(
                        "online" if state == "up" else "detected",
                        "Network metadata only",
                    ),
                    details={
                        "interface": interface.name,
                        "operstate": state,
                        "address": address.strip(),
                        "wireless": wireless,
                        "signal": "unavailable",
                    },
                    last_seen=timestamp,
                    capabilities={"metadata": True, "configuration": False},
                    source="sysfs network metadata",
                )
            )
        if not records and error == "permission_denied":
            return [self._permission_record("network_adapter", error)]
        return records

    def _battery(self, timestamp: float) -> List[DeviceRecord]:
        interfaces, error = self.environment.glob(
            self.environment.sys_root / "class" / "power_supply", "*"
        )
        records = []
        for interface in interfaces:
            supply_type, _ = self.environment.read_text(interface / "type")
            if supply_type.strip().lower() not in {"battery", "ups"}:
                continue
            capacity, _ = self.environment.read_text(interface / "capacity")
            status, _ = self.environment.read_text(interface / "status")
            records.append(
                DeviceRecord(
                    device_id="battery:%s" % interface.name,
                    name=interface.name,
                    category="battery",
                    present=True,
                    available=True,
                    ownership="kernel",
                    health=DeviceHealth(
                        "online", "Power-supply metadata available"
                    ),
                    details={
                        "interface": interface.name,
                        "type": supply_type.strip(),
                    },
                    last_seen=timestamp,
                    telemetry={
                        "capacity_percent": self._number(capacity),
                        "status": status.strip() or "unknown",
                    },
                    capabilities={"metadata": True, "control": False},
                    source="sysfs power-supply metadata",
                )
            )
        if not records and error == "permission_denied":
            return [self._permission_record("battery", error)]
        return records

    def _mcu(
        self,
        body: Mapping[str, Any],
        serial: List[DeviceRecord],
        timestamp: float,
    ) -> DeviceRecord:
        details = body.get("mcu")
        details = dict(details) if isinstance(details, Mapping) else {}
        state = str(details.get("state", details.get("status", "unknown"))).lower()
        known = state not in {"", "unknown", "unavailable"}
        configured_serial = next(
            (
                item.details.get("device_path")
                for item in serial
                if item.details.get("configured")
            ),
            "",
        )
        return DeviceRecord(
            device_id="mcu:robot-body",
            name=str(details.get("name", "Robot MCU")),
            category="mcu",
            present=known or bool(configured_serial),
            available=state in {"online", "ready", "healthy", "fresh", "ok"},
            ownership=(
                "bx1-web.service" if body.get("connected") else "unknown"
            ),
            health=DeviceHealth(
                "online"
                if state in {"online", "ready", "healthy", "fresh", "ok"}
                else "owned_elsewhere"
                if known
                else "adapter_pending",
                "Status proxy only; no serial probe or reset",
            ),
            details={
                **details,
                "configured_serial": configured_serial,
                "probe_sent": False,
                "serial_opened": False,
            },
            last_seen=timestamp if known else None,
            capabilities={"status_proxy": True, "probe": False, "control": False},
            source="Existing Robot Body",
        )

    def _permission_record(
        self, category: str, error: str
    ) -> DeviceRecord:
        return DeviceRecord(
            device_id="%s:permission" % category,
            name="%s metadata" % category.replace("_", " ").title(),
            category=category,
            present=False,
            available=False,
            ownership="unknown",
            health=DeviceHealth("permission_denied", "Metadata is not readable"),
            error=error,
            capabilities={"control": False},
            source="system metadata",
        )

    @staticmethod
    def _categories(values: List[Mapping[str, Any]]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for item in values:
            category = str(item.get("category", "unknown"))
            result[category] = result.get(category, 0) + 1
        return dict(sorted(result.items()))

    @staticmethod
    def _number(value: str) -> Any:
        try:
            return float(value.strip())
        except ValueError:
            return None
