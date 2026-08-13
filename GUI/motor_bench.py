"""BX1 motor commissioning and balance-analysis GUI.

Presentation only:
    GUI -> GUIController -> Master_Main_GUI.py -> Robot API -> LEO

This widget never talks directly to robot hardware or sockets.
"""

from __future__ import annotations

import csv
import math
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class CombinedCommissioningPlot(QWidget):
    """One shared time plot for motor RPM, balance angle and encoder movement.

    Left axis       : wheel RPM
    Right axis      : robot angle error in degrees
    Outer-right axis: relative encoder movement in counts

    All three axes are symmetric around zero so the centre horizontal line has
    the same physical meaning for every series.  Encoder values are plotted as
    movement relative to the first encoder sample after a chart clear, rather
    than as the MKS drive's large cumulative absolute position.
    """

    SPEED_NAMES = ("Left cmd", "Right cmd", "Left actual", "Right actual")
    ENCODER_NAMES = ("Left encoder Δ", "Right encoder Δ")

    SERIES_COLOURS = {
        "Left cmd": QColor("#2f80ed"),
        "Right cmd": QColor("#f2994a"),
        "Left actual": QColor("#9b51e0"),
        "Right actual": QColor("#56ccf2"),
        "Robot angle": QColor("#27ae60"),
        "Left encoder Δ": QColor("#eb5757"),
        "Right encoder Δ": QColor("#f2c94c"),
    }

    def __init__(self, *, window_seconds: int = 30, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.window_seconds = max(5, int(window_seconds))
        self._speed_series = {
            name: deque(maxlen=12000) for name in self.SPEED_NAMES
        }
        self._angle_series = {"Robot angle": deque(maxlen=12000)}
        self._encoder_series = {
            name: deque(maxlen=12000) for name in self.ENCODER_NAMES
        }
        self._markers = deque(maxlen=300)
        self.setMinimumHeight(430)

    def set_window_seconds(self, seconds: int) -> None:
        self.window_seconds = max(5, int(seconds))
        self.update()

    @staticmethod
    def _append(series_map, name: str, elapsed_s: float, value: Any) -> None:
        if name not in series_map or value is None:
            return
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(numeric):
            return
        series_map[name].append((float(elapsed_s), numeric))

    def append_speed(self, name: str, elapsed_s: float, value: Any) -> None:
        self._append(self._speed_series, name, elapsed_s, value)
        self.update()

    def append_angle(self, elapsed_s: float, value: Any) -> None:
        self._append(self._angle_series, "Robot angle", elapsed_s, value)
        self.update()

    def append_encoder(self, name: str, elapsed_s: float, value: Any) -> None:
        self._append(self._encoder_series, name, elapsed_s, value)
        self.update()

    def add_marker(self, elapsed_s: float, label: str) -> None:
        self._markers.append((float(elapsed_s), str(label)))
        self.update()

    def clear(self) -> None:
        for series_map in (
            self._speed_series,
            self._angle_series,
            self._encoder_series,
        ):
            for values in series_map.values():
                values.clear()
        self._markers.clear()
        self.update()

    @staticmethod
    def _symmetric_limit(values, minimum: float) -> float:
        if not values:
            return float(minimum)
        peak = max(abs(float(value)) for value in values)
        limit = max(float(minimum), peak * 1.18)
        if limit <= 2:
            step = 0.5
        elif limit <= 5:
            step = 1.0
        elif limit <= 20:
            step = 5.0
        elif limit <= 50:
            step = 10.0
        elif limit <= 200:
            step = 50.0
        elif limit <= 1000:
            step = 200.0
        else:
            magnitude = 10 ** max(0, int(math.floor(math.log10(limit))) - 1)
            step = 2 * magnitude
        return math.ceil(limit / step) * step

    def _visible_points(self):
        latest = 0.0
        for series_map in (
            self._speed_series,
            self._angle_series,
            self._encoder_series,
        ):
            for values in series_map.values():
                if values:
                    latest = max(latest, values[-1][0])
        if self._markers:
            latest = max(latest, self._markers[-1][0])

        x_max = max(float(self.window_seconds), latest)
        x_min = max(0.0, x_max - self.window_seconds)

        def visible_map(series_map):
            return {
                name: [(x, y) for x, y in values if x >= x_min]
                for name, values in series_map.items()
            }

        speeds = visible_map(self._speed_series)
        angles = visible_map(self._angle_series)
        encoders = visible_map(self._encoder_series)
        speed_values = [y for points in speeds.values() for _, y in points]
        angle_values = [y for points in angles.values() for _, y in points]
        encoder_values = [y for points in encoders.values() for _, y in points]
        return (
            x_min,
            x_max,
            speeds,
            angles,
            encoders,
            speed_values,
            angle_values,
            encoder_values,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        palette = self.palette()
        text_colour = palette.text().color()
        muted = QColor(text_colour)
        muted.setAlpha(155)
        grid = QColor(text_colour)
        grid.setAlpha(38)
        border = QColor(text_colour)
        border.setAlpha(75)

        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        # Extra room on the right for angle and encoder axes.
        plot = outer.adjusted(76, 72, -152, -34)

        painter.setPen(QPen(text_colour))
        painter.drawText(
            QRectF(8, 4, self.width() - 16, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Balance response — angle, wheel speed and encoder movement",
        )
        painter.setPen(QPen(muted))
        painter.drawText(
            QRectF(5, 26, self.width() - 10, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Zero RPM, zero angle error and zero encoder movement share the centre line.",
        )

        (
            x_min,
            x_max,
            speeds,
            angles,
            encoders,
            speed_values,
            angle_values,
            encoder_values,
        ) = self._visible_points()

        # Commanded zero speed is enough to render an informative graph even
        # before measured MKS RPM/encoder readback has arrived.
        if not speed_values and not angle_values and not encoder_values:
            painter.setPen(QPen(muted))
            painter.drawText(plot, Qt.AlignCenter, "Waiting for telemetry")
            painter.setPen(QPen(border))
            painter.drawRect(plot)
            return

        speed_limit = self._symmetric_limit(speed_values, 5.0)
        angle_limit = self._symmetric_limit(angle_values, 1.0)
        encoder_limit = self._symmetric_limit(encoder_values, 50.0)

        painter.setPen(QPen(muted))
        painter.drawText(
            QRectF(plot.left() - 70, 48, 68, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Motor RPM",
        )
        painter.drawText(
            QRectF(plot.right() + 7, 48, 62, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Angle °",
        )
        painter.drawText(
            QRectF(plot.right() + 73, 48, 74, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Encoder Δ",
        )

        # Five horizontal divisions keep zero exactly at the middle division.
        for i in range(5):
            frac = i / 4.0
            y = plot.top() + frac * plot.height()
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

            rpm_value = speed_limit * (1.0 - 2.0 * frac)
            angle_value = angle_limit * (1.0 - 2.0 * frac)
            encoder_value = encoder_limit * (1.0 - 2.0 * frac)

            painter.setPen(QPen(muted))
            painter.drawText(
                QRectF(2, y - 9, 65, 18),
                Qt.AlignRight | Qt.AlignVCenter,
                f"{rpm_value:+.1f}",
            )
            painter.drawText(
                QRectF(plot.right() + 7, y - 9, 61, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{angle_value:+.2f}",
            )
            painter.drawText(
                QRectF(plot.right() + 74, y - 9, 72, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{encoder_value:+.0f}",
            )

        for i in range(6):
            frac = i / 5.0
            x = plot.left() + frac * plot.width()
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        zero_colour = QColor(text_colour)
        zero_colour.setAlpha(120)
        zero_y = plot.center().y()
        painter.setPen(QPen(zero_colour, 1.7))
        painter.drawLine(QPointF(plot.left(), zero_y), QPointF(plot.right(), zero_y))

        painter.setPen(QPen(border, 1))
        painter.drawRect(plot)

        span_x = max(0.001, x_max - x_min)

        def map_x(x: float) -> float:
            return plot.left() + (x - x_min) / span_x * plot.width()

        def map_value(x: float, y: float, limit: float) -> QPointF:
            py = plot.center().y() - (y / limit) * (plot.height() / 2.0)
            return QPointF(map_x(x), py)

        def draw_series(points, colour, style, limit):
            if not points:
                return
            path = QPainterPath()
            path.moveTo(map_value(points[0][0], points[0][1], limit))
            for x, y in points[1:]:
                path.lineTo(map_value(x, y, limit))
            painter.setPen(QPen(colour, 2.0, style))
            painter.drawPath(path)

        draw_series(speeds.get("Left cmd"), self.SERIES_COLOURS["Left cmd"], Qt.SolidLine, speed_limit)
        draw_series(speeds.get("Right cmd"), self.SERIES_COLOURS["Right cmd"], Qt.SolidLine, speed_limit)
        draw_series(speeds.get("Left actual"), self.SERIES_COLOURS["Left actual"], Qt.DashLine, speed_limit)
        draw_series(speeds.get("Right actual"), self.SERIES_COLOURS["Right actual"], Qt.DashLine, speed_limit)
        draw_series(angles.get("Robot angle"), self.SERIES_COLOURS["Robot angle"], Qt.SolidLine, angle_limit)
        draw_series(encoders.get("Left encoder Δ"), self.SERIES_COLOURS["Left encoder Δ"], Qt.DotLine, encoder_limit)
        draw_series(encoders.get("Right encoder Δ"), self.SERIES_COLOURS["Right encoder Δ"], Qt.DotLine, encoder_limit)

        # Compact two-row legend.  A line is still drawn even when a measured
        # series has no samples so the user can see which traces are expected.
        legend_items = (
            ("L cmd", "Left cmd", Qt.SolidLine),
            ("R cmd", "Right cmd", Qt.SolidLine),
            ("L actual", "Left actual", Qt.DashLine),
            ("R actual", "Right actual", Qt.DashLine),
            ("Angle", "Robot angle", Qt.SolidLine),
            ("L enc Δ", "Left encoder Δ", Qt.DotLine),
            ("R enc Δ", "Right encoder Δ", Qt.DotLine),
        )
        legend_x = plot.left() + 6
        legend_y = 54
        for label, key, style in legend_items:
            colour = self.SERIES_COLOURS[key]
            painter.setPen(QPen(colour, 2.5, style))
            painter.drawLine(QPointF(legend_x, legend_y), QPointF(legend_x + 15, legend_y))
            painter.setPen(QPen(text_colour))
            painter.drawText(
                QRectF(legend_x + 19, legend_y - 9, 70, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                label,
            )
            legend_x += 86
            if legend_x > plot.right() - 70:
                legend_x = plot.left() + 6
                legend_y += 17

        # Event markers are deliberately small top-edge tags.  The previous
        # full-height dashed marker + rotated label obscured the actual traces.
        last_label_right = -1e9
        for marker_x, marker_label in list(self._markers):
            if marker_x < x_min or marker_x > x_max:
                continue
            px = map_x(marker_x)
            colour = QColor(text_colour)
            colour.setAlpha(140)
            painter.setPen(QPen(colour, 1))
            painter.drawLine(QPointF(px, plot.top()), QPointF(px, plot.top() + 10))
            triangle = QPolygonF(
                [
                    QPointF(px - 3, plot.top()),
                    QPointF(px + 3, plot.top()),
                    QPointF(px, plot.top() + 5),
                ]
            )
            painter.setBrush(colour)
            painter.drawPolygon(triangle)
            painter.setBrush(Qt.NoBrush)

            # Avoid stacking labels on top of one another.  The marker itself is
            # always shown; labels are shown when there is enough room.
            if px > last_label_right + 42:
                short = str(marker_label)[:12]
                painter.setPen(QPen(muted))
                painter.drawText(
                    QRectF(px + 4, plot.top() + 1, 80, 16),
                    Qt.AlignLeft | Qt.AlignTop,
                    short,
                )
                last_label_right = px + min(80, 7 * len(short))

        painter.setPen(QPen(muted))
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 5, 85, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{x_min:.1f}s",
        )
        painter.drawText(
            QRectF(plot.right() - 85, plot.bottom() + 5, 85, 18),
            Qt.AlignRight | Qt.AlignVCenter,
            f"{x_max:.1f}s",
        )



def _set_action_button(button: QPushButton, role: str, height: int = 36) -> QPushButton:
    """Give commissioning controls a clear theme-aware action appearance."""
    button.setProperty("bxRole", str(role))
    button.setMinimumHeight(int(height))
    button.setCursor(Qt.PointingHandCursor)
    return button

class MotorBenchPage(QWidget):
    """Safe motor commissioning controls plus a merged live analysis plot."""

    CSV_FIELDS = [
        "wall_time",
        "elapsed_s",
        "event",
        "balance_armed",
        "fault",
        "pitch_deg",
        "zero_deg",
        "target_pitch_deg",
        "pitch_error_deg",
        "pitch_rate_dps",
        "balance_output_rpm",
        "left_command_rpm",
        "right_command_rpm",
        "left_actual_rpm",
        "right_actual_rpm",
        "left_encoder_counts",
        "right_encoder_counts",
        "left_encoder_deg",
        "right_encoder_deg",
        "movement_lean_deg",
        "steering_rpm",
    ]

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._api_connected = False
        self._recording = False
        self._display_started = time.monotonic()
        self._record_started = None
        self._records: list[Dict[str, Any]] = []
        self._latest_balance: Dict[str, Any] = {}
        self._latest_motor: Dict[str, Any] = {}
        self._last_motor_packet_monotonic = 0.0
        self._encoder_origin = {"left": None, "right": None}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        title = QLabel("Motor Commissioning / Balance Analysis")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.status_label = QLabel(
            "Robot API waiting. Motor tests require BALANCE DISARMED."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --------------------------------------------------------------
        # Upright zero / balance calibration
        # --------------------------------------------------------------
        balance_frame = QFrame()
        balance_frame.setFrameShape(QFrame.StyledPanel)
        balance_layout = QVBoxLayout(balance_frame)
        balance_heading = QLabel("UPRIGHT / BALANCE ZERO")
        balance_heading.setStyleSheet("font-weight: 800;")
        balance_layout.addWidget(balance_heading)

        balance_values = QHBoxLayout()
        self.pitch_value = QLabel("Pitch --°")
        self.zero_value = QLabel("Zero --°")
        self.error_value = QLabel("Error --°")
        self.balance_state_value = QLabel("DISARMED / waiting")
        for widget in (
            self.pitch_value,
            self.zero_value,
            self.error_value,
            self.balance_state_value,
        ):
            widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            balance_values.addWidget(widget)
        balance_values.addStretch(1)
        balance_layout.addLayout(balance_values)

        zero_buttons = QHBoxLayout()
        self.zero_button = _set_action_button(
            QPushButton("SET CURRENT ANGLE AS UPRIGHT ZERO"), "primary", 40
        )
        self.gyrozero_button = _set_action_button(QPushButton("GYRO ZERO"), "secondary", 40)
        self.clear_fault_button = _set_action_button(
            QPushButton("CLEAR BALANCE FAULT"), "warning", 40
        )
        self.zero_button.clicked.connect(self._set_upright_zero)
        self.gyrozero_button.clicked.connect(self._gyro_zero)
        self.clear_fault_button.clicked.connect(self._clear_fault)
        zero_buttons.addWidget(self.zero_button, 2)
        zero_buttons.addWidget(self.gyrozero_button, 1)
        zero_buttons.addWidget(self.clear_fault_button, 1)
        balance_layout.addLayout(zero_buttons)

        zero_note = QLabel(
            "Upright zero captures the robot's CURRENT physical angle as the balance point. "
            "Place LEO at the exact upright position first. Balance must be DISARMED."
        )
        zero_note.setWordWrap(True)
        balance_layout.addWidget(zero_note)
        layout.addWidget(balance_frame)

        # --------------------------------------------------------------
        # Motor bench controls
        # --------------------------------------------------------------
        control_frame = QFrame()
        control_frame.setFrameShape(QFrame.StyledPanel)
        controls = QVBoxLayout(control_frame)
        control_top = QHBoxLayout()

        speed_label = QLabel("Test speed")
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 10)
        self.speed_spin.setValue(2)
        self.speed_spin.setSuffix(" rpm")

        pulse_label = QLabel("Jog pulse")
        self.pulse_spin = QSpinBox()
        self.pulse_spin.setRange(100, 1000)
        self.pulse_spin.setSingleStep(50)
        self.pulse_spin.setValue(400)
        self.pulse_spin.setSuffix(" ms")

        run_label = QLabel("Timed run")
        self.run_spin = QSpinBox()
        self.run_spin.setRange(1, 15)
        self.run_spin.setValue(3)
        self.run_spin.setSuffix(" s")

        dwell_label = QLabel("Reversal stop")
        self.dwell_spin = QSpinBox()
        self.dwell_spin.setRange(100, 2000)
        self.dwell_spin.setSingleStep(100)
        self.dwell_spin.setValue(500)
        self.dwell_spin.setSuffix(" ms")

        for label, widget in (
            (speed_label, self.speed_spin),
            (pulse_label, self.pulse_spin),
            (run_label, self.run_spin),
            (dwell_label, self.dwell_spin),
        ):
            control_top.addWidget(label)
            control_top.addWidget(widget)
            control_top.addSpacing(10)
        control_top.addStretch(1)
        controls.addLayout(control_top)

        motor_row = QHBoxLayout()
        motor_row.addWidget(self._build_motor_box("LEFT MOTOR", "left"), 1)
        motor_row.addWidget(self._build_motor_box("RIGHT MOTOR", "right"), 1)
        controls.addLayout(motor_row)

        stop_row = QHBoxLayout()
        self.stop_button = _set_action_button(
            QPushButton("STOP ALL MOTORS"), "danger", 48
        )
        self.stop_button.clicked.connect(self._stop_all)
        stop_row.addWidget(self.stop_button)
        controls.addLayout(stop_row)
        layout.addWidget(control_frame)

        # --------------------------------------------------------------
        # Live numeric readback
        # --------------------------------------------------------------
        values_frame = QFrame()
        values_frame.setFrameShape(QFrame.StyledPanel)
        values_layout = QHBoxLayout(values_frame)
        self.angle_live = QLabel("ANGLE --°")
        self.left_command_live = QLabel("LEFT CMD 0.0 RPM")
        self.right_command_live = QLabel("RIGHT CMD 0.0 RPM")
        self.left_actual_live = QLabel("LEFT ACTUAL -- RPM")
        self.right_actual_live = QLabel("RIGHT ACTUAL -- RPM")
        self.left_encoder_live = QLabel("LEFT ENC --")
        self.right_encoder_live = QLabel("RIGHT ENC --")
        for widget in (
            self.angle_live,
            self.left_command_live,
            self.right_command_live,
            self.left_actual_live,
            self.right_actual_live,
            self.left_encoder_live,
            self.right_encoder_live,
        ):
            widget.setStyleSheet("font-weight: 700;")
            values_layout.addWidget(widget)
        values_layout.addStretch(1)
        layout.addWidget(values_frame)

        # --------------------------------------------------------------
        # Recording / chart controls
        # --------------------------------------------------------------
        recording_row = QHBoxLayout()
        self.start_record_button = _set_action_button(QPushButton("START RECORDING"), "success")
        self.stop_record_button = _set_action_button(QPushButton("STOP RECORDING"), "warning")
        self.clear_button = _set_action_button(QPushButton("CLEAR / ZERO CHART"), "secondary")
        self.export_button = _set_action_button(QPushButton("EXPORT CSV"), "primary")
        self.stop_record_button.setEnabled(False)

        window_label = QLabel("Chart window")
        self.window_spin = QSpinBox()
        self.window_spin.setRange(10, 300)
        self.window_spin.setValue(30)
        self.window_spin.setSuffix(" s")
        self.record_status = QLabel("Not recording")

        self.start_record_button.clicked.connect(self.start_recording)
        self.stop_record_button.clicked.connect(self.stop_recording)
        self.clear_button.clicked.connect(self.clear_charts)
        self.export_button.clicked.connect(self.export_csv)
        self.window_spin.valueChanged.connect(self._set_chart_window)

        for widget in (
            self.start_record_button,
            self.stop_record_button,
            self.clear_button,
            self.export_button,
        ):
            recording_row.addWidget(widget)
        recording_row.addSpacing(12)
        recording_row.addWidget(window_label)
        recording_row.addWidget(self.window_spin)
        recording_row.addStretch(1)
        recording_row.addWidget(self.record_status)
        layout.addLayout(recording_row)

        self.plot = CombinedCommissioningPlot()
        layout.addWidget(self.plot)

        note = QLabel(
            "LEFT axis = wheel RPM. RIGHT axis = robot angle error. OUTER RIGHT axis = "
            "encoder movement relative to the first sample after CLEAR / ZERO CHART. "
            "All three share the same centre zero line. Command RPM is always shown; "
            "measured MKS RPM/encoder values remain '--' if the drive has not returned "
            "readback. While balance is ARMED, direct MKS readback remains suspended so "
            "diagnostic RS485 traffic cannot disturb wheel control."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

        scroll.setWidget(container)
        outer.addWidget(scroll)

        controller.robot_api_telemetry_received.connect(self._on_robot_telemetry)
        controller.robot_api_status_received.connect(self._on_robot_api_status)
        controller.event_received.connect(self._on_event)

    def _build_motor_box(self, title: str, motor: str) -> QFrame:
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(box)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 800;")
        layout.addWidget(heading)

        prepare = _set_action_button(
            QPushButton("PREPARE / ENABLE FOR TEST STAND"), "primary", 40
        )
        prepare.clicked.connect(lambda checked=False, m=motor: self._prepare_motor(m))
        layout.addWidget(prepare)

        jog_row = QHBoxLayout()
        jog_fwd = _set_action_button(QPushButton("JOG +"), "success")
        jog_rev = _set_action_button(QPushButton("JOG -"), "warning")
        jog_fwd.clicked.connect(lambda checked=False, m=motor: self._jog(m, +1))
        jog_rev.clicked.connect(lambda checked=False, m=motor: self._jog(m, -1))
        jog_row.addWidget(jog_fwd)
        jog_row.addWidget(jog_rev)
        layout.addLayout(jog_row)

        run_row = QHBoxLayout()
        run_fwd = _set_action_button(QPushButton("TIMED RUN +"), "success")
        run_rev = _set_action_button(QPushButton("TIMED RUN -"), "warning")
        run_fwd.clicked.connect(lambda checked=False, m=motor: self._timed_run(m, +1))
        run_rev.clicked.connect(lambda checked=False, m=motor: self._timed_run(m, -1))
        run_row.addWidget(run_fwd)
        run_row.addWidget(run_rev)
        layout.addLayout(run_row)

        reversal = _set_action_button(
            QPushButton("FORWARD → STOP → REVERSE TEST"), "primary", 40
        )
        reversal.clicked.connect(lambda checked=False, m=motor: self._reversal_test(m))
        layout.addWidget(reversal)

        values = QLabel("Cmd 0 rpm | Actual -- rpm | Encoder --")
        values.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(values)
        if motor == "left":
            self.left_values = values
        else:
            self.right_values = values
        return box

    def showEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().showEvent(event)
        if self._api_connected and not self._recording:
            self.controller.request_action("analysis_live_start")

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().hideEvent(event)
        if self._api_connected and not self._recording:
            self.controller.request_action("analysis_live_stop")

    def _display_elapsed(self) -> float:
        return time.monotonic() - self._display_started

    def _record_elapsed(self) -> float:
        if self._record_started is None:
            return 0.0
        return time.monotonic() - self._record_started

    def _set_chart_window(self, seconds: int) -> None:
        self.plot.set_window_seconds(seconds)

    def _balance_is_armed(self) -> bool:
        return bool(self._latest_balance.get("armed", False))

    def _require_disarmed(self, action: str) -> bool:
        if not self._api_connected:
            QMessageBox.warning(self, action, "Robot API is not connected.")
            return False
        if self._balance_is_armed():
            QMessageBox.warning(
                self,
                action,
                "Balance is ARMED. DISARM LEO before using this commissioning control.",
            )
            return False
        return True

    def _prepare_motor(self, motor: str) -> None:
        if not self._require_disarmed("Prepare test-stand motor"):
            return
        self.status_label.setText(
            f"Preparing {motor} motor: known-good work mode/current, enable, zero speed..."
        )
        self.controller.request_action(
            "motor_bench_prepare",
            motor=motor,
        )

    def _jog(self, motor: str, direction: int) -> None:
        if not self._require_disarmed("Motor jog"):
            return
        rpm = int(self.speed_spin.value()) * (1 if direction >= 0 else -1)
        duration_ms = int(self.pulse_spin.value())
        self._add_marker(f"{motor[0].upper()} J{rpm:+d}")
        self.status_label.setText(
            f"Requested {motor} jog {rpm:+d} RPM for {duration_ms} ms..."
        )
        self.controller.request_action(
            "motor_bench_jog",
            motor=motor,
            rpm=rpm,
            duration_ms=duration_ms,
        )

    def _timed_run(self, motor: str, direction: int) -> None:
        if not self._require_disarmed("Timed motor run"):
            return
        rpm = int(self.speed_spin.value()) * (1 if direction >= 0 else -1)
        duration_ms = int(self.run_spin.value()) * 1000
        self._add_marker(f"{motor[0].upper()} RUN{rpm:+d}")
        self.status_label.setText(
            f"Requested {motor} timed run {rpm:+d} RPM for {duration_ms / 1000:.1f} s..."
        )
        self.controller.request_action(
            "motor_bench_run",
            motor=motor,
            rpm=rpm,
            duration_ms=duration_ms,
        )

    def _reversal_test(self, motor: str) -> None:
        if not self._require_disarmed("Motor reversal test"):
            return
        rpm = int(self.speed_spin.value())
        run_ms = int(self.run_spin.value()) * 1000
        dwell_ms = int(self.dwell_spin.value())
        answer = QMessageBox.question(
            self,
            "Run controlled reversal test",
            (
                f"Run the {motor.upper()} wheel at +{rpm} RPM for {run_ms / 1000:.1f} s, "
                f"stop for {dwell_ms} ms, then run at -{rpm} RPM for "
                f"{run_ms / 1000:.1f} s?\n\n"
                "Only this one wheel will be driven. Keep LEO safely supported."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._add_marker(f"{motor[0].upper()} REV TEST")
        self.status_label.setText(f"Starting controlled {motor} reversal test...")
        self.controller.request_action(
            "motor_bench_reversal",
            motor=motor,
            rpm=rpm,
            run_ms=run_ms,
            dwell_ms=dwell_ms,
        )

    def _stop_all(self) -> None:
        self._add_marker("STOP")
        self.status_label.setText("STOP ALL requested...")
        self.controller.request_action("motor_bench_stop")

    def _set_upright_zero(self) -> None:
        if not self._require_disarmed("Set upright zero"):
            return
        pitch = self._latest_balance.get("pitch_deg")
        pitch_text = "current measured angle"
        try:
            pitch_text = f"{float(pitch):+.3f}°"
        except (TypeError, ValueError):
            pass
        answer = QMessageBox.question(
            self,
            "Set LEO upright zero",
            (
                f"Set {pitch_text} as LEO's new UPRIGHT BALANCE POINT?\n\n"
                "Make sure the robot is being held at the exact physical upright position."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.status_label.setText("Capturing new upright balance zero...")
        self.controller.request_action("balance_zero")

    def _gyro_zero(self) -> None:
        if not self._require_disarmed("Gyro zero"):
            return
        answer = QMessageBox.question(
            self,
            "Calibrate gyro zero",
            "Keep LEO completely still while the gyro zero calibration runs. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.status_label.setText("Calibrating gyro zero - keep LEO still...")
            self.controller.request_action("balance_gyrozero")

    def _clear_fault(self) -> None:
        if not self._api_connected:
            return
        self.controller.request_action("balance_clear_fault")

    def start_recording(self) -> None:
        if self._recording:
            return
        if not self._api_connected:
            QMessageBox.warning(
                self,
                "Balance analysis",
                "Robot API is not connected. Start LEO before recording.",
            )
            return
        self._records = []
        self._recording = True
        self._record_started = time.monotonic()
        self.start_record_button.setEnabled(False)
        self.stop_record_button.setEnabled(True)
        self.record_status.setText("Recording 00:00:00 | 0 samples")
        self.controller.request_action("analysis_recording_start")
        self._add_marker("REC START")

    def stop_recording(self) -> None:
        if not self._recording:
            return
        self._add_marker("REC STOP")
        self._recording = False
        self.start_record_button.setEnabled(True)
        self.stop_record_button.setEnabled(False)
        self.controller.request_action("analysis_recording_stop")
        if self.isVisible() and self._api_connected:
            self.controller.request_action("analysis_live_start")
        self._update_record_status(stopped=True)

    def clear_charts(self) -> None:
        self._display_started = time.monotonic()
        self.plot.clear()
        self._encoder_origin = {"left": None, "right": None}
        self._records = []
        self._record_started = time.monotonic() if self._recording else None
        self._update_record_status()

    def _add_marker(self, label: str) -> None:
        x = self._display_elapsed()
        self.plot.add_marker(x, label)
        if self._recording:
            self._records.append(self._merged_record(event=label))
            self._update_record_status()

    def _relative_encoder(self, motor: str, value: Any) -> Any:
        if value is None:
            return None
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return None
        if self._encoder_origin[motor] is None:
            self._encoder_origin[motor] = numeric
        return numeric - int(self._encoder_origin[motor])

    def _merged_record(self, event: str = "") -> Dict[str, Any]:
        b = self._latest_balance
        m = self._latest_motor
        left = dict(m.get("left") or {})
        right = dict(m.get("right") or {})
        armed = bool(b.get("armed", False))
        left_command = (
            b.get("left_command_rpm")
            if armed
            else left.get("command_rpm", b.get("left_command_rpm"))
        )
        right_command = (
            b.get("right_command_rpm")
            if armed
            else right.get("command_rpm", b.get("right_command_rpm"))
        )
        return {
            "wall_time": datetime.now().isoformat(timespec="milliseconds"),
            "elapsed_s": round(self._record_elapsed(), 4),
            "event": event,
            "balance_armed": armed,
            "fault": b.get("fault"),
            "pitch_deg": b.get("pitch_deg"),
            "zero_deg": b.get("zero_deg"),
            "target_pitch_deg": b.get("target_pitch_deg"),
            "pitch_error_deg": b.get("error_deg"),
            "pitch_rate_dps": b.get("pitch_rate_dps"),
            "balance_output_rpm": b.get("output_rpm"),
            "left_command_rpm": left_command,
            "right_command_rpm": right_command,
            "left_actual_rpm": left.get("actual_rpm"),
            "right_actual_rpm": right.get("actual_rpm"),
            "left_encoder_counts": left.get("encoder_counts"),
            "right_encoder_counts": right.get("encoder_counts"),
            "left_encoder_deg": left.get("encoder_deg"),
            "right_encoder_deg": right.get("encoder_deg"),
            "movement_lean_deg": b.get("movement_lean_deg"),
            "steering_rpm": b.get("steering_rpm"),
        }

    def _update_record_status(self, *, stopped: bool = False) -> None:
        if self._record_started is None:
            self.record_status.setText("Not recording")
            return
        seconds = int(self._record_elapsed())
        h, rem = divmod(seconds, 3600)
        minute, second = divmod(rem, 60)
        prefix = "Stopped" if stopped else ("Recording" if self._recording else "Ready")
        self.record_status.setText(
            f"{prefix} {h:02d}:{minute:02d}:{second:02d} | {len(self._records)} samples"
        )

    def export_csv(self) -> None:
        if not self._records:
            QMessageBox.information(
                self,
                "Export motor/balance recording",
                "There is no recorded data to export yet.",
            )
            return
        default_name = (
            "BX1_Motor_Balance_"
            + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            + ".csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export motor / balance recording",
            str(Path.home() / default_name),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(self._records)
        self.status_label.setText(f"Exported {len(self._records)} samples to {path}")

    @staticmethod
    def _format_number(value: Any, pattern: str, fallback: str = "--") -> str:
        if value is None:
            return fallback
        try:
            return pattern.format(float(value))
        except (TypeError, ValueError):
            return fallback

    def _update_balance_labels(self, data: Dict[str, Any]) -> None:
        pitch = self._format_number(data.get("pitch_deg"), "{:+.3f}")
        zero = self._format_number(data.get("zero_deg"), "{:+.3f}")
        error = self._format_number(data.get("error_deg"), "{:+.3f}")
        armed = bool(data.get("armed", False))
        self.pitch_value.setText(f"Pitch {pitch}°")
        self.zero_value.setText(f"Zero {zero}°")
        self.error_value.setText(f"Error {error}°")
        self.angle_live.setText(f"ANGLE {error}°")
        self.balance_state_value.setText("ARMED" if armed else "DISARMED")
        self.zero_button.setEnabled(self._api_connected and not armed)
        self.gyrozero_button.setEnabled(self._api_connected and not armed)

    def _on_robot_api_status(self, status: dict) -> None:
        event = str((status or {}).get("event", ""))
        if event in {"robot_api_socket_connected", "robot_api_connected"}:
            was_connected = self._api_connected
            self._api_connected = True
            if not was_connected and event == "robot_api_connected":
                self.controller.request_action("motor_bench_status_request")
                if self.isVisible() and not self._recording:
                    self.controller.request_action("analysis_live_start")
        elif event in {
            "robot_api_disconnected",
            "robot_api_stopped",
            "robot_api_connection_error",
        }:
            self._api_connected = False
            self.status_label.setText("Robot API offline - motor controls disabled.")
        self._update_balance_labels(self._latest_balance)

    def _on_robot_telemetry(self, packet: dict) -> None:
        packet = dict(packet or {})
        topic = str(packet.get("topic", ""))
        data = packet.get("data")
        if not isinstance(data, dict):
            return
        x = self._display_elapsed()

        if topic == "balance.state":
            self._latest_balance = dict(data)
            self._update_balance_labels(data)
            self.plot.append_angle(x, data.get("error_deg"))

            armed = bool(data.get("armed", False))
            motor_packet_fresh = (
                time.monotonic() - self._last_motor_packet_monotonic
            ) < 1.0

            # Always show command RPM.  While DISARMED, fresh motor.bench
            # telemetry has the authoritative raw test command.  Before that
            # first packet arrives, the balance command is zero and gives the
            # expected stationary 0-RPM line rather than a blank chart.
            if armed or not motor_packet_fresh:
                left_cmd = data.get("left_command_rpm", 0)
                right_cmd = data.get("right_command_rpm", 0)
                self.plot.append_speed("Left cmd", x, 0 if left_cmd is None else left_cmd)
                self.plot.append_speed("Right cmd", x, 0 if right_cmd is None else right_cmd)
                self.left_command_live.setText(
                    f"LEFT CMD {self._format_number(left_cmd, '{:+.1f}', '0.0')} RPM"
                )
                self.right_command_live.setText(
                    f"RIGHT CMD {self._format_number(right_cmd, '{:+.1f}', '0.0')} RPM"
                )

            if self._recording:
                self._records.append(self._merged_record())
                self._update_record_status()

        elif topic == "motor.bench":
            self._last_motor_packet_monotonic = time.monotonic()
            self._latest_motor = dict(data)
            left = dict(data.get("left") or {})
            right = dict(data.get("right") or {})

            left_cmd = left.get("command_rpm", 0)
            right_cmd = right.get("command_rpm", 0)
            self.plot.append_speed("Left cmd", x, 0 if left_cmd is None else left_cmd)
            self.plot.append_speed("Right cmd", x, 0 if right_cmd is None else right_cmd)
            self.plot.append_speed("Left actual", x, left.get("actual_rpm"))
            self.plot.append_speed("Right actual", x, right.get("actual_rpm"))

            left_relative = self._relative_encoder("left", left.get("encoder_counts"))
            right_relative = self._relative_encoder("right", right.get("encoder_counts"))
            self.plot.append_encoder("Left encoder Δ", x, left_relative)
            self.plot.append_encoder("Right encoder Δ", x, right_relative)

            self.left_values.setText(self._motor_value_text(left))
            self.right_values.setText(self._motor_value_text(right))
            self.left_command_live.setText(
                f"LEFT CMD {self._format_number(left_cmd, '{:+.1f}', '0.0')} RPM"
            )
            self.right_command_live.setText(
                f"RIGHT CMD {self._format_number(right_cmd, '{:+.1f}', '0.0')} RPM"
            )
            self.left_actual_live.setText(
                f"LEFT ACTUAL {self._format_number(left.get('actual_rpm'), '{:+.1f}')} RPM"
            )
            self.right_actual_live.setText(
                f"RIGHT ACTUAL {self._format_number(right.get('actual_rpm'), '{:+.1f}')} RPM"
            )
            left_encoder = left.get("encoder_counts")
            right_encoder = right.get("encoder_counts")
            self.left_encoder_live.setText(
                "LEFT ENC --" if left_encoder is None else f"LEFT ENC {int(left_encoder)}"
            )
            self.right_encoder_live.setText(
                "RIGHT ENC --" if right_encoder is None else f"RIGHT ENC {int(right_encoder)}"
            )

            if bool(data.get("balance_armed", False)):
                self.status_label.setText(
                    "Balance ARMED: direct MKS actual-RPM/encoder polling suspended; "
                    "balance command telemetry remains active."
                )
            elif data.get("readback_available", False):
                readback_values = (
                    left.get("actual_rpm"),
                    left.get("encoder_counts"),
                    right.get("actual_rpm"),
                    right.get("encoder_counts"),
                )
                if all(value is None for value in readback_values):
                    errors = []
                    for label, motor_data in (("left", left), ("right", right)):
                        for key, message in dict(motor_data.get("errors") or {}).items():
                            errors.append(f"{label} {key}: {message}")
                    self.status_label.setText(
                        "Motor command telemetry is live, but MKS measured RPM/encoder "
                        "readback returned no values"
                        + (" | " + " ; ".join(errors[:4]) if errors else "")
                    )
                else:
                    self.status_label.setText(
                        "Motor telemetry active. Jog, timed run and reversal tests are "
                        "available while balance is DISARMED."
                    )

    @staticmethod
    def _motor_value_text(data: Dict[str, Any]) -> str:
        command = data.get("command_rpm")
        actual = data.get("actual_rpm")
        encoder = data.get("encoder_counts")
        command_text = "0" if command is None else f"{int(command):+d}"
        actual_text = "--" if actual is None else f"{float(actual):+.1f}"
        encoder_text = "--" if encoder is None else str(int(encoder))
        return f"Cmd {command_text} rpm | Actual {actual_text} rpm | Encoder {encoder_text}"

    def _on_event(self, event: dict) -> None:
        event = dict(event or {})
        name = str(event.get("event", ""))
        data = dict(event.get("data") or {})

        if name == "balance_command_result":
            command = str(data.get("command", ""))
            ok = bool(data.get("ok", False))
            if command == "balance.zero":
                self._add_marker("ZERO")
                self.status_label.setText(
                    "Upright zero captured successfully."
                    if ok
                    else f"Upright zero failed: {data.get('error', 'unknown error')}"
                )
            elif command == "balance.gyrozero":
                self._add_marker("GYRO ZERO")
                self.status_label.setText(
                    "Gyro zero calibration complete."
                    if ok
                    else f"Gyro zero failed: {data.get('error', 'unknown error')}"
                )
            elif command == "balance.clear_fault" and ok:
                self._add_marker("FAULT CLEAR")
            return

        if name == "motor_test_command_result":
            ok = bool(data.get("ok", False))
            command = str(data.get("command", ""))
            response = data.get("response")
            if ok and command == "motor.test_prepare" and isinstance(response, dict):
                motor = str(response.get("motor", "motor"))
                mode = str(response.get("work_mode", "?"))
                current = response.get("current_ma", "?")
                self.status_label.setText(
                    f"{motor.upper()} test-stand profile prepared: {mode}, {current} mA, drive enabled at 0 RPM. "
                    "You can now jog/run it; the API still performs the same preparation automatically before every run."
                )
            elif ok:
                self.status_label.setText(f"{command} accepted by LEO.")
            else:
                self.status_label.setText(
                    f"{command} failed: {data.get('error', 'unknown error')}"
                )
            return

        if name == "analysis_recording_result" and not bool(data.get("ok", False)):
            self.status_label.setText(
                f"Telemetry request failed: {data.get('error', 'unknown error')}"
            )
