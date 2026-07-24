from __future__ import annotations

import unittest
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_ui.app_shell import build_default_page_registry
from bx1_ui.command_palette import CommandPaletteIndex
from bx1_ui.design_tokens import load_design_tokens
from bx1_ui.navigation import NavigationState
from bx1_ui.page_registry import PageDefinition, PageRegistry
from bx1_integrations.base import BaseIntegration, IntegrationSettings
from bx1_integrations.registry import IntegrationRegistry
from main_pyqt import DEFAULT_CONFIG, MainWindow


class _Card:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class _DocumentStore:
    def status(self) -> dict:
        return {"document_count": 0, "chunk_count": 0}


class _SttService:
    def status(self) -> dict:
        return {"loaded": False, "loading": False, "package_available": True}


class _BehaviourStore:
    def status(self) -> dict:
        return {"installed_count": 0}


class _Core:
    latest_frame = None
    document_store = _DocumentStore()
    stt_service = _SttService()
    behaviour_store = _BehaviourStore()

    def ollama_health(self, **_kwargs: object) -> dict:
        return {"ok": True}

    def latest_body_context(self) -> dict:
        return {}


class _Integration(BaseIntegration):
    integration_id = "demo"
    display_name = "Demo"

    @property
    def capabilities(self) -> list:
        return []

    def execute_action(self, action_id: str, params=None, *, initiated_by_ai: bool = False, confirmed: bool = False):
        raise NotImplementedError


class GuiModernisationTests(unittest.TestCase):
    def test_page_registry_has_unique_page_ids(self) -> None:
        registry = build_default_page_registry()
        self.assertEqual(len(registry.page_ids()), len(set(registry.page_ids())))
        self.assertEqual(registry.duplicate_routes(), {})

    def test_canonical_routing_aliases(self) -> None:
        registry = build_default_page_registry()
        self.assertEqual(registry.canonical_id("dashboard"), "home")
        self.assertEqual(registry.canonical_id("skills"), "capabilities")
        self.assertEqual(registry.canonical_id("robot updates"), "robot")
        self.assertEqual(registry.canonical_id("help"), "settings")

    def test_command_palette_search(self) -> None:
        registry = build_default_page_registry()
        index = CommandPaletteIndex(registry)
        self.assertEqual(index.search("spotify")[0].page.page_id, "integrations")
        self.assertEqual(index.search("documents")[0].page.page_id, "knowledge")
        self.assertEqual(index.search("capability forge")[0].page.page_id, "capabilities")

    def test_sidebar_page_selection(self) -> None:
        state = NavigationState(build_default_page_registry())
        self.assertEqual(state.select("chat"), "conversation")
        self.assertEqual(state.select("body"), "robot")
        self.assertTrue(state.toggle_collapsed())
        self.assertTrue(all(len(label) <= 1 for label in state.visible_labels()))

    def test_unavailable_page_handling(self) -> None:
        registry = PageRegistry()
        registry.register(PageDefinition("home", "Home", "H", "core"))
        registry.register(PageDefinition("future", "Future", "F", "core", available=False, unavailable_reason="Not ready"))
        state = NavigationState(registry)
        with self.assertRaisesRegex(ValueError, "Not ready"):
            state.select("future")

    def test_duplicate_route_detection(self) -> None:
        registry = PageRegistry()
        registry.register(PageDefinition("one", "One", "1", "core", aliases=("same",)))
        with self.assertRaises(ValueError):
            registry.register(PageDefinition("two", "Two", "2", "core", aliases=("same",)))

    def test_theme_token_loading(self) -> None:
        dark = load_design_tokens("dark").as_dict()
        light = load_design_tokens("light").as_dict()
        self.assertEqual(dark["name"], "dark")
        self.assertEqual(light["name"], "light")
        self.assertNotEqual(dark["background"], light["background"])

    def test_existing_important_workspaces_still_reachable(self) -> None:
        registry = build_default_page_registry()
        checks = {
            "chat": "conversation",
            "voice": "conversation",
            "documents": "knowledge",
            "memory": "knowledge",
            "behaviour forge": "capabilities",
            "capability forge": "capabilities",
            "octoprint": "integrations",
            "spotify": "integrations",
            "robot updates": "robot",
            "models": "settings",
            "theme": "settings",
        }
        index = CommandPaletteIndex(registry)
        for query, page_id in checks.items():
            with self.subTest(query=query):
                self.assertEqual(index.search(query)[0].page.page_id, page_id)

    def test_refresh_mission_cards_uses_public_registry_all_api(self) -> None:
        window = SimpleNamespace()
        window.cfg = dict(DEFAULT_CONFIG)
        window.core = _Core()
        window.mission_cards = {key: _Card() for key in ("BRAIN", "BODY", "VOICE", "MODEL", "PERSONALITY", "LIBRARY", "SKILLS", "INTEGRATIONS")}
        window.refresh_runtime_identity_panel = lambda: None

        window.integration_registry = IntegrationRegistry()
        MainWindow.refresh_mission_cards(window)
        self.assertIn("0 connectors", window.mission_cards["INTEGRATIONS"].text)

        window.integration_registry = IntegrationRegistry.load_defaults([_Integration(IntegrationSettings(mock_mode=True))])
        MainWindow.refresh_mission_cards(window)
        self.assertIn("1 connectors", window.mission_cards["INTEGRATIONS"].text)


if __name__ == "__main__":
    unittest.main()
