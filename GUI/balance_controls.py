"""Large persistent balance ARM/DISARM control for the BX1 GUI.

Presentation only:
    GUI -> GUIController -> Master_Main_GUI.py -> RobotAPIServer -> LEO

This widget never talks to the robot directly.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BalanceSafetyControl(QFrame):
    """
    One large state-dependent safety control.

    DISARMED:
        Shows ARM MOTORS.

    ARMED:
        Changes to a large red DISARM / STOP button.

    DISARM never asks for confirmation.
    ARM requires confirmation and is still validated by LEO's MCU.
    """

    def __init__(
        self,
        controller,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.controller = controller

        self._api_connected = False
        self._seen_balance_state = False

        self._armed = False
        self._zero_valid = False
        self._imu_ok = False
        self._fault = None
        self._pitch = None

        self.setObjectName(
            "bx1_balance_safety_control"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            8,
            3,
            8,
            3,
        )
        layout.setSpacing(10)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        text_column.setSpacing(0)

        self.state_label = QLabel(
            "MOTORS: API WAITING"
        )
        self.state_label.setAlignment(
            Qt.AlignRight
            | Qt.AlignVCenter
        )

        self.detail_label = QLabel(
            "Waiting for balance telemetry"
        )
        self.detail_label.setAlignment(
            Qt.AlignRight
            | Qt.AlignVCenter
        )

        text_column.addWidget(
            self.state_label
        )
        text_column.addWidget(
            self.detail_label
        )

        self.toggle_button = QPushButton(
            "ARM MOTORS"
        )

        self.toggle_button.setMinimumSize(
            210,
            50,
        )

        self.toggle_button.setCursor(
            Qt.PointingHandCursor
        )

        self.toggle_button.clicked.connect(
            self._pressed
        )

        layout.addLayout(
            text_column
        )

        layout.addWidget(
            self.toggle_button
        )

        controller.event_received.connect(
            self._on_event
        )

        controller.robot_api_telemetry_received.connect(
            self._on_robot_api_telemetry
        )

        controller.robot_api_status_received.connect(
            self._on_robot_api_status
        )

        self._refresh()

    @staticmethod
    def _fault_clear(
        fault,
    ) -> bool:
        if isinstance(
            fault,
            dict,
        ):
            fault = fault.get(
                "code",
                fault.get(
                    "fault",
                    0,
                ),
            )

        return fault in (
            None,
            0,
            "0",
            "none",
            "None",
            "",
        )

    def _on_robot_api_status(
        self,
        status: dict,
    ) -> None:
        status = dict(
            status
            or {}
        )

        event = str(
            status.get(
                "event",
                "",
            )
        )

        if event in {
            "robot_api_socket_connected",
            "robot_api_connected",
        }:
            self._api_connected = True

        elif event in {
            "robot_api_disconnected",
            "robot_api_stopped",
            "robot_api_connection_error",
        }:
            self._api_connected = False
            self._seen_balance_state = False

        self._refresh()

    def _on_event(
        self,
        event: dict,
    ) -> None:
        event = dict(
            event
            or {}
        )

        if str(
            event.get(
                "event",
                "",
            )
        ) != "balance_command_result":
            return

        data = dict(
            event.get("data")
            or {}
        )

        command = str(
            data.get(
                "command",
                "",
            )
        )

        ok = bool(
            data.get(
                "ok",
                False,
            )
        )

        if not ok:
            self.detail_label.setText(
                str(
                    data.get("error")
                    or "Balance command rejected"
                )
            )

            self._refresh()
            return

        if command == "balance.disarm":
            self._armed = False

        self._refresh()

    def _on_robot_api_telemetry(
        self,
        packet: dict,
    ) -> None:
        packet = dict(
            packet
            or {}
        )

        if str(
            packet.get(
                "topic",
                "",
            )
        ) != "balance.state":
            return

        data = packet.get(
            "data"
        )

        if not isinstance(
            data,
            dict,
        ):
            return

        self._api_connected = True
        self._seen_balance_state = True

        self._armed = bool(
            data.get(
                "armed",
                False,
            )
        )

        self._zero_valid = bool(
            data.get(
                "zero_valid",
                False,
            )
        )

        self._imu_ok = bool(
            data.get(
                "imu_ok",
                data.get(
                    "imu_ready",
                    False,
                ),
            )
        )

        self._fault = data.get(
            "fault",
            data.get(
                "fault_code",
                0,
            ),
        )

        self._pitch = data.get(
            "pitch_deg"
        )

        self._refresh()

    def _safe_to_arm(
        self,
    ) -> bool:
        return bool(
            self._api_connected
            and self._seen_balance_state
            and not self._armed
            and self._zero_valid
            and self._imu_ok
            and self._fault_clear(
                self._fault
            )
        )

    def _refresh(
        self,
    ) -> None:
        details = []

        if self._pitch is not None:
            try:
                details.append(
                    f"Pitch {float(self._pitch):+.2f}°"
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

        if not self._api_connected:
            self.state_label.setText(
                "MOTORS: API OFFLINE"
            )

            self.state_label.setStyleSheet(
                "font-weight: 800; "
                "color: #a33;"
            )

            self.detail_label.setText(
                "Waiting for LEO on port 8774"
            )

            self.toggle_button.setText(
                "ARM UNAVAILABLE"
            )

            self.toggle_button.setEnabled(
                False
            )

            self.toggle_button.setStyleSheet(
                "QPushButton {"
                " font-size: 13pt;"
                " font-weight: 900;"
                " background: #d6d6d6;"
                " color: #777;"
                " border: 2px solid #b7b7b7;"
                " border-radius: 9px;"
                " padding: 8px 16px;"
                "}"
            )

            return

        if self._armed:
            self.state_label.setText(
                "MOTORS: ARMED"
            )

            self.state_label.setStyleSheet(
                "font-weight: 900; "
                "color: #c62828;"
            )

            details.append(
                "BALANCE ACTIVE"
            )

            self.toggle_button.setText(
                "DISARM / STOP"
            )

            self.toggle_button.setEnabled(
                True
            )

            self.toggle_button.setStyleSheet(
                "QPushButton {"
                " font-size: 14pt;"
                " font-weight: 900;"
                " background: #d7263d;"
                " color: white;"
                " border: 3px solid #981b2c;"
                " border-radius: 9px;"
                " padding: 8px 18px;"
                "}"
                "QPushButton:hover {"
                " background: #ed334b;"
                "}"
                "QPushButton:pressed {"
                " background: #a51429;"
                "}"
            )

        else:
            self.state_label.setText(
                "MOTORS: DISARMED"
            )

            self.state_label.setStyleSheet(
                "font-weight: 900; "
                "color: #218838;"
            )

            if not self._seen_balance_state:
                details.append(
                    "Waiting for balance state"
                )

            elif not self._zero_valid:
                details.append(
                    "Upright zero required"
                )

            elif not self._imu_ok:
                details.append(
                    "IMU not ready"
                )

            elif not self._fault_clear(
                self._fault
            ):
                details.append(
                    f"Fault {self._fault}"
                )

            else:
                details.append(
                    "Ready to arm"
                )

            if self._safe_to_arm():
                self.toggle_button.setText(
                    "ARM MOTORS"
                )

                self.toggle_button.setEnabled(
                    True
                )

                # Amber is intentional: ARM is an energising action,
                # not a "safe/green" action.
                self.toggle_button.setStyleSheet(
                    "QPushButton {"
                    " font-size: 14pt;"
                    " font-weight: 900;"
                    " background: #f4b942;"
                    " color: #2c220d;"
                    " border: 3px solid #c48c1b;"
                    " border-radius: 9px;"
                    " padding: 8px 18px;"
                    "}"
                    "QPushButton:hover {"
                    " background: #ffc857;"
                    "}"
                    "QPushButton:pressed {"
                    " background: #d99b28;"
                    "}"
                )

            else:
                self.toggle_button.setText(
                    "ARM UNAVAILABLE"
                )

                self.toggle_button.setEnabled(
                    False
                )

                self.toggle_button.setStyleSheet(
                    "QPushButton {"
                    " font-size: 13pt;"
                    " font-weight: 900;"
                    " background: #d6d6d6;"
                    " color: #777;"
                    " border: 2px solid #b7b7b7;"
                    " border-radius: 9px;"
                    " padding: 8px 16px;"
                    "}"
                )

        self.detail_label.setText(
            " | ".join(details)
            if details
            else "Balance status available"
        )

    def _pressed(
        self,
    ) -> None:
        if self._armed:
            # STOP must be one click and immediate.
            self.detail_label.setText(
                "DISARM requested..."
            )

            self.controller.request_action(
                "balance_disarm"
            )

            return

        if not self._safe_to_arm():
            return

        answer = QMessageBox.question(
            self,
            "Arm LEO motors",
            (
                "ARM LEO'S WHEEL MOTORS?\n\n"
                "The balance controller will energise both wheel drives.\n"
                "Keep the area clear and be ready to stop the robot."
            ),
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.detail_label.setText(
            "ARM requested..."
        )

        self.controller.request_action(
            "balance_arm"
        )
