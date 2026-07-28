"""Observer-only telemetry plugins discovered by BX1 OS Core."""

from .base import CorePlugin, PluginContext
from .registry import PluginRegistry

__all__ = ["CorePlugin", "PluginContext", "PluginRegistry"]
