from __future__ import annotations

import base64
import json
import tempfile
import time
import uuid
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
    endpoint_candidates: Optional[List[str]] = None


class EndpointResolver:
    """Local-first endpoint selection without replaying non-idempotent calls."""

    def __init__(self, configured: str, candidates: Optional[List[str]] = None) -> None:
        configured = str(configured or "").rstrip("/")
        raw = [str(item or "").rstrip("/") for item in (candidates or [])]
        if not raw:
            raw = ["http://192.168.68.53:8765", "http://100.92.216.101:8765"]
        # Local is always preferred for the known BX1 routes. Preserve a
        # legacy single URL by retaining it after the preferred candidates.
        preferred = ["http://192.168.68.53:8765", "http://100.92.216.101:8765"]
        if configured and configured not in raw:
            raw.append(configured)
        raw = preferred + raw
        self.candidates = list(dict.fromkeys(item for item in raw if item))
        self.active = self.candidates[0] if self.candidates else ""
        self.active_route = self._route(self.active)
        self.last_success_at = ""
        self.last_failure_reason = ""
        self.last_latency_ms: Optional[float] = None
        self.last_local_probe: Dict[str, Any] = {"state": "not_probed"}
        self.last_fallback_probe: Dict[str, Any] = {"state": "not_probed"}
        self._last_probe = 0.0

    @staticmethod
    def _route(url: str) -> str:
        if "100.92.216.101" in url or "100.72.130.12" in url:
            return "tailscale"
        if "192.168." in url or "127.0.0.1" in url or "localhost" in url:
            return "local"
        return "configured"

    def snapshot(self) -> Dict[str, Any]:
        return {
            "preferred_endpoint": self.candidates[0] if self.candidates else "",
            "active_endpoint": self.active,
            "active_route": self.active_route,
            "candidates": list(self.candidates),
            "latency_ms": self.last_latency_ms,
            "last_success_at": self.last_success_at,
            "last_failure_reason": self.last_failure_reason,
            "local_probe": dict(self.last_local_probe),
            "fallback_probe": dict(self.last_fallback_probe),
        }

    def choose(self, headers: Optional[Dict[str, str]] = None, timeout: float = 1.5, force: bool = False) -> str:
        if self.active and not force and (time.monotonic() - self._last_probe) < 10.0:
            return self.active
        last_error = ""
        for candidate in self.candidates:
            started = time.perf_counter()
            try:
                response = requests.get(f"{candidate}/api/status", headers=headers or {}, timeout=timeout)
                if response.status_code >= 500:
                    raise RuntimeError(f"HTTP {response.status_code}")
                self.active = candidate
                self.active_route = self._route(candidate)
                self.last_latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
                self.last_success_at = now_iso()
                self.last_failure_reason = ""
                probe = {"state": "available", "latency_ms": self.last_latency_ms, "at": self.last_success_at}
                if self._route(candidate) == "local":
                    self.last_local_probe = probe
                elif self._route(candidate) == "tailscale":
                    self.last_fallback_probe = probe
                self._last_probe = time.monotonic()
                return candidate
            except Exception as exc:
                last_error = str(exc)
                probe = {"state": "unavailable", "error": last_error}
                if self._route(candidate) == "local":
                    self.last_local_probe = probe
                elif self._route(candidate) == "tailscale":
                    self.last_fallback_probe = probe
        self._last_probe = time.monotonic()
        self.last_failure_reason = last_error or "no endpoint candidates configured"
        raise RuntimeError(f"No Brain endpoint is reachable: {self.last_failure_reason}")

    def mark_failure(self, reason: str) -> None:
        self.last_failure_reason = str(reason or "request failed")
        self._last_probe = 0.0


class BX1BrainClient:
    """HTTP client for the BX1 Brain App Robot API."""

    def __init__(self, cfg: BrainClientConfig) -> None:
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        candidates = cfg.endpoint_candidates or [
            self.base_url,
            "http://192.168.68.53:8765",
            "http://100.92.216.101:8765",
        ]
        self.endpoint_resolver = EndpointResolver(self.base_url, candidates)
        self.base_url = self.endpoint_resolver.active

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
        if not self.base_url and not self.endpoint_resolver.candidates:
            raise RuntimeError("Brain App URL is not configured. Save the Brain PC address in Brain Connection.")

    def _get_json(self, endpoint: str, timeout: int | float = 10) -> Dict[str, Any]:
        self._require_base_url()
        try:
            self.base_url = self.endpoint_resolver.choose(self._headers(), timeout=min(float(timeout), 2.0))
            r = requests.get(f"{self.base_url}{endpoint}", headers=self._headers(), timeout=timeout)
            result = self._response_json_or_error(r, endpoint)
            return result
        except Exception as exc:
            self.endpoint_resolver.mark_failure(str(exc))
            raise

    def _post_json(self, endpoint: str, payload: Dict[str, Any], timeout: int | float) -> Dict[str, Any]:
        self._require_base_url()
        try:
            # Probe/select before POST. A failed POST is never replayed on another route.
            self.base_url = self.endpoint_resolver.choose(self._headers(), timeout=min(float(timeout), 2.0))
            request_id = str(payload.get("request_id") or uuid.uuid4())
            payload = dict(payload)
            payload.setdefault("request_id", request_id)
            headers = self._headers()
            headers["X-BX1-Request-ID"] = request_id
            r = requests.post(f"{self.base_url}{endpoint}", headers=headers, json=payload, timeout=timeout)
            return self._response_json_or_error(r, endpoint)
        except Exception as exc:
            self.endpoint_resolver.mark_failure(str(exc))
            raise

    def endpoint_status(self) -> Dict[str, Any]:
        return self.endpoint_resolver.snapshot()

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
