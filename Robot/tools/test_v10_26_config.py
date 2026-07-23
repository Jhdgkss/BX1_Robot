#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def check(condition: bool, message: str, errors: list[str]) -> None:
    if condition:
        print(f"PASS: {message}")
    else:
        print(f"FAIL: {message}")
        errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    errors: list[str] = []

    required = [
        project / "python/main.py",
        project / "python/web_control.py",
        project / "python/audio_io.py",
        project / "python/camera_io.py",
        project / "python/config.json",
    ]
    for path in required:
        check(path.exists(), f"exists: {path.relative_to(project)}", errors)

    cfg = json.loads((project / "python/config.json").read_text(encoding="utf-8"))
    check(str(cfg.get("version")) == "10.26", "config version is 10.26", errors)
    check(cfg.get("input_mode") == "both" and cfg.get("voice_enabled") is True, "live keyboard + microphone enabled", errors)
    check([str(x).lower() for x in cfg.get("wake_words", [])] == ["hello", "hey", "robot"], "natural wake words configured", errors)
    check(cfg.get("mouth_audio_reactive_enabled") is True, "reactive mouth enabled", errors)
    check(cfg.get("camera_enabled") is True and cfg.get("auto_camera_on_vision_request") is True, "on-demand camera enabled", errors)
    check(cfg.get("send_periodic_camera_frames") is True, "passive Brain camera frames enabled", errors)
    check(cfg.get("visual_awareness_enabled") is True, "local visual awareness enabled", errors)
    servos = ((cfg.get("hardware_registry") or {}).get("servos") or {})
    check((servos.get("head_yaw") or {}).get("pin") == 9, "yaw servo is D9", errors)
    check((servos.get("gimbal_left") or {}).get("pin") == 10, "left gimbal servo is D10", errors)
    check((servos.get("gimbal_right") or {}).get("pin") == 11, "right gimbal servo is D11", errors)
    phrases = [str(x).lower() for x in cfg.get("vision_trigger_phrases", [])]
    for phrase in ("look at this", "what's this", "describe this", "what am i holding"):
        check(phrase in phrases, f"vision trigger present: {phrase}", errors)

    main_text = (project / "python/main.py").read_text(encoding="utf-8")
    web_text = (project / "python/web_control.py").read_text(encoding="utf-8")
    audio_text = (project / "python/audio_io.py").read_text(encoding="utf-8")
    camera_text = (project / "python/camera_io.py").read_text(encoding="utf-8")

    check("def visual_awareness_loop" in main_text, "visual awareness loop installed", errors)
    check("def web_camera_vision" in main_text, "web camera vision endpoint installed", errors)
    check("external_awake_until" in main_text, "visual presence can open voice session", errors)
    check("speech_audio_file_start" in audio_text and "_bx1_build_wav_mouth_profile" in audio_text, "speech test uses WAV mouth envelope", errors)
    check("capture_analysis_jpeg" in camera_text and "haarcascade_frontalface_default" in camera_text, "local face/motion camera analysis installed", errors)
    check("Vision / Awareness" in web_text and "/api/camera_snapshot.jpg" in web_text, "vision web page and snapshot route installed", errors)
    check("/api/camera_vision" in web_text and "/api/vision_settings" in web_text, "vision control API routes installed", errors)

    python_bin = project / ".venv/bin/python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    compile_files = [str(p) for p in required[:4]]
    result = subprocess.run([str(python_bin), "-m", "py_compile", *compile_files], text=True, capture_output=True)
    check(result.returncode == 0, "Python files compile", errors)
    if result.returncode != 0:
        print(result.stderr)

    # Prove migration preserves a valid JSON file and applies v10.26 defaults.
    with tempfile.TemporaryDirectory() as tmp:
        temp_cfg = Path(tmp) / "config.json"
        temp_cfg.write_text(json.dumps({"brain_base_url": "http://example:8765", "mic_device": "plughw:0,0"}), encoding="utf-8")
        migrate = project / "tools/migrate_v10_26_config.py"
        defaults = project / "python/config.v10.26.defaults.json"
        cmd = [str(python_bin), str(migrate), str(temp_cfg)]
        if defaults.exists():
            cmd += ["--defaults", str(defaults)]
        migrated = subprocess.run(cmd, text=True, capture_output=True)
        check(migrated.returncode == 0, "configuration migration executes", errors)
        if migrated.returncode == 0:
            test_cfg = json.loads(temp_cfg.read_text(encoding="utf-8"))
            check(test_cfg.get("brain_base_url") == "http://example:8765", "migration preserves Brain URL", errors)
            check(test_cfg.get("mic_device") == "plughw:0,0", "migration preserves microphone device", errors)
            check(test_cfg.get("version") == "10.26", "migration writes v10.26", errors)

    if errors:
        print(f"\nVALIDATION FAILED: {len(errors)} problem(s)")
        return 1
    print("\nVALIDATION PASSED: BX1 v10.26 body update is internally consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
