"""Redacted observer and safe Body bridge for the v0.6 voice vertical slice."""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Dict, Mapping, Optional
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

    def session_state(self, session_id: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Return metadata-only progress for one correlation id."""
        current = float(self.clock() if now is None else now)
        matching = [item for item in self.snapshot()["events"] if item.get("session_id") == session_id]
        if not matching:
            return {"state": "unknown", "reason": "session_not_observed"}
        last = matching[-1]
        if last.get("event") == "FaultRaised":
            return {"state": "failed", "reason": str(last.get("metadata", {}).get("reason") or "unknown_fault")}
        if last.get("event") == "SpeechFinished":
            return {"state": "complete", "reason": "playback_finished"}
        if last.get("event") == "SpeechStarted":
            return {"state": "playing", "reason": "body_playback_started"}
        if last.get("event") == "ThinkingStarted":
            age_ms = max(0, round((current - float(last.get("timestamp") or current)) * 1000))
            return {"state": "thinking", "reason": "brain_processing", "age_ms": age_ms}
        return {"state": "sending", "reason": "body_request_accepted"}


class VoiceVerticalSlice:
    """OS-side bridge that may ask the existing Body to run a voice-safe test."""

    def __init__(
        self,
        timeline: VoiceTimeline,
        *,
        body_url: str = "http://127.0.0.1:8088",
        probe_timeout: float = 5.0,
        request_timeout: float = 240.0,
        opener: Optional[Callable[..., Any]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        parsed = urlparse(body_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 8088:
            raise ValueError("voice bridge is restricted to loopback Robot Body port 8088")
        self.timeline = timeline
        self.body_url = body_url.rstrip("/")
        self.probe_timeout = max(1.0, min(float(probe_timeout), 20.0))
        self.request_timeout = max(10.0, min(float(request_timeout), 300.0))
        self.opener = opener or request.urlopen
        self.clock = clock
        self.brain_endpoint = ""
        self.connection = {"state": "not_connected", "reason": "not_probed", "updated_at": 0.0}
        self._accepted_sessions: Dict[str, float] = {}

    def update_brain_endpoint(self, body: Mapping[str, Any]) -> str:
        telemetry = body.get("telemetry") if isinstance(body.get("telemetry"), Mapping) else {}
        if isinstance(telemetry.get("value"), Mapping):
            telemetry = telemetry["value"]
        network = body.get("network") if isinstance(body.get("network"), Mapping) else telemetry.get("network", {})
        network = network if isinstance(network, Mapping) else {}
        raw = network.get("brain_app_base_url") or body.get("brain_base_url") or ""
        if isinstance(raw, Mapping):
            raw = raw.get("value", "")
        endpoint = self._safe_endpoint(str(raw).strip())
        if endpoint:
            self.brain_endpoint = endpoint
        return self.brain_endpoint

    @staticmethod
    def _safe_endpoint(value: str) -> str:
        parsed = urlparse(value if "://" in value else "http://" + value)
        if not parsed.hostname or not parsed.port:
            return ""
        host = parsed.hostname
        parts = host.split(".")
        if len(parts) == 4 and all(part.isdigit() for part in parts):
            host = ".".join(parts[:3] + ["*"])
        elif len(host) > 6:
            host = host[:3] + "…"
        return "%s:%s" % (host, parsed.port)

    def connection_snapshot(self) -> Dict[str, Any]:
        return {
            "state": str(self.connection.get("state") or "not_connected"),
            "reason": str(self.connection.get("reason") or "not_probed"),
            "endpoint": self.brain_endpoint,
            "updated_at": float(self.connection.get("updated_at") or 0.0),
        }

    def session_state(self, session_id: str) -> Dict[str, Any]:
        """Report metadata-only progress and surface a missing observer update."""
        state = self.timeline.session_state(session_id)
        accepted_at = self._accepted_sessions.get(session_id)
        if (
            accepted_at is not None
            and state.get("state") in {"unknown", "sending", "thinking"}
            and (time.time() - accepted_at) > 10.0
        ):
            return {"state": "degraded", "reason": "observer_event_delay"}
        return state

    def _remember_accepted_session(self, session_id: str) -> None:
        self._accepted_sessions[session_id] = time.time()
        if len(self._accepted_sessions) > 250:
            cutoff = time.time() - 3600.0
            self._accepted_sessions = {
                key: value for key, value in self._accepted_sessions.items()
                if value >= cutoff
            }

    def _body_json(self, path: str, payload: Mapping[str, Any], timeout: float) -> Dict[str, Any]:
        req = request.Request(
            self.body_url + path,
            data=json.dumps(dict(payload)).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with self.opener(req, timeout=timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("body_response_too_large")
        result = json.loads(raw.decode("utf-8"))
        if not isinstance(result, Mapping):
            raise ValueError("body_response_malformed")
        return dict(result)

    def typed_test(self, text: str) -> Dict[str, Any]:
        # Text is used only for this immediate relay and is never placed in timeline/output.
        question = str(text or "").strip()
        if not question or len(question) > 1000:
            raise ValueError("typed_question_must_be_1_to_1000_characters")
        session_id = "voice-" + uuid.uuid4().hex
        started = self.clock()
        try:
            result = self._body_json(
                "/api/voice/vertical-slice",
                {"text": question, "session_id": session_id},
                self.request_timeout,
            )
            if not bool(result.get("ok")):
                reason = str(result.get("failure_stage") or "body_request_rejected")
                self.timeline.record({"event": "FaultRaised", "session_id": session_id, "reason": reason, "source": "bx1_os"})
                return {"ok": False, "session_id": session_id, "error": reason, "state": "failed"}
            self._remember_accepted_session(session_id)
            return {
                "ok": True,
                "session_id": session_id,
                "latency_ms": round((self.clock() - started) * 1000, 2),
                "playback_owner": "robot_body",
                "state": "playing_reply",
            }
        except (error.HTTPError, error.URLError, socket.timeout, TimeoutError, ValueError, OSError) as exc:
            reason = "body_response_timeout" if isinstance(exc, (socket.timeout, TimeoutError)) else "body_response_unavailable"
            self.timeline.record({"event": "FaultRaised", "session_id": session_id, "reason": reason, "source": "bx1_os"})
            return {"ok": False, "session_id": session_id, "error": reason, "state": "failed"}

    def brain_probe(self) -> Dict[str, Any]:
        started = self.clock()
        try:
            value = self._body_json("/api/voice/vertical-slice/probe", {}, self.probe_timeout)
            state = str(value.get("state") or "not_connected")
            reason = str(value.get("reason") or "brain_probe_malformed")
            self.connection = {"state": state, "reason": reason, "updated_at": time.time()}
            if value.get("endpoint"):
                self.brain_endpoint = self._safe_endpoint(str(value.get("endpoint"))) or self.brain_endpoint
            return {
                "ok": state == "connected",
                "state": state,
                "reason": reason,
                "endpoint": self.brain_endpoint,
                "latency_ms": round((self.clock() - started) * 1000, 2),
            }
        except (error.HTTPError, error.URLError, socket.timeout, TimeoutError, ValueError, OSError):
            self.connection = {"state": "not_connected", "reason": "body_probe_unavailable", "updated_at": time.time()}
            return {"ok": False, "state": "not_connected", "reason": "body_probe_unavailable", "endpoint": self.brain_endpoint}
