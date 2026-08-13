"""
BX1 Incoming Video Server - PC Side
====================================

Receives JPEG frames from the robot over WebSocket.

This module does NOT:
  - access the GUI directly
  - run YOLO
  - control the robot camera
  - save frames to disk

Master_Main_GUI.py owns orchestration and supplies callbacks.

Wire protocol for the first implementation:
  - one binary WebSocket message = one complete JPEG frame
  - text messages are ignored except for diagnostics
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import websockets


@dataclass
class VideoStats:
    connected: bool = False
    client: str = ""
    frames_received: int = 0
    bytes_received: int = 0
    fps: float = 0.0
    bandwidth_kbps: float = 0.0
    last_frame_time: float = 0.0


class IncomingVideoServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8772,
        *,
        frame_callback: Optional[
            Callable[[bytes, Dict], None]
        ] = None,
        status_callback: Optional[
            Callable[[Dict], None]
        ] = None,
        max_jpeg_bytes: int = 4 * 1024 * 1024,
    ):
        self.host = str(host)
        self.port = int(port)

        self.frame_callback = frame_callback
        self.status_callback = status_callback

        self.max_jpeg_bytes = int(max_jpeg_bytes)

        self.server = None
        self.stats = VideoStats()

        self._window_started = time.perf_counter()
        self._window_frames = 0
        self._window_bytes = 0

    def _publish_status(
        self,
        event: str,
        **extra,
    ):
        packet = {
            "event": str(event),
            "connected": self.stats.connected,
            "client": self.stats.client,
            "frames_received": self.stats.frames_received,
            "bytes_received": self.stats.bytes_received,
            "fps": round(self.stats.fps, 2),
            "bandwidth_kbps": round(
                self.stats.bandwidth_kbps,
                1,
            ),
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
            max_size=self.max_jpeg_bytes,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
        )

        print(
            f"[VIDEO] PC receiver listening on "
            f"ws://{self.host}:{self.port}"
        )

        self._publish_status(
            "video_server_started",
            host=self.host,
            port=self.port,
        )

        return self.server

    async def stop(self):
        if self.server is None:
            return

        self.server.close()
        await self.server.wait_closed()
        self.server = None

        self.stats.connected = False
        self.stats.client = ""

        self._publish_status(
            "video_server_stopped"
        )

    async def _handler(
        self,
        websocket,
        path=None,
    ):
        remote = getattr(
            websocket,
            "remote_address",
            None,
        )

        self.stats.connected = True
        self.stats.client = str(remote or "")

        self._window_started = time.perf_counter()
        self._window_frames = 0
        self._window_bytes = 0

        print(
            f"[VIDEO] Robot camera connected: "
            f"{self.stats.client}"
        )

        self._publish_status(
            "video_client_connected"
        )

        try:
            async for message in websocket:
                if isinstance(message, str):
                    # Reserved for future metadata/control messages.
                    continue

                jpeg = bytes(message)

                if not jpeg:
                    continue

                if len(jpeg) > self.max_jpeg_bytes:
                    self._publish_status(
                        "video_frame_rejected",
                        reason="frame_too_large",
                        bytes=len(jpeg),
                    )
                    continue

                # Basic JPEG sanity check.
                if not (
                    jpeg.startswith(b"\xff\xd8")
                    and jpeg.endswith(b"\xff\xd9")
                ):
                    self._publish_status(
                        "video_frame_rejected",
                        reason="not_jpeg",
                        bytes=len(jpeg),
                    )
                    continue

                now_wall = time.time()

                self.stats.frames_received += 1
                self.stats.bytes_received += len(jpeg)
                self.stats.last_frame_time = now_wall

                self._window_frames += 1
                self._window_bytes += len(jpeg)

                elapsed = (
                    time.perf_counter()
                    - self._window_started
                )

                if elapsed >= 1.0:
                    self.stats.fps = (
                        self._window_frames
                        / elapsed
                    )

                    self.stats.bandwidth_kbps = (
                        self._window_bytes
                        / 1024.0
                        / elapsed
                    )

                    self._window_started = (
                        time.perf_counter()
                    )
                    self._window_frames = 0
                    self._window_bytes = 0

                metadata = {
                    "timestamp": now_wall,
                    "bytes": len(jpeg),
                    "fps": round(
                        self.stats.fps,
                        2,
                    ),
                    "bandwidth_kbps": round(
                        self.stats.bandwidth_kbps,
                        1,
                    ),
                    "client": self.stats.client,
                    "frame_number": (
                        self.stats.frames_received
                    ),
                }

                if callable(self.frame_callback):
                    try:
                        self.frame_callback(
                            jpeg,
                            metadata,
                        )
                    except Exception as exc:
                        self._publish_status(
                            "video_frame_callback_error",
                            error=(
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                        )

        except websockets.ConnectionClosed:
            pass

        except Exception as exc:
            self._publish_status(
                "video_client_error",
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

        finally:
            self.stats.connected = False
            self.stats.client = ""

            print(
                "[VIDEO] Robot camera disconnected."
            )

            self._publish_status(
                "video_client_disconnected"
            )
