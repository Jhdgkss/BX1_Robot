from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from bx1_capabilities.manifest import load_manifest, validate_manifest_dict
from bx1_capabilities.models import CapabilityError, CapabilityRecord, CapabilityRunResult, CapabilityValidationError
from bx1_capabilities.package_io import export_folder_to_zip, import_zip_to_folder, validate_package_folder
from bx1_capabilities.runner import CapabilityRunner
from bx1_capabilities.scanner import scan_capability_source
from bx1_capabilities.templates import create_greeting_template, create_support_responder_package


FOLDER_README = """# BX1 Runtime Capabilities

These folders are runtime data and should not normally be committed to Git.

- `workshop/`: generated or imported packages under review.
- `installed/`: approved enabled capability packages.
- `disabled/`: installed packages that are not active.
- `archive/`: previous versions and removed packages.
- `quarantine/`: rejected or unsafe packages retained for review.

This is controlled isolation, not a complete operating-system security sandbox.
Capabilities run in a separate worker process with limited environment, timeout,
JSON input/output and no MainWindow object.
"""


class CapabilityManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.workshop_dir = self.root / "workshop"
        self.installed_dir = self.root / "installed"
        self.disabled_dir = self.root / "disabled"
        self.archive_dir = self.root / "archive"
        self.quarantine_dir = self.root / "quarantine"
        self.runner = CapabilityRunner()
        for folder in (self.workshop_dir, self.installed_dir, self.disabled_dir, self.archive_dir, self.quarantine_dir):
            folder.mkdir(parents=True, exist_ok=True)
        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text(FOLDER_README, encoding="utf-8")

    def create_addon_template(self, capability_id: str = "workshop_greeting") -> Path:
        return create_greeting_template(self.workshop_dir / capability_id, capability_id)

    def create_support_demo_package(self) -> Path:
        return create_support_responder_package(self.workshop_dir / "support_mention_responder")

    def import_addon(self, source: Path) -> Path:
        source = Path(source)
        if source.is_file() and source.suffix.lower() == ".zip":
            return import_zip_to_folder(source, self.workshop_dir)
        validate_package_folder(source)
        manifest = load_manifest(source / "manifest.json")
        target = self.workshop_dir / manifest.capability_id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        validate_package_folder(target)
        return target

    def validate_package(self, package_dir: Path) -> Dict[str, Any]:
        package_dir = Path(package_dir)
        validate_package_folder(package_dir)
        manifest = load_manifest(package_dir / "manifest.json")
        actual_checksum = __import__("bx1_capabilities.manifest", fromlist=["sha256_file"]).sha256_file(package_dir / "capability.py")
        if manifest.checksum and manifest.checksum != actual_checksum:
            raise CapabilityValidationError("capability.py checksum does not match manifest.")
        scan_capability_source(package_dir / "capability.py")
        return {"ok": True, "manifest": manifest, "checksum": actual_checksum}

    def run_tests(self, package_dir: Path) -> Dict[str, Any]:
        self.validate_package(package_dir)
        proc = subprocess.run(
            [sys.executable, "-I", "-c", "import runpy, sys; sys.path.insert(0, '.'); runpy.run_path('tests.py', run_name='__main__')"],
            cwd=str(package_dir),
            capture_output=True,
            text=True,
            timeout=15,
            env={"PYTHONIOENCODING": "utf-8", "BX1_CAPABILITY_MODE": "test"},
        )
        if proc.returncode != 0:
            raise CapabilityValidationError("Capability tests failed:\n" + proc.stdout + proc.stderr)
        return {"ok": True, "stdout": proc.stdout, "stderr": proc.stderr}

    def mock_execute(self, package_dir: Path, action: str, parameters: Optional[Dict[str, Any]] = None, settings: Optional[Dict[str, Any]] = None, *, confirmed: bool = False) -> CapabilityRunResult:
        manifest = load_manifest(Path(package_dir) / "manifest.json")
        return self.runner.run(package_dir, action, parameters or {}, {"mock_mode": True, "settings": settings or manifest.settings_schema}, settings or manifest.settings_schema, confirmed=confirmed)

    def install(self, package_dir: Path, *, approved: bool = False) -> CapabilityRecord:
        if not approved:
            raise CapabilityValidationError("Installation requires explicit approval.")
        self.validate_package(package_dir)
        self.run_tests(package_dir)
        manifest = load_manifest(Path(package_dir) / "manifest.json")
        target = self.installed_dir / manifest.capability_id
        if target.exists():
            archive_target = self.archive_dir / manifest.capability_id / f"{int(time.time())}_{manifest.version}"
            archive_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(archive_target))
        if (self.disabled_dir / manifest.capability_id).exists():
            shutil.rmtree(self.disabled_dir / manifest.capability_id)
        shutil.copytree(package_dir, target)
        return CapabilityRecord(manifest, str(target), "installed")

    def list_records(self) -> List[CapabilityRecord]:
        records: List[CapabilityRecord] = []
        for state, folder in (("installed", self.installed_dir), ("disabled", self.disabled_dir), ("quarantine", self.quarantine_dir)):
            for child in sorted(folder.iterdir()) if folder.exists() else []:
                if child.is_dir() and (child / "manifest.json").exists():
                    try:
                        records.append(CapabilityRecord(load_manifest(child / "manifest.json"), str(child), state))
                    except Exception:
                        pass
        return records

    def get_record(self, capability_id: str) -> CapabilityRecord:
        for record in self.list_records():
            if record.manifest.capability_id == capability_id:
                return record
        raise FileNotFoundError(f"Capability not found: {capability_id}")

    def disable(self, capability_id: str) -> None:
        source = self.installed_dir / capability_id
        if not source.exists():
            return
        target = self.disabled_dir / capability_id
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))

    def enable(self, capability_id: str) -> None:
        source = self.disabled_dir / capability_id
        if not source.exists():
            return
        target = self.installed_dir / capability_id
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))

    def remove(self, capability_id: str) -> None:
        for folder in (self.installed_dir, self.disabled_dir):
            source = folder / capability_id
            if source.exists():
                target = self.archive_dir / capability_id / f"removed_{int(time.time())}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                return

    def rollback(self, capability_id: str) -> CapabilityRecord:
        archive_root = self.archive_dir / capability_id
        candidates = sorted([item for item in archive_root.iterdir() if item.is_dir()]) if archive_root.exists() else []
        if not candidates:
            raise FileNotFoundError(f"No archived version available for {capability_id}.")
        latest = candidates[-1]
        current = self.installed_dir / capability_id
        if current.exists():
            rollback_archive = archive_root / f"rollback_replaced_{int(time.time())}"
            shutil.move(str(current), str(rollback_archive))
        shutil.copytree(latest, current)
        return CapabilityRecord(load_manifest(current / "manifest.json"), str(current), "installed")

    def quarantine(self, package_dir: Path, reason: str = "") -> Path:
        package_dir = Path(package_dir)
        target = self.quarantine_dir / f"{package_dir.name}_{int(time.time())}"
        shutil.copytree(package_dir, target)
        (target / "QUARANTINE_REASON.txt").write_text(str(reason or "Rejected by safety validation."), encoding="utf-8")
        return target

    def execute_installed(self, capability_id: str, action: str, parameters: Optional[Dict[str, Any]] = None, *, confirmed: bool = False) -> CapabilityRunResult:
        record = self.get_record(capability_id)
        if record.state != "installed":
            return CapabilityRunResult(False, capability_id, action, error="disabled", message="Capability is not enabled.")
        return self.mock_execute(Path(record.path), action, parameters or {}, record.manifest.settings_schema, confirmed=confirmed)

    def match_trigger(self, text: str) -> Optional[CapabilityRecord]:
        query = " ".join(str(text or "").lower().split())
        for record in self.list_records():
            if record.state != "installed":
                continue
            for phrase in record.manifest.trigger_phrases:
                trigger = " ".join(phrase.lower().split())
                if query == trigger or (trigger.startswith("@") and trigger in query):
                    return record
        return None

    def export(self, capability_id: str, output_dir: Path) -> Path:
        record = self.get_record(capability_id)
        name = f"bx1-capability-{record.manifest.capability_id}-{record.manifest.version}.zip"
        return export_folder_to_zip(Path(record.path), Path(output_dir) / name)
