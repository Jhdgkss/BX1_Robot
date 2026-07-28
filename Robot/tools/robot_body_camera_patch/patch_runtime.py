#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import py_compile
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional


PATCH_VERSION = "1.0.0"
PATCH_TAG = "BX1_ROBOT_BODY_CAMERA_PATCH_v1.0.0"
PATCH_ID = "bx1-robot-body-camera-patch-20260728_v1_0_0"
TARGET_ROOT = Path("/home/arduino/Arduino_Q_Client_V1")
BACKUP_ROOT = Path("/home/arduino/Robot_Body_Camera_Patch_backups")
BODY_SERVICE = "bx1-web.service"
BODY_PORT = 8088
BX1_SERVICE = "bx1-os-alpha.service"
BX1_PORT = 8089
BODY_BASE_URL = "http://127.0.0.1:8088"
CAMERA_NODES = ("/dev/video0", "/dev/video1")
MAX_HTTP_BYTES = 2 * 1024 * 1024


class PatchError(RuntimeError):
    pass


class CommandRunner:
    def run(
        self,
        command: Iterable[str],
        *,
        timeout: int = 30,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout)),
            check=False,
        )
        if check and result.returncode:
            raise PatchError(
                "command failed (%s): %s"
                % (result.returncode, " ".join(command))
            )
        return result


@dataclass
class PatchEnvironment:
    target_root: Path = TARGET_ROOT
    backup_root: Path = BACKUP_ROOT
    proc_root: Path = Path("/proc")
    runner: Any = field(default_factory=CommandRunner)
    urlopen: Callable[..., Any] = urllib.request.urlopen
    system_name: Callable[[], str] = platform.system
    geteuid: Callable[[], int] = getattr(os, "geteuid", lambda: 1)
    clock: Callable[[], float] = time.time
    sleeper: Callable[[float], None] = time.sleep
    chown: Callable[[Path, int, int], None] = field(
        default=lambda path, uid, gid: (
            os.chown(path, uid, gid) if hasattr(os, "chown") else None
        )
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_manifest(package_root: Path) -> Dict[str, Any]:
    path = package_root / "manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PatchError("patch manifest is unavailable or invalid") from exc
    if not isinstance(value, dict):
        raise PatchError("patch manifest must be a JSON object")
    expected = {
        "schema": "bx1.robot_body.camera_patch.v1",
        "patch_id": PATCH_ID,
        "patch_version": PATCH_VERSION,
        "patch_tag": PATCH_TAG,
        "target_root": str(TARGET_ROOT),
        "target_service": BODY_SERVICE,
        "target_port": BODY_PORT,
    }
    for key, required in expected.items():
        if value.get(key) != required:
            raise PatchError("patch manifest %s mismatch" % key)
    files = value.get("files")
    if not isinstance(files, list) or not files:
        raise PatchError("patch manifest contains no changed files")
    allowed = {
        "python/main.py",
        "python/web_control.py",
        "python/camera_io.py",
    }
    paths = {str(item.get("path", "")) for item in files}
    if paths != allowed:
        raise PatchError("patch manifest changed-file scope is unsafe")
    return value


def _require_linux(env: PatchEnvironment) -> None:
    if env.system_name() != "Linux":
        raise PatchError("Robot Body camera patch requires Linux")


def _require_root(env: PatchEnvironment) -> None:
    if int(env.geteuid()) != 0:
        raise PatchError("installation and rollback require root privileges")


def _systemctl_value(
    env: PatchEnvironment, service: str, property_name: str
) -> str:
    result = env.runner.run(
        [
            "systemctl",
            "show",
            service,
            "--property",
            property_name,
            "--value",
        ],
        timeout=15,
    )
    if result.returncode:
        return ""
    return str(result.stdout or "").strip()


def service_snapshot(env: PatchEnvironment, service: str) -> Dict[str, Any]:
    load = _systemctl_value(env, service, "LoadState") or "not-found"
    active = _systemctl_value(env, service, "ActiveState") or "inactive"
    main_pid = _systemctl_value(env, service, "MainPID") or "0"
    try:
        pid = int(main_pid)
    except ValueError:
        pid = 0
    return {
        "name": service,
        "load_state": load,
        "active_state": active,
        "main_pid": pid,
    }


def port_listening(port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout):
            return True
    except OSError:
        return False


def wait_for_body_ready(
    env: PatchEnvironment,
    *,
    attempts: int = 60,
    interval: float = 0.5,
) -> bool:
    for _ in range(max(1, int(attempts))):
        if port_listening(BODY_PORT):
            try:
                response = _http_get(env, "/api/status")
                if response["status"] == 200:
                    return True
            except PatchError:
                pass
        env.sleeper(max(0.05, float(interval)))
    return False


def _http_get(
    env: PatchEnvironment,
    path: str,
    *,
    timeout: float = 2.0,
    limit: int = MAX_HTTP_BYTES,
) -> Dict[str, Any]:
    if not path.startswith("/") or "://" in path:
        raise PatchError("HTTP path is not allowlisted")
    request = urllib.request.Request(
        BODY_BASE_URL + path,
        method="GET",
        headers={"Cache-Control": "no-cache"},
    )
    try:
        with env.urlopen(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise PatchError("HTTP response exceeded safety limit")
            return {
                "status": int(getattr(response, "status", 200)),
                "headers": dict(response.headers.items()),
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": int(exc.code),
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "body": exc.read(min(limit, 64 * 1024)),
        }
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise PatchError("Robot Body HTTP request failed: %s" % path) from exc


def _json_response(value: Mapping[str, Any], name: str) -> Dict[str, Any]:
    try:
        decoded = json.loads(bytes(value["body"]).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, KeyError) as exc:
        raise PatchError("%s response is not valid JSON" % name) from exc
    if not isinstance(decoded, dict):
        raise PatchError("%s response is not a JSON object" % name)
    return decoded


def camera_owners(
    env: PatchEnvironment,
    nodes: Iterable[str] = CAMERA_NODES,
) -> Dict[str, Any]:
    targets = {os.path.realpath(str(node)) for node in nodes}
    owners = []
    permission_errors = 0
    examined = 0
    try:
        processes = list(env.proc_root.iterdir())
    except OSError as exc:
        return {
            "owners": [],
            "examined_processes": 0,
            "permission_errors": 1,
            "error": str(exc),
        }
    for process in processes:
        if not process.name.isdigit():
            continue
        examined += 1
        matched = []
        try:
            descriptors = list((process / "fd").iterdir())
        except FileNotFoundError:
            continue
        except PermissionError:
            permission_errors += 1
            continue
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                target = os.path.realpath(os.readlink(descriptor))
            except FileNotFoundError:
                continue
            except PermissionError:
                permission_errors += 1
                continue
            except OSError:
                continue
            if target in targets:
                matched.append(target)
        if not matched:
            continue
        try:
            cmdline = (process / "cmdline").read_bytes().replace(
                b"\x00", b" "
            ).decode("utf-8", errors="replace").strip()
        except OSError:
            cmdline = ""
        try:
            exe = os.readlink(process / "exe")
        except OSError:
            exe = ""
        owners.append(
            {
                "pid": int(process.name),
                "nodes": sorted(set(matched)),
                "cmdline": cmdline,
                "exe": exe,
                "fingerprint": "%s|%s" % (exe, cmdline),
            }
        )
    return {
        "owners": owners,
        "examined_processes": examined,
        "permission_errors": permission_errors,
        "error": "",
    }


def _faults(status: Mapping[str, Any]) -> list[str]:
    faults = []
    doctor = status.get("hardware_doctor")
    if isinstance(doctor, Mapping):
        for value in doctor.get("faults", []) or []:
            faults.append(str(value))
    for event in status.get("events", []) or []:
        if not isinstance(event, Mapping):
            continue
        kind = str(event.get("kind", "")).lower()
        if kind in {"fault", "error", "hardware_fault"}:
            faults.append(
                "%s:%s" % (kind, event.get("message", event.get("error", "")))
            )
    return sorted(set(faults))


def capture_baseline(env: PatchEnvironment) -> Dict[str, Any]:
    body = service_snapshot(env, BODY_SERVICE)
    bx1 = service_snapshot(env, BX1_SERVICE)
    status_response = _http_get(env, "/api/status")
    if status_response["status"] != 200:
        raise PatchError("existing Robot Body status endpoint is unavailable")
    status = _json_response(status_response, "Robot Body status")
    return {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "body_service": body,
        "bx1_service": bx1,
        "port_8088_listening": port_listening(BODY_PORT),
        "port_8089_listening": port_listening(BX1_PORT),
        "camera_owners": camera_owners(env),
        "active_faults": _faults(status),
        "status_keys": sorted(status),
    }


def validate_prepatch(
    package_root: Path,
    env: PatchEnvironment,
) -> Dict[str, Any]:
    _require_linux(env)
    manifest = load_manifest(package_root)
    root = env.target_root.resolve(strict=False)
    if root != TARGET_ROOT and env.target_root == TARGET_ROOT:
        raise PatchError("production root canonical path mismatch")
    if not root.is_dir():
        raise PatchError("production Robot Body installation is missing")
    body = service_snapshot(env, BODY_SERVICE)
    if body["load_state"] == "not-found":
        raise PatchError("bx1-web.service is not installed")
    if body["active_state"] != "active":
        raise PatchError("bx1-web.service must be active before patching")
    mismatches = []
    verified = []
    for item in manifest["files"]:
        relative = Path(str(item["path"]))
        target = root / relative
        if not target.is_file():
            mismatches.append(
                {"path": relative.as_posix(), "reason": "missing"}
            )
            continue
        actual = sha256_file(target)
        expected = str(item["pre_patch_sha256"])
        if actual != expected:
            mismatches.append(
                {
                    "path": relative.as_posix(),
                    "reason": "unexpected_source_difference",
                    "expected": expected,
                    "actual": actual,
                }
            )
        else:
            verified.append(relative.as_posix())
    if mismatches:
        raise PatchError(
            "pre-patch source mismatch: %s"
            % ", ".join(item["path"] for item in mismatches)
        )
    baseline = capture_baseline(env)
    if not baseline["port_8088_listening"]:
        raise PatchError("production port 8088 is not listening")
    return {
        "ok": True,
        "mode": "dry-run",
        "patch_id": PATCH_ID,
        "target_root": str(root),
        "target_service": BODY_SERVICE,
        "verified_pre_patch_files": verified,
        "baseline": baseline,
        "changes_made": False,
    }


def _compile_files(files: Iterable[Path]) -> None:
    for path in files:
        try:
            py_compile.compile(
                str(path),
                cfile=str(path) + ".pyc",
                doraise=True,
            )
        except py_compile.PyCompileError as exc:
            raise PatchError("Python syntax validation failed: %s" % path) from exc
        finally:
            Path(str(path) + ".pyc").unlink(missing_ok=True)


def _timestamp_name(env: PatchEnvironment) -> str:
    return (
        dt.datetime.fromtimestamp(env.clock())
        .strftime("%Y%m%d_%H%M%S")
        + "_ROBOT_BODY_CAMERA_PATCH_v1_0_0"
    )


def _backup_files(
    package_root: Path,
    manifest: Mapping[str, Any],
    baseline: Mapping[str, Any],
    env: PatchEnvironment,
) -> tuple[Path, list[Dict[str, Any]]]:
    backup = env.backup_root / _timestamp_name(env)
    backup.mkdir(parents=True, exist_ok=False)
    metadata = []
    for item in manifest["files"]:
        relative = Path(str(item["path"]))
        source = env.target_root / relative
        destination = backup / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        stat = source.stat()
        metadata.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256_file(destination),
                "mode": stat.st_mode & 0o7777,
                "uid": stat.st_uid,
                "gid": stat.st_gid,
            }
        )
    write_json(
        backup / "backup_manifest.json",
        {
            "schema": "bx1.robot_body.camera_patch.backup.v1",
            "patch_id": PATCH_ID,
            "target_root": str(TARGET_ROOT),
            "target_service": BODY_SERVICE,
            "files": metadata,
            "baseline": baseline,
        },
    )
    write_json(backup / "baseline.json", baseline)
    return backup, metadata


def _stage_files(
    package_root: Path,
    manifest: Mapping[str, Any],
    backup: Path,
) -> list[Path]:
    staged = []
    for item in manifest["files"]:
        relative = Path(str(item["path"]))
        source = package_root / "changed_files" / relative
        if not source.is_file():
            raise PatchError("changed file is missing: %s" % relative)
        if sha256_file(source) != item["post_patch_sha256"]:
            raise PatchError("changed file hash mismatch: %s" % relative)
        destination = backup / "staging" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        staged.append(destination)
    _compile_files(staged)
    return staged


def _atomic_replace(
    source: Path,
    target: Path,
    metadata: Mapping[str, Any],
    env: PatchEnvironment,
) -> None:
    temporary = target.with_name(
        ".%s.%s.new" % (target.name, PATCH_ID)
    )
    shutil.copyfile(source, temporary)
    os.chmod(temporary, int(metadata["mode"]))
    env.chown(temporary, int(metadata["uid"]), int(metadata["gid"]))
    os.replace(temporary, target)


def _verify_postpatch(
    manifest: Mapping[str, Any], env: PatchEnvironment
) -> None:
    for item in manifest["files"]:
        target = env.target_root / str(item["path"])
        if sha256_file(target) != item["post_patch_sha256"]:
            raise PatchError("post-patch verification failed: %s" % item["path"])


def _check(
    checks: list[Dict[str, Any]],
    name: str,
    passed: bool,
    evidence: Any,
    *,
    required: bool = True,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "required": bool(required),
            "evidence": evidence,
        }
    )


def _stream_probe(env: PatchEnvironment) -> Dict[str, Any]:
    request = urllib.request.Request(
        BODY_BASE_URL + "/api/camera/stream?fps=5",
        method="GET",
        headers={"Cache-Control": "no-cache"},
    )
    try:
        response = env.urlopen(request, timeout=3.0)
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            return {
                "ok": True,
                "status": 503,
                "detail": "no_cached_frame_safe",
            }
        return {"ok": False, "status": exc.code, "detail": "http_error"}
    try:
        content_type = str(response.headers.get("Content-Type", ""))
        boundary = response.readline(256)
        headers = {}
        for _ in range(20):
            line = response.readline(4096)
            if line in {b"\r\n", b"\n", b""}:
                break
            name, _, value = line.decode(
                "ascii", errors="replace"
            ).partition(":")
            headers[name.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0") or "0")
        jpeg = response.read(min(length, MAX_HTTP_BYTES + 1))
        valid = (
            content_type.lower().startswith("multipart/x-mixed-replace")
            and b"--frame" in boundary
            and 0 < length <= MAX_HTTP_BYTES
            and len(jpeg) == length
            and jpeg.startswith(b"\xff\xd8")
            and jpeg.endswith(b"\xff\xd9")
        )
        return {
            "ok": valid,
            "status": int(getattr(response, "status", 200)),
            "content_type": content_type,
            "frame_bytes": len(jpeg),
        }
    except (OSError, ValueError):
        return {"ok": False, "status": 200, "detail": "malformed_stream"}
    finally:
        response.close()


def qualify(
    env: PatchEnvironment,
    baseline: Mapping[str, Any],
) -> Dict[str, Any]:
    checks: list[Dict[str, Any]] = []
    body = service_snapshot(env, BODY_SERVICE)
    bx1 = service_snapshot(env, BX1_SERVICE)
    _check(
        checks,
        "bx1-web.service active",
        body["active_state"] == "active",
        body,
    )
    _check(
        checks,
        "Port 8088 listening",
        port_listening(BODY_PORT),
        {"port": BODY_PORT},
    )
    ui = _http_get(env, "/")
    _check(
        checks,
        "Existing Robot Body UI reachable",
        ui["status"] == 200 and bool(ui["body"]),
        {"status": ui["status"]},
    )
    status_response = _http_get(env, "/api/status")
    status = (
        _json_response(status_response, "Robot Body status")
        if status_response["status"] == 200
        else {}
    )
    _check(
        checks,
        "Existing status endpoint reachable",
        status_response["status"] == 200,
        {"status": status_response["status"]},
    )
    camera_response = _http_get(env, "/api/camera/status")
    camera = (
        _json_response(camera_response, "camera status")
        if camera_response["status"] == 200
        else {}
    )
    required_camera_keys = {
        "available",
        "owner",
        "source",
        "resolution",
        "frame_sequence",
        "last_frame_timestamp",
        "frame_age_ms",
        "estimated_fps",
        "stale",
        "error",
    }
    _check(
        checks,
        "Camera status endpoint reachable",
        camera_response["status"] == 200
        and required_camera_keys.issubset(camera),
        {
            "status": camera_response["status"],
            "keys": sorted(camera),
        },
    )
    snapshot = _http_get(env, "/api/camera/snapshot")
    content_type = str(snapshot["headers"].get("Content-Type", "")).lower()
    valid_snapshot = (
        snapshot["status"] == 503
        or (
            snapshot["status"] == 200
            and content_type.startswith("image/jpeg")
            and snapshot["body"].startswith(b"\xff\xd8")
            and snapshot["body"].endswith(b"\xff\xd9")
        )
    )
    _check(
        checks,
        "Cached snapshot endpoint safe",
        valid_snapshot,
        {
            "status": snapshot["status"],
            "content_type": content_type,
            "bytes": len(snapshot["body"]),
        },
    )
    stream = _stream_probe(env)
    _check(checks, "MJPEG connect and disconnect", stream["ok"], stream)
    for _ in range(20):
        post_stream = _http_get(env, "/api/camera/status")
        post_camera = (
            _json_response(post_stream, "camera status")
            if post_stream["status"] == 200
            else {}
        )
        if int(post_camera.get("active_preview_streams", 0) or 0) == 0:
            break
        env.sleeper(0.1)
    _check(
        checks,
        "Preview client cleanup",
        int(post_camera.get("active_preview_streams", 0) or 0) == 0,
        {
            "active_preview_streams": post_camera.get(
                "active_preview_streams"
            )
        },
    )
    owners = camera_owners(env)
    before_owners = (
        baseline.get("camera_owners", {}).get("owners", [])
        if isinstance(baseline.get("camera_owners"), Mapping)
        else []
    )
    before_fingerprints = {
        str(item.get("fingerprint", "")) for item in before_owners
    }
    after_fingerprints = {
        str(item.get("fingerprint", "")) for item in owners["owners"]
    }
    extras = sorted(after_fingerprints - before_fingerprints)
    _check(
        checks,
        "No extra camera owner process",
        not extras and owners["permission_errors"] == 0,
        {
            "before": before_owners,
            "after": owners["owners"],
            "extra_fingerprints": extras,
            "permission_errors": owners["permission_errors"],
        },
    )
    _check(
        checks,
        "No second camera process",
        len(owners["owners"]) <= len(before_owners),
        {
            "before_count": len(before_owners),
            "after_count": len(owners["owners"]),
        },
    )
    baseline_bx1 = baseline.get("bx1_service", {})
    bx1_unchanged = (
        bx1.get("load_state") == baseline_bx1.get("load_state")
        and bx1.get("active_state") == baseline_bx1.get("active_state")
    )
    _check(
        checks,
        "bx1-os-alpha.service state unchanged",
        bx1_unchanged,
        {"before": baseline_bx1, "after": bx1},
    )
    port_8089_now = port_listening(BX1_PORT)
    _check(
        checks,
        "Port 8089 state unchanged",
        port_8089_now == bool(baseline.get("port_8089_listening")),
        {
            "before": baseline.get("port_8089_listening"),
            "after": port_8089_now,
        },
    )
    _check(
        checks,
        "Microphone status remains available",
        isinstance(status.get("mic"), Mapping),
        {"present": "mic" in status},
    )
    voice = status.get("voice_runtime")
    _check(
        checks,
        "STT status remains available",
        isinstance(voice, Mapping),
        {"present": "voice_runtime" in status},
    )
    state = status.get("state")
    sensors = state.get("sensors", {}) if isinstance(state, Mapping) else {}
    imu_known = isinstance(sensors, Mapping) and any(
        "imu" in str(key).lower()
        or str(key).lower() in {"roll", "pitch", "yaw"}
        for key in sensors
    )
    _check(
        checks,
        "IMU telemetry remains available",
        imu_known,
        {"sensor_keys": sorted(sensors) if isinstance(sensors, Mapping) else []},
    )
    faults = _faults(status)
    new_faults = sorted(set(faults) - set(baseline.get("active_faults", [])))
    _check(
        checks,
        "No new active faults",
        not new_faults,
        {
            "before": baseline.get("active_faults", []),
            "after": faults,
            "new": new_faults,
        },
    )
    failures = [
        item["name"]
        for item in checks
        if item["required"] and not item["passed"]
    ]
    return {
        "schema": "bx1.robot_body.camera_patch.qualification.v1",
        "patch_id": PATCH_ID,
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "hardware_actions_requested": False,
        "camera_capture_requested": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def _restore_from_backup(
    backup: Path,
    env: PatchEnvironment,
    *,
    restart: bool,
) -> Dict[str, Any]:
    manifest_path = backup / "backup_manifest.json"
    try:
        saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PatchError("backup manifest is unavailable") from exc
    if (
        saved.get("patch_id") != PATCH_ID
        or saved.get("target_root") != str(TARGET_ROOT)
        or saved.get("target_service") != BODY_SERVICE
    ):
        raise PatchError("backup manifest safety validation failed")
    files = saved.get("files", [])
    backup_files = [backup / "files" / str(item["path"]) for item in files]
    _compile_files(backup_files)
    for item, source in zip(files, backup_files):
        if sha256_file(source) != item["sha256"]:
            raise PatchError("backup file hash mismatch: %s" % item["path"])
        _atomic_replace(
            source,
            env.target_root / str(item["path"]),
            item,
            env,
        )
    if restart:
        result = env.runner.run(
            ["systemctl", "restart", BODY_SERVICE],
            timeout=40,
        )
        if result.returncode:
            raise PatchError("bx1-web.service restart failed during rollback")
        if not wait_for_body_ready(env):
            raise PatchError(
                "port 8088 or Robot Body status did not return after rollback"
            )
    report = {
        "schema": "bx1.robot_body.camera_patch.rollback.v1",
        "patch_id": PATCH_ID,
        "success": True,
        "backup": str(backup),
        "restored_files": [str(item["path"]) for item in files],
        "service_restarted": bool(restart),
        "bx1_os_touched": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(backup / "rollback_report.json", report)
    return report


def install(
    package_root: Path,
    env: PatchEnvironment,
    *,
    no_restart: bool = False,
) -> Dict[str, Any]:
    _require_linux(env)
    _require_root(env)
    preflight = validate_prepatch(package_root, env)
    manifest = load_manifest(package_root)
    backup, metadata = _backup_files(
        package_root, manifest, preflight["baseline"], env
    )
    report: Dict[str, Any] = {
        "schema": "bx1.robot_body.camera_patch.deployment.v1",
        "patch_id": PATCH_ID,
        "mode": "install-no-restart" if no_restart else "install",
        "backup": str(backup),
        "changed_files": [
            str(item["path"]) for item in manifest["files"]
        ],
        "service_restarted": False,
        "qualification_passed": False,
        "rollback_attempted": False,
        "success": False,
    }
    try:
        staged = _stage_files(package_root, manifest, backup)
        by_path = {str(item["path"]): item for item in metadata}
        for item, source in zip(manifest["files"], staged):
            relative = str(item["path"])
            _atomic_replace(
                source,
                env.target_root / relative,
                by_path[relative],
                env,
            )
        _verify_postpatch(manifest, env)
        if no_restart:
            report.update(
                {
                    "success": True,
                    "qualification_passed": False,
                    "qualification_state": "pending_restart",
                }
            )
            write_json(backup / "deployment_report.json", report)
            return report
        restart = env.runner.run(
            ["systemctl", "restart", BODY_SERVICE],
            timeout=40,
        )
        if restart.returncode:
            raise PatchError("bx1-web.service restart failed")
        report["service_restarted"] = True
        if not wait_for_body_ready(env):
            raise PatchError(
                "port 8088 or Robot Body status did not return after restart"
            )
        qualification = qualify(env, preflight["baseline"])
        write_json(backup / "qualification_report.json", qualification)
        if not qualification["passed"]:
            raise PatchError(
                "qualification failed: %s"
                % ", ".join(qualification["failures"])
            )
        report.update(
            {
                "success": True,
                "qualification_passed": True,
                "qualification_state": "passed",
            }
        )
        write_json(backup / "deployment_report.json", report)
        return report
    except Exception as exc:
        report["error"] = str(exc)
        report["rollback_attempted"] = True
        try:
            rollback = _restore_from_backup(backup, env, restart=True)
            report["rollback_success"] = bool(rollback["success"])
        except Exception as rollback_exc:
            report["rollback_success"] = False
            report["rollback_error"] = str(rollback_exc)
        write_json(backup / "deployment_report.json", report)
        raise PatchError(str(exc)) from exc


def rollback(backup: Path, env: PatchEnvironment) -> Dict[str, Any]:
    _require_linux(env)
    _require_root(env)
    root = env.backup_root.resolve(strict=False)
    selected = backup.resolve(strict=False)
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise PatchError("backup path escaped the approved backup root") from exc
    return _restore_from_backup(selected, env, restart=True)


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="BX1 Robot Body cached camera endpoint patch"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.add_argument("--install", action="store_true")
    apply_parser.add_argument("--no-restart", action="store_true")
    qualify_parser = subparsers.add_parser("qualify")
    qualify_parser.add_argument("--baseline", type=Path, required=True)
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args(argv)
    env = PatchEnvironment()
    try:
        if args.command == "apply":
            if args.dry_run and args.install:
                parser.error("--dry-run and --install are mutually exclusive")
            if args.no_restart and not args.install:
                parser.error("--no-restart requires --install")
            if not args.install:
                result = validate_prepatch(_package_root(), env)
            else:
                result = install(
                    _package_root(), env, no_restart=args.no_restart
                )
        elif args.command == "qualify":
            baseline_path = args.baseline.resolve(strict=True)
            allowed = BACKUP_ROOT.resolve(strict=False)
            try:
                baseline_path.relative_to(allowed)
            except ValueError as exc:
                raise PatchError(
                    "baseline escaped approved backup root"
                ) from exc
            baseline = json.loads(
                baseline_path.read_text(encoding="utf-8")
            )
            result = qualify(env, baseline)
        else:
            result = rollback(args.backup, env)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("passed", result.get("ok", result.get("success", True))) else 1
    except PatchError as exc:
        print(
            json.dumps(
                {"ok": False, "patch_id": PATCH_ID, "error": str(exc)},
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
