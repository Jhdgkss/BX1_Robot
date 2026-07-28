#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping, Optional


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


def qualify(
    *,
    install_root: Path,
    service_name: str,
    status_url: str,
    snapshot: Optional[Mapping[str, Any]] = None,
    skip_systemd: bool = False,
    allow_hardware_unavailable: bool = False,
    allow_brain_offline: bool = False,
    timeout_s: float = 10.0,
) -> Dict[str, Any]:
    started = time.time()
    checks = []
    root = install_root.resolve()

    if snapshot is None:
        snapshot = _get_json(status_url, timeout_s=timeout_s)
    snapshot = dict(snapshot)
    bx1_os = _mapping(snapshot.get("bx1_os"))
    startup = _mapping(bx1_os.get("startup"))

    checks.append(
        Check(
            "Bootstrap",
            bool(bx1_os.get("startup_validated"))
            and bool(startup.get("success")),
            "BX1 OS Alpha startup report is validated",
            {
                "milestone": bx1_os.get("milestone"),
                "schema": startup.get("schema"),
            },
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
            {
                "missing": sorted(required - registered),
                "registered_count": registry.get("registered_count"),
                "running_count": registry.get("running_count"),
            },
        )
    )
    scheduler = _mapping(bx1_os.get("scheduler"))
    checks.append(
        Check(
            "Scheduler",
            scheduler.get("state") == "READY"
            and int(scheduler.get("tick_count", 0)) > 0,
            "Cooperative Scheduler is active",
            scheduler,
        )
    )
    events = _mapping(bx1_os.get("events"))
    checks.append(
        Check(
            "Event Bus",
            events.get("state") == "READY",
            "Event Bus is available",
            events,
        )
    )
    diagnostics = _mapping(bx1_os.get("diagnostics"))
    checks.append(
        Check(
            "Diagnostics",
            diagnostics.get("state") == "READY",
            "Diagnostics Service is ready",
            diagnostics,
        )
    )
    communication = _mapping(bx1_os.get("communication"))
    checks.append(
        Check(
            "Communication",
            communication.get("state") == "READY"
            and communication.get("transport") == "in_memory",
            "Communication is active in safe in-memory mode",
            communication,
        )
    )
    health = _mapping(bx1_os.get("health"))
    checks.append(
        Check(
            "Health Monitor",
            health.get("state") == "READY"
            and int(health.get("check_count", 0)) > 0,
            "Health Monitor is operational",
            health,
        )
    )
    runtime_hardware = _mapping(bx1_os.get("runtime_hardware"))
    state = _mapping(snapshot.get("state"))
    bridge_available = bool(
        state.get("bridge_available", state.get("mcu_transport_connected", False))
    )
    bridge_ok = runtime_hardware.get("state") == "READY" and (
        bridge_available or allow_hardware_unavailable
    )
    checks.append(
        Check(
            "Hardware Bridge",
            bridge_ok,
            (
                "BX1 owns the existing hardware bridge"
                if bridge_available
                else "Bridge unavailable; override accepted"
                if allow_hardware_unavailable
                else "Existing hardware bridge is unavailable"
            ),
            {
                "service": runtime_hardware,
                "bridge_available": bridge_available,
                "bridge_mode": state.get("bridge_mode"),
            },
        )
    )

    brain = _mapping(snapshot.get("brain"))
    brain_url = str(brain.get("base_url", "")).rstrip("/")
    brain_ok = False
    brain_detail = "Brain App URL is not configured"
    brain_evidence: Dict[str, Any] = {"configured": bool(brain_url)}
    if brain_url:
        try:
            config = _load_json(root / "python" / "config.json")
            headers = {"Accept": "application/json"}
            api_key = str(config.get("api_key", "")).strip()
            if api_key:
                headers["X-BX1-API-Key"] = api_key
            response = _get_json(
                brain_url + "/api/status",
                timeout_s=timeout_s,
                headers=headers,
            )
            brain_ok = isinstance(response, Mapping)
            brain_detail = "Brain App status endpoint answered"
            brain_evidence["response_keys"] = sorted(response)[:30]
        except Exception as exc:
            brain_detail = "Brain App qualification failed: %s" % exc
    if allow_brain_offline and not brain_ok:
        brain_ok = True
        brain_detail += "; offline override accepted"
    checks.append(Check("Brain Connection", brain_ok, brain_detail, brain_evidence))

    checks.append(
        Check(
            "Web Interface",
            bool(snapshot.get("ok")) and bool(snapshot),
            "Robot status API answered",
            {"url": status_url, "response_ok": snapshot.get("ok")},
        )
    )

    if skip_systemd:
        service_active = True
        service_enabled = True
        service_evidence = {"skipped": True}
    else:
        active = _run(["systemctl", "is-active", service_name])
        enabled = _run(["systemctl", "is-enabled", service_name])
        service_active = active["returncode"] == 0 and active["stdout"] == "active"
        service_enabled = enabled["returncode"] == 0 and enabled["stdout"] in {
            "enabled",
            "enabled-runtime",
        }
        service_evidence = {"active": active, "enabled": enabled}
    checks.append(
        Check(
            "Existing Runtime",
            service_active and service_enabled and bool(snapshot.get("ok")),
            "Robot service is active, enabled and serving its existing API",
            service_evidence,
        )
    )

    passed = all(check.passed for check in checks)
    return {
        "schema": "bx1.deployment.qualification.v1",
        "milestone": "BX1 OS Alpha",
        "started_at": started,
        "completed_at": time.time(),
        "passed": passed,
        "install_root": str(root),
        "service_name": service_name,
        "status_url": status_url,
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "hardware_actions_requested": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-release", type=Path)
    parser.add_argument(
        "--install-root",
        type=Path,
        default=Path("/home/arduino/Arduino_Q_Client_V1"),
    )
    parser.add_argument("--service-name", default="bx1-web.service")
    parser.add_argument(
        "--status-url",
        default="http://127.0.0.1:8088/api/status",
    )
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
        snapshot = (
            _load_json(args.snapshot_file)
            if args.snapshot_file is not None
            else None
        )
        report = qualify(
            install_root=args.install_root,
            service_name=args.service_name,
            status_url=args.status_url,
            snapshot=snapshot,
            skip_systemd=args.skip_systemd,
            allow_hardware_unavailable=args.allow_hardware_unavailable,
            allow_brain_offline=args.allow_brain_offline,
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


if __name__ == "__main__":
    raise SystemExit(main())
