from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robot_brain.personality_store import PACKAGE_EXTENSION, PersonalityStore


CONTROL_LABELS = {
    "humour": "Humour",
    "honesty": "Honesty / directness",
    "sarcasm": "Sarcasm",
    "flirtiness": "Light flirtiness",
    "timidity": "Timidity / caution",
    "curiosity": "Curiosity",
    "chattiness": "Chattiness",
    "technical": "Technical depth",
    "obedience": "Obedience vs independence",
    "confidence": "Confidence",
    "energy": "Energy",
    "empathy": "Empathy",
    "caution": "Safety caution",
}


class PersonalityStudio(QMainWindow):
    """Separate editor for complete Robot Brain personality projects."""

    def __init__(
        self,
        *,
        store: PersonalityStore,
        config_provider: Callable[[], Dict[str, Any]],
        theme_names: Mapping[str, str],
        on_activate: Callable[[str], None],
        on_saved: Callable[[str], None],
        on_open_voice_lab: Callable[[str], None],
        on_test_voice: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.config_provider = config_provider
        self.theme_names = dict(theme_names)
        self.on_activate = on_activate
        self.on_saved = on_saved
        self.on_open_voice_lab = on_open_voice_lab
        self.on_test_voice = on_test_voice
        self.current_slug = ""
        self._loading = False
        self._voice_profiles: Dict[str, Dict[str, Any]] = {}
        self.control_sliders: Dict[str, QSlider] = {}
        self.control_value_labels: Dict[str, QLabel] = {}

        self.setWindowTitle("Personality Studio")
        self.resize(1180, 800)
        self.setMinimumSize(920, 650)
        self._build_ui()
        self.refresh_library(self.store.selected_slug())

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Personality Studio")
        title.setStyleSheet("font-size: 20pt; font-weight: 700;")
        subtitle = QLabel(
            "Create, edit, import and export complete characters. The physical robot hardware profile is not changed."
        )
        subtitle.setWordWrap(True)
        title_row.addWidget(title)
        title_row.addWidget(subtitle, 1)
        root_layout.addLayout(title_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_library_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 850])
        root_layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.load_button = QPushButton("Load into Brain")
        self.load_button.setObjectName("PrimaryButton")
        self.save_button = QPushButton("Save Changes")
        self.save_as_button = QPushButton("Save As New")
        self.close_button = QPushButton("Close")
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.load_button)
        bottom.addWidget(self.save_button)
        bottom.addWidget(self.save_as_button)
        bottom.addWidget(self.close_button)
        root_layout.addLayout(bottom)

        self.load_button.clicked.connect(self.load_current_into_brain)
        self.save_button.clicked.connect(self.save_current)
        self.save_as_button.clicked.connect(self.save_as_new)
        self.close_button.clicked.connect(self.close)
        self.setCentralWidget(root)

    def _build_library_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(QLabel("Saved personality projects"))
        self.personality_list = QListWidget()
        self.personality_list.currentItemChanged.connect(self._list_selection_changed)
        layout.addWidget(self.personality_list, 1)

        grid = QGridLayout()
        self.new_button = QPushButton("New")
        self.duplicate_button = QPushButton("Duplicate")
        self.delete_button = QPushButton("Delete")
        self.import_button = QPushButton("Import File")
        self.export_button = QPushButton("Export File")
        self.open_folder_button = QPushButton("Open Project Folder")
        grid.addWidget(self.new_button, 0, 0)
        grid.addWidget(self.duplicate_button, 0, 1)
        grid.addWidget(self.delete_button, 1, 0)
        grid.addWidget(self.import_button, 1, 1)
        grid.addWidget(self.export_button, 2, 0)
        grid.addWidget(self.open_folder_button, 2, 1)
        layout.addLayout(grid)

        self.new_button.clicked.connect(self.new_personality)
        self.duplicate_button.clicked.connect(self.duplicate_personality)
        self.delete_button.clicked.connect(self.delete_personality)
        self.import_button.clicked.connect(self.import_personality)
        self.export_button.clicked.connect(self.export_personality)
        self.open_folder_button.clicked.connect(self.open_project_folder)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_identity_tab(), "Identity & Appearance")
        self.tabs.addTab(self._build_character_tab(), "Character")
        self.tabs.addTab(self._build_voice_tab(), "Voice")
        layout.addWidget(self.tabs)
        return panel

    def _build_identity_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        project_box = QGroupBox("Personality project")
        project_form = QFormLayout(project_box)
        self.project_name_edit = QLineEdit()
        self.project_description_edit = QPlainTextEdit()
        self.project_description_edit.setMaximumHeight(90)
        project_form.addRow("Project name", self.project_name_edit)
        project_form.addRow("Description", self.project_description_edit)
        layout.addWidget(project_box)

        identity_box = QGroupBox("Robot identity")
        identity_form = QFormLayout(identity_box)
        self.robot_name_edit = QLineEdit()
        self.robot_profile_edit = QLineEdit()
        self.robot_subtitle_edit = QLineEdit()
        self.identity_mode_combo = QComboBox()
        self.identity_mode_combo.addItem("Robot-aware character", "robot")
        self.identity_mode_combo.addItem("Human-like character", "humanlike")
        self.gender_combo = QComboBox()
        for value in ("unspecified", "female", "male", "non-binary"):
            self.gender_combo.addItem(value.replace("-", " ").title(), value)
        self.theme_combo = QComboBox()
        for key, label in self.theme_names.items():
            self.theme_combo.addItem(label, key)
        identity_form.addRow("Robot name", self.robot_name_edit)
        identity_form.addRow("Robot profile / role", self.robot_profile_edit)
        identity_form.addRow("GUI subtitle", self.robot_subtitle_edit)
        identity_form.addRow("Identity style", self.identity_mode_combo)
        identity_form.addRow("Character gender", self.gender_combo)
        identity_form.addRow("GUI theme", self.theme_combo)
        layout.addWidget(identity_box)

        note = QLabel(
            "The robot name and theme are loaded together. The name drives the window title, headers, conversation labels, "
            "API identity, wake phrases and voice speaker metadata."
        )
        note.setWordWrap(True)
        note.setObjectName("HintLabel")
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_character_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls_box = QGroupBox("Personality controls")
        controls_grid = QGridLayout(controls_box)
        for row, (key, label) in enumerate(CONTROL_LABELS.items()):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setTickInterval(10)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            value_label = QLabel("50 / 100")
            value_label.setMinimumWidth(70)
            slider.valueChanged.connect(lambda value, output=value_label: output.setText(f"{value} / 100"))
            self.control_sliders[key] = slider
            self.control_value_labels[key] = value_label
            controls_grid.addWidget(QLabel(label), row, 0)
            controls_grid.addWidget(slider, row, 1)
            controls_grid.addWidget(value_label, row, 2)
        controls_grid.setColumnStretch(1, 1)
        layout.addWidget(controls_box)

        prompt_box = QGroupBox("LLM personality prompt")
        prompt_layout = QVBoxLayout(prompt_box)
        self.personality_lock_check = QCheckBox("Force this character on every reply")
        self.personality_repair_check = QCheckBox("Repair generic assistant wording")
        strength_row = QHBoxLayout()
        self.personality_strength_spin = QSpinBox()
        self.personality_strength_spin.setRange(0, 100)
        strength_row.addWidget(QLabel("Style strength"))
        strength_row.addWidget(self.personality_strength_spin)
        strength_row.addStretch(1)
        self.personality_prompt_edit = QPlainTextEdit()
        self.personality_prompt_edit.setMinimumHeight(240)
        prompt_layout.addWidget(self.personality_lock_check)
        prompt_layout.addWidget(self.personality_repair_check)
        prompt_layout.addLayout(strength_row)
        prompt_layout.addWidget(self.personality_prompt_edit)
        layout.addWidget(prompt_box, 1)
        return page

    def _build_voice_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        voice_box = QGroupBox("Personality voice")
        form = QFormLayout(voice_box)
        self.voice_profile_combo = QComboBox()
        self.voice_profile_combo.setEditable(True)
        self.voice_engine_combo = QComboBox()
        self.voice_engine_combo.addItem("Dot.TTS voice clone", "dottts")
        self.voice_engine_combo.addItem("Microsoft Edge voice", "edge")
        self.dottts_model_combo = QComboBox()
        self.dottts_model_combo.addItem("MF - fast", "mf")
        self.dottts_model_combo.addItem("SOAR - higher quality", "soar")
        self.edge_voice_edit = QLineEdit()
        self.voice_style_edit = QPlainTextEdit()
        self.voice_style_edit.setMaximumHeight(100)
        self.voice_rate_spin = QSpinBox()
        self.voice_rate_spin.setRange(80, 300)
        self.voice_volume_spin = QDoubleSpinBox()
        self.voice_volume_spin.setRange(0.0, 1.0)
        self.voice_volume_spin.setDecimals(2)
        self.voice_volume_spin.setSingleStep(0.05)
        self.emotional_delivery_check = QCheckBox("Use emotional delivery routing")
        self.inline_delivery_check = QCheckBox("Use natural-language performance directions")
        self.voice_sample_edit = QPlainTextEdit()
        self.voice_sample_edit.setMaximumHeight(85)

        form.addRow("Voice profile", self.voice_profile_combo)
        form.addRow("Engine", self.voice_engine_combo)
        form.addRow("Dot.TTS model", self.dottts_model_combo)
        form.addRow("Edge fallback voice", self.edge_voice_edit)
        form.addRow("Voice direction", self.voice_style_edit)
        form.addRow("Speech rate", self.voice_rate_spin)
        form.addRow("Volume", self.voice_volume_spin)
        form.addRow("Emotional delivery", self.emotional_delivery_check)
        form.addRow("Experimental direction", self.inline_delivery_check)
        form.addRow("Test phrase", self.voice_sample_edit)
        layout.addWidget(voice_box)

        self.voice_binding_label = QLabel()
        self.voice_binding_label.setWordWrap(True)
        self.voice_binding_label.setObjectName("HintLabel")
        layout.addWidget(self.voice_binding_label)

        actions = QHBoxLayout()
        self.train_voice_button = QPushButton("Open / Train Voice")
        self.test_voice_button = QPushButton("Save and Test Voice")
        self.refresh_voice_button = QPushButton("Refresh Voice Profiles")
        actions.addWidget(self.train_voice_button)
        actions.addWidget(self.test_voice_button)
        actions.addWidget(self.refresh_voice_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        note = QLabel(
            "The Voice Lab is opened in a personality-specific namespace. A reference recording and exact transcript saved there "
            "will return automatically whenever this personality is loaded. Export File packages available reference assets with the character."
        )
        note.setWordWrap(True)
        note.setObjectName("HintLabel")
        layout.addWidget(note)
        layout.addStretch(1)

        self.voice_profile_combo.currentTextChanged.connect(self._voice_profile_changed)
        self.train_voice_button.clicked.connect(self.open_voice_lab)
        self.test_voice_button.clicked.connect(self.test_voice)
        self.refresh_voice_button.clicked.connect(self.refresh_voice_profiles)
        return page

    def _select_combo_data(self, combo: QComboBox, value: Any) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(str(value or ""))
        combo.setCurrentIndex(max(0, index))

    def refresh_library(self, preferred_slug: str = "") -> None:
        selected = preferred_slug or self.current_slug or self.store.selected_slug()
        self.personality_list.blockSignals(True)
        self.personality_list.clear()
        selected_item: Optional[QListWidgetItem] = None
        for profile in self.store.list():
            robot_name = str(profile.settings.get("robot_name") or "").strip()
            label = profile.name if not robot_name else f"{profile.name}\n{robot_name}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, profile.slug)
            self.personality_list.addItem(item)
            if profile.slug == selected:
                selected_item = item
        self.personality_list.blockSignals(False)
        if selected_item is not None:
            self.personality_list.setCurrentItem(selected_item)
            self.load_profile(selected)
        elif self.personality_list.count():
            self.personality_list.setCurrentRow(0)

    def _list_selection_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if current is None or self._loading:
            return
        slug = str(current.data(Qt.ItemDataRole.UserRole) or "")
        if slug:
            self.load_profile(slug)

    def load_profile(self, slug: str) -> None:
        profile = self.store.get(slug)
        base = self.config_provider()
        cfg = self.store.preview(slug, base)
        self.current_slug = slug
        self._loading = True
        try:
            self.project_name_edit.setText(profile.name)
            self.project_description_edit.setPlainText(profile.description)
            self.robot_name_edit.setText(str(cfg.get("robot_name") or ""))
            self.robot_profile_edit.setText(str(cfg.get("robot_profile") or ""))
            self.robot_subtitle_edit.setText(str(cfg.get("robot_subtitle") or ""))
            self._select_combo_data(self.identity_mode_combo, str(cfg.get("persona_identity_mode") or "robot"))
            self._select_combo_data(self.gender_combo, str(cfg.get("persona_gender") or "unspecified"))
            self._select_combo_data(self.theme_combo, str(cfg.get("ui_style_preset") or "glass_blue"))

            controls = cfg.get("personality_controls") if isinstance(cfg.get("personality_controls"), dict) else {}
            for key, slider in self.control_sliders.items():
                slider.setValue(max(0, min(100, int(controls.get(key, 50) or 0))))
            self.personality_lock_check.setChecked(bool(cfg.get("personality_lock_enabled", True)))
            self.personality_repair_check.setChecked(bool(cfg.get("personality_repair_enabled", True)))
            self.personality_strength_spin.setValue(int(cfg.get("personality_style_strength", 86) or 86))
            self.personality_prompt_edit.setPlainText(str(cfg.get("personality_prompt") or ""))

            self._rebuild_voice_profiles(cfg, profile.voice_profile_name, profile.voice_profile)
            self._select_combo_data(self.voice_engine_combo, str(cfg.get("voice_engine") or "dottts"))
            self._select_combo_data(self.dottts_model_combo, str(cfg.get("dottts_model") or "mf"))
            self.edge_voice_edit.setText(str(cfg.get("edge_voice") or "en-GB-RyanNeural"))
            self.voice_style_edit.setPlainText(str(cfg.get("voice_style") or ""))
            self.voice_rate_spin.setValue(int(cfg.get("voice_rate", 165) or 165))
            self.voice_volume_spin.setValue(float(cfg.get("voice_volume", 0.9) or 0.9))
            self.emotional_delivery_check.setChecked(bool(cfg.get("dottts_emotional_delivery_enabled", True)))
            self.inline_delivery_check.setChecked(bool(cfg.get("dottts_inline_delivery_instructions", False)))
            self.voice_sample_edit.setPlainText(str(cfg.get("voice_lab_sample_text") or ""))
            self.voice_binding_label.setText(
                f"Voice namespace: {self.store.voice_namespace(slug)}\n"
                f"Project file extension: {PACKAGE_EXTENSION}"
            )
            self.status_label.setText(f"Editing: {profile.name}")
        finally:
            self._loading = False

    def _rebuild_voice_profiles(
        self,
        cfg: Mapping[str, Any],
        preferred_name: str = "",
        embedded_profile: Optional[Mapping[str, Any]] = None,
    ) -> None:
        profiles = cfg.get("voice_lab_profiles") if isinstance(cfg.get("voice_lab_profiles"), dict) else {}
        self._voice_profiles = {str(name): copy.deepcopy(item) for name, item in profiles.items() if isinstance(item, dict)}
        selected = preferred_name or str(cfg.get("selected_voice_profile") or "")
        if selected and isinstance(embedded_profile, Mapping):
            self._voice_profiles[selected] = copy.deepcopy(dict(embedded_profile))
        self.voice_profile_combo.blockSignals(True)
        self.voice_profile_combo.clear()
        for name in sorted(self._voice_profiles):
            self.voice_profile_combo.addItem(name, name)
        if selected and self.voice_profile_combo.findText(selected) < 0:
            self.voice_profile_combo.addItem(selected, selected)
        self.voice_profile_combo.setCurrentText(selected)
        self.voice_profile_combo.blockSignals(False)
        self._voice_profile_changed(selected)

    def _voice_profile_changed(self, name: str) -> None:
        if self._loading:
            return
        profile = self._voice_profiles.get(str(name or "").strip(), {})
        if profile.get("style") and not self.voice_style_edit.toPlainText().strip():
            self.voice_style_edit.setPlainText(str(profile.get("style") or ""))

    def collect_config(self) -> Dict[str, Any]:
        base = self.config_provider()
        if self.current_slug:
            try:
                base = self.store.preview(self.current_slug, base)
            except Exception:
                pass
        cfg = copy.deepcopy(base)
        cfg.update(
            {
                "robot_name": self.robot_name_edit.text().strip() or "Unnamed",
                "robot_profile": self.robot_profile_edit.text().strip() or "robot companion",
                "robot_subtitle": self.robot_subtitle_edit.text().strip(),
                "persona_identity_mode": str(self.identity_mode_combo.currentData() or "robot"),
                "persona_gender": str(self.gender_combo.currentData() or "unspecified"),
                "ui_style_preset": str(self.theme_combo.currentData() or "glass_blue"),
                "personality_controls": {key: int(slider.value()) for key, slider in self.control_sliders.items()},
                "personality_lock_enabled": self.personality_lock_check.isChecked(),
                "personality_repair_enabled": self.personality_repair_check.isChecked(),
                "personality_style_strength": int(self.personality_strength_spin.value()),
                "personality_prompt": self.personality_prompt_edit.toPlainText().strip(),
                "voice_engine": str(self.voice_engine_combo.currentData() or "dottts"),
                "dottts_model": str(self.dottts_model_combo.currentData() or "mf"),
                "edge_voice": self.edge_voice_edit.text().strip() or "en-GB-RyanNeural",
                "voice_style": self.voice_style_edit.toPlainText().strip(),
                "voice_rate": int(self.voice_rate_spin.value()),
                "voice_volume": float(self.voice_volume_spin.value()),
                "dottts_emotional_delivery_enabled": self.emotional_delivery_check.isChecked(),
                "dottts_inline_delivery_instructions": self.inline_delivery_check.isChecked(),
                "voice_lab_sample_text": self.voice_sample_edit.toPlainText().strip(),
            }
        )
        voice_name = self.voice_profile_combo.currentText().strip() or f"{cfg['robot_name']} Main Voice"
        voice_profiles = cfg.get("voice_lab_profiles") if isinstance(cfg.get("voice_lab_profiles"), dict) else {}
        voice_profiles = copy.deepcopy(voice_profiles)
        voice_profile = copy.deepcopy(self._voice_profiles.get(voice_name, {}))
        voice_profile.setdefault("description", f"Voice profile for {cfg['robot_name']}.")
        voice_profile.setdefault("mode", str(cfg["voice_engine"]))
        voice_profile["model_choice"] = str(cfg["dottts_model"])
        voice_profile["speaker"] = str(cfg["robot_name"])
        voice_profile["style"] = str(cfg["voice_style"])
        voice_profiles[voice_name] = voice_profile
        cfg["voice_lab_profiles"] = voice_profiles
        cfg["selected_voice_profile"] = voice_name
        return cfg

    def save_current(self, *, notify: bool = True) -> bool:
        if not self.current_slug:
            return False
        try:
            cfg = self.collect_config()
            profile = self.store.update(
                self.current_slug,
                cfg,
                name=self.project_name_edit.text().strip(),
                description=self.project_description_edit.toPlainText().strip(),
                select=False,
            )
            self.on_saved(profile.slug)
            self.refresh_library(profile.slug)
            self.status_label.setText(f"Saved: {profile.name}")
            if notify:
                QMessageBox.information(self, "Personality Studio", f"Saved personality project: {profile.name}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save personality", f"The personality could not be saved.\n\n{exc}")
            return False

    def save_as_new(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "Save personality as new",
            "New personality project name",
            text=(self.project_name_edit.text().strip() + " Copy").strip(),
        )
        if not accepted:
            return
        try:
            cfg = self.collect_config()
            profile = self.store.create(name, cfg, self.project_description_edit.toPlainText().strip(), select=False)
            self.on_saved(profile.slug)
            self.refresh_library(profile.slug)
            self.status_label.setText(f"Created: {profile.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Create personality", str(exc))

    def load_current_into_brain(self) -> None:
        if not self.current_slug:
            return
        if not self.save_current(notify=False):
            return
        self.on_activate(self.current_slug)
        self.status_label.setText(f"Loaded into Brain: {self.project_name_edit.text().strip()}")

    def new_personality(self) -> None:
        name, accepted = QInputDialog.getText(self, "New personality", "Personality project name")
        if not accepted:
            return
        try:
            cfg = self.config_provider()
            cfg = copy.deepcopy(cfg)
            cfg["robot_name"] = str(name or "Unnamed").strip() or "Unnamed"
            profile = self.store.create(name, cfg, "New personality project", select=False)
            self.refresh_library(profile.slug)
        except Exception as exc:
            QMessageBox.critical(self, "New personality", str(exc))

    def duplicate_personality(self) -> None:
        if not self.current_slug:
            return
        source = self.store.get(self.current_slug)
        name, accepted = QInputDialog.getText(
            self, "Duplicate personality", "Name for the copy", text=f"{source.name} Copy"
        )
        if not accepted:
            return
        try:
            profile = self.store.duplicate(self.current_slug, name, select=False)
            self.refresh_library(profile.slug)
        except Exception as exc:
            QMessageBox.critical(self, "Duplicate personality", str(exc))

    def delete_personality(self) -> None:
        if not self.current_slug:
            return
        profile = self.store.get(self.current_slug)
        result = QMessageBox.question(
            self,
            "Delete personality",
            f"Delete '{profile.name}' from the personality library?\n\nVoice assets are retained in the runtime folder for recovery.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            replacement = self.store.delete(self.current_slug)
            self.refresh_library(replacement)
        except Exception as exc:
            QMessageBox.warning(self, "Delete personality", str(exc))

    def import_personality(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import personality project",
            str(Path.home()),
            f"BX Personality Project (*{PACKAGE_EXTENSION});;All files (*.*)",
        )
        if not path:
            return
        try:
            profile = self.store.import_profile(Path(path), activate=False)
            self.on_saved(profile.slug)
            self.refresh_library(profile.slug)
            QMessageBox.information(self, "Import complete", f"Imported personality project: {profile.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Import personality", f"The file could not be imported.\n\n{exc}")

    def export_personality(self) -> None:
        if not self.current_slug:
            return
        if not self.save_current(notify=False):
            return
        profile = self.store.get(self.current_slug)
        suggested = Path.home() / f"{profile.slug}{PACKAGE_EXTENSION}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export personality project",
            str(suggested),
            f"BX Personality Project (*{PACKAGE_EXTENSION})",
        )
        if not path:
            return
        try:
            output = self.store.export_profile(self.current_slug, Path(path), include_voice_assets=True)
            QMessageBox.information(self, "Export complete", f"Personality project saved to:\n{output}")
        except Exception as exc:
            QMessageBox.critical(self, "Export personality", f"The project could not be exported.\n\n{exc}")

    def open_project_folder(self) -> None:
        try:
            import os
            import subprocess
            import sys

            path = self.store.assets_dir
            path.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.warning(self, "Open folder", str(exc))

    def open_voice_lab(self) -> None:
        if not self.current_slug:
            return
        if not self.save_current(notify=False):
            return
        self.on_activate(self.current_slug)
        self.on_open_voice_lab(self.current_slug)

    def test_voice(self) -> None:
        if not self.current_slug:
            return
        if not self.save_current(notify=False):
            return
        self.on_activate(self.current_slug)
        self.on_test_voice(self.current_slug)

    def refresh_voice_profiles(self) -> None:
        if not self.current_slug:
            return
        profile = self.store.get(self.current_slug)
        cfg = self.config_provider()
        selected = self.voice_profile_combo.currentText().strip() or profile.voice_profile_name
        self._rebuild_voice_profiles(cfg, selected, profile.voice_profile)
        self.status_label.setText("Voice profiles refreshed from the Brain configuration")
