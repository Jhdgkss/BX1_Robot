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
from bx1_capabilities.models import CapabilityAction, CapabilityError, CapabilityManifest, CapabilityRecord, CapabilityRunResult, CapabilityValidationError
from bx1_capabilities.reminder_clock import ReminderClockService
from bx1_capabilities.package_io import export_folder_to_zip, import_zip_to_folder, validate_package_folder
from bx1_capabilities.runner import CapabilityRunner
from bx1_capabilities.scanner import scan_capability_source
from bx1_capabilities.templates import create_greeting_template, create_proposal_package, create_support_responder_package
from bx1_capabilities.design import CapabilityProposal


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
    def __init__(
        self, root: Path, *, reminder_service: Optional[ReminderClockService] = None,
        include_builtin_reminder: bool = False, reminder_unavailable_reason: str = "",
    ) -> None:
        self.root = Path(root)
        self.workshop_dir = self.root / "workshop"
        self.installed_dir = self.root / "installed"
        self.disabled_dir = self.root / "disabled"
        self.archive_dir = self.root / "archive"
        self.quarantine_dir = self.root / "quarantine"
        self.runner = CapabilityRunner()
        self.activity: List[Dict[str, Any]] = []
        self.reminder_service = reminder_service
        self.reminder_unavailable_reason = str(reminder_unavailable_reason or "")
        self.include_builtin_reminder = bool(include_builtin_reminder or reminder_service is not None)
        self._builtin_disabled: set[str] = set()
        self._builtin_state_path = self.root / "builtin_state.json"
        for folder in (self.workshop_dir, self.installed_dir, self.disabled_dir, self.archive_dir, self.quarantine_dir):
            folder.mkdir(parents=True, exist_ok=True)
        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text(FOLDER_README, encoding="utf-8")
        if self.include_builtin_reminder:
            try:
                state_data = json.loads(self._builtin_state_path.read_text(encoding="utf-8")) if self._builtin_state_path.exists() else {}
                self._builtin_disabled = {str(item) for item in state_data.get("disabled", [])}
            except Exception:
                self._builtin_disabled = set()
            if self.reminder_service is None and not self.reminder_unavailable_reason:
                self.reminder_service = ReminderClockService(self.root / "builtin_data" / "reminder_clock")
            if self.reminder_service is not None:
                self.reminder_service.activity = lambda event, message: self._record_activity(event, "reminder_clock", message)
            else:
                self._builtin_disabled.add("reminder_clock")
                self._record_activity("unavailable", "reminder_clock", self.reminder_unavailable_reason)
            self._archive_mock_reminder_package()

    def _archive_mock_reminder_package(self) -> None:
        for folder in (self.installed_dir, self.disabled_dir):
            source = folder / "reminder_clock"
            if source.exists():
                target = self.archive_dir / "reminder_clock" / f"replaced_by_builtin_{int(time.time())}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                self._record_activity("updated", "reminder_clock", "Mock Reminder Clock archived and replaced by functional built-in v1.0.0.")

    def _save_builtin_state(self) -> None:
        self._builtin_state_path.write_text(json.dumps({"disabled": sorted(self._builtin_disabled)}, indent=2), encoding="utf-8")

    def _reminder_manifest(self) -> CapabilityManifest:
        actions = [
            CapabilityAction(name, name.replace("_", " ").title(), ["WRITE_LOCAL_DATA"], name in {"cancel_reminder", "dismiss_reminder"})
            for name in ("create_reminder", "create_alarm", "list_reminders", "cancel_reminder", "snooze_reminder", "dismiss_reminder", "get_reminder_status")
        ]
        runtime_status = "unavailable" if self.reminder_service is None else "functional"
        last_test = self.reminder_unavailable_reason or "built-in validated"
        raw = {"runtime_status": runtime_status, "last_test_result": last_test}
        return CapabilityManifest(
            "reminder_clock", "Reminder Clock", "1.0.0",
            "Persistent profile-local reminders and alarms with a background scheduler.",
            "tool", ["remind me to check something", "set an alarm for tomorrow", "list my pending reminders"],
            actions, ["WRITE_LOCAL_DATA"], {"cancel_reminder": "explicit", "dismiss_reminder": "explicit"},
            [], [], 5.0, [], {}, {"controls": [{"type": "status", "id": "scheduler", "label": "Scheduler"}]},
            "BX1 Brain built-in", "", "2.12.0", "builtin", True,
            ["Reminder text is stored as data and never executed."],
            ["Cannot execute reminder text.", "Cannot access network services.", "Cannot run shell commands."], raw,
        )

    def create_addon_template(self, capability_id: str = "workshop_greeting") -> Path:
        return create_greeting_template(self.workshop_dir / capability_id, capability_id)

    def create_support_demo_package(self) -> Path:
        return create_support_responder_package(self.workshop_dir / "support_mention_responder")

    def design_proposal(self, proposal: CapabilityProposal) -> Path:
        path = create_proposal_package(self.workshop_dir / proposal.capability_id, proposal)
        self._record_activity("design_generated", proposal.capability_id, f"Design generated for {proposal.capability_name}.")
        return path

    def _record_activity(self, event: str, capability_id: str, message: str) -> None:
        self.activity.append({"timestamp": time.time(), "event": event, "capability_id": capability_id, "message": message})
        self.activity = self.activity[-500:]

    def find_action(self, action_ids: set[str]) -> Optional[CapabilityRecord]:
        for record in self.list_records():
            if {action.action_id for action in record.manifest.actions} & set(action_ids):
                return record
        return None

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
        self._record_activity("validation_passed", manifest.capability_id, "Manifest and source safety validation passed.")
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
        manifest = load_manifest(Path(package_dir) / "manifest.json")
        self._record_activity("tests_passed", manifest.capability_id, "Automated capability tests passed.")
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
        if manifest.capability_id == "reminder_clock" and self.include_builtin_reminder:
            raise CapabilityValidationError("Reminder Clock is a unique built-in capability; install a versioned Brain update instead.")
        target = self.installed_dir / manifest.capability_id
        if target.exists():
            current_manifest = load_manifest(target / "manifest.json")
            if current_manifest.version == manifest.version and current_manifest.checksum == manifest.checksum:
                raise CapabilityValidationError(f"Capability {manifest.capability_id} {manifest.version} is already installed.")
            archive_target = self.archive_dir / manifest.capability_id / f"{int(time.time())}_{manifest.version}"
            archive_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(archive_target))
        if (self.disabled_dir / manifest.capability_id).exists():
            shutil.rmtree(self.disabled_dir / manifest.capability_id)
        shutil.copytree(package_dir, target)
        self._record_activity("installed", manifest.capability_id, "Capability installed after explicit approval.")
        return CapabilityRecord(manifest, str(target), "installed")

    def list_records(self) -> List[CapabilityRecord]:
        records: List[CapabilityRecord] = []
        if self.include_builtin_reminder:
            state = "disabled" if "reminder_clock" in self._builtin_disabled else "installed"
            records.append(CapabilityRecord(self._reminder_manifest(), "builtin://reminder_clock", state))
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
        if capability_id == "reminder_clock" and self.include_builtin_reminder:
            self._builtin_disabled.add(capability_id)
            self._save_builtin_state()
            if self.reminder_service is not None:
                self.reminder_service.shutdown()
            self._record_activity("disabled", capability_id, "Capability disabled.")
            return
        source = self.installed_dir / capability_id
        if not source.exists():
            return
        target = self.disabled_dir / capability_id
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))
        self._record_activity("disabled", capability_id, "Capability disabled.")

    def enable(self, capability_id: str) -> None:
        if capability_id == "reminder_clock" and self.include_builtin_reminder:
            if self.reminder_service is None:
                self._record_activity("enable_failed", capability_id, self.reminder_unavailable_reason)
                return
            self._builtin_disabled.discard(capability_id)
            self._save_builtin_state()
            if self.reminder_service is not None:
                self.reminder_service.start()
            self._record_activity("enabled", capability_id, "Capability enabled.")
            return
        source = self.disabled_dir / capability_id
        if not source.exists():
            return
        target = self.installed_dir / capability_id
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))
        self._record_activity("enabled", capability_id, "Capability enabled.")

    def remove(self, capability_id: str) -> None:
        if capability_id == "reminder_clock" and self.include_builtin_reminder:
            raise CapabilityValidationError("The built-in Reminder Clock cannot be removed; it can be disabled.")
        for folder in (self.installed_dir, self.disabled_dir):
            source = folder / capability_id
            if source.exists():
                target = self.archive_dir / capability_id / f"removed_{int(time.time())}"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                self._record_activity("removed", capability_id, "Capability moved to the archive.")
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
        if capability_id == "reminder_clock" and self.reminder_service is not None:
            action_meta = next((item for item in record.manifest.actions if item.action_id == action), None)
            if action_meta is None:
                return CapabilityRunResult(False, capability_id, action, error="unknown_action", message=f"Unknown action: {action}")
            if action_meta.confirmation_required and not confirmed:
                return CapabilityRunResult(False, capability_id, action, error="confirmation_required", message="Action requires confirmation.", requires_confirmation=True)
            self._record_activity("action_invoked", capability_id, f"Action {action} invoked.")
            started = time.perf_counter()
            try:
                result = self.reminder_service.execute(action, parameters or {})
            except Exception as exc:
                self._record_activity("runtime_error", capability_id, f"Action {action} failed: {exc}")
                return CapabilityRunResult(False, capability_id, action, error="runtime_error", message=str(exc), duration_s=time.perf_counter() - started)
            ok = bool(result.get("ok"))
            self._record_activity("action_result", capability_id, f"Action {action}: {'success' if ok else result.get('error', 'failed')}.")
            return CapabilityRunResult(ok, capability_id, action, result, str(result.get("message") or ""), str(result.get("error") or ""), time.perf_counter() - started)
        if capability_id == "reminder_clock" and self.include_builtin_reminder:
            return CapabilityRunResult(
                False, capability_id, action, error="unavailable",
                message=self.reminder_unavailable_reason or "Reminder Clock is unavailable.",
            )
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
