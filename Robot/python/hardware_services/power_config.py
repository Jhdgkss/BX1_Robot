from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Optional


DEFAULT_POWER_CONFIGURATION: Dict[str, Any] = {
    "power_service": {
        "enabled": True,
        "mode": "digital_twin",
        "system_power_budget_w": 120.0,
        "reserved_power_w": 10.0,
        "movement_min_available_w": 30.0,
        "charging_enabled": True,
        "shutdown_on_battery_fault": True,
        "rails": {
            "logic_5v": {"required": True, "healthy": True},
            "compute_12v": {"required": True, "healthy": True},
            "motor_bus": {"required": False, "healthy": True},
        },
    },
    "battery_service": {
        "enabled": True,
        "fitted": True,
        "cell_count": 3,
        "nominal_capacity_wh": 180.0,
        "low_soc_pct": 20.0,
        "critical_soc_pct": 10.0,
        "shutdown_soc_pct": 5.0,
        "full_soc_pct": 98.0,
        "cell_imbalance_warning_v": 0.10,
        "cell_imbalance_fault_v": 0.25,
        "minimum_temperature_c": 0.0,
        "maximum_temperature_c": 60.0,
    },
    "battery_monitor": {
        "enabled": True,
        "backend": "mock",
        "cell_count": 3,
        "cell_voltages_v": [4.0, 4.0, 4.0],
        "pack_current_a": 1.0,
        "temperature_c": 25.0,
        "state_of_charge_pct": 75.0,
        "charging": False,
        "runtime_override_s": None,
    },
    "bms": {
        "enabled": True,
        "backend": "mock",
        "output_enabled": True,
        "temperature_c": 25.0,
        "cell_voltages_v": [4.0, 4.0, 4.0],
        "balancing": False,
    },
    "docking": {
        "enabled": False,
        "backend": "interface_only",
    },
    "capability_registry": {
        "simulated": True,
        "capabilities": {
            "imu": True,
            "range_sensor": False,
            "battery_monitor": True,
            "smart_bms": False,
            "wheel_encoders": False,
            "camera": True,
            "microphone": True,
            "speaker": True,
            "power_monitor": True,
            "charging_dock": False,
        },
    },
}


def load_power_configuration(config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Load Phase 2 sections from a full Robot config or service-only mapping."""
    source: Mapping[str, Any] = config or {}
    if isinstance(source.get("hardware_services"), Mapping):
        source = source["hardware_services"]  # type: ignore[index]
    result = copy.deepcopy(DEFAULT_POWER_CONFIGURATION)
    for section in DEFAULT_POWER_CONFIGURATION:
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
    battery = config["battery_service"]
    shutdown = float(battery["shutdown_soc_pct"])
    critical = float(battery["critical_soc_pct"])
    low = float(battery["low_soc_pct"])
    full = float(battery["full_soc_pct"])
    if not 0.0 <= shutdown <= critical <= low < full <= 100.0:
        raise ValueError(
            "battery thresholds must satisfy 0 <= shutdown <= critical <= low < full <= 100"
        )
    if int(battery["cell_count"]) < 1:
        raise ValueError("battery_service cell_count must be positive")
    if float(battery["nominal_capacity_wh"]) <= 0.0:
        raise ValueError("nominal_capacity_wh must be positive")
    if float(battery["cell_imbalance_warning_v"]) < 0.0 or float(
        battery["cell_imbalance_fault_v"]
    ) < float(battery["cell_imbalance_warning_v"]):
        raise ValueError("cell imbalance limits are invalid")
    if float(battery["minimum_temperature_c"]) >= float(
        battery["maximum_temperature_c"]
    ):
        raise ValueError("battery temperature limits are invalid")

    power = config["power_service"]
    budget = float(power["system_power_budget_w"])
    reserved = float(power["reserved_power_w"])
    movement = float(power["movement_min_available_w"])
    if budget <= 0.0 or reserved < 0.0 or movement < 0.0:
        raise ValueError("power budget values are invalid")
