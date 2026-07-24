from __future__ import annotations

try:
    from PyQt6.QtWidgets import QLabel, QWidget
except Exception:  # pragma: no cover
    QLabel = QWidget = object  # type: ignore


def set_toast(label: QLabel, message: str, *, level: str = "info") -> None:
    label.setProperty("toastLevel", level)
    label.setText(message)
    label.setVisible(bool(message))

