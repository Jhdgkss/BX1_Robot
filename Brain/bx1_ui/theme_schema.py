from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class BX1Theme:
    theme_id: str
    display_name: str
    mode: str = "dark"
    accent_colour: str = "#45a3ff"
    secondary_accent: str = "#5eead4"
    page_background: str = "#071017"
    sidebar_background: str = "#0b1721"
    card_background: str = "#111b24"
    raised_card_background: str = "#162430"
    text_colour: str = "#e8f1f7"
    muted_text: str = "#8fa2af"
    border_colour: str = "#29404f"
    warning_colour: str = "#f59e0b"
    error_colour: str = "#ef4444"
    success_colour: str = "#22c55e"
    title_font_size: int = 18
    body_font_size: int = 10
    spacing_scale: int = 10
    border_radius: int = 12
    shadow_strength: int = 30
    panel_transparency: int = 235
    glass_effect: bool = True
    button_radius: int = 10
    table_header_style: str = "filled"
    chart_palette: List[str] = field(default_factory=lambda: ["#45a3ff", "#5eead4", "#f59e0b", "#a78bfa"])
    progress_bar_style: str = "gradient"
    protected: bool = False
    description: str = ""
    navigation_font_size: int = 14
    navigation_icon_size: int = 16
    sidebar_expanded_width: int = 232
    sidebar_collapsed_width: int = 74
    navigation_item_height: int = 44
    chart_label_font_size: int = 12
    dashboard_card_spacing: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


REQUIRED_THEME_FIELDS = {
    "theme_id",
    "display_name",
    "mode",
    "accent_colour",
    "secondary_accent",
    "page_background",
    "sidebar_background",
    "card_background",
    "raised_card_background",
    "text_colour",
    "muted_text",
    "border_colour",
    "warning_colour",
    "error_colour",
    "success_colour",
    "title_font_size",
    "body_font_size",
    "spacing_scale",
    "border_radius",
    "shadow_strength",
    "panel_transparency",
    "glass_effect",
    "button_radius",
    "table_header_style",
    "chart_palette",
    "progress_bar_style",
}


def relative_luminance(hex_colour: str) -> float:
    colour = _require_hex(hex_colour)
    values = [int(colour[i : i + 2], 16) / 255.0 for i in (1, 3, 5)]
    adjusted = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return 0.2126 * adjusted[0] + 0.7152 * adjusted[1] + 0.0722 * adjusted[2]


def contrast_ratio(foreground: str, background: str) -> float:
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter = max(first, second)
    darker = min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def validate_theme_dict(data: Dict[str, Any]) -> BX1Theme:
    if not isinstance(data, dict):
        raise ValueError("Theme must be a JSON object.")
    defaults = BX1Theme("default_theme", "Default Theme").to_dict()
    normalized = {**defaults, **data}
    missing = sorted(REQUIRED_THEME_FIELDS.difference(normalized))
    if missing:
        raise ValueError("Theme is missing fields: " + ", ".join(missing))
    theme_id = str(normalized.get("theme_id") or "").strip()
    if not re.match(r"^[a-z0-9][a-z0-9_\-]{1,63}$", theme_id):
        raise ValueError("Theme ID must use lowercase letters, numbers, hyphen or underscore.")
    mode = str(normalized.get("mode") or "").lower()
    if mode not in {"light", "dark"}:
        raise ValueError("Theme mode must be light or dark.")
    colour_fields = [
        "accent_colour",
        "secondary_accent",
        "page_background",
        "sidebar_background",
        "card_background",
        "raised_card_background",
        "text_colour",
        "muted_text",
        "border_colour",
        "warning_colour",
        "error_colour",
        "success_colour",
    ]
    for field_name in colour_fields:
        _require_hex(str(normalized.get(field_name) or ""), field_name)
    chart_palette = normalized.get("chart_palette")
    if not isinstance(chart_palette, list) or not chart_palette:
        raise ValueError("chart_palette must be a non-empty list.")
    for colour in chart_palette:
        _require_hex(str(colour), "chart_palette")
    numeric_ranges = {
        "title_font_size": (10, 36),
        "body_font_size": (8, 18),
        "spacing_scale": (4, 24),
        "border_radius": (0, 28),
        "shadow_strength": (0, 100),
        "panel_transparency": (80, 255),
        "button_radius": (0, 28),
        "navigation_font_size": (11, 18),
        "navigation_icon_size": (12, 24),
        "sidebar_expanded_width": (200, 280),
        "sidebar_collapsed_width": (56, 96),
        "navigation_item_height": (38, 58),
        "chart_label_font_size": (10, 18),
        "dashboard_card_spacing": (6, 20),
    }
    for field_name, (low, high) in numeric_ranges.items():
        value = int(normalized.get(field_name))
        if value < low or value > high:
            raise ValueError(f"{field_name} must be between {low} and {high}.")
        normalized[field_name] = value
    normalized["glass_effect"] = bool(normalized.get("glass_effect"))
    normalized["chart_palette"] = [str(colour) for colour in chart_palette]
    normalized["protected"] = bool(normalized.get("protected", False))
    normalized["description"] = str(normalized.get("description") or "")
    return BX1Theme(**{key: normalized[key] for key in BX1Theme.__dataclass_fields__.keys() if key in normalized})


def accessibility_status(theme: BX1Theme) -> Dict[str, Any]:
    body = contrast_ratio(theme.text_colour, theme.card_background)
    muted = contrast_ratio(theme.muted_text, theme.card_background)
    accent = contrast_ratio(theme.accent_colour, theme.card_background)
    return {
        "body_contrast": round(body, 2),
        "muted_contrast": round(muted, 2),
        "accent_contrast": round(accent, 2),
        "passes_body_text": body >= 4.5,
        "passes_large_accent": accent >= 3.0,
    }


def _require_hex(value: str, field_name: str = "colour") -> str:
    if not HEX_RE.match(value):
        raise ValueError(f"{field_name} must be a #RRGGBB colour.")
    return value
