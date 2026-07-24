from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


DEFAULT_WAKE_TEMPLATES = ["hey {robot_name}", "hello {robot_name}"]
DEFAULT_WAKE_ACK_PHRASES = ["Yes?", "I'm listening.", "Go ahead."]
DEFAULT_WAITING_PHRASES = [
    "Let me think about that.",
    "One moment.",
    "I am checking that now.",
    "Working on it.",
    "I am still looking into that.",
]
DEFAULT_SLEEP_ACK = "Going quiet."


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise_lines(value: Any, *, maximum: int = 30) -> List[str]:
    if isinstance(value, str):
        raw = value.replace("\r", "").split("\n")
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raw = []
    result: List[str] = []
    seen = set()
    for item in raw:
        text = re.sub(r"\s+", " ", str(item or "").strip())
        key = text.casefold()
        if text and key not in seen:
            result.append(text[:220])
            seen.add(key)
        if len(result) >= maximum:
            break
    return result


def safe_key(value: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip().lower()).strip("_")
    return key or "phrase"


def _spoken_name_variants(robot_name: str) -> List[str]:
    """Return the written name plus a speech-friendly acronym/digit variant."""
    name = re.sub(r"\s+", " ", str(robot_name or "Robot").strip()) or "Robot"
    variants = [name]
    compact = re.sub(r"[^A-Za-z0-9]", "", name)
    digit_words = {
        "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
        "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
    }
    should_spell = bool(any(ch.isdigit() for ch in compact) or (compact.isupper() and 1 < len(compact) <= 6))
    if compact and should_spell:
        spoken = " ".join(digit_words.get(ch, ch.lower()) for ch in compact)
        if spoken.casefold() != name.casefold():
            variants.append(spoken)
    return variants


def build_wake_phrases(cfg: Dict[str, Any], robot_name: str) -> List[str]:
    templates = normalise_lines(cfg.get("body_wake_phrase_templates") or DEFAULT_WAKE_TEMPLATES, maximum=10)
    aliases = normalise_lines(cfg.get("body_wake_aliases") or [], maximum=10)
    names = _spoken_name_variants(robot_name)
    phrases: List[str] = []
    for template in templates:
        for name in names:
            try:
                phrase = template.format(robot_name=name, name=name)
            except Exception:
                phrase = template.replace("{robot_name}", name).replace("{name}", name)
            phrase = re.sub(r"\s+", " ", phrase.strip()).lower()
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    primary_name = names[0]
    for alias in aliases:
        try:
            phrase = alias.format(robot_name=primary_name, name=primary_name)
        except Exception:
            phrase = alias.replace("{robot_name}", primary_name).replace("{name}", primary_name)
        phrase = re.sub(r"\s+", " ", phrase.strip()).lower()
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    if not phrases:
        phrases = [f"hey {primary_name.lower()}", f"hello {primary_name.lower()}"]
    return phrases


def phrase_definitions(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    wake_ack = normalise_lines(cfg.get("body_wake_ack_phrases") or DEFAULT_WAKE_ACK_PHRASES, maximum=10)
    waiting = normalise_lines(cfg.get("body_waiting_phrases") or DEFAULT_WAITING_PHRASES, maximum=30)
    sleep_ack = re.sub(r"\s+", " ", str(cfg.get("body_sleep_ack_phrase") or DEFAULT_SLEEP_ACK).strip()) or DEFAULT_SLEEP_ACK
    definitions: List[Dict[str, Any]] = []
    for index, text in enumerate(wake_ack, start=1):
        definitions.append({
            "key": "wake_ack" if index == 1 else f"wake_ack_{index:02d}",
            "category": "wake acknowledgement",
            "text": text,
            "enabled": True,
            "delivery": "warm",
        })
    for index, text in enumerate(waiting, start=1):
        definitions.append({
            "key": f"thinking_{index:02d}",
            "category": "waiting for Brain",
            "text": text,
            "enabled": True,
            "delivery": "thoughtful",
        })
    definitions.append({
        "key": "sleep_ack",
        "category": "sleep acknowledgement",
        "text": sleep_ack,
        "enabled": True,
        "delivery": "calm",
    })
    return definitions


def settings_payload(cfg: Dict[str, Any], robot_name: str) -> Dict[str, Any]:
    return {
        "robot_name": robot_name,
        "wake_mode": str(cfg.get("body_wake_mode") or "automatic"),
        "wake_engine_preference": str(cfg.get("body_wake_engine_preference") or "dynamic_vosk"),
        "wake_phrases": build_wake_phrases(cfg, robot_name),
        "wake_phrase_templates": normalise_lines(cfg.get("body_wake_phrase_templates") or DEFAULT_WAKE_TEMPLATES, maximum=10),
        "wake_aliases": normalise_lines(cfg.get("body_wake_aliases") or [], maximum=10),
        "wake_sensitivity": float(cfg.get("body_wake_sensitivity", 0.72) or 0.72),
        "wake_ack_phrases": normalise_lines(cfg.get("body_wake_ack_phrases") or DEFAULT_WAKE_ACK_PHRASES, maximum=10),
        "waiting_phrases": normalise_lines(cfg.get("body_waiting_phrases") or DEFAULT_WAITING_PHRASES, maximum=30),
        "sleep_ack_phrase": str(cfg.get("body_sleep_ack_phrase") or DEFAULT_SLEEP_ACK),
        "thinking_cue_initial_delay_s": float(cfg.get("body_waiting_initial_delay_s", 1.2) or 1.2),
        "thinking_cue_repeat_s": float(cfg.get("body_waiting_repeat_s", 8.0) or 8.0),
        "thinking_cue_max_per_reply": int(cfg.get("body_waiting_max_per_reply", 3) or 3),
        "profile_sync_interval_s": float(cfg.get("body_profile_sync_interval_s", 15.0) or 15.0),
        "definitions": phrase_definitions(cfg),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BodyVoiceLibrary:
    """Profile-owned generated speech files published to the robot body."""

    SCHEMA = "bx1.body_voice_bundle.v1"

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("schema", self.SCHEMA)
                    data.setdefault("items", {})
                    return data
            except Exception:
                pass
        return {"schema": self.SCHEMA, "bundle_version": "", "generated_at": "", "items": {}}

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.manifest_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.manifest_path)

    def item_path(self, item: Dict[str, Any]) -> Optional[Path]:
        filename = Path(str(item.get("filename") or "")).name
        if not filename:
            return None
        candidate = (self.root / filename).resolve()
        if candidate.parent != self.root or not candidate.is_file():
            return None
        return candidate

    def status(self, definitions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        manifest = self.load_manifest()
        items = manifest.get("items") if isinstance(manifest.get("items"), dict) else {}
        rows: List[Dict[str, Any]] = []
        for definition in definitions:
            key = str(definition.get("key") or "")
            item = dict(items.get(key) or {}) if isinstance(items.get(key), dict) else {}
            path = self.item_path(item)
            text_matches = str(item.get("text") or "") == str(definition.get("text") or "")
            rows.append({
                **definition,
                "generated": bool(path and text_matches),
                "stale": bool(path and not text_matches),
                "filename": path.name if path else "",
                "size_bytes": path.stat().st_size if path else 0,
                "sha256": str(item.get("sha256") or ""),
                "generated_at": str(item.get("generated_at") or ""),
                "engine": str(item.get("engine") or ""),
                "format": str(item.get("format") or (path.suffix.lstrip(".") if path else "")),
                "audio_url": f"/api/body_audio/{path.name}" if path else "",
            })
        return {
            "schema": self.SCHEMA,
            "bundle_version": str(manifest.get("bundle_version") or ""),
            "generated_at": str(manifest.get("generated_at") or ""),
            "count": sum(1 for row in rows if row.get("generated")),
            "expected_count": len(rows),
            "items": rows,
        }

    def generate(
        self,
        definition: Dict[str, Any],
        generator: Callable[[str, str], Dict[str, Any]],
        source_audio_dir: Path,
    ) -> Dict[str, Any]:
        key = safe_key(str(definition.get("key") or "phrase"))
        text = str(definition.get("text") or "").strip()
        delivery = str(definition.get("delivery") or "normal")
        if not text:
            return {"ok": False, "key": key, "error": "Phrase text is empty."}
        result = generator(text, delivery)
        if not result.get("ok"):
            return {"ok": False, "key": key, "text": text, "error": str(result.get("error") or result)}
        source = (Path(source_audio_dir) / Path(str(result.get("filename") or "")).name).resolve()
        source_root = Path(source_audio_dir).resolve()
        if source.parent != source_root or not source.is_file():
            return {"ok": False, "key": key, "text": text, "error": "Generated audio file was not published by the Brain API."}
        suffix = source.suffix.lower() if source.suffix.lower() in {".wav", ".mp3", ".ogg"} else ".wav"
        target = self.root / f"{key}{suffix}"
        temp = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, temp)
        temp.replace(target)
        try:
            source.unlink(missing_ok=True)
        except Exception:
            pass
        generated_at = now_iso()
        item = {
            "key": key,
            "category": str(definition.get("category") or ""),
            "text": text,
            "delivery": delivery,
            "filename": target.name,
            "format": target.suffix.lstrip("."),
            "size_bytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "generated_at": generated_at,
            "engine": str(result.get("engine") or ""),
            "voice": str(result.get("voice") or ""),
        }
        manifest = self.load_manifest()
        items = manifest.setdefault("items", {})
        if not isinstance(items, dict):
            items = {}
            manifest["items"] = items
        items[key] = item
        manifest["schema"] = self.SCHEMA
        manifest["generated_at"] = generated_at
        manifest["bundle_version"] = generated_at
        self.save_manifest(manifest)
        return {"ok": True, **item, "audio_url": f"/api/body_audio/{target.name}"}

    def generate_many(
        self,
        definitions: Iterable[Dict[str, Any]],
        generator: Callable[[str, str], Dict[str, Any]],
        source_audio_dir: Path,
    ) -> Dict[str, Any]:
        results = [self.generate(definition, generator, source_audio_dir) for definition in definitions]
        generated = sum(1 for item in results if item.get("ok"))
        return {
            "ok": generated == len(results) and generated > 0,
            "generated": generated,
            "requested": len(results),
            "results": results,
        }
