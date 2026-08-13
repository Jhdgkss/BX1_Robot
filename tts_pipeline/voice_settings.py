"""Persistent Qwen TTS voice-clone settings for BX1.

This module owns TTS configuration persistence only. It does not control
Qwen, audio playback, the GUI, or the robot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = PROJECT_ROOT / "settings" / "tts_voice.json"

SUPPORTED_MODELS = (
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "model_name": SUPPORTED_MODELS[0],
    "reference_audio": str(PROJECT_ROOT / "TTS_Tests" / "reference.wav"),
    "reference_text": "",
    # Preserve the current BX1 behaviour on first launch. For the higher
    # fidelity ICL clone, the GUI changes this to False after an exact
    # reference transcript has been entered.
    "x_vector_only_mode": True,
    "language": "English",
    "max_chunk_chars": 55,
    "split_on_commas": True,
    "max_new_tokens": 128,
    "max_batch_chunks": 6,
    "do_sample": True,
    "top_k": 50,
    "top_p": 1.0,
    "temperature": 0.9,
    "repetition_penalty": 1.05,
    "normalise_quiet_audio": True,
    "quiet_peak_threshold": 0.20,
    "normalise_target_peak": 0.90,
}


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


class TTSVoiceSettings:
    """Load, validate and save BX1 TTS settings."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else SETTINGS_FILE

    def defaults(self) -> Dict[str, Any]:
        return dict(DEFAULT_SETTINGS)

    def normalise(self, values: Dict[str, Any] | None) -> Dict[str, Any]:
        source = self.defaults()
        if values:
            source.update(dict(values))

        model_name = str(source.get("model_name", "")).strip()
        if model_name not in SUPPORTED_MODELS:
            model_name = DEFAULT_SETTINGS["model_name"]

        reference_audio = str(
            source.get("reference_audio", DEFAULT_SETTINGS["reference_audio"])
            or DEFAULT_SETTINGS["reference_audio"]
        ).strip()

        reference_text = str(source.get("reference_text", "") or "").strip()
        language = str(source.get("language", "English") or "English").strip()

        result = {
            "model_name": model_name,
            "reference_audio": reference_audio,
            "reference_text": reference_text,
            "x_vector_only_mode": bool(source.get("x_vector_only_mode", True)),
            "language": language or "English",
            "max_chunk_chars": int(
                _clamp(int(source.get("max_chunk_chars", 55)), 20, 240)
            ),
            "split_on_commas": bool(source.get("split_on_commas", True)),
            "max_new_tokens": int(
                _clamp(int(source.get("max_new_tokens", 128)), 32, 4096)
            ),
            "max_batch_chunks": int(
                _clamp(int(source.get("max_batch_chunks", 6)), 1, 16)
            ),
            "do_sample": bool(source.get("do_sample", True)),
            "top_k": int(_clamp(int(source.get("top_k", 50)), 1, 500)),
            "top_p": float(
                _clamp(float(source.get("top_p", 1.0)), 0.05, 1.0)
            ),
            "temperature": float(
                _clamp(float(source.get("temperature", 0.9)), 0.05, 2.0)
            ),
            "repetition_penalty": float(
                _clamp(float(source.get("repetition_penalty", 1.05)), 1.0, 2.0)
            ),
            "normalise_quiet_audio": bool(
                source.get("normalise_quiet_audio", True)
            ),
            "quiet_peak_threshold": float(
                _clamp(float(source.get("quiet_peak_threshold", 0.20)), 0.01, 1.0)
            ),
            "normalise_target_peak": float(
                _clamp(float(source.get("normalise_target_peak", 0.90)), 0.05, 1.0)
            ),
        }

        return result

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self.defaults()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(
                "[TTS SETTINGS] Could not read "
                f"{self.path}: {type(exc).__name__}: {exc}"
            )
            return self.defaults()

        if not isinstance(data, dict):
            return self.defaults()

        return self.normalise(data)

    def save(self, values: Dict[str, Any]) -> Dict[str, Any]:
        clean = self.normalise(values)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")

        temp_path.write_text(
            json.dumps(clean, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)

        return clean
