"""BX1 balance self-teaching / guided auto-tune page.

Presentation and low-rate analysis only:
    GUI -> GUIController -> Master_Main_GUI.py -> Robot API -> LEO

The 100 Hz balance loop and all hard safety interlocks remain on the MCU.
This page never sends wheel RPM directly and never automatically ARM's LEO.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)



def _set_action_button(button: QPushButton, role: str, height: int = 38) -> QPushButton:
    """Give self-teaching controls a clear theme-aware action appearance."""
    button.setProperty("bxRole", str(role))
    button.setMinimumHeight(int(height))
    button.setCursor(Qt.PointingHandCursor)
    return button

class BalanceLearningPage(QWidget):
    """Learn balance trim, score stability and guide conservative Kp/Kd tuning."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._api_connected = False
        self._latest: Dict[str, Any] = {}
        self._parameter_bundle: Dict[str, Any] = {}

        self._mode = "idle"
        self._mode_started = 0.0
        self._samples: List[Dict[str, float]] = []
        self._accepted_samples = 0
        self._rejected_samples = 0
        self._learned_trim: float | None = None

        self._autotune_original: Dict[str, float] = {}
        self._autotune_candidates: List[Dict[str, float]] = []
        self._autotune_results: List[Dict[str, Any]] = []
        self._autotune_index = -1
        self._autotune_test_started = 0.0
        self._autotune_test_seconds = 8.0
        self._last_armed = False

        self._state_path = (
            Path(__file__).resolve().parent.parent
            / "settings"
            / "balance_learning.json"
        )
        self._saved_state = self._load_state()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        title = QLabel("Balance Learning / Self Teaching")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.status_label = QLabel(
            "Connect to LEO. Set a physical upright zero before balance learning."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # --------------------------------------------------------------
        # Live state
        # --------------------------------------------------------------
        live = QFrame()
        live.setFrameShape(QFrame.StyledPanel)
        live_layout = QVBoxLayout(live)
        live_heading = QLabel("LIVE BALANCE STATE")
        live_heading.setStyleSheet("font-weight: 800;")
        live_layout.addWidget(live_heading)

        row = QHBoxLayout()
        self.pitch_live = QLabel("Pitch --°")
        self.error_live = QLabel("Error --°")
        self.trim_live = QLabel("Learned trim --°")
        self.kp_live = QLabel("Kp --")
        self.kd_live = QLabel("Kd --")
        self.state_live = QLabel("DISARMED")
        for item in (
            self.pitch_live,
            self.error_live,
            self.trim_live,
            self.kp_live,
            self.kd_live,
            self.state_live,
        ):
            item.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(item)
        row.addStretch(1)
        live_layout.addLayout(row)
        layout.addWidget(live)

        # --------------------------------------------------------------
        # Phase 0: upright zero
        # --------------------------------------------------------------
        zero_frame = QFrame()
        zero_frame.setFrameShape(QFrame.StyledPanel)
        zero_layout = QVBoxLayout(zero_frame)
        zero_heading = QLabel("0. PHYSICAL UPRIGHT REFERENCE")
        zero_heading.setStyleSheet("font-weight: 800;")
        zero_layout.addWidget(zero_heading)
        zero_note = QLabel(
            "Place LEO at the physical upright position and capture it once. "
            "The learned balance trim is then measured relative to this reference."
        )
        zero_note.setWordWrap(True)
        zero_layout.addWidget(zero_note)
        zero_row = QHBoxLayout()
        self.zero_button = _set_action_button(
            QPushButton("SET CURRENT ANGLE AS PHYSICAL UPRIGHT ZERO"), "primary", 42
        )
        self.zero_button.clicked.connect(self._set_zero)
        self.refresh_button = _set_action_button(
            QPushButton("REFRESH PARAMETERS"), "secondary", 42
        )
        self.refresh_button.clicked.connect(
            lambda: self.controller.request_action("balance_get_parameters")
        )
        zero_row.addWidget(self.zero_button, 2)
        zero_row.addWidget(self.refresh_button, 1)
        zero_layout.addLayout(zero_row)
        layout.addWidget(zero_frame)

        # --------------------------------------------------------------
        # Phase 1: effective balance point
        # --------------------------------------------------------------
        learn_frame = QFrame()
        learn_frame.setFrameShape(QFrame.StyledPanel)
        learn_layout = QVBoxLayout(learn_frame)
        learn_heading = QLabel("1. LEARN EFFECTIVE BALANCE POINT")
        learn_heading.setStyleSheet("font-weight: 800;")
        learn_layout.addWidget(learn_heading)
        learn_note = QLabel(
            "This uses the MCU adaptive trim while LEO is balancing with no movement "
            "command. It learns the small centre-of-gravity offset between the physical "
            "upright reference and the angle that actually requires the least correction."
        )
        learn_note.setWordWrap(True)
        learn_layout.addWidget(learn_note)

        learn_settings = QHBoxLayout()
        learn_settings.addWidget(QLabel("Learning time"))
        self.learn_seconds = QSpinBox()
        self.learn_seconds.setRange(15, 120)
        self.learn_seconds.setValue(45)
        self.learn_seconds.setSuffix(" s")
        learn_settings.addWidget(self.learn_seconds)
        learn_settings.addWidget(QLabel("Fast learning rate"))
        self.learn_rate = QDoubleSpinBox()
        self.learn_rate.setRange(0.001, 0.050)
        self.learn_rate.setDecimals(3)
        self.learn_rate.setSingleStep(0.001)
        self.learn_rate.setValue(0.010)
        self.learn_rate.setSuffix(" °/s")
        learn_settings.addWidget(self.learn_rate)
        learn_settings.addStretch(1)
        learn_layout.addLayout(learn_settings)

        learn_buttons = QHBoxLayout()
        self.prepare_learn_button = _set_action_button(
            QPushButton("PREPARE LEARN MODE"), "primary", 42
        )
        self.start_learn_button = _set_action_button(
            QPushButton("START LEARNING WHEN ARMED"), "success", 42
        )
        self.accept_trim_button = _set_action_button(
            QPushButton("ACCEPT LEARNED BALANCE POINT"), "success", 42
        )
        self.cancel_learn_button = _set_action_button(
            QPushButton("CANCEL / DISARM"), "danger", 42
        )
        self.start_learn_button.setEnabled(False)
        self.accept_trim_button.setEnabled(False)
        self.prepare_learn_button.clicked.connect(self._prepare_balance_learning)
        self.start_learn_button.clicked.connect(self._start_balance_learning)
        self.accept_trim_button.clicked.connect(self._accept_learned_trim)
        self.cancel_learn_button.clicked.connect(self._cancel_learning)
        for button in (
            self.prepare_learn_button,
            self.start_learn_button,
            self.accept_trim_button,
            self.cancel_learn_button,
        ):
            learn_buttons.addWidget(button)
        learn_layout.addLayout(learn_buttons)

        self.learn_result = QLabel("No learned balance point yet.")
        self.learn_result.setWordWrap(True)
        learn_layout.addWidget(self.learn_result)
        layout.addWidget(learn_frame)

        # --------------------------------------------------------------
        # Phase 2: baseline stability score
        # --------------------------------------------------------------
        baseline_frame = QFrame()
        baseline_frame.setFrameShape(QFrame.StyledPanel)
        baseline_layout = QVBoxLayout(baseline_frame)
        baseline_heading = QLabel("2. MEASURE BALANCE QUALITY")
        baseline_heading.setStyleSheet("font-weight: 800;")
        baseline_layout.addWidget(baseline_heading)
        baseline_note = QLabel(
            "Record a repeatable stability test. The comparison score uses angle error, "
            "pitch rate and commanded wheel effort. It is for comparing LEO with himself, "
            "not an absolute industry rating."
        )
        baseline_note.setWordWrap(True)
        baseline_layout.addWidget(baseline_note)
        baseline_row = QHBoxLayout()
        self.baseline_seconds = QSpinBox()
        self.baseline_seconds.setRange(5, 60)
        self.baseline_seconds.setValue(15)
        self.baseline_seconds.setSuffix(" s")
        self.baseline_button = _set_action_button(
            QPushButton("START STABILITY TEST"), "primary", 40
        )
        self.baseline_button.clicked.connect(self._start_baseline)
        baseline_row.addWidget(QLabel("Test time"))
        baseline_row.addWidget(self.baseline_seconds)
        baseline_row.addWidget(self.baseline_button)
        baseline_row.addStretch(1)
        baseline_layout.addLayout(baseline_row)
        self.baseline_result = QLabel("No stability test recorded yet.")
        self.baseline_result.setWordWrap(True)
        baseline_layout.addWidget(self.baseline_result)
        layout.addWidget(baseline_frame)

        # --------------------------------------------------------------
        # Phase 3: conservative guided autotune
        # --------------------------------------------------------------
        tune_frame = QFrame()
        tune_frame.setFrameShape(QFrame.StyledPanel)
        tune_layout = QVBoxLayout(tune_frame)
        tune_heading = QLabel("3. GUIDED Kp / Kd AUTO TUNE")
        tune_heading.setStyleSheet("font-weight: 800;")
        tune_layout.addWidget(tune_heading)
        tune_note = QLabel(
            "The Brain tests a small set of values around the current Kp/Kd. "
            "LEO is NEVER armed automatically: for each candidate you press the normal "
            "ARM MOTORS control. The test records for 8 seconds, then DISARMS automatically. "
            "The best result is only saved after you press ACCEPT BEST."
        )
        tune_note.setWordWrap(True)
        tune_layout.addWidget(tune_note)

        tune_buttons = QHBoxLayout()
        self.start_tune_button = _set_action_button(
            QPushButton("CREATE / START GUIDED AUTO TUNE"), "primary", 42
        )
        self.accept_tune_button = _set_action_button(
            QPushButton("ACCEPT BEST"), "success", 42
        )
        self.restore_tune_button = _set_action_button(
            QPushButton("RESTORE ORIGINAL"), "warning", 42
        )
        self.cancel_tune_button = _set_action_button(
            QPushButton("CANCEL AUTO TUNE"), "danger", 42
        )
        self.accept_tune_button.setEnabled(False)
        self.restore_tune_button.setEnabled(False)
        self.start_tune_button.clicked.connect(self._start_autotune)
        self.accept_tune_button.clicked.connect(self._accept_best_tune)
        self.restore_tune_button.clicked.connect(self._restore_original_tune)
        self.cancel_tune_button.clicked.connect(self._cancel_autotune)
        for button in (
            self.start_tune_button,
            self.accept_tune_button,
            self.restore_tune_button,
            self.cancel_tune_button,
        ):
            tune_buttons.addWidget(button)
        tune_layout.addLayout(tune_buttons)
        self.tune_status = QLabel("Auto tune idle.")
        self.tune_status.setWordWrap(True)
        tune_layout.addWidget(self.tune_status)

        self.tune_table = QTableWidget(0, 5)
        self.tune_table.setHorizontalHeaderLabels(
            ["Candidate", "Kp", "Kd", "Score", "Result"]
        )
        tune_layout.addWidget(self.tune_table)
        layout.addWidget(tune_frame)

        # --------------------------------------------------------------
        # Mechanical wear tracking placeholder / history
        # --------------------------------------------------------------
        mech_frame = QFrame()
        mech_frame.setFrameShape(QFrame.StyledPanel)
        mech_layout = QVBoxLayout(mech_frame)
        mech_heading = QLabel("4. MECHANICAL WEAR / BACKLASH HISTORY")
        mech_heading.setStyleSheet("font-weight: 800;")
        mech_layout.addWidget(mech_heading)
        self.backlash_label = QLabel(
            "Backlash has not been calibrated. The history framework is ready; final "
            "mechanical calibration will use the controlled reversal test plus motor "
            "readback and the INA3221 supply-current measurement when fitted."
        )
        self.backlash_label.setWordWrap(True)
        mech_layout.addWidget(self.backlash_label)
        self.mech_history = QTableWidget(0, 4)
        self.mech_history.setHorizontalHeaderLabels(
            ["Date", "Left backlash", "Right backlash", "Change / note"]
        )
        mech_layout.addWidget(self.mech_history)
        layout.addWidget(mech_frame)

        layout.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        controller.robot_api_telemetry_received.connect(self._on_telemetry)
        controller.robot_api_status_received.connect(self._on_api_status)
        controller.event_received.connect(self._on_event)

        self._refresh_history_table()
        self._update_buttons()

    # ------------------------------------------------------------------
    # Persistent comparison history
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {"stability_history": [], "mechanical_history": []}

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self._saved_state, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self.status_label.setText(
                f"Could not save balance-learning history: {type(exc).__name__}: {exc}"
            )

    def _refresh_history_table(self) -> None:
        history = list(self._saved_state.get("mechanical_history") or [])[-12:]
        self.mech_history.setRowCount(len(history))
        for row, item in enumerate(reversed(history)):
            values = [
                str(item.get("timestamp", "")),
                str(item.get("left", "--")),
                str(item.get("right", "--")),
                str(item.get("note", "")),
            ]
            for col, value in enumerate(values):
                self.mech_history.setItem(row, col, QTableWidgetItem(value))

    # ------------------------------------------------------------------
    # Page lifecycle / connection
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._api_connected:
            self.controller.request_action("learning_live_start")
            self.controller.request_action("balance_get_parameters")

    def hideEvent(self, event) -> None:
        if self._api_connected and self._mode == "idle":
            self.controller.request_action("learning_live_stop")
        super().hideEvent(event)

    def _on_api_status(self, status: dict) -> None:
        name = str((status or {}).get("event", ""))
        if name in {"robot_api_socket_connected", "robot_api_connected"}:
            was_connected = self._api_connected
            self._api_connected = True
            if not was_connected and name == "robot_api_connected":
                self.controller.request_action("learning_live_start")
                self.controller.request_action("balance_get_parameters")
        elif name in {
            "robot_api_disconnected",
            "robot_api_stopped",
            "robot_api_connection_error",
        }:
            self._api_connected = False
            self.status_label.setText("Robot API offline. Learning paused.")
            if self._mode != "idle":
                self._mode = "idle"
        self._update_buttons()

    # ------------------------------------------------------------------
    # Telemetry and scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _float(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(data.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def _sample_from(self, data: Dict[str, Any]) -> Dict[str, float]:
        left = self._float(data, "left_command_rpm")
        right = self._float(data, "right_command_rpm")
        return {
            "t": time.monotonic(),
            "error": self._float(data, "error_deg"),
            "rate": self._float(data, "pitch_rate_dps"),
            "output": self._float(data, "output_rpm"),
            "effort": (abs(left) + abs(right)) / 2.0,
            "trim": self._float(data, "adaptive_trim_deg"),
            "movement": self._float(data, "movement_lean_deg"),
            "steering": self._float(data, "steering_rpm"),
            "fault": self._float(data, "fault"),
        }

    def _stable_learning_sample(self, sample: Dict[str, float]) -> bool:
        return (
            sample["fault"] == 0
            and abs(sample["movement"]) <= 0.02
            and abs(sample["steering"]) <= 0.5
            and abs(sample["rate"]) <= 3.0
            and abs(sample["error"]) <= 3.0
        )

    @staticmethod
    def _rms(values: List[float]) -> float:
        if not values:
            return 0.0
        return math.sqrt(sum(v * v for v in values) / len(values))

    def _metrics(self, samples: List[Dict[str, float]]) -> Dict[str, float]:
        if not samples:
            return {
                "samples": 0,
                "rms_error": 99.0,
                "peak_error": 99.0,
                "rms_rate": 99.0,
                "mean_effort": 99.0,
                "peak_effort": 99.0,
                "score": 0.0,
            }
        errors = [s["error"] for s in samples]
        rates = [s["rate"] for s in samples]
        efforts = [s["effort"] for s in samples]
        rms_error = self._rms(errors)
        peak_error = max(abs(v) for v in errors)
        rms_rate = self._rms(rates)
        mean_effort = statistics.fmean(efforts)
        peak_effort = max(efforts)

        # Comparison score only. It is intentionally conservative and is not
        # presented as a physical stability certification.
        penalty = (
            rms_error * 28.0
            + peak_error * 7.0
            + rms_rate * 2.0
            + mean_effort * 0.45
            + peak_effort * 0.08
        )
        score = max(0.0, min(100.0, 100.0 - penalty))
        return {
            "samples": float(len(samples)),
            "rms_error": rms_error,
            "peak_error": peak_error,
            "rms_rate": rms_rate,
            "mean_effort": mean_effort,
            "peak_effort": peak_effort,
            "score": score,
        }

    def _on_telemetry(self, packet: dict) -> None:
        packet = dict(packet or {})
        if str(packet.get("topic", "")) != "balance.state":
            return
        data = packet.get("data")
        if not isinstance(data, dict):
            return

        self._latest = dict(data)
        armed = bool(data.get("armed", False))
        error = self._float(data, "error_deg")
        trim = self._float(data, "adaptive_trim_deg")
        self.pitch_live.setText(f"Pitch {self._float(data, 'pitch_deg'):+.3f}°")
        self.error_live.setText(f"Error {error:+.3f}°")
        self.trim_live.setText(f"Learned trim {trim:+.3f}°")
        self.kp_live.setText(f"Kp {self._float(data, 'kp'):.2f}")
        self.kd_live.setText(f"Kd {self._float(data, 'kd'):.2f}")
        self.state_live.setText("ARMED" if armed else "DISARMED")

        sample = self._sample_from(data)

        if self._mode == "learn_wait_arm" and armed and not self._last_armed:
            self.status_label.setText(
                "LEO is armed. Press START LEARNING WHEN ARMED when the robot is settled."
            )

        elif self._mode == "learn_recording" and armed:
            if self._stable_learning_sample(sample):
                self._samples.append(sample)
                self._accepted_samples += 1
            else:
                self._rejected_samples += 1

        elif self._mode == "baseline_recording" and armed:
            if sample["fault"] == 0:
                self._samples.append(sample)

        elif self._mode == "autotune_wait_arm" and armed and not self._last_armed:
            self._mode = "autotune_recording"
            self._autotune_test_started = time.monotonic()
            self._samples = []
            candidate = self._current_candidate()
            self.tune_status.setText(
                f"Testing candidate {self._autotune_index + 1}/{len(self._autotune_candidates)}: "
                f"Kp {candidate['kp']:.2f}, Kd {candidate['kd']:.2f} for "
                f"{self._autotune_test_seconds:.0f}s."
            )

        elif self._mode == "autotune_recording":
            if armed and sample["fault"] == 0:
                self._samples.append(sample)
            elif not armed and self._last_armed:
                # A fall/fault/manual disarm before the timer completes is a
                # failed candidate and must never be rewarded.
                if time.monotonic() - self._autotune_test_started < 3.0:
                    self._finish_autotune_candidate(early=True)

        elif self._mode == "autotune_wait_disarm" and not armed and self._last_armed:
            QTimer.singleShot(250, self._advance_autotune)

        self._last_armed = armed
        self._update_buttons()

    # ------------------------------------------------------------------
    # Phase 0 / 1 balance-point learning
    # ------------------------------------------------------------------

    def _set_zero(self) -> None:
        if not self._api_connected or bool(self._latest.get("armed", False)):
            return
        answer = QMessageBox.question(
            self,
            "Set physical upright zero",
            "Hold LEO at the physical upright position. Set the CURRENT angle as the physical upright reference?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.controller.request_action("balance_zero")

    def _prepare_balance_learning(self) -> None:
        if bool(self._latest.get("armed", False)):
            self.status_label.setText("DISARM LEO before preparing balance learning.")
            return
        if not bool(self._latest.get("zero_valid", False)):
            self.status_label.setText("Set the physical upright zero first.")
            return

        current_trim = self._float(self._latest, "adaptive_trim_deg")
        limit = max(0.5, min(1.5, abs(current_trim) + 0.75))
        self.controller.request_action(
            "balance_set_parameters",
            values={
                "adaptive_trim_enabled": True,
                "adaptive_trim_limit_deg": limit,
                "adaptive_trim_deadband_deg": 0.05,
                "adaptive_trim_rate_deg_per_s": float(self.learn_rate.value()),
                "adaptive_trim_deg": current_trim,
            },
            save=False,
        )
        self._mode = "learn_wait_arm"
        self._learned_trim = None
        self.accept_trim_button.setEnabled(False)
        self.status_label.setText(
            "Learn mode prepared. ARM LEO using the normal ARM MOTORS control, let him settle, then start learning."
        )

    def _start_balance_learning(self) -> None:
        if not bool(self._latest.get("armed", False)):
            self.status_label.setText("LEO must be ARMED and balancing before learning starts.")
            return
        if abs(self._float(self._latest, "movement_lean_deg")) > 0.02:
            self.status_label.setText("Movement command is active. HOLD/centre movement before learning.")
            return
        self._mode = "learn_recording"
        self._mode_started = time.monotonic()
        self._samples = []
        self._accepted_samples = 0
        self._rejected_samples = 0
        self.learn_result.setText("Learning effective balance point...")

    def _finish_balance_learning(self) -> None:
        if self._mode != "learn_recording":
            return
        self.controller.request_action("balance_disarm")
        stable = list(self._samples)
        if len(stable) < 20:
            self._mode = "idle"
            self.learn_result.setText(
                f"Learning failed: only {len(stable)} stable samples were accepted. "
                "No balance-point change has been saved."
            )
            return

        tail_count = max(10, len(stable) // 3)
        tail = stable[-tail_count:]
        trims = [s["trim"] for s in tail]
        errors = [s["error"] for s in tail]
        learned = statistics.median(trims)
        mean_error = statistics.fmean(errors)
        trim_span = max(trims) - min(trims) if trims else 0.0
        self._learned_trim = learned
        self._mode = "idle"
        self.accept_trim_button.setEnabled(True)
        quality = "converged" if abs(mean_error) <= 0.12 and trim_span <= 0.08 else "still moving"
        self.learn_result.setText(
            f"Learned trim {learned:+.3f}°. Final mean error {mean_error:+.3f}°, "
            f"trim span {trim_span:.3f}° ({quality}). Accepted {self._accepted_samples} samples, "
            f"rejected {self._rejected_samples}. Press ACCEPT to store it and return to the slow background learning rate."
        )

    def _accept_learned_trim(self) -> None:
        if self._learned_trim is None or bool(self._latest.get("armed", False)):
            return
        limit = max(0.5, min(1.5, abs(self._learned_trim) + 0.5))
        self.controller.request_action(
            "balance_set_parameters",
            values={
                "adaptive_trim_enabled": True,
                "adaptive_trim_limit_deg": limit,
                "adaptive_trim_deadband_deg": 0.15,
                "adaptive_trim_rate_deg_per_s": 0.0003,
                "adaptive_trim_deg": float(self._learned_trim),
            },
            save=True,
        )
        self.accept_trim_button.setEnabled(False)
        self.status_label.setText(
            f"Saving learned balance trim {self._learned_trim:+.3f}° on LEO."
        )

    def _cancel_learning(self) -> None:
        self._mode = "idle"
        self._samples = []
        self.controller.request_action("balance_disarm")
        self.status_label.setText("Balance learning cancelled; DISARM requested.")

    # ------------------------------------------------------------------
    # Phase 2 baseline
    # ------------------------------------------------------------------

    def _start_baseline(self) -> None:
        if not bool(self._latest.get("armed", False)):
            self.status_label.setText("ARM LEO and let him settle before starting a stability test.")
            return
        self._mode = "baseline_recording"
        self._mode_started = time.monotonic()
        self._samples = []
        self.baseline_result.setText("Measuring balance quality...")

    def _finish_baseline(self) -> None:
        if self._mode != "baseline_recording":
            return
        metrics = self._metrics(self._samples)
        self._mode = "idle"
        self.baseline_result.setText(
            f"Comparison score {metrics['score']:.1f}/100 | RMS angle error {metrics['rms_error']:.3f}° | "
            f"peak error {metrics['peak_error']:.3f}° | RMS pitch rate {metrics['rms_rate']:.3f}°/s | "
            f"mean wheel effort {metrics['mean_effort']:.2f} RPM."
        )
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kp": self._float(self._latest, "kp"),
            "kd": self._float(self._latest, "kd"),
            **metrics,
        }
        history = self._saved_state.setdefault("stability_history", [])
        history.append(entry)
        del history[:-100]
        self._save_state()

    # ------------------------------------------------------------------
    # Phase 3 guided auto-tune
    # ------------------------------------------------------------------

    def _start_autotune(self) -> None:
        if bool(self._latest.get("armed", False)):
            self.tune_status.setText("DISARM LEO before starting guided auto tune.")
            return
        if not bool(self._latest.get("zero_valid", False)):
            self.tune_status.setText("Physical upright zero is required before auto tune.")
            return

        kp = max(0.1, self._float(self._latest, "kp", 10.0))
        kd = max(0.0, self._float(self._latest, "kd", 0.5))
        self._autotune_original = {"kp": kp, "kd": kd}

        raw = [
            {"kp": kp, "kd": kd},
            {"kp": kp * 0.95, "kd": kd},
            {"kp": kp * 1.05, "kd": kd},
            {"kp": kp, "kd": max(0.0, kd - 0.10)},
            {"kp": kp, "kd": min(10.0, kd + 0.10)},
        ]
        candidates: List[Dict[str, float]] = []
        seen = set()
        for item in raw:
            candidate = {
                "kp": round(max(0.0, min(50.0, item["kp"])), 2),
                "kd": round(max(0.0, min(10.0, item["kd"])), 2),
            }
            key = (candidate["kp"], candidate["kd"])
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
        self._autotune_candidates = candidates
        self._autotune_results = []
        self._autotune_index = 0
        self.accept_tune_button.setEnabled(False)
        self.restore_tune_button.setEnabled(True)
        self._rebuild_tune_table()
        self._apply_current_candidate()

    def _current_candidate(self) -> Dict[str, float]:
        if 0 <= self._autotune_index < len(self._autotune_candidates):
            return self._autotune_candidates[self._autotune_index]
        return dict(self._autotune_original)

    def _apply_current_candidate(self) -> None:
        if self._autotune_index >= len(self._autotune_candidates):
            self._finish_autotune_plan()
            return
        candidate = self._current_candidate()
        self.controller.request_action(
            "balance_set_parameters",
            values={"kp": candidate["kp"], "kd": candidate["kd"]},
            save=False,
        )
        self._mode = "autotune_wait_arm"
        self._samples = []
        self.tune_status.setText(
            f"Candidate {self._autotune_index + 1}/{len(self._autotune_candidates)} applied: "
            f"Kp {candidate['kp']:.2f}, Kd {candidate['kd']:.2f}. "
            "Press the normal ARM MOTORS button when LEO is upright. The timed test starts automatically."
        )
        self._rebuild_tune_table()

    def _finish_autotune_candidate(self, *, early: bool = False) -> None:
        if self._mode not in {"autotune_recording", "autotune_wait_disarm"}:
            return
        candidate = self._current_candidate()
        metrics = self._metrics(self._samples)
        if early or len(self._samples) < 20:
            metrics["score"] = 0.0
            result_text = "FAILED / early stop"
        else:
            result_text = "complete"
        self._autotune_results.append(
            {"candidate": dict(candidate), "metrics": metrics, "result": result_text}
        )
        self._mode = "autotune_wait_disarm"
        self.controller.request_action("balance_disarm")
        self.tune_status.setText(
            f"Candidate {self._autotune_index + 1} score {metrics['score']:.1f}. DISARM requested."
        )
        self._rebuild_tune_table()
        if early:
            # We observed the drive already disarmed, so there may be no future
            # armed->disarmed edge for the normal advance logic to see.
            QTimer.singleShot(350, self._advance_autotune)

    def _advance_autotune(self) -> None:
        if self._mode != "autotune_wait_disarm":
            return
        self._autotune_index += 1
        self._apply_current_candidate()

    def _finish_autotune_plan(self) -> None:
        self._mode = "idle"
        if not self._autotune_results:
            self.tune_status.setText("No completed auto-tune candidates.")
            return
        best = max(self._autotune_results, key=lambda r: float(r["metrics"]["score"]))
        candidate = best["candidate"]
        score = float(best["metrics"]["score"])
        self.tune_status.setText(
            f"Guided auto tune complete. Best measured candidate: Kp {candidate['kp']:.2f}, "
            f"Kd {candidate['kd']:.2f}, comparison score {score:.1f}/100. "
            "Nothing has been permanently saved yet."
        )
        self.accept_tune_button.setEnabled(score > 0.0)
        self.restore_tune_button.setEnabled(True)
        self._rebuild_tune_table()

    def _best_tune(self) -> Dict[str, float] | None:
        if not self._autotune_results:
            return None
        best = max(self._autotune_results, key=lambda r: float(r["metrics"]["score"]))
        if float(best["metrics"]["score"]) <= 0.0:
            return None
        return dict(best["candidate"])

    def _accept_best_tune(self) -> None:
        if bool(self._latest.get("armed", False)):
            return
        best = self._best_tune()
        if not best:
            return
        self.controller.request_action(
            "balance_set_parameters",
            values=best,
            save=True,
        )
        self.tune_status.setText(
            f"Saving best measured gains: Kp {best['kp']:.2f}, Kd {best['kd']:.2f}."
        )
        self.accept_tune_button.setEnabled(False)

    def _restore_original_tune(self) -> None:
        if bool(self._latest.get("armed", False)) or not self._autotune_original:
            return
        self.controller.request_action(
            "balance_set_parameters",
            values=dict(self._autotune_original),
            save=False,
        )
        self.tune_status.setText(
            f"Original gains restored: Kp {self._autotune_original['kp']:.2f}, "
            f"Kd {self._autotune_original['kd']:.2f}."
        )

    def _cancel_autotune(self) -> None:
        self.controller.request_action("balance_disarm")
        self._mode = "idle"
        if self._autotune_original:
            QTimer.singleShot(300, self._restore_original_tune)
        self.tune_status.setText("Guided auto tune cancelled; original gains will be restored.")

    def _rebuild_tune_table(self) -> None:
        self.tune_table.setRowCount(len(self._autotune_candidates))
        result_by_key = {
            (r["candidate"]["kp"], r["candidate"]["kd"]): r
            for r in self._autotune_results
        }
        for row, candidate in enumerate(self._autotune_candidates):
            result = result_by_key.get((candidate["kp"], candidate["kd"]))
            score = "--"
            result_text = "waiting"
            if result:
                score = f"{float(result['metrics']['score']):.1f}"
                result_text = str(result.get("result", "complete"))
            elif row == self._autotune_index and self._mode.startswith("autotune"):
                result_text = "current"
            values = [
                str(row + 1),
                f"{candidate['kp']:.2f}",
                f"{candidate['kd']:.2f}",
                score,
                result_text,
            ]
            for col, value in enumerate(values):
                self.tune_table.setItem(row, col, QTableWidgetItem(value))

    # ------------------------------------------------------------------
    # Events / parameter bundle / timer
    # ------------------------------------------------------------------

    def _on_event(self, event: dict) -> None:
        event = dict(event or {})
        if str(event.get("event", "")) != "balance_command_result":
            return
        data = dict(event.get("data") or {})
        command = str(data.get("command", ""))
        ok = bool(data.get("ok", False))
        if not ok:
            self.status_label.setText(
                f"{command} failed: {data.get('error', 'unknown error')}"
            )
            return

        response = data.get("response")
        if command == "balance.get_parameters" and isinstance(response, dict):
            self._parameter_bundle = dict(response)
            backlash = dict(response.get("backlash") or {})
            left = int(backlash.get("left_counts", 0) or 0)
            right = int(backlash.get("right_counts", 0) or 0)
            if left or right:
                self.backlash_label.setText(
                    f"Stored backlash measurement: LEFT {left} counts / "
                    f"{float(backlash.get('left_deg', 0.0)):.3f}°, RIGHT {right} counts / "
                    f"{float(backlash.get('right_deg', 0.0)):.3f}°. Compensation remains locked "
                    "until the measurement method is validated with INA3221 / wheel-load evidence."
                )
        elif command == "balance.zero":
            self.status_label.setText(
                "Physical upright reference captured. You can now prepare balance learning."
            )
            self.controller.request_action("balance_get_parameters")
        elif command == "balance.set_parameters":
            self.controller.request_action("balance_get_parameters")
        self._update_buttons()

    def _tick(self) -> None:
        now = time.monotonic()
        if self._mode == "learn_recording":
            duration = float(self.learn_seconds.value())
            elapsed = now - self._mode_started
            remaining = max(0.0, duration - elapsed)
            self.learn_result.setText(
                f"Learning... {remaining:.1f}s remaining | stable samples {self._accepted_samples} | "
                f"rejected {self._rejected_samples} | current trim {self._float(self._latest, 'adaptive_trim_deg'):+.3f}°"
            )
            if elapsed >= duration:
                self._finish_balance_learning()

        elif self._mode == "baseline_recording":
            duration = float(self.baseline_seconds.value())
            elapsed = now - self._mode_started
            self.baseline_result.setText(
                f"Measuring... {max(0.0, duration - elapsed):.1f}s remaining | {len(self._samples)} samples"
            )
            if elapsed >= duration:
                self._finish_baseline()

        elif self._mode == "autotune_recording":
            elapsed = now - self._autotune_test_started
            if elapsed >= self._autotune_test_seconds:
                self._finish_autotune_candidate()
            else:
                candidate = self._current_candidate()
                self.tune_status.setText(
                    f"Testing Kp {candidate['kp']:.2f}, Kd {candidate['kd']:.2f}: "
                    f"{self._autotune_test_seconds - elapsed:.1f}s remaining | {len(self._samples)} samples"
                )

    def _update_buttons(self) -> None:
        armed = bool(self._latest.get("armed", False))
        zero_valid = bool(self._latest.get("zero_valid", False))
        idle = self._mode == "idle"
        self.zero_button.setEnabled(self._api_connected and not armed and idle)
        self.refresh_button.setEnabled(self._api_connected)
        self.prepare_learn_button.setEnabled(
            self._api_connected and not armed and zero_valid and self._mode in {"idle", "learn_wait_arm"}
        )
        self.start_learn_button.setEnabled(
            self._api_connected and armed and self._mode == "learn_wait_arm"
        )
        self.baseline_button.setEnabled(self._api_connected and armed and idle)
        self.start_tune_button.setEnabled(self._api_connected and not armed and zero_valid and idle)
        self.accept_tune_button.setEnabled(
            self.accept_tune_button.isEnabled() and not armed
        )
        self.restore_tune_button.setEnabled(
            bool(self._autotune_original) and not armed
        )
