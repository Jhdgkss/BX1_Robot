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
# CHUNKING
# ------------------------------------------------------------

MAX_CHUNK_CHARS = 55

SPLIT_ON_COMMAS = True


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

# Deliberate silence between remainder chunks.
# Keep at zero for this test.
INTER_CHUNK_SILENCE_MS = 0


# ------------------------------------------------------------
# GPU
# ------------------------------------------------------------

DEVICE = "cuda:0"

DTYPE = torch.bfloat16

ATTENTION_IMPLEMENTATION = "sdpa"


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

        # Single section too long.
        # Split it at word boundaries.
        if len(part) > MAX_CHUNK_CHARS:

            words = part.split()

            temp = ""

            for word in words:

                proposed_word = (
                    f"{temp} {word}".strip()
                    if temp
                    else word
                )

                if len(proposed_word) <= MAX_CHUNK_CHARS:

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
# JOIN MULTIPLE WAVS
# ============================================================

def join_audio(
    wavs,
    sample_rate,
):

    pieces = []

    silence = None

    if INTER_CHUNK_SILENCE_MS > 0:

        silence_length = int(
            sample_rate
            * INTER_CHUNK_SILENCE_MS
            / 1000
        )

        silence = np.zeros(
            silence_length,
            dtype=np.float32,
        )

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
# CREATE IN-MEMORY WAV
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
# LOAD ONE QWEN ENGINE
# ============================================================

def load_engine(name):

    print()
    print(
        f"[{name}] Loading Qwen..."
    )

    start = time.perf_counter()

    model = Qwen3TTSModel.from_pretrained(
        MODEL_NAME,
        device_map=DEVICE,
        dtype=DTYPE,
        attn_implementation=ATTENTION_IMPLEMENTATION,
    )

    torch.cuda.synchronize()

    print(
        f"[{name}] Model loaded in "
        f"{time.perf_counter() - start:.2f}s"
    )

    allocated = (
        torch.cuda.memory_allocated()
        / 1024**3
    )

    print(
        f"[CUDA] Allocated after {name}: "
        f"{allocated:.2f} GB"
    )

    # --------------------------------------------------------
    # Create this engine's voice profile
    # --------------------------------------------------------

    print(
        f"[{name}] Creating voice profile..."
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
        f"[{name}] Voice profile created in "
        f"{time.perf_counter() - start:.2f}s"
    )

    return model, voice_prompt


# ============================================================
# GENERATE FIRST PHRASE
# ============================================================

def generate_first(
    model,
    voice_prompt,
    text,
    cuda_stream,
    result,
):

    try:

        print()
        print(
            f"[ENGINE A] Generating opening:"
        )

        print(
            f"           {text}"
        )

        start = time.perf_counter()

        # Use a separate CUDA stream.
        with torch.cuda.stream(cuda_stream):

            with torch.inference_mode():

                wavs, sample_rate = (
                    model.generate_voice_clone(
                        text=text,
                        language=LANGUAGE,
                        voice_clone_prompt=(
                            voice_prompt
                        ),
                        max_new_tokens=(
                            MAX_NEW_TOKENS
                        ),
                    )
                )

        cuda_stream.synchronize()

        generation_time = (
            time.perf_counter()
            - start
        )

        audio = prepare_audio(
            wavs[0]
        )

        duration = (
            len(audio)
            / sample_rate
        )

        result["audio"] = make_wav_bytes(
            audio,
            sample_rate,
        )

        result["duration"] = duration

        result["generation_time"] = (
            generation_time
        )

        result["sample_rate"] = (
            sample_rate
        )

        print()
        print(
            f"[ENGINE A] Complete in "
            f"{generation_time:.2f}s"
        )

        print(
            f"[ENGINE A] Speech duration: "
            f"{duration:.2f}s"
        )

        print(
            f"[ENGINE A] RTF: "
            f"{generation_time / duration:.2f}"
        )

    except Exception as exc:

        result["error"] = exc

    finally:

        result["finished"] = True


# ============================================================
# GENERATE REMAINDER BATCH
# ============================================================

def generate_remainder(
    model,
    voice_prompt,
    chunks,
    cuda_stream,
    result,
):

    try:

        print()
        print(
            f"[ENGINE B] Generating "
            f"{len(chunks)} remaining chunks AS A BATCH:"
        )

        for index, text in enumerate(
            chunks,
            start=2,
        ):

            print(
                f"           {index}: {text}"
            )

        start = time.perf_counter()

        # ----------------------------------------------------
        # Engine B gets its OWN CUDA stream.
        # ----------------------------------------------------

        with torch.cuda.stream(cuda_stream):

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
                        max_new_tokens=(
                            MAX_NEW_TOKENS
                        ),
                    )
                )

        cuda_stream.synchronize()

        generation_time = (
            time.perf_counter()
            - start
        )

        joined = join_audio(
            wavs,
            sample_rate,
        )

        duration = (
            len(joined)
            / sample_rate
        )

        result["audio"] = make_wav_bytes(
            joined,
            sample_rate,
        )

        result["duration"] = duration

        result["generation_time"] = (
            generation_time
        )

        result["sample_rate"] = (
            sample_rate
        )

        print()
        print(
            f"[ENGINE B] Complete in "
            f"{generation_time:.2f}s"
        )

        print(
            f"[ENGINE B] Speech duration: "
            f"{duration:.2f}s"
        )

        print(
            f"[ENGINE B] Batch RTF: "
            f"{generation_time / duration:.2f}"
        )

    except Exception as exc:

        result["error"] = exc

    finally:

        result["finished"] = True


# ============================================================
# SPEAK TEXT
# ============================================================

def speak_text(
    engine_a,
    prompt_a,
    engine_b,
    prompt_b,
    stream_a,
    stream_b,
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

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        print(
            f"  {index}: {chunk}"
        )

    overall_start = (
        time.perf_counter()
    )

    # ========================================================
    # ONLY ONE CHUNK
    # ========================================================

    if len(chunks) == 1:

        result = {
            "finished": False,
            "error": None,
        }

        generate_first(
            engine_a,
            prompt_a,
            chunks[0],
            stream_a,
            result,
        )

        if result["error"]:
            raise result["error"]

        time_to_first = (
            time.perf_counter()
            - overall_start
        )

        print()
        print(
            "[PLAY] Playing..."
        )

        winsound.PlaySound(
            result["audio"],
            winsound.SND_MEMORY,
        )

        print()
        print(
            "===================================================="
        )

        print(
            f"Time to first speech: "
            f"{time_to_first:.2f}s"
        )

        print(
            f"Total wall time: "
            f"{time.perf_counter() - overall_start:.2f}s"
        )

        print(
            "===================================================="
        )

        return


    # ========================================================
    # MULTIPLE CHUNKS
    # ========================================================

    first_chunk = chunks[0]

    remainder_chunks = chunks[1:]


    result_a = {
        "finished": False,
        "error": None,
    }

    result_b = {
        "finished": False,
        "error": None,
    }


    # ========================================================
    # LAUNCH BOTH TTS ENGINES AT THE SAME TIME
    # ========================================================

    print()
    print(
        "[PARALLEL] Starting BOTH engines..."
    )


    thread_a = threading.Thread(
        target=generate_first,
        args=(
            engine_a,
            prompt_a,
            first_chunk,
            stream_a,
            result_a,
        ),
        daemon=True,
    )


    thread_b = threading.Thread(
        target=generate_remainder,
        args=(
            engine_b,
            prompt_b,
            remainder_chunks,
            stream_b,
            result_b,
        ),
        daemon=True,
    )


    parallel_start = (
        time.perf_counter()
    )


    thread_a.start()

    thread_b.start()


    # ========================================================
    # WAIT ONLY FOR OPENING PHRASE
    # ========================================================

    thread_a.join()


    if result_a["error"]:
        raise result_a["error"]


    time_to_first_speech = (
        time.perf_counter()
        - overall_start
    )


    print()
    print(
        "===================================================="
    )

    print(
        f"[PLAY A] Starting first speech at "
        f"{time_to_first_speech:.2f}s"
    )

    print(
        "===================================================="
    )


    # ========================================================
    # PLAY OPENING PHRASE
    #
    # ENGINE B IS STILL GENERATING IN PARALLEL.
    # ========================================================

    first_play_start = (
        time.perf_counter()
    )


    winsound.PlaySound(
        result_a["audio"],
        winsound.SND_MEMORY,
    )


    first_play_end = (
        time.perf_counter()
    )


    print()
    print(
        "[PLAY A] First phrase finished."
    )


    # ========================================================
    # IS ENGINE B READY?
    # ========================================================

    gap_start = (
        time.perf_counter()
    )


    if not result_b["finished"]:

        print()
        print(
            "[BUFFER] Engine B is not ready."
        )

        print(
            "[BUFFER] Waiting..."
        )


    thread_b.join()


    gap_time = (
        time.perf_counter()
        - gap_start
    )


    if result_b["error"]:
        raise result_b["error"]


    # ========================================================
    # PLAY REMAINDER
    # ========================================================

    print()
    print(
        f"[PLAY B] Playing "
        f"{result_b['duration']:.2f}s "
        f"remainder..."
    )


    winsound.PlaySound(
        result_b["audio"],
        winsound.SND_MEMORY,
    )


    total_time = (
        time.perf_counter()
        - overall_start
    )


    parallel_elapsed = (
        time.perf_counter()
        - parallel_start
    )


    # ========================================================
    # RESULTS
    # ========================================================

    print()
    print(
        "===================================================="
    )

    print(
        "DUAL ENGINE RESULT"
    )

    print(
        "===================================================="
    )


    print(
        f"Engine A generation: "
        f"{result_a['generation_time']:.2f}s"
    )

    print(
        f"Engine A speech: "
        f"{result_a['duration']:.2f}s"
    )


    print(
        f"Engine B generation: "
        f"{result_b['generation_time']:.2f}s"
    )

    print(
        f"Engine B speech: "
        f"{result_b['duration']:.2f}s"
    )


    print()

    print(
        f"Time to first speech: "
        f"{time_to_first_speech:.2f}s"
    )


    print(
        f"Gap before remainder: "
        f"{gap_time:.2f}s"
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

    print()
    print(
        "===================================================="
    )

    print(
        "       QWEN3-TTS DUAL ENGINE TEST"
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

    print(
        f"[CUDA] Total VRAM: "
        f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB"
    )


    # ========================================================
    # ENGINE A
    # ========================================================

    engine_a, prompt_a = (
        load_engine(
            "ENGINE A"
        )
    )


    # ========================================================
    # ENGINE B
    # ========================================================

    engine_b, prompt_b = (
        load_engine(
            "ENGINE B"
        )
    )


    # ========================================================
    # CREATE TWO CUDA STREAMS
    # ========================================================

    stream_a = torch.cuda.Stream(
        device=DEVICE
    )

    stream_b = torch.cuda.Stream(
        device=DEVICE
    )


    allocated = (
        torch.cuda.memory_allocated()
        / 1024**3
    )

    reserved = (
        torch.cuda.memory_reserved()
        / 1024**3
    )


    print()
    print(
        f"[CUDA] Both engines loaded."
    )

    print(
        f"[CUDA] Allocated: "
        f"{allocated:.2f} GB"
    )

    print(
        f"[CUDA] Reserved: "
        f"{reserved:.2f} GB"
    )


    print()
    print(
        "===================================================="
    )

    print(
        "LEO DUAL TTS READY"
    )

    print(
        "===================================================="
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

                engine_a,
                prompt_a,

                engine_b,
                prompt_b,

                stream_a,
                stream_b,

                text,
            )


        except KeyboardInterrupt:

            print()
            print(
                "[QWEN] Exiting."
            )

            break


        except torch.OutOfMemoryError as exc:

            print()
            print(
                "[CUDA] OUT OF MEMORY."
            )

            print(
                "Two simultaneous Qwen engines "
                "use too much VRAM."
            )

            print(exc)

            torch.cuda.empty_cache()


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