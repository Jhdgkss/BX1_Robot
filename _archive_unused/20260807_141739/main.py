import asyncio
import math
import time

import numpy as np

from colorama import Fore, Back, Style


# ============================================================
# BX1 MODULES
# ============================================================

from incoming_audio import IncomingAudioServer
from speech_segmenter import SpeechSegmenter
from stt_engine import STTEngine
from transcript_processor import TranscriptProcessor
from llm_client import LLMClient
from audio_to_robot_streamer import AudioToRobotStreamer

# ============================================================
# NEW - TTS
# ============================================================
#
# This imports our Qwen TTS engine.
#
# tts_engine.py should be located in:
#
# C:\Git WorkSpace\BX_Dev\BX1_Dev\tts_engine.py
#
# ============================================================

from tts_engine import QwenTTSEngine


# ============================================================
# AUDIO SEGMENTATION WORKER
# ============================================================
#
# This worker continuously receives raw microphone audio
# from LEO.
#
# It passes that audio into the Voice Activity Detector (VAD).
#
# When the VAD decides that a complete spoken phrase has
# finished, it places that phrase into utterance_queue.
#
# ============================================================

async def segmentation_worker(
    incoming,
    segmenter,
    utterance_queue,
):

    # --------------------------------------------------------
    # Diagnostic counters
    # --------------------------------------------------------

    diagnostic_start = time.monotonic()

    total_bytes = 0
    total_blocks = 0
    total_samples = 0

    sum_squares = 0.0
    maximum_peak = 0


    # --------------------------------------------------------
    # This worker runs continuously.
    # --------------------------------------------------------

    while True:

        # ====================================================
        # WAIT FOR AUDIO FROM ROBOT
        # ====================================================

        pcm_block = await incoming.audio_queue.get()


        # If we reach this point, an actual audio block
        # has arrived from LEO.

        total_bytes += len(pcm_block)

        total_blocks += 1


        # ====================================================
        # AUDIO LEVEL DIAGNOSTIC
        # ====================================================
        #
        # The incoming audio is:
        #
        # 16-bit
        # signed
        # little-endian
        # mono PCM
        #
        # ====================================================

        samples = np.frombuffer(
            pcm_block,
            dtype="<i2",
        )


        if samples.size:

            # Convert before squaring / abs.
            #
            # This prevents int16 overflow around -32768.

            samples_float = samples.astype(
                np.float64
            )

            samples_int = samples.astype(
                np.int32
            )


            sum_squares += float(
                np.sum(
                    samples_float
                    * samples_float
                )
            )


            total_samples += samples.size


            block_peak = int(
                np.max(
                    np.abs(samples_int)
                )
            )


            maximum_peak = max(
                maximum_peak,
                block_peak,
            )


        # ====================================================
        # PRINT AUDIO STATUS ONCE PER SECOND
        # ====================================================

        now = time.monotonic()

        elapsed = (
            now
            - diagnostic_start
        )


        if elapsed >= 1.0:

            if total_samples > 0:

                rms = math.sqrt(
                    sum_squares
                    / total_samples
                )


                if rms > 0:

                    rms_dbfs = (
                        20.0
                        * math.log10(
                            rms
                            / 32768.0
                        )
                    )

                else:

                    rms_dbfs = -100.0


                if maximum_peak > 0:

                    peak_dbfs = (
                        20.0
                        * math.log10(
                            maximum_peak
                            / 32768.0
                        )
                    )

                else:

                    peak_dbfs = -100.0


            else:

                rms_dbfs = -100.0

                peak_dbfs = -100.0


            bytes_per_second = (
                total_bytes
                / elapsed
            )


            # ------------------------------------------------
            # OPTIONAL AUDIO INFORMATION
            # ------------------------------------------------
            #
            # Uncomment this section if you want to see
            # microphone levels continuously.
            #
            # ------------------------------------------------

            """
            print(
                Fore.CYAN
                + (
                    f"[AUDIO] "
                    f"{bytes_per_second / 1024:5.1f} kB/s | "
                    f"{total_blocks:3d} blocks/s | "
                    f"RMS {rms_dbfs:6.1f} dBFS | "
                    f"PEAK {peak_dbfs:6.1f} dBFS"
                )
                + Style.RESET_ALL
            )
            """


            # ------------------------------------------------
            # Reset diagnostic counters for next second.
            # ------------------------------------------------

            diagnostic_start = now

            total_bytes = 0
            total_blocks = 0
            total_samples = 0

            sum_squares = 0.0
            maximum_peak = 0


        # ====================================================
        # PASS AUDIO INTO SPEECH SEGMENTER
        # ====================================================

        completed = segmenter.feed(
            pcm_block
        )


        # There may be zero, one or more completed speech
        # segments returned.

        for utterance in completed:

            print(
                Fore.YELLOW
                + (
                    f"[VAD] Completed utterance: "
                    f"{len(utterance)} bytes"
                )
                + Style.RESET_ALL
            )


            # ------------------------------------------------
            # Prevent the queue growing forever.
            # ------------------------------------------------

            if utterance_queue.full():

                try:

                    utterance_queue.get_nowait()

                except asyncio.QueueEmpty:

                    pass


            # Send completed speech to Whisper.

            await utterance_queue.put(
                utterance
            )


# ============================================================
# WHISPER / LLM / TTS WORKER
# ============================================================
#
# This worker performs the main conversation pipeline:
#
#
#     Speech from LEO
#
#           ↓
#
#     Faster-Whisper
#
#           ↓
#
#     Transcript Processor
#
#           ↓
#
#     Ollama LLM
#
#           ↓
#
#          reply
#
#           ↓
#
#       Qwen TTS
#
#
# ============================================================

async def transcription_worker(
    utterance_queue,
    stt,
    transcript,
    llm,

    # ========================================================
    # NEW - TTS
    # ========================================================
    #
    # We now also pass the TTS engine into this worker.
    #
    # ========================================================

    tts,
):


    while True:

        # ====================================================
        # WAIT FOR A COMPLETE SPEECH UTTERANCE
        # ====================================================

        utterance = await utterance_queue.get()


        print(
            Fore.MAGENTA
            + "[STT] Sending utterance to Whisper..."
            + Style.RESET_ALL
        )


        # ====================================================
        # SPEECH TO TEXT
        # ====================================================
        #
        # Whisper is not asynchronous itself.
        #
        # asyncio.to_thread() lets Whisper perform its work
        # without freezing the rest of the asyncio program.
        #
        # ====================================================

        result = await asyncio.to_thread(
            stt.transcribe,
            utterance,
        )


        # ====================================================
        # NOTHING RECOGNISED
        # ====================================================

        if not result.text:

            print(
                Fore.MAGENTA
                + "[STT] No speech recognised."
                + Style.RESET_ALL
            )

            continue


        # ====================================================
        # PROCESS TRANSCRIPT
        # ====================================================
        #
        # TranscriptProcessor handles things such as:
        #
        #   Leo
        #   Hey Leo
        #   conversation sessions
        #   wake detection
        #   command text
        #
        # ====================================================

        event = transcript.process(
            result.text
        )


        transcript.print_event(
            event,
            result,
        )


        # ====================================================
        # SEND COMMAND TO LLM
        # ====================================================
        #
        # Only send speech to Ollama when TranscriptProcessor
        # says that it belongs to the active conversation.
        #
        # ====================================================

        if (
            event.send_to_llm
            and llm.enabled
        ):

            print(
                Fore.GREEN
                + "    -> Sending to LLM..."
                + Style.RESET_ALL
            )


            try:

                # =================================================
                # ASK OLLAMA
                # =================================================
                #
                # event.command_text
                #
                # is the USER'S command/question.
                #
                # For example:
                #
                #     "How are you?"
                #
                # =================================================

                reply = await asyncio.to_thread(
                    llm.ask,
                    event.command_text,
                )


                # =================================================
                # OLLAMA HAS RETURNED AN ANSWER
                # =================================================
                #
                # reply
                #
                # is LEO's answer.
                #
                # For example:
                #
                #     "I'm doing very well. How can I help?"
                #
                # =================================================

                if reply:

                    print()

                    print(
                        Fore.YELLOW
                        + Back.BLUE
                        + Style.BRIGHT
                        + f" LEO "
                        + Style.RESET_ALL
                        + " "
                        + Fore.CYAN
                        + reply
                        + Style.RESET_ALL
                    )


                    # =============================================
                    # NEW - TTS
                    # =============================================
                    #
                    # THIS IS THE IMPORTANT LINE.
                    #
                    # We take the exact reply returned by Ollama
                    # and send it directly to Qwen TTS.
                    #
                    #
                    #           Ollama
                    #
                    #             ↓
                    #
                    #            reply
                    #
                    #             ↓
                    #
                    #       tts.speak(reply)
                    #
                    #
                    # speak() places the text into the TTS queue.
                    #
                    # It does NOT need to wait here for all the
                    # speech to finish.
                    #
                    # =============================================

                    tts.speak(
                        reply
                    )


            # ====================================================
            # LLM ERROR
            # ====================================================

            except Exception as exc:

                print(
                    Fore.RED
                    + f"[LLM] Error: {exc}"
                    + Style.RESET_ALL
                )


# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print("====================================================")
    print(" BX1 BRAIN STARTING")
    print("====================================================")
    print()


    # ========================================================
    # CREATE AUDIO SERVER
    # ========================================================

    incoming = IncomingAudioServer()


    # ========================================================
    # CREATE SPEECH SEGMENTER
    # ========================================================

    segmenter = SpeechSegmenter()


    # ========================================================
    # CREATE FASTER-WHISPER ENGINE
    # ========================================================

    stt = STTEngine()


    # ========================================================
    # CREATE TRANSCRIPT / WAKE PROCESSOR
    # ========================================================

    transcript = TranscriptProcessor()


    # ========================================================
    # CREATE OLLAMA CLIENT
    # ========================================================

    llm = LLMClient()



    # ============================================================
    # PC -> ROBOT AUDIO STREAMER
    # ============================================================
    #
    # This opens port 8771.
    #
    # The Arduino will connect here to receive LEO's voice.
    # ============================================================

    robot_audio = AudioToRobotStreamer()

    robot_audio.start()

    # ========================================================
    # NEW - CREATE QWEN TTS ENGINE
    # ========================================================
    #
    # IMPORTANT:
    #
    # Qwen is loaded HERE only once.
    #
    # It should NOT be loaded for every LLM reply.
    #
    #
    # Brain startup:
    #
    #     Load Qwen model
    #          ↓
    #     Load LEO voice
    #          ↓
    #     Keep both in GPU memory
    #
    #
    # Later:
    #
    #     reply
    #       ↓
    #     speak()
    #
    # ========================================================

    tts = QwenTTSEngine(
        robot_audio
    )


    # ========================================================
    # SPEECH UTTERANCE QUEUE
    # ========================================================

    utterance_queue = asyncio.Queue(
        maxsize=10
    )


    # ========================================================
    # START ROBOT AUDIO WEBSOCKET SERVER
    # ========================================================

    server = await incoming.start()


    # ========================================================
    # START AUDIO SEGMENTATION WORKER
    # ========================================================

    segment_task = asyncio.create_task(

        segmentation_worker(
            incoming,
            segmenter,
            utterance_queue,
        )
    )


    # ========================================================
    # START STT / LLM / TTS WORKER
    # ========================================================

    transcription_task = asyncio.create_task(

        transcription_worker(

            utterance_queue,

            stt,

            transcript,

            llm,

            # =================================================
            # NEW - TTS
            # =================================================

            tts,
        )
    )


    # ========================================================
    # STARTUP INFORMATION
    # ========================================================

    print()
    print("[BX1] Voice pipeline ready.")


    print(
        "[BX1] LLM is "
        + (
            "ENABLED"
            if llm.enabled
            else "DISABLED"
        )
    )


    print(
        "[BX1] TTS is "
        + (
            "ENABLED"
            if tts.enabled
            else "DISABLED"
        )
    )


    print()
    print(
        "[BX1] Waiting for live microphone audio..."
    )
    print()


    # ========================================================
    # RUN BX1
    # ========================================================

    try:

        await asyncio.gather(

            server.wait_closed(),

            segment_task,

            transcription_task,
        )


    # ========================================================
    # SHUTDOWN
    # ========================================================

    finally:

        print()
        print("[BX1] Shutting down...")


        # Stop asyncio workers.

        segment_task.cancel()

        transcription_task.cancel()

        ##stop streaming audio to the robot
        robot_audio.stop()

        # ----------------------------------------------------
        # NEW - STOP TTS WORKER
        # ----------------------------------------------------

        tts.close()


        # Stop websocket server.

        server.close()

        await server.wait_closed()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )


    except KeyboardInterrupt:

        print()
        print(
            "BX1 Brain stopped."
        )