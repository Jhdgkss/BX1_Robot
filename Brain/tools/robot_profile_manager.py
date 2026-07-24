from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from robot_brain.profile_store import ProfileStore, RobotProfile, safe_slug
from bx1_modules.persona_presets import (
    FEMALE_COMPANION_PROFILE,
    FEMALE_COMPANION_PROMPT,
)


DEFAULT_PERSONALITY = (
    "You are {robot_name}, {robot_profile}. Be helpful, concise, curious and honest. "
    "Keep a consistent character while respecting robot safety limits. Never claim a "
    "physical action happened unless body telemetry confirms it."
)


class AuroraBackground(QWidget):
    """Paints a soft fallback backdrop when native Windows Mica is unavailable."""

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt method name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        background = QLinearGradient(0, 0, self.width(), self.height())
        background.setColorAt(0.0, QColor(5, 14, 26, 238))
        background.setColorAt(0.48, QColor(10, 25, 43, 229))
        background.setColorAt(1.0, QColor(4, 12, 23, 242))
        painter.fillRect(self.rect(), QBrush(background))

        blue = QRadialGradient(self.width() * 0.18, self.height() * 0.08, self.width() * 0.56)
        blue.setColorAt(0.0, QColor(22, 137, 215, 78))
        blue.setColorAt(1.0, QColor(22, 137, 215, 0))
        painter.fillRect(self.rect(), QBrush(blue))

        teal = QRadialGradient(self.width() * 0.88, self.height() * 0.92, self.width() * 0.48)
        teal.setColorAt(0.0, QColor(25, 205, 184, 48))
        teal.setColorAt(1.0, QColor(25, 205, 184, 0))
        painter.fillRect(self.rect(), QBrush(teal))
        super().paintEvent(event)


class GlassPanel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("glassPanel")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 105))
        self.setGraphicsEffect(shadow)


class ProfileManager(QMainWindow):
    profile_switch_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, *, integrated: bool = False) -> None:
        super().__init__(parent)
        self.integrated = integrated
        self.store = ProfileStore(ROOT)
        self.profiles: list[RobotProfile] = []
        self._backdrop_attempted = False
        self._fade_animation: QPropertyAnimation | None = None
        self._slug_was_edited = False

        self.setWindowTitle("Robot Brain — Profile Manager")
        self.setWindowIcon(self._make_window_icon())
        self.resize(1180, 820)
        self.setMinimumSize(980, 700)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._build_interface()
        self._apply_style()
        self.refresh_profiles()

    @staticmethod
    def _make_window_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(8, 8, 56, 56)
        gradient.setColorAt(0.0, QColor("#48baff"))
        gradient.setColorAt(1.0, QColor("#2ad9b2"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(5, 5, 54, 54), 18, 18)
        painter.setPen(QColor("#04111f"))
        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "RB")
        painter.end()
        return QIcon(pixmap)

    def _build_interface(self) -> None:
        root = AuroraBackground()
        root.setObjectName("auroraRoot")
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(34, 28, 34, 28)
        page.setSpacing(22)

        header = QHBoxLayout()
        header.setSpacing(15)
        logo = QLabel("RB")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(56, 56)
        header.addWidget(logo)

        heading = QVBoxLayout()
        heading.setSpacing(1)
        title = QLabel("Robot Brain")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Choose a robot profile or create a completely independent one")
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()

        platform_badge = QLabel("●  PROFILE ISOLATION ON")
        platform_badge.setObjectName("statusBadge")
        platform_badge.setToolTip("Each robot owns its identity, personality, voice, ports, memory and runtime data.")
        header.addWidget(platform_badge)
        page.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(22)
        page.addLayout(content, 1)

        content.addWidget(self._build_profile_panel(), 5)
        content.addWidget(self._build_create_panel(), 7)

        footer = QHBoxLayout()
        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("footerStatus")
        footer.addWidget(self.status_label)
        footer.addStretch()
        safety = QLabel("Shared brain • Independent robots • Body controller owns safety")
        safety.setObjectName("footerNote")
        footer.addWidget(safety)
        page.addLayout(footer)

    def _build_profile_panel(self) -> GlassPanel:
        panel = GlassPanel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        eyebrow = QLabel("YOUR ROBOTS")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Select a profile")
        title.setObjectName("panelTitle")
        description = QLabel("The selected robot's own settings and memory will be loaded.")
        description.setObjectName("supportText")
        description.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(description)

        self.profile_list = QListWidget()
        self.profile_list.setObjectName("profileList")
        self.profile_list.setSpacing(6)
        self.profile_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.profile_list.currentItemChanged.connect(self._profile_selected)
        layout.addWidget(self.profile_list, 1)

        self.profile_summary = QLabel("Select a robot to view its connection details.")
        self.profile_summary.setObjectName("profileSummary")
        self.profile_summary.setWordWrap(True)
        self.profile_summary.setMinimumHeight(68)
        layout.addWidget(self.profile_summary)

        self.launch_button = QPushButton("Switch to selected robot" if self.integrated else "Launch selected robot")
        self.launch_button.setObjectName("primaryButton")
        self.launch_button.setMinimumHeight(48)
        self.launch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_button.clicked.connect(self.launch_selected)
        layout.addWidget(self.launch_button)
        return panel

    def _build_create_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("profileCreateScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = GlassPanel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(13)

        eyebrow = QLabel("NEW ROBOT")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Create an independent brain profile")
        title.setObjectName("panelTitle")
        description = QLabel(
            "Copy the platform settings from an existing robot, then give the new robot its own identity, "
            "personality, API port and cloned voice. The shared GPU voice host is reused. The source profile is never overwritten."
        )
        description.setObjectName("supportText")
        description.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(description)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(9)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("For example: Nova")
        self.name_edit.textEdited.connect(self._suggest_profile_id)
        self.slug_edit = QLineEdit()
        self.slug_edit.setPlaceholderText("nova")
        self.slug_edit.textEdited.connect(self._mark_slug_as_edited)
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("A curious workshop assistant")
        self.persona_preset_combo = QComboBox()
        self.persona_preset_combo.addItem("Standard robot personality", "standard")
        self.persona_preset_combo.addItem("Curious Female Companion", "female_companion")
        self.persona_preset_combo.currentIndexChanged.connect(self._persona_preset_changed)
        self.source_combo = QComboBox()

        self.api_port_spin = QSpinBox()
        self.api_port_spin.setRange(1024, 65535)
        self.api_port_spin.setValue(8766)
        self.api_port_spin.setToolTip("Local port used by the Robot Brain API.")
        self._add_field(form, 0, 0, "Robot name", self.name_edit)
        self._add_field(form, 0, 1, "Profile ID", self.slug_edit)
        self._add_field(form, 2, 0, "Persona preset", self.persona_preset_combo, column_span=2)
        self._add_field(form, 4, 0, "Character description", self.description_edit, column_span=2)
        self._add_field(form, 6, 0, "Copy platform settings from", self.source_combo, column_span=2)
        self._add_field(form, 8, 0, "Brain API port", self.api_port_spin, column_span=2)
        layout.addLayout(form)

        shared_voice = QLabel("One shared Dot.TTS GPU service • port 8092 • independent reference voice per robot")
        shared_voice.setObjectName("hintText")
        shared_voice.setWordWrap(True)
        layout.addWidget(shared_voice)

        personality_label = QLabel("Personality prompt")
        personality_label.setObjectName("fieldLabel")
        layout.addWidget(personality_label)
        self.personality_edit = QTextEdit()
        self.personality_edit.setAcceptRichText(False)
        self.personality_edit.setPlainText(DEFAULT_PERSONALITY)
        self.personality_edit.setMinimumHeight(112)
        self.personality_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.personality_edit, 1)

        hint = QLabel(
            "You can use {robot_name} and {robot_profile}. New profiles start with an empty Dot.TTS "
            "reference so another robot never inherits BX1's voice."
        )
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.create_button = QPushButton("Create robot profile")
        self.create_button.setObjectName("secondaryButton")
        self.create_button.setMinimumHeight(46)
        self.create_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_button.clicked.connect(self.create_profile)
        layout.addWidget(self.create_button)
        scroll.setWidget(panel)
        return scroll

    @staticmethod
    def _add_field(
        form: QGridLayout,
        row: int,
        column: int,
        label_text: str,
        widget: QWidget,
        *,
        column_span: int = 1,
    ) -> None:
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        form.addWidget(label, row, column, 1, column_span)
        form.addWidget(widget, row + 1, column, 1, column_span)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: transparent; }
            QWidget {
                color: #eaf5ff;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QWidget#auroraRoot { background: transparent; }
            QScrollArea#profileCreateScroll { background: transparent; border: none; }
            QScrollArea#profileCreateScroll > QWidget > QWidget { background: transparent; }
            QLabel#logo {
                color: #03111f;
                font-size: 14pt;
                font-weight: 800;
                border-radius: 18px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #49bdff, stop:1 #2bd8b2);
            }
            QLabel#pageTitle { font-size: 25pt; font-weight: 750; color: #f5fbff; }
            QLabel#pageSubtitle { color: #9db3c8; font-size: 10.5pt; }
            QLabel#statusBadge {
                color: #79f0cd;
                font-size: 8.5pt;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 9px 14px;
                border-radius: 15px;
                border: 1px solid rgba(57, 217, 175, 105);
                background: rgba(18, 79, 69, 120);
            }
            QFrame#glassPanel {
                background: rgba(10, 23, 38, 218);
                border: 1px solid rgba(116, 175, 219, 72);
                border-radius: 18px;
            }
            QLabel#eyebrow {
                color: #54c9ff;
                font-size: 8.5pt;
                font-weight: 750;
                letter-spacing: 1.5px;
            }
            QLabel#panelTitle { color: #f4faff; font-size: 16pt; font-weight: 700; }
            QLabel#supportText, QLabel#footerNote { color: #91a9bf; }
            QLabel#fieldLabel { color: #c8d9e8; font-size: 9pt; font-weight: 650; }
            QLabel#hintText {
                color: #9bc3d9;
                padding: 9px 11px;
                background: rgba(31, 82, 111, 78);
                border: 1px solid rgba(78, 164, 208, 64);
                border-radius: 9px;
            }
            QLabel#profileSummary {
                color: #b9d7e9;
                padding: 11px 12px;
                background: rgba(4, 13, 23, 148);
                border: 1px solid rgba(105, 165, 207, 48);
                border-radius: 10px;
            }
            QLabel#footerStatus { color: #6ee7c4; font-weight: 650; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox {
                color: #eff8ff;
                selection-background-color: #237fba;
                background: rgba(3, 12, 23, 185);
                border: 1px solid rgba(106, 164, 207, 82);
                border-radius: 9px;
                padding: 9px 11px;
                min-height: 21px;
            }
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #4fc3ff;
                background: rgba(4, 18, 32, 220);
            }
            QSpinBox { padding-right: 5px; }
            QComboBox::drop-down { width: 28px; border: none; }
            QComboBox QAbstractItemView {
                color: #eaf5ff;
                background: #102237;
                border: 1px solid #31516c;
                selection-background-color: #1d638f;
                padding: 5px;
            }
            QListWidget#profileList {
                outline: none;
                background: transparent;
                border: none;
            }
            QListWidget#profileList::item {
                color: #cfe3f1;
                background: rgba(6, 18, 31, 148);
                border: 1px solid rgba(105, 165, 207, 44);
                border-radius: 11px;
                padding: 12px 13px;
            }
            QListWidget#profileList::item:hover {
                background: rgba(21, 65, 94, 170);
                border-color: rgba(82, 187, 239, 105);
            }
            QListWidget#profileList::item:selected {
                color: #ffffff;
                background: rgba(24, 111, 158, 190);
                border: 1px solid #58c8ff;
            }
            QPushButton {
                color: #eaf7ff;
                font-weight: 700;
                border-radius: 10px;
                padding: 10px 16px;
            }
            QPushButton#primaryButton {
                border: 1px solid rgba(67, 236, 180, 150);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #15744f, stop:1 #179b72);
            }
            QPushButton#primaryButton:hover { background: #1aaa7c; border-color: #79f0cd; }
            QPushButton#primaryButton:pressed { background: #126547; }
            QPushButton#secondaryButton {
                border: 1px solid rgba(86, 194, 249, 140);
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #155f92, stop:1 #258fc5);
            }
            QPushButton#secondaryButton:hover { background: #2a9dd5; border-color: #70d1ff; }
            QPushButton#secondaryButton:pressed { background: #14577f; }
            QScrollBar:vertical {
                width: 9px; margin: 2px; background: transparent;
            }
            QScrollBar::handle:vertical {
                min-height: 28px; border-radius: 4px; background: rgba(104, 169, 207, 115);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )

    def refresh_profiles(self, select_slug: str | None = None) -> None:
        self.profiles = self.store.discover()
        selected_slug = safe_slug(select_slug or self.store.selected_slug())

        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected_row = 0
        for row, profile in enumerate(self.profiles):
            item = QListWidgetItem(
                f"{profile.name}   [{profile.slug}]\n"
                f"{profile.description}\n"
                f"Brain API {profile.api_port}   •   Shared Dot.TTS 8092"
            )
            item.setData(Qt.ItemDataRole.UserRole, profile.slug)
            item.setSizeHint(QSize(0, 88))
            self.profile_list.addItem(item)
            if profile.slug == selected_slug:
                selected_row = row
        self.profile_list.blockSignals(False)

        self.source_combo.blockSignals(True)
        previous_source = self.source_combo.currentData()
        self.source_combo.clear()
        for profile in self.profiles:
            self.source_combo.addItem(f"{profile.name}  [{profile.slug}]", profile.slug)
        source_row = self.source_combo.findData(previous_source or selected_slug)
        self.source_combo.setCurrentIndex(max(0, source_row))
        self.source_combo.blockSignals(False)

        if self.profiles:
            self.profile_list.setCurrentRow(selected_row)
            self.launch_button.setEnabled(True)
        else:
            self.profile_summary.setText("No robot profiles were found.")
            self.launch_button.setEnabled(False)
        self._suggest_unused_ports()

    def _current_profile(self) -> RobotProfile | None:
        item = self.profile_list.currentItem()
        if item is None:
            return None
        slug = str(item.data(Qt.ItemDataRole.UserRole) or "")
        return next((profile for profile in self.profiles if profile.slug == slug), None)

    def _profile_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        slug = str(current.data(Qt.ItemDataRole.UserRole) or "")
        profile = next((item for item in self.profiles if item.slug == slug), None)
        if profile is None:
            return
        try:
            self.profile_summary.setText(
                f"Selected: {profile.name}\n"
                f"Profile: {profile.slug}   •   Brain API: {profile.api_port}   •   Shared Dot.TTS: 8092"
            )
            self.status_label.setText(f"{profile.name} is ready to use.")
        except Exception as exc:
            self.status_label.setText(f"Could not select profile: {exc}")

    def _suggest_profile_id(self, name: str) -> None:
        if not self._slug_was_edited:
            self.slug_edit.setText(safe_slug(name))

    def _mark_slug_as_edited(self, _value: str) -> None:
        self._slug_was_edited = True

    def _persona_preset_changed(self, _index: int = 0) -> None:
        preset = str(self.persona_preset_combo.currentData() or "standard")
        if preset == "female_companion":
            self.name_edit.clear()
            self.name_edit.setPlaceholderText("Unnamed — she will propose a name on first launch")
            if not self._slug_was_edited:
                self.slug_edit.setText("companion")
            self.description_edit.setText(FEMALE_COMPANION_PROFILE)
            self.personality_edit.setPlainText(FEMALE_COMPANION_PROMPT)
            self.status_label.setText("This profile will ask her to choose a name on first launch; you approve it before it is saved.")
        else:
            self.name_edit.setPlaceholderText("For example: Nova")
            self.description_edit.clear()
            self.personality_edit.setPlainText(DEFAULT_PERSONALITY)
            self.status_label.setText("Ready.")

    def _suggest_unused_ports(self) -> None:
        used_api = {profile.api_port for profile in self.profiles}
        api_port = next((port for port in range(8765, 8865) if port not in used_api), 8766)
        self.api_port_spin.setValue(api_port)

    def create_profile(self) -> None:
        preset = str(self.persona_preset_combo.currentData() or "standard")
        try:
            profile = self.store.create(
                slug=self.slug_edit.text(),
                name=self.name_edit.text(),
                description=self.description_edit.text(),
                personality=self.personality_edit.toPlainText().strip(),
                source=str(self.source_combo.currentData() or "bx1"),
                api_port=self.api_port_spin.value(),
                tts_port=8092,
                preset=preset,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not create profile", str(exc))
            self.status_label.setText("Profile was not created. Check the highlighted details and try again.")
            return

        self.refresh_profiles(profile.slug)
        self.name_edit.clear()
        self._slug_was_edited = False
        self.slug_edit.clear()
        self.description_edit.clear()
        self.persona_preset_combo.setCurrentIndex(0)
        self.personality_edit.setPlainText(DEFAULT_PERSONALITY)
        self.status_label.setText(f"Created {profile.name}. It now has independent settings and runtime data.")
        QMessageBox.information(
            self,
            "Robot profile created",
            f"Created {profile.name} [{profile.slug}].\n\n"
            "Its identity, personality, ports, memory and voice reference are independent. "
            "The source robot was not changed."
            + ("\n\nOn first launch she will propose one name; it is saved only if you approve it." if preset == "female_companion" else ""),
        )

    def launch_selected(self) -> None:
        profile = self._current_profile()
        if profile is None:
            QMessageBox.warning(self, "Select a robot", "Choose a robot profile before launching.")
            return
        try:
            if self.integrated:
                self.profile_switch_requested.emit(profile.slug)
                return
            self.store.select(profile.slug)
            subprocess.Popen(
                [
                    "cmd.exe",
                    "/c",
                    str(ROOT / "START_BX1_BRAIN.bat"),
                    "--profile",
                    profile.slug,
                    "--robot-name",
                    profile.name,
                    "--api-port",
                    str(profile.api_port),
                ],
                cwd=str(ROOT),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not launch Robot Brain", str(exc))
            return
        QApplication.quit()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt method name
        super().showEvent(event)
        if self._backdrop_attempted:
            return
        self._backdrop_attempted = True
        QTimer.singleShot(0, self._enable_windows_mica)
        self.setWindowOpacity(0.0)
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_animation.setDuration(260)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.start()

    def _enable_windows_mica(self) -> None:
        """Use the documented Windows 11 backdrop API; retain the painted fallback elsewhere."""
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.c_void_p(int(self.winId()))
            dwm = ctypes.windll.dwmapi

            dark_mode = ctypes.c_int(1)
            # Attribute 20 is current; 19 supports earlier Windows 10 builds.
            if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)) != 0:
                dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))

            DWMWA_SYSTEMBACKDROP_TYPE = 38
            DWMSBT_MAINWINDOW = 2
            backdrop = ctypes.c_int(DWMSBT_MAINWINDOW)
            dwm.DwmSetWindowAttribute(
                hwnd,
                DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(backdrop),
                ctypes.sizeof(backdrop),
            )

            class Margins(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_int),
                    ("right", ctypes.c_int),
                    ("top", ctypes.c_int),
                    ("bottom", ctypes.c_int),
                ]

            margins = Margins(-1, -1, -1, -1)
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            # Styling and the painted aurora remain fully functional without DWM support.
            pass


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Robot Brain Profile Manager")
    app.setOrganizationName("Robot Brain")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = ProfileManager()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
