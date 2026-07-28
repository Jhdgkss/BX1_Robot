from __future__ import annotations

from typing import Any, Mapping

from .device import DeviceHealth, DeviceRecord


class MotorAdapter:
    name = "motors"

    def discover(
        self, robot_body: Mapping[str, Any], timestamp: float
    ) -> DeviceRecord:
        hardware = robot_body.get("hardware")
        hardware = dict(hardware) if isinstance(hardware, Mapping) else {}
        control = hardware.get("hardware_control", {})
        control = dict(control) if isinstance(control, Mapping) else {}
        configured = bool(
            control.get("motor_armed")
            or control.get("rs485_enabled")
            or control.get("drive_enabled")
        )
        return DeviceRecord(
            device_id="motors:robot-body",
            name="Robot drive motors",
            category="motors",
            present=configured,
            available=False,
            ownership=(
                "bx1-web.service"
                if robot_body.get("connected")
                else "unknown"
            ),
            health=DeviceHealth(
                "owned_elsewhere" if configured else "adapter_pending",
                "Configuration only; RS485 is never opened by BX1 OS",
            ),
            details={
                "configured": configured,
                "connected": control.get("connected"),
                "device_or_bus": control.get(
                    "serial_port", "Robot Body drive bus"
                ),
                "faults": [],
                "adapter_state": "read_only_proxy",
            },
            last_seen=timestamp if robot_body.get("connected") else None,
            capabilities={"status_proxy": True, "rs485": False, "control": False},
            source="Existing Robot Body configuration",
        )
