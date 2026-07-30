from __future__ import annotations

import base64
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests


@dataclass
class BrainClientConfig:
    base_url: str
    api_key: str = ""
    chat_timeout_s: int = 180
    vision_timeout_s: int = 180
    command_ack_timeout_s: int = 10


class BX1BrainClient:
    """HTTP client for the BX1 Brain App Robot API."""

    def __init__(self, cfg: BrainClientConfig) -> None:
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["X-BX1-API-Key"] = self.cfg.api_key
        return headers

    def _response_json_or_error(self, response: requests.Response, endpoint: str) -> Dict[str, Any]:
        """Return JSON, including useful server-side error text.

        requests.raise_for_status() hides the JSON body in normal exception text.
        When the Windows Brain App returns a 500 we need to show the actual cause
        on the robot web page, e.g. Ollama not running, wrong model, or TTS API
        unavailable.
        """
        text = response.text or ""
        try:
            data = response.json() if text else {}
        except Exception:
            data = {"raw_response": text[:1200]}
        if response.status_code >= 400:
            detail = ""
            if isinstance(data, dict):
                detail = str(data.get("error") or data.get("detail") or data.get("message") or data)
            else:
                detail = str(data)
            raise RuntimeError(f"Brain App {endpoint} returned HTTP {response.status_code}: {detail}")
        if not isinstance(data, dict):
            raise RuntimeError(f"Brain App {endpoint} returned non-object JSON: {data!r}")
        return data

    def _require_base_url(self) -> None:
        if not self.base_url:
            raise RuntimeError("Brain App URL is not configured. Save the Brain PC address in Brain Connection.")

    def _get_json(self, endpoint: str, timeout: int | float = 10) -> Dict[str, Any]:
        self._require_base_url()
        r = requests.get(f"{self.base_url}{endpoint}", headers=self._headers(), timeout=timeout)
        return self._response_json_or_error(r, endpoint)

    def _post_json(self, endpoint: str, payload: Dict[str, Any], timeout: int | float) -> Dict[str, Any]:
        self._require_base_url()
        r = requests.post(
            f"{self.base_url}{endpoint}",
            headers=self._headers(),
            json=payload,
            timeout=timeout,
        )
        return self._response_json_or_error(r, endpoint)

    def status(self) -> Dict[str, Any]:
        return self._get_json("/api/status", timeout=10)

    def stt_status(self) -> Dict[str, Any]:
        return self._get_json("/api/stt/status", timeout=10)

    def transcribe_wav(
        self,
        wav_bytes: bytes,
        *,
        language: str = "en",
        hotwords: str = "",
        initial_prompt: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload = {
            "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
            "mime_type": "audio/wav",
            "language": str(language or "en"),
            "hotwords": str(hotwords or ""),
            "initial_prompt": str(initial_prompt or ""),
            "metadata": metadata or {},
        }
        return self._post_json(
            "/api/stt/transcribe",
            payload,
            timeout=int(timeout_s or self.cfg.chat_timeout_s),
        )

    def send_body_state(self, body_state: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"body_state": body_state}
        return self._post_json("/api/body_state", payload, timeout=10)

    def chat(
        self,
        robot_id: str,
        message: str,
        body_state: Optional[Dict[str, Any]] = None,
        use_web: Optional[bool] = None,
        use_memory: Optional[bool] = None,
        robot_profile: Optional[Dict[str, Any]] = None,
        source: str = "robot_body",
        trigger: str = "manual",
        event_id: str = "",
        input_metadata: Optional[Dict[str, Any]] = None,
        return_audio: bool = True,
    ) -> Dict[str, Any]:
        payload = {
            "robot_id": robot_id,
            "message": message,
            "body_state": body_state or {},
            "robot_profile": robot_profile or {},
            "source": str(source or "robot_body"),
            "trigger": str(trigger or "manual"),
            "event_id": str(event_id or ""),
            "input_metadata": input_metadata or {},
            "speak": False,
            "return_audio": bool(return_audio),
            "vision_context": False,
        }
        if use_web is not None:
            payload["use_web"] = bool(use_web)
        if use_memory is not None:
            payload["use_memory"] = bool(use_memory)
        return self._post_json("/api/chat", payload, timeout=self.cfg.chat_timeout_s)

    def vision_frame(
        self,
        robot_id: str,
        image_bytes: bytes,
        body_state: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        robot_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a camera frame to the Brain App without asking the LLM to analyse it."""
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "robot_id": robot_id,
            "image_base64": image_b64,
            "body_state": body_state or {},
            "robot_profile": robot_profile or {},
            "metadata": metadata or {},
            "mime_type": "image/jpeg",
        }
        return self._post_json("/api/vision_frame", payload, timeout=self.cfg.vision_timeout_s)

    def vision(
        self,
        robot_id: str,
        prompt: str,
        image_bytes: bytes,
        body_state: Optional[Dict[str, Any]] = None,
        use_web: Optional[bool] = None,
        robot_profile: Optional[Dict[str, Any]] = None,
        source: str = "robot_body",
        trigger: str = "vision_request",
        event_id: str = "",
        input_metadata: Optional[Dict[str, Any]] = None,
        return_audio: bool = True,
    ) -> Dict[str, Any]:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "robot_id": robot_id,
            "message": prompt,
            "image_base64": image_b64,
            "body_state": body_state or {},
            "robot_profile": robot_profile or {},
            "source": str(source or "robot_body"),
            "trigger": str(trigger or "vision_request"),
            "event_id": str(event_id or ""),
            "input_metadata": input_metadata or {},
            "speak": False,
            "return_audio": bool(return_audio),
            "mime_type": "image/jpeg",
            "vision_context": True,
        }
        if use_web is not None:
            payload["use_web"] = bool(use_web)
        return self._post_json("/api/vision", payload, timeout=self.cfg.vision_timeout_s)

    def command_ack(self, ack: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_json("/api/command_ack", {"ack": ack}, timeout=self.cfg.command_ack_timeout_s)

    def download_response_audio(self, result: Dict[str, Any]) -> Path:
        """Download Brain-published reply audio using the normal API connection."""
        nested = result.get("audio") if isinstance(result.get("audio"), dict) else {}
        raw_url = str(
            result.get("audio_url")
            or nested.get("audio_url")
            or nested.get("relative_audio_url")
            or ""
        ).strip()
        if not raw_url:
            raise RuntimeError("Brain response did not include an audio URL.")
        if raw_url.startswith("/"):
            url = urljoin(self.base_url + "/", raw_url.lstrip("/"))
        else:
            url = raw_url
            parsed = urlparse(url)
            if parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}:
                brain = urlparse(self.base_url)
                url = urlunparse((brain.scheme or "http", brain.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in {".wav", ".mp3", ".ogg"}:
            suffix = ".wav"
        with tempfile.NamedTemporaryFile(prefix="bx1_brain_reply_", suffix=suffix, delete=False) as handle:
            target = Path(handle.name)
        try:
            with requests.get(url, headers=self._headers(), stream=True, timeout=self.cfg.chat_timeout_s) as response:
                response.raise_for_status()
                with target.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            output.write(chunk)
            if target.stat().st_size < 1000:
                raise RuntimeError("Downloaded Brain audio is too small to be valid.")
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
