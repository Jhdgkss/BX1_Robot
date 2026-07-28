from __future__ import annotations

import copy
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple


DEVICE_STATES = {
    "online",
    "offline",
    "detected",
    "busy",
    "permission_denied",
    "owned_elsewhere",
    "unsupported",
    "adapter_pending",
    "unavailable",
    "unknown",
}


@dataclass(frozen=True)
class DeviceHealth:
    state: str = "unknown"
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        state = self.state if self.state in DEVICE_STATES else "unknown"
        return {
            "state": state,
            "healthy": state in {"online", "detected"},
            "warning": state in {
                "busy",
                "owned_elsewhere",
                "unsupported",
                "adapter_pending",
                "unavailable",
            },
            "fault": state in {"offline", "permission_denied"},
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    name: str
    category: str
    present: bool
    available: bool
    ownership: str
    health: DeviceHealth
    details: Mapping[str, Any] = field(default_factory=dict)
    last_seen: Optional[float] = None
    error: str = ""
    telemetry: Mapping[str, Any] = field(default_factory=dict)
    capabilities: Mapping[str, Any] = field(default_factory=dict)
    source: str = "system_metadata"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "category": self.category,
            "present": self.present,
            "available": self.available,
            "ownership": self.ownership,
            "health": self.health.as_dict(),
            "details": copy.deepcopy(dict(self.details)),
            "last_seen": self.last_seen,
            "error": self.error,
            "telemetry": copy.deepcopy(dict(self.telemetry)),
            "capabilities": copy.deepcopy(dict(self.capabilities)),
            "source": self.source,
            "control": "blocked",
        }


def observation(
    value: Any,
    *,
    timestamp: float,
    source: str,
    quality: str,
    stale: bool = False,
    error: str = "",
) -> Dict[str, Any]:
    return {
        "value": copy.deepcopy(value),
        "timestamp": float(timestamp),
        "source": str(source),
        "quality": str(quality),
        "stale": bool(stale),
        "error": str(error),
    }


class HardwareEnvironment:
    """Filesystem-only inspector. It never opens a device node."""

    def __init__(
        self,
        *,
        dev_root: Path = Path("/dev"),
        proc_root: Path = Path("/proc"),
        sys_root: Path = Path("/sys"),
        clock: Callable[[], float] = time.time,
        which: Callable[[str], Optional[str]] = shutil.which,
        text_reader: Optional[Callable[[Path], str]] = None,
    ) -> None:
        self.dev_root = Path(dev_root)
        self.proc_root = Path(proc_root)
        self.sys_root = Path(sys_root)
        self.clock = clock
        self.which = which
        self._text_reader = text_reader

    def read_text(self, path: Path, limit: int = 256 * 1024) -> Tuple[str, str]:
        try:
            if self._text_reader is not None:
                value = self._text_reader(Path(path))
            else:
                value = Path(path).read_text(
                    encoding="utf-8", errors="replace"
                )
            return str(value)[:limit], ""
        except PermissionError:
            return "", "permission_denied"
        except OSError as exc:
            return "", str(exc)

    def glob(self, root: Path, pattern: str) -> Tuple[List[Path], str]:
        try:
            return sorted(Path(root).glob(pattern)), ""
        except PermissionError:
            return [], "permission_denied"
        except OSError as exc:
            return [], str(exc)

    def exists(self, path: Path) -> Tuple[bool, str]:
        try:
            return Path(path).exists(), ""
        except PermissionError:
            return False, "permission_denied"
        except OSError as exc:
            return False, str(exc)

    def tool(self, name: str) -> Optional[str]:
        try:
            return self.which(str(name))
        except OSError:
            return None

    def owners(self, device: Path, limit: int = 4096) -> List[Dict[str, Any]]:
        """Resolve matching /proc fd links without reading environments."""
        target = os.path.realpath(str(device))
        owners: List[Dict[str, Any]] = []
        pids, _ = self.glob(self.proc_root, "[0-9]*")
        for process_dir in pids[: max(1, int(limit))]:
            try:
                pid = int(process_dir.name)
                fd_entries = list((process_dir / "fd").iterdir())
            except (OSError, ValueError):
                continue
            matched = False
            for descriptor in fd_entries:
                try:
                    if os.path.realpath(str(descriptor.resolve())) == target:
                        matched = True
                        break
                except OSError:
                    continue
            if not matched:
                continue
            comm, _ = self.read_text(process_dir / "comm", limit=256)
            cgroup, _ = self.read_text(process_dir / "cgroup", limit=4096)
            service = (
                "bx1-web.service"
                if "bx1-web.service" in cgroup
                else "bx1-os-alpha.service"
                if "bx1-os-alpha.service" in cgroup
                else ""
            )
            owners.append(
                {
                    "pid": pid,
                    "process": comm.strip()[:128] or "unknown",
                    "service": service,
                }
            )
        return owners
