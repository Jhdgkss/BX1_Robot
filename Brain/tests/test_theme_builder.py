from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_ui.chart_widgets import BoundedTelemetryHistory, SparklineChart, format_metric
from bx1_ui.theme_manager import ThemeManager, builtin_themes, theme_to_legacy_palette
from bx1_ui.theme_schema import accessibility_status, contrast_ratio, validate_theme_dict


class ThemeBuilderTests(unittest.TestCase):
    def test_theme_schema_validation(self) -> None:
        theme = builtin_themes()["engineering_blue"]
        loaded = validate_theme_dict(theme.to_dict())
        self.assertEqual(loaded.theme_id, "engineering_blue")
        bad = theme.to_dict()
        bad["accent_colour"] = "blue"
        with self.assertRaises(ValueError):
            validate_theme_dict(bad)

    def test_theme_schema_older_saved_theme_gets_layout_defaults(self) -> None:
        old_theme = builtin_themes()["engineering_blue"].to_dict()
        for key in ("navigation_font_size", "navigation_icon_size", "sidebar_expanded_width", "sidebar_collapsed_width", "navigation_item_height", "chart_label_font_size", "dashboard_card_spacing"):
            old_theme.pop(key, None)
        loaded = validate_theme_dict(old_theme)
        self.assertGreaterEqual(loaded.navigation_font_size, 13)
        self.assertGreaterEqual(loaded.sidebar_expanded_width, 220)
        self.assertGreaterEqual(loaded.navigation_item_height, 40)

    def test_builtin_preset_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ThemeManager(Path(tmp))
            themes = manager.load_all()
            for theme_id in ("clean_light", "graphite_glass", "engineering_blue", "bx1_neon", "workshop", "midnight_gold"):
                self.assertIn(theme_id, themes)
                self.assertTrue(themes[theme_id].protected)

    def test_malformed_theme_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.json").write_text("{bad", encoding="utf-8")
            manager = ThemeManager(root)
            theme = manager.load_theme("missing_theme", fallback="clean_light")
            self.assertEqual(theme.theme_id, "clean_light")

    def test_custom_theme_save_load_import_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ThemeManager(Path(tmp) / "themes")
            theme = manager.duplicate("engineering_blue", "engineering_blue_custom", "Engineering Blue Custom")
            path = manager.save_custom(theme, overwrite=True)
            loaded = manager.load_file(path)
            self.assertEqual(loaded.theme_id, "engineering_blue_custom")
            exported = manager.export_theme("engineering_blue_custom", Path(tmp) / "export.json")
            imported_path = ThemeManager(Path(tmp) / "other").import_theme(exported)
            self.assertTrue(imported_path.exists())

    def test_protected_preset_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ThemeManager(Path(tmp))
            with self.assertRaises(ValueError):
                manager.delete_custom("clean_light")

    def test_contrast_calculation(self) -> None:
        self.assertGreater(contrast_ratio("#ffffff", "#000000"), 20)
        status = accessibility_status(builtin_themes()["engineering_blue"])
        self.assertTrue(status["passes_body_text"])

    def test_dashboard_metric_formatting_and_bounded_history(self) -> None:
        self.assertEqual(format_metric(1.234, "s"), "1.2 s")
        self.assertEqual(format_metric(42, "%"), "42%")
        history = BoundedTelemetryHistory(limit=3)
        for value in range(5):
            history.add({"total_s": value})
        self.assertEqual(len(history), 3)
        self.assertEqual(history.values("total_s"), [2.0, 3.0, 4.0])

    def test_empty_chart_accepts_no_values(self) -> None:
        chart = SparklineChart.__new__(SparklineChart)
        chart.values = []
        SparklineChart.set_values(chart, [], colour="#45a3ff")
        self.assertEqual(chart.values, [])

    def test_chart_layout_properties_keep_title_outside_plot(self) -> None:
        chart = SparklineChart.__new__(SparklineChart)
        chart.values = []
        chart.draws_title_in_plot = False
        chart.plot_padding = 14
        self.assertFalse(chart.draws_title_in_plot)
        self.assertGreaterEqual(chart.plot_padding, 12)

    def test_theme_application_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "app_config.json"
            manager = ThemeManager(Path(tmp) / "themes")
            manager.apply_to_brain_config(config, "engineering_blue")
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(data["ui_style_preset"], "engineering_blue")
            legacy = theme_to_legacy_palette(manager.load_theme("engineering_blue"))
            self.assertIn("bg0", legacy)
            self.assertIn("accent", legacy)
            self.assertGreaterEqual(int(legacy["navigation_font_size"]), 13)
            self.assertGreaterEqual(int(legacy["sidebar_expanded_width"]), 220)


if __name__ == "__main__":
    unittest.main()
