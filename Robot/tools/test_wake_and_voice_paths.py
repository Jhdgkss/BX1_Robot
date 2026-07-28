#!/usr/bin/env python3
"""Offline checks for BX1 wake diagnostics and Brain-owned forced speech."""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


def require(text: str, needle: str, message: str) -> None:
    if needle not in text:
        raise AssertionError(message)


def function_source(text: str, name: str) -> str:
    pattern = re.compile(rf"def\s+{re.escape(name)}\([^)]*\).*?:")
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"{name}() was not found")
    start = match.start()
    next_match = re.search(r"\n    def\s+|\nclass\s+", text[match.end():])
    if not next_match:
        return text[start:]
    return text[start : match.end() + next_match.start()]


def run(root: Path) -> None:
    robot_main_path = root / "Robot" / "python" / "main.py"
    robot_audio_path = root / "Robot" / "python" / "audio_io.py"
    brain_main_path = root / "Brain" / "main_pyqt.py"

    robot_main = robot_main_path.read_text(encoding="utf-8")
    robot_audio = robot_audio_path.read_text(encoding="utf-8")
    brain_main = brain_main_path.read_text(encoding="utf-8")

    ast.parse(robot_main, filename=str(robot_main_path))
    ast.parse(robot_audio, filename=str(robot_audio_path))
    ast.parse(brain_main, filename=str(brain_main_path))

    wake_diag = function_source(robot_main, "build_wake_diagnostics")
    for key in (
        "listener_state",
        "audio_device",
        "rms_dbfs",
        "peak_dbfs",
        "gate_open",
        "recognized_text",
        "recognition_confidence",
        "wake_match_score",
        "cooldown_remaining_s",
        "tts_speaking_lockout",
    ):
        require(wake_diag, key, f"wake diagnostics missing {key}")
    require(robot_main, "last_wake_diagnostics", "runtime snapshot must retain the last wake diagnostic packet")
    require(robot_main, "stt_guard_remaining_s", "runtime snapshot must expose wake/TTS guard remaining time")
    require(robot_main, "speech_output_active", "runtime snapshot must expose TTS lockout state")
    require(robot_main, "log_wake_diagnostics(diagnostics)", "wake decisions must be logged")
    require(robot_main, "wake_fuzzy_threshold", "wake phrase matching must still use configured fuzzy threshold")
    require(robot_main, 'metrics.update({\n                        "stt_gate_override": "wake_phrase"', "wake phrases must be able to bypass only the STT rejection gate")

    web_test = function_source(robot_main, "web_test_speech")
    require(web_test, 'tts_cfg.tts_backend = "brain-tts"', "Robot web speech test must prefer Brain TTS when configured")
    require(web_test, "tts_cfg.brain_tts_use_brain_defaults = True", "Robot web speech test must inherit Brain selected voice")
    require(web_test, "self.tts.update_config(old_tts_cfg)", "Robot web speech test must restore unrelated TTS configuration")
    require(web_test, "forced_brain_voice_defaults", "Robot web speech test must report whether Brain defaults were used")

    brain_request = function_source(robot_audio, "_request_brain_tts_audio")
    require(brain_request, '"voice_owner": "brain_app"', "Robot request must identify Brain as voice owner")
    require(brain_request, "if not bool(getattr(self.cfg, \"brain_tts_use_brain_defaults\", True))", "Robot must omit voice overrides by default")
    require(brain_request, "effective_engine", "Robot must capture effective Brain engine metadata")
    require(brain_request, "effective_voice", "Robot must capture effective Brain voice metadata")
    require(brain_request, "fallback_reason", "Robot must capture Brain fallback reason")

    api_handler = brain_main[brain_main.find('if parsed.path in {"/api/tts", "/robot/speak"}'):]
    require(api_handler, "requested_engine=str(body.get(\"engine\") or \"\")", "Brain API must accept explicit engine override")
    require(api_handler, "requested_voice=str(body.get(\"voice\") or \"\")", "Brain API must accept explicit voice override")
    generate = function_source(brain_main, "generate_tts_audio_for_robot")
    require(generate, "effective_engine", "Brain TTS response must include effective engine")
    require(generate, "effective_voice", "Brain TTS response must include effective voice")
    require(generate, "fallback_reason", "Brain TTS response must include fallback reason")
    require(generate, "request_source", "Brain TTS response must include request source")
    require(generate, "_edge_audio_for_robot", "Brain TTS must keep clear fallback when Dot.TTS is unavailable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    run(args.repo_root.resolve())
    print("Wake and forced voice path checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
