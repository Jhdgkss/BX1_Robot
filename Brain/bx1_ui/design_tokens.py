from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class DesignTokens:
    name: str
    background: str
    panel: str
    panel_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_alt: str
    danger: str
    warning: str
    radius: int = 10
    spacing: int = 10

    def as_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "background": self.background,
            "panel": self.panel,
            "panel_alt": self.panel_alt,
            "border": self.border,
            "text": self.text,
            "muted": self.muted,
            "accent": self.accent,
            "accent_alt": self.accent_alt,
            "danger": self.danger,
            "warning": self.warning,
            "radius": str(self.radius),
            "spacing": str(self.spacing),
        }


def load_design_tokens(theme_name: str = "dark") -> DesignTokens:
    normalized = str(theme_name or "dark").lower()
    if "light" in normalized:
        return DesignTokens(
            name="light",
            background="#eef3f8",
            panel="#ffffff",
            panel_alt="#f5f8fb",
            border="#c9d4df",
            text="#17212b",
            muted="#5d6b7a",
            accent="#2667ff",
            accent_alt="#00a6a6",
            danger="#b42318",
            warning="#a15c00",
        )
    return DesignTokens(
        name="dark",
        background="#071017",
        panel="#111b24",
        panel_alt="#162430",
        border="#29404f",
        text="#e8f1f7",
        muted="#8fa2af",
        accent="#45a3ff",
        accent_alt="#5eead4",
        danger="#ef4444",
        warning="#f59e0b",
    )

