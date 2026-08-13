"""
BX1 GUI Robot Connection Settings
==================================

User-editable connection preferences are stored in:
    settings/gui_settings.json

settings/config.py is deliberately NOT rewritten by the GUI.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Dict, Tuple


DEFAULT_SETTINGS = {
    "robot_connection": {
        "preferred": "LOCAL",
        "local_ip": "192.168.68.54",
        "tailscale_ip": "100.72.130.12",
        "web_port": 8088
    }
}


class RobotConnectionSettings:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parent.parent
        self.settings_path = (
            self.project_root
            / "settings"
            / "gui_settings.json"
        )

        self.data = {}
        self.load()

    def load(self) -> Dict:
        data = {}

        if self.settings_path.exists():
            try:
                with self.settings_path.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    data = json.load(file)
            except Exception:
                data = {}

        defaults = DEFAULT_SETTINGS["robot_connection"]
        existing = data.get("robot_connection", {})

        self.data = {
            "robot_connection": {
                "preferred": str(
                    existing.get(
                        "preferred",
                        defaults["preferred"],
                    )
                ).upper(),
                "local_ip": str(
                    existing.get(
                        "local_ip",
                        defaults["local_ip"],
                    )
                ).strip(),
                "tailscale_ip": str(
                    existing.get(
                        "tailscale_ip",
                        defaults["tailscale_ip"],
                    )
                ).strip(),
                "web_port": int(
                    existing.get(
                        "web_port",
                        defaults["web_port"],
                    )
                ),
            }
        }

        return self.data

    def save(
        self,
        *,
        local_ip: str,
        tailscale_ip: str,
        preferred: str,
        web_port: int = 8088,
    ) -> None:
        preferred = str(preferred).upper().strip()

        if preferred not in {
            "LOCAL",
            "TAILSCALE",
        }:
            preferred = "LOCAL"

        self.data = {
            "robot_connection": {
                "preferred": preferred,
                "local_ip": str(local_ip).strip(),
                "tailscale_ip": str(tailscale_ip).strip(),
                "web_port": int(web_port),
            }
        }

        self.settings_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.settings_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self.data,
                file,
                indent=2,
            )

    def connection(self) -> Dict:
        return dict(
            self.data["robot_connection"]
        )

    def address_for(
        self,
        connection_type: str,
    ) -> str:
        connection_type = str(
            connection_type
        ).upper()

        connection = self.connection()

        if connection_type == "TAILSCALE":
            return connection["tailscale_ip"]

        return connection["local_ip"]

    def selected(self) -> Tuple[str, str]:
        connection = self.connection()
        connection_type = connection["preferred"]

        return (
            connection_type,
            self.address_for(connection_type),
        )

    def test(
        self,
        connection_type: str,
        timeout: float = 2.0,
    ) -> Tuple[bool, str]:
        """
        Test whether the robot's web/control port is reachable.

        This does not start the BX1 audio pipeline; it is only a
        simple reachability test for the selected robot address.
        """
        connection = self.connection()

        host = self.address_for(
            connection_type
        )
        port = int(
            connection.get(
                "web_port",
                8088,
            )
        )

        if not host:
            return False, "No IP address has been configured."

        try:
            with socket.create_connection(
                (host, port),
                timeout=timeout,
            ):
                pass

            return (
                True,
                f"Robot reachable at {host}:{port}",
            )

        except Exception as exc:
            return (
                False,
                f"Could not reach {host}:{port}\n"
                f"{type(exc).__name__}: {exc}",
            )
