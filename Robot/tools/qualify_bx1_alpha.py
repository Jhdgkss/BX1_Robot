#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


LIVE_ROOT = Path("/home/arduino/Arduino_Q_Client_V1")
LIVE_SERVICE = "bx1-web.service"
LIVE_PORT = 8088
DEFAULT_ROOT = Path("/home/arduino/BX1_OS")
DEFAULT_SERVICE = "bx1-os-alpha.service"
DEFAULT_PORT = 8089
RELEASE_VERSION = "0.7.2-operator-integration"
RELEASE_TAG = "BX1_OS_v0.7.2_operator_integration"
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
    management = _mapping(config.get("management_interface"))
    if (
        management.get("enabled") is not True
        or management.get("architecture_only") is not True
        or management.get("read_only") is not True
    ):
        failures.append("management interface architecture-only profile is missing")
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
    launcher_pid: Optional[int] = None,
    launcher_path: Optional[Path] = None,
    proc_root: Path = Path("/proc"),
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

    checks.append(
        Check(
            "Alpha Installation Root",
            root.is_dir(),
            "The side-by-side BX1_OS installation exists during qualification",
            {"path": str(root), "is_directory": root.is_dir()},
        )
    )
    try:
        config_report = observer_configuration(root, web_port)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        config_report = {
            "passed": False,
            "failures": ["observer configuration unavailable: %s" % type(exc).__name__],
            "observer_only": False,
            "qualification_mode": False,
            "web_port": None,
            "enabled_hardware": [],
        }
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
        load_state = _run(
            ["systemctl", "show", service_name, "--property", "LoadState", "--value"]
        )
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
        alpha_state = {"active": active, "enabled": enabled, "load_state": load_state}
        live_state = {"active": live}

    expected_alpha_active = mode == "canary"
    alpha_loaded = (
        True
        if skip_systemd
        else alpha_state["load_state"]["returncode"] == 0
        and alpha_state["load_state"]["stdout"] == "loaded"
    )
    checks.append(
        Check(
            "Alpha Unit Installed",
            alpha_loaded,
            "The dedicated Alpha service unit is loaded",
            {"loaded": alpha_loaded},
        )
    )
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

    process_evidence = _processes_using_root(
        root,
        proc_root=proc_root,
        qualifier_pid=os.getpid(),
        qualifier_parent_pid=os.getppid(),
        launcher_pid=launcher_pid,
        launcher_path=launcher_path,
    )
    checks.append(
        Check(
            "BX1_OS Process Isolation",
            mode == "canary"
            or (
                process_evidence["proc_root_available"]
                and not process_evidence["matching_processes"]
            ),
            (
                "Canary process is permitted"
                if mode == "canary"
                else "No process is running from BX1_OS after install-only"
            ),
            process_evidence,
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
        "schema": "bx1.deployment.qualification.v3",
        "milestone": "BX1 OS Alpha",
        "release_version": RELEASE_VERSION,
        "release_tag": RELEASE_TAG,
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
            "Release Identity",
            bx1_os.get("release_version") == RELEASE_VERSION
            and bx1_os.get("release_tag") == RELEASE_TAG,
            "Canary reports the expected BX1 OS Alpha release identity",
            {
                "expected_version": RELEASE_VERSION,
                "actual_version": bx1_os.get("release_version"),
                "expected_tag": RELEASE_TAG,
                "actual_tag": bx1_os.get("release_tag"),
            },
        )
    )
    management = _mapping(bx1_os.get("management_interface"))
    capabilities = _mapping(management.get("capabilities"))
    checks.append(
        Check(
            "Management Interface",
            management.get("id") == "bx1-os-management"
            and management.get("state") == "READY"
            and management.get("architecture_only") is True
            and capabilities
            and all(value is False for value in capabilities.values()),
            "BX1 OS Management Interface is ready with all control capabilities disabled",
            {
                "id": management.get("id"),
                "state": management.get("state"),
                "architecture_only": management.get("architecture_only"),
                "capabilities": capabilities,
            },
        )
    )
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
    parser.add_argument("--launcher-pid", type=int)
    parser.add_argument("--launcher-path", type=Path)
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
            launcher_pid=args.launcher_pid,
            launcher_path=args.launcher_path,
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


def _processes_using_root(
    root: Path,
    *,
    proc_root: Path = Path("/proc"),
    qualifier_pid: Optional[int] = None,
    qualifier_parent_pid: Optional[int] = None,
    launcher_pid: Optional[int] = None,
    launcher_path: Optional[Path] = None,
) -> Dict[str, Any]:
    qualifier = int(os.getpid() if qualifier_pid is None else qualifier_pid)
    qualifier_parent = int(
        os.getppid() if qualifier_parent_pid is None else qualifier_parent_pid
    )
    install_root = root.resolve(strict=False)
    evidence: Dict[str, Any] = {
        "qualifier_pid": qualifier,
        "qualifier_parent_pid": qualifier_parent,
        "declared_launcher_pid": launcher_pid,
        "declared_launcher_path": (
            str(launcher_path.resolve(strict=False)) if launcher_path else ""
        ),
        "install_root": str(install_root),
        "examined_process_count": 0,
        "proc_root_available": proc_root.is_dir(),
        "matching_pids": [],
        "matching_processes": [],
        "excluded_pids": [],
        "excluded_processes": [],
        "inspection_errors": [],
    }
    if not evidence["proc_root_available"]:
        evidence["inspection_errors"].append(
            {"pid": None, "field": "proc_root", "error": "procfs_unavailable"}
        )
        return evidence

    records: Dict[int, Dict[str, Any]] = {}
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        evidence["inspection_errors"].append(
            {"pid": None, "field": "proc_root", "error": type(exc).__name__}
        )
        return evidence
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        evidence["examined_process_count"] += 1
        record, errors = _read_process_record(entry, pid)
        evidence["inspection_errors"].extend(errors)
        if record is not None:
            records[pid] = record

    ancestor_pids = _ancestor_pids(
        records, qualifier_pid=qualifier, qualifier_parent_pid=qualifier_parent
    )
    for pid in sorted(records):
        record = records[pid]
        match_reasons = _process_match_reasons(record, install_root)
        if not match_reasons:
            continue
        item = {
            "pid": pid,
            "ppid": record.get("ppid"),
            "cmdline": _display_cmdline(record.get("argv", [])),
            "exe": record.get("exe", ""),
            "cwd": record.get("cwd", ""),
            "match_reasons": match_reasons,
            "is_ancestor": pid in ancestor_pids,
        }
        exclusion_reason = ""
        if pid == qualifier:
            exclusion_reason = "current_qualifier_process"
        elif (
            launcher_pid is not None
            and pid == int(launcher_pid)
            and pid in ancestor_pids
            and launcher_path is not None
            and _is_verified_qualification_launcher(record, launcher_path)
        ):
            exclusion_reason = "verified_current_deployment_launcher_ancestor"
        if exclusion_reason:
            item["reason"] = exclusion_reason
            evidence["excluded_pids"].append(pid)
            evidence["excluded_processes"].append(item)
        else:
            evidence["matching_pids"].append(pid)
            evidence["matching_processes"].append(item)
    return evidence


def _read_process_record(
    entry: Path, pid: int
) -> tuple[Optional[Dict[str, Any]], list[Dict[str, Any]]]:
    errors: list[Dict[str, Any]] = []
    try:
        first_stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        ppid, start_time = _parse_proc_stat(first_stat)
    except (OSError, ValueError) as exc:
        errors.append(
            {"pid": pid, "field": "stat", "error": type(exc).__name__}
        )
        return None, errors

    argv: list[str] = []
    try:
        raw = (entry / "cmdline").read_bytes()
        argv = [
            value.decode("utf-8", errors="replace")
            for value in raw.split(b"\0")
            if value
        ]
    except OSError as exc:
        errors.append(
            {"pid": pid, "field": "cmdline", "error": type(exc).__name__}
        )

    values: Dict[str, str] = {}
    for field in ("exe", "cwd"):
        try:
            target = os.readlink(entry / field)
            if target.endswith(" (deleted)"):
                target = target[: -len(" (deleted)")]
            values[field] = str(Path(target).resolve(strict=False))
        except (OSError, RuntimeError, ValueError) as exc:
            values[field] = ""
            errors.append(
                {"pid": pid, "field": field, "error": type(exc).__name__}
            )
    try:
        second_stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        _, second_start_time = _parse_proc_stat(second_stat)
        if second_start_time != start_time:
            errors.append(
                {"pid": pid, "field": "stat", "error": "pid_reused_during_inspection"}
            )
            return None, errors
    except (OSError, ValueError) as exc:
        errors.append(
            {"pid": pid, "field": "stat_recheck", "error": type(exc).__name__}
        )
        return None, errors
    return {
        "pid": pid,
        "ppid": ppid,
        "start_time": start_time,
        "argv": argv,
        "exe": values["exe"],
        "cwd": values["cwd"],
    }, errors


def _parse_proc_stat(text: str) -> tuple[int, str]:
    close = text.rfind(")")
    fields = text[close + 2 :].split() if close >= 0 else []
    if len(fields) < 20:
        raise ValueError("malformed proc stat")
    return int(fields[1]), fields[19]


def _ancestor_pids(
    records: Mapping[int, Mapping[str, Any]],
    *,
    qualifier_pid: int,
    qualifier_parent_pid: int,
) -> set[int]:
    ancestors: set[int] = set()
    cursor = qualifier_parent_pid
    while cursor > 0 and cursor not in ancestors and cursor != qualifier_pid:
        ancestors.add(cursor)
        record = records.get(cursor)
        if record is None:
            break
        try:
            cursor = int(record.get("ppid", 0))
        except (TypeError, ValueError):
            break
    return ancestors


def _process_match_reasons(
    record: Mapping[str, Any], install_root: Path
) -> list[str]:
    reasons: list[str] = []
    exe = str(record.get("exe", ""))
    cwd = str(record.get("cwd", ""))
    argv = [str(value) for value in record.get("argv", [])]
    if exe and _inside_root(Path(exe), install_root):
        reasons.append("executable_inside_install_root")

    command_paths = _command_paths(argv, Path(cwd) if cwd else None)
    paths_inside = [path for path in command_paths if _inside_root(path, install_root)]
    if paths_inside:
        reasons.append("command_path_inside_install_root")

    executable_name = Path(exe or (argv[0] if argv else "")).name.lower()
    shell_names = {"bash", "dash", "fish", "ksh", "sh", "zsh"}
    if cwd and _inside_root(Path(cwd), install_root) and (
        executable_name not in shell_names or bool(paths_inside)
    ):
        reasons.append("working_directory_inside_install_root")

    inside_names = {path.name.lower() for path in paths_inside}
    if inside_names & {
        "main.py",
        "run_bx1_os_alpha.sh",
        "run_bx1_os_management.sh",
    }:
        reasons.append("alpha_web_runtime")
    if "bx1_management" in argv and paths_inside:
        reasons.append("bx1_management_runtime")
    if inside_names & {
        "hardware_bridge.py",
        "run_robot_body.sh",
        "mcu_router_bridge.py",
        "mcu_serial_bridge.py",
    }:
        reasons.append("alpha_hardware_bridge")
    return reasons


def _command_paths(argv: Sequence[str], cwd: Optional[Path]) -> list[Path]:
    paths: list[Path] = []
    for value in argv:
        candidate = (
            value.split("=", 1)[1]
            if value.startswith("-") and "=" in value
            else value
        )
        if not candidate or candidate.startswith("-"):
            continue
        path = Path(candidate)
        rooted_path = path.is_absolute() or candidate.startswith("/")
        looks_like_path = rooted_path or "/" in candidate or "\\" in candidate
        if not looks_like_path and path.suffix.lower() not in {".py", ".sh"}:
            continue
        if not rooted_path:
            if cwd is None:
                continue
            path = cwd / path
        paths.append(path.resolve(strict=False))
    return paths


def _inside_root(path: Path, root: Path) -> bool:
    resolved = path.resolve(strict=False)
    return resolved == root or root in resolved.parents


def _is_verified_qualification_launcher(
    record: Mapping[str, Any], expected_launcher: Path
) -> bool:
    trusted_names = {"deploy_bx1_os.py", "deploy_bx1_os.sh"}
    expected = expected_launcher.resolve(strict=False)
    if expected.name not in trusted_names:
        return False
    paths = _command_paths(
        [str(value) for value in record.get("argv", [])],
        Path(str(record.get("cwd"))) if record.get("cwd") else None,
    )
    return any(path.resolve(strict=False) == expected for path in paths)


def _display_cmdline(argv: Sequence[str]) -> str:
    secret_option = re.compile(
        r"(?i)(password|passwd|secret|token|api[-_]?key|credential)"
    )
    displayed: list[str] = []
    redact_next = False
    for raw in argv:
        value = str(raw)
        if redact_next:
            displayed.append("<redacted>")
            redact_next = False
            continue
        if value.startswith("-") and "=" in value:
            key, _ = value.split("=", 1)
            displayed.append(key + "=<redacted>" if secret_option.search(key) else value)
        else:
            displayed.append(value)
            redact_next = value.startswith("-") and bool(secret_option.search(value))
    text = " ".join(displayed)
    return text[:2000] + ("..." if len(text) > 2000 else "")


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
