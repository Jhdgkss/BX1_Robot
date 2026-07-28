#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from bx1_core import (  # noqa: E402
    BootstrapError,
    CompatibilityServiceAdapter,
    ServiceLifecycleState,
    bootstrap_runtime,
    load_core_configuration,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeLegacyHardware:
    def __init__(self) -> None:
        self.available = False
        self.last_state = {"bridge_mode": "test"}
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)
        return {"ok": True, "action": action}


def fake_hardware_factory(root, config):
    return CompatibilityServiceAdapter(
        "runtime_hardware",
        FakeLegacyHardware(),
    )


def integrated_bootstrap(*, clock=None, config=None):
    clock = clock or Clock()
    return bootstrap_runtime(
        config or {},
        service_factories={"runtime_hardware": fake_hardware_factory},
        service_dependencies={"runtime_hardware": {"events", "logging"}},
        required_services={"runtime_hardware"},
        monotonic_clock=clock,
        wall_clock=clock,
    )


class BootstrapTests(unittest.TestCase):
    def test_successful_bootstrap_starts_and_validates_every_service(self):
        result = integrated_bootstrap()
        report = result.report
        self.assertTrue(report["success"])
        self.assertEqual(report["milestone"], "BX1 OS Alpha")
        self.assertTrue(report["dependency_valid"])
        self.assertEqual(report["missing_services"], [])
        self.assertTrue(report["scheduler"]["heartbeat"]["alive"])
        self.assertTrue(report["communication"]["health"]["healthy"])
        for name in report["required_services"]:
            self.assertEqual(report["service_states"][name], "RUNNING")

    def test_missing_required_service_fails_with_clear_report(self):
        with self.assertRaises(BootstrapError) as raised:
            bootstrap_runtime({}, required_services={"not_installed"})
        report = raised.exception.report
        self.assertFalse(report["success"])
        self.assertTrue(report["failed_safe"])
        self.assertIn("not_installed", report["missing_services"])
        self.assertIn("missing required services", " ".join(report["errors"]))

    def test_dependency_failure_is_detected_before_runtime_start(self):
        with self.assertRaises(BootstrapError) as raised:
            bootstrap_runtime(
                {},
                service_factories={
                    "runtime_hardware": fake_hardware_factory
                },
                service_dependencies={
                    "runtime_hardware": {"missing_dependency"}
                },
                required_services={"runtime_hardware"},
            )
        report = raised.exception.report
        self.assertFalse(report["dependency_valid"])
        self.assertIn(
            "missing service dependencies",
            " ".join(report["dependency_errors"]),
        )

    def test_configuration_loader_runs_once_and_preserves_legacy_keys(self):
        calls = []
        legacy = {
            "app_version": "10.39",
            "voice_enabled": True,
            "brain_base_url": "http://brain:8765",
        }

        def loader():
            calls.append(True)
            return legacy

        result = bootstrap_runtime(config_loader=loader)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.configuration, legacy)
        self.assertEqual(
            result.report["configuration_summary"]["application_version"],
            "10.39",
        )
        self.assertNotIn("brain_base_url", result.report["configuration_summary"])


class OwnershipAndLifecycleTests(unittest.TestCase):
    def test_compatibility_adapter_preserves_delegate_interface(self):
        result = integrated_bootstrap()
        hardware = result.bx1.service("runtime_hardware")
        response = hardware.send_action({"type": "legacy_action"})
        self.assertTrue(response["ok"])
        self.assertEqual(hardware.delegate.actions[0]["type"], "legacy_action")
        self.assertFalse(hardware.available)
        self.assertEqual(hardware.diagnostics()["bridge_mode"], "test")
        self.assertFalse(hardware.diagnostics()["hardware_polled"])

    def test_registry_exposes_dependency_graph_and_running_state(self):
        result = integrated_bootstrap()
        validation = result.bx1.services.validate_dependencies()
        self.assertTrue(validation["valid"])
        self.assertEqual(
            validation["graph"]["runtime_hardware"],
            ["events", "logging"],
        )
        self.assertEqual(
            result.bx1.services.registration("runtime_hardware").state,
            ServiceLifecycleState.RUNNING,
        )

    def test_scheduler_executes_runtime_callbacks_cooperatively(self):
        clock = Clock()
        result = integrated_bootstrap(clock=clock)
        called = []
        result.bx1.scheduler.schedule_once(
            0.5,
            lambda: called.append("ran"),
            name="alpha_test",
        )
        clock.advance(0.5)
        tick = result.bx1.tick()
        self.assertEqual(called, ["ran"])
        self.assertEqual(tick["failures"], [])
        self.assertTrue(result.bx1.scheduler.heartbeat()["alive"])

    def test_stop_all_stops_owned_compatibility_service(self):
        result = integrated_bootstrap()
        result.bx1.services.stop_all()
        self.assertEqual(
            result.bx1.services.registration("runtime_hardware").state,
            ServiceLifecycleState.STOPPED,
        )
        self.assertEqual(
            result.bx1.service("runtime_hardware").status()["state"],
            "INITIALISING",
        )


class DiagnosticsAndCompatibilityTests(unittest.TestCase):
    def test_startup_diagnostics_include_runtime_architecture(self):
        result = integrated_bootstrap()
        report = result.bx1.diagnostics.report()
        runtime = report["runtime"]
        self.assertEqual(
            runtime["startup_report"]["milestone"], "BX1 OS Alpha"
        )
        self.assertIn("runtime_hardware", runtime["registered_services"])
        self.assertEqual(
            runtime["dependency_graph"]["runtime_hardware"],
            ["events", "logging"],
        )
        self.assertTrue(runtime["communication"]["registered"])
        self.assertEqual(
            runtime["communication"]["status"]["transport"], "in_memory"
        )

    def test_existing_and_new_checked_in_configs_remain_compatible(self):
        for name in ("config.example.json", "config.fresh.json", "config.json"):
            raw = json.loads((ROOT / "python" / name).read_text(encoding="utf-8"))
            core = load_core_configuration(raw)
            self.assertTrue(core["runtime_integration"]["compatibility_mode"])
            self.assertTrue(core["runtime_integration"]["fail_safe"])
            self.assertEqual(
                core["communication"]["transport"], "in_memory"
            )
        legacy = load_core_configuration({"voice_enabled": True})
        self.assertTrue(legacy["runtime_integration"]["enabled"])

    def test_runtime_startup_uses_bx1_and_retains_direct_fallback(self):
        path = ROOT / "python" / "main.py"
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        self.assertIn("SERVICE = create_robot_body_service()", source)
        self.assertIn("self.hardware = resolve_runtime_hardware", source)
        self.assertIn("return fallback_factory(config)", source)
        self.assertIn("self.bx1.tick()", source)
        self.assertIn('"bx1_os": self.bx1_os_diagnostics()', source)

    def test_robot_bootstrap_resolves_owned_bridge_without_hardware(self):
        path = ROOT / "python" / "main.py"
        spec = importlib.util.spec_from_file_location(
            "bx1_main_alpha_integration_test", path
        )
        if spec is None or spec.loader is None:
            self.fail("could not load Robot runtime module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        result = module.bootstrap_robot_runtime(
            {"app_version": "compatibility-test"},
            hardware_factory=lambda config: FakeLegacyHardware(),
        )
        owned = module.resolve_runtime_hardware(
            result.configuration,
            result.bx1,
            fallback_factory=lambda config: self.fail(
                "owned service unexpectedly used direct fallback"
            ),
        )
        self.assertIs(owned, result.bx1.service("runtime_hardware"))
        self.assertEqual(owned.configuration()["behaviour_preserved"], True)
        self.assertTrue(result.report["success"])

        fallback = object()
        resolved = module.resolve_runtime_hardware(
            {},
            None,
            fallback_factory=lambda config: fallback,
        )
        self.assertIs(resolved, fallback)

    def test_bootstrap_module_has_no_hardware_or_transport_imports(self):
        path = ROOT / "python" / "bx1_core" / "bootstrap.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(
            imported
            & {
                "serial",
                "socket",
                "http",
                "urllib",
                "websockets",
                "paho",
                "RPi",
                "board",
                "busio",
                "smbus",
                "gpiozero",
                "spidev",
            }
        )


if __name__ == "__main__":
    unittest.main()
