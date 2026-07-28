#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from bx1_core import (  # noqa: E402
    DiagnosticsService,
    HealthMonitor,
    LoggingService,
    SchedulerService,
    ServiceRegistry,
    create_bx1,
    load_core_configuration,
)
from hardware_services import EventBus, EventType  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class DummyService:
    def __init__(self, name="dummy", order=None) -> None:
        self.name = name
        self.state = "READY"
        self.healthy = True
        self.order = order if order is not None else []

    def start(self):
        self.order.append("start:" + self.name)

    def stop(self):
        self.order.append("stop:" + self.name)

    def status(self):
        return {"service": self.name, "state": self.state}

    def health(self):
        return {
            "healthy": self.healthy,
            "available": True,
            "state": self.state,
            "reason": self.state,
        }

    def diagnostics(self):
        return {"name": self.name}

    def configuration(self):
        return {"name": self.name}


class ServiceRegistryTests(unittest.TestCase):
    def test_registration_discovery_dependencies_and_lifecycle(self):
        order = []
        registry = ServiceRegistry()
        database = DummyService("database", order)
        api = DummyService("api", order)
        registry.register("database", database)
        registry.register("api", api, dependencies={"database"})
        started = registry.start_all()
        self.assertEqual(started, ["database", "api"])
        self.assertEqual(order, ["start:database", "start:api"])
        self.assertIs(registry.service("api"), api)
        self.assertEqual(registry.dependencies("api"), {"database"})
        self.assertEqual(registry.dependents("database"), {"api"})
        self.assertEqual(set(registry.discover()), {"api", "database"})
        with self.assertRaises(RuntimeError):
            registry.stop("database")
        registry.stop("database", cascade=True)
        self.assertEqual(order[-2:], ["stop:api", "stop:database"])

    def test_duplicate_missing_and_cyclic_dependencies_are_rejected(self):
        registry = ServiceRegistry()
        registry.register("one", DummyService("one"), dependencies={"two"})
        with self.assertRaises(ValueError):
            registry.register("one", DummyService("duplicate"))
        with self.assertRaises(RuntimeError):
            registry.start_all()
        registry.register("two", DummyService("two"), dependencies={"one"})
        with self.assertRaises(RuntimeError):
            registry.start_all()

    def test_unregister_protects_dependents(self):
        registry = ServiceRegistry()
        registry.register("base", DummyService())
        registry.register("consumer", DummyService(), dependencies={"base"})
        with self.assertRaises(RuntimeError):
            registry.unregister("base")
        removed = registry.unregister("base", force=True)
        self.assertIsInstance(removed, DummyService)


class SchedulerTests(unittest.TestCase):
    def test_one_shot_periodic_delayed_and_tick_callbacks(self):
        clock = Clock()
        scheduler = SchedulerService(clock=clock)
        calls = []
        scheduler.schedule_once(2, lambda: calls.append("once"), name="once")
        periodic = scheduler.schedule_periodic(
            1, lambda: calls.append("periodic"), name="periodic"
        )
        ticks = []
        token = scheduler.add_tick_callback(ticks.append)

        scheduler.tick()
        self.assertEqual(calls, [])
        clock.advance(1)
        scheduler.run_pending()
        self.assertEqual(calls, ["periodic"])
        clock.advance(1)
        scheduler.tick()
        self.assertEqual(calls, ["periodic", "once", "periodic"])
        self.assertEqual(ticks, [100.0, 101.0, 102.0])
        self.assertTrue(scheduler.cancel(periodic))
        self.assertTrue(scheduler.remove_tick_callback(token))
        self.assertTrue(scheduler.heartbeat()["alive"])
        self.assertFalse(scheduler.diagnostics()["threaded"])

    def test_callback_failures_are_isolated(self):
        clock = Clock()
        scheduler = SchedulerService(clock=clock)
        calls = []
        scheduler.schedule_once(0, lambda: 1 / 0, name="bad")
        scheduler.schedule_once(0, lambda: calls.append("good"), name="good")
        result = scheduler.tick()
        self.assertEqual(calls, ["good"])
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(scheduler.diagnostics()["failure_count"], 1)

    def test_invalid_intervals_are_rejected(self):
        scheduler = SchedulerService()
        with self.assertRaises(ValueError):
            scheduler.schedule_periodic(0, lambda: None)
        with self.assertRaises(ValueError):
            scheduler.schedule_once(-1, lambda: None)


class LoggingTests(unittest.TestCase):
    def test_levels_structured_context_and_service_logs(self):
        clock = Clock()
        logging = LoggingService({"level": "INFO"}, clock=clock)
        self.assertIsNone(logging.debug("filtered"))
        logging.info("root message", request_id="a")
        bound = logging.service("battery")
        bound.warning("low", state_of_charge=15)
        bound.error("fault", code="CELL")
        records = logging.records(service="battery")
        self.assertEqual([item["level"] for item in records], ["WARNING", "ERROR"])
        self.assertEqual(records[0]["context"]["state_of_charge"], 15)
        self.assertEqual(logging.diagnostics()["levels"]["ERROR"], 1)

    def test_future_sinks_are_injected_and_failures_isolated(self):
        logging = LoggingService()
        received = []
        logging.add_sink("memory", received.append)
        logging.add_sink("bad", lambda record: 1 / 0)
        logging.info("hello")
        self.assertEqual(len(received), 1)
        self.assertEqual(logging.diagnostics()["sink_failures"], 1)
        self.assertFalse(logging.diagnostics()["file_logging_active"])


class DiagnosticsTests(unittest.TestCase):
    def test_aggregates_health_faults_stale_and_missing(self):
        registry = ServiceRegistry()
        healthy = DummyService("healthy")
        fault = DummyService("fault")
        fault.state = "FAULT"
        fault.healthy = False
        stale = DummyService("stale")
        stale.state = "STALE"
        stale.healthy = False
        registry.register("healthy", healthy)
        registry.register("fault", fault)
        registry.register("stale", stale)
        registry.start_all()
        diagnostics = DiagnosticsService(
            registry,
            {"required_services": ["healthy", "fault", "stale", "missing"]},
        )
        report = diagnostics.report()
        self.assertEqual(report["overall_state"], "FAULT")
        self.assertEqual(report["faulted"], ["fault"])
        self.assertEqual(report["stale"], ["stale"])
        self.assertEqual(report["missing"], ["missing"])
        self.assertIn("diagnostics", report["services"]["healthy"])

    def test_diagnostics_collector_is_itself_introspectable(self):
        registry = ServiceRegistry()
        diagnostics = DiagnosticsService(registry)
        self.assertEqual(diagnostics.status()["state"], "READY")
        self.assertTrue(diagnostics.health()["healthy"])
        diagnostics.report()
        self.assertEqual(diagnostics.diagnostics()["report_count"], 1)


class HealthMonitorTests(unittest.TestCase):
    def test_health_changes_publish_events(self):
        registry = ServiceRegistry()
        service = DummyService("sensor")
        registry.register("sensor", service)
        registry.start_all()
        events = EventBus()
        received = []
        events.subscribe("*", lambda event: received.append(event.type))
        monitor = HealthMonitor(
            registry,
            events,
            {"required_services": ["sensor"], "publish_initial": False},
        )
        monitor.check()
        self.assertEqual(received, [])

        service.state = "STALE"
        service.healthy = False
        monitor.check()
        service.state = "FAULT"
        monitor.check()
        service.state = "READY"
        service.healthy = True
        monitor.check()
        self.assertIn(EventType.SERVICE_HEALTH_CHANGED.value, received)
        self.assertIn(EventType.SERVICE_STALE.value, received)
        self.assertIn(EventType.SERVICE_FAULT.value, received)
        self.assertIn(EventType.SERVICE_RECOVERED.value, received)

    def test_missing_required_service_is_reported(self):
        monitor = HealthMonitor(
            ServiceRegistry(),
            EventBus(),
            {"required_services": ["battery"]},
        )
        result = monitor.check()
        self.assertEqual(result["overall_state"], "FAULT")
        self.assertEqual(result["missing"], ["battery"])
        self.assertTrue(monitor.health()["healthy"])


class RootAPITests(unittest.TestCase):
    def test_root_exposes_all_required_services(self):
        clock = Clock()
        root = create_bx1(monotonic_clock=clock, wall_clock=clock)
        names = (
            "events",
            "power",
            "battery",
            "drive",
            "led",
            "range",
            "scheduler",
            "logging",
            "diagnostics",
            "health",
            "capabilities",
        )
        for name in names:
            self.assertIsNotNone(getattr(root, name))
            self.assertIs(root.service(name), getattr(root, name))
        self.assertEqual(root.diagnostics.report()["overall_state"], "HEALTHY")
        self.assertEqual(root.drive.status()["state"], "DISABLED")

    def test_root_tick_and_future_service_attachment(self):
        clock = Clock()
        root = create_bx1(monotonic_clock=clock, wall_clock=clock)
        baseline = root.health.status()["check_count"]
        clock.advance(1)
        root.tick()
        self.assertGreater(root.health.status()["check_count"], baseline)
        future = DummyService("future")
        root.attach("future", future)
        self.assertIs(root.future, future)
        self.assertIs(root.service("future"), future)

    def test_public_bx1_module_is_safe_digital_twin(self):
        from bx1 import bx1

        self.assertEqual(bx1.drive.status()["state"], "DISABLED")
        self.assertEqual(bx1.power.configuration()["mode"], "digital_twin")
        self.assertFalse(bx1.scheduler.diagnostics()["threaded"])


class ConfigurationTests(unittest.TestCase):
    def test_loader_deep_merges_and_rejects_unsafe_modes(self):
        config = load_core_configuration(
            {"core_services": {"logging": {"level": "DEBUG"}}}
        )
        self.assertEqual(config["logging"]["level"], "DEBUG")
        self.assertFalse(config["logging"]["file_logging_enabled"])
        self.assertTrue(config["scheduler"]["cooperative"])
        with self.assertRaises(ValueError):
            load_core_configuration(
                {"scheduler": {"cooperative": False}}
            )
        with self.assertRaises(ValueError):
            load_core_configuration(
                {"logging": {"file_logging_enabled": True}}
            )

    def test_checked_in_configs_have_safe_core_sections(self):
        for name in ("config.example.json", "config.fresh.json", "config.json"):
            raw = json.loads((ROOT / "python" / name).read_text(encoding="utf-8"))
            self.assertIn("core_services", raw)
            self.assertEqual(
                set(raw["core_services"]),
                {
                    "service_registry",
                    "scheduler",
                    "logging",
                    "diagnostics",
                    "health_monitor",
                    "communication",
                    "runtime_integration",
                },
            )
            config = load_core_configuration(raw)
            self.assertTrue(config["scheduler"]["cooperative"])
            self.assertFalse(config["logging"]["file_logging_enabled"])


class SafetyTests(unittest.TestCase):
    def test_core_modules_import_no_hardware_libraries_or_thread_workers(self):
        banned = {
            "serial",
            "RPi",
            "board",
            "busio",
            "smbus",
            "smbus2",
            "gpiozero",
            "periphery",
            "spidev",
            "adafruit",
        }
        core = ROOT / "python" / "bx1_core"
        for path in core.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(imported & banned)
            self.assertNotIn("threading.Thread", source)
            self.assertNotIn("from .motor", source)
            self.assertNotIn("from .led", source)


if __name__ == "__main__":
    unittest.main()
