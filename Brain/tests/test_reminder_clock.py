from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_capabilities.manager import CapabilityManager
from bx1_capabilities.models import CapabilityValidationError
from bx1_capabilities.reminder_clock import ReminderClockService


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value
    def __call__(self) -> datetime:
        return self.value


class ReminderClockTests(unittest.TestCase):
    def test_persistence_and_restart_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock(datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc))
            service = ReminderClockService(Path(tmp), now=clock)
            created = service.create({"trigger_text": "in 10 minutes", "reminder_text": "check printer"})
            restarted = ReminderClockService(Path(tmp), now=clock)
            rows = restarted.list_reminders()["reminders"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reminder_id"], created["reminder_id"])

    def test_scheduler_fires_once_and_invokes_tts_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock(datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc))
            announcements = []
            service = ReminderClockService(Path(tmp), now=clock, announce=lambda text, record: announcements.append((text, record["reminder_id"])))
            created = service.create({"trigger_text": "in 2 minutes", "reminder_text": "check printer"})
            clock.value += timedelta(minutes=3)
            self.assertEqual(service.process_due(), 1)
            self.assertEqual(service.process_due(), 0)
            self.assertEqual(announcements, [("check printer", created["reminder_id"])])
            self.assertEqual(service.status(created["reminder_id"])["reminder"]["status"], "fired")

    def test_cancel_snooze_and_dismiss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock(datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc))
            service = ReminderClockService(Path(tmp), now=clock)
            one = service.create({"trigger_text": "in 10 minutes", "message": "one"})
            self.assertTrue(service.snooze(one["reminder_id"], 20)["ok"])
            self.assertEqual(service.status(one["reminder_id"])["reminder"]["snooze_count"], 1)
            self.assertTrue(service.cancel(one["reminder_id"])["ok"])
            two = service.create({"trigger_text": "in 10 minutes", "message": "two"})
            self.assertTrue(service.dismiss(two["reminder_id"])["ok"])
            self.assertEqual(service.list_reminders()["count"], 0)

    def test_daily_recurrence_reschedules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = MutableClock(datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc))
            fired = []
            service = ReminderClockService(Path(tmp), now=clock, announce=lambda text, record: fired.append(text))
            created = service.create({"trigger_text": "in 1 minutes", "message": "daily check", "recurrence": "daily"})
            original = datetime.fromisoformat(created["trigger_datetime"])
            clock.value += timedelta(minutes=2)
            self.assertEqual(service.process_due(), 1)
            row = service.status(created["reminder_id"])["reminder"]
            self.assertEqual(row["status"], "pending")
            self.assertEqual(datetime.fromisoformat(row["trigger_datetime"]), original + timedelta(days=1))
            self.assertEqual(fired, ["daily check"])

    def test_europe_london_local_time_is_timezone_aware(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # July is BST (UTC+1); 16:30 London should be 15:30 UTC.
            clock = MutableClock(datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc))
            service = ReminderClockService(Path(tmp), now=clock)
            parsed = service.parse_trigger("16:30")
            self.assertEqual(parsed.hour, 15)
            self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_europe_london_zone_loads_from_installed_timezone_data(self) -> None:
        london = ZoneInfo("Europe/London")
        winter = datetime(2026, 1, 15, 12, 0, tzinfo=london)
        summer = datetime(2026, 7, 15, 12, 0, tzinfo=london)
        self.assertNotEqual(winter.utcoffset(), summer.utcoffset())

    def test_missing_timezone_data_does_not_crash_brain(self) -> None:
        from main_pyqt import BX1BrainCore, DEFAULT_CONFIG, GuiSignals
        cfg = dict(DEFAULT_CONFIG)
        with patch("main_pyqt.ZoneInfo", side_effect=ZoneInfoNotFoundError("Europe/London")):
            core = BX1BrainCore(GuiSignals(), cfg)
        self.assertIsNone(core.reminder_clock)
        self.assertIsNotNone(core.integration_manager)
        record = core.capability_manager.get_record("reminder_clock")
        self.assertEqual(record.manifest.raw["runtime_status"], "unavailable")
        self.assertIn("Install the tzdata Python package.", core.startup_messages[0])

    def test_invalid_timezone_falls_back_to_valid_application_default(self) -> None:
        from main_pyqt import BX1BrainCore, DEFAULT_CONFIG, GuiSignals
        cfg = dict(DEFAULT_CONFIG)
        cfg["timezone"] = "Not/A_Timezone"
        real_zoneinfo = ZoneInfo

        def checked_zoneinfo(key: str):
            if key == "Not/A_Timezone":
                raise ZoneInfoNotFoundError(key)
            return real_zoneinfo(key)

        with patch("main_pyqt.ZoneInfo", side_effect=checked_zoneinfo):
            core = BX1BrainCore(GuiSignals(), cfg)
        self.assertIsNotNone(core.reminder_clock)
        self.assertEqual(core.reminder_clock.timezone_name, "Europe/London")
        self.assertIn("Not/A_Timezone", core.configuration_errors[0])
        core.reminder_clock.shutdown()

    def test_database_initialization_error_marks_reminder_unavailable(self) -> None:
        import sqlite3
        from main_pyqt import BX1BrainCore, DEFAULT_CONFIG, GuiSignals
        with patch("main_pyqt.ReminderClockService", side_effect=sqlite3.OperationalError("database unavailable")):
            core = BX1BrainCore(GuiSignals(), dict(DEFAULT_CONFIG))
        self.assertIsNone(core.reminder_clock)
        self.assertIsNotNone(core.document_store)
        self.assertEqual(
            core.capability_manager.get_record("reminder_clock").manifest.raw["runtime_status"],
            "unavailable",
        )

    def test_dependency_and_launcher_install_tzdata_with_launch_interpreter(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        installer = (ROOT / "scripts" / "INSTALL_CORE.bat").read_text(encoding="utf-8").lower()
        launcher = (ROOT / "START_BX1_BRAIN.bat").read_text(encoding="utf-8").lower()
        self.assertIn("tzdata", requirements)
        self.assertIn('\"%robot_python%\" -m pip install -r requirements.txt', installer)
        self.assertIn("zoneinfo('europe/london')", installer)
        self.assertIn('\"%brain_python%\" main_pyqt.py', launcher)
        self.assertIn('\"%brain_python%\" -m pip install -r requirements.txt', launcher)

    def test_manager_exposes_one_functional_builtin_and_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ReminderClockService(Path(tmp) / "data")
            manager = CapabilityManager(Path(tmp) / "caps", reminder_service=service, include_builtin_reminder=True)
            reminders = [r for r in manager.list_records() if r.manifest.capability_id == "reminder_clock"]
            self.assertEqual(len(reminders), 1)
            self.assertEqual(reminders[0].manifest.raw["runtime_status"], "functional")
            first = manager.execute_installed("reminder_clock", "create_reminder", {"trigger_text": "in 5 minutes", "message": "one"})
            second = manager.execute_installed("reminder_clock", "create_reminder", {"trigger_text": "in 6 minutes", "message": "two"})
            self.assertTrue(first.ok and second.ok)
            self.assertEqual(manager.execute_installed("reminder_clock", "list_reminders").data["count"], 2)
            self.assertEqual(len([r for r in manager.list_records() if r.manifest.capability_id == "reminder_clock"]), 1)

    def test_disabled_builtin_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp), include_builtin_reminder=True)
            manager.disable("reminder_clock")
            result = manager.execute_installed("reminder_clock", "create_reminder", {"trigger_text": "in 5 minutes", "message": "blocked"})
            self.assertFalse(result.ok)
            self.assertEqual(result.error, "disabled")

    def test_builtin_rejects_duplicate_package_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp), include_builtin_reminder=True)
            # The built-in ID is unique even if a review package is generated.
            from bx1_capabilities.design import reminder_proposal
            package = manager.design_proposal(reminder_proposal("remind me"))
            with self.assertRaises(CapabilityValidationError):
                manager.install(package, approved=True)


if __name__ == "__main__":
    unittest.main()
