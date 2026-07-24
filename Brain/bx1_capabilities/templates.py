from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from bx1_capabilities.manifest import manifest_with_checksum


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_package(folder: Path, manifest: Dict[str, Any], capability_py: str, tests_py: str, readme: str, settings_schema: Dict[str, Any], ui_schema: Dict[str, Any]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "capability.py").write_text(capability_py, encoding="utf-8")
    manifest = manifest_with_checksum(manifest, folder / "capability.py")
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "tests.py").write_text(tests_py, encoding="utf-8")
    (folder / "README.md").write_text(readme, encoding="utf-8")
    (folder / "settings_schema.json").write_text(json.dumps(settings_schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "ui_schema.json").write_text(json.dumps(ui_schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return folder


def create_greeting_template(folder: Path, capability_id: str = "workshop_greeting") -> Path:
    manifest = {
        "capability_id": capability_id,
        "display_name": "Workshop Greeting",
        "version": "1.0.0",
        "description": "A simple no-permission greeting capability template.",
        "capability_type": "tool",
        "trigger_phrases": ["give me a workshop greeting"],
        "actions": [{"action_id": "greet", "description": "Return a friendly workshop greeting.", "permissions": ["NONE"], "confirmation_required": False}],
        "permissions": ["NONE"],
        "confirmation_policy": {},
        "allowed_network_domains": [],
        "allowed_file_paths": [],
        "timeout_seconds": 5,
        "dependencies": [],
        "settings_schema": {},
        "ui_schema": {"controls": [{"type": "action_button", "action": "greet", "label": "Greet"}, {"type": "status", "id": "result", "label": "Result"}]},
        "created_by": "BX1 Capability Forge",
        "created_timestamp": utc_now(),
        "minimum_brain_version": "2.12.0",
        "checksum": "",
        "enabled_by_default": True,
        "limitations": ["Returns a static greeting only."],
        "cannot_do": ["Cannot access files.", "Cannot access the network.", "Cannot control robot hardware."],
    }
    capability_py = '''"""Starter BX1 capability.

Expose only:
- get_capability_metadata()
- validate_settings(settings)
- execute(action, parameters, context)
- shutdown()
"""

def get_capability_metadata():
    return {"capability_id": "workshop_greeting", "actions": ["greet"]}

def validate_settings(settings):
    return {"ok": True}

def execute(action, parameters, context):
    if action != "greet":
        return {"ok": False, "error": "unknown_action", "message": "Unknown action."}
    name = str((parameters or {}).get("name") or "workshop")
    return {"ok": True, "message": f"Hello from the BX1 Capability Forge, {name}.", "greeting": f"Hello, {name}."}

def shutdown():
    return None
'''
    tests_py = '''import unittest
import capability

class CapabilityTests(unittest.TestCase):
    def test_greet(self):
        result = capability.execute("greet", {"name": "John"}, {})
        self.assertTrue(result["ok"])
        self.assertIn("John", result["message"])

if __name__ == "__main__":
    unittest.main()
'''
    return _write_package(folder, manifest, capability_py, tests_py, "# Workshop Greeting\n\nStarter addon template.\n", {}, manifest["ui_schema"])


def create_support_responder_package(folder: Path) -> Path:
    manifest = {
        "capability_id": "support_mention_responder",
        "display_name": "Support Mention Responder",
        "version": "1.0.0",
        "description": "Scans approved support groups for a trigger mention and drafts a technical support reply.",
        "capability_type": "integration",
        "trigger_phrases": ["scan support mentions", "draft support reply for john support", "@John_Support"],
        "actions": [
            {"action_id": "scan_mentions", "description": "Find approved support mentions.", "permissions": ["NONE"], "confirmation_required": False},
            {"action_id": "draft_reply", "description": "Draft a technical support reply.", "permissions": ["NONE"], "confirmation_required": False},
            {"action_id": "approve_send", "description": "Send an approved support reply.", "permissions": ["NETWORK_CONTROL"], "confirmation_required": True},
        ],
        "permissions": ["NETWORK_CONTROL"],
        "confirmation_policy": {"approve_send": "explicit"},
        "allowed_network_domains": [],
        "allowed_file_paths": [],
        "timeout_seconds": 5,
        "dependencies": [],
        "settings_schema": {"trigger": "@John_Support", "approved_groups": ["Field Tech Support"], "draft_only": True},
        "ui_schema": {"controls": [{"type": "text", "id": "trigger", "label": "Trigger"}, {"type": "approved_item_list", "id": "approved_groups", "label": "Approved groups"}, {"type": "checkbox", "id": "draft_only", "label": "Draft-only mode"}, {"type": "action_button", "action": "scan_mentions", "label": "Scan"}, {"type": "action_button", "action": "draft_reply", "label": "Draft"}, {"type": "action_button", "action": "approve_send", "label": "Approve Send"}, {"type": "activity_log", "id": "log", "label": "Activity"}]},
        "created_by": "BX1 Capability Forge",
        "created_timestamp": utc_now(),
        "minimum_brain_version": "2.12.0",
        "checksum": "",
        "enabled_by_default": True,
        "limitations": ["Mock/demo message source until a legitimate messaging connector is installed.", "Draft-only mode is enabled by default."],
        "cannot_do": ["Cannot read unapproved groups.", "Cannot access arbitrary messaging accounts.", "Cannot auto-reply.", "Cannot connect to live WhatsApp in mock mode."],
    }
    capability_py = r'''import re
import uuid
from datetime import datetime

PENDING_DRAFTS = {}

def get_capability_metadata():
    return {"capability_id": "support_mention_responder", "actions": ["scan_mentions", "draft_reply", "approve_send"]}

def validate_settings(settings):
    settings = settings or {}
    groups = settings.get("approved_groups") or ["Field Tech Support"]
    if isinstance(groups, str):
        groups = [item.strip() for item in re.split(r"[\n,;]+", groups) if item.strip()]
    if not groups:
        return {"ok": False, "error": "At least one approved group is required."}
    return {"ok": True}

def _settings(context):
    return (context or {}).get("settings") or {}

def _groups(settings):
    groups = settings.get("approved_groups") or ["Field Tech Support"]
    if isinstance(groups, str):
        groups = [item.strip() for item in re.split(r"[\n,;]+", groups) if item.strip()]
    return groups

def _trigger(settings):
    return str(settings.get("trigger") or "@John_Support")

def _mock_messages(settings):
    group = _groups(settings)[0]
    trigger = _trigger(settings)
    return [
        {"message_id": "mock-1", "group_id": group, "group_name": group, "sender": "Sarah", "text": f"{trigger} The printer reports thermal runaway after a nozzle change. What should I check first?", "timestamp": datetime.now().isoformat(timespec="seconds")},
        {"message_id": "mock-2", "group_id": "Random Chat", "group_name": "Random Chat", "sender": "Alex", "text": f"{trigger} lunch?", "timestamp": datetime.now().isoformat(timespec="seconds")},
    ]

def _scan(settings):
    approved = {g.lower() for g in _groups(settings)}
    trigger = _trigger(settings).lower()
    matches = []
    for msg in _mock_messages(settings):
        if {str(msg.get("group_id", "")).lower(), str(msg.get("group_name", "")).lower()} & approved and trigger in str(msg.get("text", "")).lower():
            matches.append(msg)
    return matches

def _draft(message, settings):
    text = re.sub(re.escape(_trigger(settings)), "", str(message.get("text") or ""), flags=re.IGNORECASE).strip()
    reply = "Thanks for the tag. Treat this as a safety fault first: stop unattended heating, check the sensor is seated, inspect wiring, and confirm the temperature reading is plausible before reheating."
    confidence = "high" if any(word in text.lower() for word in ("thermal", "temperature", "nozzle")) else "medium"
    draft_id = uuid.uuid4().hex
    draft = {"draft_id": draft_id, "message": message, "reply_text": reply, "confidence": confidence, "notes": ["Draft-only by default; review before sending."]}
    PENDING_DRAFTS[draft_id] = draft
    return draft

def execute(action, parameters, context):
    settings = _settings(context)
    if action == "scan_mentions":
        matches = _scan(settings)
        return {"ok": True, "matches": matches, "message": f"{len(matches)} support mention(s) found."}
    if action == "draft_reply":
        message = (parameters or {}).get("message")
        if not message:
            matches = _scan(settings)
            if not matches:
                return {"ok": False, "error": "no_mentions", "message": "No approved support mentions found."}
            message = matches[0]
        return {"ok": True, "draft": _draft(message, settings), "message": "Support reply drafted."}
    if action == "approve_send":
        if bool(settings.get("draft_only", True)):
            return {"ok": False, "error": "draft_only", "message": "Draft-only mode is enabled; sending is blocked."}
        return {"ok": True, "mock": True, "message": "Mock send completed."}
    return {"ok": False, "error": "unknown_action", "message": "Unknown action."}

def shutdown():
    return None
'''
    tests_py = '''import unittest
import capability

class CapabilityTests(unittest.TestCase):
    def test_scan_and_draft(self):
        ctx = {"settings": {"trigger": "@John_Support", "approved_groups": ["Field Tech Support"], "draft_only": True}}
        scan = capability.execute("scan_mentions", {}, ctx)
        self.assertTrue(scan["ok"])
        self.assertEqual(len(scan["matches"]), 1)
        draft = capability.execute("draft_reply", {"message": scan["matches"][0]}, ctx)
        self.assertTrue(draft["ok"])
        self.assertIn("safety fault", draft["draft"]["reply_text"])

    def test_draft_only_blocks_send(self):
        result = capability.execute("approve_send", {}, {"settings": {"draft_only": True, "approved_groups": ["Field Tech Support"]}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "draft_only")

if __name__ == "__main__":
    unittest.main()
'''
    return _write_package(folder, manifest, capability_py, tests_py, "# Support Mention Responder\n\nCapability package demo. Draft-only by default.\n", manifest["settings_schema"], manifest["ui_schema"])
