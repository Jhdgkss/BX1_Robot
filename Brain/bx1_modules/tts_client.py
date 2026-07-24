"""HTTP client helpers for the isolated Dot.TTS service."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests


class TTSServiceClient:
    """Small HTTP client for BX1_TTS_Service.

    Expected service endpoints:
    - GET  /health
    - GET  /voices
    - POST /speak
    - GET  /audio/<filename>
    """

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 60.0) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = float(timeout or 60.0)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-BX1-API-Key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        if not self.base_url:
            raise ValueError("TTS service URL is empty.")
        return self.base_url + "/" + path.lstrip("/")

    def health(self) -> Dict[str, Any]:
        r = requests.get(self._url("/health"), headers=self._headers(), timeout=min(self.timeout, 10.0))
        r.raise_for_status()
        return r.json()

    def voices(self) -> Dict[str, Any]:
        r = requests.get(self._url("/voices"), headers=self._headers(), timeout=min(self.timeout, 10.0))
        r.raise_for_status()
        return r.json()

    def speak(
        self,
        text: str,
        *,
        engine: str = "edge",
        voice: str = "bx1_default",
        volume: float = 0.9,
        rate: int = 0,
        pitch: int = 0,
        play: bool = False,
        robot_id: str = "BX1",
        mode: str = "",
        style: str = "",
        instruct: str = "",
        speaker: str = "",
        language: str = "",
        model_choice: str = "",
        attention: str = "",
        unload_model_after_generate: Optional[bool] = None,
        audio_format: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "text": text,
            "engine": engine,
            "voice": voice,
            "volume": volume,
            "rate": rate,
            "pitch": pitch,
            "play": bool(play),
            "robot_id": robot_id,
        }
        for key, value in {
            "mode": mode,
            "style": style,
            "instruct": instruct,
            "speaker": speaker,
            "language": language,
            "model_choice": model_choice,
            "attention": attention,
            "format": audio_format,
        }.items():
            if value not in (None, ""):
                payload[key] = value
        if unload_model_after_generate is not None:
            payload["unload_model_after_generate"] = bool(unload_model_after_generate)
        if extra:
            payload.update(extra)
        r = requests.post(self._url("/speak"), headers=self._headers(), data=json.dumps(payload), timeout=self.timeout)
        r.raise_for_status()
        return r.json()


    def play_audio(self, filename: str, *, volume: float = 0.9) -> Dict[str, Any]:
        """Ask the TTS service to play an already generated/cached audio file."""
        payload = {"filename": Path(filename).name, "volume": float(volume)}
        r = requests.post(self._url("/play"), headers=self._headers(), data=json.dumps(payload), timeout=min(self.timeout, 30.0))
        r.raise_for_status()
        return r.json()

    def download_audio(self, audio_url: str, suffix: Optional[str] = None) -> str:
        """Download an audio URL returned by the service to a temporary file."""
        if not audio_url:
            raise ValueError("Missing audio_url")
        if audio_url.startswith("/"):
            audio_url = urljoin(self.base_url + "/", audio_url.lstrip("/"))
        suffix = suffix or Path(audio_url.split("?", 1)[0]).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            path = tmp.name
        with requests.get(audio_url, headers=self._headers(), stream=True, timeout=self.timeout) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return path
