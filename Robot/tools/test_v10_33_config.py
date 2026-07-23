#!/usr/bin/env python3
import argparse
import importlib.util
import json
import py_compile
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--project", required=True)
args = ap.parse_args()
root = Path(args.project)
for rel in ("python/main.py", "python/web_control.py", "python/audio_io.py", "python/bx1_robot_client.py"):
    py_compile.compile(str(root / rel), doraise=True)

cfg = json.loads((root / "python/config.json").read_text(encoding="utf-8"))
assert cfg["app_version"] == "10.33"
assert cfg["brain_controls_thinking_cues"] is False
assert cfg["stt_repetition_guard_enabled"] is True
assert cfg["conversation_followup_window_s"] >= 90
assert {"hello", "hey", "robot"}.issubset({str(x).lower() for x in cfg.get("wake_words", [])})
assert "rowboat" not in {str(x).lower() for x in cfg.get("wake_word_aliases", {}).get("robot", [])}

spec = importlib.util.spec_from_file_location("bx1_audio_test", root / "python/audio_io.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
for corrupt in (
    "radio " * 20,
    "we are going to do the work together " * 8,
    "The speaker may begin with a wake phrase such as hello, hey, robot. Preserve the wake phrase in the transcript.",
):
    report = module.analyse_transcript_quality(corrupt, 5.0, cfg)
    assert report["ok"] is False, report
assert module.analyse_transcript_quality("hello bx1 can you check the camera", 2.2, cfg)["ok"] is True
print("BX1 body v10.33 validation passed")
