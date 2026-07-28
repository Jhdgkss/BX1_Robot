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
    MessageBus,
    MessageCodec,
    MessageStatus,
    MessageValidationError,
    ProtocolVersion,
    SessionManager,
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


class MessageSchemaTests(unittest.TestCase):
    def test_valid_message_round_trip_contains_exact_schema(self):
        codec = MessageCodec()
        message = codec.new(
            protocol_version="1.0.0",
            message_id="message-1",
            timestamp=123.5,
            sender="brain",
            destination="bx1",
            command="battery.status",
            payload={"detail": True},
            response=None,
            status=MessageStatus.REQUEST,
        )
        decoded = codec.decode(codec.encode(message))
        self.assertEqual(decoded, message)
        self.assertEqual(
            set(decoded.as_dict()),
            {
                "protocol_version",
                "message_id",
                "timestamp",
                "sender",
                "destination",
                "command",
                "payload",
                "response",
                "status",
            },
        )

    def test_missing_extra_duplicate_and_invalid_fields_are_rejected(self):
        codec = MessageCodec()
        valid = codec.new(
            protocol_version="1.0.0",
            sender="brain",
            destination="bx1",
            command="system.info",
        ).as_dict()
        for mutation in (
            lambda item: item.pop("sender"),
            lambda item: item.update({"extra": True}),
            lambda item: item.update({"status": "unknown"}),
            lambda item: item.update({"payload": []}),
            lambda item: item.update({"timestamp": float("nan")}),
        ):
            value = dict(valid)
            mutation(value)
            with self.assertRaises(MessageValidationError):
                codec.validate(value)
        with self.assertRaises(MessageValidationError):
            codec.decode(
                '{"protocol_version":"1.0.0","protocol_version":"1.0.0"}'
            )

    def test_json_safety_and_maximum_size_are_enforced(self):
        codec = MessageCodec(maximum_message_size=256)
        with self.assertRaises(MessageValidationError) as caught:
            codec.new(
                protocol_version="1.0.0",
                sender="brain",
                destination="bx1",
                command="system.info",
                payload={"bad": float("nan")},
            )
        self.assertEqual(caught.exception.code, "INVALID_MESSAGE")
        message = codec.new(
            protocol_version="1.0.0",
            sender="brain",
            destination="bx1",
            command="system.info",
            payload={"data": "x" * 300},
        )
        with self.assertRaises(MessageValidationError) as caught:
            codec.encode(message)
        self.assertEqual(caught.exception.code, "MESSAGE_TOO_LARGE")

    def test_protocol_version_parsing_and_compatibility(self):
        server = ProtocolVersion.parse("1.2.3")
        self.assertTrue(server.compatible_with(ProtocolVersion.parse("1.9.0")))
        self.assertFalse(server.compatible_with(ProtocolVersion.parse("2.0.0")))
        with self.assertRaises(MessageValidationError):
            ProtocolVersion.parse("v1")


class MessageBusTests(unittest.TestCase):
    def test_destination_queues_are_in_memory_and_bounded(self):
        bus = MessageBus({"maximum_queued_messages": 2})
        bus.send("brain", "one")
        bus.send("tool", "two")
        self.assertEqual(bus.receive("tool"), "two")
        self.assertEqual(bus.receive("brain"), "one")
        self.assertIsNone(bus.receive())
        bus.send("brain", "one")
        bus.send("brain", "two")
        bus.send("brain", "three")
        self.assertEqual(bus.pending("brain"), 2)
        self.assertEqual(bus.diagnostics()["dropped_count"], 1)
        self.assertFalse(bus.diagnostics()["network_used"])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.events = EventBus()
        self.received = []
        self.events.subscribe("*", lambda event: self.received.append(event.type))
        self.config = {
            "protocol_version": "1.0.0",
            "heartbeat_interval_s": 5,
            "timeout_s": 15,
            "maximum_clients": 2,
        }
        self.sessions = SessionManager(
            self.events, self.config, clock=self.clock
        )

    def test_registration_heartbeat_timeout_and_disconnect_events(self):
        session = self.sessions.register_client("brain", "1.1.0")
        self.assertTrue(self.sessions.active("brain"))
        self.clock.advance(10)
        self.sessions.heartbeat(session.session_id)
        self.clock.advance(16)
        self.assertEqual(self.sessions.expire_sessions(), [session.session_id])
        self.assertFalse(self.sessions.active("brain"))
        self.assertIn(EventType.CLIENT_CONNECTED.value, self.received)
        self.assertIn(EventType.HEARTBEAT_TIMEOUT.value, self.received)
        self.assertIn(EventType.CLIENT_DISCONNECTED.value, self.received)

    def test_maximum_clients_and_protocol_mismatch(self):
        self.sessions.register_client("one", "1.0.0")
        self.sessions.register_client("two", "1.0.1")
        with self.assertRaises(RuntimeError):
            self.sessions.register_client("three", "1.0.0")
        with self.assertRaises(MessageValidationError) as caught:
            self.sessions.register_client("old", "2.0.0")
        self.assertEqual(caught.exception.code, "PROTOCOL_MISMATCH")
        self.assertIn(EventType.PROTOCOL_MISMATCH.value, self.received)


class CommandAndCommunicationTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.root = create_bx1(
            monotonic_clock=self.clock, wall_clock=self.clock
        )
        self.communication = self.root.communication
        self.communication.register_client("brain", "1.0.0")

    def test_root_exposes_communication_service(self):
        self.assertIs(
            self.root.communication, self.root.service("communication")
        )
        self.assertEqual(
            self.communication.status()["transport"], "in_memory"
        )

    def test_read_commands_route_to_bx1_services(self):
        battery = self.communication.request("brain", "battery.status")
        power = self.communication.request("brain", "power.health")
        distance = self.communication.request("brain", "range.distance")
        system = self.communication.request("brain", "system.info")
        self.assertEqual(battery.status, "ok")
        self.assertEqual(battery.response["data"]["service"], "battery_service")
        self.assertTrue(power.response["data"]["healthy"])
        self.assertEqual(distance.response["data"]["distance_mm"], 1000.0)
        self.assertTrue(system.response["data"]["digital_twin"])

    def test_drive_and_led_commands_only_touch_digital_twin_services(self):
        drive = self.communication.request(
            "brain",
            "drive.move",
            {
                "linear_speed": 0.2,
                "angular_speed": 0.0,
                "duration_s": 1.0,
            },
        )
        self.assertEqual(drive.status, "ok")
        self.assertFalse(drive.response["data"]["accepted"])
        self.assertFalse(self.root.drive.transport.is_open)

        led = self.communication.request(
            "brain",
            "led.set",
            {"effect": "Solid", "zone": "body", "colour": "blue"},
        )
        self.assertTrue(led.response["data"]["simulated"])
        self.assertEqual(len(led.response["data"]["pixels"]), 7)

    def test_diagnostics_health_and_stop_commands(self):
        diagnostics = self.communication.request(
            "brain", "diagnostics.report"
        )
        health = self.communication.request("brain", "health.status")
        stop = self.communication.request("brain", "drive.stop")
        self.assertIn(
            diagnostics.response["data"]["overall_state"],
            {"HEALTHY", "DEGRADED"},
        )
        self.assertEqual(health.response["data"]["service"], "health_monitor")
        self.assertFalse(stop.response["data"]["accepted"])

    def test_unknown_command_and_bad_payload_return_protocol_errors(self):
        unknown = self.communication.request("brain", "unknown.command")
        invalid = self.communication.request(
            "brain", "drive.move", {"linear_speed": 1}
        )
        self.assertEqual(unknown.status, "error")
        self.assertEqual(
            unknown.response["error"]["code"], "UNKNOWN_COMMAND"
        )
        self.assertEqual(invalid.status, "error")
        self.assertEqual(
            invalid.response["error"]["code"], "INVALID_PAYLOAD"
        )

    def test_capability_negotiation_and_get_alias(self):
        direct = self.communication.capabilities()
        response = self.communication.request("brain", "GET capabilities")
        self.assertEqual(direct["protocol_version"], "1.0.0")
        self.assertEqual(response.response["data"]["transport"], "in_memory")
        self.assertIn("battery_monitor", response.response["data"]["registered"])
        self.assertIn("battery.status", response.response["data"]["commands"])

    def test_unregistered_client_and_protocol_mismatch_are_errors(self):
        codec = self.communication.codec
        no_session = codec.new(
            protocol_version="1.0.0",
            sender="tool",
            destination="bx1",
            command="system.info",
            timestamp=self.clock(),
        )
        response = self.communication.receive(codec.encode(no_session))
        self.assertEqual(response.response["error"]["code"], "SESSION_REQUIRED")

        mismatch = self.communication.request(
            "brain", "system.info", protocol_version="2.0.0"
        )
        self.assertEqual(mismatch.status, "error")
        self.assertEqual(
            mismatch.response["error"]["code"], "PROTOCOL_MISMATCH"
        )

    def test_invalid_json_publishes_invalid_message_event(self):
        events = []
        self.root.events.subscribe(
            EventType.INVALID_MESSAGE, lambda event: events.append(event)
        )
        with self.assertRaises(MessageValidationError):
            self.communication.receive("{not json")
        self.assertEqual(len(events), 1)
        self.assertEqual(self.communication.diagnostics()["invalid_count"], 1)


class StateSynchronisationTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.root = create_bx1(
            monotonic_clock=self.clock, wall_clock=self.clock
        )
        self.communication = self.root.communication

    def test_local_battery_subscription_only_updates_on_change(self):
        updates = []
        token = self.communication.subscribe("Subscribe Battery", updates.append)
        self.assertEqual(len(updates), 1)
        self.communication.state_sync.sync()
        self.assertEqual(len(updates), 1)
        self.root.battery.monitor.set_capacity(50)
        self.root.power.refresh()
        self.communication.state_sync.sync()
        self.assertEqual(len(updates), 2)
        self.assertEqual(
            updates[-1]["value"]["status"]["state_of_charge_pct"], 50.0
        )
        self.assertTrue(self.communication.unsubscribe(token))

    def test_new_subscriber_does_not_hide_pending_change_from_existing_client(self):
        first = []
        second = []
        self.communication.subscribe("Battery", first.append)
        self.root.battery.monitor.set_capacity(40)
        self.root.power.refresh()
        self.communication.subscribe("Battery", second.append)
        self.communication.state_sync.sync()
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 1)
        self.assertEqual(
            first[-1]["value"]["status"]["state_of_charge_pct"], 40.0
        )

    def test_health_diagnostics_and_event_subscriptions(self):
        health = []
        diagnostics = []
        events = []
        self.communication.subscribe("Health", health.append)
        self.communication.subscribe("Diagnostics", diagnostics.append)
        self.communication.subscribe("Events", events.append)
        self.root.events.publish(
            EventType.BATTERY_LOW,
            {"state_of_charge_pct": 15},
            source="test",
        )
        self.assertEqual(health[0]["topic"], "health")
        self.assertEqual(diagnostics[0]["topic"], "diagnostics")
        self.assertEqual(events[0]["value"]["type"], "BatteryLow")

    def test_remote_subscriber_receives_event_messages(self):
        self.communication.register_client("dashboard", "1.0.0")
        self.communication.subscribe("Battery", client_id="dashboard")
        update = self.communication.receive_for("dashboard")
        self.assertEqual(update.status, "event")
        self.assertEqual(update.command, "state.battery")
        self.assertEqual(update.payload["topic"], "battery")

    def test_manual_publish(self):
        updates = []
        self.communication.subscribe(
            "Health", updates.append, deliver_initial=False
        )
        count = self.communication.publish("health", {"state": "TEST"})
        self.assertEqual(count, 1)
        self.assertEqual(updates[0]["value"]["state"], "TEST")


class CommunicationEventTests(unittest.TestCase):
    def test_message_sent_received_and_session_events(self):
        root = create_bx1()
        events = []
        root.events.subscribe("*", lambda event: events.append(event.type))
        root.communication.register_client("brain", "1.0.0")
        root.communication.request("brain", "battery.status")
        root.communication.disconnect_client("brain")
        self.assertIn(EventType.CLIENT_CONNECTED.value, events)
        self.assertIn(EventType.MESSAGE_RECEIVED.value, events)
        self.assertIn(EventType.MESSAGE_SENT.value, events)
        self.assertIn(EventType.CLIENT_DISCONNECTED.value, events)


class ConfigurationAndSafetyTests(unittest.TestCase):
    def test_checked_in_configuration_is_safe_in_memory(self):
        for name in ("config.example.json", "config.fresh.json", "config.json"):
            raw = json.loads((ROOT / "python" / name).read_text(encoding="utf-8"))
            self.assertIn("communication", raw["core_services"])
            config = load_core_configuration(raw)
            communication = config["communication"]
            self.assertEqual(communication["transport"], "in_memory")
            self.assertEqual(communication["protocol_version"], "1.0.0")
            self.assertGreater(
                communication["timeout_s"],
                communication["heartbeat_interval_s"],
            )

    def test_unsafe_transport_and_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            load_core_configuration(
                {"communication": {"transport": "websocket"}}
            )
        with self.assertRaises(ValueError):
            load_core_configuration(
                {
                    "communication": {
                        "heartbeat_interval_s": 10,
                        "timeout_s": 5,
                    }
                }
            )

    def test_communication_modules_import_no_network_or_hardware_libraries(self):
        banned = {
            "socket",
            "http",
            "urllib",
            "websockets",
            "paho",
            "serial",
            "RPi",
            "board",
            "busio",
            "smbus",
            "gpiozero",
            "spidev",
        }
        directory = ROOT / "python" / "bx1_core" / "communication"
        for path in directory.glob("*.py"):
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


if __name__ == "__main__":
    unittest.main()
