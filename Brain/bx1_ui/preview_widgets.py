from __future__ import annotations

try:
    from PyQt6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget
except Exception:  # pragma: no cover
    QGridLayout = QLabel = QPushButton = QVBoxLayout = QWidget = object  # type: ignore

from bx1_ui.theme_manager import theme_to_legacy_palette
from bx1_ui.theme_schema import BX1Theme, accessibility_status


class ThemePreviewPanel(QWidget):  # type: ignore[misc]
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ThemePreviewPanel")
        layout = QVBoxLayout(self)
        self.title = QLabel("Theme preview")
        self.status = QLabel("Select a preset or adjust controls.")
        self.primary = QPushButton("Primary action")
        self.secondary = QPushButton("Secondary")
        self.cards = QGridLayout()
        for index, label in enumerate(("Brain", "Robot", "Voice", "Latency")):
            card = QLabel(f"{label}\nReady")
            card.setObjectName("MissionCard")
            self.cards.addWidget(card, index // 2, index % 2)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addLayout(self.cards)
        layout.addWidget(self.primary)
        layout.addWidget(self.secondary)

    def apply_theme(self, theme: BX1Theme) -> None:
        palette = theme_to_legacy_palette(theme)
        contrast = accessibility_status(theme)
        self.status.setText(f"{theme.display_name} - body contrast {contrast['body_contrast']}")
        self.setStyleSheet(
            f"""
            QWidget#ThemePreviewPanel {{ background: {palette['bg1']}; color: {palette['text']}; border: 1px solid {palette['border']}; border-radius: {theme.border_radius}px; }}
            QLabel {{ color: {palette['text']}; padding: 6px; }}
            QLabel#MissionCard {{ background: {palette['input']}; border: 1px solid {palette['border']}; border-radius: {theme.border_radius}px; }}
            QPushButton {{ background: {palette['tab_selected']}; color: {palette['title']}; border: 1px solid {palette['border']}; border-radius: {theme.button_radius}px; padding: 8px; }}
            """
        )
