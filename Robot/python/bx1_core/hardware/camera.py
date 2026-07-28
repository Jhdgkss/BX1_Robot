from __future__ import annotations

from typing import Any, List, Mapping

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment


class CameraAdapter:
    name = "camera"

    def __init__(self, environment: HardwareEnvironment) -> None:
        self.environment = environment

    def discover(self, robot_body: Mapping[str, Any]) -> List[DeviceRecord]:
        timestamp = self.environment.clock()
        dev_nodes, dev_error = self.environment.glob(
            self.environment.dev_root, "video*"
        )
        sys_nodes, sys_error = self.environment.glob(
            self.environment.sys_root / "class" / "video4linux", "video*"
        )
        names = sorted({item.name for item in (*dev_nodes, *sys_nodes)})
        records = []
        body_camera = self._mapping(robot_body.get("camera"))
        configured = str(body_camera.get("device", ""))
        owned_by_body = bool(robot_body.get("connected")) and bool(
            body_camera.get("configured")
            or configured
            or str(body_camera.get("state", "")).lower()
            in {"online", "running", "active", "busy"}
        )
        for name in names:
            node = self.environment.dev_root / name
            node_visible, _ = self.environment.exists(node)
            sys_device = (
                self.environment.sys_root
                / "class"
                / "video4linux"
                / name
            )
            friendly, _ = self.environment.read_text(sys_device / "name")
            driver = ""
            driver_path = sys_device / "device" / "driver"
            driver_exists, _ = self.environment.exists(driver_path)
            if driver_exists:
                try:
                    driver = driver_path.resolve().name
                except OSError:
                    pass
            owners = self.environment.owners(node)
            owned = bool(owners) or owned_by_body
            records.append(
                DeviceRecord(
                    device_id="camera:%s" % name,
                    name=friendly.strip() or name,
                    category="camera",
                    present=True,
                    available=node_visible and not owned,
                    ownership=(
                        self._ownership(owners)
                        if owners
                        else "bx1-web.service"
                        if owned_by_body
                        else "unclaimed"
                    ),
                    health=DeviceHealth(
                        "owned_elsewhere" if owned else "detected",
                        (
                            "Device is in use; stream was not opened"
                            if owned
                            else "Camera detected in sysfs; device node is hidden"
                            if not node_visible
                            else "Device node detected without opening it"
                        ),
                    ),
                    details={
                        "device_node": str(node),
                        "device_node_visible": node_visible,
                        "driver": driver or "unknown",
                        "usb_identity": self._usb_identity(sys_device),
                        "configured": self._configured(
                            configured, node, name
                        ),
                        "supported_formats": [],
                        "format_query": "not_run_while_observer_only",
                        "owners": owners,
                    },
                    last_seen=timestamp,
                    capabilities={
                        "metadata": True,
                        "streaming": False,
                        "control": False,
                    },
                    source="sysfs + Existing Robot Body",
                )
            )
        if not records and configured:
            records.append(
                DeviceRecord(
                    device_id="camera:configured",
                    name=configured,
                    category="camera",
                    present=False,
                    available=False,
                    ownership=(
                        "bx1-web.service"
                        if robot_body.get("connected")
                        else "unknown"
                    ),
                    health=DeviceHealth(
                        "unavailable",
                        "Configured by Existing Robot Body but not detected",
                    ),
                    details={"configured": True, "device_node": configured},
                    last_seen=timestamp if robot_body.get("connected") else None,
                    error=dev_error or sys_error or "device_not_detected",
                    capabilities={"control": False, "streaming": False},
                    source="Existing Robot Body",
                )
            )
        return records

    def _usb_identity(self, sys_device: Any) -> Mapping[str, str]:
        current = sys_device / "device"
        for _ in range(6):
            vendor, _ = self.environment.read_text(current / "idVendor")
            product, _ = self.environment.read_text(current / "idProduct")
            if vendor.strip() or product.strip():
                return {
                    "vendor": vendor.strip() or "unavailable",
                    "product": product.strip() or "unavailable",
                }
            current = current / ".."
        return {"vendor": "unavailable", "product": "unavailable"}

    @staticmethod
    def _configured(configured: str, node: Any, name: str) -> bool:
        return configured in {
            str(node),
            name,
            name.removeprefix("video"),
        }

    @staticmethod
    def _mapping(value: Any) -> dict:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _ownership(owners: List[Mapping[str, Any]]) -> str:
        services = [str(item.get("service")) for item in owners if item.get("service")]
        return services[0] if services else "owned_elsewhere"
