from __future__ import annotations

import copy
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional

from hardware_services import EventBus, EventType

from .message import MessageValidationError, ProtocolVersion


class SessionState(str, Enum):
    ACTIVE = "ACTIVE"
    TIMED_OUT = "TIMED_OUT"
    DISCONNECTED = "DISCONNECTED"


@dataclass
class ClientSession:
    session_id: str
    client_id: str
    protocol_version: str
    created_at: float
    last_heartbeat_at: float
    state: SessionState
    metadata: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return value


class SessionManager:
    def __init__(
        self,
        event_bus: EventBus,
        config: Mapping[str, Any],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.events = event_bus
        self._config = dict(config)
        self._clock = clock
        self._server_version = ProtocolVersion.parse(
            self._config["protocol_version"]
        )
        self._sessions: Dict[str, ClientSession] = {}
        self._clients: Dict[str, str] = {}

    def register_client(
        self,
        client_id: str,
        protocol_version: str,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ClientSession:
        client = str(client_id).strip()
        if not client:
            raise ValueError("client_id must not be empty")
        client_version = ProtocolVersion.parse(protocol_version)
        if not self._server_version.compatible_with(client_version):
            self.events.publish(
                EventType.PROTOCOL_MISMATCH,
                {
                    "client": client,
                    "client_version": str(client_version),
                    "server_version": str(self._server_version),
                },
                source="session_manager",
            )
            raise MessageValidationError(
                "client protocol is incompatible with BX1",
                code="PROTOCOL_MISMATCH",
            )
        existing = self.session_for_client(client)
        if existing is not None and existing.state == SessionState.ACTIVE:
            existing.last_heartbeat_at = self._clock()
            return existing
        active = sum(
            item.state == SessionState.ACTIVE for item in self._sessions.values()
        )
        if active >= int(self._config["maximum_clients"]):
            raise RuntimeError("maximum communication clients reached")
        now = self._clock()
        session = ClientSession(
            uuid.uuid4().hex,
            client,
            str(client_version),
            now,
            now,
            SessionState.ACTIVE,
            dict(metadata or {}),
        )
        self._sessions[session.session_id] = session
        self._clients[client] = session.session_id
        self.events.publish(
            EventType.CLIENT_CONNECTED,
            session.as_dict(),
            source="session_manager",
        )
        return session

    def heartbeat(self, session_id: str) -> ClientSession:
        session = self._require(session_id)
        if session.state != SessionState.ACTIVE:
            raise RuntimeError("session is not active")
        session.last_heartbeat_at = self._clock()
        return session

    def heartbeat_client(self, client_id: str) -> ClientSession:
        session = self.session_for_client(client_id)
        if session is None:
            raise KeyError("client has no session: %s" % client_id)
        return self.heartbeat(session.session_id)

    def disconnect(self, session_id: str, *, reason: str = "Client disconnected") -> bool:
        session = self._sessions.get(str(session_id))
        if session is None or session.state == SessionState.DISCONNECTED:
            return False
        session.state = SessionState.DISCONNECTED
        self.events.publish(
            EventType.CLIENT_DISCONNECTED,
            {**session.as_dict(), "reason": reason},
            source="session_manager",
        )
        return True

    def expire_sessions(self) -> List[str]:
        now = self._clock()
        timeout = float(self._config["timeout_s"])
        expired: List[str] = []
        for session in list(self._sessions.values()):
            if (
                session.state == SessionState.ACTIVE
                and now - session.last_heartbeat_at > timeout
            ):
                session.state = SessionState.TIMED_OUT
                expired.append(session.session_id)
                self.events.publish(
                    EventType.HEARTBEAT_TIMEOUT,
                    session.as_dict(),
                    source="session_manager",
                )
                self.events.publish(
                    EventType.CLIENT_DISCONNECTED,
                    {**session.as_dict(), "reason": "Heartbeat timeout"},
                    source="session_manager",
                )
        return expired

    def session_for_client(self, client_id: str) -> Optional[ClientSession]:
        session_id = self._clients.get(str(client_id).strip())
        return None if session_id is None else self._sessions.get(session_id)

    def active(self, client_id: str) -> bool:
        session = self.session_for_client(client_id)
        return bool(session and session.state == SessionState.ACTIVE)

    def status(self) -> Dict[str, Any]:
        return {
            "service": "session_manager",
            "state": "READY",
            "active_sessions": sum(
                item.state == SessionState.ACTIVE
                for item in self._sessions.values()
            ),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "healthy": True,
            "available": True,
            "state": "READY",
            "reason": "Session manager ready",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "sessions": {
                key: value.as_dict()
                for key, value in sorted(self._sessions.items())
            }
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _require(self, session_id: str) -> ClientSession:
        try:
            return self._sessions[str(session_id)]
        except KeyError as exc:
            raise KeyError("unknown session: %s" % session_id) from exc
