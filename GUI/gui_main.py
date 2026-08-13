"""
BX1_DEV PySide6 GUI
===================

This file contains presentation code only.

It does not:
- call the LLM directly
- control TTS/STT
- connect to robot hardware
- send robot audio
- replace Master_Main.py

All commands flow through GUIController.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .gui_controller import GUIController
from .connection_settings import RobotConnectionSettings
from .balance_controls import BalanceSafetyControl
from .motor_bench import MotorBenchPage
from .balance_learning import BalanceLearningPage
from . import gui_config
from settings.personality_manager import PersonalityManager, DEFAULT_PERSONALITY, DISPLAY_NAMES


THEMES = {
    "Ocean Blue": """
        QWidget {
            background: #f6f9fd;
            color: #1d2733;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QFrame#Sidebar, QFrame#Inspector {
            background: #ffffff;
            border: 1px solid #dfe8f3;
            border-radius: 10px;
        }
        QPushButton {
            border: 0;
            border-radius: 7px;
            padding: 8px 10px;
            text-align: left;
        }
        QPushButton:hover { background: #e9f2ff; }
        QPushButton:checked {
            background: #dcecff;
            color: #1267d6;
            font-weight: 600;
        }
        QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {
            background: #ffffff;
            border: 1px solid #dfe8f3;
            border-radius: 8px;
            padding: 7px;
        }
        QLabel#Title { font-size: 16pt; font-weight: 700; }
        QLabel#SectionTitle { font-size: 11pt; font-weight: 700; }
        QLabel#Online { color: #11994b; font-weight: 700; }
        QLabel#Offline { color: #cc3d3d; font-weight: 700; }
    """,

    "Dark Mode": """
        QWidget {
            background: #0f171d;
            color: #e7edf2;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QFrame#Sidebar, QFrame#Inspector {
            background: #131e25;
            border: 1px solid #223541;
            border-radius: 10px;
        }
        QPushButton {
            border: 0;
            border-radius: 7px;
            padding: 8px 10px;
            text-align: left;
        }
        QPushButton:hover { background: #1b2b35; }
        QPushButton:checked {
            background: #173e66;
            color: #7dc0ff;
            font-weight: 600;
        }
        QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {
            background: #101a20;
            border: 1px solid #263b46;
            border-radius: 8px;
            padding: 7px;
        }
        QLabel#Title { font-size: 16pt; font-weight: 700; }
        QLabel#SectionTitle { font-size: 11pt; font-weight: 700; }
        QLabel#Online { color: #39d676; font-weight: 700; }
        QLabel#Offline { color: #ff6f6f; font-weight: 700; }
    """,

    "Purple Nebula": """
        QWidget {
            background: #161126;
            color: #eeeafd;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QFrame#Sidebar, QFrame#Inspector {
            background: #211735;
            border: 1px solid #3b2a5f;
            border-radius: 10px;
        }
        QPushButton {
            border: 0;
            border-radius: 7px;
            padding: 8px 10px;
            text-align: left;
        }
        QPushButton:hover { background: #2d2047; }
        QPushButton:checked {
            background: #533080;
            color: #f2dfff;
            font-weight: 600;
        }
        QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {
            background: #1d1630;
            border: 1px solid #443166;
            border-radius: 8px;
            padding: 7px;
        }
        QLabel#Title { font-size: 16pt; font-weight: 700; }
        QLabel#SectionTitle { font-size: 11pt; font-weight: 700; }
        QLabel#Online { color: #57e485; font-weight: 700; }
        QLabel#Offline { color: #ff7474; font-weight: 700; }
    """,

    "Green Forest": """
        QWidget {
            background: #102019;
            color: #e8f2ec;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QFrame#Sidebar, QFrame#Inspector {
            background: #16291f;
            border: 1px solid #294633;
            border-radius: 10px;
        }
        QPushButton {
            border: 0;
            border-radius: 7px;
            padding: 8px 10px;
            text-align: left;
        }
        QPushButton:hover { background: #1e3829; }
        QPushButton:checked {
            background: #315f3d;
            color: #dfffe5;
            font-weight: 600;
        }
        QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {
            background: #13241b;
            border: 1px solid #31523b;
            border-radius: 8px;
            padding: 7px;
        }
        QLabel#Title { font-size: 16pt; font-weight: 700; }
        QLabel#SectionTitle { font-size: 11pt; font-weight: 700; }
        QLabel#Online { color: #73e394; font-weight: 700; }
        QLabel#Offline { color: #ff7a7a; font-weight: 700; }
    """,

    "Warm Light": """
        QWidget {
            background: #fbf7f0;
            color: #322c27;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QFrame#Sidebar, QFrame#Inspector {
            background: #fffdf9;
            border: 1px solid #eadfd3;
            border-radius: 10px;
        }
        QPushButton {
            border: 0;
            border-radius: 7px;
            padding: 8px 10px;
            text-align: left;
        }
        QPushButton:hover { background: #fff0df; }
        QPushButton:checked {
            background: #ffe3c3;
            color: #c86513;
            font-weight: 600;
        }
        QLineEdit, QTextEdit, QTableWidget, QListWidget, QComboBox {
            background: #fffdf9;
            border: 1px solid #eadfd3;
            border-radius: 8px;
            padding: 7px;
        }
        QLabel#Title { font-size: 16pt; font-weight: 700; }
        QLabel#SectionTitle { font-size: 11pt; font-weight: 700; }
        QLabel#Online { color: #329052; font-weight: 700; }
        QLabel#Offline { color: #c84646; font-weight: 700; }
    """,
}


# ------------------------------------------------------------------
# ACTION BUTTON STYLES
# ------------------------------------------------------------------
# Navigation buttons intentionally keep the normal theme rules above.
# Only buttons with the ``bxRole`` property use these stronger styles.
# This makes commissioning controls easy to recognise without turning the
# entire GUI into a wall of coloured buttons.
ACTION_BUTTON_STYLES = {
    "Ocean Blue": """
        QPushButton[bxRole="primary"] {
            background: #2f80ed; color: white; border: 2px solid #2468c4;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="primary"]:hover { background: #246fce; }
        QPushButton[bxRole="primary"]:pressed { background: #174f9a; border-color: #123f7c; }

        QPushButton[bxRole="success"] {
            background: #2f9d62; color: white; border: 2px solid #247a4c;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="success"]:hover { background: #278653; }
        QPushButton[bxRole="success"]:pressed { background: #185f3a; border-color: #12492c; }

        QPushButton[bxRole="warning"] {
            background: #e6a23c; color: #2f2108; border: 2px solid #bf8120;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="warning"]:hover { background: #d89228; }
        QPushButton[bxRole="warning"]:pressed { background: #9a6114; color: white; border-color: #784a0e; }

        QPushButton[bxRole="danger"] {
            background: #d7263d; color: white; border: 2px solid #a91b2e;
            border-radius: 10px; padding: 9px 14px; font-weight: 900;
            text-align: center;
        }
        QPushButton[bxRole="danger"]:hover { background: #e63249; }
        QPushButton[bxRole="danger"]:pressed { background: #8d1727; border-color: #70111f; }

        QPushButton[bxRole="secondary"] {
            background: #ffffff; color: #245f9f; border: 2px solid #9fc4ec;
            border-radius: 10px; padding: 9px 14px; font-weight: 700;
            text-align: center;
        }
        QPushButton[bxRole="secondary"]:hover { background: #eaf3ff; }
        QPushButton[bxRole="secondary"]:pressed { background: #bfdcff; color: #174d87; border-color: #6fa7df; }
    """,

    "Dark Mode": """
        QPushButton[bxRole="primary"] {
            background: #2b6f9f; color: #f5fbff; border: 2px solid #4087b8;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="primary"]:hover { background: #347fac; }
        QPushButton[bxRole="primary"]:pressed { background: #17425f; border-color: #235d80; }

        QPushButton[bxRole="success"] {
            background: #2d8657; color: #f5fff9; border: 2px solid #46a872;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="success"]:hover { background: #369665; }
        QPushButton[bxRole="success"]:pressed { background: #184d32; border-color: #2a714a; }

        QPushButton[bxRole="warning"] {
            background: #a97222; color: #fff8e8; border: 2px solid #cb9341;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="warning"]:hover { background: #bb812a; }
        QPushButton[bxRole="warning"]:pressed { background: #66430f; border-color: #8a5c19; }

        QPushButton[bxRole="danger"] {
            background: #b53245; color: white; border: 2px solid #d04a5d;
            border-radius: 10px; padding: 9px 14px; font-weight: 900;
            text-align: center;
        }
        QPushButton[bxRole="danger"]:hover { background: #ca3c51; }
        QPushButton[bxRole="danger"]:pressed { background: #681c29; border-color: #8d2637; }

        QPushButton[bxRole="secondary"] {
            background: #17252d; color: #dceaf2; border: 2px solid #35505f;
            border-radius: 10px; padding: 9px 14px; font-weight: 700;
            text-align: center;
        }
        QPushButton[bxRole="secondary"]:hover { background: #20343f; }
        QPushButton[bxRole="secondary"]:pressed { background: #0d171d; color: #9fbed0; border-color: #29404d; }
    """,

    "Purple Nebula": """
        QPushButton[bxRole="primary"] {
            background: #6940a5; color: #fffaff; border: 2px solid #875ac4;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="primary"]:hover { background: #7a4db7; }
        QPushButton[bxRole="primary"]:pressed { background: #432568; border-color: #5a337f; }

        QPushButton[bxRole="success"] {
            background: #347d60; color: #f5fff9; border: 2px solid #4da17e;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="success"]:hover { background: #3d906e; }
        QPushButton[bxRole="success"]:pressed { background: #1f4d3a; border-color: #326f56; }

        QPushButton[bxRole="warning"] {
            background: #a96f2a; color: #fff8ed; border: 2px solid #cb8c43;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="warning"]:hover { background: #bc7e33; }
        QPushButton[bxRole="warning"]:pressed { background: #684112; border-color: #87561c; }

        QPushButton[bxRole="danger"] {
            background: #ad3855; color: white; border: 2px solid #cf5571;
            border-radius: 10px; padding: 9px 14px; font-weight: 900;
            text-align: center;
        }
        QPushButton[bxRole="danger"]:hover { background: #c14361; }
        QPushButton[bxRole="danger"]:pressed { background: #651d31; border-color: #862842; }

        QPushButton[bxRole="secondary"] {
            background: #2a1f43; color: #eee7fa; border: 2px solid #5d4686;
            border-radius: 10px; padding: 9px 14px; font-weight: 700;
            text-align: center;
        }
        QPushButton[bxRole="secondary"]:hover { background: #382958; }
        QPushButton[bxRole="secondary"]:pressed { background: #171022; color: #c9b8e4; border-color: #48356a; }
    """,

    "Green Forest": """
        QPushButton[bxRole="primary"] {
            background: #39754f; color: #f4fff7; border: 2px solid #55976a;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="primary"]:hover { background: #44865b; }
        QPushButton[bxRole="primary"]:pressed { background: #21472f; border-color: #32623f; }

        QPushButton[bxRole="success"] {
            background: #468c57; color: #f4fff6; border: 2px solid #63aa74;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="success"]:hover { background: #529c64; }
        QPushButton[bxRole="success"]:pressed { background: #285436; border-color: #3c754a; }

        QPushButton[bxRole="warning"] {
            background: #9b742d; color: #fff9eb; border: 2px solid #bb9145;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="warning"]:hover { background: #ad8336; }
        QPushButton[bxRole="warning"]:pressed { background: #5e4314; border-color: #7c5b20; }

        QPushButton[bxRole="danger"] {
            background: #a93443; color: white; border: 2px solid #c94c5a;
            border-radius: 10px; padding: 9px 14px; font-weight: 900;
            text-align: center;
        }
        QPushButton[bxRole="danger"]:hover { background: #bd3e4e; }
        QPushButton[bxRole="danger"]:pressed { background: #621c27; border-color: #832735; }

        QPushButton[bxRole="secondary"] {
            background: #192e22; color: #e6f2ea; border: 2px solid #41684d;
            border-radius: 10px; padding: 9px 14px; font-weight: 700;
            text-align: center;
        }
        QPushButton[bxRole="secondary"]:hover { background: #23402e; }
        QPushButton[bxRole="secondary"]:pressed { background: #0f1d15; color: #bed5c5; border-color: #31523b; }
    """,

    "Warm Light": """
        QPushButton[bxRole="primary"] {
            background: #d97820; color: white; border: 2px solid #b65e10;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="primary"]:hover { background: #e48732; }
        QPushButton[bxRole="primary"]:pressed { background: #984609; border-color: #7d3907; }

        QPushButton[bxRole="success"] {
            background: #4f9364; color: white; border: 2px solid #39784d;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="success"]:hover { background: #5ba471; }
        QPushButton[bxRole="success"]:pressed { background: #2c593b; border-color: #20472e; }

        QPushButton[bxRole="warning"] {
            background: #df9b3e; color: #3b270d; border: 2px solid #be7c25;
            border-radius: 10px; padding: 9px 14px; font-weight: 800;
            text-align: center;
        }
        QPushButton[bxRole="warning"]:hover { background: #eba94f; }
        QPushButton[bxRole="warning"]:pressed { background: #955b15; color: white; border-color: #75450e; }

        QPushButton[bxRole="danger"] {
            background: #c54b4b; color: white; border: 2px solid #9f3434;
            border-radius: 10px; padding: 9px 14px; font-weight: 900;
            text-align: center;
        }
        QPushButton[bxRole="danger"]:hover { background: #d65b5b; }
        QPushButton[bxRole="danger"]:pressed { background: #7d2929; border-color: #642020; }

        QPushButton[bxRole="secondary"] {
            background: #fffaf3; color: #8a511c; border: 2px solid #dfb98f;
            border-radius: 10px; padding: 9px 14px; font-weight: 700;
            text-align: center;
        }
        QPushButton[bxRole="secondary"]:hover { background: #fff0df; }
        QPushButton[bxRole="secondary"]:pressed { background: #f0cfaa; color: #6e3e14; border-color: #ca9660; }
    """,
}

# Disabled action buttons keep their shape so it is obvious that a control
# exists, but lose the strong action colour until the action becomes valid.
ACTION_BUTTON_DISABLED_STYLE = """
    QPushButton[bxRole]:disabled {
        background: #8a8f94; color: #e9eaeb; border: 2px solid #777c81;
        border-radius: 10px; padding: 9px 14px; font-weight: 700;
        text-align: center;
    }
"""


class StageIndicator(QWidget):
    """Small reusable status icon + label."""

    def __init__(
        self,
        icon_path,
        fallback_text: str,
        label_text: str,
        icon_size: int,
    ):
        super().__init__()

        self._state = "idle"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.state_glyph = QLabel("○")
        self.icon_label = QLabel()
        self.text_label = QLabel(label_text)

        path = Path(icon_path)

        if path.exists():
            pixmap = QPixmap(str(path))

            if not pixmap.isNull():
                self.icon_label.setPixmap(
                    pixmap.scaled(
                        icon_size,
                        icon_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            else:
                self.icon_label.setText(fallback_text)
        else:
            self.icon_label.setText(fallback_text)

        layout.addWidget(self.state_glyph)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)

        self.set_state("idle")

    def set_state(self, state: str):
        state = str(state or "idle").lower()
        self._state = state

        if state == "active":
            self.state_glyph.setText("●")
            self.setStyleSheet("font-weight: 700;")
        elif state == "complete":
            self.state_glyph.setText("✓")
            self.setStyleSheet("")
        else:
            self.state_glyph.setText("○")
            self.setStyleSheet("color: #7f8a94;")


class MessageBubble(QFrame):
    def __init__(
        self,
        sender: str,
        text: str,
        message_id: str,
        click_callback,
    ):
        super().__init__()

        self.sender = sender
        self.text = text
        self.message_id = message_id
        self.click_callback = click_callback
        self.stage_indicators = {}

        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)

        self.sender_label = QLabel(sender)
        self.sender_label.setStyleSheet("font-weight: 700;")

        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(self.sender_label)
        layout.addWidget(text_label)

        if sender.upper() not in {"YOU", "BACKGROUND"}:
            status_row = QHBoxLayout()
            status_row.setSpacing(12)

            self.stage_indicators = {
                "thinking": StageIndicator(
                    gui_config.THINKING_ICON,
                    gui_config.THINKING_FALLBACK,
                    gui_config.THINKING_TEXT,
                    gui_config.CHAT_MESSAGE_STATUS_ICON_SIZE,
                ),
                "generating_audio": StageIndicator(
                    gui_config.GENERATING_AUDIO_ICON,
                    gui_config.GENERATING_AUDIO_FALLBACK,
                    gui_config.GENERATING_AUDIO_TEXT,
                    gui_config.CHAT_MESSAGE_STATUS_ICON_SIZE,
                ),
                "playing_audio": StageIndicator(
                    gui_config.PLAYING_AUDIO_ICON,
                    gui_config.PLAYING_AUDIO_FALLBACK,
                    gui_config.PLAYING_AUDIO_TEXT,
                    gui_config.CHAT_MESSAGE_STATUS_ICON_SIZE,
                ),
            }

            for indicator in self.stage_indicators.values():
                status_row.addWidget(indicator)

            status_row.addStretch(1)
            layout.addLayout(status_row)

        sender_upper = sender.upper()

        if sender_upper == "YOU":
            self.setStyleSheet(
                "QFrame { background: rgba(81, 170, 104, 0.18); "
                "border: 1px solid rgba(81,170,104,0.35); "
                "border-radius: 10px; }"
            )
        elif sender_upper == "BACKGROUND":
            self.sender_label.setText("BACKGROUND — NOT ADDRESSED TO LEO")
            self.setStyleSheet(
                "QFrame { background: rgba(214, 163, 66, 0.18); "
                "border: 1px solid rgba(214,163,66,0.48); "
                "border-radius: 10px; } "
                "QLabel { color: #8a6a25; }"
            )
            self.setToolTip(
                "Whisper heard this speech, but it was not accepted by "
                "wake/session gating. It was not sent to the LLM."
            )
        else:
            self.setStyleSheet(
                "QFrame { background: rgba(68, 126, 190, 0.14); "
                "border: 1px solid rgba(68,126,190,0.30); "
                "border-radius: 10px; }"
            )

    def set_sender(self, sender: str):
        self.sender = str(sender)
        self.sender_label.setText(self.sender)


    def set_stage_state(
        self,
        stage: str,
        state: str,
    ):
        indicator = self.stage_indicators.get(stage)

        if indicator is not None:
            indicator.set_state(state)

    def mousePressEvent(self, event):
        if callable(self.click_callback):
            self.click_callback(self.message_id)
        super().mousePressEvent(event)


class BX1MainWindow(QMainWindow):
    def __init__(
        self,
        controller: GUIController,
        robot_image: Optional[str] = None,
    ) -> None:
        super().__init__()

        self.controller = controller

        self.settings = QSettings("BX1", "BX1_DEV")
        self.robot_connections = RobotConnectionSettings()
        self.personality = PersonalityManager()
        self.robot_display_name = self.personality.get_name()

        # Session-only history. Nothing is written to disk automatically.
        saved_robot_image = self.settings.value(
            "appearance/robot_image",
            "",
            type=str,
        )
        self.robot_image = robot_image or saved_robot_image or None

        saved_icon = self.settings.value(
            "appearance/app_icon",
            "",
            type=str,
        )
        self.app_icon_path = saved_icon or None

        self._messages: Dict[str, Dict[str, Any]] = {}
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._message_bubbles: Dict[str, MessageBubble] = {}
        self._message_stage_states: Dict[str, Dict[str, str]] = {}
        self._events = deque(maxlen=2000)
        self._telemetry = deque(maxlen=5000)

        self.setWindowTitle(f"BX1_DEV — {self.robot_display_name}")
        self.resize(1450, 860)

        self._build_ui()
        self._connect_controller()
        self.apply_theme(
            self.settings.value(
                "appearance/theme",
                "Ocean Blue",
                type=str,
            )
        )
        self._apply_app_icon(self.app_icon_path)

    # ------------------------------------------------------------------
    # UI BUILD
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addLayout(self._build_top_bar())

        body = QHBoxLayout()
        body.setSpacing(8)

        self.sidebar = self._build_sidebar()
        self.pages = self._build_pages()
        self.inspector = self._build_inspector()

        body.addWidget(self.sidebar, 0)
        body.addWidget(self.pages, 1)
        body.addWidget(self.inspector, 0)

        root.addLayout(body, 1)

    def _build_top_bar(self):
        layout = QHBoxLayout()
        layout.setSpacing(12)

        title = QLabel("BX1_DEV")
        title.setObjectName("Title")

        self.mode_label = QLabel("LOCAL")
        self.mode_label.setStyleSheet("font-weight: 700;")

        self.balance_control = BalanceSafetyControl(
            self.controller,
            self,
        )

        self.connection_label = QLabel("● Offline")
        self.connection_label.setObjectName("Offline")

        layout.addWidget(title)
        layout.addSpacing(18)
        layout.addWidget(self.mode_label)
        layout.addStretch(1)
        layout.addWidget(self.balance_control)
        layout.addSpacing(8)
        layout.addWidget(self.connection_label)

        return layout

    def _build_sidebar(self):
        frame = QFrame()
        frame.setObjectName("Sidebar")
        frame.setFixedWidth(190)

        layout = QVBoxLayout(frame)

        self.robot_picture = QLabel()
        self.robot_picture.setAlignment(Qt.AlignCenter)
        self.robot_picture.setMinimumHeight(135)
        self._load_robot_image(self.robot_image)

        self.robot_name = QLabel(self.robot_display_name)
        self.robot_name.setAlignment(Qt.AlignCenter)
        self.robot_name.setStyleSheet("font-weight: 700;")

        layout.addWidget(self.robot_picture)
        layout.addWidget(self.robot_name)

        self.nav_buttons = {}

        nav_items = [
            ("Chat", 0),
            ("Dashboard", 1),
            ("Telemetry", 2),
            ("Hardware", 3),
            ("Balance Learning", 4),
            ("Brain", 5),
            ("Vision", 6),
            ("Personality", 7),
            ("Events", 8),
            ("Debug", 9),
            ("Settings", 10),
        ]

        for label, index in nav_items:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, i=index, b=button: self._select_page(i, b)
            )

            self.nav_buttons[label] = button
            layout.addWidget(button)

        self.nav_buttons["Chat"].setChecked(True)

        layout.addStretch(1)

        export_button = QPushButton("Export Data")
        export_button.clicked.connect(
            lambda: self.controller.request_action("export_debug")
        )
        layout.addWidget(export_button)

        return frame

    def _build_pages(self):
        stack = QStackedWidget()

        self.chat_page = self._build_chat_page()
        self.dashboard_page = self._placeholder_page(
            "Dashboard",
            "Overall BX1 status and key robot/brain metrics.",
        )
        self.telemetry_page = self._build_telemetry_page()
        self.hardware_page = self._build_hardware_page()
        self.balance_learning_page = self._build_balance_learning_page()
        self.brain_page = self._build_brain_page()
        self.vision_page = self._build_vision_page()
        self.personality_page = self._build_personality_page()
        self.events_page = self._build_events_page()
        self.debug_page = self._build_debug_page()
        self.settings_page = self._build_settings_page()

        for page in (
            self.chat_page,
            self.dashboard_page,
            self.telemetry_page,
            self.hardware_page,
            self.balance_learning_page,
            self.brain_page,
            self.vision_page,
            self.personality_page,
            self.events_page,
            self.debug_page,
            self.settings_page,
        ):
            stack.addWidget(page)

        return stack

    def _build_chat_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.chat_heading = QLabel(
            f"ROBO-CHAT — {self.robot_display_name}"
        )
        self.chat_heading.setObjectName("SectionTitle")

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)

        self.chat_scroll.setWidget(self.chat_container)

        self.chat_status_row = QHBoxLayout()
        self.chat_status_row.setSpacing(16)

        self.chat_stage_indicators = {
            "thinking": StageIndicator(
                gui_config.THINKING_ICON,
                gui_config.THINKING_FALLBACK,
                gui_config.THINKING_TEXT,
                gui_config.CHAT_BOTTOM_STATUS_ICON_SIZE,
            ),
            "generating_audio": StageIndicator(
                gui_config.GENERATING_AUDIO_ICON,
                gui_config.GENERATING_AUDIO_FALLBACK,
                gui_config.GENERATING_AUDIO_TEXT,
                gui_config.CHAT_BOTTOM_STATUS_ICON_SIZE,
            ),
            "playing_audio": StageIndicator(
                gui_config.PLAYING_AUDIO_ICON,
                gui_config.PLAYING_AUDIO_FALLBACK,
                gui_config.PLAYING_AUDIO_TEXT,
                gui_config.CHAT_BOTTOM_STATUS_ICON_SIZE,
            ),
        }

        for indicator in self.chat_stage_indicators.values():
            self.chat_status_row.addWidget(indicator)

        self.chat_status_row.addStretch(1)

        entry_row = QHBoxLayout()

        self.message_entry = QLineEdit()
        self.message_entry.setPlaceholderText("Type your message...")
        self.message_entry.returnPressed.connect(self._send_message)

        send_button = QPushButton("Send")
        send_button.clicked.connect(self._send_message)

        entry_row.addWidget(self.message_entry, 1)
        entry_row.addWidget(send_button)

        layout.addWidget(self.chat_heading)
        layout.addWidget(self.chat_scroll, 1)
        layout.addLayout(self.chat_status_row)
        layout.addLayout(entry_row)

        return page

    def _build_brain_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)

        title = QLabel("Brain / Voice")
        title.setObjectName("SectionTitle")

        description = QLabel(
            "Qwen voice-clone settings. Changes are sent through the GUI "
            "controller to Master_Main_GUI.py; the GUI never controls Qwen "
            "or robot audio directly."
        )
        description.setWordWrap(True)

        self.tts_status_label = QLabel(
            "TTS settings: waiting for active engine"
        )
        self.tts_status_label.setWordWrap(True)
        self.tts_status_label.setStyleSheet("font-weight: 600;")

        outer.addWidget(title)
        outer.addWidget(description)
        outer.addWidget(self.tts_status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # --------------------------------------------------------------
        # VOICE CLONE
        # --------------------------------------------------------------
        clone_title = QLabel("Voice Clone")
        clone_title.setObjectName("SectionTitle")
        content_layout.addWidget(clone_title)

        clone_form = QFormLayout()

        self.tts_model_combo = QComboBox()
        self.tts_model_combo.addItem(
            "Qwen 0.6B Base — smaller model",
            "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        )
        self.tts_model_combo.addItem(
            "Qwen 1.7B Base — larger model",
            "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        )
        clone_form.addRow("Model:", self.tts_model_combo)

        reference_widget = QWidget()
        reference_row = QHBoxLayout(reference_widget)
        reference_row.setContentsMargins(0, 0, 0, 0)

        self.tts_reference_edit = QLineEdit()
        self.tts_reference_edit.setReadOnly(True)
        self.tts_reference_edit.setPlaceholderText(
            "Select a clean WAV reference voice"
        )

        choose_reference = QPushButton("Choose WAV...")
        choose_reference.clicked.connect(self.choose_tts_reference)

        reference_row.addWidget(self.tts_reference_edit, 1)
        reference_row.addWidget(choose_reference)
        clone_form.addRow("Reference voice:", reference_widget)

        self.tts_clone_mode_combo = QComboBox()
        self.tts_clone_mode_combo.addItem(
            "Full ICL — audio + exact transcript (recommended)",
            False,
        )
        self.tts_clone_mode_combo.addItem(
            "Speaker embedding only — audio only",
            True,
        )
        clone_form.addRow("Clone mode:", self.tts_clone_mode_combo)

        self.tts_reference_text = QTextEdit()
        self.tts_reference_text.setMaximumHeight(110)
        self.tts_reference_text.setPlaceholderText(
            "For Full ICL, type the EXACT words spoken in the reference WAV."
        )
        clone_form.addRow("Reference transcript:", self.tts_reference_text)

        self.tts_language_combo = QComboBox()
        self.tts_language_combo.setEditable(True)
        self.tts_language_combo.addItems(
            ["English", "Auto"]
        )
        clone_form.addRow("Language:", self.tts_language_combo)

        content_layout.addLayout(clone_form)
        content_layout.addSpacing(12)

        # --------------------------------------------------------------
        # GENERATION
        # --------------------------------------------------------------
        generation_title = QLabel("Generation")
        generation_title.setObjectName("SectionTitle")
        content_layout.addWidget(generation_title)

        generation_form = QFormLayout()

        self.tts_temperature = QDoubleSpinBox()
        self.tts_temperature.setRange(0.05, 2.0)
        self.tts_temperature.setDecimals(2)
        self.tts_temperature.setSingleStep(0.05)
        generation_form.addRow("Temperature:", self.tts_temperature)

        self.tts_top_k = QSpinBox()
        self.tts_top_k.setRange(1, 500)
        generation_form.addRow("Top K:", self.tts_top_k)

        self.tts_top_p = QDoubleSpinBox()
        self.tts_top_p.setRange(0.05, 1.0)
        self.tts_top_p.setDecimals(2)
        self.tts_top_p.setSingleStep(0.05)
        generation_form.addRow("Top P:", self.tts_top_p)

        self.tts_repetition_penalty = QDoubleSpinBox()
        self.tts_repetition_penalty.setRange(1.0, 2.0)
        self.tts_repetition_penalty.setDecimals(2)
        self.tts_repetition_penalty.setSingleStep(0.01)
        generation_form.addRow(
            "Repetition penalty:",
            self.tts_repetition_penalty,
        )

        self.tts_do_sample = QCheckBox("Enable sampling")
        generation_form.addRow("Sampling:", self.tts_do_sample)

        self.tts_max_new_tokens = QSpinBox()
        self.tts_max_new_tokens.setRange(32, 4096)
        self.tts_max_new_tokens.setSingleStep(32)
        generation_form.addRow(
            "Max new tokens:",
            self.tts_max_new_tokens,
        )

        content_layout.addLayout(generation_form)
        content_layout.addSpacing(12)

        # --------------------------------------------------------------
        # BX1 CHUNKING / AUDIO
        # --------------------------------------------------------------
        pipeline_title = QLabel("BX1 TTS Pipeline")
        pipeline_title.setObjectName("SectionTitle")
        content_layout.addWidget(pipeline_title)

        pipeline_form = QFormLayout()

        self.tts_max_chunk_chars = QSpinBox()
        self.tts_max_chunk_chars.setRange(20, 240)
        pipeline_form.addRow(
            "Max chunk characters:",
            self.tts_max_chunk_chars,
        )

        self.tts_max_batch_chunks = QSpinBox()
        self.tts_max_batch_chunks.setRange(1, 16)
        pipeline_form.addRow(
            "Chunks per GPU batch:",
            self.tts_max_batch_chunks,
        )

        self.tts_split_on_commas = QCheckBox(
            "Allow comma boundaries when splitting speech"
        )
        pipeline_form.addRow("Chunk splitting:", self.tts_split_on_commas)

        self.tts_normalise_quiet = QCheckBox(
            "Normalise unusually quiet generated audio"
        )
        pipeline_form.addRow("Audio normalisation:", self.tts_normalise_quiet)

        self.tts_quiet_threshold = QDoubleSpinBox()
        self.tts_quiet_threshold.setRange(0.01, 1.0)
        self.tts_quiet_threshold.setDecimals(2)
        self.tts_quiet_threshold.setSingleStep(0.01)
        pipeline_form.addRow("Quiet peak threshold:", self.tts_quiet_threshold)

        self.tts_target_peak = QDoubleSpinBox()
        self.tts_target_peak.setRange(0.05, 1.0)
        self.tts_target_peak.setDecimals(2)
        self.tts_target_peak.setSingleStep(0.05)
        pipeline_form.addRow("Normalised target peak:", self.tts_target_peak)

        content_layout.addLayout(pipeline_form)
        content_layout.addSpacing(14)

        # --------------------------------------------------------------
        # APPLY / TEST
        # --------------------------------------------------------------
        test_form = QFormLayout()
        self.tts_test_text = QLineEdit(
            "Hello, I'm Leo. This is a voice replication test."
        )
        test_form.addRow("Test phrase:", self.tts_test_text)
        content_layout.addLayout(test_form)

        button_row = QHBoxLayout()
        apply_button = QPushButton("Apply Voice Settings")
        apply_button.clicked.connect(self.apply_tts_settings)

        test_button = QPushButton("Test Voice")
        test_button.clicked.connect(self.test_tts_voice)

        button_row.addStretch(1)
        button_row.addWidget(apply_button)
        button_row.addWidget(test_button)
        content_layout.addLayout(button_row)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        return page

    def choose_tts_reference(self):
        start_path = self.tts_reference_edit.text().strip()
        start_folder = str(Path(start_path).parent) if start_path else ""

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Qwen Reference Voice",
            start_folder,
            "WAV Audio (*.wav);;All Files (*)",
        )

        if path:
            self.tts_reference_edit.setText(path)
            self.tts_status_label.setText(
                "Reference changed. Press Apply Voice Settings to rebuild the voice."
            )

    def _current_tts_settings_from_form(self):
        model_name = self.tts_model_combo.currentData()
        x_vector_only = bool(self.tts_clone_mode_combo.currentData())

        return {
            "model_name": str(model_name or ""),
            "reference_audio": self.tts_reference_edit.text().strip(),
            "reference_text": self.tts_reference_text.toPlainText().strip(),
            "x_vector_only_mode": x_vector_only,
            "language": self.tts_language_combo.currentText().strip() or "English",
            "max_chunk_chars": self.tts_max_chunk_chars.value(),
            "split_on_commas": self.tts_split_on_commas.isChecked(),
            "max_new_tokens": self.tts_max_new_tokens.value(),
            "max_batch_chunks": self.tts_max_batch_chunks.value(),
            "do_sample": self.tts_do_sample.isChecked(),
            "top_k": self.tts_top_k.value(),
            "top_p": self.tts_top_p.value(),
            "temperature": self.tts_temperature.value(),
            "repetition_penalty": self.tts_repetition_penalty.value(),
            "normalise_quiet_audio": self.tts_normalise_quiet.isChecked(),
            "quiet_peak_threshold": self.tts_quiet_threshold.value(),
            "normalise_target_peak": self.tts_target_peak.value(),
        }

    def apply_tts_settings(self):
        settings = self._current_tts_settings_from_form()

        if not settings["reference_audio"]:
            QMessageBox.warning(
                self,
                "BX1 Voice Settings",
                "Choose a reference WAV first.",
            )
            return

        if (
            not settings["x_vector_only_mode"]
            and not settings["reference_text"]
        ):
            QMessageBox.warning(
                self,
                "BX1 Voice Settings",
                "Full ICL cloning requires the exact transcript of the "
                "reference WAV.",
            )
            return

        self.tts_status_label.setText(
            "Applying voice settings... this can take a few seconds if the "
            "voice profile or model must be reloaded."
        )
        self.controller.request_action(
            "tts_apply_settings",
            settings=settings,
        )

    def test_tts_voice(self):
        text = self.tts_test_text.text().strip()
        if not text:
            return

        self.tts_status_label.setText("Generating test voice...")
        self.controller.request_action(
            "tts_test_voice",
            text=text,
        )

    def set_tts_settings(self, settings: Dict[str, Any]):
        settings = dict(settings or {})
        if not settings:
            return

        model_index = self.tts_model_combo.findData(
            settings.get("model_name")
        )
        if model_index >= 0:
            self.tts_model_combo.setCurrentIndex(model_index)

        self.tts_reference_edit.setText(
            str(settings.get("reference_audio", ""))
        )
        self.tts_reference_text.setPlainText(
            str(settings.get("reference_text", "") or "")
        )

        x_vector_only = bool(settings.get("x_vector_only_mode", True))
        self.tts_clone_mode_combo.setCurrentIndex(1 if x_vector_only else 0)

        language = str(settings.get("language", "English") or "English")
        lang_index = self.tts_language_combo.findText(language)
        if lang_index >= 0:
            self.tts_language_combo.setCurrentIndex(lang_index)
        else:
            self.tts_language_combo.setEditText(language)

        self.tts_max_chunk_chars.setValue(int(settings.get("max_chunk_chars", 55)))
        self.tts_split_on_commas.setChecked(bool(settings.get("split_on_commas", True)))
        self.tts_max_new_tokens.setValue(int(settings.get("max_new_tokens", 128)))
        self.tts_max_batch_chunks.setValue(int(settings.get("max_batch_chunks", 6)))
        self.tts_do_sample.setChecked(bool(settings.get("do_sample", True)))
        self.tts_top_k.setValue(int(settings.get("top_k", 50)))
        self.tts_top_p.setValue(float(settings.get("top_p", 1.0)))
        self.tts_temperature.setValue(float(settings.get("temperature", 0.9)))
        self.tts_repetition_penalty.setValue(
            float(settings.get("repetition_penalty", 1.05))
        )
        self.tts_normalise_quiet.setChecked(
            bool(settings.get("normalise_quiet_audio", True))
        )
        self.tts_quiet_threshold.setValue(
            float(settings.get("quiet_peak_threshold", 0.20))
        )
        self.tts_target_peak.setValue(
            float(settings.get("normalise_target_peak", 0.90))
        )

        clone_name = (
            "speaker embedding only"
            if x_vector_only
            else "full ICL"
        )
        self.tts_status_label.setText(
            f"Active voice: {clone_name} | {Path(settings.get('reference_audio', '')).name}"
        )

    def _build_hardware_page(self):
        return MotorBenchPage(
            self.controller,
            self,
        )

    def _build_balance_learning_page(self):
        return BalanceLearningPage(
            self.controller,
            self,
        )

    def _build_telemetry_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Telemetry")
        title.setObjectName("SectionTitle")

        self.telemetry_table = QTableWidget(0, 3)
        self.telemetry_table.setHorizontalHeaderLabels(
            ["Time", "Signal", "Value"]
        )
        self.telemetry_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(title)
        layout.addWidget(self.telemetry_table, 1)

        return page

    def _build_vision_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)

        title = QLabel("Vision")
        title.setObjectName("SectionTitle")

        self.vision_status_label = QLabel(
            "Camera: waiting for robot stream | YOLO: waiting"
        )
        self.vision_status_label.setWordWrap(True)

        outer.addWidget(title)
        outer.addWidget(self.vision_status_label)

        image_row = QHBoxLayout()

        live_box = QFrame()
        live_layout = QVBoxLayout(live_box)

        live_title = QLabel("Live Robot Camera")
        live_title.setStyleSheet(
            "font-weight: 700;"
        )

        self.live_video_label = QLabel(
            "No camera frames received"
        )
        self.live_video_label.setAlignment(
            Qt.AlignCenter
        )
        self.live_video_label.setMinimumSize(
            320,
            240,
        )
        self.live_video_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        live_layout.addWidget(live_title)
        live_layout.addWidget(
            self.live_video_label,
            1,
        )

        yolo_box = QFrame()
        yolo_layout = QVBoxLayout(yolo_box)

        yolo_title = QLabel("YOLO Detection")
        yolo_title.setStyleSheet(
            "font-weight: 700;"
        )

        self.yolo_video_label = QLabel(
            "Waiting for YOLO result"
        )
        self.yolo_video_label.setAlignment(
            Qt.AlignCenter
        )
        self.yolo_video_label.setMinimumSize(
            320,
            240,
        )
        self.yolo_video_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        yolo_layout.addWidget(yolo_title)
        yolo_layout.addWidget(
            self.yolo_video_label,
            1,
        )

        image_row.addWidget(live_box, 1)
        image_row.addWidget(yolo_box, 1)

        outer.addLayout(image_row, 2)

        stats_row = QHBoxLayout()

        self.video_fps_label = QLabel(
            "Video FPS: 0.0"
        )
        self.video_bandwidth_label = QLabel(
            "Bandwidth: 0.0 kB/s"
        )
        self.yolo_time_label = QLabel(
            "YOLO: -- ms"
        )
        self.yolo_count_label = QLabel(
            "Objects: 0"
        )

        stats_row.addWidget(
            self.video_fps_label
        )
        stats_row.addWidget(
            self.video_bandwidth_label
        )
        stats_row.addWidget(
            self.yolo_time_label
        )
        stats_row.addWidget(
            self.yolo_count_label
        )
        stats_row.addStretch(1)

        outer.addLayout(stats_row)

        button_row = QHBoxLayout()

        enable_yolo = QPushButton(
            "Enable YOLO"
        )
        enable_yolo.clicked.connect(
            lambda: self.controller.request_action(
                "vision_enable"
            )
        )

        pause_yolo = QPushButton(
            "Pause YOLO"
        )
        pause_yolo.clicked.connect(
            lambda: self.controller.request_action(
                "vision_disable"
            )
        )

        button_row.addWidget(enable_yolo)
        button_row.addWidget(pause_yolo)
        button_row.addStretch(1)

        outer.addLayout(button_row)

        # --------------------------------------------------------------
        # HEAD SERVO CONTROL
        # --------------------------------------------------------------
        head_box = QFrame()
        head_layout = QVBoxLayout(head_box)

        head_title = QLabel("Head Control")
        head_title.setStyleSheet("font-weight: 700;")

        self.head_status_label = QLabel(
            "Head servos: waiting for robot controller"
        )
        self.head_status_label.setWordWrap(True)

        self.head_position_label = QLabel(
            "Pan: 0.0°   Look: 0.0°   Tilt: 0.0°"
        )
        self.head_position_label.setStyleSheet("font-weight: 600;")

        self.head_servo_pulse_label = QLabel(
            "D9: 1500 µs   D11: 1500 µs   D10: 1500 µs"
        )

        head_layout.addWidget(head_title)
        head_layout.addWidget(self.head_status_label)
        head_layout.addWidget(self.head_position_label)
        head_layout.addWidget(self.head_servo_pulse_label)

        # A conservative 3 degree increment matches the small head-motion
        # tests already used on BX1. The robot clamps every command again.
        head_step = 3.0

        pan_row = QHBoxLayout()
        pan_left = QPushButton("Pan Left")
        pan_left.clicked.connect(
            lambda: self.controller.request_action(
                "head_move",
                pan_delta=-head_step,
            )
        )

        head_center = QPushButton("Centre Head")
        head_center.clicked.connect(
            lambda: self.controller.request_action(
                "head_center"
            )
        )

        pan_right = QPushButton("Pan Right")
        pan_right.clicked.connect(
            lambda: self.controller.request_action(
                "head_move",
                pan_delta=head_step,
            )
        )

        pan_row.addWidget(pan_left)
        pan_row.addWidget(head_center)
        pan_row.addWidget(pan_right)
        pan_row.addStretch(1)

        pose_row = QHBoxLayout()

        look_up = QPushButton("Look Up")
        look_up.clicked.connect(
            lambda: self.controller.request_action(
                "head_move",
                pitch_delta=head_step,
            )
        )

        look_down = QPushButton("Look Down")
        look_down.clicked.connect(
            lambda: self.controller.request_action(
                "head_move",
                pitch_delta=-head_step,
            )
        )

        tilt_left = QPushButton("Tilt Left")
        tilt_left.clicked.connect(
            lambda: self.controller.request_action(
                "head_move",
                roll_delta=-head_step,
            )
        )

        tilt_right = QPushButton("Tilt Right")
        tilt_right.clicked.connect(
            lambda: self.controller.request_action(
                "head_move",
                roll_delta=head_step,
            )
        )

        pose_row.addWidget(look_up)
        pose_row.addWidget(look_down)
        pose_row.addSpacing(12)
        pose_row.addWidget(tilt_left)
        pose_row.addWidget(tilt_right)
        pose_row.addStretch(1)

        head_layout.addLayout(pan_row)
        head_layout.addLayout(pose_row)

        outer.addWidget(head_box)

        self.detection_table = QTableWidget(
            0,
            6,
        )
        self.detection_table.setHorizontalHeaderLabels(
            [
                "Class",
                "Confidence",
                "X1",
                "Y1",
                "X2",
                "Y2",
            ]
        )
        self.detection_table.horizontalHeader().setStretchLastSection(
            True
        )

        outer.addWidget(
            self.detection_table,
            1,
        )

        return page


    def set_live_video_frame(
        self,
        jpeg_bytes: bytes,
        metadata: Dict[str, Any],
    ):
        pixmap = QPixmap()
        pixmap.loadFromData(
            jpeg_bytes,
            "JPG",
        )

        if not pixmap.isNull():
            target = self.live_video_label.size()

            self.live_video_label.setPixmap(
                pixmap.scaled(
                    target,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        self.video_fps_label.setText(
            "Video FPS: "
            + str(
                metadata.get(
                    "fps",
                    0.0,
                )
            )
        )

        self.video_bandwidth_label.setText(
            "Bandwidth: "
            + str(
                metadata.get(
                    "bandwidth_kbps",
                    0.0,
                )
            )
            + " kB/s"
        )


    def set_vision_result(
        self,
        annotated_jpeg: bytes,
        result: Dict[str, Any],
    ):
        pixmap = QPixmap()
        pixmap.loadFromData(
            annotated_jpeg,
            "JPG",
        )

        if not pixmap.isNull():
            target = self.yolo_video_label.size()

            self.yolo_video_label.setPixmap(
                pixmap.scaled(
                    target,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        inference_ms = result.get(
            "inference_ms",
            "--",
        )

        detections = result.get(
            "detections",
            [],
        )

        self.yolo_time_label.setText(
            f"YOLO: {inference_ms} ms"
        )
        self.yolo_count_label.setText(
            f"Objects: {len(detections)}"
        )

        self.detection_table.setRowCount(
            len(detections)
        )

        for row, detection in enumerate(
            detections
        ):
            xyxy = list(
                detection.get(
                    "xyxy",
                    [0, 0, 0, 0],
                )
            )

            while len(xyxy) < 4:
                xyxy.append(0)

            values = [
                detection.get(
                    "class_name",
                    "",
                ),
                f"{float(detection.get('confidence', 0.0)) * 100.0:.1f}%",
                xyxy[0],
                xyxy[1],
                xyxy[2],
                xyxy[3],
            ]

            for column, value in enumerate(
                values
            ):
                self.detection_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(
                        str(value)
                    ),
                )


    def set_vision_status(
        self,
        status: Dict[str, Any],
    ):
        event = str(
            status.get(
                "event",
                "",
            )
        )

        if event == "video_client_connected":
            self.vision_status_label.setText(
                "Camera: connected | YOLO: waiting/active"
            )

        elif event == "video_client_disconnected":
            self.vision_status_label.setText(
                "Camera: disconnected | YOLO: waiting"
            )

        elif event == "video_server_started":
            self.vision_status_label.setText(
                "Camera receiver ready on port "
                + str(
                    status.get(
                        "port",
                        8772,
                    )
                )
                + " | waiting for robot"
            )

        elif event == "yolo_loading":
            self.vision_status_label.setText(
                "Camera receiver active | YOLO model loading..."
            )

        elif event == "yolo_ready":
            self.vision_status_label.setText(
                "Camera receiver active | YOLO ready"
            )

        elif event == "yolo_paused":
            self.vision_status_label.setText(
                "Camera receiver active | YOLO paused"
            )

        elif event == "yolo_enabled":
            self.vision_status_label.setText(
                "Camera receiver active | YOLO enabled"
            )

        elif event == "yolo_unavailable":
            self.vision_status_label.setText(
                "Camera receiver active | YOLO unavailable: "
                + str(
                    status.get(
                        "error",
                        "",
                    )
                )
            )

        elif event.endswith("_error"):
            self.vision_status_label.setText(
                event
                + ": "
                + str(
                    status.get(
                        "error",
                        "",
                    )
                )
            )


    def set_head_state(
        self,
        state: Dict[str, Any],
    ):
        pan = float(state.get("pan", 0.0))
        pitch = float(state.get("pitch", 0.0))
        roll = float(state.get("roll", 0.0))

        self.head_position_label.setText(
            f"Pan: {pan:+.1f}°   "
            f"Look: {pitch:+.1f}°   "
            f"Tilt: {roll:+.1f}°"
        )

        pulses = dict(
            state.get("servo_pulses_us", {})
        )

        self.head_servo_pulse_label.setText(
            "D9: "
            + str(pulses.get("yaw_d9", "--"))
            + " µs   D11: "
            + str(pulses.get("neck_left_d11", "--"))
            + " µs   D10: "
            + str(pulses.get("neck_right_d10", "--"))
            + " µs"
        )

        if bool(state.get("mcu_ok", True)):
            self.head_status_label.setText(
                "Head servos connected | "
                "position = MCU commanded target"
            )
        else:
            self.head_status_label.setText(
                "Head controller connected but MCU servo command failed"
            )


    def set_head_status(
        self,
        status: Dict[str, Any],
    ):
        event = str(status.get("event", ""))

        if event == "head_server_started":
            self.head_status_label.setText(
                "Head control receiver ready on port "
                + str(status.get("port", 8773))
                + " | waiting for robot"
            )

        elif event == "head_client_connected":
            self.head_status_label.setText(
                "Head servos connected | waiting for position state"
            )

        elif event == "head_client_disconnected":
            self.head_status_label.setText(
                "Head servos disconnected"
            )

        elif event.endswith("_error") or event == "head_command_rejected":
            self.head_status_label.setText(
                "Head control: "
                + str(status.get("error", event))
            )


    def _build_personality_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)

        title = QLabel("Personality")
        title.setObjectName("SectionTitle")

        description = QLabel(
            "Edit the robot identity and personality. Settings are saved "
            "to settings/personality.json and applied to the active LLM."
        )
        description.setWordWrap(True)

        outer.addWidget(title)
        outer.addWidget(description)

        form = QFormLayout()

        self.personality_name_edit = QLineEdit(
            self.personality.get_name()
        )
        form.addRow(
            "Name:",
            self.personality_name_edit,
        )
        outer.addLayout(form)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        self.personality_sliders = {}
        self.personality_value_labels = {}

        current = self.personality.get_all()

        for key in DEFAULT_PERSONALITY:
            row = QHBoxLayout()

            label = QLabel(DISPLAY_NAMES[key])
            label.setMinimumWidth(150)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(current[key]))

            value_label = QLabel(f"{int(current[key])}%")
            value_label.setMinimumWidth(45)
            value_label.setAlignment(
                Qt.AlignRight | Qt.AlignVCenter
            )

            slider.valueChanged.connect(
                lambda value, target=value_label:
                    target.setText(f"{value}%")
            )

            self.personality_sliders[key] = slider
            self.personality_value_labels[key] = value_label

            row.addWidget(label)
            row.addWidget(slider, 1)
            row.addWidget(value_label)

            content_layout.addLayout(row)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        button_row = QHBoxLayout()

        reload_button = QPushButton("Reload Saved")
        reload_button.clicked.connect(
            self.reload_personality_page
        )

        save_button = QPushButton("Save Personality")
        save_button.clicked.connect(
            self.save_personality_page
        )

        button_row.addStretch(1)
        button_row.addWidget(reload_button)
        button_row.addWidget(save_button)

        outer.addLayout(button_row)

        return page


    def reload_personality_page(self):
        self.personality.load()

        self.personality_name_edit.setText(
            self.personality.get_name()
        )

        values = self.personality.get_all()

        for key, slider in self.personality_sliders.items():
            slider.setValue(int(values[key]))


    def save_personality_page(self):
        values = {
            key: slider.value()
            for key, slider in self.personality_sliders.items()
        }

        try:
            saved = self.personality.set_many(
                values,
                name=self.personality_name_edit.text(),
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "BX1 Personality",
                str(exc),
            )
            return

        self.set_robot_display_name(
            saved["name"]
        )

        self.controller.request_action(
            "personality_changed",
            name=saved["name"],
            settings={
                key: saved[key]
                for key in DEFAULT_PERSONALITY
            },
        )

        QMessageBox.information(
            self,
            "BX1 Personality",
            "Personality settings saved and applied.",
        )


    def set_robot_display_name(self, name: str):
        name = str(name or "LEO").strip() or "LEO"
        self.robot_display_name = name

        self.robot_name.setText(name)
        self.chat_heading.setText(
            f"ROBO-CHAT — {name}"
        )
        self.setWindowTitle(
            f"BX1_DEV — {name}"
        )

        for message_id, message in self._messages.items():
            sender = str(message.get("sender", ""))

            if sender.upper() in {"YOU", "BACKGROUND"}:
                continue

            message["sender"] = name

            bubble = self._message_bubbles.get(message_id)
            if bubble is not None:
                bubble.set_sender(name)

        selected_id = self.inspector_message_id.text()
        if selected_id in self._messages:
            self.show_reply_inspector(selected_id)


    def _build_events_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Events")
        title.setObjectName("SectionTitle")

        self.event_list = QListWidget()

        layout.addWidget(title)
        layout.addWidget(self.event_list, 1)

        return page

    def _build_debug_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Debug")
        title.setObjectName("SectionTitle")

        self.debug_text = QTextEdit()
        self.debug_text.setReadOnly(True)

        layout.addWidget(title)
        layout.addWidget(self.debug_text, 1)

        return page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Settings")
        title.setObjectName("SectionTitle")

        form = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())

        current_theme = self.settings.value(
            "appearance/theme",
            "Ocean Blue",
            type=str,
        )
        if current_theme in THEMES:
            self.theme_combo.setCurrentText(current_theme)

        self.theme_combo.currentTextChanged.connect(
            self.apply_theme
        )

        form.addRow("Theme:", self.theme_combo)

        robot_row = QHBoxLayout()
        self.robot_image_path_label = QLabel(
            self.robot_image or "Default / no image selected"
        )
        self.robot_image_path_label.setWordWrap(True)

        choose_robot = QPushButton("Choose Image...")
        choose_robot.clicked.connect(
            self.choose_robot_image
        )

        clear_robot = QPushButton("Clear")
        clear_robot.clicked.connect(
            self.clear_robot_image
        )

        robot_row.addWidget(choose_robot)
        robot_row.addWidget(clear_robot)

        robot_widget = QWidget()
        robot_widget_layout = QVBoxLayout(robot_widget)
        robot_widget_layout.setContentsMargins(0, 0, 0, 0)
        robot_widget_layout.addWidget(self.robot_image_path_label)
        robot_widget_layout.addLayout(robot_row)

        form.addRow("Robot image:", robot_widget)

        icon_row = QHBoxLayout()
        self.app_icon_path_label = QLabel(
            self.app_icon_path or "Default application icon"
        )
        self.app_icon_path_label.setWordWrap(True)

        choose_icon = QPushButton("Choose Icon...")
        choose_icon.clicked.connect(
            self.choose_app_icon
        )

        clear_icon = QPushButton("Clear")
        clear_icon.clicked.connect(
            self.clear_app_icon
        )

        icon_row.addWidget(choose_icon)
        icon_row.addWidget(clear_icon)

        icon_widget = QWidget()
        icon_widget_layout = QVBoxLayout(icon_widget)
        icon_widget_layout.setContentsMargins(0, 0, 0, 0)
        icon_widget_layout.addWidget(self.app_icon_path_label)
        icon_widget_layout.addLayout(icon_row)

        form.addRow("App icon:", icon_widget)

        connection_title = QLabel("Robot Connection")
        connection_title.setObjectName("SectionTitle")

        connection = self.robot_connections.connection()

        self.local_robot_ip = QLineEdit(
            connection.get(
                "local_ip",
                "",
            )
        )

        self.tailscale_robot_ip = QLineEdit(
            connection.get(
                "tailscale_ip",
                "",
            )
        )

        self.connection_preference = QComboBox()
        self.connection_preference.addItems(
            [
                "LOCAL",
                "TAILSCALE",
            ]
        )
        self.connection_preference.setCurrentText(
            connection.get(
                "preferred",
                "LOCAL",
            )
        )

        local_test_button = QPushButton(
            "Test Local"
        )
        local_test_button.clicked.connect(
            lambda: self.test_robot_connection(
                "LOCAL"
            )
        )

        tailscale_test_button = QPushButton(
            "Test Tailscale"
        )
        tailscale_test_button.clicked.connect(
            lambda: self.test_robot_connection(
                "TAILSCALE"
            )
        )

        save_connection_button = QPushButton(
            "Save Connection Settings"
        )
        save_connection_button.clicked.connect(
            self.save_robot_connection_settings
        )

        connection_form = QFormLayout()
        connection_form.addRow(
            "Local robot IP:",
            self.local_robot_ip,
        )
        connection_form.addRow(
            "Tailscale robot IP:",
            self.tailscale_robot_ip,
        )
        connection_form.addRow(
            "Preferred:",
            self.connection_preference,
        )

        test_row = QHBoxLayout()
        test_row.addWidget(local_test_button)
        test_row.addWidget(tailscale_test_button)

        history_info = QLabel(
            "Conversation, timing, event and telemetry history is kept only "
            "for the current BX1 session. Closing the program clears it. "
            "Use Export Data when you want to keep a debug record."
        )
        history_info.setWordWrap(True)

        layout.addWidget(title)
        layout.addLayout(form)
        layout.addSpacing(18)
        layout.addWidget(connection_title)
        layout.addLayout(connection_form)
        layout.addLayout(test_row)
        layout.addWidget(save_connection_button)
        layout.addSpacing(18)
        layout.addWidget(history_info)
        layout.addStretch(1)

        return page

    def _build_inspector(self):
        frame = QFrame()
        frame.setObjectName("Inspector")
        frame.setFixedWidth(330)

        layout = QVBoxLayout(frame)

        title = QLabel("REPLY INSPECTOR")
        title.setObjectName("SectionTitle")

        self.inspector_message_id = QLabel("No reply selected")
        self.inspector_summary = QTextEdit()
        self.inspector_summary.setReadOnly(True)

        layout.addWidget(title)
        layout.addWidget(self.inspector_message_id)
        layout.addWidget(self.inspector_summary, 1)

        return frame

    @staticmethod
    def _placeholder_page(title_text: str, description: str):
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")

        description_label = QLabel(description)
        description_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description_label)
        layout.addStretch(1)

        return page

    # ------------------------------------------------------------------
    # ROBOT CONNECTION SETTINGS
    # ------------------------------------------------------------------

    def save_robot_connection_settings(self):
        self.robot_connections.save(
            local_ip=self.local_robot_ip.text(),
            tailscale_ip=self.tailscale_robot_ip.text(),
            preferred=self.connection_preference.currentText(),
            web_port=8088,
        )

        QMessageBox.information(
            self,
            "BX1 Robot Connection",
            "Robot connection settings saved.",
        )

    def test_robot_connection(
        self,
        connection_type: str,
    ):
        # Save the current text first so the test uses what is visible.
        self.robot_connections.save(
            local_ip=self.local_robot_ip.text(),
            tailscale_ip=self.tailscale_robot_ip.text(),
            preferred=self.connection_preference.currentText(),
            web_port=8088,
        )

        ok, message = self.robot_connections.test(
            connection_type
        )

        if ok:
            QMessageBox.information(
                self,
                "BX1 Connection Test",
                message,
            )
        else:
            QMessageBox.warning(
                self,
                "BX1 Connection Test",
                message,
            )

    # ------------------------------------------------------------------
    # APPEARANCE SETTINGS
    # ------------------------------------------------------------------

    def choose_robot_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Robot Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )

        if not path:
            return

        self.robot_image = path
        self.settings.setValue(
            "appearance/robot_image",
            path,
        )
        self.robot_image_path_label.setText(path)
        self._load_robot_image(path)

    def clear_robot_image(self):
        self.robot_image = None
        self.settings.remove(
            "appearance/robot_image"
        )
        self.robot_image_path_label.setText(
            "Default / no image selected"
        )
        self._load_robot_image(None)

    def choose_app_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose BX1 Application Icon",
            "",
            "Icons / Images (*.ico *.png *.jpg *.jpeg);;All Files (*)",
        )

        if not path:
            return

        self.app_icon_path = path
        self.settings.setValue(
            "appearance/app_icon",
            path,
        )
        self.app_icon_path_label.setText(path)
        self._apply_app_icon(path)

    def clear_app_icon(self):
        self.app_icon_path = None
        self.settings.remove(
            "appearance/app_icon"
        )
        self.app_icon_path_label.setText(
            "Default application icon"
        )
        self.setWindowIcon(QIcon())

        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(QIcon())

    def _apply_app_icon(self, image_path: Optional[str]):
        if not image_path:
            return

        path = Path(image_path)
        if not path.exists():
            return

        icon = QIcon(str(path))
        if icon.isNull():
            return

        self.setWindowIcon(icon)

        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

    # ------------------------------------------------------------------
    # CONTROLLER CONNECTIONS
    # ------------------------------------------------------------------

    def _connect_controller(self):
        self.controller.mode_changed.connect(self.set_mode)
        self.controller.connection_changed.connect(self.set_connection)

        self.controller.user_message_received.connect(
            lambda message_id, text: self.add_message(
                "YOU",
                text,
                message_id,
            )
        )

        self.controller.background_message_received.connect(
            lambda message_id, text: self.add_message(
                "BACKGROUND",
                text,
                message_id,
            )
        )

        self.controller.leo_message_received.connect(
            lambda message_id, text: self.add_message(
                self.robot_display_name,
                text,
                message_id,
            )
        )

        self.controller.event_received.connect(self.add_event)
        self.controller.telemetry_received.connect(self.add_telemetry)
        self.controller.reply_metrics_received.connect(self.set_reply_metrics)

        self.controller.video_frame_received.connect(
            self.set_live_video_frame
        )
        self.controller.vision_result_received.connect(
            self.set_vision_result
        )
        self.controller.vision_status_received.connect(
            self.set_vision_status
        )

        self.controller.head_state_received.connect(
            self.set_head_state
        )
        self.controller.head_status_received.connect(
            self.set_head_status
        )

        self.controller.tts_settings_received.connect(
            self.set_tts_settings
        )

        self.controller.clear_requested.connect(self.clear_all)

    # ------------------------------------------------------------------
    # GUI ACTIONS
    # ------------------------------------------------------------------

    def _select_page(self, index: int, selected_button: QPushButton):
        self.pages.setCurrentIndex(index)

        for button in self.nav_buttons.values():
            button.setChecked(button is selected_button)

    def _send_message(self):
        text = self.message_entry.text().strip()

        if not text:
            return

        self.controller.request_user_message(text)
        self.message_entry.clear()

    def apply_theme(self, theme_name: str):
        base_stylesheet = THEMES.get(theme_name, THEMES["Ocean Blue"])
        action_stylesheet = ACTION_BUTTON_STYLES.get(
            theme_name,
            ACTION_BUTTON_STYLES["Ocean Blue"],
        )
        self.setStyleSheet(
            base_stylesheet
            + action_stylesheet
            + ACTION_BUTTON_DISABLED_STYLE
        )
        self.settings.setValue(
            "appearance/theme",
            theme_name,
        )

    def set_mode(self, mode: str):
        self.mode_label.setText(str(mode).upper())

    def set_connection(self, connected: bool, robot_name: str):
        # Hardware connection identity is separate from personality name.
        if connected:
            self.connection_label.setText("● Robot Online")
            self.connection_label.setObjectName("Online")
        else:
            self.connection_label.setText("● Robot Offline")
            self.connection_label.setObjectName("Offline")

        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)

    def add_message(
        self,
        sender: str,
        text: str,
        message_id: str,
    ):
        self._messages[message_id] = {
            "sender": sender,
            "text": text,
        }


        bubble = MessageBubble(
            sender=sender,
            text=text,
            message_id=message_id,
            click_callback=self.show_reply_inspector,
        )

        self._message_bubbles[message_id] = bubble

        for stage, state in self._message_stage_states.get(
            message_id,
            {},
        ).items():
            bubble.set_stage_state(
                stage,
                state,
            )

        self.chat_layout.addWidget(bubble)

        QTimer.singleShot(
            0,
            lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ),
        )

    def add_event(self, event: Dict[str, Any]):
        self._events.append(event)

        timestamp = datetime.fromtimestamp(
            event.get("timestamp", 0)
        ).strftime("%H:%M:%S.%f")[:-3]

        source = event.get("source", "")
        name = event.get("event", "")
        message_id = event.get("message_id") or ""

        line = f"{timestamp}  {source:<10} {name:<26} {message_id}"

        self.event_list.addItem(QListWidgetItem(line))
        self.event_list.scrollToBottom()

        self.debug_text.append(line)

        if name == "tts_settings_applied":
            self.tts_status_label.setText(
                "Voice settings applied successfully."
            )
        elif name == "tts_settings_error":
            error_text = str(
                event.get("data", {}).get("error", "Unknown TTS settings error")
            )
            self.tts_status_label.setText(
                "Voice settings error: " + error_text
            )
        elif name == "tts_test_completed":
            self.tts_status_label.setText(
                "Voice test completed."
            )
        elif name == "tts_test_error":
            error_text = str(
                event.get("data", {}).get("error", "Unknown TTS test error")
            )
            self.tts_status_label.setText(
                "Voice test error: " + error_text
            )

        self._apply_chat_process_event(
            event
        )

    def _set_message_stage(
        self,
        message_id: str,
        stage: str,
        state: str,
    ):
        if not message_id:
            return

        states = self._message_stage_states.setdefault(
            message_id,
            {},
        )
        states[stage] = state

        bubble = self._message_bubbles.get(
            message_id
        )

        if bubble is not None:
            bubble.set_stage_state(
                stage,
                state,
            )

    def _set_bottom_stage(
        self,
        stage: str,
        state: str,
    ):
        indicator = self.chat_stage_indicators.get(
            stage
        )

        if indicator is not None:
            indicator.set_state(state)

    def _apply_chat_process_event(
        self,
        event: Dict[str, Any],
    ):
        name = str(
            event.get("event", "")
        )
        message_id = event.get(
            "message_id"
        )

        if name == "llm_started":
            self._set_message_stage(
                message_id,
                "thinking",
                "active",
            )
            self._set_bottom_stage(
                "thinking",
                "active",
            )
            self._set_bottom_stage(
                "generating_audio",
                "idle",
            )
            self._set_bottom_stage(
                "playing_audio",
                "idle",
            )

        elif name == "llm_completed":
            self._set_message_stage(
                message_id,
                "thinking",
                "complete",
            )
            self._set_bottom_stage(
                "thinking",
                "complete",
            )

        elif name == "tts_started":
            self._set_message_stage(
                message_id,
                "generating_audio",
                "active",
            )
            self._set_bottom_stage(
                "generating_audio",
                "active",
            )

        elif name == "audio_generation_completed":
            self._set_message_stage(
                message_id,
                "generating_audio",
                "complete",
            )
            self._set_bottom_stage(
                "generating_audio",
                "complete",
            )

        elif name == "audio_playback_started":
            self._set_message_stage(
                message_id,
                "playing_audio",
                "active",
            )
            self._set_bottom_stage(
                "playing_audio",
                "active",
            )

        elif name == "audio_playback_completed":
            self._set_message_stage(
                message_id,
                "playing_audio",
                "complete",
            )
            self._set_bottom_stage(
                "playing_audio",
                "complete",
            )

    def add_telemetry(self, telemetry: Dict[str, Any]):
        self._telemetry.append(telemetry)

        timestamp = datetime.fromtimestamp(
            telemetry.get("timestamp", 0)
        ).strftime("%H:%M:%S")

        for key, value in telemetry.items():
            if key == "timestamp":
                continue

            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    self._append_telemetry_row(
                        timestamp,
                        f"{key}.{sub_key}",
                        sub_value,
                    )
            else:
                self._append_telemetry_row(
                    timestamp,
                    key,
                    value,
                )

    def _append_telemetry_row(
        self,
        timestamp: str,
        signal: str,
        value: Any,
    ):
        row = self.telemetry_table.rowCount()
        self.telemetry_table.insertRow(row)

        self.telemetry_table.setItem(
            row,
            0,
            QTableWidgetItem(timestamp),
        )
        self.telemetry_table.setItem(
            row,
            1,
            QTableWidgetItem(str(signal)),
        )
        self.telemetry_table.setItem(
            row,
            2,
            QTableWidgetItem(str(value)),
        )

        self.telemetry_table.scrollToBottom()

    def set_reply_metrics(
        self,
        message_id: str,
        metrics: Dict[str, Any],
    ):
        self._metrics[message_id] = metrics

        if self.inspector_message_id.text() == message_id:
            self.show_reply_inspector(message_id)

    def show_reply_inspector(self, message_id: str):
        """Show data for the exact message selected in this session."""
        self.inspector_message_id.setText(message_id)

        message = self._messages.get(
            message_id,
            {},
        )

        metrics = self._metrics.get(
            message_id,
            {},
        )

        events = [
            event
            for event in self._events
            if event.get("message_id") == message_id
        ]

        lines = []

        if message:
            lines.append(
                f"Sender: {message.get('sender', '')}"
            )
            lines.append("")
            lines.append(
                message.get("text", "")
            )
            lines.append("")

        if metrics:
            lines.append("TIMING / GENERATION")
            lines.append("-------------------")

            for key, value in metrics.items():
                if isinstance(value, dict):
                    continue

                lines.append(
                    f"{key}: {value}"
                )

            nested = {
                key: value
                for key, value in metrics.items()
                if isinstance(value, dict)
            }

            for section, values in nested.items():
                lines.append("")
                lines.append(section.upper())
                lines.append("-" * len(section))

                for key, value in values.items():
                    lines.append(
                        f"{key}: {value}"
                    )

        if events:
            lines.append("")
            lines.append("EVENT TIMELINE")
            lines.append("--------------")

            for event in events:
                timestamp = datetime.fromtimestamp(
                    event.get("timestamp", 0)
                ).strftime("%H:%M:%S.%f")[:-3]

                source = event.get("source", "")
                event_name = event.get("event", "")

                lines.append(
                    f"{timestamp}  {source}  {event_name}"
                )

        if not message and not metrics and not events:
            lines.append(
                "No information is available for this message "
                "in the current session."
            )
        elif message and not metrics and not events:
            lines.append(
                "No generation timing was recorded for this message."
            )

        self.inspector_summary.setPlainText(
            "\n".join(lines)
        )

    def clear_all(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self._messages.clear()
        self._metrics.clear()
        self._message_bubbles.clear()
        self._message_stage_states.clear()
        self._events.clear()
        self._telemetry.clear()

        self.event_list.clear()
        self.debug_text.clear()
        self.telemetry_table.setRowCount(0)

        if hasattr(self, "hardware_page") and hasattr(self.hardware_page, "clear_charts"):
            self.hardware_page.clear_charts()

        self.inspector_message_id.setText("No reply selected")
        self.inspector_summary.clear()

        for indicator in self.chat_stage_indicators.values():
            indicator.set_state("idle")

    def _load_robot_image(self, image_path: Optional[str]):
        if image_path:
            path = Path(image_path)

            if path.exists():
                pixmap = QPixmap(str(path))

                if not pixmap.isNull():
                    self.robot_picture.setPixmap(
                        pixmap.scaled(
                            150,
                            130,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    )
                    return

        self.robot_picture.setText("LEO")


def run_gui(
    controller: GUIController,
    *,
    robot_image: Optional[str] = None,
) -> int:
    """
    Start the BX1 PySide6 GUI.

    This function should eventually be started by Master_Main.py.
    """
    app = QApplication.instance()

    owns_app = app is None

    if app is None:
        app = QApplication([])

    window = BX1MainWindow(
        controller=controller,
        robot_image=robot_image,
    )

    window.show()

    if owns_app:
        return app.exec()

    return 0


if __name__ == "__main__":
    # Standalone GUI preview only.
    #
    # This does not replace Master_Main.py. It allows the layout/themes
    # to be developed without needing the robot or LLM stack running.
    controller = GUIController()

    controller.set_mode("LOCAL")
    controller.set_robot_connection(False, "LEO-01")

    def preview_command(command):
        if command.name == "user_message":
            message_id = controller.publish_user_message(
                command.data["text"]
            )

            reply_id = controller.publish_leo_message(
                "GUI preview mode. Master_Main.py is not connected.",
                "reply_" + message_id[4:],
            )

            controller.publish_reply_metrics(
                reply_id,
                {
                    "stt_ms": 0,
                    "llm_ms": 1100,
                    "tts_ms": 560,
                    "total_response_ms": 2410,
                    "mode": "PREVIEW",
                    "system_at_request": {
                        "battery": "N/A",
                        "cpu": "31%",
                        "memory": "64%",
                    },
                },
            )

    controller.set_command_handler(preview_command)

    run_gui(controller)
