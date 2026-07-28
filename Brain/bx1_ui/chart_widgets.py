from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List, Tuple

try:
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QPainter, QPen
    from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
except Exception:  # pragma: no cover
    QRectF = Qt = QColor = QPainter = QPen = QFrame = QLabel = QVBoxLayout = QWidget = None  # type: ignore


def format_metric(value: float | int | None, unit: str = "", precision: int = 1) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except Exception:
        return "n/a"
    if unit == "%":
        return f"{number:.0f}%"
    if unit == "ms":
        return f"{number:.0f} ms"
    if unit == "s":
        return f"{number:.{precision}f} s"
    if unit:
        return f"{number:.{precision}f} {unit}"
    return f"{number:.{precision}f}"


class BoundedTelemetryHistory:
    def __init__(self, limit: int = 120) -> None:
        self.limit = max(1, int(limit or 120))
        self.samples: Deque[dict] = deque(maxlen=self.limit)

    def add(self, sample: dict) -> None:
        self.samples.append(dict(sample or {}))

    def values(self, key: str) -> List[float]:
        values: List[float] = []
        for sample in self.samples:
            try:
                values.append(float(sample.get(key) or 0.0))
            except Exception:
                values.append(0.0)
        return values

    def __len__(self) -> int:
        return len(self.samples)


class SparklineChart(QWidget):  # type: ignore[misc]
    def __init__(self, title: str = "", empty_text: str = "No data yet", parent=None) -> None:
        super().__init__(parent)
        self.title = title
        self.empty_text = empty_text or "Waiting for data"
        self.values: List[float] = []
        self.colour = "#45a3ff"
        self.draws_title_in_plot = False
        self.plot_padding = 14
        self.setMinimumHeight(128)
        self.setMinimumWidth(220)

    def set_values(self, values: Iterable[float], *, colour: str = "#45a3ff") -> None:
        self.values = [float(value) for value in values]
        self.colour = colour
        try:
            self.update()
        except RuntimeError:
            pass

    def paintEvent(self, _event) -> None:  # pragma: no cover - visual Qt path
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor("#29404f"), 1))
        painter.drawRoundedRect(QRectF(rect), 8, 8)
        chart_rect = rect.adjusted(self.plot_padding, self.plot_padding, -self.plot_padding, -self.plot_padding)
        if not self.values:
            painter.setPen(QColor("#5f7180"))
            painter.drawText(chart_rect, int(Qt.AlignmentFlag.AlignCenter), self.empty_text)
            return
        low = min(self.values)
        high = max(self.values)
        spread = high - low or 1.0
        step = chart_rect.width() / max(1, len(self.values) - 1)
        points: List[Tuple[float, float]] = []
        for index, value in enumerate(self.values):
            x = chart_rect.left() + index * step
            y = chart_rect.bottom() - ((value - low) / spread) * chart_rect.height()
            points.append((x, y))
        painter.setPen(QPen(QColor(self.colour), 2))
        for first, second in zip(points, points[1:]):
            painter.drawLine(int(first[0]), int(first[1]), int(second[0]), int(second[1]))


class MetricChartCard(QFrame):  # type: ignore[misc]
    def __init__(self, title: str, empty_text: str = "Waiting for data", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("MetricChartCard")
        self.setMinimumHeight(190)
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("ChartCardTitle")
        self.value_label = QLabel("Waiting for data")
        self.value_label.setObjectName("ChartCardValue")
        self.chart = SparklineChart(title, empty_text)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.chart, 1)

    def set_values(self, values: Iterable[float], *, value_text: str = "", colour: str = "#45a3ff") -> None:
        values = [float(value) for value in values]
        self.value_label.setText(value_text or ("Waiting for data" if not values else format_metric(values[-1])))
        self.chart.set_values(values, colour=colour)
