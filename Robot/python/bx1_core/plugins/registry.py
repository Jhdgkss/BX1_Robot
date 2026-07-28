from __future__ import annotations

import copy
import importlib
import pkgutil
import threading
from typing import Any, Dict, Iterable, List, Optional

from ..events import CoreEventType
from ..health import HealthState, PluginHealth
from .base import CorePlugin, PluginContext


class PluginRegistry:
    """Discovers, registers and supervises isolated Core plugins."""

    def __init__(self, context: PluginContext) -> None:
        self.context = context
        self._plugins: Dict[str, CorePlugin] = {}
        self._errors: Dict[str, str] = {}
        self._lock = threading.RLock()

    def discover(self, package_name: str = "bx1_core.plugins") -> List[str]:
        package = importlib.import_module(package_name)
        discovered: List[CorePlugin] = []
        for module_info in sorted(
            pkgutil.iter_modules(package.__path__, package.__name__ + "."),
            key=lambda item: item.name,
        ):
            module = importlib.import_module(module_info.name)
            plugin_class = getattr(module, "PLUGIN_CLASS", None)
            if plugin_class is None:
                continue
            plugin = plugin_class()
            if not isinstance(plugin, CorePlugin):
                raise TypeError(
                    "PLUGIN_CLASS must derive from CorePlugin: %s"
                    % module_info.name
                )
            discovered.append(plugin)
        for plugin in discovered:
            self.register(plugin)
        return self.names()

    def register(self, plugin: CorePlugin) -> None:
        name = self._normalise(plugin.name)
        with self._lock:
            if name in self._plugins:
                raise ValueError("plugin is already registered: %s" % name)
            plugin.register(self.context)
            self._plugins[name] = plugin
        self.context.events.publish(
            CoreEventType.PLUGIN_LOADED,
            {"name": name, "version": str(plugin.version)},
            source="core.plugins",
        )

    def update(self, names: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        selected = self.names() if names is None else [
            self._normalise(name) for name in names
        ]
        updated: List[str] = []
        faults: Dict[str, str] = {}
        for name in selected:
            with self._lock:
                plugin = self._plugins.get(name)
            if plugin is None:
                faults[name] = "plugin is not registered"
                continue
            try:
                plugin.update()
                with self._lock:
                    self._errors.pop(name, None)
                updated.append(name)
                self.context.events.publish(
                    CoreEventType.PLUGIN_UPDATED,
                    {"name": name, "version": str(plugin.version)},
                    source="core.plugins",
                )
            except Exception as exc:
                message = str(exc)
                with self._lock:
                    self._errors[name] = message
                faults[name] = message
                self.context.events.publish(
                    CoreEventType.PLUGIN_FAULT,
                    {"name": name, "error": message},
                    source="core.plugins",
                )
        return {"updated": updated, "faults": faults}

    def health(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            plugins = list(self._plugins.items())
            errors = dict(self._errors)
        result: Dict[str, Dict[str, Any]] = {}
        for name, plugin in plugins:
            if name in errors:
                health = PluginHealth(
                    HealthState.FAULT,
                    self.context.clock(),
                    {"reason": "Plugin update failed", "error": errors[name]},
                )
            else:
                health = plugin.health()
            result[name] = health.as_dict()
        return result

    def snapshot(self) -> Dict[str, Any]:
        health = self.health()
        with self._lock:
            plugins = list(self._plugins.items())
        return {
            "schema": "bx1.core.plugins.v1",
            "plugins": [
                {
                    "name": name,
                    "version": str(plugin.version),
                    "health": copy.deepcopy(health[name]),
                }
                for name, plugin in plugins
            ],
        }

    def shutdown(self) -> Dict[str, str]:
        errors: Dict[str, str] = {}
        with self._lock:
            plugins = list(reversed(list(self._plugins.items())))
        for name, plugin in plugins:
            try:
                plugin.shutdown()
            except Exception as exc:
                errors[name] = str(exc)
        return errors

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._plugins)

    @staticmethod
    def _normalise(name: Any) -> str:
        value = str(name).strip().lower()
        if not value:
            raise ValueError("plugin name must not be empty")
        return value
