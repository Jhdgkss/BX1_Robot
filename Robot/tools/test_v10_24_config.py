#!/usr/bin/env python3
"""Static release checks for BX1 UNO Q body client v10.24."""
from __future__ import annotations

import argparse
import ast
import json
import tempfile
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def duplicate_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    duplicates: list[str] = []

    def inspect_body(body: list[ast.stmt], scope: str) -> None:
        seen: set[str] = set()
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen:
                    duplicates.append(f"{scope}{node.name}")
                seen.add(node.name)
            if isinstance(node, ast.ClassDef):
                inspect_body(node.body, f"{scope}{node.name}.")

    inspect_body(tree.body, "")
    return duplicates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project.resolve()

    config_path = root / "python" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    require(str(config.get("version")) == "10.24", "config version is not 10.24")
    require(str(config.get("app_version")) == "10.24", "app_version is not 10.24")

    ownership_true = (
        "brain_tts_use_brain_defaults",
        "brain_controls_web_memory",
        "brain_controls_thinking_cues",
        "brain_controls_idle_dialogue",
    )
    ownership_false = (
        "thinking_cues_enabled",
        "thinking_cue_speak",
        "voice_command_immediate_cue_enabled",
        "idle_life_self_chatter_enabled",
        "idle_life_internet_curiosity_enabled",
    )
    for key in ownership_true:
        require(config.get(key) is True, f"{key} must be true")
    for key in ownership_false:
        require(config.get(key) is False, f"{key} must be false")

    require(config.get("stt_capture_method") == "alsa", "production STT capture must use ALSA")
    require(config.get("stt_endpointing_enabled") is True, "STT endpointing must be enabled")
    require(int(config.get("stt_pre_roll_ms", 0)) >= 300, "STT pre-roll is too short")
    require(int(config.get("stt_end_silence_ms", 0)) >= 800, "STT end silence is too short")
    require(float(config.get("stt_max_utterance_s", 0)) >= 15, "STT max utterance is too short")

    main_source = (root / "python" / "main.py").read_text(encoding="utf-8")
    audio_source = (root / "python" / "audio_io.py").read_text(encoding="utf-8")
    bridge_source = (root / "python" / "hardware_bridge.py").read_text(encoding="utf-8")
    web_source = (root / "python" / "web_control.py").read_text(encoding="utf-8")
    sketch_source = (root / "sketch" / "sketch.ino").read_text(encoding="utf-8")

    require("def get_control_ownership" in main_source, "ownership status method missing")
    require("brain_controls_web_memory" in main_source, "Brain web/memory guard missing")
    require("brain_controls_idle_dialogue" in main_source, "Brain idle-dialogue guard missing")
    require('backend = "brain-tts"' in main_source, "body audio compatibility endpoint must retain Brain TTS route")
    require('self.cfg["brain_tts_use_brain_defaults"] = True' in main_source, "body audio endpoint must not override Brain voice selection")
    require("PERSONALITY_PRESETS" not in main_source, "body personality presets must be removed")
    require("def _save_personality_controls" not in main_source, "body personality writer must be removed")
    require("def record_microphone_utterance" in audio_source, "endpointed ALSA capture missing")
    for name in ("bx1_stt_last_raw.wav", "bx1_stt_last_filtered.wav", "bx1_stt_last_submitted.wav"):
        require(name in audio_source or name in main_source or name in web_source, f"debug WAV route missing: {name}")

    require('self.call("bx1_set_led_zone"' in bridge_source, "direct mouth/LED RPC missing in Python bridge")
    require("bool bx1_set_led_zone" in sketch_source, "direct mouth/LED RPC missing in MCU sketch")
    require('Bridge.provide("bx1_set_led_zone"' in sketch_source, "direct mouth/LED RPC is not registered")
    require('#define BX1_FIRMWARE_VERSION "10.24"' in sketch_source, "MCU firmware version mismatch")

    require("BX1 Body Diagnostic Console 10.24" in web_source, "v10.24 diagnostic UI missing")
    require("/api/stt_audio/submitted.wav" in web_source, "submitted STT WAV route missing")
    for old_control_id in ("useWeb", "useMemory", "ttsBackend", "brainTtsEngine", "thinkingCuesEnabled", "idleSelfChatter"):
        require(old_control_id not in web_source, f"duplicate Brain-owned web control remains: {old_control_id}")

    for path in (root / "python").glob("*.py"):
        duplicates = duplicate_functions(path)
        require(not duplicates, f"duplicate function definitions in {path.name}: {duplicates}")

    # Verify migration preserves a representative calibrated installation while
    # enforcing the ownership boundary.
    import importlib.util
    migration_path = root / "tools" / "migrate_v10_24_config.py"
    spec = importlib.util.spec_from_file_location("bx1_migrate_v10_24", migration_path)
    require(spec is not None and spec.loader is not None, "cannot load migration module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        test_cfg = Path(tmp) / "config.json"
        original = {
            "version": "10.23",
            "brain_base_url": "http://192.168.68.53:8765",
            "mic_device": "plughw:0,0",
            "hardware_registry": {"servos": {"yaw": {"pin": 9, "trim_us": 32}}},
            "thinking_cues_enabled": True,
        }
        test_cfg.write_text(json.dumps(original), encoding="utf-8")
        migrated = module.migrate(test_cfg, config_path)
        require(migrated["brain_base_url"] == original["brain_base_url"], "migration erased Brain URL")
        require(migrated["mic_device"] == original["mic_device"], "migration erased microphone")
        require(migrated["hardware_registry"] == original["hardware_registry"], "migration erased hardware calibration")
        require(migrated["thinking_cues_enabled"] is False, "migration did not disable duplicate thinking cues")

    print("BX1 v10.24 validation passed")
    print("- STT endpointing/debug evidence present")
    print("- Brain/body ownership boundary enforced")
    print("- direct mouth LED RPC present in Python and MCU")
    print("- diagnostic UI contains no duplicate Brain-owned controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
