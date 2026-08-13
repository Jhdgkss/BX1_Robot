import time
import math
import winsound
from pathlib import Path

import numpy as np
import torch
import soundfile as sf

from qwen_tts import Qwen3TTSModel


# ============================================================
# USER CONFIGURATION
# ============================================================

# Qwen model
MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"


# Voice sample
REFERENCE_AUDIO = "reference.wav"


# Language
LANGUAGE = "English"


# Generated WAV.
# This is overwritten for each sentence.
OUTPUT_AUDIO = "qwen_leo_test.wav"


# Automatically play each generated sentence
PLAY_AUDIO = True


# Maximum generation length.
#
# 256 is suitable for testing ordinary sentences.
# We can tune this later for LEO.
MAX_NEW_TOKENS = 256


# GPU
DEVICE = "cuda:0"

DTYPE = torch.bfloat16

ATTENTION_IMPLEMENTATION = "sdpa"


# Voice cloning mode.
#
# True = use speaker characteristics only.
# This is the mode that worked correctly for us.
X_VECTOR_ONLY_MODE = True


# ============================================================
# END USER CONFIGURATION
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

REFERENCE_AUDIO_PATH = BASE_DIR / REFERENCE_AUDIO

OUTPUT_AUDIO_PATH = BASE_DIR / OUTPUT_AUDIO


# ============================================================
# PYTORCH PERFORMANCE SETTINGS
# ============================================================

# Allow PyTorch to use faster matrix multiplication where suitable.
torch.set_float32_matmul_precision("high")

if torch.cuda.is_available():

    # RTX Ada GPUs support TF32.
    torch.backends.cuda.matmul.allow_tf32 = True


# ============================================================
# STARTUP
# ============================================================

print()
print("====================================================")
print("       QWEN3-TTS INTERACTIVE LEO TEST")
print("====================================================")
print()


# ============================================================
# CHECK REFERENCE AUDIO
# ============================================================

print(f"[VOICE] Reference:")
print(f"        {REFERENCE_AUDIO_PATH}")

if not REFERENCE_AUDIO_PATH.exists():

    raise FileNotFoundError(
        f"\nReference audio not found:\n"
        f"{REFERENCE_AUDIO_PATH}"
    )


print(
    f"[VOICE] Size: "
    f"{REFERENCE_AUDIO_PATH.stat().st_size / 1024:.1f} KB"
)

print()


# ============================================================
# CHECK CUDA
# ============================================================

print("[CUDA] Checking GPU...")


if not torch.cuda.is_available():

    raise RuntimeError(
        "CUDA is not available."
    )


print(
    f"[CUDA] GPU: "
    f"{torch.cuda.get_device_name(0)}"
)

print(
    f"[CUDA] CUDA: "
    f"{torch.version.cuda}"
)

print()


# ============================================================
# LOAD MODEL - ONCE
# ============================================================

print("[QWEN] Loading model ONCE...")


start = time.perf_counter()


model = Qwen3TTSModel.from_pretrained(

    MODEL_NAME,

    device_map=DEVICE,

    dtype=DTYPE,

    attn_implementation=ATTENTION_IMPLEMENTATION,
)


torch.cuda.synchronize()


load_time = time.perf_counter() - start


print(
    f"[QWEN] Model loaded in "
    f"{load_time:.2f} seconds"
)

print()


# ============================================================
# CREATE VOICE CLONE PROMPT - ONCE
# ============================================================
#
# This is important.
#
# Previously generate_voice_clone() was being given reference.wav
# every time.
#
# Now Qwen analyses reference.wav ONCE.
#
# The resulting voice_clone_prompt stays in memory and is reused
# for every sentence entered below.
#
# ============================================================

print("[VOICE] Creating LEO voice profile ONCE...")


start = time.perf_counter()


with torch.inference_mode():

    voice_clone_prompt = model.create_voice_clone_prompt(

        ref_audio=str(
            REFERENCE_AUDIO_PATH
        ),

        ref_text=None,

        x_vector_only_mode=X_VECTOR_ONLY_MODE,
    )


torch.cuda.synchronize()


voice_time = time.perf_counter() - start


print(
    f"[VOICE] Voice profile created in "
    f"{voice_time:.2f} seconds"
)


print()
print("[READY] LEO TTS is ready.")
print()
print("Type something and press ENTER.")
print("Type 'quit' to exit.")
print()


# ============================================================
# SPEECH GENERATION FUNCTION
# ============================================================

def speak(text: str):

    """
    Generate speech using the already-loaded model
    and already-created LEO voice profile.
    """

    text = text.strip()

    if not text:
        return


    print()
    print("--------------------------------------------")
    print(f"[LEO] {text}")
    print("--------------------------------------------")


    # --------------------------------------------------------
    # Generate speech
    # --------------------------------------------------------

    start = time.perf_counter()


    with torch.inference_mode():

        wavs, sample_rate = model.generate_voice_clone(

            text=text,

            language=LANGUAGE,

            # IMPORTANT:
            #
            # We reuse the voice profile.
            # reference.wav is NOT analysed again.
            #
            voice_clone_prompt=voice_clone_prompt,

            max_new_tokens=MAX_NEW_TOKENS,
        )


    torch.cuda.synchronize()


    generation_time = time.perf_counter() - start


    # --------------------------------------------------------
    # Validate audio
    # --------------------------------------------------------

    if wavs is None or len(wavs) == 0:

        print("[ERROR] Qwen returned no audio.")

        return


    audio = np.asarray(
        wavs[0],
        dtype=np.float32,
    )


    audio = np.squeeze(audio)


    if audio.size == 0:

        print("[ERROR] Generated audio is empty.")

        return


    # --------------------------------------------------------
    # Audio information
    # --------------------------------------------------------

    duration = len(audio) / sample_rate

    peak = float(
        np.max(
            np.abs(audio)
        )
    )


    rms = float(
        np.sqrt(
            np.mean(
                np.square(audio)
            )
        )
    )


    if rms > 0:

        rms_db = (
            20.0
            * math.log10(rms)
        )

    else:

        rms_db = -999.0


    print()
    print(
        f"[TIME] Generation: "
        f"{generation_time:.2f} seconds"
    )

    print(
        f"[AUDIO] Duration: "
        f"{duration:.2f} seconds"
    )

    print(
        f"[AUDIO] Sample rate: "
        f"{sample_rate} Hz"
    )

    print(
        f"[AUDIO] Peak: "
        f"{peak:.4f}"
    )

    print(
        f"[AUDIO] RMS: "
        f"{rms_db:.1f} dBFS"
    )


    # --------------------------------------------------------
    # Normalise quiet output
    # --------------------------------------------------------

    if peak > 0 and peak < 0.20:

        print(
            "[AUDIO] Normalising quiet output..."
        )

        audio = (
            audio
            / peak
            * 0.90
        )


    audio = np.clip(
        audio,
        -1.0,
        1.0,
    )


    # --------------------------------------------------------
    # Save WAV
    # --------------------------------------------------------

    sf.write(

        str(
            OUTPUT_AUDIO_PATH
        ),

        audio,

        sample_rate,

        subtype="PCM_16",
    )


    # --------------------------------------------------------
    # Play WAV
    # --------------------------------------------------------

    if PLAY_AUDIO:

        print("[AUDIO] Playing...")

        winsound.PlaySound(

            str(
                OUTPUT_AUDIO_PATH
            ),

            winsound.SND_FILENAME,
        )


    print(
        "[READY] Enter another sentence."
    )


# ============================================================
# INTERACTIVE LOOP
# ============================================================

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

            print()
            print("[QWEN] Shutting down.")

            break


        speak(text)


    except KeyboardInterrupt:

        print()
        print()
        print("[QWEN] Ctrl+C received. Exiting.")

        break


    except Exception as exc:

        print()
        print(
            f"[ERROR] "
            f"{type(exc).__name__}: {exc}"
        )


print()
print("====================================================")
print("                  TEST ENDED")
print("====================================================")