from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from ..events import CoreEventBus
from ..health import HealthState, PluginHealth
from ..state import StateStore


@dataclass(frozen=True)
class PluginContext:
    state: StateStore
    events: CoreEventBus
    config: Mapping[str, Any]
    install_root: Path
    started_at: float
    clock: Callable[[], float] = time.time
    monotonic_clock: Callable[[], float] = time.monotonic
    metadata: Mapping[str, Any] = field(default_factory=dict)


class CorePlugin:
    """Small lifecycle contract implemented by Core telemetry plugins."""

    name = "unnamed"
    version = "1.0"

    def __init__(self) -> None:
        self.context: Optional[PluginContext] = None
        self._health = PluginHealth(
            HealthState.WARNING,
            time.time(),
            {"reason": "Plugin is not registered"},
        )

    def register(self, context: PluginContext) -> None:
        self.context = context
        self._set_health(HealthState.HEALTHY, {"reason": "Plugin registered"})

    def update(self) -> None:
        raise NotImplementedError

    def health(self) -> PluginHealth:
        return self._health

    def shutdown(self) -> None:
        return None

    def _set_health(
        self,
        state: HealthState,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        clock = self.context.clock if self.context is not None else time.time
        self._health = PluginHealth(state, clock(), dict(details or {}))

    def _require_context(self) -> PluginContext:
        if self.context is None:
            raise RuntimeError("plugin is not registered: %s" % self.name)
        return self.context
