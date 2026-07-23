#!/usr/bin/env python3
"""Small helper for editing the robot profile from SSH.

Examples:
  ./tools/set_robot_profile.py --name BX1 --id BX1 --theme dark-blue --tts-output plughw:1,0
  ./tools/set_robot_profile.py --name BX2 --id BX2 --theme green
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "python" / "config.json"
PROFILE = ROOT / "python" / "robot_profile.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", dest="robot_id")
    ap.add_argument("--name", dest="robot_name")
    ap.add_argument("--display-name")
    ap.add_argument("--theme", choices=["dark-blue", "graphite", "green", "amber", "purple", "light"])
    ap.add_argument("--tts-output", help="ALSA output device, for example plughw:1,0")
    ap.add_argument("--summary")
    ap.add_argument("--tone")
    args = ap.parse_args()

    cfg = load_json(CONFIG)
    profile = load_json(PROFILE)

    robot_id = args.robot_id or profile.get("robot_id") or cfg.get("robot_id") or "BX1"
    robot_name = args.robot_name or profile.get("robot_name") or cfg.get("robot_name") or robot_id
    profile["robot_id"] = str(robot_id)
    profile["robot_name"] = str(robot_name)
    profile["display_name"] = str(args.display_name or profile.get("display_name") or robot_name)

    wake_words = profile.get("wake_words") or cfg.get("wake_words") or []
    if isinstance(wake_words, str):
        wake_words = [w.strip() for w in wake_words.replace(",", "\n").splitlines() if w.strip()]
    for item in (str(robot_name).lower(), str(robot_id).lower()):
        if item and item not in wake_words:
            wake_words.insert(0, item)
    profile["wake_words"] = wake_words

    personality = dict(profile.get("personality") or {})
    if args.summary:
        personality["summary"] = args.summary
    personality.setdefault("summary", "A friendly practical robot assistant.")
    if args.tone:
        personality["tone"] = args.tone
    personality.setdefault("tone", "warm, curious and technically helpful")
    personality.setdefault("verbosity", "medium")
    personality.setdefault("humour_level", 0.35)
    personality.setdefault("confidence_level", 0.65)
    personality.setdefault("rules", ["Keep spoken replies concise unless asked for detail."])
    profile["personality"] = personality

    voice = dict(profile.get("voice_profile") or {})
    if args.tts_output:
        voice["playback_device"] = args.tts_output
        cfg["tts_playback_device"] = args.tts_output
    voice.setdefault("engine", cfg.get("tts_backend", "edge-tts"))
    voice.setdefault("voice", cfg.get("tts_edge_voice", cfg.get("tts_voice", "en-GB-SoniaNeural")))
    voice.setdefault("playback_device", cfg.get("tts_playback_device", "default"))
    voice.setdefault("fallback_voice_allowed", bool(cfg.get("tts_fallback_to_espeak", False)))
    profile["voice_profile"] = voice

    ui = dict(profile.get("ui") or {})
    if args.theme:
        ui["theme"] = args.theme
        cfg["ui_theme"] = args.theme
    ui.setdefault("theme", cfg.get("ui_theme", "dark-blue"))
    profile["ui"] = ui

    cfg["robot_id"] = profile["robot_id"]
    cfg["robot_name"] = profile["robot_name"]
    cfg["wake_words"] = profile["wake_words"]
    save_json(PROFILE, profile)
    save_json(CONFIG, cfg)
    print(f"Saved robot profile: {profile['robot_name']} ({profile['robot_id']})")
    print(f"Profile file: {PROFILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
