from __future__ import annotations

import copy
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import urlparse


class RobotBodyClient:
    """Allowlisted GET-only client for the production Robot Body API."""

    PATHS = {
        "status": "/api/status",
        "microphones": "/api/mic_devices",
        "speakers": "/api/mic_playback_devices",
    }

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8088",
        *,
        timeout: float = 0.5,
        opener: Optional[Callable[..., Any]] = None,
        clock: Callable[[], float] = time.time,
        max_bytes: int = 1024 * 1024,
    ) -> None:
        parsed = urlparse(str(base_url))
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.port != 8088
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "Robot Body adapter is restricted to loopback port 8088"
            )
        self.base_url = str(base_url).rstrip("/")
        self.timeout = max(0.05, min(float(timeout), 2.0))
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self.max_bytes = max(1024, int(max_bytes))

    def get(self, name: str) -> Dict[str, Any]:
        if name not in self.PATHS:
            raise ValueError("Robot Body endpoint is not allowlisted: %s" % name)
        url = self.base_url + self.PATHS[name]
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Accept": "application/json"},
        )
        started = self.clock()
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(self.max_bytes + 1)
                server = str(response.headers.get("Server", ""))
            if len(raw) > self.max_bytes:
                raise ValueError("Robot Body response exceeded size limit")
            value = json.loads(raw.decode("utf-8", errors="strict"))
            if not isinstance(value, Mapping):
                raise ValueError("Robot Body response is not a JSON object")
            return {
                "ok": True,
                "data": copy.deepcopy(dict(value)),
                "server": server,
                "latency_ms": round((self.clock() - started) * 1000.0, 2),
                "timestamp": self.clock(),
                "error": "",
            }
        except (TimeoutError, socket.timeout):
            error = "timeout"
        except urllib.error.HTTPError as exc:
            error = "http_%s" % exc.code
        except urllib.error.URLError as exc:
            error = (
                "timeout"
                if isinstance(exc.reason, (TimeoutError, socket.timeout))
                else "unavailable"
            )
        except (UnicodeError, json.JSONDecodeError, ValueError):
            error = "malformed_response"
        except OSError:
            error = "unavailable"
        return {
            "ok": False,
            "data": {},
            "server": "",
            "latency_ms": round((self.clock() - started) * 1000.0, 2),
            "timestamp": self.clock(),
            "error": error,
        }

    def collect(self) -> Dict[str, Any]:
        status_result = self.get("status")
        if not status_result["ok"]:
            return self._offline(status_result)
        status = status_result["data"]
        microphone_result = self.get("microphones")
        speaker_result = self.get("speakers")
        body_version = self._first(
            status,
            (
                ("identity", "version"),
                ("identity", "app_version"),
                ("robot_profile", "version"),
                ("bx1_os", "release_version"),
            ),
        )
        server = status_result.get("server", "")
        if not body_version and "/" in server:
            body_version = server.rsplit("/", 1)[-1]
        state = self._mapping(status.get("state"))
        sensors = self._mapping(state.get("sensors"))
        doctor = self._mapping(status.get("hardware_doctor"))
        audio = self._mapping(status.get("audio"))
        mic = self._mapping(status.get("mic"))
        voice_runtime = self._mapping(status.get("voice_runtime"))
        vision = self._mapping(status.get("vision_awareness"))
        hardware = self._mapping(status.get("hardware"))
        mic_level = self._mapping(status.get("mic_level")).get("level", {})
        faults = self._faults(state, doctor, status.get("events"))
        return {
            "connected": True,
            "version": str(body_version or "unknown"),
            "health": "warning" if faults else "healthy",
            "active_faults": faults,
            "timestamp": status_result["timestamp"],
            "latency_ms": status_result["latency_ms"],
            "source": "Existing Robot Body",
            "error": "",
            "microphone": {
                "configured_device": str(mic.get("mic_device", "")),
                "settings": self._select(
                    mic,
                    (
                        "mic_device",
                        "sample_rate",
                        "mic_channels",
                        "channels",
                        "sample_width",
                        "record_seconds",
                    ),
                ),
                "devices": (
                    microphone_result["data"].get("devices", [])
                    if microphone_result["ok"]
                    else []
                ),
                "device_error": microphone_result["error"],
                "level": copy.deepcopy(
                    mic_level if isinstance(mic_level, Mapping) else {}
                ),
            },
            "speaker": {
                "configured_device": str(
                    audio.get("tts_playback_device", "")
                ),
                "volume": audio.get("tts_volume"),
                "muted": (
                    not bool(audio.get("tts_enabled"))
                    if "tts_enabled" in audio
                    else None
                ),
                "devices": (
                    speaker_result["data"].get("devices", [])
                    if speaker_result["ok"]
                    else []
                ),
                "device_error": speaker_result["error"],
            },
            "stt": {
                "state": str(
                    voice_runtime.get(
                        "state", voice_runtime.get("phase", "unknown")
                    )
                ),
                "listening": bool(
                    voice_runtime.get(
                        "listening", voice_runtime.get("loop_active", False)
                    )
                ),
            },
            "tts": {
                "state": (
                    "enabled" if audio.get("tts_enabled") else "disabled"
                ),
                "backend": str(audio.get("tts_backend", "unknown")),
            },
            "mcu": self._mcu_component(state, sensors, doctor),
            "imu": self._imu_component(state, sensors, doctor),
            "camera": {
                "configured": bool(vision.get("camera_enabled", False)),
                "device": vision.get("camera_device"),
                "state": self._first(
                    state, (("camera",), ("camera_state",))
                )
                or "unknown",
            },
            "mouth_led": self._component(state, doctor, "mouth"),
            "hardware": self._select(
                hardware, ("hardware_registry", "hardware_control")
            ),
        }

    def _offline(self, result: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "connected": False,
            "version": "unknown",
            "health": "unavailable",
            "active_faults": [],
            "timestamp": result.get("timestamp", self.clock()),
            "latency_ms": result.get("latency_ms"),
            "source": "Existing Robot Body",
            "error": str(result.get("error", "unavailable")),
            "microphone": {},
            "speaker": {},
            "stt": {"state": "unknown", "listening": False},
            "tts": {"state": "unknown", "backend": "unknown"},
            "mcu": {"state": "unknown"},
            "imu": {"state": "unknown"},
            "camera": {"state": "unknown"},
            "mouth_led": {"state": "unknown"},
            "hardware": {},
        }

    @staticmethod
    def _mapping(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @classmethod
    def _first(cls, value: Mapping[str, Any], paths: Tuple[Tuple[str, ...], ...]) -> Any:
        for path in paths:
            current: Any = value
            for key in path:
                if not isinstance(current, Mapping) or key not in current:
                    current = None
                    break
                current = current[key]
            if current is not None and current != "":
                return current
        return None

    @staticmethod
    def _select(value: Mapping[str, Any], keys: Tuple[str, ...]) -> Dict[str, Any]:
        return {
            key: copy.deepcopy(value[key])
            for key in keys
            if key in value
        }

    @classmethod
    def _component(
        cls,
        state: Mapping[str, Any],
        doctor: Mapping[str, Any],
        name: str,
    ) -> Dict[str, Any]:
        direct = state.get(name)
        if isinstance(direct, Mapping):
            return copy.deepcopy(dict(direct))
        diagnosis = doctor.get("diagnosis", doctor)
        if isinstance(diagnosis, Mapping):
            candidate = diagnosis.get(name)
            if isinstance(candidate, Mapping):
                return copy.deepcopy(dict(candidate))
        return {"state": str(direct or "unknown")}

    @classmethod
    def _mcu_component(
        cls,
        state: Mapping[str, Any],
        sensors: Mapping[str, Any],
        doctor: Mapping[str, Any],
    ) -> Dict[str, Any]:
        direct = cls._component(state, doctor, "mcu")
        if direct.get("state") != "unknown":
            return direct
        keys = (
            "mcu_ok",
            "mcu_transport_connected",
            "mcu_heartbeat_fresh",
            "mcu_last_update_age_ms",
            "mcu_stale",
            "mcu_health_reason",
        )
        details = cls._select(sensors, keys)
        if not details:
            return direct
        online = all(
            bool(sensors.get(key))
            for key in (
                "mcu_ok",
                "mcu_transport_connected",
                "mcu_heartbeat_fresh",
            )
        )
        details["state"] = "online" if online else "offline"
        details["source"] = "Existing Robot Body sensor telemetry"
        return details

    @classmethod
    def _imu_component(
        cls,
        state: Mapping[str, Any],
        sensors: Mapping[str, Any],
        doctor: Mapping[str, Any],
    ) -> Dict[str, Any]:
        direct = cls._component(state, doctor, "imu")
        if direct.get("state") != "unknown":
            return direct
        keys = (
            "imu_ok",
            "imu_present",
            "imu_initialised",
            "imu_sample_fresh",
            "imu_sample_age_ms",
            "imu_stale",
            "imu_healthy",
            "imu_health_reason",
            "imu_error",
            "imu_source",
            "imu_bus",
            "imu_address",
            "imu_last_update_age_ms",
        )
        details = cls._select(sensors, keys)
        if not details:
            return direct
        healthy = bool(
            sensors.get(
                "imu_healthy",
                sensors.get("imu_ok") and sensors.get("imu_sample_fresh", True),
            )
        )
        present = bool(
            sensors.get("imu_present", sensors.get("imu_initialised", False))
        )
        details["state"] = (
            "fresh" if healthy else "offline" if present else "unavailable"
        )
        details["source"] = "Existing Robot Body sensor telemetry"
        return details

    @staticmethod
    def _faults(
        state: Mapping[str, Any],
        doctor: Mapping[str, Any],
        events: Any,
    ) -> list[Dict[str, Any]]:
        faults = []
        for source_name, source in (("state", state), ("doctor", doctor)):
            values = source.get("faults", []) if isinstance(source, Mapping) else []
            if isinstance(values, list):
                for value in values[:50]:
                    faults.append({"source": source_name, "detail": str(value)[:300]})
        if isinstance(events, list):
            for event in events[-50:]:
                if isinstance(event, Mapping) and str(
                    event.get("level", event.get("type", ""))
                ).lower() in {"error", "fault"}:
                    faults.append(
                        {
                            "source": "events",
                            "detail": str(
                                event.get("message", event.get("detail", "fault"))
                            )[:300],
                        }
                    )
        return faults[:100]
