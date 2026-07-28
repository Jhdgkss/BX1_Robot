#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent


def load_tool(name: str, filename: str):
    path = ROOT / "tools" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load_tool("bx1_release_builder_test", "build_bx1_release.py")
qualification = load_tool(
    "bx1_qualification_test",
    "qualify_bx1_alpha.py",
)


def valid_snapshot():
    required = [
        "events",
        "capabilities",
        "logging",
        "scheduler",
        "led",
        "drive",
        "range",
        "battery",
        "power",
        "diagnostics",
        "health",
        "communication",
        "runtime_hardware",
    ]
    return {
        "ok": True,
        "bx1_os": {
            "milestone": "BX1 OS Alpha",
            "startup_validated": True,
            "startup": {
                "schema": "bx1.runtime.startup.v1",
                "success": True,
                "required_services": required,
                "registered_services": required,
            },
            "service_registry": {
                "state": "READY",
                "registered_count": len(required),
                "running_count": len(required),
            },
            "scheduler": {"state": "READY", "tick_count": 4},
            "events": {"state": "READY"},
            "diagnostics": {"state": "READY"},
            "communication": {
                "state": "READY",
                "transport": "in_memory",
            },
            "health": {"state": "READY", "check_count": 2},
            "runtime_hardware": {"state": "READY"},
        },
        "state": {
            "bridge_available": True,
            "bridge_mode": "router_rpc",
        },
        "brain": {"base_url": "http://brain.invalid:8765"},
    }


class ReleaseBuilderTests(unittest.TestCase):
    def test_package_is_hashed_safe_and_excludes_user_data_and_firmware(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            archive, sidecar, manifest = builder.build_release(
                REPOSITORY,
                output,
                timestamp="20260728_120000",
            )
            self.assertTrue(archive.is_file())
            self.assertTrue(sidecar.is_file())
            self.assertFalse(manifest["firmware_included"])
            paths = {item["path"] for item in manifest["files"]}
            self.assertIn("python/main.py", paths)
            self.assertIn("python/bx1.py", paths)
            self.assertIn("tools/deploy_bx1_os.sh", paths)
            self.assertIn("tools/rollback_bx1_os.sh", paths)
            self.assertNotIn("python/config.json", paths)
            self.assertFalse(any(path.startswith("sketch/") for path in paths))
            for path in paths:
                relative = PurePosixPath(path)
                self.assertFalse(relative.is_absolute())
                self.assertNotIn("..", relative.parts)

            extracted = Path(temporary) / "extracted"
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted)
            package_root = extracted / manifest["release_id"]
            for relative in (
                "deploy_bx1_os.sh",
                "rollback_bx1_os.sh",
                "payload/tools/run_robot_body.sh",
                "payload/tools/check_web_health.sh",
            ):
                data = (package_root / relative).read_bytes()
                self.assertNotIn(b"\r\n", data)
            verified = qualification.verify_release(package_root)
            self.assertTrue(verified["valid"])
            self.assertEqual(
                verified["checked_files"],
                len(manifest["files"]),
            )

    def test_tampered_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive, _, manifest = builder.build_release(
                REPOSITORY,
                Path(temporary) / "output",
                timestamp="20260728_120001",
            )
            extracted = Path(temporary) / "extracted"
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted)
            package_root = extracted / manifest["release_id"]
            target = package_root / "payload" / "python" / "bx1.py"
            target.write_text("tampered\n", encoding="utf-8")
            report = qualification.verify_release(package_root)
            self.assertFalse(report["valid"])
            self.assertTrue(
                any("hash mismatch" in item for item in report["failures"])
            )


class QualificationTests(unittest.TestCase):
    def test_complete_alpha_snapshot_passes_without_physical_actions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "python").mkdir()
            (root / "python" / "config.json").write_text(
                json.dumps(
                    {
                        "brain_base_url": "http://brain.invalid:8765",
                        "api_key": "preserved",
                    }
                ),
                encoding="utf-8",
            )
            report = qualification.qualify(
                install_root=root,
                service_name="bx1-web.service",
                status_url="http://127.0.0.1:8088/api/status",
                snapshot=valid_snapshot(),
                skip_systemd=True,
                allow_brain_offline=True,
            )
            self.assertTrue(report["passed"])
            self.assertFalse(report["hardware_actions_requested"])
            self.assertEqual(report["failed_checks"], [])
            self.assertEqual(
                {item["name"] for item in report["checks"]},
                {
                    "Bootstrap",
                    "Service Registry",
                    "Scheduler",
                    "Event Bus",
                    "Diagnostics",
                    "Communication",
                    "Health Monitor",
                    "Hardware Bridge",
                    "Brain Connection",
                    "Web Interface",
                    "Existing Runtime",
                },
            )

    def test_failed_bootstrap_and_hardware_are_reported(self):
        snapshot = valid_snapshot()
        snapshot["bx1_os"]["startup_validated"] = False
        snapshot["state"]["bridge_available"] = False
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "python").mkdir()
            (root / "python" / "config.json").write_text(
                "{}",
                encoding="utf-8",
            )
            report = qualification.qualify(
                install_root=root,
                service_name="bx1-web.service",
                status_url="memory://status",
                snapshot=snapshot,
                skip_systemd=True,
                allow_brain_offline=True,
            )
        self.assertFalse(report["passed"])
        self.assertIn("Bootstrap", report["failed_checks"])
        self.assertIn("Hardware Bridge", report["failed_checks"])


class TransactionSafetyTests(unittest.TestCase):
    def test_deployer_backs_up_before_stopping_or_copying(self):
        source = (ROOT / "tools" / "deploy_bx1_os.sh").read_text(
            encoding="utf-8"
        )
        backup_ready = source.index("BACKUP_COMPLETE=1")
        stop = source.index('systemctl stop "$SERVICE_NAME"')
        install = source.index(
            'tar -cf - -C "$RELEASE_ROOT/payload" .'
        )
        self.assertLess(backup_ready, stop)
        self.assertLess(stop, install)
        self.assertIn("rollback_on_failure", source)
        self.assertIn("CONFIG_SHA_AFTER", source)
        self.assertIn("--verify-release", source)

    def test_rollback_requires_complete_backup_and_exact_manifest(self):
        source = (ROOT / "tools" / "rollback_bx1_os.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("deployment_manifest.json", source)
        self.assertIn("deployed_release_manifest.json", source)
        self.assertIn("unsafe deployed path", source)
        self.assertIn("unsafe backup archive member", source)
        self.assertIn("CONFIG_SHA_EXPECTED", source)
        self.assertIn("partial_deployment_remaining", source)

    def test_service_unit_runs_existing_launcher_as_alpha(self):
        service = (ROOT / "service" / "bx1-web.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Description=BX1 OS Alpha Robot Body", service)
        self.assertIn("Environment=BX1_OS_MILESTONE=ALPHA", service)
        self.assertIn("tools/run_robot_body.sh", service)
        self.assertIn("WantedBy=multi-user.target", service)


if __name__ == "__main__":
    unittest.main()
