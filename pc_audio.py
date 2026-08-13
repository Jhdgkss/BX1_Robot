# ============================================================
# BX1 PC AUDIO PLAYER
# ============================================================
#
# Receives already-generated 16-bit PCM audio from tts_engine.py
# via main_Local.py, creates one WAV file, and plays that WAV on
# the local Windows PC.
#
# This module performs NO TTS generation and NO networking.
#
# AUDIO FLOW
# ----------
#
#     tts_engine.py
#          |
#          | start_tts / send_pcm16 / end_tts
#          v
#     main_Local.py
#          |
#          v
#     pc_audio.py
#          |
#          v
#      WAV file
#          |
#          v
#     PC speakers
#
# ============================================================

from pathlib import Path
import tempfile
import threading
import wave
import winsound


# ============================================================
# AUDIO FORMAT
# ============================================================

DEFAULT_SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2

# Laptop/Windows audio devices can take a short time to wake up.
# Add silence before and after the generated PCM so the first and
# last spoken samples are not lost by the physical audio device.
#
# These values do NOT alter Qwen's speech; they only pad the WAV.

PRE_ROLL_MS = 250
POST_ROLL_MS = 300


# ============================================================
# PC AUDIO OUTPUT
# ============================================================

class PCAudioOutput:

    def __init__(self):

        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._pcm_parts = []
        self._lock = threading.RLock()
        self.started = False
        self.last_wav_path = None


    # ========================================================
    # START MODULE
    # ========================================================

    def start(self):

        with self._lock:

            if self.started:
                return

            self.started = True

        print()
        print("==============================================")
        print(" BX1 PC AUDIO PLAYER")
        print("==============================================")
        print("Speech generation : EXTERNAL")
        print("Robot streaming   : DISABLED")
        print("sounddevice       : NOT USED")
        print("Playback          : WAV -> Windows speakers")
        print(f"Pre-roll silence  : {PRE_ROLL_MS} ms")
        print(f"Post-roll silence : {POST_ROLL_MS} ms")
        print("==============================================")
        print()


    # ========================================================
    # START ONE TTS REPLY
    # ========================================================

    def start_tts(
        self,
        sample_rate=DEFAULT_SAMPLE_RATE,
    ):

        if not self.started:
            self.start()

        with self._lock:

            self.sample_rate = int(sample_rate)

            # Start a completely fresh PCM buffer for this reply.
            self._pcm_parts = []

        print(
            f"[PC AUDIO] Starting new reply "
            f"({self.sample_rate} Hz)."
        )

        return True


    # ========================================================
    # RECEIVE GENERATED PCM
    # ========================================================

    def send_pcm16(
        self,
        pcm_data: bytes,
    ):

        if not pcm_data:
            return False

        with self._lock:

            # Copy the bytes so the source buffer can safely go
            # out of scope after this function returns.
            self._pcm_parts.append(
                bytes(pcm_data)
            )

        return True


    # ========================================================
    # SILENCE GENERATOR
    # ========================================================

    @staticmethod
    def _silence_bytes(
        milliseconds,
        sample_rate,
    ):

        sample_count = int(
            sample_rate
            * milliseconds
            / 1000.0
        )

        # PCM16 mono silence = two zero bytes per sample.
        return b"\x00\x00" * sample_count


    # ========================================================
    # CREATE WAV AND PLAY IT
    # ========================================================

    def end_tts(self):

        with self._lock:

            if not self._pcm_parts:

                print(
                    "[PC AUDIO] No generated audio received."
                )

                return False

            generated_pcm = b"".join(
                self._pcm_parts
            )

            self._pcm_parts = []

            sample_rate = self.sample_rate


        # ----------------------------------------------------
        # ADD AUDIO DEVICE PRE-ROLL / POST-ROLL
        # ----------------------------------------------------

        pre_roll = self._silence_bytes(
            PRE_ROLL_MS,
            sample_rate,
        )

        post_roll = self._silence_bytes(
            POST_ROLL_MS,
            sample_rate,
        )

        playback_pcm = (
            pre_roll
            + generated_pcm
            + post_roll
        )


        # ----------------------------------------------------
        # CREATE TEMPORARY WAV
        # ----------------------------------------------------

        wav_path = (
            Path(
                tempfile.gettempdir()
            )
            / "bx1_leo_reply.wav"
        )

        with wave.open(
            str(wav_path),
            "wb",
        ) as wav_file:

            wav_file.setnchannels(
                CHANNELS
            )

            wav_file.setsampwidth(
                SAMPLE_WIDTH_BYTES
            )

            wav_file.setframerate(
                sample_rate
            )

            wav_file.writeframes(
                playback_pcm
            )

        self.last_wav_path = wav_path


        generated_duration = (
            len(generated_pcm)
            / (
                sample_rate
                * CHANNELS
                * SAMPLE_WIDTH_BYTES
            )
        )

        playback_duration = (
            len(playback_pcm)
            / (
                sample_rate
                * CHANNELS
                * SAMPLE_WIDTH_BYTES
            )
        )

        print(
            f"[PC AUDIO] Generated speech: "
            f"{generated_duration:.2f}s"
        )

        print(
            f"[PC AUDIO] Playback WAV: "
            f"{playback_duration:.2f}s "
            f"(includes {PRE_ROLL_MS} ms pre-roll + "
            f"{POST_ROLL_MS} ms post-roll)"
        )

        print(
            f"[PC AUDIO] WAV created: "
            f"{wav_path}"
        )

        print(
            "[PC AUDIO] Playing on PC..."
        )


        # ----------------------------------------------------
        # WINDOWS WAV PLAYBACK
        # ----------------------------------------------------
        #
        # PlaySound is synchronous by default when SND_ASYNC
        # is not specified. Therefore this returns only when
        # Windows has finished playing the complete WAV.
        # ----------------------------------------------------

        try:

            winsound.PlaySound(
                str(wav_path),
                winsound.SND_FILENAME,
            )

        except Exception as exc:

            print(
                f"[PC AUDIO] Playback error: "
                f"{type(exc).__name__}: {exc}"
            )

            return False

        print(
            "[PC AUDIO] Playback complete."
        )

        return True


    # ========================================================
    # STOP / CLOSE
    # ========================================================

    def stop(self):

        with self._lock:

            self._pcm_parts = []
            self.started = False

        try:

            # Stop any current PlaySound playback.
            winsound.PlaySound(
                None,
                0,
            )

        except Exception:

            pass

        print(
            "[PC AUDIO] Stopped."
        )


    def close(self):

        self.stop()