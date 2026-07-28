from __future__ import annotations

import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict
from urllib.parse import parse_qs, urlparse


class SpotifyOAuthCallback:
    """Single-use loopback OAuth receiver. It never logs callback URLs or codes."""

    def __init__(self, redirect_uri: str, *, timeout: float = 180.0) -> None:
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.port:
            raise ValueError("Spotify redirect URI must be a loopback HTTP URI with an explicit port")
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path or "/callback"
        self.timeout = max(10.0, min(600.0, float(timeout)))
        self.state = secrets.token_urlsafe(32)
        self.result: Dict[str, str] = {}
        self._event = threading.Event()
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != owner.path:
                    self.send_error(404)
                    return
                query = parse_qs(parsed.query)
                owner.result = {
                    "state": str((query.get("state") or [""])[0]),
                    "code": str((query.get("code") or [""])[0]),
                    "error": str((query.get("error") or [""])[0]),
                }
                body = b"Spotify authorization received. You may close this window and return to BX1 Brain."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                owner._event.set()

            def log_message(self, _format: str, *_args: object) -> None:
                return

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as exc:
            raise RuntimeError(f"Spotify callback port {self.port} is unavailable") from exc
        threading.Thread(target=self._server.serve_forever, name="spotify-oauth-callback", daemon=True).start()

    def wait(self) -> Dict[str, str]:
        if not self._event.wait(self.timeout):
            self.stop()
            return {"error": "callback_timeout", "state": "", "code": ""}
        self.stop()
        if self.result.get("error"):
            return {"error": "user_denied", "state": self.result.get("state", ""), "code": ""}
        if self.result.get("state") != self.state:
            return {"error": "state_mismatch", "state": "", "code": ""}
        if not self.result.get("code"):
            return {"error": "missing_authorization_code", "state": "", "code": ""}
        return {"error": "", "state": self.state, "code": self.result["code"]}

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
