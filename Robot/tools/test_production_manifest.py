#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().with_name("production_manifest.py")
SPEC = importlib.util.spec_from_file_location("production_manifest", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load production_manifest.py")
production_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_manifest)


class ProductionManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "python").mkdir()
        (self.root / "tools").mkdir()
        (self.root / "VERSION.txt").write_text("10.39\n", encoding="utf-8")
        (self.root / "python" / "main.py").write_text(
            "print('body')\n", encoding="utf-8"
        )
        (self.root / "tools" / "run_robot_body.sh").write_text(
            "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
        )
        (self.root / "python" / "config.json").write_text(
            '{"api_key": "must-not-appear"}\n', encoding="utf-8"
        )
        (self.root / "python" / "robot_profile.json").write_text(
            '{"private": true}\n', encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def capture(self):
        return production_manifest.capture_manifest(
            self.root,
            expected_version="10.39",
        )

    def test_capture_excludes_private_files_and_normalizes_modes(self) -> None:
        manifest = self.capture()
        entries = {item["path"]: item for item in manifest["files"]}
        self.assertNotIn("python/config.json", entries)
        self.assertNotIn("python/robot_profile.json", entries)
        self.assertEqual(manifest["private_files_excluded"], 2)
        self.assertEqual(entries["python/main.py"]["mode"], "0644")
        self.assertEqual(entries["tools/run_robot_body.sh"]["mode"], "0755")

    def test_capture_normalizes_text_line_endings(self) -> None:
        path = self.root / "app.yaml"
        path.write_bytes(b"name: bx1\r\nversion: 10.39\r\n")
        windows = self.capture()
        path.write_bytes(b"name: bx1\nversion: 10.39\n")
        linux = self.capture()
        windows_entry = next(
            item for item in windows["files"] if item["path"] == "app.yaml"
        )
        linux_entry = next(
            item for item in linux["files"] if item["path"] == "app.yaml"
        )
        self.assertEqual(windows_entry["sha256"], linux_entry["sha256"])
        self.assertEqual(windows_entry["size"], linux_entry["size"])

    def test_known_non_runtime_paths_are_not_active_support(self) -> None:
        self.assertEqual(
            production_manifest.classify_path("RUN_BX1_BRAIN_V1_7_3_UPDATE.cmd"),
            "historical",
        )
        self.assertEqual(
            production_manifest.classify_path(
                "tools/robot_body_camera_patch/patch_runtime.py"
            ),
            "staged",
        )
        self.assertEqual(
            production_manifest.classify_path("tools/audio_noise_diagnostic.py"),
            "os_source",
        )

    def test_compare_reports_changed_missing_and_extra_paths(self) -> None:
        expected = self.capture()
        (self.root / "python" / "main.py").write_text(
            "print('changed')\n", encoding="utf-8"
        )
        (self.root / "tools" / "run_robot_body.sh").unlink()
        (self.root / "python" / "camera_io.py").write_text(
            "FRAME = None\n", encoding="utf-8"
        )
        actual = self.capture()
        report = production_manifest.compare_manifests(
            expected,
            actual,
            classes={"active", "support"},
        )
        self.assertFalse(report["match"])
        self.assertEqual(
            [item["path"] for item in report["changed"]],
            ["python/main.py"],
        )
        self.assertEqual(report["missing"], ["tools/run_robot_body.sh"])
        self.assertEqual(report["extra"], ["python/camera_io.py"])

    def test_os_source_is_outside_body_comparison(self) -> None:
        expected = self.capture()
        core = self.root / "python" / "bx1_core"
        core.mkdir()
        (core / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        actual = self.capture()
        report = production_manifest.compare_manifests(
            expected,
            actual,
            classes={"active", "support"},
        )
        self.assertTrue(report["match"])

    def test_version_mismatch_is_rejected_during_capture(self) -> None:
        with self.assertRaises(production_manifest.ManifestError):
            production_manifest.capture_manifest(
                self.root,
                expected_version="10.42",
            )


if __name__ == "__main__":
    unittest.main()
