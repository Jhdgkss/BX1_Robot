#!/usr/bin/env python3
"""Focused offline checks for the web Brain connection save path."""
from __future__ import annotations

import argparse
import ast
import json
import re
import tempfile
import types
from pathlib import Path
from urllib.parse import urlparse


def normalise_brain_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Brain App URL/IP cannot be empty.")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Brain App URL must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("Brain App URL must include an IP address or hostname.")
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 8765}"


class FakeRobotService:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.cfg = {
            "brain_base_url": "http://192.168.68.50:8757",
            "brain_tts_base_url": "http://192.168.68.50:8765",
            "brain_tts_follow_brain_host": True,
            "api_key": "keep-secret",
            "mic_device": "keep-mic",
            "servo_trim": {"head_yaw": 2},
        }
        self.brain = types.SimpleNamespace(
            base_url=self.cfg["brain_base_url"],
            cfg=types.SimpleNamespace(base_url=self.cfg["brain_base_url"], api_key=self.cfg["api_key"]),
        )
        self.events = []

    def web_log(self, kind: str, message: str, data=None) -> None:
        self.events.append({"kind": kind, "message": message, "data": data or {}})

    def normalise_brain_base_url(self, value: str) -> str:
        return normalise_brain_base_url(value)

    def normalise_brain_tts_base_url(self, value: str) -> str:
        return normalise_brain_base_url(value)

    def save_config_file(self) -> None:
        self.config_path.write_text(json.dumps(self.cfg, indent=2) + "\n", encoding="utf-8")

    def apply_brain_connection(self, base_url: str, api_key=None, save: bool = True):
        clean_url = self.normalise_brain_base_url(base_url)
        clean_key = str(self.cfg.get("api_key", "") if api_key is None else api_key)
        self.cfg["brain_base_url"] = clean_url
        self.cfg["api_key"] = clean_key
        self.brain.base_url = clean_url.rstrip("/")
        self.brain.cfg.base_url = clean_url.rstrip("/")
        self.brain.cfg.api_key = clean_key
        if save:
            self.save_config_file()
        return self.get_brain_settings()

    def get_brain_settings(self):
        return {
            "base_url": self.cfg.get("brain_base_url", self.brain.base_url),
            "brain_tts_base_url": self.cfg.get("brain_tts_base_url", ""),
            "api_key_set": bool(self.cfg.get("api_key", "").strip()),
        }

    def web_update_brain_settings(self, data, client_ip=None):
        use_browser_ip = bool(data.get("use_browser_client_ip", False))
        sync_tts = bool(data.get("sync_tts_to_brain_host", use_browser_ip))
        api_key = str(data.get("api_key", self.cfg.get("api_key", "")))
        if use_browser_ip:
            if not client_ip:
                return {"ok": False, "error": "Browser client IP was not available."}
            port = str(data.get("brain_port", "8765") or "8765").strip()
            base_url = f"http://{client_ip}:{port}"
        else:
            base_url = str(data.get("brain_base_url", "") or data.get("base_url", "")).strip()
        try:
            settings = self.apply_brain_connection(base_url, api_key=api_key, save=False)
            if sync_tts:
                self.cfg["brain_tts_base_url"] = self.normalise_brain_tts_base_url(settings["base_url"])
                self.cfg["brain_tts_follow_brain_host"] = True
            self.save_config_file()
            settings = self.get_brain_settings()
        except Exception as exc:
            failure = {
                "requested_base_url": base_url,
                "use_browser_client_ip": use_browser_ip,
                "config_path": str(self.config_path),
                "error": str(exc),
            }
            self.web_log("error", f"Brain App URL save failed for {base_url or '[empty]'}: {exc}", failure)
            return {"ok": False, **failure}
        self.web_log("system", f"Brain App URL saved: {settings.get('base_url')}")
        return {"ok": True, "brain": settings, "saved_to": str(self.config_path)}


def _function_source(script: str, name: str) -> str:
    pattern = re.compile(rf"((?:async\s+)?function\s+{re.escape(name)}\([^)]*\)\{{)")
    match = pattern.search(script)
    if not match:
        raise AssertionError(f"{name}() was not found")
    start = match.start()
    index = match.end() - 1
    depth = 0
    for pos in range(index, len(script)):
        char = script[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return script[start : pos + 1]
    raise AssertionError(f"{name}() body was not closed")


def run(project: Path) -> None:
    web_path = project / "python" / "web_control.py"
    main_path = project / "python" / "main.py"

    web_text = web_path.read_text(encoding="utf-8")
    main_text = main_path.read_text(encoding="utf-8")

    ast.parse(main_text, filename=str(main_path))
    ast.parse(web_text, filename=str(web_path))

    render_advanced = _function_source(web_text, "renderAdvanced")
    assert "setValueIfClean('brainUrl'" in render_advanced, "Brain URL render must not overwrite a dirty input"
    assert "$('brainUrl').value=(d.brain||{}).base_url" not in render_advanced, "Brain URL render still force-overwrites the field"

    save_brain = _function_source(web_text, "saveBrain")
    assert "brain_base_url:requested" in save_brain, "Save must send the authoritative brain_base_url key"
    assert "base_url:requested" in save_brain, "Save must keep base_url compatibility for older handlers"
    assert "delete $('brainUrl').dataset.dirty" in save_brain, "Save must clear the dirty state only after success"
    assert "$('brainResult').textContent=e.message" in save_brain, "Save errors must be displayed in the browser"

    assert '"brain_base_url"' in main_text, "Backend must read/write brain_base_url"
    assert 'data.get("brain_base_url", "") or data.get("base_url", "")' in main_text, "Backend must accept canonical and compatibility keys"
    assert 'self.cfg["brain_base_url"] = clean_url' in main_text, "Backend must persist the normalised Brain URL"
    assert 'self.brain.base_url = clean_url.rstrip("/")' in main_text, "Backend must update the active Brain runtime client"
    assert 'port = parsed.port or 8765' in main_text, "Bare host/IP entries must normalise to the Brain API port"
    assert "requested_base_url" in main_text and "config_path" in main_text, "Failed saves must include useful diagnostics"

    config_path = project / "python" / "config.json"
    assert config_path.exists(), "Authoritative robot config file is missing"

    assert normalise_brain_base_url("192.168.68.52") == "http://192.168.68.52:8765"
    assert normalise_brain_base_url("http://192.168.68.52:8765") == "http://192.168.68.52:8765"

    with tempfile.TemporaryDirectory() as tmp:
        fake_config = Path(tmp) / "config.json"
        service = FakeRobotService(fake_config)
        original_mic = service.cfg["mic_device"]
        original_servo = dict(service.cfg["servo_trim"])
        result = service.web_update_brain_settings(
            {"brain_base_url": "192.168.68.52", "sync_tts_to_brain_host": True}
        )
        assert result["ok"] is True
        assert result["brain"]["base_url"] == "http://192.168.68.52:8765"
        assert service.get_brain_settings()["base_url"] == "http://192.168.68.52:8765"
        assert service.brain.base_url == "http://192.168.68.52:8765"
        reloaded = json.loads(fake_config.read_text(encoding="utf-8"))
        assert reloaded["brain_base_url"] == "http://192.168.68.52:8765"
        assert reloaded["brain_tts_base_url"] == "http://192.168.68.52:8765"
        assert reloaded["mic_device"] == original_mic
        assert reloaded["servo_trim"] == original_servo

        failed = service.web_update_brain_settings({"brain_base_url": "ftp://192.168.68.52"})
        assert failed["ok"] is False
        assert failed["requested_base_url"] == "ftp://192.168.68.52"
        assert "error" in failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    run(args.project_root.resolve())
    print("Brain connection settings checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
