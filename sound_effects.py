# ============================================================
# BX1 SOUND EFFECT LIBRARY
# ============================================================
#
# PURPOSE
# -------
#
# This module DOES NOT play audio.
#
# It only:
#
#     - loads sound-effect configuration
#     - maps BX1 event names to WAV files
#     - loads WAV files
#     - converts them to mono PCM16
#     - resamples them to the configured sample rate
#     - returns the PCM audio to main_Local.py
#
# AUDIO OWNERSHIP
# ---------------
#
# All orchestration and audio routing remains in main_Local.py.
#
#     event
#       |
#       v
#   main_Local.py
#       |
#       v
# sound_effects.py
#   (load only)
#       |
#       v
#   main_Local.py
#       |
#       +----> pc_audio.py
#       |
#       +----> audio_to_robot_streamer.py
#
# sound_effects.py deliberately does NOT import pc_audio.py or
# audio_to_robot_streamer.py.
#
# ============================================================

from dataclasses import dataclass
from pathlib import Path
import json

import numpy as np


DEFAULT_CONFIG_FILE = "sound_effects_config.json"
DEFAULT_SOUNDS_FOLDER = "sounds"
DEFAULT_SAMPLE_RATE = 24000


@dataclass(frozen=True)
class SoundEffect:
    """PCM audio returned to main_Local.py for routing."""

    event_name: str
    file_path: Path
    pcm16: bytes
    sample_rate: int


class SoundEffectLibrary:
    """
    Load sound-effect settings and WAV data.

    This class has no audio-output responsibilities.
    """

    def __init__(
        self,
        config_path=None,
    ):
        self.base_folder = Path(__file__).resolve().parent

        if config_path is None:
            config_path = self.base_folder / DEFAULT_CONFIG_FILE
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.config = {}

        self.enabled = True
        self.target_sample_rate = DEFAULT_SAMPLE_RATE
        self.global_volume = 1.0
        self.sounds_folder = (
            self.base_folder
            / DEFAULT_SOUNDS_FOLDER
        )

        self.reload()


    # ========================================================
    # LOAD / RELOAD CONFIG
    # ========================================================

    def reload(self):
        """
        Reload sound_effects_config.json.

        This can be called while the program is stopped and
        restarted after editing the JSON file.
        """

        try:
            with self.config_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                config = json.load(file)

        except FileNotFoundError:
            print(
                f"[SOUNDS] Config file not found: "
                f"{self.config_path}"
            )
            config = {}

        except Exception as exc:
            print(
                f"[SOUNDS] Config error: "
                f"{type(exc).__name__}: {exc}"
            )
            config = {}

        if not isinstance(config, dict):
            config = {}

        self.config = config

        self.enabled = bool(
            config.get(
                "enabled",
                True,
            )
        )

        self.target_sample_rate = int(
            config.get(
                "target_sample_rate",
                DEFAULT_SAMPLE_RATE,
            )
        )

        self.global_volume = self._clamp_volume(
            config.get(
                "volume",
                1.0,
            )
        )

        folder_name = config.get(
            "sounds_folder",
            DEFAULT_SOUNDS_FOLDER,
        )

        folder_path = Path(
            str(folder_name)
        )

        if not folder_path.is_absolute():
            folder_path = (
                self.base_folder
                / folder_path
            )

        self.sounds_folder = folder_path

        print(
            "[SOUNDS] Library loaded. "
            f"Enabled={self.enabled}, "
            f"folder={self.sounds_folder}"
        )


    # ========================================================
    # EVENT CONFIG
    # ========================================================

    def get_event_config(
        self,
        event_name,
    ):
        events = self.config.get(
            "events",
            {},
        )

        if not isinstance(events, dict):
            return None

        event = events.get(
            event_name
        )

        if not isinstance(event, dict):
            return None

        return event


    def is_enabled(
        self,
        event_name,
    ):
        if not self.enabled:
            return False

        event = self.get_event_config(
            event_name
        )

        if event is None:
            return False

        return bool(
            event.get(
                "enabled",
                True,
            )
        )


    def get_delay_seconds(
        self,
        event_name,
        default=0.0,
    ):
        event = self.get_event_config(
            event_name
        )

        if event is None:
            return float(default)

        try:
            return max(
                0.0,
                float(
                    event.get(
                        "delay_seconds",
                        default,
                    )
                ),
            )

        except Exception:
            return float(default)


    # ========================================================
    # LOAD ONE EVENT
    # ========================================================

    def load(
        self,
        event_name,
    ):
        """
        Return a SoundEffect object, or None when the event is
        disabled, missing or cannot be loaded.
        """

        if not self.is_enabled(
            event_name
        ):
            return None

        event = self.get_event_config(
            event_name
        )

        filename = str(
            event.get(
                "file",
                "",
            )
        ).strip()

        if not filename:
            print(
                f"[SOUNDS] No WAV assigned to "
                f"event '{event_name}'."
            )
            return None

        wav_path = (
            self.sounds_folder
            / filename
        ).resolve()

        # Prevent a config entry from escaping the sounds folder.
        try:
            wav_path.relative_to(
                self.sounds_folder.resolve()
            )
        except ValueError:
            print(
                f"[SOUNDS] Invalid sound path for "
                f"'{event_name}': {wav_path}"
            )
            return None

        if not wav_path.exists():
            print(
                f"[SOUNDS] Missing WAV for "
                f"'{event_name}': {wav_path}"
            )
            return None

        event_volume = self._clamp_volume(
            event.get(
                "volume",
                1.0,
            )
        )

        volume = (
            self.global_volume
            * event_volume
        )

        try:
            pcm16 = self._load_wav_as_pcm16(
                wav_path,
                self.target_sample_rate,
                volume,
            )

        except Exception as exc:
            print(
                f"[SOUNDS] Could not load "
                f"'{event_name}': "
                f"{type(exc).__name__}: {exc}"
            )
            return None

        return SoundEffect(
            event_name=event_name,
            file_path=wav_path,
            pcm16=pcm16,
            sample_rate=self.target_sample_rate,
        )


    # ========================================================
    # WAV DECODING
    # ========================================================

    @staticmethod
    def _load_wav_as_pcm16(
        wav_path,
        target_sample_rate,
        volume,
    ):
        """
        Read an uncompressed PCM WAV using Python's wave module.

        Supported sample widths:
            8-bit PCM
            16-bit PCM
            24-bit PCM
            32-bit PCM

        Stereo/multichannel audio is mixed to mono.
        """

        import wave

        with wave.open(
            str(wav_path),
            "rb",
        ) as wav_file:

            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            source_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()

            raw = wav_file.readframes(
                frame_count
            )

        if channels < 1:
            raise ValueError(
                "WAV has no audio channels."
            )

        audio = SoundEffectLibrary._pcm_bytes_to_float(
            raw,
            sample_width,
        )

        if len(audio) == 0:
            raise ValueError(
                "WAV contains no audio samples."
            )

        # Convert interleaved multichannel audio to mono.
        if channels > 1:
            usable = (
                len(audio)
                // channels
                * channels
            )

            audio = audio[:usable]

            audio = audio.reshape(
                -1,
                channels,
            ).mean(
                axis=1
            )

        audio = SoundEffectLibrary._resample(
            audio,
            source_rate,
            target_sample_rate,
        )

        audio = np.clip(
            audio * float(volume),
            -1.0,
            1.0,
        )

        pcm16 = (
            audio
            * 32767.0
        ).astype(
            "<i2"
        ).tobytes()

        return pcm16


    @staticmethod
    def _pcm_bytes_to_float(
        raw,
        sample_width,
    ):
        if sample_width == 1:
            # WAV 8-bit PCM is unsigned.
            values = np.frombuffer(
                raw,
                dtype=np.uint8,
            ).astype(
                np.float32
            )

            return (
                values - 128.0
            ) / 128.0

        if sample_width == 2:
            values = np.frombuffer(
                raw,
                dtype="<i2",
            ).astype(
                np.float32
            )

            return values / 32768.0

        if sample_width == 3:
            data = np.frombuffer(
                raw,
                dtype=np.uint8,
            )

            usable = (
                len(data)
                // 3
                * 3
            )

            data = data[:usable].reshape(
                -1,
                3,
            )

            values = (
                data[:, 0].astype(np.int32)
                | (
                    data[:, 1].astype(np.int32)
                    << 8
                )
                | (
                    data[:, 2].astype(np.int32)
                    << 16
                )
            )

            # Sign-extend 24-bit values.
            negative = (
                values
                & 0x800000
            ) != 0

            values[negative] -= (
                1 << 24
            )

            return (
                values.astype(np.float32)
                / 8388608.0
            )

        if sample_width == 4:
            values = np.frombuffer(
                raw,
                dtype="<i4",
            ).astype(
                np.float32
            )

            return values / 2147483648.0

        raise ValueError(
            f"Unsupported WAV sample width: "
            f"{sample_width} bytes"
        )


    # ========================================================
    # RESAMPLING
    # ========================================================

    @staticmethod
    def _resample(
        audio,
        source_rate,
        target_rate,
    ):
        source_rate = int(
            source_rate
        )

        target_rate = int(
            target_rate
        )

        if (
            source_rate == target_rate
            or len(audio) < 2
        ):
            return audio.astype(
                np.float32,
                copy=False,
            )

        output_length = max(
            1,
            int(
                round(
                    len(audio)
                    * target_rate
                    / source_rate
                )
            ),
        )

        source_positions = np.linspace(
            0.0,
            1.0,
            num=len(audio),
            endpoint=False,
        )

        target_positions = np.linspace(
            0.0,
            1.0,
            num=output_length,
            endpoint=False,
        )

        return np.interp(
            target_positions,
            source_positions,
            audio,
        ).astype(
            np.float32
        )


    # ========================================================
    # VOLUME
    # ========================================================

    @staticmethod
    def _clamp_volume(
        value,
    ):
        try:
            value = float(
                value
            )

        except Exception:
            value = 1.0

        return max(
            0.0,
            min(
                value,
                1.0,
            ),
        )
