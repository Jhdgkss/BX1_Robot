from __future__ import annotations

from typing import Any, Mapping

from ..hardware import ReadOnlyHardwareInventory, observation
from ..health import HealthState
from .base import CorePlugin


class HardwarePlugin(CorePlugin):
    """Read-only inventory publisher; adapters never open a device node."""

    name = "hardware"
    version = "2.0"

    def __init__(self) -> None:
        super().__init__()
        self.inventory: Any = None

    def register(self, context: Any) -> None:
        super().register(context)
        candidate = context.metadata.get("hardware_inventory")
        factory = context.metadata.get("hardware_inventory_factory")
        if candidate is not None:
            self.inventory = candidate
        elif callable(factory):
            self.inventory = factory(context)
        else:
            self.inventory = ReadOnlyHardwareInventory(
                context.config,
                environment=context.metadata.get("hardware_environment"),
                robot_body_client=context.metadata.get("robot_body_client"),
            )

    def update(self) -> None:
        context = self._require_context()
        result = self.inventory.collect()
        timestamp = float(result.get("timestamp", context.clock()))
        source = str(
            result.get("source", "BX1 OS read-only hardware observers")
        )
        quality = str(result.get("quality", "unavailable"))
        body = self._mapping(result.get("robot_body"))
        audio = self._mapping(result.get("audio"))
        audio_telemetry = self._mapping(audio.get("telemetry"))
        state_values = {
            "hardware.inventory": observation(
                result.get("inventory", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.audio.microphones": observation(
                audio.get("microphones", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.audio.speakers": observation(
                audio.get("speakers", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.microphone": observation(
                audio.get("microphones", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.speaker": observation(
                audio.get("speakers", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.camera": observation(
                result.get("camera", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.serial": observation(
                result.get("serial", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.mcu": observation(
                result.get("mcu", {}),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "hardware.imu": observation(
                result.get("imu", {}),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "hardware.servos": observation(
                result.get("servos", {}),
                timestamp=timestamp,
                source="Existing Robot Body configuration",
                quality="configured" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "hardware.motors": observation(
                result.get("motors", {}),
                timestamp=timestamp,
                source="Existing Robot Body configuration",
                quality="configured" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "hardware.touchscreen": observation(
                result.get("touchscreen", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.display": observation(
                result.get("display", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.network": observation(
                result.get("network", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.battery": observation(
                result.get("battery", []),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "hardware.diagnostics": observation(
                result.get("diagnostics", {}),
                timestamp=timestamp,
                source=source,
                quality=quality,
            ),
            "robot_body.connected": observation(
                bool(body.get("connected")),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="observed",
                stale=False,
                error=str(body.get("error", "")),
            ),
            "robot_body.version": observation(
                body.get("version", "unknown"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "robot_body.health": observation(
                body.get("health", "unavailable"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "robot_body.active_faults": observation(
                body.get("active_faults", []),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "robot_body.telemetry": observation(
                self._public_body_state(body),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "audio.input.level_rms": observation(
                audio_telemetry.get("level_rms"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality=audio_telemetry.get("measurement_state", "unavailable"),
                stale=audio_telemetry.get("level_rms") is None,
            ),
            "audio.input.level_peak": observation(
                audio_telemetry.get("level_peak"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality=audio_telemetry.get("measurement_state", "unavailable"),
                stale=audio_telemetry.get("level_peak") is None,
            ),
            "audio.input.noise_floor": observation(
                audio_telemetry.get("noise_floor"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality=audio_telemetry.get("measurement_state", "unavailable"),
                stale=audio_telemetry.get("noise_floor") is None,
            ),
            "audio.input.last_sample_timestamp": observation(
                audio_telemetry.get("last_sample_timestamp"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality=audio_telemetry.get(
                    "measurement_state", "unavailable"
                ),
                stale=audio_telemetry.get("last_sample_timestamp") is None,
            ),
            "audio.input.measurement_state": observation(
                audio_telemetry.get("measurement_state", "unavailable"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="observed",
            ),
            "audio.input.owner": observation(
                "bx1-web.service" if body.get("connected") else "unknown",
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="observed",
            ),
            "audio.output.owner": observation(
                "bx1-web.service" if body.get("connected") else "unknown",
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="observed",
            ),
            "audio.stt.state": observation(
                self._mapping(body.get("stt")).get("state", "unknown"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
            "audio.tts.state": observation(
                self._mapping(body.get("tts")).get("state", "unknown"),
                timestamp=timestamp,
                source="Existing Robot Body",
                quality="proxied" if body.get("connected") else "unavailable",
                stale=not bool(body.get("connected")),
            ),
        }
        context.state.set_many(
            {
                "hardware.observer_only": True,
                "hardware.ownership": False,
                "hardware.actions_requested": False,
                "hardware.devices_opened": False,
                **state_values,
            },
            source="plugin.hardware",
        )
        failures = self._mapping(result.get("adapter_failures"))
        warning = bool(failures) or not bool(body.get("connected"))
        self._set_health(
            HealthState.WARNING if warning else HealthState.HEALTHY,
            {
                "reason": (
                    "Observer discovery completed with degraded sources"
                    if warning
                    else "Observer discovery completed"
                ),
                "hardware_access_attempted": False,
                "ownership": False,
                "devices_opened": False,
                "adapter_failures": failures,
                "robot_body_connected": bool(body.get("connected")),
                "device_count": len(result.get("inventory", [])),
            },
        )

    @staticmethod
    def _mapping(value: Any) -> dict:
        return dict(value) if isinstance(value, Mapping) else {}

    @classmethod
    def _public_body_state(cls, body: Mapping[str, Any]) -> dict:
        return {
            key: body.get(key)
            for key in (
                "connected",
                "version",
                "health",
                "active_faults",
                "latency_ms",
                "source",
                "error",
                "microphone",
                "speaker",
                "stt",
                "tts",
                "mcu",
                "imu",
                "camera",
                "mouth_led",
            )
        }


PLUGIN_CLASS = HardwarePlugin
