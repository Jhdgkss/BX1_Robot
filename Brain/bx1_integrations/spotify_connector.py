from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult, IntegrationSettings, SafetyLevel
from bx1_integrations.events import mask_secret_text


SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"


def generate_pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(64)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


@dataclass
class SpotifyToken:
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0
    token_type: str = "Bearer"

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and time.time() >= self.expires_at - 60


class SpotifyConnector(BaseIntegration):
    integration_id = "spotify"
    display_name = "Spotify"

    def __init__(self, settings: Optional[IntegrationSettings] = None, session: Any = None) -> None:
        super().__init__(settings)
        self.session = session or requests.Session()
        self.pkce_verifier = ""

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return [
            IntegrationCapability("get_playback_state", "Get playback state"),
            IntegrationCapability("list_devices", "List devices"),
            IntegrationCapability("play_pause", "Play / pause", SafetyLevel.CONTROL),
            IntegrationCapability("play", "Play", SafetyLevel.CONTROL),
            IntegrationCapability("pause", "Pause", SafetyLevel.CONTROL),
            IntegrationCapability("next", "Next", SafetyLevel.CONTROL),
            IntegrationCapability("previous", "Previous", SafetyLevel.CONTROL),
            IntegrationCapability("volume", "Set volume", SafetyLevel.CONTROL),
            IntegrationCapability("transfer_playback", "Transfer playback", SafetyLevel.CONTROL),
            IntegrationCapability("queue_track", "Queue track", SafetyLevel.CONTROL),
        ]

    def begin_authorization(self) -> Dict[str, str]:
        verifier, challenge = generate_pkce_pair()
        self.pkce_verifier = verifier
        client_id = str(self.settings.values.get("client_id") or "")
        redirect_uri = str(self.settings.values.get("redirect_uri") or "http://127.0.0.1:8765/spotify/callback")
        scope = "user-read-playback-state user-modify-playback-state playlist-read-private user-read-currently-playing"
        return {
            "verifier": verifier,
            "challenge": challenge,
            "url": f"{SPOTIFY_AUTH_URL}?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}&code_challenge_method=S256&code_challenge={challenge}",
        }

    def _token(self) -> SpotifyToken:
        secret = self.settings.session_secrets
        return SpotifyToken(
            str(secret.get("access_token") or ""),
            str(secret.get("refresh_token") or ""),
            float(secret.get("expires_at") or 0),
            str(secret.get("token_type") or "Bearer"),
        )

    def refresh_token(self) -> IntegrationResult:
        token = self._token()
        if self.settings.mock_mode:
            self.settings.session_secrets["access_token"] = "mock-access"
            self.settings.session_secrets["expires_at"] = str(time.time() + 3600)
            return IntegrationResult(True, "refresh_token", {"mock": True}, "Mock token refreshed")
        if not token.refresh_token:
            return IntegrationResult(False, "refresh_token", error_code="expired_authorization", message="Spotify authorization expired")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": str(self.settings.values.get("client_id") or ""),
        }
        response = self.session.post(SPOTIFY_TOKEN_URL, data=data, timeout=8)
        if response.status_code >= 400:
            return self._spotify_error("refresh_token", response)
        payload = response.json()
        self.settings.session_secrets["access_token"] = payload.get("access_token", "")
        if payload.get("refresh_token"):
            self.settings.session_secrets["refresh_token"] = payload["refresh_token"]
        self.settings.session_secrets["expires_at"] = str(time.time() + int(payload.get("expires_in", 3600)))
        return IntegrationResult(True, "refresh_token", {"expires_in": payload.get("expires_in")}, "Spotify token refreshed")

    def _headers(self) -> Dict[str, str]:
        token = self._token()
        return {"Authorization": f"{token.token_type} {token.access_token}", "User-Agent": "BX1BrainIntegrationHub/1.0"}

    def _spotify_error(self, action_id: str, response: Any) -> IntegrationResult:
        status = int(getattr(response, "status_code", 0) or 0)
        codes = {
            401: "expired_authorization",
            403: "forbidden_or_missing_premium",
            429: "rate_limited",
        }
        return IntegrationResult(False, action_id, error_code=codes.get(status, "spotify_http_error"), message=f"Spotify HTTP {status}")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.settings.mock_mode:
            return self._mock_response(path)
        token = self._token()
        if token.expired:
            refresh = self.refresh_token()
            if not refresh.ok:
                raise RuntimeError(refresh.message)
        response = self.session.request(method, SPOTIFY_API_URL + path, headers=self._headers(), timeout=8, **kwargs)
        if response.status_code in (401, 403, 429):
            raise RuntimeError(self._spotify_error(path, response).error_code)
        if response.status_code >= 400:
            raise RuntimeError(f"Spotify HTTP {response.status_code}")
        if response.status_code == 204:
            return {}
        return response.json()

    def _mock_response(self, path: str) -> Any:
        if "devices" in path:
            return {"devices": [{"id": "mock-device", "name": "Demo Spotify Connect", "is_active": True}]}
        return {"is_playing": True, "device": {"name": "Demo Spotify Connect"}, "item": {"name": "Demo Track", "artists": [{"name": "BX1"}]}}

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        params = params or {}
        try:
            if action_id in ("get_playback_state", "get_currently_playing"):
                return IntegrationResult(True, action_id, self._request("GET", "/me/player"), "Playback state loaded")
            if action_id == "list_devices":
                return IntegrationResult(True, action_id, self._request("GET", "/me/player/devices"), "Devices loaded")
            if self.settings.mock_mode:
                return IntegrationResult(True, action_id, {"mock": True, "params": params}, f"Mock Spotify action: {action_id}")
            if action_id == "pause":
                self._request("PUT", "/me/player/pause")
            elif action_id == "play":
                self._request("PUT", "/me/player/play")
            elif action_id == "play_pause":
                self._request("PUT", "/me/player/pause" if params.get("is_playing", True) else "/me/player/play")
            elif action_id == "next":
                self._request("POST", "/me/player/next")
            elif action_id == "previous":
                self._request("POST", "/me/player/previous")
            elif action_id == "volume":
                self._request("PUT", f"/me/player/volume?volume_percent={int(params.get('volume', 50))}")
            elif action_id == "transfer_playback":
                self._request("PUT", "/me/player", json={"device_ids": [params.get("device_id")], "play": False})
            elif action_id == "queue_track":
                self._request("POST", f"/me/player/queue?uri={params.get('uri')}")
            else:
                return IntegrationResult(False, action_id, error_code="unknown_action", message=f"Unknown action: {action_id}")
            return IntegrationResult(True, action_id, message=f"Spotify action completed: {action_id}")
        except Exception as exc:
            return IntegrationResult(False, action_id, error_code=str(exc), message=mask_secret_text(str(exc), self.settings.session_secrets.values()))

