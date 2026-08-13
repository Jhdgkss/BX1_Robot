# ============================================================
# AUDIO TO ROBOT STREAMER
# ============================================================
#
# This file sends LEO's generated TTS audio from the
# Windows Brain PC to the Arduino Q.
#
# The Robot connects to this server using WebSocket port 8771.
#
#
# AUDIO DIRECTIONS
# ----------------
#
# Robot microphone ---> PC     port 8770
#
# PC TTS -----------> Robot    port 8771
#
#
# Keeping the two audio directions separate makes the
# system much easier to understand and debug.
#
# ============================================================


import asyncio
import json
import threading

import websockets


# ============================================================
# SETTINGS
# ============================================================

SERVER_HOST = "0.0.0.0"

SERVER_PORT = 8771


# Qwen produces 24 kHz mono audio.

TTS_SAMPLE_RATE = 24000

TTS_CHANNELS = 1


# Send approximately 100 ms of audio in each WebSocket packet.
#
# 24000 samples per second
# 2 bytes per sample
# 0.1 seconds
#
# 24000 * 2 * 0.1 = 4800 bytes

NETWORK_AUDIO_CHUNK_BYTES = 4800


# ============================================================
# ROBOT AUDIO STREAMER
# ============================================================

class AudioToRobotStreamer:

    def __init__(self):

        # The asyncio event loop used by our background
        # WebSocket server thread.

        self.loop = None


        # Async queue containing messages waiting to be
        # sent to the robot.

        self.send_queue = None


        # Used to stop the WebSocket server.

        self.stop_event = None


        # Windows threading events allow main.py and the
        # TTS thread to check our status.

        self.server_ready = threading.Event()

        self.robot_connected = threading.Event()


        # Background server thread.

        self.server_thread = None


    # ========================================================
    # START SERVER
    # ========================================================

    def start(self):

        print()
        print("==============================================")
        print(" PC -> ROBOT AUDIO SERVER")
        print("==============================================")


        self.server_thread = threading.Thread(

            target=self._thread_main,

            daemon=True,
        )


        self.server_thread.start()


        # Wait until the WebSocket server has actually
        # started listening.

        self.server_ready.wait()


    # ========================================================
    # BACKGROUND THREAD
    # ========================================================

    def _thread_main(self):

        # Create a completely separate asyncio loop for
        # the TTS WebSocket server.

        self.loop = asyncio.new_event_loop()


        asyncio.set_event_loop(
            self.loop
        )


        self.send_queue = asyncio.Queue()

        self.stop_event = asyncio.Event()


        try:

            self.loop.run_until_complete(
                self._server_main()
            )

        finally:

            self.loop.close()


    # ========================================================
    # WEBSOCKET SERVER
    # ========================================================

    async def _server_main(self):

        async with websockets.serve(

            self._handle_robot,

            SERVER_HOST,

            SERVER_PORT,

            max_size=None,

            ping_interval=20,

            ping_timeout=20,
        ):

            print(
                f"Listening on "
                f"ws://{SERVER_HOST}:{SERVER_PORT}"
            )

            print(
                "Waiting for robot speaker connection..."
            )

            print(
                "=============================================="
            )

            print()


            self.server_ready.set()


            # Stay alive until stop() is called.

            await self.stop_event.wait()


    # ========================================================
    # ROBOT CONNECTED
    # ========================================================

    async def _handle_robot(
        self,
        websocket,
    ):

        print()
        print("==============================================")
        print(" ROBOT SPEAKER LINK CONNECTED")
        print("==============================================")


        self.robot_connected.set()


        sender_task = asyncio.create_task(

            self._sender(
                websocket
            )
        )


        try:

            # Wait until the robot disconnects.

            await websocket.wait_closed()


        finally:

            sender_task.cancel()


            try:

                await sender_task

            except asyncio.CancelledError:

                pass


            self.robot_connected.clear()


            # Throw away any speech that was waiting.
            #
            # We do NOT want stale TTS to suddenly play if
            # the robot reconnects later.

            self._clear_send_queue()


            print()
            print(
                "[AUDIO OUT] Robot speaker disconnected."
            )


    # ========================================================
    # SEND QUEUED DATA
    # ========================================================

    async def _sender(
        self,
        websocket,
    ):

        while True:

            message = await self.send_queue.get()


            try:

                await websocket.send(
                    message
                )

            finally:

                self.send_queue.task_done()


    # ========================================================
    # CLEAR OLD AUDIO
    # ========================================================

    def _clear_send_queue(self):

        if self.send_queue is None:
            return


        while True:

            try:

                self.send_queue.get_nowait()

                self.send_queue.task_done()

            except asyncio.QueueEmpty:

                break


    # ========================================================
    # THREAD-SAFE QUEUE FUNCTION
    # ========================================================

    def _queue_message(
        self,
        message,
    ):

        # TTS runs in another thread.
        #
        # loop.call_soon_threadsafe() safely transfers the
        # message into the WebSocket server's asyncio loop.

        if not self.robot_connected.is_set():

            print(
                "[AUDIO OUT] Robot speaker is not connected."
            )

            return False


        self.loop.call_soon_threadsafe(

            self.send_queue.put_nowait,

            message,
        )


        return True


    # ========================================================
    # START A TTS MESSAGE
    # ========================================================

    def start_tts(
        self,
        sample_rate=TTS_SAMPLE_RATE,
    ):

        message = json.dumps(
            {
                "type": "tts_start",

                "sample_rate": sample_rate,

                "channels": TTS_CHANNELS,

                "format": "pcm_s16le",
            }
        )


        print()
        print(
            f"[AUDIO OUT] TTS START "
            f"{sample_rate} Hz"
        )


        return self._queue_message(
            message
        )


    # ========================================================
    # SEND PCM AUDIO
    # ========================================================

    def send_pcm16(
        self,
        pcm_data: bytes,
    ):

        if not pcm_data:
            return


        # Split large generated audio blocks into much smaller
        # network packets.
        #
        # This is important because the Arduino can start
        # playing before an entire multi-second block has been
        # transferred.

        for start in range(
            0,
            len(pcm_data),
            NETWORK_AUDIO_CHUNK_BYTES,
        ):

            chunk = pcm_data[
                start:
                start + NETWORK_AUDIO_CHUNK_BYTES
            ]


            if not self._queue_message(
                chunk
            ):

                break


    # ========================================================
    # END A TTS MESSAGE
    # ========================================================

    def end_tts(self):

        message = json.dumps(
            {
                "type": "tts_end",
            }
        )


        print(
            "[AUDIO OUT] TTS END"
        )


        self._queue_message(
            message
        )


    # ========================================================
    # STOP SERVER
    # ========================================================

    def stop(self):

        if (
            self.loop is None
            or self.stop_event is None
        ):

            return


        print(
            "[AUDIO OUT] Stopping server..."
        )


        self.loop.call_soon_threadsafe(
            self.stop_event.set
        )