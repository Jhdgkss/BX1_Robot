#!/usr/bin/env python3
"""Capture and compare redacted BX1 Robot Body production manifests.

The manifest contains file metadata and hashes only. Machine-local
configuration, credentials, runtime state, models, logs, backups and caches
are excluded before hashing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


SCHEMA = "bx1.production.manifest.v1"
DEFAULT_INSTALL_ROOT = "/home/arduino/Arduino_Q_Client_V1"
DEFAULT_SERVICE = "bx1-web.service"
DEFAULT_PORT = 8088

EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "backups",
    "cache",
    "diagnostic_traces",
    "logs",
    "models",
    "runtime",
}

PRIVATE_EXACT_PATHS = {
    ".env",
    "python/config.json",
    "python/robot_profile.json",
    "python/user_settings.json",
}

OS_SOURCE_FILES = {
    "python/bx1.py",
    "python/config.alpha-qualification.json",
    "python/hardware_freshness.py",
    "service/bx1-os-alpha.service",
    "tools/build_bx1_release.py",
    "tools/deploy_bx1_os.py",
    "tools/deploy_bx1_os.sh",
    "tools/production_manifest.py",
    "tools/qualify_bx1_alpha.py",
    "tools/rollback_bx1_os.py",
    "tools/rollback_bx1_os.sh",
    "tools/run_bx1_os_management.sh",
    "tools/test_bx1_core_telemetry.py",
    "tools/test_camera_preview_integration.py",
    "tools/test_communication_framework.py",
    "tools/test_core_services.py",
    "tools/test_deployment_system.py",
    "tools/test_hardware_audio_integration.py",
    "tools/test_hardware_freshness.py",
    "tools/test_hardware_services.py",
    "tools/test_management_interface.py",
    "tools/test_power_services.py",
    "tools/test_production_manifest.py",
    "tools/test_runtime_integration.py",
    "tools/audio_noise_diagnostic.py",
    "tools/imu_diagnostic.py",
    "tools/run_bx1_os_alpha.sh",
    "tools/test_phase1_diagnostics.py",
}

OS_SOURCE_PREFIXES = (
    "python/bx1_core/",
    "python/bx1_management/",
    "python/hardware_services/",
)

STAGED_EXACT_PATHS = {
    "tools/build_robot_body_camera_patch.py",
    "tools/test_robot_body_camera_patch.py",
}

STAGED_PREFIXES = (
    "Body_",
    "payload/",
    "payload_",
    "tools/robot_body_camera_patch/",
    "update_files/",
)

ACTIVE_ROOT_FILES = {
    "START_BX1_WEB.sh",
    "STOP_BX1_WEB.sh",
    "VERSION.txt",
    "app.yaml",
    "main.py",
}

ACTIVE_TOOL_FILES = {
    "tools/bx1_configure_autologin.py",
    "tools/bx1_touchscreen_calibrate.sh",
    "tools/bx1_touchscreen_kiosk.sh",
    "tools/check_mcu_router_bridge.py",
    "tools/check_mcu_router_ping.py",
    "tools/check_mcu_serial_bridge.py",
    "tools/check_web_health.sh",
    "tools/compile_mcu_sketch.sh",
    "tools/desktop_api_smoke_test.py",
    "tools/install_bx1_web_service.sh",
    "tools/run_robot_body.sh",
}

HISTORICAL_EXACT_PATHS = {
    "INSTALL_BX1_GITHUB.sh",
    "ROLLBACK_TO_OLD_BX1.sh",
    "RUN_BX1_BRAIN_V1_7_3_UPDATE.bat",
    "RUN_BX1_BRAIN_V1_7_3_UPDATE.cmd",
    "VERIFY_BX1_GITHUB.sh",
    "service/bx1-robot-body.service",
    "tools/start_touchscreen_kiosk.sh",
}

TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".html",
    ".ino",
    ".json",
    ".md",
    ".py",
    ".service",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
}

DEFAULT_COMPARE_CLASSES = {"active", "support"}


class ManifestError(RuntimeError):
    """Raised when a manifest cannot be captured or validated safely."""


def _posix(path: Path) -> str:
    return PurePosixPath(path.as_posix()).as_posix()


def _is_private(relative: str) -> bool:
    path = PurePosixPath(relative)
    name = path.name.lower()
    if relative in PRIVATE_EXACT_PATHS:
        return True
    if relative.startswith("python/config.json."):
        return True
    if name in {".env", "credentials.json", "secrets.json"}:
        return True
    if name.endswith((".key", ".pem", ".p12", ".pfx")):
        return True
    if any(part.lower() in {"credentials", "secrets"} for part in path.parts):
        return True
    return False


def _is_historical(relative: str) -> bool:
    lower = relative.lower()
    name = PurePosixPath(lower).name
    return (
        relative in HISTORICAL_EXACT_PATHS
        or ".before_" in lower
        or ".backup_" in lower
        or ".pre_v" in lower
        or name.endswith((".bak", ".old", ".orig", "~"))
        or lower.startswith("docs/patch_history/")
    )


def classify_path(relative: str) -> str:
    """Return the source-of-truth role for a non-private path."""

    if relative in OS_SOURCE_FILES or relative.startswith(OS_SOURCE_PREFIXES):
        return "os_source"
    if (
        relative in STAGED_EXACT_PATHS
        or relative.startswith(STAGED_PREFIXES)
        or relative.startswith("APPLY_BX1_")
    ):
        return "staged"
    if _is_historical(relative):
        return "historical"
    if relative in ACTIVE_ROOT_FILES:
        return "active"
    if relative.startswith(("python/", "sketch/", "mcu_micropython/")):
        return "active"
    if relative == "service/bx1-web.service":
        return "active"
    if relative in ACTIVE_TOOL_FILES:
        return "active"
    if relative.startswith("tools/"):
        return "support"
    if relative.startswith("service/"):
        return "historical"
    if relative.startswith("docs/") or PurePosixPath(relative).name.lower().startswith(
        ("readme", "changelog", "patch_summary", "validation")
    ):
        return "documentation"
    if PurePosixPath(relative).suffix.lower() in {".sh", ".bat", ".cmd"}:
        return "support"
    return "historical"


def normalized_mode(path: Path, data: bytes) -> str:
    """Return the deployable mode policy, independent of host filesystem mode."""

    executable = path.suffix.lower() in {".sh", ".bat", ".cmd"} or data.startswith(
        b"#!"
    )
    return "0755" if executable else "0644"


def normalized_payload(path: Path, data: bytes) -> bytes:
    """Return the bytes deployed from Git on either Windows or Linux."""

    if path.suffix.lower() in TEXT_SUFFIXES or data.startswith(b"#!"):
        return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iter_files(root: Path) -> Tuple[List[Path], int]:
    files: List[Path] = []
    private_count = 0
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name not in EXCLUDED_DIRECTORY_NAMES
            and not (Path(current) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = _posix(path.relative_to(root))
            if _is_private(relative):
                private_count += 1
                continue
            files.append(path)
    return files, private_count


def capture_manifest(
    root: Path,
    *,
    observed_at: str = "",
    install_root: str = DEFAULT_INSTALL_ROOT,
    service: str = DEFAULT_SERVICE,
    port: int = DEFAULT_PORT,
    expected_version: str = "",
) -> Dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ManifestError("production root is not a directory: %s" % root)

    version_path = root / "VERSION.txt"
    version = (
        version_path.read_text(encoding="utf-8", errors="strict").strip()
        if version_path.is_file()
        else ""
    )
    if expected_version and version != expected_version:
        raise ManifestError(
            "VERSION.txt is %r; expected %r" % (version or "MISSING", expected_version)
        )

    paths, private_count = _iter_files(root)
    entries: List[Dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for path in paths:
        relative = _posix(path.relative_to(root))
        raw_data = path.read_bytes()
        data = normalized_payload(path, raw_data)
        classification = classify_path(relative)
        counts[classification] += 1
        entries.append(
            {
                "classification": classification,
                "mode": normalized_mode(path, data),
                "path": relative,
                "sha256": _hash(data),
                "size": len(data),
            }
        )

    return {
        "schema": SCHEMA,
        "role": "production_robot_body",
        "observed_at": observed_at,
        "install_root": install_root,
        "service": service,
        "web_port": int(port),
        "version": version,
        "private_files_excluded": private_count,
        "classification_counts": dict(sorted(counts.items())),
        "files": entries,
    }


def _entries(
    manifest: Mapping[str, Any],
    classes: Set[str],
) -> Dict[str, Mapping[str, Any]]:
    if manifest.get("schema") != SCHEMA:
        raise ManifestError("unsupported manifest schema")
    result: Dict[str, Mapping[str, Any]] = {}
    for raw in manifest.get("files", []):
        entry = dict(raw)
        classification = str(entry.get("classification", ""))
        if classification not in classes:
            continue
        path = str(entry.get("path", ""))
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts:
            raise ManifestError("unsafe manifest path: %r" % path)
        if path in result:
            raise ManifestError("duplicate manifest path: %s" % path)
        result[path] = entry
    return result


def compare_manifests(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    classes: Set[str],
) -> Dict[str, Any]:
    expected_entries = _entries(expected, classes)
    actual_entries = _entries(actual, classes)
    expected_paths = set(expected_entries)
    actual_paths = set(actual_entries)
    changed: List[Dict[str, Any]] = []
    for path in sorted(expected_paths & actual_paths):
        wanted = expected_entries[path]
        found = actual_entries[path]
        fields = [
            field
            for field in ("sha256", "size", "mode", "classification")
            if wanted.get(field) != found.get(field)
        ]
        if fields:
            changed.append({"path": path, "fields": fields})

    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    version_match = expected.get("version") == actual.get("version")
    return {
        "schema": "bx1.production.comparison.v1",
        "classes": sorted(classes),
        "expected_version": expected.get("version", ""),
        "actual_version": actual.get("version", ""),
        "version_match": version_match,
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "match": version_match and not missing and not extra and not changed,
    }


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError("cannot read manifest %s: %s" % (path, exc)) from exc
    if not isinstance(value, dict):
        raise ManifestError("manifest root must be a JSON object")
    return value


def _classes(value: str) -> Set[str]:
    classes = {part.strip() for part in value.split(",") if part.strip()}
    if not classes:
        raise argparse.ArgumentTypeError("at least one class is required")
    return classes


def _write_json(value: Mapping[str, Any], output: Optional[Path]) -> None:
    rendered = json.dumps(dict(value), indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture", help="capture a redacted manifest")
    capture.add_argument("--root", type=Path, required=True)
    capture.add_argument("--output", type=Path)
    capture.add_argument("--observed-at", default="")
    capture.add_argument("--install-root", default=DEFAULT_INSTALL_ROOT)
    capture.add_argument("--service", default=DEFAULT_SERVICE)
    capture.add_argument("--port", type=int, default=DEFAULT_PORT)
    capture.add_argument("--expected-version", default="")

    compare = commands.add_parser("compare", help="compare two captured manifests")
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)
    compare.add_argument(
        "--classes",
        type=_classes,
        default=set(DEFAULT_COMPARE_CLASSES),
        help="comma-separated classifications (default: active,support)",
    )
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capture":
            value = capture_manifest(
                args.root,
                observed_at=args.observed_at,
                install_root=args.install_root,
                service=args.service,
                port=args.port,
                expected_version=args.expected_version,
            )
            _write_json(value, args.output)
            return 0
        result = compare_manifests(
            _load(args.expected),
            _load(args.actual),
            classes=set(args.classes),
        )
        _write_json(result, args.output)
        return 0 if result["match"] else 1
    except ManifestError as exc:
        print("production manifest error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
