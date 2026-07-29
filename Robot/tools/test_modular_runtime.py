#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from bx1_runtime import ModuleManager, RuntimeEventBus  # noqa: E402
from bx1_runtime.runtime import ModuleManifest  # noqa: E402


class ModularRuntimeTests(unittest.TestCase):
    def test_example_loads_without_hardware_capabilities(self):
        manager = ModuleManager(ROOT / "modules")
        manager.load_all()
        snapshot = manager.snapshot()
        module = next(item for item in snapshot["modules"] if item["id"] == "speech_indicator")
        self.assertEqual(module["id"], "speech_indicator")
        self.assertEqual(module["state"], "healthy")
        self.assertNotIn("camera", " ".join(module["capabilities"]))
        manager.events.publish("speech.started", {}, "test")
        self.assertTrue(module["health"]["active"] is False)  # snapshot is immutable evidence
        self.assertGreaterEqual(manager.snapshot()["event_bus"]["queued"], 2)
        manager.stop()

    def test_hardware_capability_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.json"
            path.write_text(json.dumps({"schema": "bx1.module.manifest.v1", "id": "unsafe", "name": "Unsafe", "version": "1", "entrypoint": "module.py:Module", "capabilities": ["camera.raw"], "subscriptions": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                ModuleManifest.load(path)

    def test_event_bus_is_bounded(self):
        events = RuntimeEventBus(limit=2)
        for number in range(3):
            events.publish("test", {"number": number}, "unit")
        self.assertEqual(events.diagnostics()["queued"], 2)
        self.assertEqual(events.diagnostics()["dropped"], 1)


if __name__ == "__main__":
    unittest.main()
