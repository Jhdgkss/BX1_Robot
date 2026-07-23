#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "10.28"


def check(condition: bool, message: str, errors: list[str]) -> None:
    if condition:
        print(f"PASS: {message}")
    else:
        print(f"FAIL: {message}")
        errors.append(message)


def extract_method(text: str, name: str) -> str:
    match = re.search(rf"^    def {re.escape(name)}\(.*?(?=^    def |^class |\Z)", text, re.M | re.S)
    return match.group(0) if match else ""


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
        project / "tools/migrate_v10_28_config.py",
        project / "INSTALL_BX1_OPENCV.sh",
        project / "INSTALL_BX1_BETTER_STT_MODEL.sh",
    ]
    for path in required:
        check(path.exists(), f"exists: {path.relative_to(project)}", errors)

    cfg = json.loads((project / "python/config.json").read_text(encoding="utf-8"))
    check(str(cfg.get("version")) == VERSION and str(cfg.get("app_version")) == VERSION, "config version is 10.28", errors)
    check(cfg.get("input_mode") == "both" and cfg.get("voice_enabled") is True, "live keyboard + microphone enabled", errors)
    wake_words = [str(x).lower() for x in cfg.get("wake_words", [])]
    check(all(word in wake_words for word in ["hello", "hey", "robot"]), "natural default wake words configured", errors)
    check(int(cfg.get("stt_pre_roll_ms", 0)) >= 700, "STT pre-roll protects first words", errors)
    check(int(cfg.get("stt_end_silence_ms", 0)) >= 1350, "STT end silence protects sentence endings", errors)
    check(int(cfg.get("stt_post_roll_ms", 0)) >= 300, "STT post-roll enabled", errors)
    check(int(cfg.get("stt_start_trigger_ms", 999)) <= 80, "STT starts promptly", errors)
    check(float(cfg.get("audio_noise_reduction_strength", 1.0)) <= 0.20, "noise reduction no longer over-processes speech", errors)
    check(cfg.get("camera_live_preview_enabled") is True, "camera live preview enabled", errors)
    check(1.0 <= float(cfg.get("camera_live_preview_interval_s", 0)) <= 5.0, "camera preview interval is usable", errors)
    check(cfg.get("idle_life_response_mode") == "brain", "idle responses use desktop Brain personality", errors)
    check(isinstance(cfg.get("idle_life_require_alone"), bool), "idle presence gate is configurable", errors)
    check(cfg.get("idle_life_event_provenance_enabled") is True, "idle event provenance enabled", errors)

    servos = ((cfg.get("hardware_registry") or {}).get("servos") or {})
    check((servos.get("head_yaw") or {}).get("pin") == 9, "yaw servo is D9", errors)
    check((servos.get("gimbal_left") or {}).get("pin") == 10, "left gimbal servo is D10", errors)
    check((servos.get("gimbal_right") or {}).get("pin") == 11, "right gimbal servo is D11", errors)

    main_text = (project / "python/main.py").read_text(encoding="utf-8")
    web_text = (project / "python/web_control.py").read_text(encoding="utf-8")
    audio_text = (project / "python/audio_io.py").read_text(encoding="utf-8")
    camera_text = (project / "python/camera_io.py").read_text(encoding="utf-8")

    vision_update = extract_method(main_text, "web_update_visual_awareness_settings")
    check(bool(vision_update), "vision settings method found", errors)
    check("clamp_int_value" in vision_update and "clamp_float_value" in vision_update, "vision settings use shared clamp helpers", errors)
    check("clamp_int(" not in vision_update, "vision settings NameError path removed", errors)
    check("def get_camera_snapshot_jpeg" in main_text and "web_preview_fresh" in main_text, "cached/fresh camera preview installed", errors)
    check('"person_present": None' in main_text and '"alone": None' in main_text, "OpenCV absence reports presence as unknown", errors)
    check("def visual_awareness_loop" in main_text and "capture_analysis_jpeg" in camera_text, "face/motion awareness path installed", errors)
    check("AUTONOMOUS IDLE-LIFE EVENT" in main_text and "def handle_idle_brain_response" in main_text, "Brain-authored idle responses installed", errors)
    check('source="idle_life"' in main_text and 'trigger=f"idle_{kind}"' in main_text and '"display_text": f"Idle-life {kind} phase"' in main_text, "idle responses carry explicit Brain provenance", errors)
    check('"hello": {"hi", "hullo", "yellow"}' in main_text, "natural hi/hello wake alias installed", errors)
    check("def web_test_idle_life_action" in main_text and "def web_reset_idle_life_timer" in main_text, "idle test/reset controls installed", errors)
    check("Idle Life" in web_text and "page-idle" in web_text, "Idle Life web page installed", errors)
    check("visionPreviewTimer" in web_text and "syncVisionPreviewTimer" in web_text, "Vision live-preview timer installed", errors)
    check("/api/test_idle_life_action" in web_text and "/api/reset_idle_life_timer" in web_text, "Idle Life API routes installed", errors)
    check("qwen2.5vl:7b" in main_text and "active chat model appears not to accept images" in main_text, "clear desktop vision-model diagnostic installed", errors)
    check("vosk_model_tier" in main_text and "INSTALL_BX1_BETTER_STT_MODEL.sh" in web_text, "improved STT model guidance installed", errors)
    check("stt_pre_roll_ms: int = 700" in audio_text, "audio engine default pre-roll updated", errors)

    python_bin = project / ".venv/bin/python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    compile_files = [str(p) for p in required[:4]] + [str(project / "tools/migrate_v10_28_config.py")]
    result = subprocess.run([str(python_bin), "-m", "py_compile", *compile_files], text=True, capture_output=True)
    check(result.returncode == 0, "Python files compile", errors)
    if result.returncode != 0:
        print(result.stderr)

    # Syntax-check the embedded browser JavaScript when Node is available.
    node = subprocess.run(["bash", "-lc", "command -v node || true"], text=True, capture_output=True).stdout.strip()
    if node:
        script_match = re.search(r"<script>(.*?)</script>", web_text, re.S)
        if script_match:
            with tempfile.TemporaryDirectory() as tmp:
                js = Path(tmp) / "web_control.js"
                js.write_text(script_match.group(1), encoding="utf-8")
                js_check = subprocess.run([node, "--check", str(js)], text=True, capture_output=True)
                check(js_check.returncode == 0, "embedded browser JavaScript parses", errors)
                if js_check.returncode != 0:
                    print(js_check.stderr)
        else:
            check(False, "embedded browser JavaScript found", errors)

    # Prove migration preserves site-specific values while updating old defaults.
    with tempfile.TemporaryDirectory() as tmp:
        temp_project = Path(tmp) / "project"
        (temp_project / "python").mkdir(parents=True)
        temp_cfg = temp_project / "python/config.json"
        original = {
            "brain_base_url": "http://192.168.68.53:8765",
            "mic_device": "plughw:0,0",
            "wake_words": ["hello", "hey", "robot"],
            "stt_pre_roll_ms": 450,
            "audio_noise_reduction_strength": 0.45,
            "hardware_registry": {"servos": {
                "head_yaw": {"pin": 9, "home_deg": 3.5, "invert": True},
                "gimbal_left": {"pin": 10, "home_deg": -2.0},
                "gimbal_right": {"pin": 11, "home_deg": 1.25},
            }},
        }
        temp_cfg.write_text(json.dumps(original), encoding="utf-8")
        migrate = project / "tools/migrate_v10_28_config.py"
        defaults = project / "python/config.v10.28.defaults.json"
        cmd = [str(python_bin), str(migrate), str(temp_cfg)]
        if defaults.exists():
            cmd += ["--defaults", str(defaults)]
        migrated = subprocess.run(cmd, text=True, capture_output=True)
        check(migrated.returncode == 0, "configuration migration executes", errors)
        if migrated.returncode == 0:
            test_cfg = json.loads(temp_cfg.read_text(encoding="utf-8"))
            test_servos = ((test_cfg.get("hardware_registry") or {}).get("servos") or {})
            check(test_cfg.get("brain_base_url") == original["brain_base_url"], "migration preserves Brain URL", errors)
            check(test_cfg.get("mic_device") == "plughw:0,0", "migration preserves microphone device", errors)
            check((test_servos.get("head_yaw") or {}).get("home_deg") == 3.5, "migration preserves yaw trim", errors)
            check((test_servos.get("gimbal_left") or {}).get("home_deg") == -2.0, "migration preserves left gimbal trim", errors)
            check((test_servos.get("gimbal_right") or {}).get("home_deg") == 1.25, "migration preserves right gimbal trim", errors)
            check(test_cfg.get("version") == VERSION, "migration writes v10.28", errors)
            check(test_cfg.get("stt_pre_roll_ms") == 700, "migration upgrades old STT pre-roll default", errors)
            check(test_cfg.get("audio_noise_reduction_strength") == 0.20, "migration upgrades old noise-reduction default", errors)

    if errors:
        print(f"\nVALIDATION FAILED: {len(errors)} problem(s)")
        return 1
    print("\nVALIDATION PASSED: BX1 v10.28 integrated interaction update is internally consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
