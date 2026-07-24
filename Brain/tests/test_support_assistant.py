from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_integrations.base import IntegrationSettings
from bx1_integrations.registry import IntegrationRegistry
from bx1_integrations.support_assistant import (
    SupportAssistantConnector,
    SupportMessage,
    message_mentions_trigger,
    parse_group_list,
)


class SupportAssistantTests(unittest.TestCase):
    def test_parse_group_list(self) -> None:
        self.assertEqual(parse_group_list("Field Tech; Printers\nField Tech"), ["Field Tech", "Printers"])

    def test_trigger_detection(self) -> None:
        self.assertTrue(message_mentions_trigger("@John_Support can you help?", "@John_Support"))
        self.assertFalse(message_mentions_trigger("@SomeoneElse can you help?", "@John_Support"))

    def test_scans_only_approved_groups(self) -> None:
        messages = [
            {"id": "1", "group_id": "approved", "group_name": "Approved", "sender": "A", "text": "@John_Support help"},
            {"id": "2", "group_id": "private", "group_name": "Private", "sender": "B", "text": "@John_Support no"},
        ]
        connector = SupportAssistantConnector(
            IntegrationSettings({"approved_groups": ["approved"], "trigger": "@John_Support"}, mock_mode=False),
            message_source=lambda: messages,
        )
        matches = connector.scan_mentions()
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].message_id, "1")

    def test_draft_reply_contains_safety_advice(self) -> None:
        connector = SupportAssistantConnector(IntegrationSettings({"approved_groups": ["Field"], "trigger": "@John_Support"}, mock_mode=True))
        draft = connector.draft_reply(
            SupportMessage("1", "Field", "Field", "Sarah", "@John_Support thermal runaway after nozzle change", "now")
        )
        self.assertEqual(draft.confidence, "high")
        self.assertIn("safety fault", draft.reply_text)

    def test_draft_only_blocks_send_even_when_confirmed(self) -> None:
        connector = SupportAssistantConnector(IntegrationSettings({"draft_only": True}, mock_mode=True))
        draft = connector.draft_reply(SupportMessage("1", "Field", "Field", "Sarah", "@John_Support help", "now"))
        result = connector.send_reply(draft.draft_id)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "draft_only")

    def test_registry_requires_confirmation_for_send(self) -> None:
        connector = SupportAssistantConnector(IntegrationSettings({"draft_only": False}, mock_mode=True))
        registry = IntegrationRegistry.load_defaults([connector])
        result = registry.execute("support_mentions", "send_approved_reply", {"draft_id": "missing"}, initiated_by_ai=True)
        self.assertFalse(result.ok)
        self.assertTrue(result.requires_confirmation)

    def test_mock_send_after_confirmation(self) -> None:
        connector = SupportAssistantConnector(IntegrationSettings({"draft_only": False}, mock_mode=True))
        draft = connector.draft_reply(SupportMessage("1", "Field", "Field", "Sarah", "@John_Support help", "now"))
        registry = IntegrationRegistry.load_defaults([connector])
        result = registry.execute("support_mentions", "send_approved_reply", {"draft_id": draft.draft_id}, confirmed=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.data["mock"])


if __name__ == "__main__":
    unittest.main()
