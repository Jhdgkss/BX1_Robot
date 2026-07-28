from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_capabilities.design import (
    PendingProposalState, classify_capability, detect_capability_gap,
    reminder_proposal,
)
from bx1_capabilities.manager import CapabilityManager
from bx1_capabilities.models import CapabilityValidationError
from bx1_capabilities.awareness import (
    capability_status_target, confirmed_reminder_result, guard_capability_claims,
    parse_reminder_request, reminder_availability, safe_capability_summary,
)


class CapabilityDesignTests(unittest.TestCase):
    def test_shared_type_classifier(self) -> None:
        cases = {
            "Remind me tomorrow at four": "tool",
            "Connect Spotify through its API": "integration",
            "Create a greeting with head movement and mouth lights": "behaviour",
            "Add support for a new distance sensor": "hardware",
        }
        for description, expected in cases.items():
            self.assertEqual(classify_capability(description).capability_type, expected)

    def test_informational_questions_do_not_create_gap(self) -> None:
        for text in ("What is an alarm clock?", "Could a robot theoretically set an alarm?",
                     "Write a story about a robot with a reminder."):
            self.assertEqual(detect_capability_gap(text, [])[0], "none")

    def test_missing_reminder_creates_structured_proposal(self) -> None:
        state, proposal = detect_capability_gap("Remind me in ten minutes to check the printer", [])
        self.assertEqual(state, "missing")
        self.assertEqual(proposal.capability_type, "tool")
        self.assertIn("create_reminder", proposal.actions)
        self.assertIn("shell_execution", proposal.forbidden_permissions)

    def test_existing_and_disabled_capabilities_are_found_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.design_proposal(reminder_proposal("set a reminder"))
            manager.install(package, approved=True)
            self.assertEqual(detect_capability_gap("remind me tomorrow", manager.list_records())[0], "existing")
            manager.disable("reminder_clock")
            self.assertEqual(detect_capability_gap("remind me tomorrow", manager.list_records())[0], "disabled")

    def test_pending_approval_rejection_and_topic_expiry(self) -> None:
        pending = PendingProposalState()
        pending.set(reminder_proposal("remind me tomorrow"))
        self.assertEqual(pending.interpret_followup("Yes, create it"), "approve_design")
        pending.set(reminder_proposal("remind me tomorrow"))
        self.assertEqual(pending.interpret_followup("No"), "reject")
        pending.set(reminder_proposal("remind me tomorrow"))
        self.assertEqual(pending.interpret_followup("How is the printer doing?"), "topic_changed")
        pending.clear()
        self.assertEqual(pending.interpret_followup("Yes"), "none")

    def test_design_build_test_and_explicit_install_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            proposal = reminder_proposal("remind me in ten minutes")
            package = manager.design_proposal(proposal)
            validated = manager.validate_package(package)
            self.assertEqual(validated["manifest"].capability_type, "tool")
            self.assertTrue(manager.run_tests(package)["ok"])
            self.assertTrue(manager.mock_execute(package, "create_reminder").ok)
            with self.assertRaises(CapabilityValidationError):
                manager.install(package, approved=False)
            record = manager.install(package, approved=True)
            self.assertEqual(record.manifest.capability_id, "reminder_clock")

    def test_reminder_status_query_and_action_are_distinguished(self) -> None:
        self.assertEqual(capability_status_target("Are you capable of setting reminders?"), "reminder_clock")
        self.assertEqual(capability_status_target("Can you set an alarm?"), "reminder_clock")
        self.assertEqual(capability_status_target("Can you set a reminder for 16:30?"), "")
        request = parse_reminder_request("Can you set a reminder for 16:30?")
        self.assertEqual(request.trigger_text, "16:30")
        self.assertEqual(request.reminder_text, "")

    def test_observed_reminder_wording_routes_as_action(self) -> None:
        request = parse_reminder_request("Hi. Can you set a reminder for 16:30 please")
        self.assertIsNotNone(request)
        self.assertEqual(request.trigger_text, "16:30")

    def test_complete_reminder_request_parses_required_arguments(self) -> None:
        request = parse_reminder_request("Remind me at 16:30 to check the printer.")
        self.assertTrue(request.complete)
        self.assertEqual(request.reminder_text, "check the printer")

    def test_confirmed_result_requires_id_and_iso_datetime(self) -> None:
        self.assertTrue(confirmed_reminder_result(SimpleNamespace(ok=True, data={
            "reminder_id": "r-1", "confirmed_trigger_datetime": "2026-07-28T16:30:00+01:00"
        })))
        self.assertFalse(confirmed_reminder_result(SimpleNamespace(ok=True, data={"message": "done"})))
        self.assertFalse(confirmed_reminder_result(SimpleNamespace(ok=False, data={
            "reminder_id": "r-1", "trigger_datetime": "2026-07-28T16:30:00"
        })))

    def test_claim_guard_blocks_false_reminder_success(self) -> None:
        summary = {"reminder_clock": {"installed": False, "enabled": False}}
        guarded = guard_capability_claims(
            "Set a reminder for 16:30", "Sure. I'll set a reminder for 16:30.", summary
        )
        self.assertIn("don't have an enabled reminder capability", guarded)
        guarded_status = guard_capability_claims(
            "Are you capable of setting reminders?", "Yes, I can do that.", summary
        )
        self.assertIn("Not currently", guarded_status)

    def test_mock_result_cannot_be_described_as_real_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            package = manager.design_proposal(reminder_proposal("remind me tomorrow"))
            manager.install(package, approved=True)
            record = manager.get_record("reminder_clock")
            result = manager.execute_installed(record.manifest.capability_id, "create_reminder", {
                "trigger_text": "16:30", "reminder_text": "check printer"
            })
            self.assertTrue(result.ok)
            self.assertFalse(confirmed_reminder_result(result))

    def test_reminder_registry_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = CapabilityManager(Path(tmp))
            self.assertEqual(reminder_availability(manager.list_records()).state, "missing")
            package = manager.design_proposal(reminder_proposal("remind me tomorrow"))
            manager.install(package, approved=True)
            self.assertEqual(reminder_availability(manager.list_records()).state, "enabled")
            manager.disable("reminder_clock")
            self.assertEqual(reminder_availability(manager.list_records()).state, "disabled")

    def test_informational_alarm_question_remains_unrouted(self) -> None:
        self.assertEqual(capability_status_target("What is an alarm clock?"), "")
        self.assertIsNone(parse_reminder_request("What is an alarm clock?"))


if __name__ == "__main__":
    unittest.main()
