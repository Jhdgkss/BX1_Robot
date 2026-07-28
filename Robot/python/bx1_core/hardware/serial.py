from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Mapping

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment


class SerialAdapter:
    name = "serial"

    def __init__(self, environment: HardwareEnvironment) -> None:
        self.environment = environment

    def discover(self, robot_body: Mapping[str, Any]) -> List[DeviceRecord]:
        timestamp = self.environment.clock()
        nodes: List[Path] = []
        sys_names = set()
        errors = []
        for pattern in ("ttyACM*", "ttyUSB*"):
            found, error = self.environment.glob(
                self.environment.dev_root, pattern
            )
            nodes.extend(found)
            if error:
                errors.append(error)
            found_sys, sys_error = self.environment.glob(
                self.environment.sys_root / "class" / "tty", pattern
            )
            sys_names.update(item.name for item in found_sys)
            if sys_error:
                errors.append(sys_error)
        nodes.extend(self.environment.dev_root / name for name in sys_names)
        configured = self._configured_port(robot_body)
        records = []
        for node in sorted(set(nodes)):
            owners = self.environment.owners(node)
            visible, _ = self.environment.exists(node)
            permitted = self._readable(node)
            state = (
                "owned_elsewhere"
                if owners
                else "permission_denied"
                if visible and not permitted
                else "unavailable"
                if not visible
                else "detected"
            )
            records.append(
                DeviceRecord(
                    device_id="serial:%s" % node.name,
                    name=node.name,
                    category="serial",
                    present=True,
                    available=visible and permitted and not owners,
                    ownership=(
                        self._owner(owners) if owners else "unclaimed"
                    ),
                    health=DeviceHealth(
                        state,
                        (
                            "Device is owned; no probe sent"
                            if owners
                            else "Permission denied"
                            if visible and not permitted
                            else "Detected in sysfs; device node is hidden"
                            if not visible
                            else "Serial candidate detected; no probe sent"
                        ),
                    ),
                    details={
                        "device_path": str(node),
                        "device_node_visible": visible,
                        "configured": configured in {str(node), node.name},
                        "vendor": self._attribute(node.name, "idVendor"),
                        "product": self._attribute(node.name, "idProduct"),
                        "owners": owners,
                        "configured_role": (
                            "mcu" if configured in {str(node), node.name} else "candidate"
                        ),
                    },
                    last_seen=timestamp,
                    error=(
                        "permission_denied"
                        if visible and not permitted
                        else "device_node_not_visible"
                        if not visible
                        else ""
                    ),
                    capabilities={
                        "metadata": True,
                        "probe": False,
                        "write": False,
                        "reset": False,
                    },
                    source="device filesystem + Existing Robot Body",
                )
            )
        if configured and not records:
            records.append(
                DeviceRecord(
                    device_id="serial:configured",
                    name=configured,
                    category="serial",
                    present=False,
                    available=False,
                    ownership=(
                        "bx1-web.service"
                        if robot_body.get("connected")
                        else "unknown"
                    ),
                    health=DeviceHealth(
                        "unavailable",
                        "Configured MCU port is not present in the observer namespace",
                    ),
                    details={
                        "device_path": configured,
                        "configured": True,
                        "configured_role": "mcu",
                    },
                    last_seen=timestamp if robot_body.get("connected") else None,
                    error=errors[0] if errors else "device_not_detected",
                    capabilities={"probe": False, "write": False, "reset": False},
                    source="Existing Robot Body",
                )
            )
        return records

    def _attribute(self, name: str, attribute: str) -> str:
        candidates = [
            self.environment.sys_root
            / "class"
            / "tty"
            / name
            / "device"
            / ".."
            / attribute,
            self.environment.sys_root
            / "class"
            / "tty"
            / name
            / "device"
            / attribute,
        ]
        for path in candidates:
            value, _ = self.environment.read_text(path)
            if value.strip():
                return value.strip()
        return "unavailable"

    @staticmethod
    def _readable(path: Path) -> bool:
        try:
            return path.exists() and os.access(path, os.R_OK | os.W_OK)
        except PermissionError:
            return False
        except OSError:
            return False

    @staticmethod
    def _owner(owners: List[Mapping[str, Any]]) -> str:
        services = [str(item.get("service")) for item in owners if item.get("service")]
        return services[0] if services else "owned_elsewhere"

    @staticmethod
    def _configured_port(robot_body: Mapping[str, Any]) -> str:
        hardware = robot_body.get("hardware")
        if not isinstance(hardware, Mapping):
            return ""
        control = hardware.get("hardware_control")
        if isinstance(control, Mapping):
            return str(
                control.get(
                    "serial_port", control.get("mcu_serial_port", "")
                )
            )
        return ""
