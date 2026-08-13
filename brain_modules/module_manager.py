"""Loads optional BX1 Brain modules listed in brain_modules/modules.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading


class BrainModuleManager:
    def __init__(self, *, registry_path=None, brain_api_url="ws://127.0.0.1:8775"):
        self.project_root = Path(__file__).resolve().parent.parent
        self.registry_path = Path(registry_path) if registry_path else Path(__file__).resolve().parent / "modules.json"
        self.brain_api_url = str(brain_api_url)
        self._processes = {}
        self._lock = threading.RLock()

    def load_registry(self):
        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        modules = data.get("modules", [])
        if not isinstance(modules, list):
            raise ValueError("brain_modules/modules.json: modules must be a list")
        clean = []
        seen = set()
        for item in modules:
            if not isinstance(item, dict):
                continue
            module_id = str(item.get("id") or item.get("name") or "").strip()
            filename = str(item.get("file") or "").strip()
            if not module_id or not filename:
                continue
            if module_id.lower() in seen:
                raise ValueError(f"Duplicate module id: {module_id}")
            seen.add(module_id.lower())
            clean.append({**item, "id": module_id, "file": filename,
                          "enabled": bool(item.get("enabled", False)),
                          "autostart": bool(item.get("autostart", False))})
        return clean

    def _definition(self, module_id):
        wanted = str(module_id).strip().lower()
        for item in self.load_registry():
            if item["id"].lower() == wanted:
                return item
        raise KeyError(f"Unknown Brain module: {module_id}")

    def _script_path(self, filename):
        root = self.project_root.resolve()
        path = (root / filename).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Module file must remain inside the BX1 project") from exc
        if not path.is_file():
            raise FileNotFoundError(f"Module script not found: {path}")
        return path

    def start_autostart_modules(self):
        modules = self.load_registry()
        started = 0
        for item in modules:
            if item["enabled"] and item["autostart"]:
                try:
                    if self.start_module(item["id"]):
                        started += 1
                except Exception as exc:
                    print(f"[BRAIN MODULES] {item['id']} failed to start: {type(exc).__name__}: {exc}")
        print(f"[BRAIN MODULES] Registry loaded: {len(modules)} module(s), {started} autostarted.")

    def start_module(self, module_id):
        item = self._definition(module_id)
        if not item["enabled"]:
            raise PermissionError(f"Module '{item['id']}' is disabled in modules.json")
        path = self._script_path(item["file"])
        with self._lock:
            old = self._processes.get(item["id"])
            if old is not None and old.poll() is None:
                return False
            env = os.environ.copy()
            env["BX1_BRAIN_API_URL"] = self.brain_api_url
            env["BX1_PROJECT_ROOT"] = str(self.project_root)
            env["BX1_MODULE_ID"] = item["id"]
            proc = subprocess.Popen([sys.executable, str(path)], cwd=str(self.project_root), env=env)
            self._processes[item["id"]] = proc
        print(f"[BRAIN MODULES] Started {item['id']} (pid {proc.pid})")
        return True

    def stop_module(self, module_id, timeout=2.0):
        module_id = str(module_id)
        with self._lock:
            proc = self._processes.get(module_id)
        if proc is None:
            return False
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=float(timeout))
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=1.0)
        with self._lock:
            self._processes.pop(module_id, None)
        return True

    def stop_all(self):
        with self._lock:
            names = list(self._processes)
        for name in names:
            try:
                self.stop_module(name)
            except Exception as exc:
                print(f"[BRAIN MODULES] Stop error for {name}: {type(exc).__name__}: {exc}")
