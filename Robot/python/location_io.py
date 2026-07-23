from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


@dataclass
class LocationConfig:
    enabled: bool = True
    mode: str = "static"
    site: str = "workshop"
    room: str = "unknown"
    zone: str = "unknown"
    map_name: str = "default"
    map_x_m: Optional[float] = None
    map_y_m: Optional[float] = None
    heading_deg: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None


class LocationProvider:
    """Small location provider for BX1 body telemetry.

    For the first physical build this is intentionally static/config-driven.
    That gives the Brain App a stable location field now, without pretending we
    have GPS, SLAM or room mapping fitted before those sensors exist.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        loc = cfg.get("location", {}) if isinstance(cfg.get("location"), dict) else {}
        self.cfg = LocationConfig(
            enabled=bool(loc.get("enabled", cfg.get("location_enabled", True))),
            mode=str(loc.get("mode", cfg.get("location_mode", "static"))),
            site=str(loc.get("site", cfg.get("location_site", "workshop"))),
            room=str(loc.get("room", cfg.get("location_room", "unknown"))),
            zone=str(loc.get("zone", cfg.get("location_zone", "unknown"))),
            map_name=str(loc.get("map", cfg.get("location_map", "default"))),
            map_x_m=self._float_or_none(loc.get("map_x_m", cfg.get("location_map_x_m"))),
            map_y_m=self._float_or_none(loc.get("map_y_m", cfg.get("location_map_y_m"))),
            heading_deg=self._float_or_none(loc.get("heading_deg", cfg.get("location_heading_deg"))),
            latitude=self._float_or_none(loc.get("latitude", loc.get("lat", cfg.get("location_latitude")))),
            longitude=self._float_or_none(loc.get("longitude", loc.get("lon", cfg.get("location_longitude")))),
            altitude_m=self._float_or_none(loc.get("altitude_m", cfg.get("location_altitude_m"))),
        )

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    def read(self) -> Dict[str, Any]:
        if not self.cfg.enabled:
            return {"schema": "bx1.location.v1", "mode": "disabled", "updated_at": now_iso()}
        packet: Dict[str, Any] = {
            "schema": "bx1.location.v1",
            "mode": self.cfg.mode,
            "source": "uno_q_config",
            "site": self.cfg.site,
            "room": self.cfg.room,
            "zone": self.cfg.zone,
            "map": self.cfg.map_name,
            "updated_at": now_iso(),
        }
        optional = {
            "map_x_m": self.cfg.map_x_m,
            "map_y_m": self.cfg.map_y_m,
            "heading_deg": self.cfg.heading_deg,
            "latitude": self.cfg.latitude,
            "longitude": self.cfg.longitude,
            "altitude_m": self.cfg.altitude_m,
        }
        for key, value in optional.items():
            if value is not None:
                packet[key] = value
        return packet
