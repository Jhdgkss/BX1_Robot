from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bx1_modules.emotional_delivery import build_dottts_text, extract_delivery, strip_delivery_tag
from bx1_modules.persona_presets import female_companion_config, parse_name_suggestion
from robot_brain.profile_store import ProfileStore


ROOT = Path(__file__).resolve().parents[1]


class EmotionalDeliveryTests(unittest.TestCase):
    def test_hidden_tag_selects_delivery_without_leaking(self) -> None:
        text = "[voice:playful] You do enjoy giving me the easy jobs, John. [chuckle]"
        plan = extract_delivery(text)
        self.assertEqual(plan.key, "playful")
        self.assertEqual(strip_delivery_tag(text), "You do enjoy giving me the easy jobs, John. [chuckle]")

    def test_inline_direction_can_be_enabled_or_disabled(self) -> None:
        dialogue = "That is genuinely interesting."
        expressive = build_dottts_text(dialogue, "excited", enabled=True, inline_instructions=True)
        plain = build_dottts_text(dialogue, "excited", enabled=True, inline_instructions=False)
        self.assertTrue(expressive.startswith("[Curious, energised"))
        self.assertTrue(expressive.endswith(dialogue))
        self.assertEqual(plain, dialogue)
        self.assertNotIn("voice:", expressive)


class FemalePersonaTests(unittest.TestCase):
    def test_preset_is_self_naming_and_context_limited(self) -> None:
        cfg = female_companion_config()
        self.assertEqual(cfg["robot_name"], "Unnamed")
        self.assertEqual(cfg["persona_identity_mode"], "humanlike")
        self.assertEqual(cfg["persona_gender"], "female")
        self.assertTrue(cfg["identity_name_pending"])
        self.assertLessEqual(cfg["personality_controls"]["flirtiness"], 25)
        prompt = cfg["personality_prompt"].lower()
        self.assertIn("do not flirt during diagnostics", prompt)
        self.assertIn("answer honestly", prompt)

    def test_name_proposal_parser_accepts_json_and_rejects_noise(self) -> None:
        parsed = parse_name_suggestion('{"name":"Mara","reason":"It feels bright and curious.","introduction":"I think Mara suits me."}')
        self.assertEqual(parsed["name"], "Mara")
        with self.assertRaises(ValueError):
            parse_name_suggestion("Perhaps Alice or Clara")

    def test_profile_preset_does_not_modify_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "config").mkdir()
            shutil.copy2(ROOT / "config" / "app_config_bx1.json", root / "config" / "app_config_bx1.json")
            (root / "config" / "robot_profiles.json").write_text(
                json.dumps({"schema_version": 1, "selected_profile": "bx1", "profiles": {"bx1": {"name": "BX1", "description": "robot", "api_port": 8765, "tts_port": 8092}}}),
                encoding="utf-8",
            )
            store = ProfileStore(root)
            created = store.create(
                slug="companion",
                name="",
                description="",
                personality="",
                source="bx1",
                api_port=8766,
                preset="female_companion",
            )
            companion = store.read_app_config("companion")
            source = store.read_app_config("bx1")
            self.assertEqual(created.name, "Unnamed")
            self.assertEqual(companion["persona_gender"], "female")
            self.assertEqual(source["robot_name"], "BX1")
            self.assertEqual(store.selected_slug(), "bx1")
            store.update_identity("companion", name="Mara", description=companion["robot_profile"])
            discovered = {profile.slug: profile for profile in store.discover()}
            self.assertEqual(discovered["companion"].name, "Mara")

    def test_main_reply_path_preserves_private_delivery_metadata(self) -> None:
        source = (ROOT / "main_pyqt.py").read_text(encoding="utf-8")
        self.assertIn("raw_reply =", source)
        self.assertIn("voice_delivery = extract_delivery(raw_reply", source)
        self.assertIn('"voice_delivery": voice_delivery', source)
        self.assertIn("build_dottts_text(", source)


if __name__ == "__main__":
    unittest.main()

