from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from bx1_modules.persona_presets import female_companion_config


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value).strip()).strip("_").lower()


@dataclass(frozen=True)
class RobotProfile:
    slug: str
    name: str
    description: str
    api_port: int
    tts_port: int


class ProfileStore:
    """Owns robot-specific configuration without changing the shared brain code."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.config_dir = self.root / "config"
        self.runtime_dir = self.root / "runtime"
        self.registry_path = self.config_dir / "robot_profiles.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def _read_registry(self) -> Dict[str, Any]:
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {"schema_version": 1, "selected_profile": "bx1", "profiles": {}}

    def _write_registry(self, data: Dict[str, Any]) -> None:
        self.registry_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def discover(self) -> List[RobotProfile]:
        registry = self._read_registry()
        records = registry.get("profiles") if isinstance(registry.get("profiles"), dict) else {}
        slugs = {safe_slug(x) for x in records}
        for path in self.config_dir.glob("app_config_*.json"):
            slugs.add(safe_slug(path.stem.removeprefix("app_config_")))
        result: List[RobotProfile] = []
        for slug in sorted(x for x in slugs if x):
            item = records.get(slug, {}) if isinstance(records.get(slug), dict) else {}
            cfg = self.read_app_config(slug)
            result.append(RobotProfile(
                slug=slug,
                name=str(item.get("name") or cfg.get("robot_name") or slug.upper()),
                description=str(item.get("description") or cfg.get("robot_profile") or "Robot assistant"),
                api_port=int(item.get("api_port") or cfg.get("api_port") or 8765),
                # Dot.TTS is a shared GPU host. Profiles keep independent voice
                # references, but they do not load duplicate model processes.
                tts_port=8092,
            ))
        return result

    def read_app_config(self, slug: str) -> Dict[str, Any]:
        path = self.config_dir / f"app_config_{safe_slug(slug)}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @staticmethod
    def _port_from_url(value: Any) -> int:
        match = re.search(r":(\d+)(?:/|$)", str(value or ""))
        return int(match.group(1)) if match else 0

    def selected_slug(self) -> str:
        return safe_slug(self._read_registry().get("selected_profile") or "bx1") or "bx1"

    def select(self, slug: str) -> None:
        slug = safe_slug(slug)
        if slug not in {p.slug for p in self.discover()}:
            raise ValueError(f"Unknown robot profile: {slug}")
        data = self._read_registry()
        data["selected_profile"] = slug
        self._write_registry(data)

    def create(self, *, slug: str, name: str, description: str, personality: str,
               source: str = "bx1", api_port: int = 8765, tts_port: int = 8092,
               preset: str = "") -> RobotProfile:
        slug, source = safe_slug(slug), safe_slug(source)
        tts_port = 8092
        if not slug:
            raise ValueError("Enter a profile ID using letters or numbers.")
        if (self.config_dir / f"app_config_{slug}.json").exists():
            raise FileExistsError(f"Profile '{slug}' already exists.")
        src_app = self.config_dir / f"app_config_{source}.json"
        if not src_app.exists():
            src_app = self.config_dir / "app_config.example.json"
        app = json.loads(src_app.read_text(encoding="utf-8"))
        app.update({
            "brain_profile": slug,
            "robot_name": name.strip() or slug.upper(),
            "robot_profile": description.strip() or "configurable robot assistant",
            "api_port": int(api_port),
            "dottts_service_url": "http://127.0.0.1:8092",
            "personality_prompt": personality.strip() or (
                "You are {robot_name}, {robot_profile}. Be helpful, concise, curious and honest. "
                "Never claim a physical action happened unless body telemetry confirms it."
            ),
            "project_context": (
                "This is a reusable Robot Brain profile. Identity, personality, memory, voice and runtime "
                "data belong to this robot profile; shared code and safety rules belong to the platform."
            ),
        })
        if str(preset or "").strip().lower() == "female_companion":
            companion = female_companion_config(name.strip() or "Unnamed")
            app.update(companion)
            if description.strip():
                app["robot_profile"] = description.strip()
            if personality.strip():
                app["personality_prompt"] = personality.strip()
        robot_name = str(app["robot_name"])
        source_profiles = app.get("voice_lab_profiles") if isinstance(app.get("voice_lab_profiles"), dict) else {}
        source_selected = str(app.get("selected_voice_profile") or "")
        voice_template = dict(source_profiles.get(source_selected) or next(iter(source_profiles.values()), {}) or {})
        voice_template.update({
            "description": f"Main {robot_name} Dot.TTS cloned voice profile.",
            "mode": "dottts",
            "model_choice": "mf",
            "speaker": robot_name,
            "reference_audio_path": "",
            "reference_audio_filename": "",
            "reference_transcript_path": "",
            "reference_text": "",
            "sample_filename": "",
            "created_at": "",
        })
        voice_name = f"{robot_name} Main Voice"
        app["voice_lab_profiles"] = {voice_name: voice_template}
        app["selected_voice_profile"] = voice_name
        app["voice_lab_sample_text"] = f"Hello. I am {robot_name}. My voice system is online and ready."
        app["speech_cache_files"] = {}
        (self.config_dir / f"app_config_{slug}.json").write_text(json.dumps(app, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.runtime_dir.joinpath(slug).mkdir(parents=True, exist_ok=True)
        record = self._read_registry()
        profiles = record.setdefault("profiles", {})
        profiles[slug] = {"name": app["robot_name"], "description": app["robot_profile"], "api_port": int(api_port), "tts_port": int(tts_port)}
        self._write_registry(record)
        return RobotProfile(slug, app["robot_name"], app["robot_profile"], int(api_port), int(tts_port))

    def update_identity(self, slug: str, *, name: str, description: str = "") -> None:
        """Keep the profile picker in sync after an identity chooses a name."""
        slug = safe_slug(slug)
        if not slug:
            raise ValueError("A profile ID is required.")
        record = self._read_registry()
        profiles = record.setdefault("profiles", {})
        item = profiles.setdefault(slug, {})
        item["name"] = str(name or slug.upper()).strip() or slug.upper()
        if str(description or "").strip():
            item["description"] = str(description).strip()
        self._write_registry(record)
