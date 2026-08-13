"""Local API for optional BX1 Brain scripts.

Flow:
    module -> bx1.brain.v1 -> Master -> bx1.robot.v1 -> LEO
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import websockets

from .commands import API_ID, DEFAULT_HOST, DEFAULT_PORT, LOCAL_COMMANDS, ROBOT_COMMANDS


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class BrainAPIServer:
    def __init__(self, *, robot_api, host=DEFAULT_HOST, port=DEFAULT_PORT, led_task_callback=None):
        self.robot_api = robot_api
        self.host = str(host)
        self.port = int(port)
        self.led_task_callback = led_task_callback
        self._server = None
        self.started_at = 0.0

    @property
    def robot_connected(self):
        return bool(self.robot_api is not None and getattr(self.robot_api, "connected", False))

    async def start(self):
        if self._server is not None:
            return self._server
        self._server = await websockets.serve(
            self._handler,
            self.host,
            self.port,
            max_size=256 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )
        self.started_at = time.time()
        print(f"[BRAIN API] Listening on ws://{self.host}:{self.port}")
        print("[BRAIN API] Optional module balance ARM: DISABLED")
        return self._server

    async def stop(self):
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        print("[BRAIN API] Stopped.")

    async def _send(self, websocket, request_id, ok, result=None, error=""):
        packet = {
            "api": API_ID,
            "type": "response",
            "reply_to": str(request_id or ""),
            "timestamp": _utc_now(),
            "ok": bool(ok),
        }
        if ok:
            packet["result"] = result if result is not None else {}
        else:
            packet["error"] = str(error or "Command failed")
        await websocket.send(json.dumps(packet, separators=(",", ":")))

    async def _handler(self, websocket):
        async for raw in websocket:
            if isinstance(raw, bytes):
                continue
            request_id = ""
            try:
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError("Message must be a JSON object")
                request_id = str(message.get("id") or "")
                if message.get("api") not in (None, API_ID):
                    raise ValueError("Wrong API identifier")
                if str(message.get("type") or "") != "command":
                    raise ValueError("Message type must be command")
                name = str(message.get("name") or "").strip()
                params = message.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("params must be an object")
                result = await self._execute(name, params)
                await self._send(websocket, request_id, True, result=result)
            except Exception as exc:
                await self._send(
                    websocket,
                    request_id,
                    False,
                    error=f"{type(exc).__name__}: {exc}",
                )

    async def _execute(self, name, params):
        if name == "brain.status":
            return {
                "api": API_ID,
                "robot_connected": self.robot_connected,
                "robot_id": str(getattr(self.robot_api, "robot_id", "") or ""),
                "module_api": f"ws://{self.host}:{self.port}",
                "external_arm": False,
                "uptime_seconds": max(0.0, time.time() - self.started_at) if self.started_at else 0.0,
            }

        if name == "brain.commands":
            return {"commands": sorted(ROBOT_COMMANDS | LOCAL_COMMANDS)}

        if name == "led.task":
            task = str(params.get("task") or params.get("name") or "").strip()
            if not task:
                raise ValueError("led.task requires task")
            if self.led_task_callback is None:
                raise RuntimeError("LED task engine is unavailable")
            self.led_task_callback(task)
            return {"task": task}

        if name == "balance.arm":
            raise PermissionError("Optional modules may not ARM LEO. Use the normal GUI ARM control.")

        if name not in ROBOT_COMMANDS:
            raise PermissionError(f"Command '{name}' is not exposed by bx1.brain.v1")

        if not self.robot_connected:
            raise ConnectionError("LEO Robot API is not connected")

        timeout = 6.0
        if name.startswith("drive."):
            timeout = 2.5
        if name in {"balance.disarm", "drive.stop", "drive.estop"}:
            timeout = 4.0

        response = await self.robot_api.send_command(name, dict(params), timeout=timeout)
        if isinstance(response, dict) and isinstance(response.get("result"), dict):
            return dict(response["result"])
        if isinstance(response, dict):
            return dict(response)
        return {"value": response}
