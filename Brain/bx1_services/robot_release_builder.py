"""Build safe BX1 Robot Linux release archives for the Robot Update Manager."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from bx1_services.robot_update_service import (
    DEFAULT_PRESERVED_PATHS,
    DEFAULT_SERVICE_NAME,
    DEFAULT_TARGET_DIRECTORY,
    MAX_ARCHIVE_BYTES,
    MANIFEST_NAME,
    SHA256SUMS_NAME,
    ManifestFile,
    PackageValidationError,
    inspect_release_archive,
    release_content_checksum,
)


BUILDER_VERSION = "2.0"
DEFAULT_PRODUCT = "BX1 Robot"
DEFAULT_RELEASE_TYPE = "linux-software"
DEFAULT_MINIMUM_BRAIN_VERSION = "2.12.0"
MAX_RELEASE_FILE_COUNT = 5000
DETERMINISTIC_MTIME = 0

EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "payload",
    "update_files",
    "files",
    "models",
    "cache",
    "caches",
    "logs",
    "traces",
    "diagnostics",
    "backups",
    "backup",
    "browser_profiles",
}
EXCLUDED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".trace",
    ".tmp",
    ".bak",
    ".old",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".gz",
    ".zip",
    ".7z",
}
EXCLUDED_FILE_NAMES = {
    ".env",
    "secrets.json",
    "secrets.local.json",
    "known_hosts",
}
PROTECTED_PATHS = set(DEFAULT_PRESERVED_PATHS)
PROTECTED_PREFIXES = {
    "runtime/audio",
    "runtime/calibration",
    "calibration",
}
MCU_SUFFIXES = {".ino", ".hex", ".uf2"}
MCU_PREFIXES = {"sketch", "firmware", "mcu"}
VERSION_RE = re.compile(r"(?<!\d)([0-9]+(?:\.[0-9]+){1,3})(?!\d)")


class RobotReleaseBuilderError(Exception):
    """Base class for release builder failures."""


class VersionConflictError(RobotReleaseBuilderError):
    """Raised when versions conflict and no acknowledged override was provided."""


class ReleaseOverwriteError(RobotReleaseBuilderError):
    """Raised when an output package already exists and overwrite is not allowed."""


class SourceSafetyError(RobotReleaseBuilderError):
    """Raised when source files are unsafe for packaging."""


@dataclass(frozen=True)
class VersionDeclaration:
    path: str
    version: str
    source: str


@dataclass(frozen=True)
class SourceInspection:
    source_dir: Path
    detected_version: str
    declarations: List[VersionDeclaration]
    conflicts: List[str]
    warnings: List[str]


@dataclass(frozen=True)
class ReleaseFile:
    source_path: Path
    archive_path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ReleaseBuildOptions:
    source_dir: Path
    output_dir: Path
    version_override: str = ""
    acknowledge_version_conflict: bool = False
    overwrite: bool = False
    product: str = DEFAULT_PRODUCT
    release_type: str = DEFAULT_RELEASE_TYPE
    service_name: str = DEFAULT_SERVICE_NAME
    target_directory: str = DEFAULT_TARGET_DIRECTORY
    minimum_brain_version: str = DEFAULT_MINIMUM_BRAIN_VERSION
    preserved_paths: List[str] = field(default_factory=lambda: list(DEFAULT_PRESERVED_PATHS) + ["calibration", "runtime/calibration"])


@dataclass(frozen=True)
class ReleaseBuildResult:
    package_path: Path
    manifest_path: Path
    checksums_path: Path
    version: str
    archive_sha256: str
    content_checksum: str
    file_count: int
    warnings: List[str]


ProgressCallback = Callable[[str], None]


def _normalise_archive_path(path: Path) -> str:
    value = path.as_posix().strip()
    if not value or value.startswith("/") or value.startswith("~") or ".." in value.split("/"):
        raise SourceSafetyError(f"Unsafe archive path: {value}")
    if re.match(r"^[A-Za-z]:", value):
        raise SourceSafetyError(f"Unsafe archive path: {value}")
    return value


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path, max_bytes: int = 1024 * 1024) -> str:
    data = path.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def _version_from_app_yaml(source_dir: Path) -> List[VersionDeclaration]:
    app_yaml = source_dir / "app.yaml"
    if not app_yaml.exists() or not app_yaml.is_file():
        return []
    declarations: List[VersionDeclaration] = []
    for line in _read_text(app_yaml).splitlines():
        if "version" not in line.lower():
            continue
        match = VERSION_RE.search(line)
        if match:
            declarations.append(VersionDeclaration("app.yaml", match.group(1), "app.yaml"))
            break
    return declarations


def _version_from_python_sources(source_dir: Path) -> List[VersionDeclaration]:
    declarations: List[VersionDeclaration] = []
    candidates = [
        source_dir / "main.py",
        source_dir / "python" / "main.py",
        source_dir / "python" / "web_control.py",
    ]
    patterns = [
        re.compile(r"(?:ROBOT_VERSION|APP_VERSION|VERSION|version)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
        re.compile(r"Robot(?:\s+Body)?\s+V?([0-9]+(?:\.[0-9]+){1,3})", re.IGNORECASE),
    ]
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        text = _read_text(candidate)
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                declarations.append(
                    VersionDeclaration(
                        candidate.relative_to(source_dir).as_posix(),
                        match.group(1).strip(),
                        "python-source",
                    )
                )
                break
    return declarations


def inspect_robot_source(source_dir: Path) -> SourceInspection:
    source = Path(source_dir).expanduser().resolve()
    warnings: List[str] = []
    if not source.exists() or not source.is_dir():
        raise SourceSafetyError(f"Robot source directory does not exist: {source}")
    declarations = _version_from_app_yaml(source) + _version_from_python_sources(source)
    versions = sorted({item.version for item in declarations})
    conflicts: List[str] = []
    if not declarations:
        warnings.append("No Robot version declarations were found in app.yaml or authoritative Python source.")
        detected = ""
    elif len(versions) > 1:
        conflicts.append("Conflicting Robot versions: " + ", ".join(f"{item.path}={item.version}" for item in declarations))
        detected = versions[-1]
    else:
        detected = versions[0]
    if (source / "python" / "config.json").exists():
        warnings.append("python/config.json is ignored for version detection and will be preserved on the robot.")
    return SourceInspection(source, detected, declarations, conflicts, warnings)


def _is_secret_path(archive_path: str) -> bool:
    lower = archive_path.lower()
    name = Path(lower).name
    return (
        name in EXCLUDED_FILE_NAMES
        or name.startswith(".env")
        or "secret" in name
        or lower.endswith(".pem")
        or lower.endswith(".key")
        or lower.endswith(".pfx")
    )


def _is_protected_path(archive_path: str) -> bool:
    lower = archive_path.lower()
    if lower in {path.lower() for path in PROTECTED_PATHS}:
        return True
    return any(lower == prefix.lower() or lower.startswith(f"{prefix.lower()}/") for prefix in PROTECTED_PREFIXES)


def _is_mcu_path(archive_path: str) -> bool:
    lower = archive_path.lower()
    parts = lower.split("/")
    return any(part in MCU_PREFIXES for part in parts) or any(lower.endswith(suffix) for suffix in MCU_SUFFIXES)


def _excluded_reason(archive_path: str) -> Optional[str]:
    lower = archive_path.lower()
    parts = lower.split("/")
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return "historical/runtime/dependency directory"
    if _is_protected_path(archive_path):
        return "protected robot-local configuration or runtime asset"
    if _is_secret_path(archive_path):
        return "secret or environment file"
    if _is_mcu_path(archive_path):
        return "MCU firmware is excluded from Linux releases"
    if Path(lower).suffix in EXCLUDED_FILE_SUFFIXES:
        return "generated archive/cache/log file"
    return None


def collect_release_files(source_dir: Path, *, max_file_count: int = MAX_RELEASE_FILE_COUNT) -> tuple[List[ReleaseFile], List[str]]:
    source = Path(source_dir).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise SourceSafetyError(f"Robot source directory does not exist: {source}")
    warnings: List[str] = []
    release_files: List[ReleaseFile] = []
    seen_archive_paths: set[str] = set()
    for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
        root_path = Path(root)
        kept_dirs = []
        for dirname in sorted(dirs):
            child = root_path / dirname
            relative = _normalise_archive_path(child.relative_to(source))
            if child.is_symlink():
                resolved = child.resolve()
                if not _is_under(resolved, source):
                    raise SourceSafetyError(f"Symlink escapes source directory: {relative}")
                warnings.append(f"Excluded symlinked directory: {relative}")
                continue
            reason = _excluded_reason(relative + "/placeholder")
            if reason:
                warnings.append(f"Excluded {relative}/: {reason}.")
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for filename in sorted(files):
            path = root_path / filename
            relative_path = path.relative_to(source)
            archive_path = _normalise_archive_path(relative_path)
            if path.is_symlink():
                resolved = path.resolve()
                if not _is_under(resolved, source):
                    raise SourceSafetyError(f"Symlink escapes source directory: {archive_path}")
                warnings.append(f"Excluded symlinked file: {archive_path}")
                continue
            reason = _excluded_reason(archive_path)
            if reason:
                warnings.append(f"Excluded {archive_path}: {reason}.")
                continue
            if archive_path in seen_archive_paths:
                raise SourceSafetyError(f"Duplicate archive path: {archive_path}")
            seen_archive_paths.add(archive_path)
            stat = path.stat()
            release_files.append(ReleaseFile(path, archive_path, stat.st_size, _sha256_file(path)))
            if len(release_files) > max_file_count:
                raise SourceSafetyError(f"Release exceeds the {max_file_count} file limit.")
    release_files.sort(key=lambda item: item.archive_path)
    return release_files, warnings


def _manifest_payload(options: ReleaseBuildOptions, version: str, release_files: Iterable[ReleaseFile], created_timestamp: str) -> Dict[str, Any]:
    included = [
        {"path": item.archive_path, "size": item.size, "sha256": item.sha256}
        for item in release_files
    ]
    content_checksum = release_content_checksum(
        ManifestFile(path=item["path"], sha256=item["sha256"], size=int(item["size"])) for item in included
    )
    return {
        "product": options.product,
        "version": version,
        "release_type": options.release_type,
        "created_timestamp": created_timestamp,
        "service_name": options.service_name,
        "target_directory": options.target_directory,
        "minimum_brain_version": options.minimum_brain_version,
        "preserved_paths": list(options.preserved_paths),
        "included_files": included,
        "package_checksum": content_checksum,
        "builder_version": BUILDER_VERSION,
    }


def _write_tar_gz(output_path: Path, manifest: Dict[str, Any], checksums_text: str, release_files: List[ReleaseFile]) -> None:
    with output_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=DETERMINISTIC_MTIME) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                def add_bytes(name: str, payload: bytes, mode: int = 0o644) -> None:
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mtime = DETERMINISTIC_MTIME
                    info.mode = mode
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    tar.addfile(info, fileobj=None if not payload else io.BytesIO(payload))

                add_bytes(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n")
                add_bytes(SHA256SUMS_NAME, checksums_text.encode("utf-8"))
                for item in release_files:
                    info = tarfile.TarInfo(item.archive_path)
                    info.size = item.size
                    info.mtime = DETERMINISTIC_MTIME
                    info.mode = 0o755 if os.access(item.source_path, os.X_OK) else 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    with item.source_path.open("rb") as handle:
                        tar.addfile(info, handle)


class RobotReleaseBuilder:
    def inspect_source(self, source_dir: Path) -> SourceInspection:
        return inspect_robot_source(source_dir)

    def build(self, options: ReleaseBuildOptions, progress: Optional[ProgressCallback] = None) -> ReleaseBuildResult:
        emit = progress or (lambda message: None)
        source_info = inspect_robot_source(options.source_dir)
        version = options.version_override.strip() or source_info.detected_version
        if not version:
            raise VersionConflictError("No Robot version was detected. Provide an acknowledged version override.")
        if source_info.conflicts and not (options.version_override and options.acknowledge_version_conflict):
            raise VersionConflictError("; ".join(source_info.conflicts))
        if options.version_override and source_info.detected_version and options.version_override != source_info.detected_version and not options.acknowledge_version_conflict:
            raise VersionConflictError("Version override differs from detected Robot version and must be acknowledged.")
        declared_versions = {item.version for item in source_info.declarations}
        if options.version_override and declared_versions and options.version_override not in declared_versions:
            raise VersionConflictError("Version override is not present in the selected Robot source declarations.")
        output_dir = Path(options.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        final_package = output_dir / f"bx1-robot-{version}.tar.gz"
        final_manifest = output_dir / MANIFEST_NAME
        final_checksums = output_dir / SHA256SUMS_NAME
        if final_package.exists() and not options.overwrite:
            raise ReleaseOverwriteError(f"Release archive already exists: {final_package}")
        temp_dir = Path(tempfile.mkdtemp(prefix="bx1_robot_release_", dir=str(output_dir)))
        try:
            emit(f"Inspecting source: {source_info.source_dir}")
            release_files, collect_warnings = collect_release_files(source_info.source_dir)
            if not release_files:
                raise SourceSafetyError("No deployable Linux-side Robot files were found.")
            emit(f"Collected {len(release_files)} deployable file(s).")
            created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            manifest = _manifest_payload(options, version, release_files, created)
            checksums_text = "\n".join(f"{item.sha256}  {item.archive_path}" for item in release_files) + "\n"
            temp_package = temp_dir / final_package.name
            _write_tar_gz(temp_package, manifest, checksums_text, release_files)
            if temp_package.stat().st_size > MAX_ARCHIVE_BYTES:
                raise PackageValidationError(f"Built release exceeds the {MAX_ARCHIVE_BYTES} byte archive limit.")
            inspect_release_archive(temp_package)
            emit("Validated built package with the Robot Update Manager inspector.")
            archive_sha256 = _sha256_file(temp_package)
            temp_manifest = temp_dir / MANIFEST_NAME
            temp_checksums = temp_dir / SHA256SUMS_NAME
            temp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp_checksums.write_text(checksums_text, encoding="utf-8")
            if final_package.exists() and options.overwrite:
                final_package.unlink()
            if final_manifest.exists() and options.overwrite:
                final_manifest.unlink()
            if final_checksums.exists() and options.overwrite:
                final_checksums.unlink()
            shutil.move(str(temp_package), str(final_package))
            shutil.move(str(temp_manifest), str(final_manifest))
            shutil.move(str(temp_checksums), str(final_checksums))
            emit(f"Release written: {final_package}")
            return ReleaseBuildResult(
                package_path=final_package,
                manifest_path=final_manifest,
                checksums_path=final_checksums,
                version=version,
                archive_sha256=archive_sha256,
                content_checksum=str(manifest["package_checksum"]),
                file_count=len(release_files),
                warnings=source_info.warnings + source_info.conflicts + collect_warnings,
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


__all__ = [
    "BUILDER_VERSION",
    "DEFAULT_MINIMUM_BRAIN_VERSION",
    "DEFAULT_PRODUCT",
    "DEFAULT_RELEASE_TYPE",
    "ReleaseBuildOptions",
    "ReleaseBuildResult",
    "ReleaseFile",
    "ReleaseOverwriteError",
    "RobotReleaseBuilder",
    "RobotReleaseBuilderError",
    "SourceInspection",
    "SourceSafetyError",
    "VersionConflictError",
    "VersionDeclaration",
    "collect_release_files",
    "inspect_robot_source",
]
