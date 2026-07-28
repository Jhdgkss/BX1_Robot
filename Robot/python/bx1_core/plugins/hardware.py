from __future__ import annotations

from ..health import HealthState
from .base import CorePlugin


class HardwarePlugin(CorePlugin):
    """Ownership-free namespace placeholder; it never opens a device."""

    name = "hardware"
    version = "1.0"

    def update(self) -> None:
        context = self._require_context()
        context.state.set_many(
            {
                "hardware.camera": "blocked",
                "hardware.microphone": "blocked",
                "hardware.speaker": "unavailable",
                "hardware.touchscreen": "unavailable",
                "hardware.imu": "unavailable",
                "hardware.servos": "blocked",
                "hardware.motors": "blocked",
                "hardware.observer_only": True,
                "hardware.ownership": False,
                "hardware.actions_requested": False,
            },
            source="plugin.hardware",
        )
        self._set_health(
            HealthState.HEALTHY,
            {
                "reason": "Observer isolation active",
                "hardware_access_attempted": False,
                "ownership": False,
            },
        )


PLUGIN_CLASS = HardwarePlugin
