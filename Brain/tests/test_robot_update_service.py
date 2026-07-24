from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_services.robot_update_service import (
    DEFAULT_PRESERVED_PATHS,
    DEFAULT_SERVICE_NAME,
    DEFAULT_TARGET_DIRECTORY,
    ManifestValidationError,
    PackageValidationError,
    RobotConnectionSettings,
    RobotUpdateError,
    RobotUpdateService,
    UnsafeArchiveError,
    UpdateRequest,
    inspect_release_archive,
    parse_sha256sums,
    safe_extract_archive,
    validate_manifest,
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def base_manifest(files: list[dict[str, object]]) -> dict[str, object]:
    return {
        "product": "BX1 Robot Linux",
        "version": "10.42",
        "release_type": "robot-linux",
        "created": "2026-07-24T12:00:00Z",
        "service_name": DEFAULT_SERVICE_NAME,
        "target_directory": DEFAULT_TARGET_DIRECTORY,
        "minimum_compatible_brain_version": "2.12.0",
        "preserved_paths": list(DEFAULT_PRESERVED_PATHS) + ["calibration", "runtime/calibration"],
        "files": files,
    }


def write_release_archive(path: Path, files: dict[str, bytes], manifest_overrides: dict[str, object] | None = None) -> dict[str, object]:
    manifest_files = [
        {"path": name, "sha256": sha256_bytes(payload), "size": len(payload)}
        for name, payload in sorted(files.items())
    ]
    manifest = base_manifest(manifest_files)
    if manifest_overrides:
        manifest.update(manifest_overrides)
    sums = "\n".join(f"{item['sha256']}  {item['path']}" for item in manifest_files) + "\n"
    with tarfile.open(path, "w:gz") as tar:
        manifest_payload = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo("release-manifest.json")
        info.size = len(manifest_payload)
        tar.addfile(info, io.BytesIO(manifest_payload))
        sums_payload = sums.encode("utf-8")
        info = tarfile.TarInfo("SHA256SUMS.txt")
        info.size = len(sums_payload)
        tar.addfile(info, io.BytesIO(sums_payload))
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return manifest


class FakeTransport:
    def __init__(self) -> None:
        self.connected = False
        self.commands: list[str] = []
        self.uploads: list[tuple[Path, str]] = []

    def connect(self, settings: RobotConnectionSettings) -> None:
        if settings.password == "fail":
            raise RobotUpdateError("authentication failed")
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def run(self, command: str, *, check: bool = True) -> str:
        self.commands.append(command)
        if command.endswith("/python/config.json"):
            return '{"version": "10.42.1"}'
        return "BX1_CONNECTION_OK\nLinux robot\n"

    def upload_file(self, local_path: Path, remote_path: str) -> None:
        self.uploads.append((local_path, remote_path))


class RobotUpdateServiceTests(unittest.TestCase):
    def test_manifest_validation_accepts_complete_linux_release(self) -> None:
        payload = b"print('robot')\n"
        manifest = base_manifest([{"path": "python/main.py", "sha256": sha256_bytes(payload), "size": len(payload)}])
        parsed = validate_manifest(manifest)
        self.assertEqual(parsed.version, "10.42")
        self.assertEqual(parsed.service_name, DEFAULT_SERVICE_NAME)
        self.assertIn("runtime/audio", parsed.preserved_paths)

    def test_manifest_validation_requires_protected_paths_to_be_preserved(self) -> None:
        payload = b"print('robot')\n"
        manifest = base_manifest([{"path": "python/main.py", "sha256": sha256_bytes(payload)}])
        manifest["preserved_paths"] = ["python/config.json"]
        with self.assertRaisesRegex(ManifestValidationError, "runtime/touchscreen.env"):
            validate_manifest(manifest)

    def test_manifest_validation_rejects_protected_path_payloads(self) -> None:
        payload = b'{"version":"10.42"}'
        manifest = base_manifest([{"path": "python/config.json", "sha256": sha256_bytes(payload)}])
        with self.assertRaisesRegex(ManifestValidationError, "preserved path"):
            validate_manifest(manifest)

    def test_mcu_files_are_rejected_from_normal_robot_releases(self) -> None:
        payload = b"void setup() {}\n"
        manifest = base_manifest([{"path": "Robot/sketch/sketch.ino", "sha256": sha256_bytes(payload)}])
        with self.assertRaisesRegex(ManifestValidationError, "MCU firmware"):
            validate_manifest(manifest)

    def test_checksum_validation_catches_mismatches(self) -> None:
        payload = b"print('robot')\n"
        manifest = validate_manifest(base_manifest([{"path": "python/main.py", "sha256": sha256_bytes(payload)}]))
        checksums = parse_sha256sums(f"{'0' * 64}  python/main.py\n")
        with self.assertRaisesRegex(PackageValidationError, "Checksum mismatch"):
            from bx1_services.robot_update_service import validate_checksums

            validate_checksums(manifest, checksums)

    def test_archive_inspection_validates_manifest_checksums_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bx1-robot-10.42.tar.gz"
            write_release_archive(archive, {"python/main.py": b"print('robot')\n", "python/web_control.py": b"# web\n"})
            result = inspect_release_archive(archive)
            self.assertEqual(result.manifest.version, "10.42")
            self.assertEqual(result.file_count, 2)
            self.assertEqual(result.checksum_count, 2)

    def test_safe_archive_extraction_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bx1-robot-10.42.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                payload = b"escape"
                info = tarfile.TarInfo("../escape.txt")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
            with self.assertRaises(UnsafeArchiveError):
                safe_extract_archive(archive, Path(tmp) / "out")

    def test_safe_archive_extraction_keeps_files_inside_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bx1-robot-10.42.tar.gz"
            write_release_archive(archive, {"python/main.py": b"print('robot')\n"})
            out = Path(tmp) / "out"
            extracted = safe_extract_archive(archive, out)
            self.assertTrue((out / "python" / "main.py").exists())
            self.assertTrue(all(out.resolve() in path.resolve().parents for path in extracted))

    def test_mocked_connection_uses_transport_without_hardware(self) -> None:
        transports: list[FakeTransport] = []

        def factory() -> FakeTransport:
            transport = FakeTransport()
            transports.append(transport)
            return transport

        service = RobotUpdateService(transport_factory=factory)
        output = service.test_connection(RobotConnectionSettings(hostname="192.0.2.10", password="session-only"))
        self.assertIn("BX1_CONNECTION_OK", output)
        self.assertEqual(transports[0].commands[0], "printf 'BX1_CONNECTION_OK\\n' && uname -a")

    def test_installed_version_is_read_through_mocked_transport(self) -> None:
        service = RobotUpdateService(transport_factory=FakeTransport)
        version = service.read_installed_version(RobotConnectionSettings(hostname="192.0.2.10"))
        self.assertEqual(version, "10.42.1")

    def test_dry_run_update_builds_plan_without_live_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bx1-robot-10.42.tar.gz"
            write_release_archive(archive, {"python/main.py": b"print('robot')\n"})
            events: list[str] = []
            service = RobotUpdateService(transport_factory=FakeTransport)
            plan = service.run_update(
                UpdateRequest(
                    package_path=archive,
                    connection=RobotConnectionSettings(hostname="192.0.2.10"),
                    dry_run=True,
                ),
                progress=lambda event: events.append(event.message),
            )
            self.assertGreaterEqual(len(plan), 8)
            self.assertTrue(all(message.startswith("DRY RUN:") for message in events))


if __name__ == "__main__":
    unittest.main()
