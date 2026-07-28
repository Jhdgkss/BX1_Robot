#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from hardware_services import (  # noqa: E402
    CallbackLEDStrip,
    CommandValidator,
    DigitalTwin,
    EventBus,
    EventType,
    FutureToFSensor,
    HardwareState,
    HardwareStateManager,
    LEDEffect,
    LEDService,
    MockDistanceSensor,
    RangeService,
    RS485Transport,
    SimulatedLEDStrip,
    create_hardware_services,
)


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, value: float) -> None:
        self.value += value / 1000.0


class EventBusTests(unittest.TestCase):
    def test_subscribe_publish_unsubscribe_and_diagnostics(self):
        bus = EventBus(history_limit=5)
        received = []
        token = bus.subscribe(EventType.WAKE_DETECTED, received.append)

        event = bus.publish(
            EventType.WAKE_DETECTED, {"word": "BX1"}, source="test"
        )
        self.assertEqual(event.type, "WakeDetected")
        self.assertEqual(received[0].payload["word"], "BX1")
        self.assertTrue(bus.unsubscribe(token))
        bus.publish(EventType.WAKE_DETECTED)
        self.assertEqual(len(received), 1)
        self.assertEqual(bus.diagnostics()["published"]["WakeDetected"], 2)

    def test_wildcard_and_subscriber_failure_are_isolated(self):
        bus = EventBus()
        seen = []
        bus.subscribe("*", lambda event: seen.append(event.type))
        bus.subscribe(EventType.ROBOT_READY, lambda event: 1 / 0)
        bus.publish(EventType.ROBOT_READY)
        self.assertEqual(seen, ["RobotReady"])
        self.assertEqual(bus.diagnostics()["subscriber_failures"], 1)
        self.assertTrue(bus.health()["healthy"])


class HardwareStateTests(unittest.TestCase):
    def test_state_transitions_and_health(self):
        clock = Clock()
        manager = HardwareStateManager(clock=clock)
        self.assertEqual(
            manager.register("sensor", fitted=True, enabled=True),
            HardwareState.INITIALISING,
        )
        manager.transition("sensor", HardwareState.READY, reason="sample received")
        self.assertTrue(manager.health("sensor")["healthy"])
        clock.advance_ms(1200)
        manager.transition("sensor", HardwareState.STALE, reason="sample expired")
        self.assertFalse(manager.health("sensor")["healthy"])
        self.assertEqual(len(manager.diagnostics("sensor")["transitions"]), 2)

    def test_invalid_transition_is_rejected(self):
        manager = HardwareStateManager()
        manager.register("motor", fitted=False, enabled=False)
        with self.assertRaises(ValueError):
            manager.transition("motor", HardwareState.READY)


class LEDServiceTests(unittest.TestCase):
    def test_default_layout_is_exactly_seven_pixels(self):
        strip = SimulatedLEDStrip()
        service = LEDService(strip)
        config = service.configuration()
        self.assertEqual(config["pixel_count"], 7)
        self.assertEqual(config["zones"]["head"], [0])
        self.assertEqual(config["zones"]["body"], [1, 2, 3, 4, 5, 6])

    def test_all_effects_render_without_touching_other_zone(self):
        clock = Clock()
        strip = SimulatedLEDStrip()
        service = LEDService(strip, clock=clock)
        service.set_effect(LEDEffect.SOLID, zone="head", colour="green")
        head = strip.snapshot()[0]
        for effect in LEDEffect:
            frame = service.set_effect(
                effect,
                zone="body",
                colour="#00aaff",
                secondary_colour="purple",
                period_s=1.0,
                duration_s=1.0,
            )
            self.assertEqual(len(frame), 7)
            self.assertEqual(frame[0], head)
            service.tick(0.75)

    def test_callback_adapter_is_not_used_until_a_frame_is_written(self):
        frames = []
        output = CallbackLEDStrip(lambda pixels: frames.append(list(pixels)))
        self.assertEqual(frames, [])
        service = LEDService(output)
        self.assertEqual(frames, [])
        service.set_effect("Solid", zone="body", colour="blue")
        self.assertEqual(len(frames), 1)
        self.assertEqual(len(frames[0]), 7)

    def test_bad_zone_and_pixel_count_are_rejected(self):
        with self.assertRaises(ValueError):
            LEDService(SimulatedLEDStrip(), {"pixel_count": 8})
        with self.assertRaises(ValueError):
            LEDService(SimulatedLEDStrip(), {"zones": {"bad": [7]}})


class MotorServiceTests(unittest.TestCase):
    def test_validator_accepts_safe_values_and_rejects_limits(self):
        validator = CommandValidator(
            {"limits": {"max_speed": 0.5, "max_acceleration": 0.8, "max_duration_s": 2}}
        )
        self.assertTrue(validator.validate(0.5, -0.5, 2, 0.8)["valid"])
        invalid = validator.validate(0.6, float("nan"), 3, 1.0)
        self.assertFalse(invalid["valid"])
        self.assertGreaterEqual(len(invalid["errors"]), 4)

    def test_drive_is_disabled_by_default_and_command_is_logged(self):
        twin = DigitalTwin.create()
        result = twin.drive.drive_wheels(0.2, 0.2, duration_s=1)
        self.assertFalse(result["accepted"])
        self.assertEqual(twin.drive.status()["state"], "DISABLED")
        self.assertEqual(twin.drive.diagnostics()["command_count"], 1)

    def test_enabled_drive_remains_dry_run_and_applies_inversion(self):
        twin = DigitalTwin.create(
            {
                "motor": {
                    "drive_enabled": True,
                    "drive_dry_run": True,
                    "rs485_enabled": False,
                    "inversion": {"left": False, "right": True},
                }
            }
        )
        result = twin.drive.drive_wheels(0.25, 0.5, duration_s=1)
        self.assertTrue(result["accepted"])
        self.assertFalse(result["transport"]["transmitted"])
        self.assertEqual(result["state"]["left_applied"], 0.25)
        self.assertEqual(result["state"]["right_applied"], -0.5)
        self.assertFalse(twin.drive.transport.is_open)
        differential = twin.drive.drive(0.25, 0.05, duration_s=1)
        self.assertTrue(differential["accepted"])
        self.assertAlmostEqual(differential["state"]["left_requested"], 0.2)
        self.assertAlmostEqual(differential["state"]["right_requested"], 0.3)

    def test_transport_cannot_open_and_unsafe_config_faults(self):
        transport = RS485Transport({"rs485_enabled": True})
        self.assertEqual(transport.status()["state"], "FAULT")
        self.assertFalse(transport.diagnostics()["hardware_io_permitted"])
        with self.assertRaises(RuntimeError):
            transport.open()
        twin = DigitalTwin.create(
            {"motor": {"drive_enabled": True, "drive_dry_run": False}}
        )
        self.assertEqual(twin.drive.status()["state"], "FAULT")
        result = twin.drive.drive_wheels(0.1, 0.1, duration_s=1)
        self.assertFalse(result["accepted"])
        rs485_twin = DigitalTwin.create(
            {"motor": {"drive_enabled": True, "rs485_enabled": True}}
        )
        self.assertEqual(rs485_twin.drive.status()["state"], "FAULT")
        self.assertFalse(
            rs485_twin.drive.drive_wheels(0.1, 0.1, duration_s=1)["accepted"]
        )


class RangeServiceTests(unittest.TestCase):
    def test_mock_readings_are_configurable_and_cycle(self):
        sensor = MockDistanceSensor(
            {
                "readings": [
                    {"distance_mm": 300, "signal_quality": 0.9},
                    {"distance_mm": 450, "signal_quality": 0.7},
                ]
            }
        )
        service = RangeService(sensor)
        self.assertEqual(service.poll().distance_mm, 300)
        self.assertEqual(service.poll().distance_mm, 450)
        self.assertEqual(service.poll().distance_mm, 300)
        self.assertTrue(service.available)
        self.assertTrue(service.healthy)

    def test_mock_out_of_range_and_fault_fields(self):
        sensor = MockDistanceSensor({"max_distance_mm": 1000})
        sensor.set_reading(1500, signal_quality=0.2)
        service = RangeService(sensor)
        reading = service.poll()
        self.assertTrue(reading.out_of_range)
        self.assertIn("outside", reading.fault_reason)
        sensor.set_reading(None, available=False, fault_reason="simulated disconnect")
        reading = service.poll()
        self.assertFalse(reading.available)
        self.assertFalse(reading.healthy)
        self.assertEqual(service.status()["state"], "FAULT")

    def test_sample_becomes_stale(self):
        clock = Clock()
        sensor = MockDistanceSensor(clock=clock)
        service = RangeService(sensor, {"stale_after_ms": 100}, clock=clock)
        service.poll()
        clock.advance_ms(101)
        self.assertGreater(service.sample_age_ms, 100)
        self.assertFalse(service.healthy)
        self.assertEqual(service.status()["state"], "STALE")

    def test_future_tof_sensor_does_not_access_hardware(self):
        sensor = FutureToFSensor()
        reading = sensor.sample()
        self.assertEqual(sensor.status()["state"], "NOT_FITTED")
        self.assertFalse(reading.available)
        self.assertIn("not implemented", reading.fault_reason)


class DigitalTwinTests(unittest.TestCase):
    def test_twin_services_share_public_introspection_contract(self):
        twin = DigitalTwin.create()
        for service in (twin.event_bus, twin.leds, twin.drive, twin.range):
            self.assertIsInstance(service.status(), dict)
            self.assertIsInstance(service.health(), dict)
            self.assertIsInstance(service.diagnostics(), dict)
            self.assertIsInstance(service.configuration(), dict)

    def test_event_flow_animates_body_but_preserves_mouth_pixel(self):
        twin = DigitalTwin.create()
        twin.leds.set_effect("Solid", zone="head", colour="green")
        mouth_before = twin.simulated_leds.snapshot()[0]
        twin.event_bus.publish(EventType.THINKING_STARTED)
        twin.leds.tick(0.25)
        frame = twin.simulated_leds.snapshot()
        self.assertEqual(frame[0], mouth_before)
        self.assertTrue(any(pixel != (0, 0, 0) for pixel in frame[1:]))
        twin.event_bus.publish(EventType.THINKING_FINISHED)
        self.assertTrue(all(pixel == (0, 0, 0) for pixel in twin.simulated_leds.snapshot()[1:]))

    def test_physical_adapter_factory_has_the_same_service_surface(self):
        frames = []
        sensor = MockDistanceSensor({"default_distance_mm": 600})
        services = create_hardware_services(
            {"mode": "physical"},
            physical_led_writer=lambda pixels: frames.append(list(pixels)),
            range_sensor=sensor,
        )
        services.leds.set_effect("Solid", zone="body", colour="cyan")
        self.assertEqual(len(frames), 1)
        self.assertEqual(services.range.poll().distance_mm, 600)
        self.assertEqual(set(services.status()), {"mode", "event_bus", "leds", "drive", "range"})

    def test_factory_accepts_the_full_robot_configuration_shape(self):
        services = create_hardware_services(
            {"hardware_services": {"mode": "digital_twin", "bind_default_events": False}}
        )
        self.assertEqual(services.mode, "digital_twin")
        self.assertEqual(services.leds.diagnostics()["event_bindings"], 0)


if __name__ == "__main__":
    unittest.main()
