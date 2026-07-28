#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from hardware_services import (  # noqa: E402
    BatteryDigitalTwin,
    BatteryState,
    BatteryStateMachine,
    CapabilityRegistry,
    EventBus,
    EventType,
    HardwareOnlyBMS,
    INA219Monitor,
    INA226Monitor,
    INA228Monitor,
    MockBMS,
    MockBatteryMonitor,
    PassiveBMS,
    SmartBMS,
    create_power_services,
    load_power_configuration,
)


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ConfigurationTests(unittest.TestCase):
    def test_loader_accepts_full_robot_configuration_and_deep_merges(self):
        config = load_power_configuration(
            {
                "hardware_services": {
                    "power_service": {"system_power_budget_w": 90},
                    "battery_service": {"low_soc_pct": 25},
                    "capability_registry": {
                        "capabilities": {"custom_power_board": True}
                    },
                }
            }
        )
        self.assertEqual(config["power_service"]["system_power_budget_w"], 90)
        self.assertEqual(config["power_service"]["reserved_power_w"], 10)
        self.assertEqual(config["battery_service"]["low_soc_pct"], 25)
        self.assertTrue(
            config["capability_registry"]["capabilities"]["custom_power_board"]
        )
        self.assertTrue(config["capability_registry"]["capabilities"]["camera"])

    def test_non_mock_backend_is_rejected_in_phase_two(self):
        with self.assertRaises(ValueError):
            create_power_services(
                {"battery_monitor": {"backend": "INA228"}}
            )

    def test_checked_in_configuration_files_load_safely(self):
        import json

        for name in ("config.example.json", "config.fresh.json", "config.json"):
            raw = json.loads((ROOT / "python" / name).read_text(encoding="utf-8"))
            config = load_power_configuration(raw)
            self.assertEqual(config["power_service"]["mode"], "digital_twin")
            self.assertEqual(config["battery_monitor"]["backend"], "mock")
            self.assertEqual(config["bms"]["backend"], "mock")
            self.assertFalse(config["docking"]["enabled"])

    def test_invalid_safety_threshold_order_is_rejected(self):
        with self.assertRaises(ValueError):
            load_power_configuration(
                {
                    "battery_service": {
                        "shutdown_soc_pct": 15,
                        "critical_soc_pct": 10,
                    }
                }
            )


class CapabilityRegistryTests(unittest.TestCase):
    def test_registry_is_extensible_and_queryable(self):
        registry = CapabilityRegistry({"camera": True, "smart_bms": False})
        self.assertTrue(registry.has("camera"))
        self.assertFalse(registry.has("smart_bms"))
        registry.register(
            "custom_power_board",
            True,
            simulated=True,
            metadata={"revision": "A"},
        )
        self.assertTrue(registry.query(camera=True, custom_power_board=True))
        self.assertEqual(
            registry.get("custom_power_board").metadata["revision"], "A"
        )
        self.assertTrue(registry.unregister("custom_power_board"))

    def test_registry_exposes_service_introspection(self):
        registry = CapabilityRegistry()
        self.assertEqual(registry.status()["state"], "READY")
        self.assertTrue(registry.health()["healthy"])
        self.assertIn("capabilities", registry.diagnostics())
        self.assertIn("battery_monitor", registry.configuration())


class BatteryStateMachineTests(unittest.TestCase):
    def test_legal_transitions_are_recorded(self):
        clock = Clock()
        machine = BatteryStateMachine(clock=clock)
        machine.transition(BatteryState.READY)
        machine.transition(BatteryState.LOW)
        machine.transition(BatteryState.CRITICAL)
        machine.transition(BatteryState.SHUTDOWN_PENDING)
        self.assertEqual(machine.state, BatteryState.SHUTDOWN_PENDING)
        self.assertEqual(len(machine.diagnostics()["transitions"]), 4)
        self.assertIn(
            "READY", machine.configuration()["legal_transitions"]["INITIALISING"]
        )

    def test_illegal_transition_is_rejected(self):
        machine = BatteryStateMachine(fitted=False)
        with self.assertRaises(ValueError):
            machine.transition(BatteryState.READY)


class MonitorAndBMSTests(unittest.TestCase):
    def test_mock_monitor_returns_coherent_cell_and_pack_values(self):
        monitor = MockBatteryMonitor(
            {
                "cell_voltages_v": [3.9, 4.0, 4.1],
                "pack_current_a": 2.0,
                "temperature_c": 30,
                "state_of_charge_pct": 50,
            }
        )
        sample = monitor.read()
        self.assertAlmostEqual(sample.pack_voltage_v, 12.0)
        self.assertAlmostEqual(sample.pack_power_w, 24.0)
        self.assertAlmostEqual(sample.balance_error_v, 0.2)
        self.assertEqual(sample.state_of_charge_pct, 50)

    def test_mock_monitor_controls(self):
        monitor = MockBatteryMonitor()
        monitor.set_pack_voltage(11.1)
        monitor.set_current(3)
        monitor.set_temperature(35)
        monitor.set_capacity(0.4)
        monitor.set_runtime(123)
        monitor.set_cell_voltage(2, 3.8)
        monitor.set_charging(True)
        sample = monitor.read()
        self.assertEqual(sample.state_of_charge_pct, 40)
        self.assertEqual(sample.runtime_override_s, 123)
        self.assertEqual(sample.cell_voltages_v[1], 3.8)
        self.assertLess(sample.pack_current_a, 0)
        self.assertTrue(sample.charging)

    def test_hardware_monitor_placeholders_are_inert(self):
        for monitor_type in (INA219Monitor, INA226Monitor, INA228Monitor):
            monitor = monitor_type()
            self.assertEqual(monitor.status()["state"], "NOT_FITTED")
            with self.assertRaises(RuntimeError):
                monitor.read()

    def test_mock_bms_output_faults_cells_and_balancing(self):
        bms = MockBMS()
        self.assertTrue(bms.output_enabled())
        bms.disable_output()
        self.assertFalse(bms.output_enabled())
        bms.set_fault("overcurrent")
        self.assertEqual(bms.faults(), ["overcurrent"])
        self.assertFalse(bms.enable_output())
        self.assertTrue(bms.reset_fault())
        self.assertTrue(bms.enable_output())
        bms.set_cell_voltages([3.8, 3.9, 4.0])
        bms.set_balancing(True)
        self.assertEqual(bms.cell_voltages(), [3.8, 3.9, 4.0])
        self.assertTrue(bms.balancing_state()["active"])

    def test_future_bms_placeholders_are_inert(self):
        for bms_type in (SmartBMS, PassiveBMS, HardwareOnlyBMS):
            bms = bms_type()
            self.assertEqual(bms.status()["state"], "NOT_FITTED")
            self.assertFalse(bms.output_enabled())
            with self.assertRaises(RuntimeError):
                bms.enable_output()


class BatteryServiceTests(unittest.TestCase):
    def test_default_battery_service_values_and_runtime_estimation(self):
        twin = BatteryDigitalTwin.create()
        battery = twin.battery
        self.assertEqual(battery.pack_voltage(), 12.0)
        self.assertEqual(battery.pack_current(), 1.0)
        self.assertEqual(battery.pack_power(), 12.0)
        self.assertEqual(battery.battery_temperature(), 25.0)
        self.assertEqual(battery.state_of_charge(), 75.0)
        self.assertAlmostEqual(battery.estimated_runtime(), 40500.0)
        self.assertEqual(battery.charging_state(), "not_charging")

    def test_low_critical_charging_and_full_states_publish_events(self):
        bus = EventBus()
        events = []
        bus.subscribe("*", lambda event: events.append(event.type))
        twin = BatteryDigitalTwin.create(event_bus=bus)
        twin.set_capacity(15)
        twin.set_capacity(8)
        twin.set_charging(True)
        twin.set_capacity(100)
        self.assertIn(EventType.BATTERY_LOW.value, events)
        self.assertIn(EventType.BATTERY_CRITICAL.value, events)
        self.assertIn(EventType.BATTERY_CHARGING.value, events)
        self.assertIn(EventType.BATTERY_FULL.value, events)
        self.assertEqual(twin.battery.status()["state"], "FULL")

    def test_battery_fault_removed_and_inserted_events(self):
        bus = EventBus()
        events = []
        bus.subscribe("*", lambda event: events.append(event.type))
        twin = BatteryDigitalTwin.create(event_bus=bus)
        twin.set_fault("simulated BMS fault")
        self.assertEqual(twin.battery.status()["state"], "FAULT")
        twin.set_fault(None)
        self.assertEqual(twin.battery.status()["state"], "READY")
        twin.set_fitted(False)
        twin.set_fitted(True)
        self.assertIn(EventType.BATTERY_FAULT.value, events)
        self.assertIn(EventType.BATTERY_REMOVED.value, events)
        self.assertIn(EventType.BATTERY_INSERTED.value, events)

    def test_cell_imbalance_warning_and_fault(self):
        twin = BatteryDigitalTwin.create()
        twin.set_cell_voltage(1, 3.85)
        health = twin.battery.battery_health()
        self.assertTrue(health["balance_warning"])
        self.assertFalse(health["healthy"])
        self.assertEqual(twin.battery.status()["state"], "READY")
        twin.set_cell_voltage(1, 3.5)
        self.assertEqual(twin.battery.status()["state"], "FAULT")
        self.assertGreater(twin.battery.balance_error(), 0.25)

    def test_runtime_override(self):
        twin = BatteryDigitalTwin.create()
        twin.set_runtime(900)
        self.assertEqual(twin.battery.estimated_runtime(), 900)
        self.assertEqual(twin.power.remaining_runtime(), 900)


class PowerServiceTests(unittest.TestCase):
    def test_power_budgeting_and_motion_permission(self):
        twin = BatteryDigitalTwin.create()
        power = twin.power
        self.assertEqual(power.available_power(), 110)
        self.assertTrue(power.can_move())
        power.set_load("compute", 50, essential=True)
        power.set_load("payload", 35)
        self.assertEqual(power.available_power(), 25)
        self.assertFalse(power.can_move())
        power.remove_load("payload")
        self.assertEqual(power.available_power(), 60)
        self.assertTrue(power.can_move())

    def test_charging_permission_follows_battery_state(self):
        twin = BatteryDigitalTwin.create()
        self.assertTrue(twin.power.can_charge())
        twin.set_capacity(100)
        self.assertFalse(twin.power.can_charge())
        twin.set_capacity(50)
        twin.set_fault("charger fault")
        self.assertFalse(twin.power.can_charge())

    def test_rail_fault_and_restore_events(self):
        bus = EventBus()
        events = []
        bus.subscribe("*", lambda event: events.append(event.type))
        twin = BatteryDigitalTwin.create(event_bus=bus)
        twin.power.set_rail("logic_5v", False, voltage_v=0, reason="simulated")
        self.assertTrue(twin.power.shutdown_required())
        self.assertEqual(twin.power.status()["state"], "FAULT")
        twin.power.set_rail("logic_5v", True, voltage_v=5)
        self.assertIn(EventType.POWER_RAIL_FAULT.value, events)
        self.assertIn(EventType.POWER_RESTORED.value, events)

    def test_shutdown_request_and_cancellation_events(self):
        bus = EventBus()
        events = []
        bus.subscribe("*", lambda event: events.append(event.type))
        twin = BatteryDigitalTwin.create(event_bus=bus)
        twin.power.request_shutdown("test shutdown")
        self.assertTrue(twin.power.shutdown_required())
        self.assertEqual(twin.power.status()["state"], "SHUTDOWN_PENDING")
        self.assertTrue(twin.power.cancel_shutdown())
        self.assertFalse(twin.power.shutdown_required())
        self.assertIn(EventType.SHUTDOWN_REQUESTED.value, events)
        self.assertIn(EventType.SHUTDOWN_CANCELLED.value, events)


class DigitalTwinTests(unittest.TestCase):
    def test_all_required_controls_update_public_services(self):
        twin = BatteryDigitalTwin.create()
        twin.set_voltage(11.4)
        twin.set_current(2)
        twin.set_temperature(32)
        twin.set_capacity(60)
        twin.set_runtime(600)
        twin.set_cell_voltage(3, 3.7)
        self.assertAlmostEqual(twin.battery.pack_voltage(), 11.3)
        self.assertEqual(twin.battery.pack_current(), 2)
        self.assertEqual(twin.battery.battery_temperature(), 32)
        self.assertEqual(twin.battery.state_of_charge(), 60)
        self.assertEqual(twin.battery.estimated_runtime(), 600)
        self.assertEqual(twin.battery.cell_voltage(3), 3.7)

    def test_service_container_introspection(self):
        twin = BatteryDigitalTwin.create()
        self.assertEqual(twin.mode, "digital_twin")
        self.assertIn("battery", twin.status())
        self.assertIn("power", twin.health())
        self.assertIn("event_bus", twin.diagnostics())
        self.assertIn("battery_service", twin.configuration())


class SafetyTests(unittest.TestCase):
    def test_phase_two_modules_import_no_hardware_io_libraries(self):
        files = (
            "battery.py",
            "battery_monitor.py",
            "battery_state.py",
            "battery_twin.py",
            "bms.py",
            "capability.py",
            "docking.py",
            "power.py",
            "power_config.py",
        )
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
        for name in files:
            path = ROOT / "python" / "hardware_services" / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported & banned,
                "%s imports prohibited hardware modules: %s"
                % (name, sorted(imported & banned)),
            )

    def test_phase_two_modules_do_not_depend_on_actuator_services(self):
        for name in ("battery.py", "battery_twin.py", "power.py"):
            source = (
                ROOT / "python" / "hardware_services" / name
            ).read_text(encoding="utf-8")
            self.assertNotIn("from .motor", source)
            self.assertNotIn("from .led", source)


if __name__ == "__main__":
    unittest.main()
