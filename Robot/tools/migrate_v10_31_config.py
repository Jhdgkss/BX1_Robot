from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path


def main() -> int:
    project = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    config = project / "python" / "config.json"
    example = project / "python" / "config.example.json"
    if not config.exists():
        if not example.exists():
            print(f"ERROR: Missing {config} and {example}")
            return 1
        shutil.copy2(example, config)
        print(f"Created {config} from the clean example.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = config.with_name(f"config.json.before_v10_31_{stamp}")
    shutil.copy2(config, backup)
    data = json.loads(config.read_text(encoding="utf-8"))
    data["app_version"] = "10.31"
    data["version"] = "10.31"
    data.setdefault("stt_transcription_backend", "brain_faster_whisper")
    data.setdefault("brain_stt_enabled", True)
    data.setdefault("brain_stt_timeout_s", 120)
    data.setdefault("brain_stt_fallback_to_vosk", True)
    data.setdefault("brain_stt_language", "en")
    data.setdefault("brain_stt_hotwords", "")
    data.setdefault("brain_stt_initial_prompt", "")
    data["stt_debug_keep_audio"] = True
    # Repair the old aggressive defaults while preserving deliberate user tuning.
    if float(data.get("stt_adaptive_margin_db", 8.0) or 8.0) >= 7.5:
        data["stt_adaptive_margin_db"] = 2.0
    if int(data.get("stt_pre_roll_ms", 450) or 450) <= 700:
        data["stt_pre_roll_ms"] = 900
    if int(data.get("stt_end_silence_ms", 1100) or 1100) <= 1350:
        data["stt_end_silence_ms"] = 1700
    if float(data.get("audio_noise_reduction_strength", 0.2) or 0.2) > 0.15:
        data["audio_noise_reduction_strength"] = 0.10
    config.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Migrated {config} to BX1 Body v10.31")
    print(f"Backup: {backup}")
    print("Primary STT: desktop Brain faster-whisper; fallback: local Vosk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
