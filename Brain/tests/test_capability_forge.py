from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_capabilities.manager import CapabilityManager
from bx1_capabilities.manifest import validate_manifest_dict, validate_ui_schema
from bx1_capabilities.models import CapabilitySecurityError, CapabilityValidationError
from bx1_capabilities.package_io import import_zip_to_folder
from bx1_capabilities.scanner import scan_capability_source, scan_text_for_secrets


class CapabilityForgeTests(unittest.TestCase):
    def test_manifest_validation_and_permission_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_addon_template()
            data = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            data["permissions"] = []
            manifest = validate_manifest_dict(data)
            self.assertEqual(manifest.permissions, ["NONE"])

    def test_missing_manifest_fields_and_invalid_id(self) -> None:
        with self.assertRaises(CapabilityValidationError):
            validate_manifest_dict({"capability_id": "bad"})
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_addon_template("workshop_greeting")
            data = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            data["capability_id"] = "Bad-ID"
            with self.assertRaises(CapabilityValidationError):
                validate_manifest_dict(data)

    def test_prohibited_import_eval_exec_and_secret_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "capability.py"
            path.write_text("import subprocess\nx = eval('1')\n", encoding="utf-8")
            with self.assertRaises(CapabilitySecurityError):
                scan_capability_source(path)
            self.assertTrue(scan_text_for_secrets("api_key='1234567890abcdef'"))

    def test_path_traversal_and_duplicate_zip_entries_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../evil.txt", "bad")
            with self.assertRaises(CapabilityValidationError):
                import_zip_to_folder(archive, Path(tmp) / "out")
            duplicate = Path(tmp) / "dup.zip"
            with zipfile.ZipFile(duplicate, "w") as zf:
                zf.writestr("cap/manifest.json", "{}")
                zf.writestr("cap/manifest.json", "{}")
            with self.assertRaises(CapabilityValidationError):
                import_zip_to_folder(duplicate, Path(tmp) / "out2")

    def test_broad_trigger_and_network_domain_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_addon_template()
            data = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            data["trigger_phrases"] = ["hi"]
            with self.assertRaises(CapabilityValidationError):
                validate_manifest_dict(data)
            data["trigger_phrases"] = ["give me a workshop greeting"]
            data["allowed_network_domains"] = ["https://example.com/path"]
            with self.assertRaises(CapabilityValidationError):
                validate_manifest_dict(data)

    def test_safe_ui_schema_validation(self) -> None:
        self.assertEqual(validate_ui_schema({"controls": [{"type": "text", "id": "x"}]})["controls"][0]["type"], "text")
        with self.assertRaises(CapabilityValidationError):
            validate_ui_schema({"controls": [{"type": "custom_pyqt", "code": "print(1)"}]})

    def test_user_addon_template_install_execute_disable_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_addon_template()
            manager.validate_package(package)
            manager.run_tests(package)
            record = manager.install(package, approved=True)
            self.assertEqual(record.manifest.capability_id, "workshop_greeting")
            result = manager.execute_installed("workshop_greeting", "greet", {"name": "John"})
            self.assertTrue(result.ok)
            self.assertIn("John", result.message)
            self.assertIsNotNone(manager.match_trigger("give me a workshop greeting"))
            manager.disable("workshop_greeting")
            self.assertIsNone(manager.match_trigger("give me a workshop greeting"))
            disabled = manager.execute_installed("workshop_greeting", "greet")
            self.assertFalse(disabled.ok)
            manager.enable("workshop_greeting")
            manager.remove("workshop_greeting")
            with self.assertRaises(FileNotFoundError):
                manager.get_record("workshop_greeting")

    def test_confirmation_timeout_and_worker_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_support_demo_package()
            manager.install(package, approved=True)
            blocked = manager.execute_installed("support_mention_responder", "approve_send")
            self.assertFalse(blocked.ok)
            self.assertTrue(blocked.requires_confirmation)
            cap = package / "capability.py"
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            cap.write_text("def get_capability_metadata(): return {}\ndef validate_settings(settings): return {'ok': True}\ndef execute(action, parameters, context):\n    raise RuntimeError('boom')\ndef shutdown(): return None\n", encoding="utf-8")
            (package / "tests.py").write_text("import capability\nassert capability.get_capability_metadata() == {}\n", encoding="utf-8")
            manifest["checksum"] = __import__("bx1_capabilities.manifest", fromlist=["sha256_file"]).sha256_file(cap)
            (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            manager.install(package, approved=True)
            failed = manager.execute_installed("support_mention_responder", "scan_mentions")
            self.assertFalse(failed.ok)
            self.assertEqual(failed.error, "worker_failed")

    def test_failed_tests_block_install_and_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_addon_template()
            (package / "tests.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
            with self.assertRaises(CapabilityValidationError):
                manager.install(package, approved=True)
            quarantine = manager.quarantine(package, "test failure")
            self.assertTrue((quarantine / "QUARANTINE_REASON.txt").exists())

    def test_update_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_addon_template()
            manager.install(package, approved=True)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            manifest["version"] = "1.1.0"
            (package / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            manager.install(package, approved=True)
            self.assertEqual(manager.get_record("workshop_greeting").manifest.version, "1.1.0")
            manager.rollback("workshop_greeting")
            self.assertEqual(manager.get_record("workshop_greeting").manifest.version, "1.0.0")

    def test_support_mention_responder_package_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.create_support_demo_package()
            manager.validate_package(package)
            manager.run_tests(package)
            scan = manager.mock_execute(package, "scan_mentions")
            self.assertTrue(scan.ok)
            record = manager.install(package, approved=True)
            self.assertEqual(record.manifest.capability_id, "support_mention_responder")
            self.assertIsNotNone(manager.match_trigger("@John_Support please help"))
            manager.disable("support_mention_responder")
            self.assertIsNone(manager.match_trigger("@John_Support please help"))
            manager.enable("support_mention_responder")
            manager.remove("support_mention_responder")
            with self.assertRaises(FileNotFoundError):
                manager.get_record("support_mention_responder")

    def test_export_and_import_user_addon_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp) / "a")
            package = manager.create_addon_template()
            manager.install(package, approved=True)
            archive = manager.export("workshop_greeting", Path(tmp))
            other = CapabilityManager(Path(tmp) / "b")
            imported = other.import_addon(archive)
            other.validate_package(imported)
            self.assertEqual((imported / "manifest.json").exists(), True)


if __name__ == "__main__":
    unittest.main()
