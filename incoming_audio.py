import asyncio
import json
import websockets
import settings.config as config

class IncomingAudioServer:
    def __init__(self):
        self.audio_queue = asyncio.Queue(maxsize=config.INCOMING_AUDIO_QUEUE_BLOCKS)
        self.connected_websocket = None
        self.robot_stream_info = {}
        self.total_audio_bytes = 0
        self.dropped_blocks = 0

    async def _queue_audio(self, pcm: bytes):
        if self.audio_queue.full():
            try:
                self.audio_queue.get_nowait()
                self.dropped_blocks += 1
            except asyncio.QueueEmpty:
                pass
        try:
            self.audio_queue.put_nowait(pcm)
        except asyncio.QueueFull:
            self.dropped_blocks += 1

    async def _handle_robot(self, websocket):
        self.connected_websocket = websocket
        print("\n==============================================")
        print("LEO AUDIO LINK CONNECTED")
        print(f"Remote: {websocket.remote_address}")
        print("==============================================\n")

        try:
            async for message in websocket:
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        print(f"[NET] Invalid text message: {message!r}")
                        continue

                    if data.get("type") == "audio_stream_start":
                        self.robot_stream_info = data
                        print(
                            "[NET] Robot audio format: "
                            f"{data.get('sample_rate')} Hz, "
                            f"{data.get('channels')} ch, "
                            f"{data.get('format')}"
                        )
                    else:
                        print(f"[NET] Control: {data}")
                    continue

                self.total_audio_bytes += len(message)
                await self._queue_audio(message)

        except websockets.ConnectionClosed as exc:
            print(f"[NET] LEO disconnected: {exc}")
        finally:
            if self.connected_websocket is websocket:
                self.connected_websocket = None

    async def start(self):
        server = await websockets.serve(
            self._handle_robot,
            config.BRAIN_HOST,
            config.BRAIN_AUDIO_PORT,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )
        print("\nBX1 Brain Audio Server")
        print("======================")
        print(f"Listening on ws://{config.BRAIN_HOST}:{config.BRAIN_AUDIO_PORT}")
        print("Waiting for LEO...\n")
        return server

    async def send_json(self, data: dict) -> bool:
        ws = self.connected_websocket
        if ws is None:
            return False
        await ws.send(json.dumps(data))
        return True

    async def send_binary(self, data: bytes) -> bool:
        ws = self.connected_websocket
        if ws is None:
            return False
        await ws.send(data)
        return True
