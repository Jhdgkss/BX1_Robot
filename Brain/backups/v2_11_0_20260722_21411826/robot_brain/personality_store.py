from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


PERSONALITY_SETTING_KEYS = (
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
    "voice_style",
    "selected_voice_profile",
    "edge_voice",
    "dottts_emotional_delivery_enabled",
    "dottts_inline_delivery_instructions",
    "dottts_default_delivery",
)


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


@dataclass(frozen=True)
class PersonalityProfile:
    slug: str
    name: str
    description: str
    settings: Dict[str, Any]
    created_at: str
    updated_at: str


class PersonalityStore:
    """Persistent personality library owned by one physical robot profile."""

    def __init__(self, root: Path, robot_profile: str) -> None:
        self.root = Path(root).resolve()
        self.config_dir = self.root / "config"
        self.robot_profile = personality_slug(robot_profile) or "default"
        self.path = self.config_dir / f"personality_profiles_{self.robot_profile}.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _empty(self) -> Dict[str, Any]:
        return {"schema_version": 1, "selected_personality": "", "personalities": {}}

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("personalities"), dict):
                data.setdefault("schema_version", 1)
                data.setdefault("selected_personality", "")
                return data
        except Exception:
            pass
        return self._empty()

    def _write(self, data: Dict[str, Any]) -> None:
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
    def _record(slug: str, item: Dict[str, Any]) -> PersonalityProfile:
        return PersonalityProfile(
            slug=slug,
            name=str(item.get("name") or slug.replace("_", " ").title()),
            description=str(item.get("description") or ""),
            settings=_json_copy(item.get("settings") if isinstance(item.get("settings"), dict) else {}),
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

    def bootstrap(self, current_cfg: Mapping[str, Any], female_cfg: Optional[Mapping[str, Any]] = None) -> None:
        """Migrate the current V2.8 settings and add the requested female persona once."""
        data = self._read()
        profiles = data.setdefault("personalities", {})
        if profiles:
            return
        now = _now_iso()
        current_slug = "current_personality"
        profiles[current_slug] = {
            "name": "Current Personality",
            "description": "The personality that was active before the personality library was added.",
            "settings": snapshot_personality(current_cfg),
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
                "created_at": now,
                "updated_at": now,
            }
        data["schema_version"] = 1
        data["selected_personality"] = current_slug
        self._write(data)

    def create(self, name: str, cfg: Mapping[str, Any], description: str = "") -> PersonalityProfile:
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
            "created_at": now,
            "updated_at": now,
        }
        data["selected_personality"] = slug
        self._write(data)
        return self._record(slug, profiles[slug])

    def update(self, slug: str, cfg: Mapping[str, Any], *, name: Optional[str] = None,
               description: Optional[str] = None) -> PersonalityProfile:
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
        item["updated_at"] = _now_iso()
        data["selected_personality"] = slug
        self._write(data)
        return self._record(slug, item)

    def duplicate(self, slug: str, new_name: str) -> PersonalityProfile:
        source = self.get(slug)
        return self.create(new_name, source.settings, source.description)

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

    def apply(self, slug: str, cfg: Mapping[str, Any]) -> Dict[str, Any]:
        profile = self.select(slug)
        result = copy.deepcopy(dict(cfg))
        result.update(_json_copy(profile.settings))
        result["selected_personality_profile"] = profile.slug
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
        return selected
