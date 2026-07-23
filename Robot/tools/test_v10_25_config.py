#!/usr/bin/env python3
"""Static release checks for BX1 body client v10.25."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import tempfile
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def duplicate_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    duplicates: list[str] = []

    def inspect(body: list[ast.stmt], scope: str) -> None:
        seen: set[str] = set()
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in seen:
                    duplicates.append(scope + node.name)
                seen.add(node.name)
            if isinstance(node, ast.ClassDef):
                inspect(node.body, scope + node.name + ".")

    inspect(tree.body, "")
    return duplicates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project.resolve()

    config_path = root / "python" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    require(config.get("version") == "10.25", "config version is not 10.25")
    require(config.get("app_version") == "10.25", "app_version is not 10.25")
    require(config.get("web_enabled") is True, "web interface is not enabled")
    require(config.get("voice_enabled") is True, "live voice is not enabled")
    require(config.get("input_mode") == "both", "keyboard + voice mode is not enabled")
    require([str(x).lower() for x in config.get("wake_words", [])] == ["hello", "hey", "robot"], "natural wake words are not configured")

    registry = config.get("hardware_registry") or {}
    servos = registry.get("servos") or {}
    require(servos.get("head_yaw", {}).get("pin") == 9, "yaw must use D9")
    require(servos.get("gimbal_left", {}).get("pin") == 10, "left gimbal must use D10")
    require(servos.get("gimbal_right", {}).get("pin") == 11, "right gimbal must use D11")
    require(servos.get("head_yaw", {}).get("invert") is True, "yaw reverse must be enabled")
    require(all(servos.get(k, {}).get("enabled") is True for k in ("head_yaw", "gimbal_left", "gimbal_right")), "head servos must be enabled")
    bus = (registry.get("led_buses") or {}).get("main") or {}
    require(bus.get("enabled") is True, "main LED chain must be enabled")
    require(1 <= int(bus.get("total_pixels", 0)) <= 500, "LED count must be 1..500")

    main_source = (root / "python" / "main.py").read_text(encoding="utf-8")
    web_source = (root / "python" / "web_control.py").read_text(encoding="utf-8")
    for token in (
        "def start_estimated_remote_speech_animation",
        'self.set_voice_runtime("processing"',
        'self.set_voice_runtime("speaking"',
        "manual_audio_capture_requested.set()",
    ):
        require(token in main_source, f"missing runtime interaction feature: {token}")
    for token in (
        "BX1 Robot Control 10.25",
        'data-page="conversation"',
        "function sendChat",
        "function listenChat",
        "function setNaturalWakeWords",
        "function saveSimpleHardware",
        "servoYawPin",
        "ledBusCount",
        "data-dirty",
        '"/conversation"',
    ):
        require(token in web_source, f"missing web UI feature: {token}")
    require('server_version = "RobotBodyClient/10.25"' in web_source, "web server version mismatch")

    for path in (root / "python").glob("*.py"):
        duplicates = duplicate_functions(path)
        require(not duplicates, f"duplicate function definitions in {path.name}: {duplicates}")

    migration_path = root / "tools" / "migrate_v10_25_config.py"
    spec = importlib.util.spec_from_file_location("bx1_migrate_v10_25", migration_path)
    require(spec is not None and spec.loader is not None, "cannot load migration module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        original = {
            "version": "10.24",
            "brain_base_url": "http://192.168.68.53:8765",
            "mic_device": "plughw:0,0",
            "hardware_registry": {
                "servos": {
                    "head_yaw": {"pin": 5, "home_deg": 2.5, "min_deg": -14, "max_deg": 17},
                    "gimbal_left": {"pin": 6, "home_deg": -1.5},
                    "gimbal_right": {"pin": 9, "home_deg": 3.0},
                },
                "led_buses": {"main": {"enabled": False, "data_pin": 3, "total_pixels": 42, "brightness_limit": 0.4}},
                "led_zones": {"mouth": {"enabled": True, "start": 5, "end": 7}},
            },
        }
        path.write_text(json.dumps(original), encoding="utf-8")
        migrated = module.migrate(path, config_path)
        require(migrated["brain_base_url"] == original["brain_base_url"], "migration erased Brain URL")
        require(migrated["mic_device"] == original["mic_device"], "migration erased microphone")
        s = migrated["hardware_registry"]["servos"]
        require(s["head_yaw"]["home_deg"] == 2.5, "migration erased yaw trim")
        require(s["gimbal_left"]["home_deg"] == -1.5, "migration erased left trim")
        require(s["gimbal_right"]["home_deg"] == 3.0, "migration erased right trim")
        require(migrated["hardware_registry"]["led_buses"]["main"]["total_pixels"] == 42, "migration erased LED count")
        require(migrated["hardware_registry"]["led_zones"]["mouth"]["start"] == 5, "migration erased LED zone")

    print("BX1 v10.25 validation passed")
    print("- keyboard and robot-microphone conversation page present")
    print("- natural wake words and startup listening enabled")
    print("- servo mapping D9/D10/D11 and LED editor present")
    print("- speech/state LED runtime hooks present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
