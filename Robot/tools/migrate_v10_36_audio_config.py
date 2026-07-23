#!/usr/bin/env python3
"""Safely apply the BX1 v10.36 low-latency microphone/STT settings."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def migrate_config(config: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    migrated = dict(config)
    changes: Dict[str, Dict[str, Any]] = {}

    def set_value(key: str, value: Any) -> None:
        old = migrated.get(key)
        if old != value:
            changes[key] = {"from": old, "to": value}
            migrated[key] = value

    # Primary faster-whisper should run first. Local Vosk is retained, but is
    # invoked only when the desktop STT service is unavailable.
    set_value("stt_defer_local_vosk_when_brain_enabled", True)

    # Ignore short post-speech clicks/chirps rather than restarting the complete
    # end-silence timer.
    set_value("stt_speech_resume_trigger_ms", 140)
    set_value("stt_transient_guard_after_ms", 220)
    set_value("stt_endpoint_hysteresis_db", 3.0)

    # Reduce avoidable waiting while preserving enough tail for natural speech.
    old_end = int(round(_number(migrated.get("stt_end_silence_ms"), 850)))
    if old_end > 650:
        set_value("stt_end_silence_ms", 600)
    old_post = int(round(_number(migrated.get("stt_post_roll_ms"), 250)))
    if old_post > 180:
        set_value("stt_post_roll_ms", 160)
    old_margin = _number(migrated.get("stt_adaptive_margin_db"), 8.0)
    if old_margin > 5.0:
        set_value("stt_adaptive_margin_db", 5.0)

    set_value("app_version", "10.36")
    set_value("version", "10.36")
    return migrated, {
        "from_version": str(config.get("version") or config.get("app_version") or "unknown"),
        "to_version": "10.36",
        "changes": changes,
        "preserved_keys": len(config),
    }


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
        backup = path.with_name(f"{path.name}.before_v10_36_audio_{stamp}.bak")
        shutil.copy2(path, backup)

    temporary = path.with_suffix(path.suffix + ".v10_36.tmp")
    temporary.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    report["config_path"] = str(path)
    report["backup_path"] = str(backup or "")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Path to python/config.json")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    print(json.dumps({"ok": True, **migrate_file(args.config, create_backup=not args.no_backup)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
