"""Local-first, non-replaying Robot Body endpoint resolver for the Brain."""
from __future__ import annotations

import time
import json
import uuid
from typing import Any, Dict, Iterable, Optional
from urllib import request


class RobotEndpointResolver:
    def __init__(self, configured: str = "", candidates: Optional[Iterable[str]] = None) -> None:
        configured = str(configured or "").rstrip("/")
        supplied = [str(item or "").rstrip("/") for item in (candidates or []) if str(item or "").strip()]
        ordered = ["http://192.168.68.54:8088", "http://100.72.130.12:8088", *supplied]
        if configured:
            ordered.append(configured)
        self.candidates = list(dict.fromkeys(item for item in ordered if item))
        self.preferred = self.candidates[0] if self.candidates else ""
        self.active = self.preferred
        self.last_failure_reason = ""
        self.last_latency_ms: Optional[float] = None
        self.last_success_at = ""
        self.local_probe: Dict[str, Any] = {"state": "not_probed"}
        self.fallback_probe: Dict[str, Any] = {"state": "not_probed"}
        self._last_probe = 0.0

    @staticmethod
    def route(url: str) -> str:
        return "local" if "192.168." in url or "127.0.0.1" in url else "tailscale" if "100.72.130.12" in url else "configured"

    def choose(self, timeout: float = 1.2, force: bool = False) -> str:
        if self.active and not force and time.monotonic() - self._last_probe < 10.0:
            return self.active
        last = ""
        for candidate in self.candidates:
            started = time.perf_counter()
            try:
                with request.urlopen(candidate + "/api/status", timeout=timeout) as response:
                    if response.status >= 500:
                        raise RuntimeError(f"HTTP {response.status}")
                latency = round((time.perf_counter() - started) * 1000.0, 1)
                stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                probe = {"state": "available", "latency_ms": latency, "at": stamp}
                if self.route(candidate) == "local": self.local_probe = probe
                elif self.route(candidate) == "tailscale": self.fallback_probe = probe
                self.active, self.last_latency_ms, self.last_success_at = candidate, latency, stamp
                self.last_failure_reason, self._last_probe = "", time.monotonic()
                return candidate
            except Exception as exc:
                last = str(exc)
                probe = {"state": "unavailable", "error": last}
                if self.route(candidate) == "local": self.local_probe = probe
                elif self.route(candidate) == "tailscale": self.fallback_probe = probe
        self.last_failure_reason = last or "no_robot_endpoint"
        self._last_probe = time.monotonic()
        raise RuntimeError(self.last_failure_reason)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "preferred_endpoint": self.preferred,
            "active_endpoint": self.active,
            "active_route": self.route(self.active) if self.active else "unavailable",
            "candidates": list(self.candidates),
            "local_probe": dict(self.local_probe),
            "fallback_probe": dict(self.fallback_probe),
            "latency_ms": self.last_latency_ms,
            "last_failure_reason": self.last_failure_reason,
            "last_successful_connection": self.last_success_at,
        }

    def request(self, path: str, *, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> bytes:
        """Perform exactly one request on the selected route; POST is never replayed."""
        endpoint = self.choose(timeout=min(timeout, 2.0))
        request_id = str(uuid.uuid4())
        body = None
        headers = {"Accept": "application/json"}
        if method.upper() == "POST":
            data = dict(payload or {})
            data.setdefault("request_id", request_id)
            body = json.dumps(data).encode("utf-8")
            headers.update({"Content-Type": "application/json", "X-BX1-Request-ID": request_id})
        req = request.Request(endpoint.rstrip("/") + path, data=body, method=method.upper(), headers=headers)
        with request.urlopen(req, timeout=timeout) as response:
            return response.read()
