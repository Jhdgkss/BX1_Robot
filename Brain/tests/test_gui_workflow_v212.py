from __future__ import annotations

import ast
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE_PATH = ROOT / "main_pyqt.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, str(SOURCE_PATH))
MAIN = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
METHODS = {node.name: node for node in MAIN.body if isinstance(node, ast.FunctionDef)}

from bx1_ui.app_shell import build_default_page_registry


def method_source(name: str) -> str:
    node = METHODS[name]
    return ast.get_source_segment(SOURCE, node) or ""


class GuiWorkflowV212Tests(unittest.TestCase):
    def test_runtime_first_navigation_is_present(self) -> None:
        build_ui = method_source("_build_ui")
        registry = build_default_page_registry()
        self.assertEqual(registry.page_ids(), ["home", "conversation", "knowledge", "capabilities", "integrations", "robot", "settings"])
        for builder in (
            "_build_home_workspace",
            "_build_conversation_workspace",
            "_build_knowledge_workspace",
            "_build_capabilities_workspace",
            "_build_integrations_workspace",
            "_build_robot_workspace",
            "_build_settings_workspace",
        ):
            self.assertIn(builder, build_ui)
        self.assertIn("_build_studios_workspace", SOURCE)

    def test_main_runtime_does_not_embed_duplicate_character_editors(self) -> None:
        settings = method_source("_build_settings_workspace")
        self.assertIn("_build_runtime_identity_voice_tab", settings)
        self.assertNotIn("_build_identity_tab()", settings)
        self.assertNotIn("_build_voice_memory_tab()", settings)
        self.assertIn("open_personality_studio_ui", method_source("open_identity_editor"))
        self.assertIn("open_dottts_lab_ui", method_source("open_voice_setup"))

    def test_personality_and_robot_profile_are_shown_separately(self) -> None:
        runtime = method_source("refresh_runtime_identity_panel")
        self.assertIn("Personality project", runtime)
        self.assertIn("Robot profile", runtime)
        self.assertIn("selected_voice_profile", runtime)

    def test_memory_is_owned_by_knowledge_workspace(self) -> None:
        library = method_source("_build_library_workspace")
        memory = method_source("_build_memory_overview_panel")
        self.assertIn('("Memory", self._build_memory_overview_panel())', library)
        self.assertIn("memory_enabled_check", memory)
        self.assertIn("memory_search_button", memory)

    def test_runtime_save_does_not_overwrite_missing_personality_voice_widgets(self) -> None:
        refresh = method_source("refresh_cfg_from_widgets")
        self.assertIn('if hasattr(self, "voice_engine_edit")', refresh)
        self.assertIn('if hasattr(self, "dottts_model_edit")', refresh)
        self.assertIn('if hasattr(self, "voice_rate_spin")', refresh)
        self.assertIn('if hasattr(self, "memory_enabled_check")', refresh)

    def test_version_is_v212(self) -> None:
        self.assertIn("Robot Brain V2.12.0 - Runtime Workflow and Studios", SOURCE)


if __name__ == "__main__":
    unittest.main()
