"""BX1 / LEO head-servo WebSocket server - PC side.

The robot initiates the WebSocket connection to this server on port 8773.
Master_Main_GUI.py sends high-level logical commands through this class and
receives state packets from the robot for GUI feedback.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Callable, Dict, Optional

import websockets


class HeadServoServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8773,
        *,
        state_callback: Optional[Callable[[Dict], None]] = None,
        status_callback: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        self.host = str(host)
        self.port = int(port)
        self.state_callback = state_callback
        self.status_callback = status_callback

        self.server = None
        self.websocket = None
        self.connected = False
        self.client = ""
        self.last_state: Dict = {}
        self._send_lock = asyncio.Lock()

    def _publish_status(self, event: str, **extra) -> None:
        packet = {
            "event": str(event),
            "connected": bool(self.connected),
            "client": self.client,
            "port": self.port,
            "timestamp": time.time(),
            **extra,
        }

        if callable(self.status_callback):
            self.status_callback(packet)

    async def start(self):
        if self.server is not None:
            return self.server

        self.server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            max_size=64 * 1024,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
        )

        print(
            f"[HEAD] PC control server listening on "
            f"ws://{self.host}:{self.port}"
        )

        self._publish_status("head_server_started")
        return self.server

    async def stop(self) -> None:
        websocket = self.websocket
        self.websocket = None

        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass

        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        self.connected = False
        self.client = ""
        self._publish_status("head_server_stopped")

    async def _handler(self, websocket, path=None) -> None:
        remote = getattr(websocket, "remote_address", None)

        # Only one robot head-control connection is expected. Replace a stale
        # socket if LEO reconnects.
        old_socket = self.websocket
        if old_socket is not None and old_socket is not websocket:
            try:
                await old_socket.close()
            except Exception:
                pass

        self.websocket = websocket
        self.connected = True
        self.client = str(remote or "")

        print(f"[HEAD] Robot head controller connected: {self.client}")
        self._publish_status("head_client_connected")

        # Ask for an immediate state snapshot so the GUI is populated even
        # before the first movement button is pressed.
        try:
            await websocket.send(
                json.dumps({"type": "head_state_request"})
            )
        except Exception:
            pass

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    continue

                try:
                    packet = json.loads(message)
                except json.JSONDecodeError:
                    continue

                packet_type = str(packet.get("type", ""))

                if packet_type == "head_state":
                    self.last_state = dict(packet)
                    if callable(self.state_callback):
                        self.state_callback(self.last_state)

                elif packet_type == "head_error":
                    self._publish_status(
                        "head_robot_error",
                        error=str(packet.get("error", "unknown")),
                    )

        except websockets.ConnectionClosed:
            pass

        except Exception as exc:
            self._publish_status(
                "head_client_error",
                error=f"{type(exc).__name__}: {exc}",
            )

        finally:
            if self.websocket is websocket:
                self.websocket = None
                self.connected = False
                self.client = ""

            print("[HEAD] Robot head controller disconnected.")
            self._publish_status("head_client_disconnected")

    async def _send(self, payload: Dict) -> bool:
        websocket = self.websocket

        if websocket is None or not self.connected:
            self._publish_status(
                "head_command_rejected",
                error="robot_head_not_connected",
            )
            return False

        async with self._send_lock:
            try:
                await websocket.send(json.dumps(dict(payload)))
                return True
            except Exception as exc:
                self._publish_status(
                    "head_send_error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                return False

    async def move(
        self,
        *,
        pan_delta: float = 0.0,
        pitch_delta: float = 0.0,
        roll_delta: float = 0.0,
    ) -> bool:
        return await self._send({
            "type": "head_move",
            "pan_delta": float(pan_delta),
            "pitch_delta": float(pitch_delta),
            "roll_delta": float(roll_delta),
        })

    async def set_pose(
        self,
        *,
        pan: float,
        pitch: float,
        roll: float,
    ) -> bool:
        return await self._send({
            "type": "head_set",
            "pan": float(pan),
            "pitch": float(pitch),
            "roll": float(roll),
        })

    async def center(self) -> bool:
        return await self._send({"type": "head_center"})

    async def request_state(self) -> bool:
        return await self._send({"type": "head_state_request"})
