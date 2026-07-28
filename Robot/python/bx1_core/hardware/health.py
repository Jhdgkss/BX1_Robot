from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


def observer_diagnostics(
    inventory: Iterable[Mapping[str, Any]],
    robot_body: Mapping[str, Any],
) -> Dict[str, Any]:
    devices = list(inventory)

    def present(category: str) -> bool:
        return any(
            item.get("category") == category and bool(item.get("present"))
            for item in devices
        )

    mic = robot_body.get("microphone", {})
    speaker = robot_body.get("speaker", {})
    checks = [
        _check(
            "Robot Body API reachable",
            bool(robot_body.get("connected")),
            required=True,
            detail=str(robot_body.get("error", "")),
        ),
        _check("Microphone configured", bool(_get(mic, "configured_device"))),
        _check("Microphone device present", present("microphone")),
        _check("Speaker configured", bool(_get(speaker, "configured_device"))),
        _check("Speaker device present", present("speaker")),
        _check("Camera present", present("camera")),
        _check("Serial candidate present", present("serial")),
        _check("MCU state known", _known(robot_body.get("mcu"))),
        _check("IMU state known", _known(robot_body.get("imu"))),
        _check("Touchscreen detected", present("touchscreen")),
        _check("Display detected", present("display")),
    ]
    required_failures = [
        check["name"]
        for check in checks
        if check["required"] and not check["passed"]
    ]
    return {
        "checks": checks,
        "required_failures": required_failures,
        "healthy": not required_failures,
        "optional_absence_is_fault": False,
    }


def _check(
    name: str,
    passed: bool,
    *,
    required: bool = False,
    detail: str = "",
) -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "required": bool(required),
        "state": "online" if passed else "unavailable",
        "detail": detail,
    }


def _get(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else None


def _known(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return str(value.get("state", "unknown")).lower() not in {
        "",
        "unknown",
        "unavailable",
    }
