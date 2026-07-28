"""Redacted observer and safe Body bridge for the v0.6 voice vertical slice."""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, Mapping, Optional
from urllib import error, request
from urllib.parse import urlparse


VOICE_EVENTS = {
    "WakeDetected", "ListeningStarted", "SpeechRecognised", "BrainRequestSent",
    "ThinkingStarted", "SpeechStarted", "SpeechFinished", "FaultRaised",
}
PRIVATE_FIELDS = {
    "audio", "audio_base64", "credentials", "message", "prompt", "reply",
    "speech", "text", "transcript", "raw", "api_key", "token", "password",
}


class VoiceTimeline:
    """In-memory, metadata-only timeline. It deliberately has no disk persistence."""

    def __init__(self, *, limit: int = 250, clock=time.time) -> None:
        self._events: deque[Dict[str, Any]] = deque(maxlen=max(10, int(limit)))
        self._faults: deque[Dict[str, Any]] = deque(maxlen=100)
        self._lock = threading.RLock()
        self.clock = clock

    def record(self, value: Mapping[str, Any], *, source: str = "bx1_os") -> Dict[str, Any]:
        event_type = str(value.get("event") or value.get("type") or "").strip()
        if event_type not in VOICE_EVENTS:
            raise ValueError("unsupported_voice_event")
        session_id = str(value.get("session_id") or "").strip()
        if not session_id or len(session_id) > 96:
            raise ValueError("invalid_session_id")
        timestamp = float(value.get("timestamp") or self.clock())
        metadata: Dict[str, Any] = {}
        for key in ("reason", "stage", "transport", "duration_ms", "latency_ms", "source"):
            if key not in value or key in PRIVATE_FIELDS:
                continue
            item = value[key]
            if isinstance(item, (bool, int, float)):
                metadata[key] = item
            elif isinstance(item, str):
                metadata[key] = item[:240]
        item = {
            "schema": "bx1.voice.event.v1",
            "event": event_type,
            "session_id": session_id,
            "timestamp": timestamp,
            "source": str(value.get("source") or source)[:80],
            "metadata": metadata,
        }
        with self._lock:
            self._events.append(item)
            if event_type == "FaultRaised":
                self._faults.append(item)
        return dict(item)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "schema": "bx1.voice.timeline.v1",
                "events": list(self._events),
                "active_faults": list(self._faults),
                "privacy": "metadata_only_no_audio_prompts_transcripts_or_brain_content",
            }

    def clear_observer_faults(self) -> Dict[str, Any]:
        with self._lock:
            cleared = len(self._faults)
            self._faults.clear()
        return {"ok": True, "cleared": cleared, "scope": "voice_observer_faults_only"}


class VoiceVerticalSlice:
    """OS-side bridge that may ask the existing Body to run a voice-safe test."""

    def __init__(self, timeline: VoiceTimeline, *, body_url: str = "http://127.0.0.1:8088", timeout: float = 5.0) -> None:
        parsed = urlparse(body_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 8088:
            raise ValueError("voice bridge is restricted to loopback Robot Body port 8088")
        self.timeline = timeline
        self.body_url = body_url.rstrip("/")
        self.timeout = max(1.0, min(float(timeout), 20.0))
        self.brain_endpoint = ""

    def update_brain_endpoint(self, body: Mapping[str, Any]) -> str:
        network = body.get("network") if isinstance(body.get("network"), Mapping) else {}
        raw = network.get("brain_app_base_url") or body.get("brain_base_url") or ""
        if isinstance(raw, Mapping):
            raw = raw.get("value", "")
        endpoint = str(raw).strip().rstrip("/")
        if endpoint:
            self.brain_endpoint = endpoint
        return self.brain_endpoint

    def typed_test(self, text: str) -> Dict[str, Any]:
        # Text is used only for this immediate relay and is never placed in timeline/output.
        question = str(text or "").strip()
        if not question or len(question) > 1000:
            raise ValueError("typed_question_must_be_1_to_1000_characters")
        session_id = "voice-" + uuid.uuid4().hex
        for event in ("WakeDetected", "ListeningStarted", "SpeechRecognised"):
            self.timeline.record({"event": event, "session_id": session_id, "source": "typed_test"})
        payload = json.dumps({"text": question, "session_id": session_id}).encode("utf-8")
        req = request.Request(
            self.body_url + "/api/voice/vertical-slice", data=payload, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        started = time.monotonic()
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("body_response_too_large")
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, Mapping) or not bool(result.get("ok")):
                raise ValueError("body_voice_test_failed")
            return {"ok": True, "session_id": session_id, "latency_ms": round((time.monotonic() - started) * 1000, 2), "playback_owner": "robot_body"}
        except (error.HTTPError, error.URLError, socket.timeout, TimeoutError, ValueError, OSError) as exc:
            reason = "body_timeout" if isinstance(exc, (socket.timeout, TimeoutError)) else "body_unavailable"
            self.timeline.record({"event": "FaultRaised", "session_id": session_id, "reason": reason, "source": "bx1_os"})
            return {"ok": False, "session_id": session_id, "error": reason}

    def brain_probe(self) -> Dict[str, Any]:
        endpoint = self.brain_endpoint
        if not endpoint:
            return {"ok": False, "endpoint": "", "error": "brain_endpoint_unavailable_from_body"}
        started = time.monotonic()
        try:
            with request.urlopen(request.Request(endpoint + "/api/status", headers={"Accept": "application/json"}), timeout=self.timeout) as response:
                raw = response.read(65537)
            if response.status >= 400 or len(raw) > 65536:
                raise ValueError("bad_brain_status")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, Mapping):
                raise ValueError("malformed_brain_status")
            return {"ok": True, "endpoint": endpoint, "latency_ms": round((time.monotonic() - started) * 1000, 2)}
        except (error.HTTPError, error.URLError, socket.timeout, TimeoutError, ValueError, OSError):
            return {"ok": False, "endpoint": endpoint, "error": "brain_offline_or_malformed"}
