from __future__ import annotations

from bx1_ui.navigation import NavigationState
from bx1_ui.page_registry import PageDefinition, PageRegistry


def build_default_page_registry() -> PageRegistry:
    registry = PageRegistry()
    for page in (
        PageDefinition("home", "Home", "⌂", "core", ("dashboard", "status", "warnings", "quick actions"), "basic", aliases=("dashboard",)),
        PageDefinition("conversation", "Conversation", "◌", "core", ("chat", "voice", "history", "listen", "speak"), "basic", aliases=("chat", "voice conversation")),
        PageDefinition("knowledge", "Knowledge", "▤", "core", ("documents", "rag", "memory", "sources", "library"), "basic", aliases=("documents", "memory")),
        PageDefinition("capabilities", "Capabilities", "✦", "core", ("behaviour forge", "capability forge", "addons", "workshop", "installed behaviours"), "advanced", aliases=("skills", "workshop", "forge")),
        PageDefinition("integrations", "Integrations", "⇄", "services", ("octoprint", "spotify", "connectors", "external services"), "advanced"),
        PageDefinition("robot", "Robot", "⚙", "hardware", ("telemetry", "camera", "hardware", "diagnostics", "updates", "mcu", "touchscreen"), "diagnostic", aliases=("body", "robot updates")),
        PageDefinition("settings", "Settings", "☷", "system", ("personality", "models", "voice", "tts", "stt", "api", "theme", "developer", "help"), "advanced", aliases=("runtime", "system", "studios", "help")),
    ):
        registry.register(page)
    return registry


def build_default_navigation_state() -> NavigationState:
    return NavigationState(build_default_page_registry())

