#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable


PATCH_VERSION = "1.0.0"
PATCH_TAG = "BX1_ROBOT_BODY_CAMERA_PATCH_v1.0.0"
PATCH_ID = "bx1-robot-body-camera-patch-20260728_v1_0_0"
BASELINE_TAG = "BX1_OS_ALPHA_v0.4.0"
CHANGED_FILES = (
    "Robot/python/main.py",
    "Robot/python/web_control.py",
    "Robot/python/camera_io.py",
)


def _git(repo: Path, arguments: Iterable[str], *, binary=False):
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        check=False,
        text=not binary,
    )
    if result.returncode:
        raise RuntimeError("git command failed: %s" % " ".join(arguments))
    return result.stdout


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mode(path: PurePosixPath) -> int:
    return 0o755 if path.suffix in {".sh", ".py"} and not str(path).startswith(
        "changed_files/"
    ) and not str(path).startswith("tests/") else 0o644


def _write(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    os.chmod(path, mode)


def build(
    repo: Path,
    output: Path,
) -> Dict[str, Any]:
    repo = repo.resolve()
    output = output.resolve()
    commit = str(_git(repo, ["rev-parse", "HEAD"])).strip()
    baseline_commit = str(
        _git(repo, ["rev-list", "-n", "1", BASELINE_TAG])
    ).strip()
    branch = str(_git(repo, ["branch", "--show-current"])).strip()
    tags = str(_git(repo, ["tag", "--points-at", "HEAD"])).splitlines()
    dirty = bool(str(_git(repo, ["status", "--porcelain=v1"])).strip())
    template = repo / "Robot" / "tools" / "robot_body_camera_patch"
    release_report = (
        repo
        / "Documentation"
        / "BX1_ROBOT_BODY_CAMERA_PATCH_V1_0_0_RELEASE_REPORT.md"
    )
    release_tree = output / PATCH_ID
    if release_tree.exists():
        resolved = release_tree.resolve()
        try:
            resolved.relative_to(output)
        except ValueError as exc:
            raise RuntimeError("unsafe release-tree path") from exc
        shutil.rmtree(resolved)
    release_tree.mkdir(parents=True)

    package_sources = {
        PurePosixPath("apply_robot_body_camera_patch.sh"):
            template / "apply_robot_body_camera_patch.sh",
        PurePosixPath("rollback_robot_body_camera_patch.sh"):
            template / "rollback_robot_body_camera_patch.sh",
        PurePosixPath("qualify_robot_body_camera_patch.sh"):
            template / "qualify_robot_body_camera_patch.sh",
        PurePosixPath("README.md"): template / "README.md",
        PurePosixPath("RELEASE_REPORT.md"): release_report,
        PurePosixPath("tools/patch_runtime.py"):
            template / "patch_runtime.py",
        PurePosixPath("tests/test_package.py"):
            template / "test_package.py",
    }
    package_entries = []
    for target, source in package_sources.items():
        data = source.read_bytes()
        mode = _mode(target)
        _write(release_tree / target.as_posix(), data, mode)
        package_entries.append(
            {
                "path": target.as_posix(),
                "sha256": _sha(data),
                "size": len(data),
                "mode": mode,
            }
        )

    changed_entries = []
    for repository_path in CHANGED_FILES:
        relative = repository_path.removeprefix("Robot/")
        current = (repo / repository_path).read_bytes()
        previous = _git(
            repo,
            ["show", "%s:%s" % (BASELINE_TAG, repository_path)],
            binary=True,
        )
        target = PurePosixPath("changed_files") / relative
        _write(release_tree / target.as_posix(), current, 0o644)
        package_entries.append(
            {
                "path": target.as_posix(),
                "sha256": _sha(current),
                "size": len(current),
                "mode": 0o644,
            }
        )
        changed_entries.append(
            {
                "path": relative,
                "pre_patch_sha256": _sha(previous),
                "post_patch_sha256": _sha(current),
                "post_patch_size": len(current),
                "mode": 0o644,
            }
        )

    manifest: Dict[str, Any] = {
        "schema": "bx1.robot_body.camera_patch.v1",
        "patch_id": PATCH_ID,
        "patch_version": PATCH_VERSION,
        "patch_tag": PATCH_TAG,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_git_commit": commit,
        "source_git_branch": branch,
        "source_git_tag": PATCH_TAG if PATCH_TAG in tags else "",
        "source_worktree_dirty": dirty,
        "pre_patch_source_tag": BASELINE_TAG,
        "pre_patch_source_commit": baseline_commit,
        "target_root": "/home/arduino/Arduino_Q_Client_V1",
        "target_service": "bx1-web.service",
        "target_port": 8088,
        "protected_root": "/home/arduino/BX1_OS",
        "protected_service": "bx1-os-alpha.service",
        "protected_port": 8089,
        "default_mode": "dry-run",
        "complete_project_included": False,
        "camera_capture_added": False,
        "camera_control_added": False,
        "files": changed_entries,
        "package_files": sorted(
            package_entries, key=lambda item: item["path"]
        ),
        "endpoints": [
            "GET /api/camera/status",
            "GET /api/camera/snapshot",
            "GET /api/camera/stream",
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write(release_tree / "manifest.json", manifest_bytes, 0o644)

    output.mkdir(parents=True, exist_ok=True)
    sidecar = output / (PATCH_ID + ".manifest.json")
    sidecar.write_bytes(manifest_bytes)
    archive = output / (PATCH_ID + ".tar.gz")
    with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
        for source in sorted(release_tree.rglob("*")):
            arcname = PurePosixPath(PATCH_ID) / source.relative_to(
                release_tree
            ).as_posix()
            bundle.add(source, arcname=arcname.as_posix(), recursive=False)
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = output / (archive.name + ".sha256")
    checksum.write_text(
        "%s  %s\n" % (archive_sha, archive.name),
        encoding="utf-8",
    )
    return {
        "archive": str(archive),
        "checksum": str(checksum),
        "manifest": str(sidecar),
        "release_tree": str(release_tree),
        "archive_sha256": archive_sha,
        "changed_file_count": len(changed_entries),
        "package_file_count": len(package_entries) + 1,
        "source_git_commit": commit,
        "source_worktree_dirty": dirty,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Build the minimal BX1 Robot Body camera endpoint patch"
    )
    parser.add_argument("--repository-root", type=Path, default=repo)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo / "Deployment" / "Robot_Body_Camera_Patch",
    )
    args = parser.parse_args()
    result = build(args.repository_root, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
