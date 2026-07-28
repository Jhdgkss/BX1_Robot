from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class IntegrationRoute:
    integration_id: str
    action_id: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reason: str = ""
    requires_confirmation: bool = False


_INFORMATIONAL = (
    r"\bwho (founded|created|owns) spotify\b",
    r"\bwhat is (spotify|octoprint)\b",
    r"\b(explain|describe) (how )?(spotify|octoprint)\b",
    r"\b(program|code|script).*\bplay(s|ing)? music\b",
    r"\b(listened|listening) to\b.*\b(yesterday|earlier|last)\b",
)


def route_integration_request(message: str, *, source: str = "", enabled: Optional[set[str]] = None) -> Optional[IntegrationRoute]:
    text = " ".join(str(message or "").lower().split())
    if not text or any(re.search(pattern, text) for pattern in _INFORMATIONAL):
        return None
    enabled = enabled or {"spotify", "octoprint"}
    robot_source = source in {"robot_microphone", "robot_body", "robot"}
    spotify_args: Dict[str, Any] = {"require_robot_device": robot_source}

    if "spotify" in enabled or any(word in text for word in ("music", "song", "track", "playlist", "pink floyd")):
        if re.search(r"\b(what|which).*(song|track).*(playing|on)\b|\bwhat(?:'s| is) playing\b", text):
            return IntegrationRoute("spotify", "get_playback_state", reason="playback status question")
        if re.search(r"\b(pause|stop) (the )?(music|song|spotify|playback)\b", text):
            return IntegrationRoute("spotify", "pause", spotify_args, reason="explicit playback pause")
        if re.search(r"\b(skip|next)( the)? (song|track)?\b|\bskip this song\b", text):
            return IntegrationRoute("spotify", "next", spotify_args, reason="explicit next-track command")
        if re.search(r"\b(previous|last) (song|track)\b", text):
            return IntegrationRoute("spotify", "previous", spotify_args, reason="explicit previous-track command")
        volume = re.search(r"\b(?:set|turn).*(?:volume|music).*(?:to )?(\d{1,3})\s*(?:percent|%)?", text)
        if volume:
            return IntegrationRoute("spotify", "volume", {**spotify_args, "volume": min(100, int(volume.group(1)))}, reason="explicit volume")
        if re.search(r"\b(turn|put).*(music|volume).*(down|quieter|lower)\b", text):
            return IntegrationRoute("spotify", "adjust_volume", {**spotify_args, "delta": -10}, reason="relative volume down")
        if re.search(r"\b(turn|put).*(music|volume).*(up|louder|higher)\b", text):
            return IntegrationRoute("spotify", "adjust_volume", {**spotify_args, "delta": 10}, reason="relative volume up")
        play = re.search(r"\b(?:play|put on|listen to)\s+(.+)", text)
        if play:
            query = play.group(1).strip(" .")
            query = re.sub(r"\s+(?:from|on)\s+spotify$", "", query).strip()
            if query in {"music", "some music", "something", "something from spotify", "spotify"}:
                query = ""
            return IntegrationRoute("spotify", "play_request", {**spotify_args, "query": query}, reason="explicit music request")

    if "octoprint" in enabled or "print" in text or "printer" in text:
        if re.search(r"\b(confirm|yes).*\bpause.*\bprint", text):
            return IntegrationRoute("octoprint", "pause_print", {"confirmed": True}, reason="confirmed print pause")
        if re.search(r"\bpause (the )?print\b", text):
            return IntegrationRoute("octoprint", "pause_print", reason="print pause", requires_confirmation=True)
        if re.search(r"\bresume (the )?print\b", text):
            return IntegrationRoute("octoprint", "resume_print", reason="print resume", requires_confirmation=True)
        if re.search(r"\bcancel (the )?print\b", text):
            return IntegrationRoute("octoprint", "cancel_print", reason="print cancellation", requires_confirmation=True)
        if re.search(r"\b(temperature|temp).*(printer|print)|\b(printer|print).*(temperature|temp)\b", text):
            return IntegrationRoute("octoprint", "get_printer_status", {"focus": "temperatures"}, reason="printer temperature question")
        if re.search(r"\b(how long|time).*(left|remaining).*\bprint|\bprint.*(time left|remaining)\b", text):
            return IntegrationRoute("octoprint", "get_print_progress", {"focus": "remaining"}, reason="print time question")
        if re.search(r"\b(print|printer).*(status|progress|doing)\b", text):
            return IntegrationRoute("octoprint", "get_printer_status", reason="printer status question")
    return None
