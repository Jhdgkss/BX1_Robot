from __future__ import annotations

import re
from typing import List

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment


class InputDeviceAdapter:
    name = "input_devices"

    def __init__(self, environment: HardwareEnvironment) -> None:
        self.environment = environment

    def discover(self) -> List[DeviceRecord]:
        timestamp = self.environment.clock()
        value, error = self.environment.read_text(
            self.environment.proc_root / "bus" / "input" / "devices"
        )
        records = []
        for index, block in enumerate(re.split(r"\n\s*\n", value)):
            name_match = re.search(r'^N:\s+Name="([^"]+)"', block, re.MULTILINE)
            handlers_match = re.search(
                r"^H:\s+Handlers=(.*)$", block, re.MULTILINE
            )
            if not name_match:
                continue
            name = name_match.group(1)
            handlers = (
                handlers_match.group(1).split() if handlers_match else []
            )
            event = next(
                (handler for handler in handlers if handler.startswith("event")),
                "",
            )
            touch = "touch" in name.lower() or "touchscreen" in block.lower()
            records.append(
                DeviceRecord(
                    device_id="input:%s" % (event or index),
                    name=name,
                    category="touchscreen" if touch else "input_device",
                    present=True,
                    available=True,
                    ownership="kernel",
                    health=DeviceHealth(
                        "detected", "Input metadata reported by the kernel"
                    ),
                    details={
                        "event_path": (
                            str(self.environment.dev_root / "input" / event)
                            if event
                            else ""
                        ),
                        "handlers": handlers,
                        "touchscreen": touch,
                        "mapping": "unavailable",
                    },
                    last_seen=timestamp,
                    capabilities={"metadata": True, "events_opened": False},
                    source="procfs input metadata",
                )
            )
        if not records and error == "permission_denied":
            records.append(
                DeviceRecord(
                    device_id="input:permission",
                    name="Input device metadata",
                    category="input_device",
                    present=False,
                    available=False,
                    ownership="unknown",
                    health=DeviceHealth(
                        "permission_denied", "Input metadata is not readable"
                    ),
                    error=error,
                    capabilities={"events_opened": False},
                    source="procfs input metadata",
                )
            )
        return records
