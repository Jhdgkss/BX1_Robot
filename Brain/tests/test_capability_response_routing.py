from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main_pyqt import BX1BrainCore, DEFAULT_CONFIG, GuiSignals
from bx1_capabilities.manager import CapabilityManager
from bx1_capabilities.models import CapabilityRunResult
from bx1_capabilities.design import reminder_proposal
from bx1_capabilities.reminder_clock import ReminderClockService


class CapabilityResponseRoutingTests(unittest.TestCase):
    def make_core(self, root: Path) -> BX1BrainCore:
        cfg = dict(DEFAULT_CONFIG)
        cfg.update({"api_require_ollama_online": False, "voice_speak_replies": False,
                    "integrations": {"mock_mode": True}})
        core = BX1BrainCore(GuiSignals(), cfg)
        core.reminder_clock.shutdown()
        core.capability_manager = CapabilityManager(root)
        return core

    def test_missing_reminder_request_never_calls_general_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("main_pyqt.requests.post") as post:
            core = self.make_core(Path(tmp))
            result = core.generate_reply({"message": "Hi. Can you set a reminder for 16:30 please", "source": "gui"})
            self.assertIn("don't currently have a reminder capability", result["reply"])
            self.assertEqual(result["capability_route"], "reminder action")
            post.assert_not_called()

    def test_missing_capability_status_is_registry_grounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("main_pyqt.requests.post") as post:
            core = self.make_core(Path(tmp))
            result = core.generate_reply({"message": "Are you capable of setting reminders?", "source": "gui"})
            self.assertIn("Not currently", result["reply"])
            self.assertEqual(result["capability_state"], "missing")
            post.assert_not_called()

    def test_approval_generates_workshop_proposal_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = self.make_core(Path(tmp))
            emitted = []
            core.signals.capability_proposal_ready.connect(emitted.append)
            core.generate_reply({"message": "Remind me tomorrow to check the printer", "source": "gui"})
            result = core.generate_reply({"message": "Yes", "source": "gui"})
            self.assertIn("prepared", result["reply"])
            self.assertTrue(emitted)
            self.assertFalse(core.capability_manager.list_records())
            self.assertTrue(Path(emitted[0]["package_path"]).exists())

    def test_complete_enabled_reminder_requires_confirmed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = self.make_core(Path(tmp))
            package = core.capability_manager.design_proposal(reminder_proposal("remind me"))
            core.capability_manager.install(package, approved=True)
            with patch.object(core.capability_manager, "execute_installed", return_value=CapabilityRunResult(
                True, "reminder_clock", "create_reminder",
                {"reminder_id": "r-1", "confirmed_trigger_datetime": "2026-07-28T16:30:00+01:00"},
                "created",
            )) as execute:
                result = core.generate_reply({"message": "Remind me at 16:30 to check the printer", "source": "gui"})
            execute.assert_called_once()
            self.assertIn("Reminder set", result["reply"])
            self.assertTrue(result["capability_result"]["verified_action"])

    def test_functional_reminder_is_reused_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            core = self.make_core(Path(tmp) / "review")
            service = ReminderClockService(Path(tmp) / "reminders")
            core.reminder_clock = service
            core.capability_manager = CapabilityManager(
                Path(tmp) / "capabilities", reminder_service=service, include_builtin_reminder=True
            )
            first = core.generate_reply({"message": "Remind me in 10 minutes to check the printer", "source": "gui"})
            second = core.generate_reply({"message": "Remind me in 12 minutes to check the oven", "source": "gui"})
            listed = core.generate_reply({"message": "What reminders do I have?", "source": "gui"})
            self.assertIn("Reminder set", first["reply"])
            self.assertIn("Reminder set", second["reply"])
            self.assertIn("2 pending reminders", listed["reply"])
            records = [r for r in core.capability_manager.list_records() if r.manifest.capability_id == "reminder_clock"]
            self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
