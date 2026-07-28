from __future__ import annotations

import socket
from typing import List

from ..health import HealthState
from .base import CorePlugin


class NetworkPlugin(CorePlugin):
    name = "network"
    version = "1.0"

    def update(self) -> None:
        context = self._require_context()
        addresses = self._addresses()
        selected = next(
            (address for address in addresses if not address.startswith("127.")),
            addresses[0] if addresses else None,
        )
        context.state.set_many(
            {
                "network.ip": selected,
                "network.signal": None,
                "network.state": "online" if selected else "unavailable",
            },
            source="plugin.network",
        )
        self._set_health(
            HealthState.HEALTHY if selected else HealthState.WARNING,
            {
                "reason": (
                    "Network address discovered"
                    if selected
                    else "No network address discovered"
                ),
                "addresses": addresses,
                "signal_adapter": "not_implemented",
            },
        )

    @staticmethod
    def _addresses() -> List[str]:
        try:
            values = {
                item[4][0]
                for item in socket.getaddrinfo(
                    socket.gethostname(), None, socket.AF_INET
                )
                if item[4] and item[4][0]
            }
            return sorted(values)
        except OSError:
            return []


PLUGIN_CLASS = NetworkPlugin
