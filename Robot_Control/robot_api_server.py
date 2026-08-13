"""PC Brain endpoint for the BX1 unified robot WebSocket API (port 8774).

The robot connects outward to this server. This module owns protocol framing,
request/response correlation and telemetry reception. It contains no GUI or
balance-control logic; Master_Main_GUI.py wires callbacks and GUI commands.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import websockets


API_ID = "bx1.robot.v1"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8774


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class RobotAPIServer:

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        telemetry_callback: Optional[
            Callable[[dict], None]
        ] = None,
        status_callback: Optional[
            Callable[[dict], None]
        ] = None,
    ) -> None:
        self.host = str(host)
        self.port = int(port)

        self.telemetry_callback = (
            telemetry_callback
        )

        self.status_callback = (
            status_callback
        )

        self._server = None
        self._websocket = None

        self._pending: dict[
            str,
            asyncio.Future,
        ] = {}

        self._send_lock = asyncio.Lock()

        self._connected = False
        self._robot_id = ""

    @property
    def connected(self) -> bool:
        return bool(
            self._connected
            and self._websocket is not None
        )

    @property
    def robot_id(self) -> str:
        return self._robot_id

    def _publish_status(
        self,
        event: str,
        **data: Any,
    ) -> None:
        if self.status_callback is None:
            return

        packet = {
            "event": str(event),
            "timestamp": time.time(),
            "connected": self.connected,
            "robot_id": self._robot_id,
            **data,
        }

        try:
            self.status_callback(
                packet
            )

        except Exception as exc:
            print(
                "[ROBOT API] Status callback error: "
                f"{type(exc).__name__}: {exc}"
            )

    def _publish_telemetry(
        self,
        packet: dict,
    ) -> None:
        if self.telemetry_callback is None:
            return

        try:
            self.telemetry_callback(
                dict(packet or {})
            )

        except Exception as exc:
            print(
                "[ROBOT API] Telemetry callback error: "
                f"{type(exc).__name__}: {exc}"
            )

    async def start(self):
        if self._server is not None:
            return self._server

        self._server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            max_size=2 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )

        print(
            "[ROBOT API] PC control/telemetry "
            f"server listening on ws://"
            f"{self.host}:{self.port}"
        )

        self._publish_status(
            "robot_api_listening",
            host=self.host,
            port=self.port,
        )

        return self._server

    async def stop(self) -> None:
        websocket = self._websocket

        self._websocket = None
        self._connected = False

        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass

        self._fail_pending(
            ConnectionError(
                "Robot API stopped"
            )
        )

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self._publish_status(
            "robot_api_stopped"
        )

    def _fail_pending(
        self,
        error: Exception,
    ) -> None:
        pending = list(
            self._pending.values()
        )

        self._pending.clear()

        for future in pending:
            if not future.done():
                future.set_exception(
                    error
                )

    async def _send_json(
        self,
        payload: dict,
    ) -> None:
        websocket = self._websocket

        if websocket is None:
            raise ConnectionError(
                "LEO is not connected to the "
                "Robot API on port 8774"
            )

        async with self._send_lock:
            await websocket.send(
                json.dumps(
                    payload,
                    separators=(",", ":"),
                )
            )

    async def _handler(
        self,
        websocket,
    ) -> None:
        old = self._websocket

        if (
            old is not None
            and old is not websocket
        ):
            try:
                await old.close(
                    code=1012,
                    reason="new robot connection",
                )
            except Exception:
                pass

        self._websocket = websocket
        self._connected = True

        self._publish_status(
            "robot_api_socket_connected",
            remote=str(
                websocket.remote_address
            ),
        )

        try:
            async for raw in websocket:
                if isinstance(
                    raw,
                    bytes,
                ):
                    continue

                try:
                    message = json.loads(
                        raw
                    )

                except json.JSONDecodeError:
                    self._publish_status(
                        "robot_api_bad_json"
                    )
                    continue

                if message.get("api") not in (
                    None,
                    API_ID,
                ):
                    continue

                msg_type = str(
                    message.get(
                        "type",
                        "",
                    )
                )

                if msg_type == "hello":
                    self._robot_id = str(
                        message.get("robot_id")
                        or message.get("name")
                        or "LEO-01"
                    )

                    await self._send_json(
                        {
                            "api": API_ID,
                            "type": "hello_ack",
                            "accepted": True,
                            "api_version": "1.0",
                            "timestamp": _utc_now(),
                        }
                    )

                    self._publish_status(
                        "robot_api_connected",
                        capabilities=(
                            message.get(
                                "capabilities"
                            )
                            or []
                        ),
                    )

                    continue

                if msg_type == "telemetry":
                    self._publish_telemetry(
                        message
                    )
                    continue

                if msg_type == "response":
                    reply_to = str(
                        message.get(
                            "reply_to",
                            "",
                        )
                    )

                    future = self._pending.pop(
                        reply_to,
                        None,
                    )

                    if (
                        future is not None
                        and not future.done()
                    ):
                        future.set_result(
                            message
                        )

                    continue

                if msg_type == "event":
                    self._publish_status(
                        str(
                            message.get("name")
                            or "robot_api_event"
                        ),
                        packet=message,
                    )

        except Exception as exc:
            self._publish_status(
                "robot_api_connection_error",
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

        finally:
            if self._websocket is websocket:
                self._websocket = None
                self._connected = False

                self._fail_pending(
                    ConnectionError(
                        "LEO Robot API disconnected"
                    )
                )

                self._publish_status(
                    "robot_api_disconnected"
                )

    async def send_command(
        self,
        name: str,
        params: Optional[dict] = None,
        *,
        timeout: float = 6.0,
    ) -> dict:
        if not self.connected:
            raise ConnectionError(
                "LEO Robot API is not connected"
            )

        command_id = (
            "pc-"
            + uuid.uuid4().hex[:12]
        )

        payload = {
            "api": API_ID,
            "type": "command",
            "id": command_id,
            "timestamp": _utc_now(),
            "name": str(name),
            "params": dict(
                params
                or {}
            ),
        }

        loop = asyncio.get_running_loop()

        future = loop.create_future()

        self._pending[
            command_id
        ] = future

        try:
            await self._send_json(
                payload
            )

            response = (
                await asyncio.wait_for(
                    future,
                    timeout=float(timeout),
                )
            )

        except Exception:
            self._pending.pop(
                command_id,
                None,
            )
            raise

        if not bool(
            response.get(
                "ok",
                False,
            )
        ):
            error = (
                response.get("error")
                or response.get("message")
                or "Robot rejected command"
            )

            raise RuntimeError(
                str(error)
            )

        return response

    async def arm(self) -> dict:
        return await self.send_command(
            "balance.arm"
        )

    async def disarm(self) -> dict:
        return await self.send_command(
            "balance.disarm",
            timeout=4.0,
        )

    async def balance_status(self) -> dict:
        return await self.send_command(
            "balance.status"
        )

    async def balance_parameters(self) -> dict:
        return await self.send_command(
            "balance.get_parameters"
        )

    async def balance_zero(self) -> dict:
        return await self.send_command(
            "balance.zero"
        )

    async def balance_gyrozero(self) -> dict:
        return await self.send_command(
            "balance.gyrozero",
            timeout=8.0,
        )

    async def balance_clear_fault(self) -> dict:
        return await self.send_command(
            "balance.clear_fault"
        )

    async def set_balance_parameter(
        self,
        parameter: str,
        value: Any,
        *,
        save: bool = False,
    ) -> dict:
        return await self.send_command(
            "balance.set_parameter",
            {
                "parameter": str(parameter),
                "value": value,
                "save": bool(save),
            },
        )

    async def set_balance_parameters(
        self,
        values: dict,
        *,
        save: bool = False,
    ) -> dict:
        return await self.send_command(
            "balance.set_parameters",
            {
                "values": dict(values or {}),
                "save": bool(save),
            },
        )

    async def save_balance_parameters(self) -> dict:
        return await self.send_command(
            "balance.save_parameters"
        )

    async def load_balance_parameters(self) -> dict:
        return await self.send_command(
            "balance.load_saved_parameters"
        )

    async def restore_balance_defaults(
        self,
        *,
        save: bool = False,
    ) -> dict:
        return await self.send_command(
            "balance.restore_config_defaults",
            {"save": bool(save)},
        )

    async def drive_motion(
        self,
        forward_percent: float = 0.0,
        turn_percent: float = 0.0,
    ) -> dict:
        return await self.send_command(
            "drive.set_motion",
            {
                "forward_percent": float(forward_percent),
                "turn_percent": float(turn_percent),
            },
            timeout=2.0,
        )

    async def drive_forward(self, percent: float | None = None) -> dict:
        params = {} if percent is None else {"percent": float(percent)}
        return await self.send_command("drive.forward", params, timeout=2.0)

    async def drive_reverse(self, percent: float | None = None) -> dict:
        params = {} if percent is None else {"percent": float(percent)}
        return await self.send_command("drive.reverse", params, timeout=2.0)

    async def drive_left(self, percent: float | None = None) -> dict:
        params = {} if percent is None else {"percent": float(percent)}
        return await self.send_command("drive.left", params, timeout=2.0)

    async def drive_right(self, percent: float | None = None) -> dict:
        params = {} if percent is None else {"percent": float(percent)}
        return await self.send_command("drive.right", params, timeout=2.0)

    async def drive_hold(self) -> dict:
        return await self.send_command("drive.hold", timeout=2.0)

    async def drive_stop(self) -> dict:
        return await self.send_command("drive.stop", timeout=4.0)
