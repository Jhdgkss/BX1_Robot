#!/usr/bin/env python3
"""Safely migrate an existing BX1 body configuration to the v10.35 audio contract."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import urlparse


LEGACY_REMOTE_BACKENDS = {"brain-tts", "brain_tts", "brain", "robot-brain", "robot_brain"}


def normalise_brain_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else "http://" + raw
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8765}"


def migrate_config(config: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return a migrated copy and a compact report; unknown/user keys are preserved."""
    migrated = dict(config)
    original_backend = str(migrated.get("tts_backend", "") or "").strip().lower()
    brain_url = normalise_brain_url(migrated.get("brain_base_url"))

    if brain_url:
        migrated["brain_base_url"] = brain_url
    if original_backend in LEGACY_REMOTE_BACKENDS or not original_backend:
        migrated["tts_backend"] = "edge-tts"

    migrated.update({
        "app_version": "10.35",
        "version": "10.35",
        "brain_response_audio_enabled": True,
        "brain_tts_base_url": brain_url,
        "brain_tts_follow_brain_host": True,
        "brain_tts_engine": "dottts",
        "brain_tts_voice": "active_profile",
        "brain_tts_endpoint": "/api/tts",
        "brain_tts_status_endpoint": "/api/tts/status",
        "brain_tts_use_brain_defaults": True,
        "skip_body_tts_when_brain_audio_present": True,
        "tts_fallback_to_espeak": True,
    })
    try:
        migrated["chat_timeout_s"] = max(480, int(migrated.get("chat_timeout_s", 480) or 480))
    except (TypeError, ValueError):
        migrated["chat_timeout_s"] = 480
    try:
        migrated["vision_timeout_s"] = max(480, int(migrated.get("vision_timeout_s", 480) or 480))
    except (TypeError, ValueError):
        migrated["vision_timeout_s"] = 480
    report = {
        "from_version": str(config.get("version") or config.get("app_version") or "unknown"),
        "to_version": "10.35",
        "brain_base_url": brain_url,
        "reply_audio": "Brain API /api/audio",
        "fallback_backend": migrated.get("tts_backend"),
        "preserved_keys": len(config),
    }
    return migrated, report


def migrate_file(path: Path, *, create_backup: bool = True) -> Dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    original = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(original, dict):
        raise ValueError("Configuration root must be a JSON object.")
    migrated, report = migrate_config(original)

    backup = None
    if create_backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.name}.before_v10_35_{stamp}.bak")
        shutil.copy2(path, backup)

    temporary = path.with_suffix(path.suffix + ".v10_35.tmp")
    temporary.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    report["config_path"] = str(path)
    report["backup_path"] = str(backup or "")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Path to python/config.json")
    parser.add_argument("--no-backup", action="store_true", help="Do not create an additional adjacent backup")
    args = parser.parse_args()
    report = migrate_file(args.config, create_backup=not args.no_backup)
    print(json.dumps({"ok": True, **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
