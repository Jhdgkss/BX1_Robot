from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bx1_modules.persona_presets import female_companion_config
from robot_brain.personality_store import PERSONALITY_SETTING_KEYS, PersonalityStore


class PersonalityLibraryTests(unittest.TestCase):
    def base_config(self) -> dict:
        return {
            "robot_name": "BX1",
            "robot_profile": "balancing robot",
            "robot_subtitle": "Workshop companion",
            "persona_identity_mode": "robot",
            "persona_gender": "unspecified",
            "personality_controls": {"humour": 68, "flirtiness": 0, "curiosity": 85},
            "personality_prompt": "You are {robot_name}, a dry workshop robot.",
            "personality_style_strength": 86,
            "personality_lock_enabled": True,
            "personality_repair_enabled": True,
            "selected_voice_profile": "BX1 Main Voice",
            "edge_voice": "en-GB-RyanNeural",
            "dottts_emotional_delivery_enabled": True,
            "dottts_inline_delivery_instructions": False,
            "dottts_default_delivery": "normal",
            "api_port": 8765,
            "brain_base_url": "http://192.168.68.52:8765",
            "api_robot_max_drive_speed": 0.25,
            "memory_enabled": True,
            "rag_enabled": True,
            "voice_lab_profiles": {"BX1 Main Voice": {"reference_audio_path": "matt.wav"}},
        }

    def test_bootstrap_preserves_current_and_adds_companion(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            cfg = self.base_config()
            store = PersonalityStore(Path(folder), "bx1")
            store.bootstrap(cfg, female_companion_config())
            profiles = {item.slug: item for item in store.list()}
            self.assertEqual(store.selected_slug(), "current_personality")
            self.assertEqual(profiles["current_personality"].settings["robot_name"], "BX1")
            self.assertEqual(profiles["curious_female_companion"].settings["robot_name"], "Unnamed")
            self.assertEqual(profiles["curious_female_companion"].settings["persona_gender"], "female")

    def test_switch_changes_character_only(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            cfg = self.base_config()
            store = PersonalityStore(Path(folder), "bx1")
            store.bootstrap(cfg, female_companion_config())
            switched = store.apply("curious_female_companion", cfg)
            self.assertEqual(switched["persona_identity_mode"], "humanlike")
            self.assertEqual(switched["edge_voice"], "en-GB-SoniaNeural")
            for key in ("api_port", "brain_base_url", "api_robot_max_drive_speed", "memory_enabled", "rag_enabled", "voice_lab_profiles"):
                self.assertEqual(switched[key], cfg[key], key)
            self.assertNotIn("api_port", PERSONALITY_SETTING_KEYS)
            self.assertNotIn("voice_lab_profiles", PERSONALITY_SETTING_KEYS)

    def test_save_duplicate_rename_delete_and_self_chosen_name(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            cfg = self.base_config()
            store = PersonalityStore(Path(folder), "bx1")
            store.bootstrap(cfg, female_companion_config())
            female = store.apply("curious_female_companion", cfg)
            female["robot_name"] = "Mara"
            female["identity_name_pending"] = False
            store.update("curious_female_companion", female)
            duplicate = store.duplicate("curious_female_companion", "Mara Evening")
            self.assertEqual(duplicate.settings["robot_name"], "Mara")
            renamed = store.rename(duplicate.slug, "Mara Witty")
            self.assertEqual(renamed.name, "Mara Witty")
            store.delete(duplicate.slug)
            restored = store.apply("curious_female_companion", cfg)
            self.assertEqual(restored["robot_name"], "Mara")
            self.assertFalse(restored["identity_name_pending"])

    def test_store_is_profile_specific_and_atomic_file_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = self.base_config()
            bx1 = PersonalityStore(root, "bx1")
            leo = PersonalityStore(root, "leo")
            bx1.bootstrap(cfg, female_companion_config())
            leo_cfg = dict(cfg, robot_name="Leo")
            leo.bootstrap(leo_cfg, female_companion_config())
            self.assertNotEqual(bx1.path, leo.path)
            self.assertEqual(json.loads(bx1.path.read_text(encoding="utf-8"))["schema_version"], 2)
            self.assertEqual(leo.get("current_personality").settings["robot_name"], "Leo")
            self.assertFalse(bx1.path.with_suffix(bx1.path.suffix + ".tmp").exists())


    def test_export_import_keeps_theme_and_voice_assets(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "voice.wav"
            audio.write_bytes(b"RIFF-test-audio")
            cfg = self.base_config()
            cfg["ui_style_preset"] = "plasma_purple"
            cfg["voice_lab_profiles"]["BX1 Main Voice"]["reference_audio_path"] = str(audio)
            cfg["voice_lab_profiles"]["BX1 Main Voice"]["reference_text"] = "This is my reference voice."
            source = PersonalityStore(root / "source", "bx1")
            profile = source.create("Export Test", cfg)
            package = source.export_profile(profile.slug, root / "Export Test.bxpersonality")
            self.assertTrue(package.exists())

            target = PersonalityStore(root / "target", "bx1")
            imported = target.import_profile(package)
            restored = target.apply(imported.slug, self.base_config())
            self.assertEqual(restored["ui_style_preset"], "plasma_purple")
            self.assertEqual(restored["selected_voice_profile"], "BX1 Main Voice")
            restored_audio = Path(restored["voice_lab_profiles"]["BX1 Main Voice"]["reference_audio_path"])
            self.assertTrue(restored_audio.exists())
            self.assertEqual(restored_audio.read_bytes(), b"RIFF-test-audio")

    def test_final_personality_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = PersonalityStore(Path(folder), "bx1")
            store.create("Only One", self.base_config())
            with self.assertRaises(ValueError):
                store.delete(store.selected_slug())


if __name__ == "__main__":
    unittest.main()
