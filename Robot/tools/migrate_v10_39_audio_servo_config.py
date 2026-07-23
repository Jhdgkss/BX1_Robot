#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "python" / "config.json"

if not CONFIG.exists():
    print(f"[BX1] No existing config.json at {CONFIG}; nothing to migrate.")
    raise SystemExit(0)

stamp = time.strftime("%Y%m%d_%H%M%S")
backup = CONFIG.with_name(f"config.json.before_v10_39_{stamp}.bak")
shutil.copy2(CONFIG, backup)

data = json.loads(CONFIG.read_text(encoding="utf-8"))
data["app_version"] = "10.39"
data["version"] = "10.39"

# Preserve the user's tuned microphone levels. Only add the newer endpointing
# safety fields when they are missing.
data.setdefault("stt_speech_resume_trigger_ms", 140)
data.setdefault("stt_transient_guard_after_ms", 220)
data.setdefault("stt_endpoint_hysteresis_db", 3.0)
data.setdefault("stt_debug_keep_audio", True)
data["stt_capture_method"] = "alsa"

reg = data.setdefault("hardware_registry", {})
behaviour = reg.setdefault("servo_behaviour", {})
behaviour.setdefault("quiet_release_enabled", True)
behaviour.setdefault("release_after_ms", 1200)
behaviour.setdefault("pulse_deadband_us", 4)
behaviour.setdefault(
    "note",
    "Release PWM after a pose settles to reduce servo buzz; disable if the head needs continuous holding torque.",
)

CONFIG.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"[BX1] v10.39 config migration complete: {CONFIG}")
print(f"[BX1] Backup: {backup}")
print("[BX1] Existing microphone gain/noise-gate settings were preserved.")
