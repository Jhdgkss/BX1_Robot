# ============================================================
# STANDARD PYTHON IMPORTS
# ============================================================

from dataclasses import dataclass

import os
import sys
import time

from pathlib import Path


# ============================================================
# CUDA DLL SETUP
# ============================================================
#
# IMPORTANT:
#
# Faster-Whisper uses a library called CTranslate2.
#
# On Windows, CTranslate2 needs to be able to find NVIDIA DLLs
# such as:
#
#     cublas64_12.dll
#     cudnn64_9.dll
#
# Python / Windows does not always automatically find these
# DLLs inside a virtual environment.
#
# We therefore add the CUDA DLL folders BEFORE importing:
#
#     from faster_whisper import WhisperModel
#
# ============================================================


# Keep the DLL directory handles alive for the whole time
# the program is running.
#
# If we do not keep these handles, Python can remove the
# directories from its DLL search path later.
_cuda_dll_handles = []


def add_dll_folder(folder: Path):
    """
    Add one folder to the Windows DLL search path.

    The folder is only added if it actually exists.
    """

    if not folder.exists():
        return

    folder_text = str(folder)

    # --------------------------------------------------------
    # Python 3.8+ Windows DLL search path.
    # --------------------------------------------------------

    if hasattr(os, "add_dll_directory"):

        try:

            handle = os.add_dll_directory(
                folder_text
            )

            _cuda_dll_handles.append(
                handle
            )

        except OSError:
            pass


    # --------------------------------------------------------
    # Also add the folder to PATH.
    #
    # Some native libraries still use the normal Windows
    # PATH when searching for dependent DLLs.
    # --------------------------------------------------------

    current_path = os.environ.get(
        "PATH",
        "",
    )

    if folder_text.lower() not in current_path.lower():

        os.environ["PATH"] = (
            folder_text
            + os.pathsep
            + current_path
        )


def setup_cuda_dlls():
    """
    Find CUDA DLLs inside the current Python virtual environment
    and add their folders to the Windows DLL search path.
    """

    print()
    print(
        "[CUDA] Checking Faster-Whisper CUDA libraries..."
    )


    # ========================================================
    # FIND CURRENT VIRTUAL ENVIRONMENT
    # ========================================================
    #
    # sys.prefix should currently be:
    #
    # C:\\Git WorkSpace\\BX_Dev\\BX1_Dev\\.venv
    #
    # ========================================================

    virtual_environment = Path(
        sys.prefix
    )


    site_packages = (
        virtual_environment
        / "Lib"
        / "site-packages"
    )


    print(
        f"[CUDA] Python environment: "
        f"{virtual_environment}"
    )


    # ========================================================
    # COMMON CUDA DLL LOCATIONS
    # ========================================================

    possible_folders = [

        # PyTorch normally keeps many Windows CUDA DLLs here.
        site_packages
        / "torch"
        / "lib",

        # NVIDIA pip packages may put cuBLAS here.
        site_packages
        / "nvidia"
        / "cublas"
        / "bin",

        # NVIDIA pip packages may put cuDNN here.
        site_packages
        / "nvidia"
        / "cudnn"
        / "bin",
    ]


    for folder in possible_folders:

        add_dll_folder(
            folder
        )


    # ========================================================
    # REQUIRED DLLS
    # ========================================================
    #
    # CTranslate2 currently needs these for our configuration.
    #
    # ========================================================

    required_dlls = [

        "cublas64_12.dll",

        "cudnn64_9.dll",
    ]


    for dll_name in required_dlls:

        found_file = None


        # ----------------------------------------------------
        # First check our common folders.
        # ----------------------------------------------------

        for folder in possible_folders:

            possible_file = (
                folder
                / dll_name
            )

            if possible_file.exists():

                found_file = possible_file

                break


        # ----------------------------------------------------
        # If it was not in a normal location, search the
        # current virtual environment's site-packages folder.
        #
        # This only happens during program startup.
        # ----------------------------------------------------

        if (
            found_file is None
            and site_packages.exists()
        ):

            try:

                for possible_file in site_packages.rglob(
                    dll_name
                ):

                    found_file = possible_file

                    break

            except Exception:

                pass


        # ----------------------------------------------------
        # REPORT RESULT
        # ----------------------------------------------------

        if found_file is not None:

            add_dll_folder(
                found_file.parent
            )

            print(
                f"[CUDA] FOUND: {dll_name}"
            )

            print(
                f"       {found_file}"
            )

        else:

            print(
                f"[CUDA] MISSING: {dll_name}"
            )


    print()


# ============================================================
# CONFIGURE CUDA NOW
# ============================================================
#
# THIS MUST HAPPEN BEFORE faster_whisper IS IMPORTED.
# ============================================================

setup_cuda_dlls()


# ============================================================
# THIRD-PARTY IMPORTS
# ============================================================

import numpy as np


# ============================================================
# FASTER-WHISPER IMPORT
# ============================================================
#
# CUDA DLL folders have now been configured.
# ============================================================

from faster_whisper import WhisperModel


# ============================================================
# BX1 CONFIGURATION
# ============================================================

import settings.config as config


# ============================================================
# STT RESULT
# ============================================================
#
# This holds everything returned by our speech-to-text engine.
#
# ============================================================

@dataclass
class STTResult:

    text: str

    audio_seconds: float

    processing_seconds: float

    rtf: float

    x_realtime: float

    provider: str

    model: str


# ============================================================
# SPEECH TO TEXT ENGINE
# ============================================================

class STTEngine:

    def __init__(self):

        self.model = None

        self.provider = None


        # ====================================================
        # TRY CUDA FIRST
        # ====================================================

        if config.STT_PREFER_CUDA:

            try:

                self._load_cuda()

            except Exception as exc:

                print()

                print(
                    f"[STT] CUDA model load failed:"
                )

                print(
                    f"[STT] {exc}"
                )

                print()

                print(
                    "[STT] Falling back to CPU/int8."
                )

                self._load_cpu()


        # ====================================================
        # USER HAS DISABLED CUDA
        # ====================================================

        else:

            self._load_cpu()


    # ========================================================
    # LOAD CUDA MODEL
    # ========================================================

    def _load_cuda(self):

        print(
            f"[STT] Loading "
            f"{config.STT_MODEL} "
            f"on CUDA / float16..."
        )


        self.model = WhisperModel(

            config.STT_MODEL,

            device="cuda",

            compute_type="float16",
        )


        self.provider = (
            "CUDA/float16"
        )


    # ========================================================
    # LOAD CPU MODEL
    # ========================================================

    def _load_cpu(self):

        print(
            f"[STT] Loading "
            f"{config.STT_MODEL} "
            f"on CPU / int8..."
        )


        self.model = WhisperModel(

            config.STT_MODEL,

            device="cpu",

            compute_type="int8",
        )


        self.provider = (
            "CPU/int8"
        )


    # ========================================================
    # CONVERT ROBOT AUDIO
    # ========================================================
    #
    # LEO sends:
    #
    #     signed 16-bit PCM
    #
    # Faster-Whisper wants:
    #
    #     floating point audio from -1.0 to +1.0
    #
    # ========================================================

    @staticmethod
    def _pcm16_to_float32(
        pcm: bytes,
    ):

        samples = np.frombuffer(

            pcm,

            dtype=np.int16,
        )


        return (
            samples.astype(
                np.float32
            )
            / 32768.0
        )


    # ========================================================
    # RUN WHISPER
    # ========================================================

    def _run_inference(
        self,
        audio,
    ):

        segments, _ = (
            self.model.transcribe(

                audio,

                language=(
                    config.STT_LANGUAGE
                ),

                beam_size=(
                    config.STT_BEAM_SIZE
                ),

                vad_filter=False,

                condition_on_previous_text=False,
            )
        )


        # Faster-Whisper returns a generator.
        #
        # Converting it to a list actually performs
        # the transcription.

        segments = list(
            segments
        )


        # Join all recognised speech segments together.

        text = " ".join(

            segment.text.strip()

            for segment in segments

            if segment.text.strip()
        )


        return text.strip()


    # ========================================================
    # TRANSCRIBE ONE UTTERANCE
    # ========================================================

    def transcribe(
        self,
        pcm: bytes,
    ) -> STTResult:


        # ----------------------------------------------------
        # Convert incoming LEO PCM into Whisper audio.
        # ----------------------------------------------------

        audio = self._pcm16_to_float32(
            pcm
        )


        # ----------------------------------------------------
        # Calculate how long the recorded speech was.
        # ----------------------------------------------------

        audio_seconds = (
            len(audio)
            / config.MIC_SAMPLE_RATE
        )


        # Start timing Whisper.

        started = time.perf_counter()


        # ====================================================
        # RUN STT
        # ====================================================

        try:

            text = self._run_inference(
                audio
            )


        # ====================================================
        # CUDA FAILURE FALLBACK
        # ====================================================
        #
        # If CUDA fails during actual inference, we fall back
        # to CPU so the Brain remains usable.
        #
        # ====================================================

        except Exception as exc:

            if (
                self.provider
                and
                self.provider.startswith(
                    "CUDA"
                )
            ):

                print()

                print(
                    "[STT] CUDA inference failed."
                )

                print(
                    f"[STT] Reason: {exc}"
                )

                print(
                    "[STT] Switching to CPU/int8."
                )

                print()


                self._load_cpu()


                # Try the same speech again using CPU.

                text = self._run_inference(
                    audio
                )


            else:

                # It was already using CPU, so something else
                # has gone wrong.
                raise


        # ====================================================
        # PERFORMANCE INFORMATION
        # ====================================================

        processing_seconds = (
            time.perf_counter()
            - started
        )


        if audio_seconds:

            rtf = (
                processing_seconds
                / audio_seconds
            )

        else:

            rtf = 0.0


        if processing_seconds:

            x_realtime = (
                audio_seconds
                / processing_seconds
            )

        else:

            x_realtime = 0.0


        # ====================================================
        # RETURN RESULT
        # ====================================================

        return STTResult(

            text=text,

            audio_seconds=audio_seconds,

            processing_seconds=(
                processing_seconds
            ),

            rtf=rtf,

            x_realtime=x_realtime,

            provider=self.provider,

            model=config.STT_MODEL,
        )