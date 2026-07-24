from __future__ import annotations

import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_services.robot_release_builder import (
    ReleaseBuildOptions,
    ReleaseOverwriteError,
    RobotReleaseBuilder,
    SourceSafetyError,
    VersionConflictError,
    collect_release_files,
    inspect_robot_source,
)
from bx1_services.robot_update_service import inspect_release_archive


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_source(root: Path, *, app_version: str = "10.42", python_version: str = "10.42") -> Path:
    source = root / "robot_source"
    write_text(source / "app.yaml", f"name: bx1-web\nversion: {app_version}\n")
    write_text(source / "main.py", f'ROBOT_VERSION = "{python_version}"\n')
    write_text(source / "python" / "main.py", f'APP_VERSION = "{python_version}"\nprint("robot")\n')
    write_text(source / "python" / "web_control.py", f'VERSION = "{python_version}"\n')
    write_text(source / "service" / "bx1-web.service", "[Service]\nExecStart=/usr/bin/python3 main.py\n")
    return source


class RobotReleaseBuilderTests(unittest.TestCase):
    def test_correct_manifest_generation_and_phase1_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            result = RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"), progress=lambda _msg: None)
            self.assertTrue(result.package_path.exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["product"], "BX1 Robot")
            self.assertEqual(manifest["version"], "10.42")
            self.assertEqual(manifest["release_type"], "linux-software")
            self.assertEqual(manifest["service_name"], "bx1-web.service")
            self.assertEqual(manifest["target_directory"], "/home/arduino/Arduino_Q_Client_V1")
            self.assertIn("created_timestamp", manifest)
            self.assertIn("minimum_brain_version", manifest)
            self.assertIn("included_files", manifest)
            self.assertIn("package_checksum", manifest)
            self.assertIn("builder_version", manifest)
            inspection = inspect_release_archive(result.package_path)
            self.assertEqual(inspection.manifest.version, "10.42")

    def test_sha256sums_match_included_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            result = RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            sums = result.checksums_path.read_text(encoding="utf-8").splitlines()
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            expected = {f"{item['sha256']}  {item['path']}" for item in manifest["included_files"]}
            self.assertEqual(set(sums), expected)

    def test_package_checksum_is_validated_by_inspector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            result = RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            inspection = inspect_release_archive(result.package_path)
            self.assertEqual(inspection.manifest.package_checksum, result.content_checksum)

    def test_deterministic_file_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            write_text(source / "python" / "zeta.py", "z = 1\n")
            write_text(source / "python" / "alpha.py", "a = 1\n")
            files, _warnings = collect_release_files(source)
            paths = [item.archive_path for item in files]
            self.assertEqual(paths, sorted(paths))

    def test_excludes_protected_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            write_text(source / "python" / "config.json", '{"version": "10.42.1"}')
            write_text(source / "runtime" / "touchscreen.env", "DISPLAY=:0\n")
            write_text(source / "runtime" / "audio" / "custom.wav", "audio")
            result = RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["included_files"]}
            self.assertNotIn("python/config.json", paths)
            self.assertNotIn("runtime/touchscreen.env", paths)
            self.assertNotIn("runtime/audio/custom.wav", paths)

    def test_mcu_firmware_is_rejected_from_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            write_text(source / "sketch" / "sketch.ino", "void setup() {}\n")
            result = RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["included_files"]}
            self.assertNotIn("sketch/sketch.ino", paths)
            self.assertTrue(any("MCU firmware" in warning for warning in result.warnings))

    def test_historical_payloads_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            write_text(source / "payload" / "python" / "main.py", "old")
            write_text(source / "update_files" / "main.py", "old")
            write_text(source / "files" / "main.py", "old")
            result = RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            paths = {item["path"] for item in manifest["included_files"]}
            self.assertFalse(any(path.startswith(("payload/", "update_files/", "files/")) for path in paths))

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(SourceSafetyError):
            collect_release_files(Path("../outside"))

    def test_escaping_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            link = source / "python" / "escape.txt"
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symlinks are unavailable: {exc}")
            with self.assertRaises(SourceSafetyError):
                collect_release_files(source)

    def test_conflicting_version_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_source(Path(tmp), app_version="10.42", python_version="10.39")
            info = inspect_robot_source(source)
            self.assertTrue(info.conflicts)
            with self.assertRaises(VersionConflictError):
                RobotReleaseBuilder().build(ReleaseBuildOptions(source_dir=source, output_dir=Path(tmp) / "out"))

    def test_existing_output_overwrite_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            builder = RobotReleaseBuilder()
            builder.build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            with self.assertRaises(ReleaseOverwriteError):
                builder.build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))

    def test_cleanup_after_failed_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            write_text(source / "python" / "config.json", '{"version": "10.42.1"}')
            builder = RobotReleaseBuilder()
            original_collect = __import__("bx1_services.robot_release_builder", fromlist=["collect_release_files"]).collect_release_files
            try:
                import bx1_services.robot_release_builder as module

                def failing_collect(*_args, **_kwargs):
                    raise SourceSafetyError("forced failure")

                module.collect_release_files = failing_collect
                with self.assertRaises(SourceSafetyError):
                    builder.build(ReleaseBuildOptions(source_dir=source, output_dir=root / "out"))
            finally:
                import bx1_services.robot_release_builder as module

                module.collect_release_files = original_collect
            leftovers = list((root / "out").glob("bx1_robot_release_*")) if (root / "out").exists() else []
            self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
