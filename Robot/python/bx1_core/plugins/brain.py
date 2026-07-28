from __future__ import annotations

from ..health import HealthState
from .base import CorePlugin


class BrainPlugin(CorePlugin):
    """State namespace placeholder; it never opens a Brain connection."""

    name = "brain"
    version = "1.0"

    def update(self) -> None:
        context = self._require_context()
        context.state.set_many(
            {
                "brain.connected": False,
                "brain.model": None,
                "brain.speaking": False,
                "brain.listening": False,
                "brain.thinking": False,
            },
            source="plugin.brain",
        )
        self._set_health(
            HealthState.HEALTHY,
            {
                "reason": "Observer placeholder ready",
                "connection_attempted": False,
            },
        )


PLUGIN_CLASS = BrainPlugin
