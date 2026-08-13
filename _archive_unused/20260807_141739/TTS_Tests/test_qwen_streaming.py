import io
import re
import time
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

X_VECTOR_ONLY_MODE = True


# ------------------------------------------------------------
# TEXT CHUNKING
# ------------------------------------------------------------

# Approximate maximum chunk length.
MAX_CHUNK_CHARS = 55

# Split at commas as well as sentence punctuation.
SPLIT_ON_COMMAS = True


# ------------------------------------------------------------
# PIPELINE / BUFFERING
# ------------------------------------------------------------

# Generate this many chunks BEFORE LEO starts speaking.
#
# 1 = fastest initial response, but greater chance of a gap.
# 2 = slightly slower start, but gives us an audio buffer.
# 3 = larger buffer, even less chance of a gap.
#
START_BATCH_SIZE = 2


# Maximum number of chunks to generate together in subsequent
# batch calls.
#
# For our current tests we can batch most/all of the remainder.
REMAINDER_BATCH_SIZE = 8


# ------------------------------------------------------------
# GENERATION
# ------------------------------------------------------------

MAX_NEW_TOKENS = 128


# ------------------------------------------------------------
# AUDIO
# ------------------------------------------------------------

# Extra silence deliberately inserted between generated chunks.
#
# Set to ZERO for the lowest possible gap.
INTER_CHUNK_SILENCE_MS = 0


NORMALISE_QUIET_AUDIO = True

QUIET_PEAK_THRESHOLD = 0.20

NORMALISE_TARGET_PEAK = 0.90


# ------------------------------------------------------------
# GPU
# ------------------------------------------------------------

DEVICE = "cuda:0"

DTYPE = torch.bfloat16

ATTENTION_IMPLEMENTATION = "sdpa"


# ------------------------------------------------------------
# DEBUG OUTPUT
# ------------------------------------------------------------

SHOW_CHUNKS = True
SHOW_TIMINGS = True


# ============================================================
# END USER CONFIGURATION
# ============================================================


BASE_DIR = Path(__file__).resolve().parent

REFERENCE_AUDIO_PATH = BASE_DIR / REFERENCE_AUDIO


# ============================================================
# PYTORCH PERFORMANCE
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
        p.strip()
        for p in parts
        if p.strip()
    ]

    chunks = []

    current = ""

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
        # Piece itself is too long.
        # Split approximately at word boundaries.
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
# AUDIO NORMALISATION
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


    audio = np.clip(
        audio,
        -1.0,
        1.0,
    )


    return audio


# ============================================================
# JOIN CHUNK AUDIO
# ============================================================

def join_audio(
    wavs,
    sample_rate,
):

    completed = []


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

        completed.append(audio)


        if (
            silence is not None
            and index < len(wavs) - 1
        ):

            completed.append(silence)


    return np.concatenate(
        completed
    )


# ============================================================
# CONVERT TO WINDOWS WAV IN MEMORY
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
# GENERATE A BATCH
# ============================================================

def generate_batch(
    model,
    voice_clone_prompt,
    chunks,
    batch_name,
):

    if not chunks:

        return None


    print()
    print(
        f"[GEN {batch_name}] "
        f"Generating {len(chunks)} chunk(s) together..."
    )


    for index, text in enumerate(
        chunks,
        start=1,
    ):

        print(
            f"    {index}: {text}"
        )


    start = time.perf_counter()


    # ========================================================
    # THIS IS THE IMPORTANT CHANGE
    #
    # Qwen receives a LIST of texts.
    #
    # It therefore performs batched synthesis instead of us
    # calling generate_voice_clone separately for each phrase.
    # ========================================================

    with torch.inference_mode():

        wavs, sample_rate = (
            model.generate_voice_clone(

                text=chunks,

                language=[
                    LANGUAGE
                    for _ in chunks
                ],

                voice_clone_prompt=(
                    voice_clone_prompt
                ),

                max_new_tokens=(
                    MAX_NEW_TOKENS
                ),
            )
        )


    torch.cuda.synchronize()


    generation_time = (
        time.perf_counter()
        - start
    )


    if wavs is None:

        raise RuntimeError(
            f"Batch {batch_name} returned no audio."
        )


    if len(wavs) != len(chunks):

        raise RuntimeError(
            f"Batch {batch_name}: "
            f"expected {len(chunks)} WAVs, "
            f"received {len(wavs)}."
        )


    # --------------------------------------------------------
    # Calculate total speech duration
    # --------------------------------------------------------

    durations = []

    for wav in wavs:

        audio = np.squeeze(
            np.asarray(wav)
        )

        durations.append(
            len(audio)
            / sample_rate
        )


    total_speech = sum(durations)


    rtf = (
        generation_time
        / total_speech
        if total_speech > 0
        else 0
    )


    print()

    print(
        f"[GEN {batch_name}] "
        f"Generation time: "
        f"{generation_time:.2f}s"
    )

    print(
        f"[GEN {batch_name}] "
        f"Total speech: "
        f"{total_speech:.2f}s"
    )

    print(
        f"[GEN {batch_name}] "
        f"Batch RTF: "
        f"{rtf:.2f}"
    )


    # --------------------------------------------------------
    # Join all chunks into ONE continuous audio stream.
    #
    # This eliminates winsound stopping and restarting
    # between every individual chunk.
    # --------------------------------------------------------

    joined_audio = join_audio(
        wavs,
        sample_rate,
    )


    joined_duration = (
        len(joined_audio)
        / sample_rate
    )


    wav_bytes = make_wav_bytes(
        joined_audio,
        sample_rate,
    )


    return {

        "wav_bytes": wav_bytes,

        "sample_rate": sample_rate,

        "duration": joined_duration,

        "generation_time": generation_time,

        "chunks": chunks,
    }


# ============================================================
# PLAY AUDIO
# ============================================================

def play_audio(
    batch,
    name,
):

    if batch is None:
        return


    print()

    print(
        f"[PLAY {name}] "
        f"Playing {batch['duration']:.2f}s..."
    )


    winsound.PlaySound(

        batch["wav_bytes"],

        winsound.SND_MEMORY,
    )


    print(
        f"[PLAY {name}] Finished."
    )


# ============================================================
# LOAD MODEL
# ============================================================

def load_model():

    print()
    print(
        "===================================================="
    )

    print(
        "    QWEN3-TTS BATCH / PIPELINE TEST"
    )

    print(
        "===================================================="
    )

    print()


    if not REFERENCE_AUDIO_PATH.exists():

        raise FileNotFoundError(
            f"Reference audio not found:\n"
            f"{REFERENCE_AUDIO_PATH}"
        )


    if not torch.cuda.is_available():

        raise RuntimeError(
            "CUDA is not available."
        )


    print(
        f"[CUDA] "
        f"{torch.cuda.get_device_name(0)}"
    )


    # --------------------------------------------------------
    # Load Qwen ONCE
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Create voice profile ONCE
    # --------------------------------------------------------

    print()
    print(
        "[VOICE] Creating voice profile ONCE..."
    )


    start = time.perf_counter()


    with torch.inference_mode():

        voice_clone_prompt = (
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
        voice_clone_prompt,
    )


# ============================================================
# SPEAK TEXT WITH BATCH PIPELINE
# ============================================================

def speak_text(
    model,
    voice_clone_prompt,
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
        f"[TEXT] "
        f"{len(chunks)} speech chunk(s)"
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
                f"  {index}: {chunk}"
            )


    overall_start = time.perf_counter()


    # ========================================================
    # DIVIDE INTO START BUFFER + REMAINDER
    # ========================================================

    first_chunks = (
        chunks[:START_BATCH_SIZE]
    )

    remaining_chunks = (
        chunks[START_BATCH_SIZE:]
    )


    # ========================================================
    # GENERATE FIRST AUDIO BUFFER
    # ========================================================

    first_batch = generate_batch(

        model,

        voice_clone_prompt,

        first_chunks,

        "START",
    )


    time_to_first_audio = (
        time.perf_counter()
        - overall_start
    )


    # ========================================================
    # BACKGROUND HOLDER FOR REMAINDER
    # ========================================================

    remainder_result = {
        "batch": None,
        "error": None,
        "finished": False,
    }


    # ========================================================
    # GENERATE REMAINDER IN BACKGROUND
    # ========================================================

    def remainder_worker():

        try:

            if remaining_chunks:

                remainder_result["batch"] = (
                    generate_batch(

                        model,

                        voice_clone_prompt,

                        remaining_chunks,

                        "REMAINDER",
                    )
                )

        except Exception as exc:

            remainder_result["error"] = exc

        finally:

            remainder_result["finished"] = True


    # --------------------------------------------------------
    # Start generation of remainder.
    # --------------------------------------------------------

    remainder_thread = None


    if remaining_chunks:

        remainder_thread = threading.Thread(

            target=remainder_worker,

            daemon=True,
        )

        remainder_thread.start()


    # ========================================================
    # PLAY START AUDIO
    #
    # WHILE THIS AUDIO IS PLAYING:
    #
    # GPU thread is generating the remainder batch.
    # ========================================================

    play_start = time.perf_counter()


    play_audio(
        first_batch,
        "START",
    )


    first_play_end = time.perf_counter()


    # ========================================================
    # CHECK WHETHER REMAINDER IS READY
    # ========================================================

    if remainder_thread is not None:

        if not remainder_result["finished"]:

            print()
            print(
                "[BUFFER] Audio buffer underrun."
            )

            print(
                "[BUFFER] Waiting for remainder "
                "generation to finish..."
            )


        wait_start = time.perf_counter()


        remainder_thread.join()


        gap_wait = (
            time.perf_counter()
            - wait_start
        )


        if remainder_result["error"]:

            raise remainder_result["error"]


        if gap_wait > 0.05:

            print(
                f"[BUFFER] Waited "
                f"{gap_wait:.2f}s for next audio."
            )


        # ====================================================
        # PLAY ALL REMAINING CHUNKS AS ONE CONTINUOUS WAV
        # ====================================================

        play_audio(

            remainder_result["batch"],

            "REMAINDER",
        )


    # ========================================================
    # RESULTS
    # ========================================================

    total_time = (
        time.perf_counter()
        - overall_start
    )


    print()
    print(
        "===================================================="
    )

    print(
        "[RESULT]"
    )

    print(
        f"Time to first speech: "
        f"{time_to_first_audio:.2f}s"
    )


    if remainder_thread is not None:

        print(
            f"Gap waiting for second buffer: "
            f"{gap_wait:.2f}s"
        )


    print(
        f"Total wall time: "
        f"{total_time:.2f}s"
    )

    print(
        "===================================================="
    )


# ============================================================
# MAIN
# ============================================================

def main():

    model, voice_clone_prompt = (
        load_model()
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

                voice_clone_prompt,

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