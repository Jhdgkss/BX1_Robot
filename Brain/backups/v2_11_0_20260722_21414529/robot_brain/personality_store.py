from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


# Only character-owned settings belong in a personality. Hardware, API ports,
# documents, memory, safety limits and robot-body wiring stay outside.
PERSONALITY_SETTING_KEYS = (
    # Identity and character.
    "robot_name",
    "robot_profile",
    "robot_subtitle",
    "persona_identity_mode",
    "persona_gender",
    "identity_name_pending",
    "identity_name_suggestion_made",
    "auto_name_suggestion_on_first_launch",
    "personality_controls",
    "personality_lock_enabled",
    "personality_repair_enabled",
    "personality_repair_aggressive",
    "personality_style_strength",
    "personality_prompt",
    # Appearance follows the loaded character.
    "ui_style_preset",
    # Voice selection and delivery follow the loaded character. The selected
    # Voice Lab profile itself is embedded separately in each saved record.
    "voice_style",
    "voice_engine",
    "selected_voice_profile",
    "edge_voice",
    "edge_rate_adjust_percent",
    "edge_pitch_hz",
    "voice_rate",
    "voice_volume",
    "dottts_model",
    "dottts_sampling_steps",
    "dottts_guidance_scale",
    "dottts_seed",
    "dottts_emotional_delivery_enabled",
    "dottts_inline_delivery_instructions",
    "dottts_default_delivery",
    "voice_lab_sample_text",
)

VOICE_PATH_FIELDS = (
    "reference_audio_path",
    "reference_transcript_path",
    "custom_model_path",
    "sample_filename",
)

PACKAGE_EXTENSION = ".bxpersonality"
PACKAGE_SCHEMA_VERSION = 2
STORE_SCHEMA_VERSION = 2


def personality_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_").lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_copy(value: Any) -> Any:
    """Return a JSON-safe deep copy so saved records never alias live config."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def snapshot_personality(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Capture only character settings; hardware, memory and connections stay outside."""
    result: Dict[str, Any] = {}
    for key in PERSONALITY_SETTING_KEYS:
        if key in cfg:
            result[key] = _json_copy(cfg[key])
    controls = result.get("personality_controls")
    if not isinstance(controls, dict):
        result["personality_controls"] = {}
    return result


def snapshot_selected_voice(cfg: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Capture the selected Voice Lab profile rather than the whole shared library."""
    name = str(cfg.get("selected_voice_profile") or "").strip()
    profiles = cfg.get("voice_lab_profiles")
    if not isinstance(profiles, Mapping):
        return name, {}
    item = profiles.get(name)
    if not isinstance(item, Mapping):
        return name, {}
    return name, _json_copy(dict(item))


def _host_path(raw: Any) -> Path:
    """Resolve native paths and translate common WSL /mnt/c paths on Windows."""
    value = str(raw or "").strip().strip('"').strip("'")
    if not value:
        return Path()
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    if expanded.exists():
        return expanded
    match = re.match(r"^/mnt/([A-Za-z])/(.*)$", value.replace("\\", "/"))
    if match and os.name == "nt":
        candidate = Path(f"{match.group(1).upper()}:/{match.group(2)}")
        if candidate.exists():
            return candidate
    return expanded


def _safe_archive_component(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "asset")).strip("._") or "asset"


@dataclass(frozen=True)
class PersonalityProfile:
    slug: str
    name: str
    description: str
    settings: Dict[str, Any]
    voice_profile_name: str
    voice_profile: Dict[str, Any]
    voice_active_reference: Dict[str, Any]
    created_at: str
    updated_at: str


class PersonalityStore:
    """Persistent personality project library owned by one physical robot profile.

    Each project contains identity, prompt, GUI theme, voice settings, the selected
    Voice Lab profile and a personality-specific Dot.TTS active reference.
    """

    def __init__(self, root: Path, robot_profile: str) -> None:
        self.root = Path(root).resolve()
        self.config_dir = self.root / "config"
        self.runtime_dir = self.root / "runtime"
        self.robot_profile = personality_slug(robot_profile) or "default"
        self.path = self.config_dir / f"personality_profiles_{self.robot_profile}.json"
        self.assets_dir = self.runtime_dir / self.robot_profile / "personality_assets"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def voice_namespace(self, slug: str) -> str:
        return personality_slug(f"{self.robot_profile}__personality__{personality_slug(slug) or 'default'}")

    def voice_runtime_dir(self, slug: str) -> Path:
        return self.runtime_dir / self.voice_namespace(slug) / "dottts"

    def active_reference_path(self, slug: str) -> Path:
        return self.voice_runtime_dir(slug) / "active_reference.json"

    def legacy_active_reference_path(self) -> Path:
        return self.runtime_dir / self.robot_profile / "dottts" / "active_reference.json"

    def _empty(self) -> Dict[str, Any]:
        return {"schema_version": STORE_SCHEMA_VERSION, "selected_personality": "", "personalities": {}}

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("personalities"), dict):
                data.setdefault("selected_personality", "")
                data["schema_version"] = max(int(data.get("schema_version") or 1), STORE_SCHEMA_VERSION)
                # Schema 1 records are valid; voice data is populated the next
                # time they are saved or applied.
                return data
        except Exception:
            pass
        return self._empty()

    def _write(self, data: Dict[str, Any]) -> None:
        data["schema_version"] = STORE_SCHEMA_VERSION
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _unique_slug(data: Dict[str, Any], preferred: str) -> str:
        profiles = data.get("personalities") if isinstance(data.get("personalities"), dict) else {}
        base = personality_slug(preferred) or "personality"
        slug = base
        suffix = 2
        while slug in profiles:
            slug = f"{base}_{suffix}"
            suffix += 1
        return slug

    @staticmethod
    def _voice_block(item: Mapping[str, Any]) -> Dict[str, Any]:
        voice = item.get("voice")
        return _json_copy(voice) if isinstance(voice, Mapping) else {}

    @classmethod
    def _record(cls, slug: str, item: Dict[str, Any]) -> PersonalityProfile:
        voice = cls._voice_block(item)
        return PersonalityProfile(
            slug=slug,
            name=str(item.get("name") or slug.replace("_", " ").title()),
            description=str(item.get("description") or ""),
            settings=_json_copy(item.get("settings") if isinstance(item.get("settings"), dict) else {}),
            voice_profile_name=str(voice.get("profile_name") or ""),
            voice_profile=_json_copy(voice.get("profile") if isinstance(voice.get("profile"), dict) else {}),
            voice_active_reference=_json_copy(
                voice.get("active_reference") if isinstance(voice.get("active_reference"), dict) else {}
            ),
            created_at=str(item.get("created_at") or ""),
            updated_at=str(item.get("updated_at") or ""),
        )

    def list(self) -> List[PersonalityProfile]:
        data = self._read()
        profiles = data.get("personalities") if isinstance(data.get("personalities"), dict) else {}
        return [self._record(slug, item) for slug, item in profiles.items() if isinstance(item, dict)]

    def selected_slug(self) -> str:
        data = self._read()
        profiles = data.get("personalities") if isinstance(data.get("personalities"), dict) else {}
        selected = personality_slug(str(data.get("selected_personality") or ""))
        if selected in profiles:
            return selected
        return next(iter(profiles), "")

    def get(self, slug: str) -> PersonalityProfile:
        slug = personality_slug(slug)
        data = self._read()
        profiles = data.get("personalities") if isinstance(data.get("personalities"), dict) else {}
        item = profiles.get(slug)
        if not isinstance(item, dict):
            raise KeyError(f"Unknown personality: {slug}")
        return self._record(slug, item)

    def _read_active_reference(self, slug: str, *, include_legacy: bool = False) -> Dict[str, Any]:
        candidates = [self.active_reference_path(slug)]
        if include_legacy:
            candidates.append(self.legacy_active_reference_path())
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    result = _json_copy(data)
                    result["source_config_path"] = str(path)
                    return result
            except Exception:
                continue
        return {}

    def _capture_voice(self, slug: str, cfg: Mapping[str, Any], existing: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        name, profile = snapshot_selected_voice(cfg)
        prior = dict(existing or {})
        if not name:
            name = str(prior.get("profile_name") or "")
        if not profile and isinstance(prior.get("profile"), Mapping):
            profile = _json_copy(prior["profile"])
        active = self._read_active_reference(slug, include_legacy=(slug == "current_personality"))
        if not active:
            source_namespace = personality_slug(str(cfg.get("personality_voice_namespace") or ""))
            if source_namespace and source_namespace != self.voice_namespace(slug):
                try:
                    source_path = self.runtime_dir / source_namespace / "dottts" / "active_reference.json"
                    source_data = json.loads(source_path.read_text(encoding="utf-8"))
                    if isinstance(source_data, dict):
                        active = _json_copy(source_data)
                        active["source_config_path"] = str(source_path)
                except Exception:
                    pass
        if not active and isinstance(prior.get("active_reference"), Mapping):
            active = _json_copy(prior["active_reference"])
        return {
            "profile_name": name,
            "profile": profile,
            "namespace": self.voice_namespace(slug),
            "active_reference": active,
        }

    def _ensure_runtime_active_reference(self, slug: str, active: Mapping[str, Any]) -> None:
        if not active:
            return
        target = self.active_reference_path(slug)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: _json_copy(v) for k, v in active.items() if k != "source_config_path"}
        if not payload:
            return
        try:
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _migrate_legacy_active_reference(self, slug: str) -> None:
        target = self.active_reference_path(slug)
        legacy = self.legacy_active_reference_path()
        if target.exists() or not legacy.exists():
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, target)
        except Exception:
            pass

    def bootstrap(self, current_cfg: Mapping[str, Any], female_cfg: Optional[Mapping[str, Any]] = None) -> None:
        """Migrate current settings and add the supplied companion once."""
        data = self._read()
        profiles = data.setdefault("personalities", {})
        if profiles:
            selected = self.selected_slug()
            if selected:
                self._migrate_legacy_active_reference(selected)
            return
        now = _now_iso()
        current_slug = "current_personality"
        profiles[current_slug] = {
            "name": "Current Personality",
            "description": "The personality that was active before the personality project library was added.",
            "settings": snapshot_personality(current_cfg),
            "voice": self._capture_voice(current_slug, current_cfg),
            "created_at": now,
            "updated_at": now,
        }
        if female_cfg:
            companion = dict(current_cfg)
            companion.update(dict(female_cfg))
            profiles["curious_female_companion"] = {
                "name": "Curious Female Companion",
                "description": "Warm, curious, funny, mildly sarcastic and lightly flirty in relaxed conversation.",
                "settings": snapshot_personality(companion),
                "voice": self._capture_voice("curious_female_companion", companion),
                "created_at": now,
                "updated_at": now,
            }
        data["selected_personality"] = current_slug
        self._write(data)
        self._migrate_legacy_active_reference(current_slug)

    def create(self, name: str, cfg: Mapping[str, Any], description: str = "", *, select: bool = True) -> PersonalityProfile:
        display_name = re.sub(r"\s+", " ", str(name or "").strip())
        if not display_name:
            raise ValueError("Enter a name for the personality.")
        data = self._read()
        profiles = data.setdefault("personalities", {})
        slug = self._unique_slug(data, display_name)
        now = _now_iso()
        profiles[slug] = {
            "name": display_name,
            "description": str(description or "").strip(),
            "settings": snapshot_personality(cfg),
            "voice": self._capture_voice(slug, cfg),
            "created_at": now,
            "updated_at": now,
        }
        if select:
            data["selected_personality"] = slug
        self._write(data)
        return self._record(slug, profiles[slug])

    def update(
        self,
        slug: str,
        cfg: Mapping[str, Any],
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        select: bool = True,
    ) -> PersonalityProfile:
        slug = personality_slug(slug)
        data = self._read()
        profiles = data.setdefault("personalities", {})
        item = profiles.get(slug)
        if not isinstance(item, dict):
            raise KeyError(f"Unknown personality: {slug}")
        if name is not None:
            display_name = re.sub(r"\s+", " ", str(name).strip())
            if not display_name:
                raise ValueError("Enter a name for the personality.")
            item["name"] = display_name
        if description is not None:
            item["description"] = str(description).strip()
        item["settings"] = snapshot_personality(cfg)
        item["voice"] = self._capture_voice(slug, cfg, self._voice_block(item))
        item["updated_at"] = _now_iso()
        if select:
            data["selected_personality"] = slug
        self._write(data)
        return self._record(slug, item)

    def duplicate(self, slug: str, new_name: str, *, select: bool = True) -> PersonalityProfile:
        source = self.get(slug)
        data = self._read()
        profiles = data.setdefault("personalities", {})
        display_name = re.sub(r"\s+", " ", str(new_name or "").strip())
        if not display_name:
            raise ValueError("Enter a name for the copy.")
        new_slug = self._unique_slug(data, display_name)
        now = _now_iso()
        profiles[new_slug] = {
            "name": display_name,
            "description": source.description,
            "settings": _json_copy(source.settings),
            "voice": {
                "profile_name": source.voice_profile_name,
                "profile": _json_copy(source.voice_profile),
                "namespace": self.voice_namespace(new_slug),
                "active_reference": _json_copy(source.voice_active_reference),
            },
            "created_at": now,
            "updated_at": now,
        }
        if select:
            data["selected_personality"] = new_slug
        self._write(data)
        self._ensure_runtime_active_reference(new_slug, source.voice_active_reference)
        return self._record(new_slug, profiles[new_slug])

    def rename(self, slug: str, new_name: str) -> PersonalityProfile:
        slug = personality_slug(slug)
        display_name = re.sub(r"\s+", " ", str(new_name or "").strip())
        if not display_name:
            raise ValueError("Enter a name for the personality.")
        data = self._read()
        profiles = data.setdefault("personalities", {})
        item = profiles.get(slug)
        if not isinstance(item, dict):
            raise KeyError(f"Unknown personality: {slug}")
        item["name"] = display_name
        item["updated_at"] = _now_iso()
        self._write(data)
        return self._record(slug, item)

    def select(self, slug: str) -> PersonalityProfile:
        profile = self.get(slug)
        data = self._read()
        data["selected_personality"] = profile.slug
        self._write(data)
        return profile

    def preview(self, slug: str, cfg: Mapping[str, Any]) -> Dict[str, Any]:
        """Materialise a personality without changing the selected record."""
        profile = self.get(slug)
        result = copy.deepcopy(dict(cfg))
        result.update(_json_copy(profile.settings))
        voice_name = profile.voice_profile_name or str(result.get("selected_voice_profile") or "")
        if voice_name and profile.voice_profile:
            library = result.get("voice_lab_profiles")
            library = copy.deepcopy(library) if isinstance(library, dict) else {}
            library[voice_name] = _json_copy(profile.voice_profile)
            result["voice_lab_profiles"] = library
            result["selected_voice_profile"] = voice_name
        result["selected_personality_profile"] = profile.slug
        result["personality_voice_namespace"] = self.voice_namespace(profile.slug)
        return result

    def apply(self, slug: str, cfg: Mapping[str, Any]) -> Dict[str, Any]:
        profile = self.select(slug)
        result = self.preview(slug, cfg)
        # Existing schema-1 records may not have an embedded voice yet. Preserve
        # the live selected profile and migrate the legacy active reference.
        self._migrate_legacy_active_reference(slug)
        self._ensure_runtime_active_reference(slug, profile.voice_active_reference)
        return result

    def apply_selected(self, cfg: Mapping[str, Any]) -> Dict[str, Any]:
        selected = self.selected_slug()
        return self.apply(selected, cfg) if selected else copy.deepcopy(dict(cfg))

    def delete(self, slug: str) -> str:
        slug = personality_slug(slug)
        data = self._read()
        profiles = data.setdefault("personalities", {})
        if slug not in profiles:
            raise KeyError(f"Unknown personality: {slug}")
        if len(profiles) <= 1:
            raise ValueError("At least one saved personality must remain.")
        del profiles[slug]
        selected = personality_slug(str(data.get("selected_personality") or ""))
        if selected == slug or selected not in profiles:
            selected = next(iter(profiles))
            data["selected_personality"] = selected
        self._write(data)
        # Voice assets are deliberately retained as a recovery safeguard.
        return selected

    def _add_asset_to_archive(
        self,
        archive: zipfile.ZipFile,
        source: Path,
        archive_root: str,
    ) -> Dict[str, Any]:
        if source.is_dir():
            files = [p for p in source.rglob("*") if p.is_file()]
            for path in files:
                rel = path.relative_to(source).as_posix()
                archive.write(path, f"{archive_root}/{rel}")
            return {"archive_path": archive_root, "kind": "directory", "file_count": len(files)}
        archive.write(source, archive_root)
        return {"archive_path": archive_root, "kind": "file", "file_count": 1}

    def export_profile(self, slug: str, destination: Path, *, include_voice_assets: bool = True) -> Path:
        """Export one self-contained personality project file."""
        profile = self.get(slug)
        destination = Path(destination)
        if destination.suffix.lower() != PACKAGE_EXTENSION:
            destination = destination.with_suffix(PACKAGE_EXTENSION)
        destination.parent.mkdir(parents=True, exist_ok=True)

        voice_profile = _json_copy(profile.voice_profile)
        active_reference = _json_copy(profile.voice_active_reference)
        assets: List[Dict[str, Any]] = []

        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            if include_voice_assets:
                used_paths: Dict[str, str] = {}

                def package_path(raw: Any, field: str, source_group: str) -> str:
                    source = _host_path(raw)
                    if not str(raw or "").strip() or not source.exists():
                        return str(raw or "")
                    key = str(source.resolve()).lower()
                    if key in used_paths:
                        return used_paths[key]
                    base = _safe_archive_component(source.name or field)
                    archive_root = f"assets/voice/{source_group}/{_safe_archive_component(field)}/{base}"
                    meta = self._add_asset_to_archive(archive, source, archive_root)
                    meta.update({"field": field, "source_group": source_group, "original_path": str(raw)})
                    assets.append(meta)
                    used_paths[key] = archive_root
                    return archive_root

                for field in VOICE_PATH_FIELDS:
                    if field in voice_profile:
                        voice_profile[field] = package_path(voice_profile.get(field), field, "profile")

                if active_reference.get("audio_path"):
                    active_reference["audio_path"] = package_path(
                        active_reference.get("audio_path"), "audio_path", "active_reference"
                    )
                active_reference.pop("source_config_path", None)

            manifest = {
                "format": "BX Personality Project",
                "schema_version": PACKAGE_SCHEMA_VERSION,
                "exported_at": _now_iso(),
                "source_robot_profile": self.robot_profile,
                "personality": {
                    "name": profile.name,
                    "description": profile.description,
                    "settings": _json_copy(profile.settings),
                    "voice": {
                        "profile_name": profile.voice_profile_name,
                        "profile": voice_profile,
                        "active_reference": active_reference,
                    },
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at,
                },
                "assets": assets,
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            archive.writestr(
                "README.txt",
                "BX Personality Project\n\n"
                "Load this file from Robot Brain Personality Studio. It contains the character identity, prompt, "
                "GUI theme, selected voice settings and any voice reference assets available at export time.\n",
            )
        temporary.replace(destination)
        return destination

    @staticmethod
    def _safe_member_name(name: str) -> str:
        normalised = str(name or "").replace("\\", "/").lstrip("/")
        if not normalised or normalised.startswith("../") or "/../" in f"/{normalised}":
            raise ValueError("The personality package contains an unsafe file path.")
        return normalised

    def import_profile(self, source: Path, *, activate: bool = True) -> PersonalityProfile:
        """Import a .bxpersonality package and install its voice assets safely."""
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(source)
        with zipfile.ZipFile(source, "r") as archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"This is not a valid BX personality project: {exc}") from exc
            if not isinstance(manifest, dict) or str(manifest.get("format") or "") != "BX Personality Project":
                raise ValueError("This file is not a BX Personality Project.")
            personality = manifest.get("personality")
            if not isinstance(personality, dict):
                raise ValueError("The package does not contain a personality record.")

            display_name = re.sub(r"\s+", " ", str(personality.get("name") or "Imported Personality").strip())
            data = self._read()
            profiles = data.setdefault("personalities", {})
            slug = self._unique_slug(data, display_name)
            asset_root = self.assets_dir / slug
            asset_root.mkdir(parents=True, exist_ok=True)

            def install_asset(value: Any) -> str:
                raw = str(value or "").strip()
                if not raw.startswith("assets/"):
                    return raw
                member = self._safe_member_name(raw)
                names = [self._safe_member_name(n) for n in archive.namelist()]
                exact = member in names
                children = [n for n in names if n.startswith(member.rstrip("/") + "/") and not n.endswith("/")]
                if not exact and not children:
                    return ""
                destination = asset_root / Path(member).relative_to("assets")
                if exact and not member.endswith("/"):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as src, destination.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    return str(destination)
                destination.mkdir(parents=True, exist_ok=True)
                for child in children:
                    relative = Path(child).relative_to(member)
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(child) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                return str(destination)

            settings = personality.get("settings") if isinstance(personality.get("settings"), dict) else {}
            voice = personality.get("voice") if isinstance(personality.get("voice"), dict) else {}
            voice_profile = _json_copy(voice.get("profile") if isinstance(voice.get("profile"), dict) else {})
            active_reference = _json_copy(
                voice.get("active_reference") if isinstance(voice.get("active_reference"), dict) else {}
            )
            for field in VOICE_PATH_FIELDS:
                if field in voice_profile:
                    voice_profile[field] = install_asset(voice_profile.get(field))
            if active_reference.get("audio_path"):
                active_reference["audio_path"] = install_asset(active_reference.get("audio_path"))

            now = _now_iso()
            profiles[slug] = {
                "name": display_name,
                "description": str(personality.get("description") or "").strip(),
                "settings": snapshot_personality(settings),
                "voice": {
                    "profile_name": str(voice.get("profile_name") or settings.get("selected_voice_profile") or ""),
                    "profile": voice_profile,
                    "namespace": self.voice_namespace(slug),
                    "active_reference": active_reference,
                },
                "created_at": str(personality.get("created_at") or now),
                "updated_at": now,
                "imported_from": str(source),
            }
            if activate:
                data["selected_personality"] = slug
            self._write(data)
            self._ensure_runtime_active_reference(slug, active_reference)
            return self._record(slug, profiles[slug])
