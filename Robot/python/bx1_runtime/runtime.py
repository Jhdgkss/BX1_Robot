from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import time
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Mapping, Optional

FORBIDDEN_CAPABILITY_TERMS = ("motor", "balance", "mcu", "servo", "camera", "gpio", "drive", "wheel", "shell")
SAFE_CAPABILITIES = {"events.publish", "events.subscribe", "widgets.publish", "widgets.action", "led.status.request"}
WIDGET_TYPES = {"metric", "panel", "chart", "button", "form"}


@dataclass(frozen=True)
class ModuleManifest:
    identifier: str; name: str; version: str; entrypoint: str; capabilities: tuple[str, ...]; subscriptions: tuple[str, ...]
    @classmethod
    def load(cls, path: Path) -> "ModuleManifest":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema") != "bx1.module.manifest.v1": raise ValueError("manifest must use bx1.module.manifest.v1")
        required = ("id", "name", "version", "entrypoint")
        if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required): raise ValueError("manifest is missing a required string field")
        identifier = value["id"].strip()
        if not identifier.replace("_", "").replace("-", "").isalnum() or identifier != identifier.lower(): raise ValueError("module id must be lowercase alphanumeric, _ or -")
        capabilities, subscriptions = tuple(map(str, value.get("capabilities", []))), tuple(map(str, value.get("subscriptions", [])))
        if any(cap not in SAFE_CAPABILITIES or any(term in cap for term in FORBIDDEN_CAPABILITY_TERMS) for cap in capabilities): raise ValueError("manifest requests an unsupported or hardware capability")
        if any(not item or len(item) > 80 for item in subscriptions): raise ValueError("manifest contains an invalid subscription")
        return cls(identifier, value["name"].strip(), value["version"].strip(), value["entrypoint"].strip(), capabilities, subscriptions)


class RuntimeEventBus:
    def __init__(self, limit: int = 128, clock: Callable[[], float] = time.time) -> None:
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max(1, int(limit))); self._subscribers: Dict[str, list] = {}; self._limit, self._clock, self.dropped = max(1, int(limit)), clock, 0
    def publish(self, topic: str, payload: Mapping[str, Any], source: str) -> None:
        if not topic or len(topic) > 80 or not isinstance(payload, Mapping): raise ValueError("invalid runtime event")
        if len(self._events) == self._limit: self.dropped += 1
        event = {"topic": str(topic), "payload": dict(payload), "source": str(source), "timestamp": self._clock()}; self._events.append(event)
        for callback in tuple(self._subscribers.get(event["topic"], [])) + tuple(self._subscribers.get("*", [])):
            try: callback(event)
            except Exception: pass
    def subscribe(self, topic: str, callback: Callable[[Mapping[str, Any]], None]) -> None: self._subscribers.setdefault(topic, []).append(callback)
    def diagnostics(self) -> Dict[str, Any]: return {"queue_limit": self._limit, "queued": len(self._events), "dropped": self.dropped, "subscriber_count": sum(map(len, self._subscribers.values()))}


class WidgetStore:
    """Declarative, bounded widgets only; no module-provided browser code is accepted."""
    def __init__(self) -> None: self._widgets: Dict[str, Dict[str, Any]] = {}
    def publish(self, module_id: str, value: Mapping[str, Any]) -> str:
        item = dict(value); widget_id = str(item.get("id") or "").strip(); kind = str(item.get("type") or "")
        if not widget_id or len(widget_id) > 64 or kind not in WIDGET_TYPES: raise ValueError("invalid_widget")
        if item.get("module_id") not in {None, module_id}: raise PermissionError("widget owner mismatch")
        title, placement = str(item.get("title") or "").strip(), str(item.get("placement") or "dashboard")
        if not title or len(title) > 100 or placement not in {"dashboard", "modules"}: raise ValueError("invalid_widget_metadata")
        data = item.get("data", {})
        if not isinstance(data, Mapping) or len(json.dumps(data, sort_keys=True)) > 8192: raise ValueError("widget_data_too_large")
        if kind == "chart":
            points = data.get("points", []);
            if not isinstance(points, list) or len(points) > 60 or any(not isinstance(v, (int, float)) for v in points): raise ValueError("invalid_chart_points")
        if kind == "form":
            fields = data.get("fields", []);
            if not isinstance(fields, list) or len(fields) > 6: raise ValueError("invalid_form_fields")
            for field in fields:
                if not isinstance(field, Mapping) or not str(field.get("name") or "").replace("_", "").isalnum() or len(str(field.get("name"))) > 32: raise ValueError("invalid_form_field")
        item.update({"id": widget_id, "module_id": module_id, "type": kind, "title": title, "placement": placement, "health": str(item.get("health") or "healthy"), "data": dict(data)})
        self._widgets[module_id + ":" + widget_id] = item; return widget_id
    def remove_module(self, module_id: str) -> None:
        for key in [key for key, value in self._widgets.items() if value["module_id"] == module_id]: self._widgets.pop(key, None)
    def snapshot(self, module_states: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
        values = []
        for item in self._widgets.values():
            copy = dict(item); record = module_states.get(item["module_id"], {}); copy["module_state"] = record.get("state", "fault")
            if copy["module_state"] == "fault": copy["health"] = "fault"; copy["fault"] = record.get("detail", "module unavailable")
            values.append(copy)
        return {"schema": "bx1.runtime.widgets.v1", "widgets": sorted(values, key=lambda item: (item["placement"], item["module_id"], item["id"]))}


class ModuleContext:
    def __init__(self, manifest: ModuleManifest, events: RuntimeEventBus, widgets: WidgetStore, actions: Dict[str, Callable], led_request: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None: self._manifest, self._events, self._widgets, self._actions, self._led_request = manifest, events, widgets, actions, led_request
    def _allow(self, capability: str) -> None:
        if capability not in self._manifest.capabilities: raise PermissionError("module lacks " + capability)
    def publish(self, topic: str, payload: Mapping[str, Any]) -> None: self._allow("events.publish"); self._events.publish(topic, payload, self._manifest.identifier)
    def subscribe(self, topic: str, callback: Callable[[Mapping[str, Any]], None]) -> None:
        self._allow("events.subscribe")
        if topic not in self._manifest.subscriptions: raise PermissionError("module subscription is not declared")
        self._events.subscribe(topic, callback)
    def widget(self, value: Mapping[str, Any]) -> str: self._allow("widgets.publish"); return self._widgets.publish(self._manifest.identifier, value)
    def action(self, name: str, callback: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        self._allow("widgets.action")
        if not name.replace("_", "").isalnum() or len(name) > 40: raise ValueError("invalid_action_name")
        self._actions[name] = callback
    def led_status_request(self, *, target: str, colour: str, effect: str = "solid") -> Mapping[str, Any]:
        self._allow("led.status.request")
        if target not in {"status"} or colour not in {"green", "amber", "red", "blue", "off"} or effect not in {"solid", "pulse", "off"}: raise ValueError("invalid_led_status_request")
        return self._led_request({"target": target, "colour": colour, "effect": effect, "module_id": self._manifest.identifier})


class ModuleManager:
    def __init__(self, modules_root: Path, *, persistent_root: Optional[Path] = None, event_limit: int = 128, led_request: Optional[Callable[[Mapping[str, Any]], Mapping[str, Any]]] = None) -> None:
        self.modules_root, self.persistent_root = Path(modules_root), Path(persistent_root or "/home/arduino/BX1_modules")
        self.events, self.widgets, self._modules = RuntimeEventBus(event_limit), WidgetStore(), {}
        self._led_request = led_request or (lambda _: {"ok": False, "state": "unavailable", "reason": "Body LED capability unavailable"})
    @property
    def _state_path(self) -> Path: return self.persistent_root / ".bx1-runtime.json"
    def _preferences(self) -> Dict[str, Any]:
        try: return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {"disabled": []}
    def _save_preferences(self, value: Mapping[str, Any]) -> None:
        self.persistent_root.mkdir(parents=True, exist_ok=True); temp = self._state_path.with_suffix(".tmp"); temp.write_text(json.dumps(dict(value), sort_keys=True) + "\n", encoding="utf-8"); os.replace(temp, self._state_path)
    def load_all(self) -> None:
        disabled = set(self._preferences().get("disabled", []))
        for root, source in ((self.modules_root, "bundled"), (self.persistent_root, "user")):
            if root.is_dir():
                for path in sorted(root.glob("*/module.json")): self._load(path, source, path.parent.name in disabled)
    def _load(self, manifest_path: Path, source: str, disabled: bool) -> None:
        manifest: Optional[ModuleManifest] = None
        try:
            manifest = ModuleManifest.load(manifest_path)
            if manifest.identifier in self._modules: raise ValueError("duplicate module id")
            if disabled: self._modules[manifest.identifier] = {"manifest": manifest, "instance": None, "state": "disabled", "detail": "disabled by user", "source": source, "actions": {}, "started_at": None}; return
            filename, sep, class_name = manifest.entrypoint.partition(":"); target = (manifest_path.parent / filename).resolve()
            if not sep or not class_name or manifest_path.parent.resolve() not in target.parents or target.suffix != ".py": raise ValueError("entrypoint must be a local module.py:Class")
            spec = importlib.util.spec_from_file_location("bx1_module_" + manifest.identifier, target)
            if spec is None or spec.loader is None: raise ValueError("entrypoint could not be loaded")
            loaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded); instance = getattr(loaded, class_name)(); actions: Dict[str, Callable] = {}
            instance.start(ModuleContext(manifest, self.events, self.widgets, actions, self._led_request))
            self._modules[manifest.identifier] = {"manifest": manifest, "instance": instance, "state": "healthy", "detail": "started", "source": source, "actions": actions, "started_at": time.time()}
        except Exception as exc:
            identifier = manifest.identifier if manifest else manifest_path.parent.name; self._modules[identifier] = {"manifest": manifest, "instance": None, "state": "fault", "detail": str(exc)[:300], "source": source, "actions": {}, "started_at": None}
    def reload(self) -> Dict[str, Any]: self.stop(); self.events, self.widgets, self._modules = RuntimeEventBus(self.events._limit), WidgetStore(), {}; self.load_all(); return self.snapshot()
    def install_zip(self, archive: Path) -> Dict[str, Any]:
        if archive.suffix.lower() != ".zip" or not archive.is_file() or archive.stat().st_size > 2 * 1024 * 1024: raise ValueError("invalid_module_archive")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if not names or len(names) > 32 or any(Path(name).is_absolute() or ".." in Path(name).parts or name.endswith("/") for name in names): raise ValueError("unsafe_module_archive")
            manifests = [name for name in names if Path(name).name == "module.json"]
            if manifests != ["module.json"]: raise ValueError("archive_must_contain_root_module_json")
            with tempfile.TemporaryDirectory(dir=str(self.persistent_root.parent)) as temporary:
                temp = Path(temporary); bundle.extractall(temp); manifest = ModuleManifest.load(temp / "module.json")
                target = self.persistent_root / manifest.identifier; self.persistent_root.mkdir(parents=True, exist_ok=True)
                replacement = self.persistent_root / ("." + manifest.identifier + ".new")
                if replacement.exists(): shutil.rmtree(replacement)
                shutil.copytree(temp, replacement)
                if target.exists(): shutil.rmtree(target)
                os.replace(replacement, target)
        return self.reload()
    def set_enabled(self, identifier: str, enabled: bool) -> Dict[str, Any]:
        record = self._modules.get(identifier)
        if not record or record["source"] != "user": raise ValueError("only_user_modules_can_be_changed")
        preferences = self._preferences(); disabled = set(preferences.get("disabled", [])); disabled.discard(identifier) if enabled else disabled.add(identifier); preferences["disabled"] = sorted(disabled); self._save_preferences(preferences); return self.reload()
    def remove(self, identifier: str) -> Dict[str, Any]:
        record = self._modules.get(identifier)
        if not record or record["source"] != "user": raise ValueError("only_user_modules_can_be_removed")
        target = self.persistent_root / identifier
        if target.is_dir(): shutil.rmtree(target)
        preferences = self._preferences(); preferences["disabled"] = [item for item in preferences.get("disabled", []) if item != identifier]; self._save_preferences(preferences); return self.reload()
    def clear_faults(self) -> Dict[str, Any]:
        for record in self._modules.values():
            if record["state"] == "fault": record["detail"] = "cleared; reload to retry"
        return self.snapshot()
    def invoke_action(self, identifier: str, action: str, fields: Mapping[str, Any]) -> Mapping[str, Any]:
        record = self._modules.get(identifier)
        if not record or record["state"] != "healthy" or action not in record["actions"]: raise PermissionError("module_action_unavailable")
        safe = {str(k)[:32]: str(v)[:256] for k, v in fields.items() if str(k).replace("_", "").isalnum()}
        return dict(record["actions"][action](safe))
    def snapshot(self) -> Dict[str, Any]:
        items=[]
        for identifier, record in sorted(self._modules.items()):
            manifest=record["manifest"]; health={}
            if record["instance"] is not None:
                try: health=dict(record["instance"].health())
                except Exception as exc: record["state"], record["detail"]="fault",str(exc)[:300]
            items.append({"id":identifier,"name":manifest.name if manifest else identifier,"version":manifest.version if manifest else "unknown","capabilities":list(manifest.capabilities) if manifest else [],"subscriptions":list(manifest.subscriptions) if manifest else [],"state":record["state"],"detail":record["detail"],"source":record["source"],"health":health,"started_at":record["started_at"]})
        return {"schema":"bx1.runtime.modules.v1","modules":items,"event_bus":self.events.diagnostics(),"persistent_root":str(self.persistent_root)}
    def widgets_snapshot(self) -> Dict[str, Any]: return self.widgets.snapshot(self._modules)
    def stop(self) -> None:
        for identifier, record in self._modules.items():
            self.widgets.remove_module(identifier)
            if record["instance"] is not None:
                try: record["instance"].stop()
                except Exception: record["state"]="fault"
