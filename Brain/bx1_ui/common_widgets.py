from __future__ import annotations

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
except Exception:  # pragma: no cover - imported in non-GUI unit tests
    Qt = None  # type: ignore
    QFrame = QLabel = QVBoxLayout = QWidget = object  # type: ignore


def make_status_card(title: str, value: str, detail: str = "") -> QWidget:
    card = QFrame()
    card.setObjectName("StatusCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("StatusCardTitle")
    value_label = QLabel(value)
    value_label.setObjectName("StatusCardValue")
    detail_label = QLabel(detail)
    detail_label.setObjectName("StatusCardDetail")
    detail_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(value_label)
    layout.addWidget(detail_label)
    return card

