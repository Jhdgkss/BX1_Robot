#!/usr/bin/env python3
"""Offline release checks for the BX1 v10.35 body client."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, *, payload=None, body: bytes = b"", status_code: int = 200):
        self.payload = payload or {"ok": True}
        self.body = body
        self.status_code = status_code
        self.text = json.dumps(self.payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=65536):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def run(project: Path) -> None:
    python_dir = project / "python"
    tools_dir = project / "tools"
    if "requests" not in sys.modules:
        try:
            __import__("requests")
        except ModuleNotFoundError:
            requests_stub = types.ModuleType("requests")
            requests_stub.Response = type("Response", (), {})
            requests_stub.get = lambda *args, **kwargs: None
            requests_stub.post = lambda *args, **kwargs: None
            sys.modules["requests"] = requests_stub
    client_module = load_module("bx1_robot_client_release_test", python_dir / "bx1_robot_client.py")
    migration_module = load_module("migrate_v10_35_config_release_test", tools_dir / "migrate_v10_35_config.py")

    captured = {}
    original_post = client_module.requests.post
    original_get = client_module.requests.get
    try:
        def fake_post(url, **kwargs):
            captured["post_url"] = url
            captured["post_json"] = kwargs.get("json")
            return FakeResponse(payload={"ok": True, "reply": "hello"})

        client_module.requests.post = fake_post
        client = client_module.BX1BrainClient(
            client_module.BrainClientConfig(base_url="http://192.0.2.10:8765", api_key="secret")
        )
        client.chat("BX1", "hello")
        assert captured["post_url"].endswith("/api/chat")
        assert captured["post_json"]["return_audio"] is True
        assert captured["post_json"]["speak"] is False
        assert captured["post_json"]["source"] == "robot_body"

        def fake_get(url, **kwargs):
            captured["get_url"] = url
            captured["get_headers"] = kwargs.get("headers")
            return FakeResponse(body=b"RIFF" + (b"\0" * 2048))

        client_module.requests.get = fake_get
        downloaded = client.download_response_audio({"audio": {"relative_audio_url": "/api/audio/test.wav"}})
        try:
            assert downloaded.stat().st_size > 1000
            assert captured["get_url"] == "http://192.0.2.10:8765/api/audio/test.wav"
            assert captured["get_headers"]["X-BX1-API-Key"] == "secret"
        finally:
            downloaded.unlink(missing_ok=True)
    finally:
        client_module.requests.post = original_post
        client_module.requests.get = original_get

    old = {
        "version": "10.34.2",
        "brain_base_url": "192.0.2.20:8765",
        "tts_backend": "brain-tts",
        "hardware_map": {"head_yaw": {"pin": 9}},
        "custom_user_key": "keep-me",
    }
    migrated, report = migration_module.migrate_config(old)
    assert report["to_version"] == "10.35"
    assert migrated["brain_response_audio_enabled"] is True
    assert migrated["brain_tts_base_url"] == "http://192.0.2.20:8765"
    assert migrated["brain_tts_endpoint"] == "/api/tts"
    assert migrated["tts_backend"] == "edge-tts"
    assert migrated["chat_timeout_s"] >= 480
    assert migrated["hardware_map"] == old["hardware_map"]
    assert migrated["custom_user_key"] == "keep-me"

    for path in sorted(project.rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    forbidden = ("chatter" + "box", "80" + "91")
    for path in sorted(project.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".py", ".json", ".md", ".txt", ".yaml", ".yml", ".sh", ".service"}:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            for word in forbidden:
                assert word not in text, f"obsolete voice reference {word!r} in {path}"

    example = json.loads((python_dir / "config.example.json").read_text(encoding="utf-8"))
    fresh = json.loads((python_dir / "config.fresh.json").read_text(encoding="utf-8"))
    for config in (example, fresh):
        assert config["version"] == "10.35"
        assert config["brain_response_audio_enabled"] is True
        assert config["brain_tts_endpoint"] == "/api/tts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    run(args.project_root.resolve())
    print("BX1 v10.35 release checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
