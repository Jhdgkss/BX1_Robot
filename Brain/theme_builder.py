from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bx1_ui.chart_widgets import SparklineChart
from bx1_ui.preview_widgets import ThemePreviewPanel
from bx1_ui.theme_manager import ThemeManager
from bx1_ui.theme_schema import BX1Theme, accessibility_status, validate_theme_dict


APP_DIR = Path(__file__).resolve().parent
THEMES_DIR = APP_DIR / "themes"
CONFIG_PATH = APP_DIR / "config" / "app_config.json"


class ThemeBuilderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.manager = ThemeManager(THEMES_DIR)
        self.themes: Dict[str, BX1Theme] = self.manager.load_all()
        self.current_theme = self.themes.get("engineering_blue") or next(iter(self.themes.values()))
        self.setWindowTitle("BX1 Theme Builder")
        self.resize(1180, 760)
        self._build_ui()
        self.load_theme_into_form(self.current_theme.theme_id)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        left = QVBoxLayout()
        title = QLabel("BX1 Theme Builder")
        title.setObjectName("Title")
        self.preset_list = QListWidget()
        self.refresh_presets()
        left.addWidget(title)
        left.addWidget(QLabel("Preset gallery"))
        left.addWidget(self.preset_list, 1)
        layout.addLayout(left, 1)

        center = QVBoxLayout()
        identity = QGroupBox("Theme identity")
        identity_form = QFormLayout(identity)
        self.theme_id_edit = QLineEdit()
        self.display_name_edit = QLineEdit()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["dark", "light"])
        identity_form.addRow("Theme ID", self.theme_id_edit)
        identity_form.addRow("Display name", self.display_name_edit)
        identity_form.addRow("Mode", self.mode_combo)
        center.addWidget(identity)

        colours = QGroupBox("Colour controls")
        colour_grid = QGridLayout(colours)
        self.colour_buttons: Dict[str, QPushButton] = {}
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
        for index, field in enumerate(colour_fields):
            button = QPushButton(field.replace("_", " ").title())
            button.clicked.connect(lambda _checked=False, f=field: self.pick_colour(f))
            self.colour_buttons[field] = button
            colour_grid.addWidget(button, index // 3, index % 3)
        center.addWidget(colours)

        controls = QGroupBox("Typography, spacing and panels")
        form = QFormLayout(controls)
        self.title_size_spin = self.spin(10, 36)
        self.body_size_spin = self.spin(8, 18)
        self.spacing_spin = self.spin(4, 24)
        self.radius_spin = self.spin(0, 28)
        self.shadow_spin = self.spin(0, 100)
        self.transparency_spin = self.spin(80, 255)
        self.button_radius_spin = self.spin(0, 28)
        self.navigation_font_spin = self.spin(11, 18)
        self.navigation_icon_spin = self.spin(12, 24)
        self.sidebar_expanded_spin = self.spin(200, 280)
        self.sidebar_collapsed_spin = self.spin(56, 96)
        self.navigation_height_spin = self.spin(38, 58)
        self.chart_label_spin = self.spin(10, 18)
        self.dashboard_spacing_spin = self.spin(6, 20)
        self.glass_check = QCheckBox("Glass effect")
        self.table_style_combo = QComboBox()
        self.table_style_combo.addItems(["filled", "outline", "minimal"])
        self.progress_combo = QComboBox()
        self.progress_combo.addItems(["gradient", "solid", "segmented"])
        for label, widget in (
            ("Title font size", self.title_size_spin),
            ("Body font size", self.body_size_spin),
            ("Spacing scale", self.spacing_spin),
            ("Border radius", self.radius_spin),
            ("Shadow strength", self.shadow_spin),
            ("Panel transparency", self.transparency_spin),
            ("Button radius", self.button_radius_spin),
            ("Navigation font size", self.navigation_font_spin),
            ("Navigation icon size", self.navigation_icon_spin),
            ("Sidebar expanded width", self.sidebar_expanded_spin),
            ("Sidebar collapsed width", self.sidebar_collapsed_spin),
            ("Navigation item height", self.navigation_height_spin),
            ("Chart label font size", self.chart_label_spin),
            ("Dashboard card spacing", self.dashboard_spacing_spin),
            ("Glass", self.glass_check),
            ("Table header", self.table_style_combo),
            ("Progress bars", self.progress_combo),
        ):
            form.addRow(label, widget)
        center.addWidget(controls)

        buttons = QHBoxLayout()
        for text, callback in (
            ("Save", self.save_theme),
            ("Save As", self.save_as_theme),
            ("Duplicate", self.duplicate_theme),
            ("Import", self.import_theme),
            ("Export", self.export_theme),
            ("Delete Custom", self.delete_theme),
            ("Restore Preset", self.restore_preset),
            ("Apply to Brain", self.apply_to_brain),
        ):
            button = QPushButton(text)
            if text in {"Save", "Apply to Brain"}:
                button.setObjectName("PrimaryButton")
            button.clicked.connect(callback)
            buttons.addWidget(button)
        center.addLayout(buttons)
        layout.addLayout(center, 2)

        right = QVBoxLayout()
        self.preview = ThemePreviewPanel()
        self.accessibility_label = QLabel("Contrast status")
        self.chart_preview = SparklineChart("Chart preview", "Preview data")
        self.chart_preview.set_values([1, 3, 2, 5, 4, 7, 6])
        right.addWidget(self.preview, 2)
        right.addWidget(self.accessibility_label)
        right.addWidget(self.chart_preview, 1)
        layout.addLayout(right, 2)

        self.preset_list.currentItemChanged.connect(lambda item: self.load_theme_into_form(str(item.data(256))) if item else None)
        for widget in (self.theme_id_edit, self.display_name_edit, self.mode_combo, self.title_size_spin, self.body_size_spin, self.spacing_spin, self.radius_spin, self.shadow_spin, self.transparency_spin, self.button_radius_spin, self.navigation_font_spin, self.navigation_icon_spin, self.sidebar_expanded_spin, self.sidebar_collapsed_spin, self.navigation_height_spin, self.chart_label_spin, self.dashboard_spacing_spin, self.glass_check, self.table_style_combo, self.progress_combo):
            signal = getattr(widget, "textChanged", None) or getattr(widget, "currentIndexChanged", None) or getattr(widget, "valueChanged", None) or getattr(widget, "toggled", None)
            if signal:
                signal.connect(self.update_preview)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #eef4fb; color: #17212b; font-family: Segoe UI, Arial; }
            QListWidget, QLineEdit, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #c9d4df; border-radius: 8px; padding: 6px; }
            QGroupBox { background: rgba(255,255,255,220); border: 1px solid #c9d4df; border-radius: 12px; margin-top: 16px; padding: 12px; font-weight: 650; }
            QPushButton { background: #e7eef7; border: 1px solid #c9d4df; border-radius: 9px; padding: 8px 10px; }
            QPushButton#PrimaryButton { background: #2667ff; color: white; }
            QLabel#Title { font-size: 20pt; font-weight: 750; }
            """
        )

    def spin(self, low: int, high: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        return spin

    def refresh_presets(self) -> None:
        self.preset_list.clear()
        self.themes = self.manager.load_all()
        for theme in sorted(self.themes.values(), key=lambda item: item.display_name):
            label = theme.display_name + ("  [preset]" if theme.protected else "  [custom]")
            item = QListWidgetItem(label)
            item.setData(256, theme.theme_id)
            self.preset_list.addItem(item)

    def load_theme_into_form(self, theme_id: str) -> None:
        self.current_theme = self.themes[theme_id]
        theme = self.current_theme
        self.theme_id_edit.setText(theme.theme_id)
        self.display_name_edit.setText(theme.display_name)
        self.mode_combo.setCurrentText(theme.mode)
        for field, button in self.colour_buttons.items():
            colour = getattr(theme, field)
            button.setProperty("colour", colour)
            button.setStyleSheet(f"background:{colour}; color:{self.button_text_colour(colour)};")
        self.title_size_spin.setValue(theme.title_font_size)
        self.body_size_spin.setValue(theme.body_font_size)
        self.spacing_spin.setValue(theme.spacing_scale)
        self.radius_spin.setValue(theme.border_radius)
        self.shadow_spin.setValue(theme.shadow_strength)
        self.transparency_spin.setValue(theme.panel_transparency)
        self.button_radius_spin.setValue(theme.button_radius)
        self.navigation_font_spin.setValue(theme.navigation_font_size)
        self.navigation_icon_spin.setValue(theme.navigation_icon_size)
        self.sidebar_expanded_spin.setValue(theme.sidebar_expanded_width)
        self.sidebar_collapsed_spin.setValue(theme.sidebar_collapsed_width)
        self.navigation_height_spin.setValue(theme.navigation_item_height)
        self.chart_label_spin.setValue(theme.chart_label_font_size)
        self.dashboard_spacing_spin.setValue(theme.dashboard_card_spacing)
        self.glass_check.setChecked(theme.glass_effect)
        self.table_style_combo.setCurrentText(theme.table_header_style)
        self.progress_combo.setCurrentText(theme.progress_bar_style)
        self.update_preview()

    def theme_from_form(self) -> BX1Theme:
        base = self.current_theme.to_dict()
        base.update({
            "theme_id": self.theme_id_edit.text().strip(),
            "display_name": self.display_name_edit.text().strip(),
            "mode": self.mode_combo.currentText(),
            "title_font_size": self.title_size_spin.value(),
            "body_font_size": self.body_size_spin.value(),
            "spacing_scale": self.spacing_spin.value(),
            "border_radius": self.radius_spin.value(),
            "shadow_strength": self.shadow_spin.value(),
            "panel_transparency": self.transparency_spin.value(),
            "glass_effect": self.glass_check.isChecked(),
            "button_radius": self.button_radius_spin.value(),
            "navigation_font_size": self.navigation_font_spin.value(),
            "navigation_icon_size": self.navigation_icon_spin.value(),
            "sidebar_expanded_width": self.sidebar_expanded_spin.value(),
            "sidebar_collapsed_width": self.sidebar_collapsed_spin.value(),
            "navigation_item_height": self.navigation_height_spin.value(),
            "chart_label_font_size": self.chart_label_spin.value(),
            "dashboard_card_spacing": self.dashboard_spacing_spin.value(),
            "table_header_style": self.table_style_combo.currentText(),
            "progress_bar_style": self.progress_combo.currentText(),
            "protected": False,
        })
        for field, button in self.colour_buttons.items():
            base[field] = str(button.property("colour") or getattr(self.current_theme, field))
        return validate_theme_dict(base)

    def update_preview(self) -> None:
        try:
            theme = self.theme_from_form()
            self.preview.apply_theme(theme)
            status = accessibility_status(theme)
            self.accessibility_label.setText(f"Contrast: body {status['body_contrast']} | accent {status['accent_contrast']}")
        except Exception as exc:
            self.accessibility_label.setText(f"Theme validation error: {exc}")

    def pick_colour(self, field: str) -> None:
        current = str(self.colour_buttons[field].property("colour") or "#45a3ff")
        colour = QColorDialog.getColor(QColor(current), self, field.replace("_", " ").title())
        if colour.isValid():
            value = colour.name()
            self.colour_buttons[field].setProperty("colour", value)
            self.colour_buttons[field].setStyleSheet(f"background:{value}; color:{self.button_text_colour(value)};")
            self.update_preview()

    def save_theme(self) -> None:
        try:
            path = self.manager.save_custom(self.theme_from_form(), overwrite=True)
            self.refresh_presets()
            QMessageBox.information(self, "Theme Builder", f"Saved theme:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Theme Builder", str(exc))

    def save_as_theme(self) -> None:
        self.theme_id_edit.setText(self.theme_id_edit.text().strip() + "_custom")
        self.save_theme()

    def duplicate_theme(self) -> None:
        try:
            duplicate = self.manager.duplicate(self.current_theme.theme_id, self.current_theme.theme_id + "_copy", self.current_theme.display_name + " Copy")
            path = self.manager.save_custom(duplicate, overwrite=True)
            self.refresh_presets()
            QMessageBox.information(self, "Theme Builder", f"Duplicated theme:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Theme Builder", str(exc))

    def import_theme(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import theme", str(THEMES_DIR), "Theme JSON (*.json)")
        if path:
            try:
                self.manager.import_theme(Path(path), overwrite=True)
                self.refresh_presets()
            except Exception as exc:
                QMessageBox.warning(self, "Theme Builder", str(exc))

    def export_theme(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export theme", str(THEMES_DIR / f"{self.current_theme.theme_id}.json"), "Theme JSON (*.json)")
        if path:
            self.manager.export_theme(self.current_theme.theme_id, Path(path))

    def delete_theme(self) -> None:
        try:
            self.manager.delete_custom(self.current_theme.theme_id)
            self.refresh_presets()
        except Exception as exc:
            QMessageBox.warning(self, "Theme Builder", str(exc))

    def restore_preset(self) -> None:
        self.load_theme_into_form(self.current_theme.theme_id)

    def apply_to_brain(self) -> None:
        try:
            theme = self.theme_from_form()
            if not theme.protected:
                self.manager.save_custom(theme, overwrite=True)
            self.manager.apply_to_brain_config(CONFIG_PATH, theme.theme_id)
            QMessageBox.information(self, "Theme Builder", "Theme selected for Brain. Restart Brain or apply the theme from Settings.")
        except Exception as exc:
            QMessageBox.warning(self, "Theme Builder", str(exc))

    def button_text_colour(self, hex_colour: str) -> str:
        value = int(hex_colour.lstrip("#"), 16)
        r = (value >> 16) & 255
        g = (value >> 8) & 255
        b = value & 255
        return "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 150 else "#ffffff"


def main() -> int:
    app = QApplication(sys.argv)
    window = ThemeBuilderWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
