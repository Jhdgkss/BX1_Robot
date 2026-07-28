from __future__ import annotations

import copy
import re
from typing import Any, Dict, Mapping, Optional


DEFAULT_REQUIRED_SERVICES = [
    "events",
    "capabilities",
    "logging",
    "scheduler",
    "led",
    "drive",
    "range",
    "battery",
    "power",
    "diagnostics",
    "communication",
]

DEFAULT_CORE_CONFIGURATION: Dict[str, Any] = {
    "service_registry": {
        "allow_replace": False,
        "auto_start": True,
    },
    "scheduler": {
        "enabled": True,
        "cooperative": True,
        "max_callbacks_per_tick": 100,
        "heartbeat_interval_s": 1.0,
    },
    "logging": {
        "enabled": True,
        "level": "INFO",
        "buffer_size": 1000,
        "file_logging_enabled": False,
        "file_path": "",
    },
    "diagnostics": {
        "enabled": True,
        "include_service_diagnostics": True,
        "include_configuration": False,
        "history_limit": 20,
        "required_services": list(DEFAULT_REQUIRED_SERVICES),
    },
    "health_monitor": {
        "enabled": True,
        "interval_s": 1.0,
        "publish_initial": False,
        "required_services": list(DEFAULT_REQUIRED_SERVICES),
    },
    "communication": {
        "enabled": True,
        "transport": "in_memory",
        "protocol_version": "1.0.0",
        "heartbeat_interval_s": 5.0,
        "timeout_s": 15.0,
        "state_sync_interval_s": 1.0,
        "maximum_message_size": 65536,
        "maximum_clients": 32,
        "maximum_queued_messages": 1000,
    },
    "runtime_integration": {
        "enabled": True,
        "milestone": "BX1 OS Alpha",
        "fail_safe": True,
        "compatibility_mode": True,
        "legacy_hardware_service": "runtime_hardware",
    },
}


def load_core_configuration(
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    source: Mapping[str, Any] = config or {}
    if isinstance(source.get("core_services"), Mapping):
        source = source["core_services"]  # type: ignore[index]
    result = copy.deepcopy(DEFAULT_CORE_CONFIGURATION)
    for section in DEFAULT_CORE_CONFIGURATION:
        incoming = source.get(section)
        if isinstance(incoming, Mapping):
            result[section] = _deep_merge(result[section], incoming)
    _validate(result)
    return result


def _deep_merge(base: Mapping[str, Any], incoming: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in incoming.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _validate(config: Dict[str, Any]) -> None:
    scheduler = config["scheduler"]
    if not bool(scheduler["cooperative"]):
        raise ValueError("Phase 3 SchedulerService must remain cooperative")
    if int(scheduler["max_callbacks_per_tick"]) < 1:
        raise ValueError("max_callbacks_per_tick must be positive")
    if float(scheduler["heartbeat_interval_s"]) <= 0.0:
        raise ValueError("heartbeat_interval_s must be positive")

    logging = config["logging"]
    if bool(logging["file_logging_enabled"]):
        raise ValueError("Phase 3 file logging is not enabled")
    if int(logging["buffer_size"]) < 1:
        raise ValueError("logging buffer_size must be positive")

    if int(config["diagnostics"]["history_limit"]) < 1:
        raise ValueError("diagnostics history_limit must be positive")
    if float(config["health_monitor"]["interval_s"]) <= 0.0:
        raise ValueError("health monitor interval_s must be positive")

    communication = config["communication"]
    if str(communication["transport"]).lower() != "in_memory":
        raise ValueError("Phase 4 communication transport must remain in_memory")
    if re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", str(communication["protocol_version"])) is None:
        raise ValueError("communication protocol_version must use MAJOR.MINOR.PATCH")
    heartbeat = float(communication["heartbeat_interval_s"])
    timeout = float(communication["timeout_s"])
    if heartbeat <= 0.0 or timeout <= heartbeat:
        raise ValueError("communication timeout must be greater than heartbeat interval")
    if float(communication["state_sync_interval_s"]) <= 0.0:
        raise ValueError("state_sync_interval_s must be positive")
    if int(communication["maximum_message_size"]) < 256:
        raise ValueError("maximum_message_size must be at least 256")
    if int(communication["maximum_clients"]) < 1:
        raise ValueError("maximum_clients must be positive")
    if int(communication["maximum_queued_messages"]) < 1:
        raise ValueError("maximum_queued_messages must be positive")

    runtime = config["runtime_integration"]
    if not bool(runtime["fail_safe"]):
        raise ValueError("BX1 OS Alpha runtime bootstrap must fail safely")
    if not bool(runtime["compatibility_mode"]):
        raise ValueError("BX1 OS Alpha must preserve runtime compatibility")
    if str(runtime["legacy_hardware_service"]).strip().lower() != "runtime_hardware":
        raise ValueError("legacy_hardware_service must remain runtime_hardware")
