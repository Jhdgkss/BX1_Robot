from __future__ import annotations

from typing import Any, Mapping

from .device import DeviceHealth, DeviceRecord


class ImuAdapter:
    name = "imu"

    def discover(
        self, robot_body: Mapping[str, Any], timestamp: float
    ) -> DeviceRecord:
        value = robot_body.get("imu")
        details = dict(value) if isinstance(value, Mapping) else {}
        known = bool(details and str(details.get("state", "unknown")) != "unknown")
        state = str(
            details.get(
                "state",
                details.get("status", "unknown"),
            )
        ).lower()
        online = state in {"online", "ready", "healthy", "ok", "fresh"}
        return DeviceRecord(
            device_id="imu:robot-body",
            name=str(details.get("driver", details.get("type", "Robot IMU"))),
            category="imu",
            present=known,
            available=online,
            ownership="bx1-web.service" if robot_body.get("connected") else "unknown",
            health=DeviceHealth(
                "online" if online else "offline" if known else "adapter_pending",
                "Status is proxied; I2C and SPI are not accessed",
            ),
            details={
                **details,
                "driver": details.get("driver", details.get("type", "unknown")),
                "direct_bus_access": False,
            },
            last_seen=timestamp if known else None,
            capabilities={"telemetry_proxy": True, "direct_access": False},
            source="Existing Robot Body",
        )
