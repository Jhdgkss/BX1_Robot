#!/usr/bin/env python3
"""Build the minimal Robot Body staging archive for the v0.6.1 conversation repair."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


VERSION = "0.6.1-development"
PACKAGE = "bx1-robot-body-voice-conversation-v0.6.1-development"
FILES = (
    "python/audio_io.py",
    "python/main.py",
    "python/web_control.py",
)
PRODUCTION_MANIFEST = Path(
    "Documentation/production-baselines/BX1_ROBOT_BODY_v10.39_20260728.manifest.json"
)


def payload_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def add_bytes(bundle: tarfile.TarFile, name: str, data: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    bundle.addfile(info, io.BytesIO(data))


def production_patch_file_modes(repository_root: Path) -> Dict[str, int]:
    """Read the reconciled Body manifest instead of inventing patch modes."""
    manifest_path = repository_root.resolve() / PRODUCTION_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {
        str(item.get("path", "")): item
        for item in manifest.get("files", [])
        if isinstance(item, dict)
    }
    modes: Dict[str, int] = {}
    for relative in FILES:
        entry = entries.get(relative)
        if not entry or entry.get("classification") != "active":
            raise ValueError("Body patch path is not an active production file: %s" % relative)
        mode = int(str(entry.get("mode", "")), 8)
        if mode & 0o111:
            raise ValueError("Body patch path is executable in production: %s" % relative)
        modes[relative] = mode
    return modes


def build(repository_root: Path, output_dir: Path, timestamp: str) -> tuple[Path, Path, Dict[str, Any]]:
    repo = repository_root.resolve()
    robot = repo / "Robot"
    patch_modes = production_patch_file_modes(repo)
    entries = []
    payloads = []
    for relative in FILES:
        source = robot / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        data = payload_bytes(source)
        mode = patch_modes[relative]
        payloads.append((relative, data, mode))
        entries.append({
            "path": relative,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "mode": format(mode, "04o"),
        })
    manifest: Dict[str, Any] = {
        "schema": "bx1.body.voice_observer_patch.v1",
        "package": PACKAGE,
        "version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_root": "/home/arduino/Arduino_Q_Client_V1",
        "requires_body_service_restart": True,
        "issues_no_actuator_commands": True,
        "machine_local_config_merge_required": True,
        "required_machine_local_config_keys": [
            "brain_base_url",
            "voice_observer_url",
        ],
        "files": entries,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{PACKAGE}-{timestamp}"
    archive = output_dir / f"{stem}.tar.gz"
    sidecar = output_dir / f"{stem}.manifest.json"
    sidecar.write_bytes(manifest_bytes)
    with tarfile.open(archive, "w:gz", compresslevel=6) as bundle:
        add_bytes(bundle, "body_patch_manifest.json", manifest_bytes)
        for relative, data, mode in payloads:
            add_bytes(bundle, relative, data, mode)
    return archive, sidecar, manifest


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=root)
    parser.add_argument("--output-dir", type=Path, default=root / "Deployment")
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()
    archive, sidecar, manifest = build(args.repository_root, args.output_dir, args.timestamp)
    print(json.dumps({"archive": str(archive), "manifest": str(sidecar), "files": len(manifest["files"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
