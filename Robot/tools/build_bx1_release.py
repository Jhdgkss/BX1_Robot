#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Tuple


RELEASE_VERSION = "0.3.0"
RELEASE_TAG = "BX1_OS_ALPHA_v0.3.0"

PRESERVED_PATHS = [
    "python/config.json",
    "python/config.json.*",
    "python/robot_profile.json",
    "python/robot_profile*.json",
    "python/*calibration*.json",
    "python/user_settings.json",
    ".env",
    ".venv/",
    "runtime/",
    "models/",
    "logs/",
    "backups/",
]

ROOT_STARTUP_FILES = [
    "main.py",
]

TOOL_FILES = [
    "build_bx1_release.py",
    "deploy_bx1_os.sh",
    "deploy_bx1_os.py",
    "rollback_bx1_os.sh",
    "rollback_bx1_os.py",
    "qualify_bx1_alpha.py",
    "run_robot_body.sh",
    "run_bx1_os_management.sh",
    "check_web_health.sh",
    "test_runtime_integration.py",
    "test_communication_framework.py",
    "test_core_services.py",
    "test_power_services.py",
    "test_hardware_services.py",
    "test_hardware_freshness.py",
    "test_deployment_system.py",
    "test_management_interface.py",
    "test_bx1_core_telemetry.py",
]

DOCUMENTATION_FILES = [
    "BX1_OS_ARCHITECTURE.md",
    "HARDWARE_SERVICES.md",
    "POWER_SYSTEM.md",
    "BATTERY_ARCHITECTURE.md",
    "CORE_SERVICES.md",
    "COMMUNICATION_FRAMEWORK.md",
    "RUNTIME_INTEGRATION.md",
    "DEPLOYMENT_GUIDE.md",
    "BX1_OS_ALPHA_DEPLOYMENT_REPORT.md",
    "BX1_OS_ALPHA_V0_1_2_RELEASE_NOTES.md",
    "BX1_OS_MANAGEMENT_INTERFACE.md",
    "BX1_OS_ALPHA_V0_2_0_RELEASE_NOTES.md",
    "BX1_OS_CORE.md",
    "BX1_OS_CORE_DEVELOPER_GUIDE.md",
    "BX1_OS_ALPHA_V0_3_0_RELEASE_NOTES.md",
]


def build_release(
    repository_root: Path,
    output_dir: Path,
    *,
    timestamp: str,
) -> Tuple[Path, Path, Dict[str, Any]]:
    repo = repository_root.resolve()
    robot = repo / "Robot"
    if not (robot / "python" / "main.py").is_file():
        raise ValueError("repository root does not contain Robot/python/main.py")
    files = collect_release_files(repo)
    commit, dirty = git_identity(repo)
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    release_id = "bx1-os-alpha-%s" % timestamp.lower()

    entries = []
    for source, target in files:
        data = _payload_bytes(source, target)
        entries.append(
            {
                "path": target.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "mode": _mode(source, target),
            }
        )
    manifest: Dict[str, Any] = {
        "schema": "bx1.deployment.release.v1",
        "release_id": release_id,
        "milestone": "BX1 OS Alpha",
        "release_version": RELEASE_VERSION,
        "release_tag": RELEASE_TAG,
        "created_at": created_at,
        "source_git_commit": commit,
        "source_git_branch": _git(
            repo, ["branch", "--show-current"]
        ) or "detached",
        "source_git_tag": RELEASE_TAG
        if RELEASE_TAG in _git(repo, ["tag", "--points-at", "HEAD"]).splitlines()
        else "",
        "source_worktree_dirty": dirty,
        "target_service": "bx1-os-alpha.service",
        "default_install_root": "/home/arduino/BX1_OS",
        "default_web_port": 8089,
        "default_deployment_mode": "install-only",
        "side_by_side": True,
        "firmware_included": False,
        "preserved_paths": list(PRESERVED_PATHS),
        "files": entries,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / (release_id + ".tar.gz")
    sidecar = output_dir / (release_id + ".manifest.json")
    sidecar.write_bytes(manifest_bytes)

    package_root = PurePosixPath(release_id)
    with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
        _add_bytes(
            bundle,
            package_root / "release_manifest.json",
            manifest_bytes,
            0o644,
        )
        special = {
            "tools/deploy_bx1_os.sh": "deploy_bx1_os.sh",
            "tools/rollback_bx1_os.sh": "rollback_bx1_os.sh",
            "tools/qualify_bx1_alpha.py": "qualify_bx1_alpha.py",
        }
        by_target = {target.as_posix(): source for source, target in files}
        for target, package_name in special.items():
            source = by_target[target]
            _add_bytes(
                bundle,
                package_root / package_name,
                _payload_bytes(source, PurePosixPath(target)),
                _mode(source, PurePosixPath(target)),
            )
        for source, target in files:
            _add_bytes(
                bundle,
                package_root / "payload" / target,
                _payload_bytes(source, target),
                _mode(source, target),
            )
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = output_dir / (archive.name + ".sha256")
    checksum.write_text(
        "%s  %s\n" % (archive_hash, archive.name),
        encoding="utf-8",
    )
    return archive, sidecar, manifest


def collect_release_files(repo: Path) -> List[Tuple[Path, PurePosixPath]]:
    robot = repo / "Robot"
    selected: Dict[str, Path] = {}

    def include(source: Path, target: str) -> None:
        if not source.is_file():
            raise FileNotFoundError("required release file is missing: %s" % source)
        key = PurePosixPath(target).as_posix()
        selected[key] = source

    for name in ROOT_STARTUP_FILES:
        include(robot / name, name)

    python_root = robot / "python"
    for source in sorted(python_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(python_root)
        if _exclude_python(relative):
            continue
        include(source, (PurePosixPath("python") / relative.as_posix()).as_posix())

    for name in TOOL_FILES:
        include(robot / "tools" / name, "tools/" + name)
    include(
        robot / "service" / "bx1-os-alpha.service",
        "service/bx1-os-alpha.service",
    )
    for name in DOCUMENTATION_FILES:
        include(
            repo / "Documentation" / name,
            "docs/bx1_os/" + name,
        )
    return [
        (source, PurePosixPath(target))
        for target, source in sorted(selected.items())
    ]


def git_identity(repo: Path) -> Tuple[str, bool]:
    commit = _git(repo, ["rev-parse", "HEAD"]) or "unavailable"
    dirty = bool(_git(repo, ["status", "--porcelain=v1"]))
    return commit, dirty


def main() -> int:
    default_repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repo)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_repo / "Deployment",
    )
    parser.add_argument(
        "--timestamp",
        default=dt.datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    args = parser.parse_args()
    archive, manifest, details = build_release(
        args.repository_root,
        args.output_dir,
        timestamp=args.timestamp,
    )
    print(
        json.dumps(
            {
                "archive": str(archive),
                "manifest": str(manifest),
                "release_id": details["release_id"],
                "source_git_commit": details["source_git_commit"],
                "source_worktree_dirty": details["source_worktree_dirty"],
                "file_count": len(details["files"]),
                "firmware_included": details["firmware_included"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _exclude_python(relative: Path) -> bool:
    name = relative.name
    lower_name = name.lower()
    parts = set(relative.parts)
    if "__pycache__" in parts or name.endswith((".pyc", ".pyo")):
        return True
    if name == "config.json" or name.startswith("config.json."):
        return True
    if name == "robot_profile.json" or name.startswith("robot_profile."):
        return True
    if "calibration" in lower_name or lower_name in {".env", "user_settings.json"}:
        return True
    if lower_name.endswith((".wav", ".mp3", ".zip", ".tgz", ".tar.gz")):
        return True
    return False


def _mode(source: Path, target: PurePosixPath) -> int:
    if source.suffix == ".sh" or target.name in {
        "main.py",
        "qualify_bx1_alpha.py",
        "build_bx1_release.py",
    }:
        return 0o755
    return 0o644


def _payload_bytes(source: Path, target: PurePosixPath) -> bytes:
    data = source.read_bytes()
    if source.suffix.lower() in {
        ".sh",
        ".py",
        ".service",
        ".md",
        ".txt",
        ".json",
        ".html",
    }:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def _add_bytes(
    bundle: tarfile.TarFile,
    path: PurePosixPath,
    data: bytes,
    mode: int,
) -> None:
    info = tarfile.TarInfo(path.as_posix())
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    bundle.addfile(info, io.BytesIO(data))


def _git(repo: Path, args: Iterable[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


if __name__ == "__main__":
    raise SystemExit(main())
