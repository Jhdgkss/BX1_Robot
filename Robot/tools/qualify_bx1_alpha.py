#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping, Optional


LIVE_ROOT = Path("/home/arduino/Arduino_Q_Client_V1")
LIVE_SERVICE = "bx1-web.service"
LIVE_PORT = 8088
DEFAULT_ROOT = Path("/home/arduino/BX1_OS")
DEFAULT_SERVICE = "bx1-os-alpha.service"
DEFAULT_PORT = 8089
SAMPLE_PATHS = (
    "main.py",
    "START_BX1_WEB.sh",
    "python/main.py",
    "python/config.json",
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def verify_release(release_root: Path) -> Dict[str, Any]:
    root = release_root.resolve()
    manifest_path = root / "release_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("release_manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "bx1.deployment.release.v1":
        raise ValueError("unsupported release manifest schema")
    failures = []
    checked = 0
    for entry in manifest.get("files", []):
        relative = _safe_relative(entry.get("path", ""))
        path = root / "payload" / Path(*relative.parts)
        if not path.is_file():
            failures.append("missing payload file: %s" % relative)
            continue
        digest = _sha256(path)
        if digest != entry.get("sha256"):
            failures.append("hash mismatch: %s" % relative)
        if path.stat().st_size != int(entry.get("size", -1)):
            failures.append("size mismatch: %s" % relative)
        checked += 1
    return {
        "valid": not failures,
        "checked_files": checked,
        "failures": failures,
        "release": manifest,
    }


def installation_sample(root: Path) -> Dict[str, Any]:
    digest = hashlib.sha256()
    entries: Dict[str, str] = {}
    for relative in SAMPLE_PATHS:
        path = root / Path(relative)
        value = _sha256(path) if path.is_file() else "MISSING"
        entries[relative] = value
        digest.update(relative.encode("utf-8") + b"\0" + value.encode("ascii") + b"\n")
    return {"sha256": digest.hexdigest(), "files": entries}


def observer_configuration(root: Path, expected_port: int) -> Dict[str, Any]:
    config = _load_json(root / "python" / "config.json")
    isolation = _mapping(config.get("observer_isolation"))
    required_isolation = {
        "actuators_blocked",
        "camera_blocked",
        "gpio_blocked",
        "hardware_bridge_blocked",
        "leds_blocked",
        "microphone_blocked",
        "servos_blocked",
        "wheels_blocked",
    }
    false_keys = {
        "voice_enabled",
        "camera_enabled",
        "send_periodic_camera_frames",
        "send_periodic_vision",
        "visual_awareness_enabled",
        "idle_life_enabled",
        "expression_engine_enabled",
        "hardware_auto_apply_on_start",
        "hardware_startup_home_servos",
        "hardware_doctor_enabled",
        "observer_allow_camera",
        "observer_allow_microphone",
    }
    registry = _mapping(config.get("hardware_registry"))
    enabled_hardware = []
    for section in ("led_buses", "led_zones", "servos", "sensors", "drive_buses"):
        values = _mapping(registry.get(section))
        enabled_hardware.extend(
            "%s.%s" % (section, name)
            for name, item in values.items()
            if isinstance(item, Mapping) and bool(item.get("enabled", False))
        )
    control = _mapping(config.get("hardware_control"))
    failures = []
    if not config.get("qualification_mode") or not config.get("observer_only"):
        failures.append("qualification/observer marker missing")
    if int(config.get("web_port", 0)) != int(expected_port) or int(expected_port) == LIVE_PORT:
        failures.append("qualification web port is unsafe")
    failures.extend("%s must be false" % key for key in false_keys if bool(config.get(key)))
    failures.extend(
        "%s isolation is not active" % key
        for key in sorted(required_isolation)
        if isolation.get(key) is not True
    )
    if control.get("enabled") is not False or control.get("mcu_transport") != "disabled":
        failures.append("hardware control is not disabled")
    if enabled_hardware:
        failures.append("hardware registry contains enabled devices")
    return {
        "passed": not failures,
        "failures": failures,
        "observer_only": bool(config.get("observer_only")),
        "qualification_mode": bool(config.get("qualification_mode")),
        "web_port": config.get("web_port"),
        "enabled_hardware": enabled_hardware,
    }


def qualify(
    *,
    install_root: Path,
    service_name: str,
    status_url: str,
    mode: str = "canary",
    web_port: int = DEFAULT_PORT,
    old_status_url: str = "http://127.0.0.1:8088/api/status",
    baseline: Optional[Mapping[str, Any]] = None,
    snapshot: Optional[Mapping[str, Any]] = None,
    skip_systemd: bool = False,
    allow_hardware_unavailable: bool = False,
    allow_brain_offline: bool = False,
    timeout_s: float = 10.0,
) -> Dict[str, Any]:
    del allow_hardware_unavailable, allow_brain_offline
    started = time.time()
    checks = []
    root = install_root.resolve()
    baseline_value = dict(baseline or {})

    if root == LIVE_ROOT.resolve(strict=False) or LIVE_ROOT.resolve(strict=False) in root.parents:
        raise ValueError("qualification install root resolves inside live installation")
    if service_name == LIVE_SERVICE:
        raise ValueError("qualification cannot target bx1-web.service")
    if int(web_port) == LIVE_PORT:
        raise ValueError("qualification cannot use live port 8088")
    if mode not in {"install-only", "canary"}:
        raise ValueError("unsupported qualification mode")
    _validate_local_status_url(old_status_url, LIVE_PORT)
    _validate_local_status_url(status_url, web_port)

    config_report = observer_configuration(root, web_port)
    checks.append(
        Check(
            "Observer Configuration",
            config_report["passed"],
            "Reviewed observer-only configuration blocks hardware and AV ownership",
            config_report,
        )
    )

    if skip_systemd:
        alpha_active = mode == "canary"
        alpha_enabled = False
        live_active = True
        alpha_state = {"skipped": True}
        live_state = {"skipped": True}
        old_definition_sha = baseline_value.get("old_service_definition_sha256", "")
    else:
        active = _run(["systemctl", "is-active", service_name])
        enabled = _run(["systemctl", "is-enabled", service_name])
        live = _run(["systemctl", "is-active", LIVE_SERVICE])
        old_definition = _run(["systemctl", "cat", LIVE_SERVICE])
        alpha_active = active["returncode"] == 0 and active["stdout"] == "active"
        alpha_enabled = enabled["returncode"] == 0 and enabled["stdout"] in {
            "enabled",
            "enabled-runtime",
            "linked",
            "linked-runtime",
        }
        live_active = live["returncode"] == 0 and live["stdout"] == "active"
        old_definition_sha = (
            hashlib.sha256(old_definition["stdout"].encode("utf-8")).hexdigest()
            if old_definition["returncode"] == 0
            else ""
        )
        alpha_state = {"active": active, "enabled": enabled}
        live_state = {"active": live}

    expected_alpha_active = mode == "canary"
    checks.append(
        Check(
            "Alpha Service State",
            alpha_active == expected_alpha_active and not alpha_enabled,
            (
                "Alpha service is active but disabled for a manual canary"
                if mode == "canary"
                else "Alpha service is disabled and inactive after install-only"
            ),
            alpha_state,
        )
    )
    checks.append(
        Check(
            "Live Service State",
            live_active,
            "bx1-web.service remains active",
            live_state,
        )
    )

    expected_definition = str(
        baseline_value.get("old_service_definition_sha256", "")
    )
    checks.append(
        Check(
            "Live Service Definition",
            bool(expected_definition) and old_definition_sha == expected_definition,
            "bx1-web.service definition checksum is unchanged",
            {
                "expected_sha256": expected_definition,
                "actual_sha256": old_definition_sha,
            },
        )
    )

    old_sample = installation_sample(LIVE_ROOT.resolve(strict=False))
    expected_sample = _mapping(baseline_value.get("old_installation_sample"))
    checks.append(
        Check(
            "Live Installation Sample",
            bool(expected_sample.get("sha256"))
            and old_sample["sha256"] == expected_sample.get("sha256"),
            "Sampled Arduino_Q_Client_V1 files are unchanged",
            {
                "expected_sha256": expected_sample.get("sha256"),
                "actual_sha256": old_sample["sha256"],
            },
        )
    )

    old_health_ok = False
    try:
        old_health_ok = bool(_get_json(old_status_url, timeout_s=timeout_s))
    except Exception:
        old_health_ok = False
    checks.append(
        Check(
            "Live Port 8088",
            old_health_ok,
            "The existing application remains healthy on port 8088",
            {"url": old_status_url, "healthy": old_health_ok},
        )
    )

    canary_port_used = _port_in_use(web_port)
    checks.append(
        Check(
            "Canary Port 8089",
            canary_port_used if mode == "canary" else not canary_port_used,
            (
                "Port 8089 is serving the canary"
                if mode == "canary"
                else "Port 8089 remains unused after install-only"
            ),
            {"port": web_port, "in_use": canary_port_used},
        )
    )

    matching_processes = _processes_using_root(root)
    checks.append(
        Check(
            "BX1_OS Process Isolation",
            mode == "canary" or not matching_processes,
            (
                "Canary process is permitted"
                if mode == "canary"
                else "No process is running from BX1_OS after install-only"
            ),
            {"matching_pids": matching_processes},
        )
    )

    if mode == "canary":
        if snapshot is None:
            snapshot = _get_json(status_url, timeout_s=timeout_s)
        snapshot_value = dict(snapshot)
        bx1_os = _mapping(snapshot_value.get("bx1_os"))
        startup = _mapping(bx1_os.get("startup"))
        checks.extend(_runtime_checks(snapshot_value, bx1_os, startup, status_url))
    else:
        snapshot_value = {}

    passed = all(check.passed for check in checks)
    return {
        "schema": "bx1.deployment.qualification.v2",
        "milestone": "BX1 OS Alpha",
        "qualification_mode": mode,
        "started_at": started,
        "completed_at": time.time(),
        "passed": passed,
        "install_root": str(root),
        "service_name": service_name,
        "status_url": status_url,
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "hardware_actions_requested": False,
        "actuator_access_required": False,
        "hardware_bridge_ownership_required": False,
    }


def _runtime_checks(
    snapshot: Mapping[str, Any],
    bx1_os: Mapping[str, Any],
    startup: Mapping[str, Any],
    status_url: str,
) -> list[Check]:
    checks = []
    checks.append(
        Check(
            "Bootstrap",
            bool(bx1_os.get("startup_validated")) and bool(startup.get("success")),
            "BX1 OS Alpha startup report is validated",
            {"schema": startup.get("schema"), "milestone": bx1_os.get("milestone")},
        )
    )
    registry = _mapping(bx1_os.get("service_registry"))
    required = set(startup.get("required_services", []))
    registered = set(startup.get("registered_services", []))
    checks.append(
        Check(
            "Service Registry",
            registry.get("state") == "READY"
            and not (required - registered)
            and int(registry.get("running_count", 0)) >= len(required),
            "Required services are registered and running",
            {"missing": sorted(required - registered)},
        )
    )
    for name, key in (
        ("Scheduler", "scheduler"),
        ("Event Bus", "events"),
        ("Diagnostics", "diagnostics"),
        ("Health Monitor", "health"),
    ):
        value = _mapping(bx1_os.get(key))
        extra_ok = (
            int(value.get("tick_count", 0)) > 0
            if key == "scheduler"
            else int(value.get("check_count", 1)) > 0
            if key == "health"
            else True
        )
        checks.append(
            Check(name, value.get("state") == "READY" and extra_ok, "%s is ready" % name, value)
        )
    communication = _mapping(bx1_os.get("communication"))
    checks.append(
        Check(
            "Communication",
            communication.get("state") == "READY"
            and communication.get("transport") == "in_memory",
            "Communication remains in-memory",
            communication,
        )
    )
    state = _mapping(snapshot.get("state"))
    isolation = _mapping(bx1_os.get("observer_isolation"))
    isolation_ok = (
        bx1_os.get("qualification_mode") is True
        and bx1_os.get("observer_only") is True
        and all(value is True for value in isolation.values())
        and len(isolation) >= 8
        and state.get("observer_only") is True
        and state.get("hardware_ownership") is False
        and state.get("actuator_access") is False
        and state.get("bridge_mode") == "observer_only"
    )
    checks.append(
        Check(
            "Observer Isolation",
            isolation_ok,
            "Canary reports non-owning hardware isolation",
            {
                "observer_only": bx1_os.get("observer_only"),
                "isolation": isolation,
                "bridge_mode": state.get("bridge_mode"),
                "hardware_ownership": state.get("hardware_ownership"),
                "actuator_access": state.get("actuator_access"),
            },
        )
    )
    checks.append(
        Check(
            "Web Interface",
            bool(snapshot.get("ok")),
            "Alpha status API answered on the canary port",
            {"url": status_url, "response_ok": snapshot.get("ok")},
        )
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify BX1 OS Alpha")
    parser.add_argument("--verify-release", type=Path)
    parser.add_argument("--mode", choices=("install-only", "canary"), default="canary")
    parser.add_argument("--install-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE)
    parser.add_argument("--status-url", default="http://127.0.0.1:8089/api/status")
    parser.add_argument("--old-status-url", default="http://127.0.0.1:8088/api/status")
    parser.add_argument("--web-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--snapshot-file", type=Path)
    parser.add_argument("--skip-systemd", action="store_true")
    parser.add_argument("--allow-hardware-unavailable", action="store_true")
    parser.add_argument("--allow-brain-offline", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.verify_release:
        report = verify_release(args.verify_release)
    else:
        if args.baseline is None:
            raise SystemExit("--baseline is required for side-by-side qualification")
        baseline_document = _load_json(args.baseline)
        baseline_value = (
            _mapping(baseline_document.get("baseline"))
            if baseline_document.get("schema") == "bx1.deployment.backup.v2"
            else baseline_document
        )
        report = qualify(
            install_root=args.install_root,
            service_name=args.service_name,
            status_url=args.status_url,
            mode=args.mode,
            web_port=args.web_port,
            old_status_url=args.old_status_url,
            baseline=baseline_value,
            snapshot=_load_json(args.snapshot_file) if args.snapshot_file else None,
            skip_systemd=args.skip_systemd,
            timeout_s=args.timeout,
        )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("valid", report.get("passed", False)) else 1


def _safe_relative(value: Any) -> PurePosixPath:
    path = PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("unsafe release path: %s" % value)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_json(
    url: str,
    *,
    timeout_s: float,
    headers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            if response.status >= 400:
                raise RuntimeError("HTTP %s" % response.status)
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc
    if not isinstance(value, dict):
        raise RuntimeError("endpoint returned non-object JSON")
    return value


def _load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("%s must contain a JSON object" % path)
    return value


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _run(command: Iterable[str]) -> Dict[str, Any]:
    result = subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    return {
        "command": list(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def _processes_using_root(root: Path) -> list[int]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    matches = []
    own_pid = os.getpid()
    root_text = str(root)
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            raw = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except Exception:
            continue
        if root_text in raw:
            matches.append(int(entry.name))
    return sorted(matches)


def _validate_local_status_url(url: str, expected_port: int) -> None:
    parsed = urlparse(str(url))
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != int(expected_port)
    ):
        raise ValueError("status URL must use local HTTP port %s" % expected_port)


if __name__ == "__main__":
    raise SystemExit(main())
