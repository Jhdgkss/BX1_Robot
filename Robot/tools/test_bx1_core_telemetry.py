#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from bx1_core import (  # noqa: E402
    BX1Core,
    CoreEventBus,
    CoreEventType,
    CoreServiceRegistry,
    StateStore,
    TelemetryPublisher,
)
from bx1_core.plugins import CorePlugin, PluginContext, PluginRegistry  # noqa: E402


class Clock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        self.value += 0.001
        return self.value


def qualification_config():
    return json.loads(
        (PYTHON_ROOT / "config.alpha-qualification.json").read_text(
            encoding="utf-8"
        )
    )


class StateEngineTests(unittest.TestCase):
    def test_state_is_revisioned_nested_and_emits_only_real_changes(self):
        clock = Clock()
        events = CoreEventBus(clock=clock)
        received = []
        events.subscribe(CoreEventType.STATE_CHANGED, received.append)
        state = StateStore(
            {"test.value": 1},
            events=events,
            clock=clock,
            history_limit=8,
        )
        baseline = state.revision
        self.assertIsNone(state.set("test.value", 1, source="test"))
        change = state.set("test.value", 2, source="test")
        self.assertEqual(change.revision, baseline + 1)
        self.assertEqual(state.snapshot("test"), {"value": 2})
        self.assertEqual(received[-1].payload["path"], "test.value")
        self.assertEqual(received[-1].payload["source"], "test")

    def test_state_store_is_thread_safe(self):
        state = StateStore()

        def writer(worker: int) -> None:
            for index in range(50):
                state.set(
                    "concurrency.%s.%s" % (worker, index),
                    index,
                    source="test.worker.%s" % worker,
                )

        threads = [
            threading.Thread(target=writer, args=(worker,))
            for worker in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        snapshot = state.snapshot("concurrency")
        self.assertEqual(sum(len(values) for values in snapshot.values()), 200)

    def test_incremental_telemetry_and_history_resync(self):
        clock = Clock()
        events = CoreEventBus(clock=clock)
        state = StateStore(
            {"sample.value": 1},
            events=events,
            clock=clock,
            history_limit=2,
        )
        telemetry = TelemetryPublisher(state, events, clock=clock)
        revision = state.revision
        state.set("sample.value", 2, source="test")
        update = telemetry.updates(revision)
        self.assertFalse(update["resync_required"])
        self.assertEqual(update["changes"][0]["value"], 2)
        state.set("sample.one", 1, source="test")
        state.set("sample.two", 2, source="test")
        self.assertTrue(telemetry.updates(0)["resync_required"])
        self.assertEqual(telemetry.snapshot()["state"]["sample"]["value"], 2)


class EventBusTests(unittest.TestCase):
    def test_publish_subscribe_unsubscribe_and_failure_isolation(self):
        events = CoreEventBus()
        received = []
        token = events.subscribe("TEST", received.append)
        events.subscribe("TEST", lambda event: 1 / 0)
        item = events.publish("TEST", {"value": 1}, source="unit")
        self.assertEqual(item.type, "TEST")
        self.assertEqual(received[0].payload["value"], 1)
        self.assertTrue(events.unsubscribe(token))
        events.publish("TEST")
        self.assertEqual(len(received), 1)
        self.assertEqual(events.diagnostics()["subscriber_failures"], 2)

    def test_service_projection_emits_precise_lifecycle_events(self):
        events = CoreEventBus()
        state = StateStore(events=events)
        lifecycle = []
        events.subscribe(CoreEventType.SERVICE_STARTED, lifecycle.append)
        events.subscribe(CoreEventType.SERVICE_STOPPED, lifecycle.append)
        current = [{"name": "example.service", "state": "running"}]
        registry = CoreServiceRegistry(
            state, lambda: current, events=events
        )
        registry.update()
        current[0]["state"] = "stopped"
        registry.update()
        self.assertEqual(
            [event.type for event in lifecycle],
            ["SERVICE_STARTED", "SERVICE_STOPPED"],
        )


class ProbePlugin(CorePlugin):
    name = "probe"
    version = "9"

    def update(self) -> None:
        context = self._require_context()
        context.state.set("probe.ready", True, source="plugin.probe")


class FaultPlugin(CorePlugin):
    name = "fault"

    def update(self) -> None:
        raise RuntimeError("controlled failure")


class PluginFrameworkTests(unittest.TestCase):
    def context(self):
        clock = Clock()
        events = CoreEventBus(clock=clock)
        return PluginContext(
            state=StateStore(events=events, clock=clock),
            events=events,
            config={},
            install_root=ROOT,
            started_at=clock(),
            clock=clock,
        )

    def test_plugin_contract_registration_update_and_fault_containment(self):
        registry = PluginRegistry(self.context())
        registry.register(ProbePlugin())
        registry.register(FaultPlugin())
        result = registry.update()
        self.assertEqual(result["updated"], ["probe"])
        self.assertIn("fault", result["faults"])
        self.assertTrue(registry.context.state.get("probe.ready"))
        self.assertTrue(registry.health()["fault"]["fault"])

    def test_builtin_plugins_are_discovered_without_hardware_ownership(self):
        core = BX1Core(
            qualification_config(),
            install_root=ROOT,
            service_provider=lambda: [],
            update_interval=0.05,
        )
        self.assertEqual(
            core.plugins.names(),
            ["brain", "deployment", "hardware", "network", "system"],
        )
        state = core.state_snapshot()["state"]
        self.assertFalse(state["hardware"]["ownership"])
        self.assertFalse(state["hardware"]["actions_requested"])
        self.assertFalse(state["brain"]["connected"])
        self.assertEqual(state["robot"]["mode"], "observer_only")
        health = core.health_snapshot()
        self.assertFalse(health["fault"])
        self.assertTrue(all("timestamp" in item for item in health["plugins"].values()))

    def test_deployment_plugin_publishes_reviewed_manifest_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            install_root = Path(temporary)
            (install_root / "release_manifest.json").write_text(
                json.dumps(
                    {
                        "release_version": "0.3.0",
                        "release_tag": "BX1_OS_ALPHA_v0.3.0",
                        "source_git_tag": "BX1_OS_ALPHA_v0.3.0",
                        "source_git_branch": "feature/core",
                        "source_git_commit": "abc123",
                        "created_at": "2026-07-28T12:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            core = BX1Core(
                qualification_config(),
                install_root=install_root,
                service_provider=lambda: [],
            )
            deployment = core.state_snapshot()["state"]["deployment"]
            self.assertEqual(deployment["commit"], "abc123")
            self.assertEqual(deployment["branch"], "feature/core")
            self.assertEqual(
                deployment["tag"], "BX1_OS_ALPHA_v0.3.0"
            )

    def test_cooperative_scheduler_updates_and_stops_cleanly(self):
        core = BX1Core(
            qualification_config(),
            install_root=ROOT,
            service_provider=lambda: [],
            update_interval=0.02,
        )
        before = core.state.get("core.updated_at")
        core.start()
        time.sleep(0.16)
        tick = core.tick()
        core.stop()
        after = core.state.get("core.updated_at")
        self.assertGreater(after, before)
        self.assertTrue(tick["executed"])
        self.assertFalse(core.state.get("core.running"))


if __name__ == "__main__":
    unittest.main()
