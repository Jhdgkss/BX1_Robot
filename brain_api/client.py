"""Client used by optional BX1 Brain scripts."""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import websockets

from .commands import API_ID, DEFAULT_HOST, DEFAULT_PORT


def default_url():
    return os.environ.get("BX1_BRAIN_API_URL", f"ws://{DEFAULT_HOST}:{DEFAULT_PORT}")


class AsyncBrainClient:
    def __init__(self, url=None):
        self.url = str(url or default_url())
        self.websocket = None
        self._lock = asyncio.Lock()

    async def connect(self):
        if self.websocket is None:
            self.websocket = await websockets.connect(
                self.url,
                max_size=256 * 1024,
                ping_interval=20,
                ping_timeout=20,
            )

    async def close(self):
        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            await websocket.close()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def command(self, name, params=None, timeout=5.0):
        await self.connect()
        request_id = "module-" + uuid.uuid4().hex[:12]
        payload = {
            "api": API_ID,
            "type": "command",
            "id": request_id,
            "name": str(name),
            "params": dict(params or {}),
        }
        async with self._lock:
            await self.websocket.send(json.dumps(payload, separators=(",", ":")))
            while True:
                raw = await asyncio.wait_for(self.websocket.recv(), timeout=float(timeout))
                if isinstance(raw, bytes):
                    continue
                message = json.loads(raw)
                if str(message.get("reply_to") or "") != request_id:
                    continue
                if not bool(message.get("ok", False)):
                    raise RuntimeError(str(message.get("error") or "Brain API command failed"))
                result = message.get("result")
                return dict(result) if isinstance(result, dict) else {"value": result}


async def _one(name, params=None, timeout=5.0):
    async with AsyncBrainClient() as client:
        return await client.command(name, params, timeout=timeout)


def _run(name, params=None, timeout=5.0):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_one(name, params, timeout))
    raise RuntimeError("Use AsyncBrainClient from inside asyncio code")


class DriveAPI:
    def status(self): return _run("drive.status")
    def set_motion(self, forward_percent=0.0, turn_percent=0.0):
        return _run("drive.set_motion", {"forward_percent": float(forward_percent), "turn_percent": float(turn_percent)}, 3.0)
    def forward(self, percent=8.0): return _run("drive.forward", {"percent": float(percent)}, 3.0)
    def reverse(self, percent=8.0): return _run("drive.reverse", {"percent": float(percent)}, 3.0)
    def left(self, percent=8.0): return _run("drive.left", {"percent": float(percent)}, 3.0)
    def right(self, percent=8.0): return _run("drive.right", {"percent": float(percent)}, 3.0)
    def hold(self): return _run("drive.hold", timeout=3.0)
    def stop(self): return _run("drive.stop", timeout=5.0)
    def estop(self): return _run("drive.estop", timeout=5.0)


class BalanceAPI:
    def status(self): return _run("balance.status")
    def parameters(self): return _run("balance.get_parameters")
    def disarm(self): return _run("balance.disarm", timeout=5.0)
    def clear_fault(self): return _run("balance.clear_fault")


class HeadAPI:
    def center(self): return _run("head.center")
    def state(self): return _run("head.get_state")
    def set_pose(self, pan=0.0, pitch=0.0, roll=0.0):
        return _run("head.set_pose", {"pan_deg": float(pan), "pitch_deg": float(pitch), "roll_deg": float(roll)})
    def move(self, pan=0.0, pitch=0.0, roll=0.0):
        return _run("head.move_relative", {"pan_delta_deg": float(pan), "pitch_delta_deg": float(pitch), "roll_delta_deg": float(roll)})


class LEDAPI:
    def task(self, name): return _run("led.task", {"task": str(name)})
    def mode(self, name): return _run("led.set_mode", {"mode": str(name)})
    def all(self, r, g, b, brightness_percent=None):
        params = {"r": int(r), "g": int(g), "b": int(b)}
        if brightness_percent is not None: params["brightness_percent"] = float(brightness_percent)
        return _run("led.set_all", params)
    def pixel(self, led_number, r, g, b):
        return _run("led.set_pixel", {"led_number": int(led_number), "r": int(r), "g": int(g), "b": int(b)})
    def mouth(self, level_percent): return _run("led.set_mouth_level", {"level_percent": int(level_percent)})


class LEO:
    def __init__(self):
        self.drive = DriveAPI()
        self.balance = BalanceAPI()
        self.head = HeadAPI()
        self.led = LEDAPI()
    def status(self): return _run("brain.status")
    def commands(self): return _run("brain.commands")
