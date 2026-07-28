from __future__ import annotations

import base64
import hashlib
import os
import time
from urllib.parse import urlencode
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
    description = "Spotify account, playback state and confirmed Spotify Connect controls."
    version = "2.0"

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
            IntegrationCapability("play_request", "Search and play music", SafetyLevel.CONTROL),
            IntegrationCapability("adjust_volume", "Adjust volume", SafetyLevel.CONTROL),
        ]

    @property
    def configuration_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": "enabled", "type": "bool", "default": False},
            {"key": "client_id", "type": "string", "required": True},
            {"key": "client_secret", "type": "secret", "secret": True, "required": False},
            {"key": "redirect_uri", "type": "string", "default": "http://127.0.0.1:8765/spotify/callback"},
            {"key": "scopes", "type": "string"},
            {"key": "preferred_device", "type": "string", "required": False},
            {"key": "robot_device_id", "type": "string", "required": False},
            {"key": "robot_device_name", "type": "string", "required": False},
            {"key": "default_music_source", "type": "string", "default": "liked_songs"},
            {"key": "request_timeout", "type": "float", "default": 8.0},
        ]

    def validate_configuration(self) -> List[str]:
        errors: List[str] = []
        if not self.settings.values.get("client_id") and not self.settings.mock_mode:
            errors.append("Spotify client ID is required")
        redirect = str(self.settings.values.get("redirect_uri") or "")
        if redirect and not redirect.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
            errors.append("Spotify redirect URI must be HTTPS or a loopback HTTP address")
        return errors

    def begin_authorization(self, *, state: str = "") -> Dict[str, str]:
        verifier, challenge = generate_pkce_pair()
        self.pkce_verifier = verifier
        client_id = str(self.settings.values.get("client_id") or "")
        redirect_uri = str(self.settings.values.get("redirect_uri") or "http://127.0.0.1:8765/spotify/callback")
        scope = str(self.settings.values.get("scopes") or "user-read-private user-read-playback-state user-modify-playback-state playlist-read-private user-read-currently-playing")
        query = urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
                           "scope": scope, "code_challenge_method": "S256", "code_challenge": challenge})
        return {
            "verifier": verifier,
            "challenge": challenge,
            "state": state,
            "url": f"{SPOTIFY_AUTH_URL}?{query}",
        }

    def exchange_code(self, code: str) -> IntegrationResult:
        if not code or not self.pkce_verifier:
            return IntegrationResult(False, "exchange_code", error_code="oauth_state_missing", message="Start Spotify connection before completing sign-in")
        data = {"grant_type": "authorization_code", "code": code,
                "redirect_uri": str(self.settings.values.get("redirect_uri") or "http://127.0.0.1:8765/spotify/callback"),
                "client_id": str(self.settings.values.get("client_id") or ""), "code_verifier": self.pkce_verifier}
        try:
            response = self.session.post(SPOTIFY_TOKEN_URL, data=data, timeout=self._timeout())
            if response.status_code >= 400:
                return self._spotify_error("exchange_code", response)
            self._save_token(response.json())
            return IntegrationResult(True, "exchange_code", message="Spotify account connected", speakable="Spotify is connected.")
        except requests.Timeout:
            return IntegrationResult(False, "exchange_code", error_code="timeout", message="Spotify sign-in timed out")
        except Exception as exc:
            return IntegrationResult(False, "exchange_code", error_code="oauth_error", message=mask_secret_text(str(exc), self.settings.session_secrets.values()))

    def _timeout(self) -> float:
        return max(.5, float(self.settings.values.get("request_timeout", 8.0)))

    def _save_token(self, payload: Dict[str, Any]) -> None:
        self.settings.session_secrets["access_token"] = str(payload.get("access_token") or "")
        if payload.get("refresh_token"):
            self.settings.session_secrets["refresh_token"] = str(payload["refresh_token"])
        self.settings.session_secrets["token_type"] = str(payload.get("token_type") or "Bearer")
        self.settings.session_secrets["expires_at"] = str(time.time() + int(payload.get("expires_in", 3600)))

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
        try:
            response = self.session.post(SPOTIFY_TOKEN_URL, data=data, timeout=self._timeout())
        except requests.Timeout:
            return IntegrationResult(False, "refresh_token", error_code="timeout", message="Spotify token refresh timed out")
        except Exception as exc:
            return IntegrationResult(False, "refresh_token", error_code="token_refresh_failed", message=mask_secret_text(str(exc), self.settings.session_secrets.values()))
        if response.status_code >= 400:
            return self._spotify_error("refresh_token", response)
        payload = response.json()
        self._save_token(payload)
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
        if not token.access_token:
            refresh = self.refresh_token()
            if not refresh.ok:
                raise RuntimeError(refresh.error_code or "authentication_required")
        response = self.session.request(method, SPOTIFY_API_URL + path, headers=self._headers(), timeout=self._timeout(), **kwargs)
        if response.status_code in (401, 403, 429):
            raise RuntimeError(self._spotify_error(path, response).error_code)
        if response.status_code >= 400:
            raise RuntimeError(f"Spotify HTTP {response.status_code}")
        if response.status_code == 204:
            return {}
        return response.json()

    def _devices(self) -> List[Dict[str, Any]]:
        payload = self._request("GET", "/me/player/devices")
        return list(payload.get("devices") or []) if isinstance(payload, dict) else []

    def _select_device(self, *, require_robot_device: bool = False) -> tuple[str, List[Dict[str, Any]]]:
        devices = self._devices()
        if require_robot_device:
            preferred = str(self.settings.values.get("robot_device_id") or self.settings.values.get("robot_device_name") or "").lower()
            if not preferred:
                return "", devices
        else:
            preferred = str(self.settings.values.get("preferred_device_id") or self.settings.values.get("preferred_device") or "").lower()
        selected = next((d for d in devices if str(d.get("id") or "").lower() == preferred or str(d.get("name") or "").lower() == preferred), None)
        if require_robot_device:
            return (str(selected.get("id") or "") if selected else ""), devices
        selected = selected or next((d for d in devices if d.get("is_active")), None)
        if selected is None and len(devices) == 1:
            selected = devices[0]
        return (str(selected.get("id") or "") if selected else ""), devices

    def _search(self, query: str, kinds: str = "track,artist,album,playlist", limit: int = 5) -> Dict[str, Any]:
        return self._request("GET", "/search?" + urlencode({"q": query, "type": kinds, "limit": limit}))

    @staticmethod
    def _best_item(payload: Dict[str, Any], query: str) -> tuple[str, Dict[str, Any]]:
        wanted = query.casefold().strip()
        candidates: List[tuple[int, str, Dict[str, Any]]] = []
        for plural, kind in (("tracks", "track"), ("artists", "artist"), ("albums", "album"), ("playlists", "playlist")):
            for item in ((payload.get(plural) or {}).get("items") or []):
                name = str(item.get("name") or "").casefold().strip()
                score = 100 if name == wanted else (80 if wanted in name or name in wanted else 20)
                if kind == "artist":
                    score += 5
                candidates.append((score, kind, item))
        if not candidates:
            return "", {}
        _, kind, item = max(candidates, key=lambda row: row[0])
        return kind, item

    def _play_request(self, params: Dict[str, Any], device_id: str) -> IntegrationResult:
        query = str(params.get("query") or "").strip()
        if not query:
            source = str(self.settings.values.get("default_music_source") or "liked_songs")
            if source == "resume":
                self._request("PUT", f"/me/player/play?device_id={device_id}")
                return IntegrationResult(True, "play_request", {"device_id": device_id, "selection": "current context"},
                                         "Spotify resumed playback", speakable="Playing Spotify through the robot.")
            saved = self._request("GET", "/me/tracks?limit=50")
            uris = [str(row.get("track", {}).get("uri") or "") for row in saved.get("items", [])]
            uris = [uri for uri in uris if uri]
            if not uris:
                return IntegrationResult(False, "play_request", error_code="no_default_music",
                                         message="Liked Songs is empty and no default playlist is configured")
            self._request("PUT", f"/me/player/play?device_id={device_id}", json={"uris": uris})
            return IntegrationResult(True, "play_request", {"device_id": device_id, "selection": "Liked Songs"},
                                     "Spotify started Liked Songs", speakable="Playing your Liked Songs through the robot.")
        kind, item = self._best_item(self._search(query), query)
        if not item:
            return IntegrationResult(False, "play_request", error_code="no_search_match", message=f"I could not find a confident Spotify match for {query}")
        if kind == "track":
            body = {"uris": [item.get("uri")]}
        else:
            body = {"context_uri": item.get("uri")}
        self._request("PUT", f"/me/player/play?device_id={device_id}", json=body)
        artists = ", ".join(str(a.get("name") or "") for a in item.get("artists", []))
        label = str(item.get("name") or query)
        selection = f"{label} by {artists}" if artists else label
        return IntegrationResult(True, "play_request", {"device_id": device_id, "selection": selection, "type": kind},
                                 f"Spotify started {selection}", speakable=f"Playing {selection} through the robot.")

    def health_check(self) -> IntegrationResult:
        try:
            account = self._request("GET", "/me")
            device_id, devices = self._select_device()
            if not device_id:
                return self._record_result(IntegrationResult(True, "health_check",
                    {"account": account.get("display_name") or account.get("id"), "devices": devices},
                    "Spotify account is connected, but no playback device is available",
                    error_code="no_active_device", summary="Spotify is authenticated; no playback device is active.",
                    speakable="Spotify is connected, but I cannot find an active playback device."))
            return self._record_result(IntegrationResult(True, "health_check",
                {"account": account.get("display_name") or account.get("id"), "selected_device_id": device_id},
                "Spotify account and playback device are available", speakable="Spotify is connected and a playback device is available."))
        except Exception as exc:
            code = str(exc)
            return self._record_result(IntegrationResult(False, "health_check", error_code=code, message=self._friendly_error(code)))

    def _friendly_error(self, code: str) -> str:
        return {
            "authentication_required": "Spotify account connection is required",
            "expired_authorization": "Spotify authorization expired; reconnect the account",
            "forbidden_or_missing_premium": "Spotify denied playback control; Premium may be required",
            "rate_limited": "Spotify rate limit reached; try again later",
            "no_active_device": "No Spotify Connect playback device is available",
        }.get(code, mask_secret_text(code, self.settings.session_secrets.values()))

    def _mock_response(self, path: str) -> Any:
        if path == "/me":
            return {"id": "mock-user", "display_name": "Demo Account"}
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
                if action_id == "play_request":
                    selection = str(params.get("query") or "Liked Songs")
                    destination = "the robot" if params.get("require_robot_device") else "the selected Spotify device"
                    return IntegrationResult(True, action_id, {"mock": True, "selection": selection, "device": destination},
                                             f"Spotify accepted playback of {selection}",
                                             speakable=f"Playing {selection} through {destination}.")
                return IntegrationResult(True, action_id, {"mock": True, "params": params}, f"Mock Spotify action: {action_id}")
            device_id = str(params.get("device_id") or "")
            if action_id in {"play", "pause", "play_pause", "next", "previous", "volume", "adjust_volume", "queue_track", "play_request"} and not device_id:
                require_robot = bool(params.get("require_robot_device"))
                device_id, devices = self._select_device(require_robot_device=require_robot)
                if not device_id:
                    detail = ("The configured robot Spotify Connect device is not available"
                              if require_robot else "Spotify is connected, but no playback device is available")
                    return IntegrationResult(False, action_id, {"devices": devices}, error_code="no_active_device",
                                             message=detail,
                                             speakable="Spotify is connected, but I cannot find the robot playback device. Start Spotify Connect on the robot and try again.")
            query = f"?device_id={device_id}" if device_id else ""
            selected = next((d for d in devices if str(d.get("id") or "") == device_id), {}) if 'devices' in locals() else {}
            if selected and not selected.get("is_active"):
                self._request("PUT", "/me/player", json={"device_ids": [device_id], "play": False})
            if action_id == "play_request":
                return self._play_request(params, device_id)
            if action_id == "pause":
                self._request("PUT", "/me/player/pause" + query)
            elif action_id == "play":
                self._request("PUT", "/me/player/play" + query)
            elif action_id == "play_pause":
                path = "/me/player/pause" if params.get("is_playing", True) else "/me/player/play"
                self._request("PUT", path + query)
            elif action_id == "next":
                self._request("POST", "/me/player/next" + query)
            elif action_id == "previous":
                self._request("POST", "/me/player/previous" + query)
            elif action_id == "volume":
                separator = "&" if query else "?"
                self._request("PUT", f"/me/player/volume{query}{separator}volume_percent={max(0, min(100, int(params.get('volume', 50))))}")
            elif action_id == "adjust_volume":
                playback = self._request("GET", "/me/player")
                current = int((playback.get("device") or {}).get("volume_percent") or 50)
                target = max(0, min(100, current + int(params.get("delta") or 0)))
                self._request("PUT", f"/me/player/volume?device_id={device_id}&volume_percent={target}")
            elif action_id == "transfer_playback":
                self._request("PUT", "/me/player", json={"device_ids": [params.get("device_id")], "play": False})
            elif action_id == "queue_track":
                self._request("POST", f"/me/player/queue?uri={params.get('uri')}")
            else:
                return IntegrationResult(False, action_id, error_code="unknown_action", message=f"Unknown action: {action_id}")
            return IntegrationResult(True, action_id, message=f"Spotify confirmed {action_id}", speakable="Spotify confirmed the command.")
        except Exception as exc:
            code = str(exc)
            return IntegrationResult(False, action_id, error_code=code, message=self._friendly_error(code),
                                     summary="Spotify did not confirm the command.", speakable="Spotify did not confirm that command.")
