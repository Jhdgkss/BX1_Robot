from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from ..health import HealthState
from .base import CorePlugin


class SystemPlugin(CorePlugin):
    name = "system"
    version = "1.0"

    def update(self) -> None:
        context = self._require_context()
        values = {
            "system.cpu": self._cpu_percent(),
            "system.memory": self._memory_percent(),
            "system.disk": self._disk_percent(context.install_root),
            "system.temperature": self._temperature(),
            "system.uptime": self._uptime(context),
            "system.python": platform.python_version(),
            "system.os": platform.system() or "Unknown",
            "system.kernel": platform.release() or "Unknown",
            "system.architecture": platform.machine() or "Unknown",
            "system.hostname": platform.node() or "Unknown",
            "system.serial": str(
                context.config.get("robot_serial", "Pending integration")
            ),
            "robot.mode": "observer_only",
            "robot.state": "qualification",
            "robot.enabled": False,
        }
        context.state.set_many(values, source="plugin.system")
        self._set_health(
            HealthState.HEALTHY,
            {
                "reason": "Host telemetry sampled",
                "available_metrics": sorted(
                    key for key, value in values.items() if value is not None
                ),
            },
        )

    @staticmethod
    def _cpu_percent() -> Optional[float]:
        try:
            count = max(1, os.cpu_count() or 1)
            return round(min(100.0, max(0.0, os.getloadavg()[0] / count * 100)), 1)
        except (AttributeError, OSError):
            return None

    @staticmethod
    def _memory_percent() -> Optional[float]:
        try:
            rows: Dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                name, value = line.split(":", 1)
                rows[name] = int(value.strip().split()[0])
            total = rows["MemTotal"]
            available = rows.get("MemAvailable", rows.get("MemFree", 0))
            return round((total - available) / total * 100, 1)
        except (OSError, KeyError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _disk_percent(install_root: Path) -> Optional[float]:
        try:
            target = install_root if install_root.exists() else Path.cwd()
            usage = shutil.disk_usage(str(target))
            return round(usage.used / usage.total * 100, 1)
        except (OSError, ZeroDivisionError):
            return None

    @staticmethod
    def _temperature() -> Optional[float]:
        thermal_root = Path("/sys/class/thermal")
        try:
            for source in sorted(thermal_root.glob("thermal_zone*/temp")):
                value = float(source.read_text(encoding="ascii").strip())
                celsius = value / 1000.0 if value > 200 else value
                if -20 <= celsius <= 150:
                    return round(celsius, 1)
        except (OSError, ValueError):
            return None
        return None

    @staticmethod
    def _uptime(context: Any) -> int:
        try:
            return max(
                0,
                int(
                    float(
                        Path("/proc/uptime")
                        .read_text(encoding="ascii")
                        .split()[0]
                    )
                ),
            )
        except (OSError, ValueError, IndexError):
            return max(0, int(context.clock() - context.started_at))


PLUGIN_CLASS = SystemPlugin
