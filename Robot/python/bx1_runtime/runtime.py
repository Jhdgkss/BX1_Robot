from __future__ import annotations

import importlib.util
import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Mapping, Optional


FORBIDDEN_CAPABILITY_TERMS = ("motor", "balance", "mcu", "servo", "camera", "gpio", "drive")
SAFE_CAPABILITIES = {"events.publish", "events.subscribe"}


@dataclass(frozen=True)
class ModuleManifest:
    identifier: str
    name: str
    version: str
    entrypoint: str
    capabilities: tuple[str, ...]
    subscriptions: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "ModuleManifest":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema") != "bx1.module.manifest.v1":
            raise ValueError("manifest must use bx1.module.manifest.v1")
        required = ("id", "name", "version", "entrypoint")
        if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required):
            raise ValueError("manifest is missing a required string field")
        identifier = value["id"].strip()
        if not identifier.replace("_", "").replace("-", "").isalnum() or identifier != identifier.lower():
            raise ValueError("module id must be lowercase alphanumeric, _ or -")
        capabilities = tuple(str(item) for item in value.get("capabilities", []))
        subscriptions = tuple(str(item) for item in value.get("subscriptions", []))
        if any(cap not in SAFE_CAPABILITIES or any(term in cap for term in FORBIDDEN_CAPABILITY_TERMS) for cap in capabilities):
            raise ValueError("manifest requests an unsupported or hardware capability")
        if any(not item or len(item) > 80 for item in subscriptions):
            raise ValueError("manifest contains an invalid subscription")
        return cls(identifier, value["name"].strip(), value["version"].strip(), value["entrypoint"].strip(), capabilities, subscriptions)


class RuntimeEventBus:
    """Bounded in-process event bus. Overflow drops the oldest undelivered event."""

    def __init__(self, limit: int = 128, clock: Callable[[], float] = time.time) -> None:
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max(1, int(limit)))
        self._subscribers: Dict[str, list[Callable[[Mapping[str, Any]], None]]] = {}
        self._limit, self._clock, self.dropped = max(1, int(limit)), clock, 0

    def publish(self, topic: str, payload: Mapping[str, Any], source: str) -> None:
        if not topic or len(topic) > 80 or not isinstance(payload, Mapping):
            raise ValueError("invalid runtime event")
        if len(self._events) == self._limit:
            self.dropped += 1
        event = {"topic": str(topic), "payload": dict(payload), "source": str(source), "timestamp": self._clock()}
        self._events.append(event)
        for callback in tuple(self._subscribers.get(event["topic"], [])) + tuple(self._subscribers.get("*", [])):
            try:
                callback(event)
            except Exception:
                pass

    def subscribe(self, topic: str, callback: Callable[[Mapping[str, Any]], None]) -> None:
        self._subscribers.setdefault(topic, []).append(callback)

    def diagnostics(self) -> Dict[str, Any]:
        return {"queue_limit": self._limit, "queued": len(self._events), "dropped": self.dropped, "subscriber_count": sum(map(len, self._subscribers.values()))}


class ModuleContext:
    def __init__(self, manifest: ModuleManifest, events: RuntimeEventBus) -> None:
        self._manifest, self._events = manifest, events

    def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        if "events.publish" not in self._manifest.capabilities:
            raise PermissionError("module lacks events.publish")
        self._events.publish(topic, payload, self._manifest.identifier)

    def subscribe(self, topic: str, callback: Callable[[Mapping[str, Any]], None]) -> None:
        if "events.subscribe" not in self._manifest.capabilities or topic not in self._manifest.subscriptions:
            raise PermissionError("module subscription is not declared")
        self._events.subscribe(topic, callback)


class ModuleManager:
    """Manifest-first loader with bounded, fail-contained module lifecycle."""

    def __init__(self, modules_root: Path, *, event_limit: int = 128) -> None:
        self.modules_root = Path(modules_root)
        self.events = RuntimeEventBus(event_limit)
        self._modules: Dict[str, Dict[str, Any]] = {}

    def load_all(self) -> None:
        if not self.modules_root.is_dir():
            return
        for manifest_path in sorted(self.modules_root.glob("*/module.json")):
            self._load(manifest_path)

    def _load(self, manifest_path: Path) -> None:
        manifest: Optional[ModuleManifest] = None
        try:
            manifest = ModuleManifest.load(manifest_path)
            if manifest.identifier in self._modules:
                raise ValueError("duplicate module id")
            module_file, sep, class_name = manifest.entrypoint.partition(":")
            target = (manifest_path.parent / module_file).resolve()
            if not sep or not class_name or manifest_path.parent.resolve() not in target.parents or target.suffix != ".py":
                raise ValueError("entrypoint must be a local module.py:Class")
            spec = importlib.util.spec_from_file_location("bx1_module_" + manifest.identifier, target)
            if spec is None or spec.loader is None:
                raise ValueError("entrypoint could not be loaded")
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
            instance = getattr(loaded, class_name)()
            context = ModuleContext(manifest, self.events)
            instance.start(context)
            self._modules[manifest.identifier] = {"manifest": manifest, "instance": instance, "state": "healthy", "detail": "started", "started_at": time.time()}
        except Exception as exc:
            identifier = manifest.identifier if manifest else manifest_path.parent.name
            self._modules[identifier] = {"manifest": manifest, "instance": None, "state": "fault", "detail": str(exc), "started_at": None}

    def snapshot(self) -> Dict[str, Any]:
        items = []
        for identifier, record in sorted(self._modules.items()):
            manifest = record["manifest"]
            health = {}
            if record["instance"] is not None:
                try:
                    health = dict(record["instance"].health())
                except Exception as exc:
                    record["state"], record["detail"] = "fault", str(exc)
            items.append({"id": identifier, "name": manifest.name if manifest else identifier, "version": manifest.version if manifest else "unknown", "capabilities": list(manifest.capabilities) if manifest else [], "subscriptions": list(manifest.subscriptions) if manifest else [], "state": record["state"], "detail": record["detail"], "health": health, "started_at": record["started_at"]})
        return {"schema": "bx1.runtime.modules.v1", "modules": items, "event_bus": self.events.diagnostics()}

    def stop(self) -> None:
        for record in self._modules.values():
            if record["instance"] is not None:
                try:
                    record["instance"].stop()
                except Exception:
                    record["state"] = "fault"
