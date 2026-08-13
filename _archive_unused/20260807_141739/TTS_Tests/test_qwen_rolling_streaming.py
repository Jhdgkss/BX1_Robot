import io
import re
import time
import queue
import threading
from pathlib import Path

import numpy as np
import torch
import soundfile as sf
import winsound

from qwen_tts import Qwen3TTSModel


# ============================================================
# USER CONFIGURATION
# ============================================================

MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

REFERENCE_AUDIO = "reference.wav"

LANGUAGE = "English"

# This is the voice-cloning mode that worked reliably for us.
X_VECTOR_ONLY_MODE = True


# ------------------------------------------------------------
# TEXT CHUNKING
# ------------------------------------------------------------

# Maximum approximate size of each spoken chunk.
MAX_CHUNK_CHARS = 55

# Allow commas to become useful speech boundaries.
SPLIT_ON_COMMAS = True


# ------------------------------------------------------------
# ROLLING BUFFER
# ------------------------------------------------------------

# First generation is deliberately small to get speech started.
FIRST_BATCH_SIZE = 1

# After speech has started, batch several chunks together.
#
# Your previous tests showed batch generation becomes MUCH
# more efficient than individual generation.
ROLLING_BATCH_SIZE = 4


# ------------------------------------------------------------
# GENERATION
# ------------------------------------------------------------

MAX_NEW_TOKENS = 128


# ------------------------------------------------------------
# AUDIO
# ------------------------------------------------------------

NORMALISE_QUIET_AUDIO = True

QUIET_PEAK_THRESHOLD = 0.20

NORMALISE_TARGET_PEAK = 0.90

# Do not deliberately add silence between chunks.
INTER_CHUNK_SILENCE_MS = 0


# ------------------------------------------------------------
# GPU
# ------------------------------------------------------------

DEVICE = "cuda:0"

DTYPE = torch.bfloat16

ATTENTION_IMPLEMENTATION = "sdpa"


# ------------------------------------------------------------
# DEBUG
# ------------------------------------------------------------

SHOW_CHUNKS = True
SHOW_BATCH_DETAILS = True


# ============================================================
# END USER CONFIGURATION
# ============================================================


BASE_DIR = Path(__file__).resolve().parent

REFERENCE_AUDIO_PATH = (
    BASE_DIR / REFERENCE_AUDIO
)


# ============================================================
# PYTORCH PERFORMANCE OPTIONS
# ============================================================

torch.set_float32_matmul_precision("high")

if torch.cuda.is_available():

    torch.backends.cuda.matmul.allow_tf32 = True


# ============================================================
# TEXT SPLITTER
# ============================================================

def split_text(text: str):

    text = re.sub(
        r"\s+",
        " ",
        text.strip(),
    )

    if not text:

        return []


    # --------------------------------------------------------
    # Split on natural punctuation first
    # --------------------------------------------------------

    if SPLIT_ON_COMMAS:

        parts = re.split(
            r"(?<=[.!?;:,])\s+",
            text,
        )

    else:

        parts = re.split(
            r"(?<=[.!?;:])\s+",
            text,
        )


    parts = [
        part.strip()
        for part in parts
        if part.strip()
    ]


    chunks = []

    current = ""


    # --------------------------------------------------------
    # Combine small pieces until MAX_CHUNK_CHARS
    # --------------------------------------------------------

    for part in parts:

        proposed = (
            f"{current} {part}".strip()
            if current
            else part
        )


        if len(proposed) <= MAX_CHUNK_CHARS:

            current = proposed

            continue


        if current:

            chunks.append(current)

            current = ""


        # ----------------------------------------------------
        # If one piece itself is too long, split on words.
        # ----------------------------------------------------

        if len(part) > MAX_CHUNK_CHARS:

            words = part.split()

            temp = ""


            for word in words:

                proposed_word = (
                    f"{temp} {word}".strip()
                    if temp
                    else word
                )


                if (
                    len(proposed_word)
                    <= MAX_CHUNK_CHARS
                ):

                    temp = proposed_word


                else:

                    if temp:

                        chunks.append(temp)

                    temp = word


            current = temp


        else:

            current = part


    if current:

        chunks.append(current)


    return chunks


# ============================================================
# AUDIO PREPARATION
# ============================================================

def prepare_audio(audio):

    audio = np.asarray(
        audio,
        dtype=np.float32,
    )


    audio = np.squeeze(audio)


    if audio.size == 0:

        raise RuntimeError(
            "Qwen returned empty audio."
        )


    peak = float(
        np.max(
            np.abs(audio)
        )
    )


    # --------------------------------------------------------
    # Normalise unusually quiet generations
    # --------------------------------------------------------

    if (
        NORMALISE_QUIET_AUDIO
        and peak > 0
        and peak < QUIET_PEAK_THRESHOLD
    ):

        audio = (
            audio
            / peak
            * NORMALISE_TARGET_PEAK
        )


    return np.clip(
        audio,
        -1.0,
        1.0,
    )


# ============================================================
# JOIN AUDIO FROM A BATCH
# ============================================================

def join_audio(
    wavs,
    sample_rate,
):

    pieces = []


    if INTER_CHUNK_SILENCE_MS > 0:

        silence_samples = int(
            sample_rate
            * INTER_CHUNK_SILENCE_MS
            / 1000
        )

        silence = np.zeros(
            silence_samples,
            dtype=np.float32,
        )

    else:

        silence = None


    for index, wav in enumerate(wavs):

        audio = prepare_audio(wav)

        pieces.append(audio)


        if (
            silence is not None
            and index < len(wavs) - 1
        ):

            pieces.append(silence)


    return np.concatenate(pieces)


# ============================================================
# CREATE WAV IN MEMORY
# ============================================================

def make_wav_bytes(
    audio,
    sample_rate,
):

    buffer = io.BytesIO()


    sf.write(
        buffer,
        audio,
        sample_rate,
        format="WAV",
        subtype="PCM_16",
    )


    return buffer.getvalue()


# ============================================================
# GENERATE ONE BATCH
# ============================================================

def generate_batch(
    model,
    voice_prompt,
    chunks,
    batch_number,
):

    print()
    print(
        f"[GEN {batch_number}] "
        f"Generating {len(chunks)} chunk(s)"
    )


    if SHOW_BATCH_DETAILS:

        for chunk in chunks:

            print(
                f"    {chunk}"
            )


    generation_start = (
        time.perf_counter()
    )


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Qwen receives all texts in this batch simultaneously.
    # --------------------------------------------------------

    with torch.inference_mode():

        wavs, sample_rate = (
            model.generate_voice_clone(

                text=chunks,

                language=[
                    LANGUAGE
                    for _ in chunks
                ],

                voice_clone_prompt=(
                    voice_prompt
                ),

                # This does NOT give us true audio streaming,
                # but is the mode Qwen currently exposes.
                non_streaming_mode=False,

                max_new_tokens=(
                    MAX_NEW_TOKENS
                ),
            )
        )


    torch.cuda.synchronize()


    generation_time = (
        time.perf_counter()
        - generation_start
    )


    if wavs is None or len(wavs) == 0:

        raise RuntimeError(
            f"Batch {batch_number} "
            f"returned no audio."
        )


    if len(wavs) != len(chunks):

        raise RuntimeError(
            f"Batch {batch_number}: "
            f"expected {len(chunks)} audio outputs, "
            f"received {len(wavs)}."
        )


    # --------------------------------------------------------
    # Join this batch into one continuous WAV
    #
    # This prevents winsound stopping/restarting between
    # individual chunks INSIDE the batch.
    # --------------------------------------------------------

    joined_audio = join_audio(
        wavs,
        sample_rate,
    )


    speech_duration = (
        len(joined_audio)
        / sample_rate
    )


    wav_bytes = make_wav_bytes(
        joined_audio,
        sample_rate,
    )


    rtf = (
        generation_time
        / speech_duration
        if speech_duration > 0
        else 0
    )


    print(
        f"[GEN {batch_number}] "
        f"Generated: {generation_time:.2f}s"
    )

    print(
        f"[GEN {batch_number}] "
        f"Speech:    {speech_duration:.2f}s"
    )

    print(
        f"[GEN {batch_number}] "
        f"RTF:       {rtf:.2f}"
    )


    return {

        "number": batch_number,

        "chunks": chunks,

        "wav_bytes": wav_bytes,

        "sample_rate": sample_rate,

        "duration": speech_duration,

        "generation_time": generation_time,

        "rtf": rtf,
    }


# ============================================================
# PLAYBACK WORKER
# ============================================================

def playback_worker(
    audio_queue,
    playback_state,
):

    first_audio = True


    while True:

        # ----------------------------------------------------
        # If playback has already started and the queue is
        # empty, we are experiencing a BUFFER UNDERRUN.
        # ----------------------------------------------------

        if (
            not first_audio
            and audio_queue.empty()
        ):

            underrun_start = (
                time.perf_counter()
            )

        else:

            underrun_start = None


        item = audio_queue.get()


        try:

            # None means finished.
            if item is None:

                return


            if first_audio:

                playback_state[
                    "first_play_time"
                ] = time.perf_counter()

                first_audio = False


            # ------------------------------------------------
            # Calculate actual silence caused by waiting
            # for generation.
            # ------------------------------------------------

            if underrun_start is not None:

                wait_time = (
                    time.perf_counter()
                    - underrun_start
                )


                if wait_time > 0.05:

                    playback_state[
                        "underruns"
                    ].append(
                        wait_time
                    )

                    print()
                    print(
                        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                    )

                    print(
                        f"[BUFFER] UNDERRUN: "
                        f"{wait_time:.2f}s silence"
                    )

                    print(
                        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                    )


            print()
            print(
                f"[PLAY {item['number']}] "
                f"{item['duration']:.2f}s audio"
            )


            # ------------------------------------------------
            # This blocks ONLY the playback thread.
            #
            # The generation thread is already producing
            # the next batch.
            # ------------------------------------------------

            winsound.PlaySound(
                item["wav_bytes"],
                winsound.SND_MEMORY,
            )


            print(
                f"[PLAY {item['number']}] "
                f"Finished"
            )


        finally:

            audio_queue.task_done()


# ============================================================
# GENERATION WORKER
# ============================================================

def generation_worker(
    model,
    voice_prompt,
    chunks,
    audio_queue,
    generation_state,
):

    try:

        batch_number = 1

        position = 0


        while position < len(chunks):

            # ------------------------------------------------
            # First batch = small
            #
            # Following batches = larger for GPU efficiency
            # ------------------------------------------------

            if batch_number == 1:

                batch_size = (
                    FIRST_BATCH_SIZE
                )

            else:

                batch_size = (
                    ROLLING_BATCH_SIZE
                )


            batch_chunks = chunks[
                position:
                position + batch_size
            ]


            batch = generate_batch(

                model,

                voice_prompt,

                batch_chunks,

                batch_number,
            )


            # ------------------------------------------------
            # As soon as this batch exists, hand it to the
            # playback worker.
            #
            # Then IMMEDIATELY start generating the next
            # batch while this one is playing.
            # ------------------------------------------------

            audio_queue.put(batch)


            position += len(
                batch_chunks
            )

            batch_number += 1


    except Exception as exc:

        generation_state[
            "error"
        ] = exc


    finally:

        generation_state[
            "finished"
        ] = True

        # Signal player that there is no more audio.
        audio_queue.put(None)


# ============================================================
# SPEAK COMPLETE TEXT
# ============================================================

def speak_text(
    model,
    voice_prompt,
    text,
):

    chunks = split_text(text)


    if not chunks:

        return


    print()
    print(
        "===================================================="
    )

    print(
        f"[TEXT] {len(chunks)} speech chunk(s)"
    )

    print(
        "===================================================="
    )


    if SHOW_CHUNKS:

        for index, chunk in enumerate(
            chunks,
            start=1,
        ):

            print(
                f" {index:2}: {chunk}"
            )


    # --------------------------------------------------------
    # Queue size is deliberately small.
    #
    # We don't want to generate an enormous response
    # before playback catches up.
    # --------------------------------------------------------

    audio_queue = queue.Queue(
        maxsize=3
    )


    generation_state = {

        "finished": False,

        "error": None,
    }


    playback_state = {

        "first_play_time": None,

        "underruns": [],
    }


    overall_start = (
        time.perf_counter()
    )


    # ========================================================
    # START PLAYER
    # ========================================================

    player = threading.Thread(

        target=playback_worker,

        args=(
            audio_queue,
            playback_state,
        ),

        daemon=True,
    )


    player.start()


    # ========================================================
    # START ONE QWEN GENERATION WORKER
    # ========================================================

    generator = threading.Thread(

        target=generation_worker,

        args=(
            model,
            voice_prompt,
            chunks,
            audio_queue,
            generation_state,
        ),

        daemon=True,
    )


    generator.start()


    # --------------------------------------------------------
    # Wait for generation and playback to complete.
    # --------------------------------------------------------

    generator.join()

    audio_queue.join()

    player.join()


    total_time = (
        time.perf_counter()
        - overall_start
    )


    if generation_state["error"]:

        raise generation_state[
            "error"
        ]


    # ========================================================
    # RESULTS
    # ========================================================

    print()
    print(
        "===================================================="
    )

    print(
        "ROLLING STREAM RESULT"
    )

    print(
        "===================================================="
    )


    first_play_time = (
        playback_state[
            "first_play_time"
        ]
    )


    if first_play_time is not None:

        time_to_first_speech = (
            first_play_time
            - overall_start
        )


        print(
            f"Time to first speech: "
            f"{time_to_first_speech:.2f}s"
        )


    underruns = (
        playback_state[
            "underruns"
        ]
    )


    print(
        f"Buffer underruns: "
        f"{len(underruns)}"
    )


    if underruns:

        print(
            f"Total silence waiting: "
            f"{sum(underruns):.2f}s"
        )

        print(
            f"Worst silence: "
            f"{max(underruns):.2f}s"
        )


    else:

        print(
            "No generation-caused pauses."
        )


    print(
        f"Total wall time: "
        f"{total_time:.2f}s"
    )


    print(
        "===================================================="
    )


# ============================================================
# LOAD QWEN
# ============================================================

def load_qwen():

    print()
    print(
        "===================================================="
    )

    print(
        "     QWEN3-TTS ROLLING STREAM TEST"
    )

    print(
        "===================================================="
    )


    if not REFERENCE_AUDIO_PATH.exists():

        raise FileNotFoundError(
            f"Reference audio not found:\n"
            f"{REFERENCE_AUDIO_PATH}"
        )


    if not torch.cuda.is_available():

        raise RuntimeError(
            "CUDA is not available."
        )


    print()
    print(
        f"[CUDA] "
        f"{torch.cuda.get_device_name(0)}"
    )


    # ========================================================
    # MODEL - LOAD ONCE
    # ========================================================

    print()
    print(
        "[QWEN] Loading model ONCE..."
    )


    start = time.perf_counter()


    model = Qwen3TTSModel.from_pretrained(

        MODEL_NAME,

        device_map=DEVICE,

        dtype=DTYPE,

        attn_implementation=(
            ATTENTION_IMPLEMENTATION
        ),
    )


    torch.cuda.synchronize()


    print(
        f"[QWEN] Loaded in "
        f"{time.perf_counter() - start:.2f}s"
    )


    # ========================================================
    # VOICE - CREATE ONCE
    # ========================================================

    print()
    print(
        "[VOICE] Creating voice profile ONCE..."
    )


    start = time.perf_counter()


    with torch.inference_mode():

        voice_prompt = (
            model.create_voice_clone_prompt(

                ref_audio=str(
                    REFERENCE_AUDIO_PATH
                ),

                ref_text=None,

                x_vector_only_mode=(
                    X_VECTOR_ONLY_MODE
                ),
            )
        )


    torch.cuda.synchronize()


    print(
        f"[VOICE] Created in "
        f"{time.perf_counter() - start:.2f}s"
    )


    print()
    print(
        "[READY] LEO TTS ready."
    )


    return (
        model,
        voice_prompt,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    model, voice_prompt = (
        load_qwen()
    )


    print()
    print(
        "Paste a paragraph and press ENTER."
    )

    print(
        "Type 'quit' to exit."
    )


    while True:

        try:

            text = input(
                "\nYou > "
            )


            if text.strip().lower() in {

                "quit",
                "exit",
                "q",

            }:

                break


            if not text.strip():

                continue


            speak_text(

                model,

                voice_prompt,

                text,
            )


        except KeyboardInterrupt:

            print()
            print(
                "[QWEN] Exiting."
            )

            break


        except Exception as exc:

            print()
            print(
                f"[ERROR] "
                f"{type(exc).__name__}: "
                f"{exc}"
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()