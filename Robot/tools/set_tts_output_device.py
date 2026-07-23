#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run from anywhere inside the project, or pass the project root as arg 2.
device = sys.argv[1] if len(sys.argv) > 1 else "plughw:1,0"
project_root = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) > 2 else Path(__file__).resolve().parents[1]
config_path = project_root / "python" / "config.json"

if not config_path.exists():
    raise SystemExit(f"config.json not found: {config_path}")

config = json.loads(config_path.read_text(encoding="utf-8"))
config["tts_playback_device"] = device
# Keep the mic playback default aligned if it is not already set.
config.setdefault("mic_playback_device", device)

tmp_path = config_path.with_suffix(".json.tmp")
tmp_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
tmp_path.replace(config_path)
print(f"Updated {config_path}")
print(f"tts_playback_device = {device}")
