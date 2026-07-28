from __future__ import annotations

from typing import List

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment


class DisplayAdapter:
    name = "display"

    def __init__(self, environment: HardwareEnvironment) -> None:
        self.environment = environment

    def discover(self) -> List[DeviceRecord]:
        timestamp = self.environment.clock()
        connectors, error = self.environment.glob(
            self.environment.sys_root / "class" / "drm", "card*-*"
        )
        records = []
        for connector in connectors:
            status, _ = self.environment.read_text(connector / "status")
            if status.strip().lower() not in {"connected", "unknown"}:
                continue
            modes, _ = self.environment.read_text(connector / "modes")
            mode_list = [
                line.strip() for line in modes.splitlines() if line.strip()
            ]
            records.append(
                DeviceRecord(
                    device_id="display:%s" % connector.name,
                    name=connector.name,
                    category="display",
                    present=status.strip().lower() == "connected",
                    available=status.strip().lower() == "connected",
                    ownership="display_server",
                    health=DeviceHealth(
                        "online"
                        if status.strip().lower() == "connected"
                        else "unknown",
                        "DRM connector metadata only",
                    ),
                    details={
                        "connector": connector.name,
                        "status": status.strip().lower() or "unknown",
                        "resolution": mode_list[0] if mode_list else "unknown",
                        "supported_modes": mode_list[:50],
                        "rotation": "unavailable",
                    },
                    last_seen=timestamp,
                    capabilities={
                        "metadata": True,
                        "rotation_control": False,
                        "mode_control": False,
                    },
                    source="sysfs DRM metadata",
                )
            )
        if not records and error == "permission_denied":
            records.append(
                DeviceRecord(
                    device_id="display:permission",
                    name="Display metadata",
                    category="display",
                    present=False,
                    available=False,
                    ownership="unknown",
                    health=DeviceHealth(
                        "permission_denied", "DRM metadata is not readable"
                    ),
                    error=error,
                    capabilities={"control": False},
                    source="sysfs DRM metadata",
                )
            )
        return records
