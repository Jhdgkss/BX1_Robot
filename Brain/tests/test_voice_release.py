from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
import shutil
from pathlib import Path

from bx1_modules.edge_voice import EdgeVoice
from robot_brain.profile_store import ProfileStore


ROOT = Path(__file__).resolve().parents[1]


class EdgeVoiceTests(unittest.TestCase):
    def test_signed_edge_adjustments(self) -> None:
        self.assertEqual(EdgeVoice._signed(0, "%"), "+0%")
        self.assertEqual(EdgeVoice._signed(-12, "%"), "-12%")
        self.assertEqual(EdgeVoice._signed(4, "Hz"), "+4Hz")

    def test_generate_uses_edge_client_without_loading_a_model(self) -> None:
        calls = {}

        class FakeCommunicate:
            def __init__(self, text: str, **kwargs) -> None:
                calls.update({"text": text, **kwargs})

            async def save(self, target: str) -> None:
                Path(target).write_bytes(b"fake-mp3")

        original = sys.modules.get("edge_tts")
        sys.modules["edge_tts"] = types.SimpleNamespace(Communicate=FakeCommunicate)
        try:
            with tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "voice.mp3"
                result = EdgeVoice().generate(
                    "Hello robot",
                    output,
                    voice="en-GB-RyanNeural",
                    rate_percent=-5,
                    pitch_hz=2,
                )
                self.assertEqual(result.read_bytes(), b"fake-mp3")
        finally:
            if original is None:
                sys.modules.pop("edge_tts", None)
            else:
                sys.modules["edge_tts"] = original
        self.assertEqual(calls["text"], "Hello robot")
        self.assertEqual(calls["rate"], "-5%")
        self.assertEqual(calls["pitch"], "+2Hz")


class VoiceReleaseTests(unittest.TestCase):
    def test_profile_manager_uses_pyqt_glass_interface(self) -> None:
        manager_path = ROOT / "tools" / "robot_profile_manager.py"
        source = manager_path.read_text(encoding="utf-8")
        self.assertIn("from PyQt6", source)
        self.assertIn("class GlassPanel", source)
        self.assertIn("DWMWA_SYSTEMBACKDROP_TYPE", source)
        removed_gui = "tkin" + "ter"
        self.assertNotIn(removed_gui, source.lower())

    def test_core_installer_does_not_launch_the_application(self) -> None:
        installer = (ROOT / "scripts" / "INSTALL_CORE.bat").read_text(encoding="utf-8").lower()
        manager_launcher = (ROOT / "START_ROBOT_BRAIN.bat").read_text(encoding="utf-8").lower()
        self.assertIn("pip install -r requirements.txt", installer)
        self.assertNotIn("start_bx1_brain.bat", installer)
        self.assertNotIn("main_pyqt.py", installer)
        self.assertIn("call start_bx1_brain.bat", manager_launcher)
        self.assertNotIn("robot_profile_manager.py", manager_launcher)

    def test_main_window_integrates_profiles_and_windows_glass(self) -> None:
        source = (ROOT / "main_pyqt.py").read_text(encoding="utf-8")
        self.assertIn("ProfileManager(self, integrated=True)", source)
        self.assertIn("DWMWA_SYSTEMBACKDROP_TYPE", source)
        self.assertIn('"glass_blue"', source)

    def test_voice_page_scrolls_instead_of_compressing_controls(self) -> None:
        source = (ROOT / "main_pyqt.py").read_text(encoding="utf-8")
        voice_page = source[source.index("def _build_voice_memory_tab"):source.index("def install_help_tooltips")]
        self.assertIn("scroll = QScrollArea()", voice_page)
        self.assertIn("QLayout.SizeConstraint.SetMinimumSize", voice_page)
        self.assertIn("voice_form.setVerticalSpacing(10)", voice_page)
        self.assertIn("scroll.setWidget(page)", voice_page)
        self.assertIn("return scroll", voice_page)

    def test_primary_and_fallback_configuration(self) -> None:
        config = json.loads((ROOT / "config" / "app_config_bx1.json").read_text(encoding="utf-8"))
        self.assertEqual(config["voice_engine"], "dottts")
        self.assertTrue(config["dottts_auto_start"])
        self.assertTrue(config["edge_fallback_enabled"])
        self.assertEqual(config["dottts_service_url"], "http://127.0.0.1:8092")
        self.assertFalse(config["dottts_stop_with_app"])
        self.assertEqual(config["ui_style_preset"], "glass_blue")

    def test_removed_engine_has_no_files_or_text_references(self) -> None:
        removed_name = "chatter" + "box"
        for path in ROOT.rglob("*"):
            if not path.is_file() or "runtime" in path.parts or ".venv" in path.parts:
                continue
            self.assertNotIn(removed_name, path.name.lower())
            if path.suffix.lower() in {".py", ".json", ".md", ".txt", ".bat", ".ps1"}:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
                self.assertNotIn(removed_name, text, str(path))

    def test_dot_service_supports_owned_shutdown(self) -> None:
        source = (ROOT / "bx1_services" / "dottts_service" / "app.py").read_text(encoding="utf-8")
        self.assertIn('request_path == "/shutdown"', source)
        self.assertIn("X-Robot-Brain-Shutdown", source)

    def test_dot_service_is_shared_with_profile_owned_voice_references(self) -> None:
        source = (ROOT / "bx1_services" / "dottts_service" / "app.py").read_text(encoding="utf-8")
        self.assertIn("SHARED_RUNTIME", source)
        self.assertIn('"shared_host": True', source)
        self.assertIn("_read_active_reference(profile)", source)
        self.assertIn("X-Robot-Profile", source)

    def test_robot_audio_is_republished_through_the_brain_api(self) -> None:
        source = (ROOT / "main_pyqt.py").read_text(encoding="utf-8")
        self.assertIn('"transport": "brain_api_proxy"', source)
        self.assertIn('f"/api/audio/{filename}"', source)
        self.assertIn('"recommended_body_version": "10.35"', source)
        self.assertIn('parsed.path in {"/api/tts", "/robot/speak"}', source)
        self.assertIn('parsed.path in {"/api/tts/status", "/robot/tts/status"}', source)

    def test_heavy_vision_packages_are_optional(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        optional = (ROOT / "INSTALL_OPTIONAL_VISION.bat").read_text(encoding="utf-8").lower()
        self.assertNotIn("ultralytics", requirements)
        self.assertNotIn("opencv-python", requirements)
        self.assertIn("ultralytics", optional)
        self.assertIn("opencv-python", optional)

    def test_new_robot_gets_independent_voice_reference(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "config").mkdir()
            shutil.copy2(ROOT / "config" / "app_config_bx1.json", root / "config" / "app_config_bx1.json")
            store = ProfileStore(root)
            profile = store.create(
                slug="nova",
                name="Nova",
                description="workshop robot",
                personality="You are {robot_name}, a curious workshop robot.",
                api_port=8770,
                tts_port=8096,
            )
            config = store.read_app_config(profile.slug)
            self.assertEqual(config["robot_name"], "Nova")
            self.assertEqual(profile.tts_port, 8092)
            self.assertEqual(config["dottts_service_url"], "http://127.0.0.1:8092")
            self.assertEqual(config["selected_voice_profile"], "Nova Main Voice")
            voice = config["voice_lab_profiles"]["Nova Main Voice"]
            self.assertEqual(voice["reference_audio_path"], "")
            self.assertEqual(voice["reference_text"], "")
            self.assertEqual(store.selected_slug(), "bx1")


if __name__ == "__main__":
    unittest.main()
