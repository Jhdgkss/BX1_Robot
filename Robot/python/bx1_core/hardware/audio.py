from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment


class AudioAdapter:
    name = "audio"

    def __init__(self, environment: HardwareEnvironment) -> None:
        self.environment = environment

    def discover(
        self, robot_body: Mapping[str, Any]
    ) -> Tuple[List[DeviceRecord], List[DeviceRecord], Dict[str, Any]]:
        timestamp = self.environment.clock()
        pcm, pcm_error = self.environment.read_text(
            self.environment.proc_root / "asound" / "pcm"
        )
        cards, cards_error = self.environment.read_text(
            self.environment.proc_root / "asound" / "cards"
        )
        names = self._card_names(cards)
        microphones: List[DeviceRecord] = []
        speakers: List[DeviceRecord] = []
        for line in pcm.splitlines():
            match = re.match(r"^\s*(\d+)-(\d+):\s*(.*?)\s*:", line)
            if not match:
                continue
            card, device, description = match.groups()
            alsa = "hw:%s,%s" % (int(card), int(device))
            friendly = names.get(int(card), description.strip() or alsa)
            if "capture" in line.lower():
                microphones.append(
                    self._record(
                        alsa,
                        friendly,
                        "microphone",
                        timestamp,
                        robot_body,
                        {
                            "alsa_device": alsa,
                            "card": int(card),
                            "device": int(device),
                            "description": description.strip(),
                            "metadata_only": True,
                        },
                    )
                )
            if "playback" in line.lower():
                speakers.append(
                    self._record(
                        alsa,
                        friendly,
                        "speaker",
                        timestamp,
                        robot_body,
                        {
                            "alsa_device": alsa,
                            "card": int(card),
                            "device": int(device),
                            "description": description.strip(),
                            "metadata_only": True,
                        },
                    )
                )

        microphones = self._merge_body_devices(
            microphones,
            self._mapping(robot_body.get("microphone")),
            "microphone",
            timestamp,
            robot_body,
        )
        speakers = self._merge_body_devices(
            speakers,
            self._mapping(robot_body.get("speaker")),
            "speaker",
            timestamp,
            robot_body,
        )
        configured_mic = str(
            self._mapping(robot_body.get("microphone")).get(
                "configured_device", ""
            )
        )
        configured_speaker = str(
            self._mapping(robot_body.get("speaker")).get(
                "configured_device", ""
            )
        )
        if configured_mic and not self._has_device(
            microphones, configured_mic
        ):
            microphones.append(
                self._configured_only(
                    configured_mic, "microphone", timestamp, robot_body
                )
            )
        if configured_speaker and not self._has_device(
            speakers, configured_speaker
        ):
            speakers.append(
                self._configured_only(
                    configured_speaker, "speaker", timestamp, robot_body
                )
            )
        level = self._mapping(
            self._mapping(robot_body.get("microphone")).get("level")
        )
        telemetry = {
            "level_rms": self._metric(
                level, "rms_dbfs", "level_rms", "rms", "dbfs"
            ),
            "level_peak": self._metric(
                level, "peak_dbfs", "level_peak", "peak"
            ),
            "noise_floor": self._metric(
                level, "noise_floor_dbfs", "noise_floor"
            ),
            "last_sample_timestamp": self._metric(
                level, "timestamp", "updated_at", "last_sample_timestamp"
            ),
            "measurement_state": (
                "proxied_from_robot_body"
                if level
                else "measurement_unavailable_while_owned"
                if robot_body.get("connected")
                else "unavailable"
            ),
            "alsa_tools": {
                "arecord": self.environment.tool("arecord") or "missing",
                "aplay": self.environment.tool("aplay") or "missing",
                "amixer": self.environment.tool("amixer") or "missing",
            },
            "metadata_errors": [
                error
                for error in (pcm_error, cards_error)
                if error and "No such file" not in error
            ],
        }
        return microphones, speakers, telemetry

    def _record(
        self,
        device_id: str,
        name: str,
        category: str,
        timestamp: float,
        robot_body: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> DeviceRecord:
        owned = bool(robot_body.get("connected"))
        settings = self._mapping(
            robot_body.get(
                "microphone" if category == "microphone" else "speaker"
            )
        )
        configured = str(settings.get("configured_device", ""))
        is_default = configured in {"", "default"} or configured == device_id
        return DeviceRecord(
            device_id="%s:%s" % (category, device_id),
            name=name,
            category=category,
            present=True,
            available=not owned,
            ownership="bx1-web.service" if owned else "unclaimed",
            health=DeviceHealth(
                "owned_elsewhere" if owned else "detected",
                (
                    "Owned by Existing Robot Body; control blocked"
                    if owned
                    else "Detected from ALSA metadata"
                ),
            ),
            details={
                **dict(details),
                "configured": configured == device_id,
                "default": is_default,
                "current_format": settings.get("current_format"),
                "supported_sample_rates": settings.get(
                    "supported_sample_rates", []
                ),
                "supported_channel_counts": settings.get(
                    "supported_channel_counts", []
                ),
                "sample_rate": self._mapping(settings.get("settings")).get(
                    "sample_rate"
                ),
                "channels": self._mapping(settings.get("settings")).get(
                    "mic_channels",
                    self._mapping(settings.get("settings")).get("channels"),
                ),
                "volume": settings.get("volume"),
                "muted": settings.get("muted"),
            },
            last_seen=timestamp,
            telemetry={},
            capabilities={
                "metadata": True,
                "live_measurement": False,
                "control": False,
            },
            source="ALSA metadata + Existing Robot Body",
        )

    def _merge_body_devices(
        self,
        records: List[DeviceRecord],
        settings: Mapping[str, Any],
        category: str,
        timestamp: float,
        robot_body: Mapping[str, Any],
    ) -> List[DeviceRecord]:
        known = {
            str(item.details.get("alsa_device", "")): item for item in records
        }
        for raw in settings.get("devices", []):
            if not isinstance(raw, Mapping):
                continue
            device = str(
                raw.get("device", raw.get("id", raw.get("name", "")))
            ).strip()
            if not device or device in known:
                continue
            records.append(
                self._record(
                    device,
                    str(
                        raw.get(
                            "description",
                            raw.get("label", raw.get("name", device)),
                        )
                    ),
                    category,
                    timestamp,
                    robot_body,
                    {
                        "alsa_device": device,
                        "card": raw.get("card"),
                        "device": raw.get("device_number"),
                        "body_reported": True,
                    },
                )
            )
            known[device] = records[-1]
        return records

    @staticmethod
    def _has_device(records: List[DeviceRecord], device: str) -> bool:
        return any(
            str(item.details.get("alsa_device", "")) == device
            for item in records
        )

    def _configured_only(
        self,
        device: str,
        category: str,
        timestamp: float,
        robot_body: Mapping[str, Any],
    ) -> DeviceRecord:
        return DeviceRecord(
            device_id="%s:configured:%s" % (category, device),
            name=device,
            category=category,
            present=False,
            available=False,
            ownership=(
                "bx1-web.service"
                if robot_body.get("connected")
                else "unknown"
            ),
            health=DeviceHealth(
                "unavailable",
                "Configured by Existing Robot Body but not independently detected",
            ),
            details={"configured": True, "alsa_device": device},
            last_seen=timestamp if robot_body.get("connected") else None,
            error="device_not_detected",
            capabilities={"metadata": True, "control": False},
            source="Existing Robot Body",
        )

    @staticmethod
    def _card_names(value: str) -> Dict[int, str]:
        result: Dict[int, str] = {}
        for line in value.splitlines():
            match = re.match(r"^\s*(\d+)\s+\[([^\]]+)\s*\]:\s*(.*)$", line)
            if match:
                result[int(match.group(1))] = (
                    match.group(3).strip() or match.group(2).strip()
                )
        return result

    @staticmethod
    def _mapping(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _metric(value: Mapping[str, Any], *names: str) -> Any:
        for name in names:
            if name in value:
                return value[name]
        return None
