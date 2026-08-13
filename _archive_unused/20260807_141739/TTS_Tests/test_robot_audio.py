import asyncio
import wave

from incoming_audio import IncomingAudioServer
from stt_engine import STTEngine


SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2       # 16-bit = 2 bytes
RECORD_SECONDS = 5

BYTES_REQUIRED = (
    SAMPLE_RATE
    * CHANNELS
    * SAMPLE_WIDTH
    * RECORD_SECONDS
)


async def main():

    print("[TEST] Loading Whisper...")
    stt = STTEngine()

    incoming = IncomingAudioServer()

    server = await incoming.start()

    print()
    print("[TEST] Waiting for LEO...")
    print()

    audio = bytearray()

    try:

        while len(audio) < BYTES_REQUIRED:

            pcm_block = await incoming.audio_queue.get()

            audio.extend(pcm_block)

            seconds = (
                len(audio)
                / SAMPLE_RATE
                / SAMPLE_WIDTH
            )

            print(
                f"\r[TEST] Capturing  START TALKING: "
                f"{seconds:.1f} / {RECORD_SECONDS} seconds",
                end="",
                flush=True,
            )

        audio = bytes(
            audio[:BYTES_REQUIRED]
        )

        print()
        print()
        print("[TEST] Capture complete.")

        # ----------------------------------------------------
        # SAVE EXACT AUDIO TO WAV
        # ----------------------------------------------------

        filename = "leo_mic_test.wav"

        with wave.open(filename, "wb") as wav:

            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(audio)

        print(
            f"[TEST] Saved: {filename}"
        )

        # ----------------------------------------------------
        # SEND DIRECTLY TO WHISPER
        # ----------------------------------------------------

        print()
        print("[TEST] Sending complete recording to Whisper...")

        result = await asyncio.to_thread(
            stt.transcribe,
            audio,
        )

        print()
        print("====================================")
        print("WHISPER RESULT")
        print("====================================")

        print(
            repr(result.text)
        )

        print("====================================")

    finally:

        server.close()
        await server.wait_closed()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\nStopped.")