from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict

from bx1_ui.theme_schema import BX1Theme, validate_theme_dict


def builtin_themes() -> Dict[str, BX1Theme]:
    presets = [
        BX1Theme("clean_light", "Clean Light", "light", "#2667ff", "#00a6a6", "#eef3f8", "#d9e7f4", "#ffffff", "#f5f8fb", "#17212b", "#5d6b7a", "#c9d4df", "#a15c00", "#b42318", "#12805c", 18, 10, 10, 12, 18, 245, False, 10, "filled", ["#2667ff", "#00a6a6", "#a15c00", "#7c3aed"], "solid", True, "Bright, readable office theme."),
        BX1Theme("graphite_glass", "Graphite Glass", "dark", "#8ab4ff", "#67e8f9", "#0b1118", "#101820", "#151f29", "#1b2935", "#edf5fb", "#9aa9b7", "#324656", "#f59e0b", "#ef4444", "#22c55e", 18, 10, 10, 14, 42, 220, True, 12, "filled", ["#8ab4ff", "#67e8f9", "#f59e0b", "#c084fc"], "gradient", True, "Soft dark glass with restrained colour."),
        BX1Theme("engineering_blue", "Engineering Blue", "dark", "#45a3ff", "#5eead4", "#071b2d", "#0b2235", "#102b40", "#17364e", "#e8f6ff", "#9fb8ca", "#2b5269", "#facc15", "#fb7185", "#4ade80", 18, 10, 10, 12, 34, 232, True, 10, "filled", ["#45a3ff", "#5eead4", "#facc15", "#38bdf8"], "gradient", True, "BX1 blue dashboard theme."),
        BX1Theme("bx1_neon", "BX1 Neon", "dark", "#22d3ee", "#a3e635", "#050814", "#08111f", "#0b1727", "#111f34", "#f0fbff", "#9bb4c7", "#263850", "#fde047", "#f43f5e", "#84cc16", 20, 10, 11, 16, 58, 210, True, 14, "filled", ["#22d3ee", "#a3e635", "#f43f5e", "#a78bfa"], "gradient", True, "High-energy neon accent theme."),
        BX1Theme("workshop", "Workshop", "dark", "#16a34a", "#86efac", "#07130e", "#0b1b13", "#0f2419", "#173423", "#e5fff1", "#9bb8a5", "#27553b", "#fde047", "#f87171", "#22c55e", 17, 10, 9, 10, 22, 236, False, 8, "filled", ["#16a34a", "#86efac", "#fde047", "#60a5fa"], "solid", True, "Low-glare engineering bench theme."),
        BX1Theme("midnight_gold", "Midnight Gold", "dark", "#f59e0b", "#facc15", "#090b12", "#121621", "#191f2d", "#242b3a", "#fff8e8", "#c8b98e", "#4a3b20", "#fb923c", "#ef4444", "#22c55e", 18, 10, 10, 13, 38, 224, True, 12, "filled", ["#f59e0b", "#facc15", "#60a5fa", "#c084fc"], "gradient", True, "Dark navy panels with gold signal accents."),
    ]
    return {theme.theme_id: theme for theme in presets}


class ThemeManager:
    def __init__(self, themes_dir: Path) -> None:
        self.themes_dir = Path(themes_dir)
        self._builtins = builtin_themes()

    def load_all(self) -> Dict[str, BX1Theme]:
        themes = dict(self._builtins)
        if self.themes_dir.exists():
            for path in sorted(self.themes_dir.glob("*.json")):
                try:
                    theme = self.load_file(path)
                except Exception:
                    continue
                themes[theme.theme_id] = theme
        return themes

    def load_theme(self, theme_id: str, *, fallback: str = "clean_light") -> BX1Theme:
        themes = self.load_all()
        return themes.get(theme_id) or themes[fallback]

    def load_file(self, path: Path) -> BX1Theme:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_theme_dict(data)

    def save_custom(self, theme: BX1Theme, *, overwrite: bool = False) -> Path:
        if theme.theme_id in self._builtins and self._builtins[theme.theme_id].protected:
            raise ValueError("Built-in presets are protected. Use Save As or Duplicate.")
        self.themes_dir.mkdir(parents=True, exist_ok=True)
        path = self.themes_dir / f"{theme.theme_id}.json"
        if path.exists() and not overwrite:
            raise FileExistsError(f"Theme already exists: {theme.theme_id}")
        path.write_text(json.dumps(theme.to_dict(), indent=2), encoding="utf-8")
        return path

    def delete_custom(self, theme_id: str) -> None:
        if theme_id in self._builtins and self._builtins[theme_id].protected:
            raise ValueError("Built-in presets cannot be deleted.")
        path = self.themes_dir / f"{theme_id}.json"
        if path.exists():
            path.unlink()

    def duplicate(self, source_id: str, new_id: str, display_name: str) -> BX1Theme:
        source = self.load_theme(source_id)
        data = source.to_dict()
        data.update({"theme_id": new_id, "display_name": display_name, "protected": False})
        return validate_theme_dict(data)

    def export_theme(self, theme_id: str, output_path: Path) -> Path:
        theme = self.load_theme(theme_id)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(theme.to_dict(), indent=2), encoding="utf-8")
        return output_path

    def import_theme(self, input_path: Path, *, overwrite: bool = False) -> Path:
        theme = self.load_file(input_path)
        if theme.theme_id in self._builtins:
            theme = validate_theme_dict({**theme.to_dict(), "theme_id": f"{theme.theme_id}_custom", "protected": False})
        return self.save_custom(theme, overwrite=overwrite)

    def apply_to_brain_config(self, config_path: Path, theme_id: str) -> None:
        themes = self.load_all()
        if theme_id not in themes:
            raise ValueError(f"Unknown theme: {theme_id}")
        path = Path(config_path)
        data: Dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        data["ui_style_preset"] = theme_id
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def theme_to_legacy_palette(theme: BX1Theme) -> Dict[str, str]:
    bg_mid = theme.raised_card_background if theme.mode == "dark" else "#f5f8fb"
    return {
        "bg0": theme.sidebar_background,
        "bg1": theme.page_background,
        "bg2": bg_mid,
        "panel": _rgba(theme.card_background, theme.panel_transparency),
        "border": theme.border_colour,
        "text": theme.text_colour,
        "muted": theme.muted_text,
        "title": theme.text_colour,
        "input": theme.card_background,
        "input2": theme.raised_card_background,
        "accent": theme.accent_colour,
        "accent2": theme.secondary_accent,
        "primary0": theme.accent_colour,
        "primary1": _darken(theme.accent_colour, 0.35),
        "danger0": theme.error_colour,
        "danger1": _darken(theme.error_colour, 0.4),
        "tab": theme.card_background,
        "tab_selected": theme.raised_card_background,
        "hint_bg": theme.raised_card_background,
        "hint_border": theme.border_colour,
        "pill": theme.raised_card_background,
        "pill_text": theme.secondary_accent,
        "warn": theme.warning_colour,
        "navigation_font_size": str(theme.navigation_font_size),
        "navigation_icon_size": str(theme.navigation_icon_size),
        "sidebar_expanded_width": str(theme.sidebar_expanded_width),
        "sidebar_collapsed_width": str(theme.sidebar_collapsed_width),
        "navigation_item_height": str(theme.navigation_item_height),
        "chart_label_font_size": str(theme.chart_label_font_size),
        "dashboard_card_spacing": str(theme.dashboard_card_spacing),
    }


def _rgba(hex_colour: str, alpha: int) -> str:
    r = int(hex_colour[1:3], 16)
    g = int(hex_colour[3:5], 16)
    b = int(hex_colour[5:7], 16)
    return f"rgba({r}, {g}, {b}, {max(0, min(255, int(alpha)))})"


def _darken(hex_colour: str, amount: float) -> str:
    parts = [int(hex_colour[i : i + 2], 16) for i in (1, 3, 5)]
    scaled = [max(0, min(255, int(part * (1.0 - amount)))) for part in parts]
    return "#" + "".join(f"{part:02x}" for part in scaled)
