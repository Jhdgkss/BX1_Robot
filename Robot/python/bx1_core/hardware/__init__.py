"""Read-only, non-owning hardware discovery for BX1 OS Core."""

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment, observation
from .camera import (
    CameraFrame,
    CameraProxyError,
    RobotBodyCameraClient,
)
from .inventory import ReadOnlyHardwareInventory
from .robot_body import RobotBodyClient

__all__ = [
    "DeviceHealth",
    "DeviceRecord",
    "HardwareEnvironment",
    "CameraFrame",
    "CameraProxyError",
    "ReadOnlyHardwareInventory",
    "RobotBodyClient",
    "RobotBodyCameraClient",
    "observation",
]
