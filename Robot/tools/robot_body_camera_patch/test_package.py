#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import py_compile
import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "tools"))

import patch_runtime as patch  # noqa: E402


class PackageVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (PACKAGE_ROOT / "manifest.json").read_text(encoding="utf-8")
        )

    def test_manifest_scope_and_payload_hashes(self):
        self.assertEqual(
            {item["path"] for item in self.manifest["files"]},
            {
                "python/main.py",
                "python/web_control.py",
                "python/camera_io.py",
            },
        )
        self.assertFalse(self.manifest["complete_project_included"])
        for item in self.manifest["package_files"]:
            path = PACKAGE_ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                item["sha256"],
            )

    def test_changed_python_compiles(self):
        for item in self.manifest["files"]:
            source = PACKAGE_ROOT / "changed_files" / item["path"]
            compiled = source.with_suffix(source.suffix + ".test.pyc")
            try:
                py_compile.compile(
                    str(source), cfile=str(compiled), doraise=True
                )
            finally:
                compiled.unlink(missing_ok=True)

    def test_camera_endpoints_are_cached_get_only(self):
        main_source = (
            PACKAGE_ROOT / "changed_files/python/main.py"
        ).read_text(encoding="utf-8")
        web_source = (
            PACKAGE_ROOT / "changed_files/python/web_control.py"
        ).read_text(encoding="utf-8")
        safe_main = main_source[
            main_source.index("    def get_cached_camera_frame"):
            main_source.index("    def get_camera_snapshot_jpeg")
        ]
        for value in (
            '"/api/camera/status"',
            '"/api/camera/snapshot"',
            '"/api/camera/stream"',
        ):
            self.assertIn(value, web_source)
        for forbidden in (
            "VideoCapture",
            "capture_jpeg",
            "/dev/video",
            "cv2.",
            ".set(",
            "subprocess",
            "os.open",
        ):
            self.assertNotIn(forbidden, safe_main)
        self.assertIn("memoryview(self.latest_camera_jpeg).tobytes()", safe_main)

    def test_runtime_has_fixed_safe_targets_and_dry_run_default(self):
        source = (PACKAGE_ROOT / "tools/patch_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(patch.TARGET_ROOT, Path("/home/arduino/Arduino_Q_Client_V1"))
        self.assertEqual(patch.BODY_SERVICE, "bx1-web.service")
        self.assertEqual(patch.BODY_PORT, 8088)
        self.assertEqual(patch.BX1_SERVICE, "bx1-os-alpha.service")
        self.assertNotIn("--target-root", source)
        self.assertNotIn("shell=True", source)
        self.assertIn("if not args.install:", source)


if __name__ == "__main__":
    unittest.main()
