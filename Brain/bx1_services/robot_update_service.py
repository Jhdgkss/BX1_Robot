"""Robot update package validation and guarded deployment planning.

Phase 1 keeps the operational logic outside the PyQt window.  The service can
inspect release archives offline, build a dry-run update plan, and exercise SSH
through an injectable transport without requiring robot hardware in tests.
"""
from __future__ import annotations

import hashlib
import json
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol


DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USERNAME = "arduino"
DEFAULT_SERVICE_NAME = "bx1-web.service"
DEFAULT_TARGET_DIRECTORY = "/home/arduino/Arduino_Q_Client_V1"
DEFAULT_PRESERVED_PATHS = (
    "python/config.json",
    "runtime/touchscreen.env",
    "runtime/audio",
)
CALIBRATION_PRESERVE_PREFIXES = (
    "calibration",
    "runtime/calibration",
    "python/calibration",
)
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 512 * 1024 * 1024
MANIFEST_NAME = "release-manifest.json"
SHA256SUMS_NAME = "SHA256SUMS.txt"
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9_.-]+)?$")
FORBIDDEN_NORMAL_UPDATE_SUFFIXES = (".ino", ".hex", ".uf2")
FORBIDDEN_NORMAL_UPDATE_PREFIXES = (
    "Robot/sketch/",
    "sketch/",
    "firmware/",
    "mcu/",
)


class RobotUpdateError(Exception):
    """Base class for robot update errors."""


class ManifestValidationError(RobotUpdateError):
    """Raised when release-manifest.json is incomplete or unsafe."""


class PackageValidationError(RobotUpdateError):
    """Raised when the release archive or checksums are invalid."""


class UnsafeArchiveError(PackageValidationError):
    """Raised when an archive member would escape the extraction root."""


class DeploymentNotImplementedError(RobotUpdateError):
    """Raised when a Phase 1 UI tries to perform unsupported deployment."""


@dataclass(frozen=True)
class RobotConnectionSettings:
    hostname: str
    port: int = DEFAULT_SSH_PORT
    username: str = DEFAULT_SSH_USERNAME
    password: str = ""
    private_key_path: str = ""


@dataclass(frozen=True)
class ManifestFile:
    path: str
    sha256: str
    size: Optional[int] = None


@dataclass(frozen=True)
class ReleaseManifest:
    product: str
    version: str
    release_type: str
    created: str
    service_name: str
    target_directory: str
    minimum_compatible_brain_version: str
    preserved_paths: List[str]
    files: List[ManifestFile]
    package_checksum: str = ""
    builder_version: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PackageInspectionResult:
    archive_path: Path
    manifest: ReleaseManifest
    archive_size: int
    file_count: int
    checksum_count: int
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpdatePlanStep:
    name: str
    detail: str
    requires_connection: bool = True
    destructive: bool = False


@dataclass(frozen=True)
class UpdateRequest:
    package_path: Path
    connection: RobotConnectionSettings
    dry_run: bool = True
    explicit_confirmation: bool = False


@dataclass(frozen=True)
class UpdateProgressEvent:
    level: str
    message: str


class RobotTransport(Protocol):
    def connect(self, settings: RobotConnectionSettings) -> None:
        ...

    def close(self) -> None:
        ...

    def run(self, command: str, *, check: bool = True) -> str:
        ...

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        ...


class ParamikoRobotTransport:
    """Minimal SSH/SFTP transport loaded lazily so Phase 1 adds no dependency."""

    def __init__(self) -> None:
        self._client: Any = None

    def connect(self, settings: RobotConnectionSettings) -> None:
        try:
            import paramiko  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise RobotUpdateError("Paramiko is not installed; SSH connection testing is unavailable.") from exc
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs: Dict[str, Any] = {
            "hostname": settings.hostname,
            "port": int(settings.port),
            "username": settings.username,
            "timeout": 8,
            "look_for_keys": False,
        }
        if settings.private_key_path:
            connect_kwargs["key_filename"] = settings.private_key_path
        if settings.password:
            connect_kwargs["password"] = settings.password
        client.connect(**connect_kwargs)
        self._client = client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def run(self, command: str, *, check: bool = True) -> str:
        if self._client is None:
            raise RobotUpdateError("SSH transport is not connected.")
        _stdin, stdout, stderr = self._client.exec_command(command)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        status = stdout.channel.recv_exit_status()
        if check and status != 0:
            raise RobotUpdateError(f"Remote command failed with exit code {status}: {err.strip()}")
        return out

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        if self._client is None:
            raise RobotUpdateError("SSH transport is not connected.")
        sftp = self._client.open_sftp()
        try:
            sftp.put(str(local_path), remote_path)
        finally:
            sftp.close()


TransportFactory = Callable[[], RobotTransport]
ProgressCallback = Callable[[UpdateProgressEvent], None]


def redact_secret(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "****"
    return f"{text[:1]}***{text[-1:]}"


def _normalise_release_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    if "\x00" in value or not value:
        raise ManifestValidationError("Release paths must be non-empty relative POSIX paths.")
    if value.startswith("/") or value.startswith("~") or re.match(r"^[A-Za-z]:", value):
        raise ManifestValidationError(f"Release path is not relative: {path}")
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ManifestValidationError(f"Release path contains traversal: {path}")
    return "/".join(parts)


def _is_forbidden_mcu_path(path: str) -> bool:
    normalised = _normalise_release_path(path)
    lower = normalised.lower()
    if lower == "robot/sketch/sketch.ino" or lower == "sketch/sketch.ino":
        return True
    return any(lower.startswith(prefix.lower()) for prefix in FORBIDDEN_NORMAL_UPDATE_PREFIXES) or any(
        lower.endswith(suffix) for suffix in FORBIDDEN_NORMAL_UPDATE_SUFFIXES
    )


def _is_preserved_path(path: str, preserved_paths: Iterable[str]) -> bool:
    normalised = _normalise_release_path(path)
    for preserved in preserved_paths:
        preserved_norm = _normalise_release_path(preserved)
        if normalised == preserved_norm or normalised.startswith(f"{preserved_norm}/"):
            return True
    return False


def _validate_sha256(value: str, *, label: str) -> str:
    digest = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ManifestValidationError(f"{label} must be a lowercase SHA256 digest.")
    return digest


def _manifest_files_from_payload(payload: Any) -> List[ManifestFile]:
    files: List[ManifestFile] = []
    if isinstance(payload, dict):
        iterator = payload.items()
        for path, checksum in iterator:
            files.append(ManifestFile(path=_normalise_release_path(str(path)), sha256=_validate_sha256(str(checksum), label=str(path))))
        return files
    if not isinstance(payload, list):
        raise ManifestValidationError("manifest files must be a list or mapping.")
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ManifestValidationError(f"manifest files[{index}] must be an object.")
        path = _normalise_release_path(str(item.get("path") or ""))
        checksum = _validate_sha256(str(item.get("sha256") or item.get("checksum") or ""), label=path)
        size_value = item.get("size")
        size: Optional[int] = None
        if size_value is not None:
            try:
                size = int(size_value)
            except Exception as exc:
                raise ManifestValidationError(f"manifest file size for {path} must be an integer.") from exc
            if size < 0:
                raise ManifestValidationError(f"manifest file size for {path} cannot be negative.")
        files.append(ManifestFile(path=path, sha256=checksum, size=size))
    return files


def validate_manifest(data: Dict[str, Any]) -> ReleaseManifest:
    if not isinstance(data, dict):
        raise ManifestValidationError("release-manifest.json must contain a JSON object.")
    alias_values = dict(data)
    if "created" not in alias_values and "created_timestamp" in alias_values:
        alias_values["created"] = alias_values["created_timestamp"]
    if "minimum_compatible_brain_version" not in alias_values and "minimum_brain_version" in alias_values:
        alias_values["minimum_compatible_brain_version"] = alias_values["minimum_brain_version"]
    if "files" not in alias_values and "included_files" in alias_values:
        alias_values["files"] = alias_values["included_files"]
    required = (
        "product",
        "version",
        "release_type",
        "created",
        "service_name",
        "target_directory",
        "minimum_compatible_brain_version",
        "preserved_paths",
        "files",
    )
    missing = [key for key in required if key not in alias_values or alias_values.get(key) in (None, "")]
    if missing:
        raise ManifestValidationError(f"release-manifest.json is missing: {', '.join(missing)}")
    product = str(alias_values["product"]).strip()
    if "bx1" not in product.lower() or "robot" not in product.lower():
        raise ManifestValidationError("manifest product must identify a BX1 robot release.")
    version = str(alias_values["version"]).strip()
    if not VERSION_RE.match(version):
        raise ManifestValidationError("manifest version must be a dotted version label.")
    release_type = str(alias_values["release_type"]).strip().lower().replace("_", "-")
    if release_type not in ("robot-linux", "linux", "normal", "linux-software"):
        raise ManifestValidationError("manifest release_type must be robot-linux, linux-software, linux or normal.")
    service_name = str(alias_values["service_name"]).strip()
    if service_name != DEFAULT_SERVICE_NAME:
        raise ManifestValidationError(f"manifest service_name must be {DEFAULT_SERVICE_NAME}.")
    target_directory = str(alias_values["target_directory"]).strip()
    if not target_directory.startswith("/") or ".." in target_directory.split("/"):
        raise ManifestValidationError("manifest target_directory must be an absolute safe Linux path.")
    preserved_raw = alias_values.get("preserved_paths")
    if not isinstance(preserved_raw, list) or not preserved_raw:
        raise ManifestValidationError("manifest preserved_paths must be a non-empty list.")
    preserved_paths = [_normalise_release_path(str(item)) for item in preserved_raw]
    missing_preserved = [path for path in DEFAULT_PRESERVED_PATHS if _normalise_release_path(path) not in preserved_paths]
    if missing_preserved:
        raise ManifestValidationError(f"manifest must preserve: {', '.join(missing_preserved)}")
    files = _manifest_files_from_payload(alias_values["files"])
    if not files:
        raise ManifestValidationError("manifest must list at least one file.")
    seen: set[str] = set()
    for item in files:
        if item.path in seen:
            raise ManifestValidationError(f"manifest contains duplicate file: {item.path}")
        seen.add(item.path)
        if _is_forbidden_mcu_path(item.path):
            raise ManifestValidationError(f"normal robot releases cannot include MCU firmware files: {item.path}")
        if _is_preserved_path(item.path, preserved_paths):
            raise ManifestValidationError(f"normal robot releases cannot overwrite preserved path: {item.path}")
    return ReleaseManifest(
        product=product,
        version=version,
        release_type=release_type,
        created=str(alias_values["created"]).strip(),
        service_name=service_name,
        target_directory=target_directory,
        minimum_compatible_brain_version=str(alias_values["minimum_compatible_brain_version"]).strip(),
        preserved_paths=preserved_paths,
        files=files,
        package_checksum=str(alias_values.get("package_checksum") or "").strip(),
        builder_version=str(alias_values.get("builder_version") or "").strip(),
        raw=dict(data),
    )


def release_content_checksum(files: Iterable[ManifestFile]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda file: file.path):
        digest.update(f"{item.path}\0{item.size if item.size is not None else ''}\0{item.sha256}\n".encode("utf-8"))
    return digest.hexdigest()


def parse_sha256sums(text: str) -> Dict[str, str]:
    checksums: Dict[str, str] = {}
    for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([0-9A-Fa-f]{64})\s+\*?(.+)$", line)
        if not match:
            raise PackageValidationError(f"SHA256SUMS.txt line {line_number} is invalid.")
        digest = match.group(1).lower()
        path = _normalise_release_path(match.group(2).strip())
        checksums[path] = digest
    return checksums


def validate_checksums(manifest: ReleaseManifest, checksums: Dict[str, str]) -> None:
    for item in manifest.files:
        actual = checksums.get(item.path)
        if actual is None:
            raise PackageValidationError(f"SHA256SUMS.txt is missing {item.path}.")
        if actual != item.sha256:
            raise PackageValidationError(f"Checksum mismatch for {item.path}.")


def _archive_member_path(member_name: str) -> str:
    try:
        return _normalise_release_path(member_name)
    except ManifestValidationError as exc:
        raise UnsafeArchiveError(str(exc)) from exc


def _archive_rooted_names(tar: tarfile.TarFile) -> Dict[str, tarfile.TarInfo]:
    members: Dict[str, tarfile.TarInfo] = {}
    for member in tar.getmembers():
        safe_name = _archive_member_path(member.name)
        if member.islnk() or member.issym():
            raise UnsafeArchiveError(f"Archive links are not allowed: {safe_name}")
        members[safe_name] = member
    return members


def _read_archive_text(tar: tarfile.TarFile, member: tarfile.TarInfo, *, max_bytes: int) -> str:
    if member.size > max_bytes:
        raise PackageValidationError(f"{member.name} exceeds the allowed size.")
    handle = tar.extractfile(member)
    if handle is None:
        raise PackageValidationError(f"Could not read {member.name}.")
    return handle.read(max_bytes + 1).decode("utf-8")


def _member_sha256(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    handle = tar.extractfile(member)
    if handle is None:
        raise PackageValidationError(f"Could not read {member.name}.")
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def inspect_release_archive(archive_path: Path, *, max_archive_bytes: int = MAX_ARCHIVE_BYTES) -> PackageInspectionResult:
    path = Path(archive_path)
    if not path.name.startswith("bx1-robot-") or not path.name.endswith(".tar.gz"):
        raise PackageValidationError("Robot release archives must be named bx1-robot-<version>.tar.gz.")
    try:
        archive_size = path.stat().st_size
    except OSError as exc:
        raise PackageValidationError(f"Release archive is not readable: {path}") from exc
    if archive_size > max_archive_bytes:
        raise PackageValidationError(f"Release archive exceeds the {max_archive_bytes} byte limit.")
    warnings: List[str] = []
    try:
        with tarfile.open(path, "r:gz") as tar:
            members = _archive_rooted_names(tar)
            if MANIFEST_NAME not in members:
                raise PackageValidationError(f"Release archive must include {MANIFEST_NAME}.")
            if SHA256SUMS_NAME not in members:
                raise PackageValidationError(f"Release archive must include {SHA256SUMS_NAME}.")
            manifest_text = _read_archive_text(tar, members[MANIFEST_NAME], max_bytes=MAX_MANIFEST_BYTES)
            try:
                manifest_data = json.loads(manifest_text)
            except json.JSONDecodeError as exc:
                raise ManifestValidationError(f"{MANIFEST_NAME} is not valid JSON: {exc}") from exc
            manifest = validate_manifest(manifest_data)
            if manifest.package_checksum:
                expected_package_checksum = _validate_sha256(manifest.package_checksum, label="package_checksum")
                actual_package_checksum = release_content_checksum(manifest.files)
                if expected_package_checksum != actual_package_checksum:
                    raise PackageValidationError("Manifest package_checksum does not match included file metadata.")
            sums_text = _read_archive_text(tar, members[SHA256SUMS_NAME], max_bytes=MAX_MANIFEST_BYTES)
            checksums = parse_sha256sums(sums_text)
            validate_checksums(manifest, checksums)
            for item in manifest.files:
                if item.path not in members:
                    raise PackageValidationError(f"Archive is missing manifest file {item.path}.")
                member = members[item.path]
                if not member.isfile():
                    raise PackageValidationError(f"Manifest file is not a regular file: {item.path}")
                if item.size is not None and member.size != item.size:
                    raise PackageValidationError(f"Size mismatch for {item.path}.")
                actual_sha = _member_sha256(tar, member)
                if actual_sha != item.sha256:
                    raise PackageValidationError(f"Archive content checksum mismatch for {item.path}.")
            extra_files = sorted(name for name, member in members.items() if member.isfile() and name not in {MANIFEST_NAME, SHA256SUMS_NAME} and name not in {file.path for file in manifest.files})
            if extra_files:
                warnings.append(f"Archive contains {len(extra_files)} file(s) not listed in the manifest.")
    except tarfile.TarError as exc:
        raise PackageValidationError(f"Release archive is not a valid tar.gz file: {exc}") from exc
    return PackageInspectionResult(
        archive_path=path,
        manifest=manifest,
        archive_size=archive_size,
        file_count=len(manifest.files),
        checksum_count=len(checksums),
        warnings=warnings,
    )


def safe_extract_archive(archive_path: Path, destination: Path) -> List[Path]:
    destination = Path(destination).resolve()
    extracted: List[Path] = []
    with tarfile.open(archive_path, "r:gz") as tar:
        members = _archive_rooted_names(tar)
        for safe_name, member in members.items():
            target = (destination / safe_name).resolve()
            if destination != target and destination not in target.parents:
                raise UnsafeArchiveError(f"Archive member escapes destination: {safe_name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise PackageValidationError(f"Could not extract {safe_name}.")
            target.write_bytes(source.read())
            extracted.append(target)
    return extracted


def build_update_plan(manifest: ReleaseManifest, *, dry_run: bool = True) -> List[UpdatePlanStep]:
    mode = "Dry-run" if dry_run else "Confirmed"
    preserved = ", ".join(manifest.preserved_paths)
    return [
        UpdatePlanStep("Inspect package", f"{mode}: validate manifest and checksums.", requires_connection=False),
        UpdatePlanStep("Read installed version", f"Query {manifest.target_directory}/python/config.json."),
        UpdatePlanStep("Back up current install", f"Create a timestamped backup of {manifest.target_directory}.", destructive=False),
        UpdatePlanStep("Upload staging package", "Upload the release archive to a temporary staging directory."),
        UpdatePlanStep("Verify remote checksums", f"Run sha256sum -c {SHA256SUMS_NAME} in staging."),
        UpdatePlanStep("Stop Robot web service", f"Stop {manifest.service_name}.", destructive=True),
        UpdatePlanStep("Install Linux software", f"Apply files while preserving {preserved}.", destructive=True),
        UpdatePlanStep("Restart Robot web service", f"Restart {manifest.service_name}.", destructive=True),
        UpdatePlanStep("Health check", "Check the Robot web API and service status."),
        UpdatePlanStep("Rollback on failure", "Restore the backup and restart the service if install or health checks fail.", destructive=True),
    ]


class RobotUpdateService:
    def __init__(self, transport_factory: Optional[TransportFactory] = None) -> None:
        self.transport_factory = transport_factory or ParamikoRobotTransport

    def inspect_package(self, archive_path: Path) -> PackageInspectionResult:
        return inspect_release_archive(Path(archive_path))

    def build_plan(self, manifest: ReleaseManifest, *, dry_run: bool = True) -> List[UpdatePlanStep]:
        return build_update_plan(manifest, dry_run=dry_run)

    def test_connection(self, settings: RobotConnectionSettings) -> str:
        if not settings.hostname.strip():
            raise RobotUpdateError("Hostname or IP address is required.")
        transport = self.transport_factory()
        try:
            transport.connect(settings)
            output = transport.run("printf 'BX1_CONNECTION_OK\\n' && uname -a", check=False)
            return output.strip() or "Connection established."
        finally:
            transport.close()

    def read_installed_version(self, settings: RobotConnectionSettings) -> str:
        if not settings.hostname.strip():
            raise RobotUpdateError("Hostname or IP address is required.")
        transport = self.transport_factory()
        try:
            transport.connect(settings)
            config_text = transport.run(f"cat {DEFAULT_TARGET_DIRECTORY}/python/config.json", check=False)
        finally:
            transport.close()
        try:
            data = json.loads(config_text)
        except Exception as exc:
            raise RobotUpdateError("Could not parse installed Robot config.json version.") from exc
        version = str(data.get("version") or data.get("app_version") or "").strip()
        if not version:
            raise RobotUpdateError("Installed Robot config.json does not declare a version.")
        return version

    def run_update(self, request: UpdateRequest, progress: Optional[ProgressCallback] = None) -> List[UpdatePlanStep]:
        inspection = self.inspect_package(request.package_path)
        plan = self.build_plan(inspection.manifest, dry_run=request.dry_run)
        emit = progress or (lambda event: None)
        if request.dry_run:
            for step in plan:
                emit(UpdateProgressEvent("info", f"DRY RUN: {step.name} - {step.detail}"))
            return plan
        if not request.explicit_confirmation:
            raise RobotUpdateError("A confirmed update requires explicit user confirmation.")
        raise DeploymentNotImplementedError(
            "Phase 1 validates packages and prepares the workflow; live deployment is intentionally not enabled yet."
        )


__all__ = [
    "DEFAULT_PRESERVED_PATHS",
    "DEFAULT_SERVICE_NAME",
    "DEFAULT_SSH_PORT",
    "DEFAULT_SSH_USERNAME",
    "DEFAULT_TARGET_DIRECTORY",
    "MAX_ARCHIVE_BYTES",
    "MAX_REQUEST_BYTES",
    "DeploymentNotImplementedError",
    "ManifestValidationError",
    "PackageInspectionResult",
    "PackageValidationError",
    "ReleaseManifest",
    "RobotConnectionSettings",
    "RobotTransport",
    "RobotUpdateError",
    "RobotUpdateService",
    "UnsafeArchiveError",
    "UpdatePlanStep",
    "UpdateProgressEvent",
    "UpdateRequest",
    "build_update_plan",
    "inspect_release_archive",
    "parse_sha256sums",
    "redact_secret",
    "release_content_checksum",
    "safe_extract_archive",
    "validate_checksums",
    "validate_manifest",
]
