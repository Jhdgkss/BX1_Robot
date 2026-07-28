from __future__ import annotations

import copy
import time
from typing import Any, Callable, Dict, Mapping, Optional

from hardware_services import EventBus, EventType

from .command_router import CommandResult, CommandRouter
from .message import (
    Message,
    MessageCodec,
    MessageStatus,
    MessageValidationError,
    ProtocolVersion,
)
from .message_bus import MessageBus
from .session import SessionManager
from .state_sync import StateSynchronizer


class CommunicationService:
    """Versioned JSON messaging, routing and state sync over in-memory queues."""

    INTERNAL_SENDERS = {"bx1"}

    def __init__(
        self,
        bx1: Any,
        event_bus: EventBus,
        config: Mapping[str, Any],
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.bx1 = bx1
        self.events = event_bus
        self._config = copy.deepcopy(dict(config))
        if str(self._config["transport"]).lower() != "in_memory":
            raise ValueError("Phase 4 CommunicationService requires in_memory transport")
        self._wall_clock = wall_clock
        self._server_version = ProtocolVersion.parse(
            self._config["protocol_version"]
        )
        self.codec = MessageCodec(
            maximum_message_size=int(self._config["maximum_message_size"])
        )
        self.message_bus = MessageBus(
            {
                "mode": "in_memory",
                "maximum_queued_messages": self._config.get(
                    "maximum_queued_messages", 1000
                ),
            },
            clock=monotonic_clock,
        )
        self.sessions = SessionManager(
            event_bus,
            self._config,
            clock=monotonic_clock,
        )
        self.router = CommandRouter(
            bx1,
            capability_provider=self.capabilities,
            protocol_version=str(self._server_version),
        )
        self.state_sync = StateSynchronizer(
            bx1,
            event_bus,
            self._deliver_update,
            clock=wall_clock,
        )
        self._received_count = 0
        self._sent_count = 0
        self._invalid_count = 0
        self._protocol_mismatch_count = 0

    def register_client(
        self,
        client_id: str,
        protocol_version: Optional[str] = None,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        session = self.sessions.register_client(
            client_id,
            protocol_version or str(self._server_version),
            metadata=metadata,
        )
        return {
            "session": session.as_dict(),
            "negotiated_protocol_version": str(self._server_version),
            "capabilities": self.capabilities(),
        }

    def disconnect_client(self, client_id: str) -> bool:
        session = self.sessions.session_for_client(client_id)
        return False if session is None else self.sessions.disconnect(session.session_id)

    def heartbeat(self, client_id: str) -> Dict[str, Any]:
        return self.sessions.heartbeat_client(client_id).as_dict()

    def send(
        self,
        destination: str,
        command: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        sender: str = "bx1",
        response: Any = None,
        status: MessageStatus = MessageStatus.REQUEST,
        protocol_version: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Message:
        try:
            message = self.codec.new(
                protocol_version=protocol_version or str(self._server_version),
                sender=sender,
                destination=destination,
                command=command,
                payload=payload,
                response=response,
                status=status,
                message_id=message_id,
                clock=self._wall_clock,
            )
            encoded = self.codec.encode(message)
        except MessageValidationError as exc:
            self._invalid_count += 1
            self.events.publish(
                EventType.INVALID_MESSAGE,
                {"error": str(exc), "code": exc.code},
                source="communication",
            )
            raise
        self.message_bus.send(message.destination, encoded)
        self._sent_count += 1
        self.events.publish(
            EventType.MESSAGE_SENT,
            self._message_summary(message),
            source="communication",
        )
        return message

    def receive(
        self,
        encoded: Optional[Any] = None,
        *,
        destination: str = "bx1",
    ) -> Optional[Message]:
        raw = self.message_bus.receive(destination) if encoded is None else encoded
        if raw is None:
            return None
        try:
            request = self.codec.decode(raw)
        except MessageValidationError as exc:
            self._invalid_count += 1
            self.events.publish(
                EventType.INVALID_MESSAGE,
                {"error": str(exc), "code": exc.code},
                source="communication",
            )
            raise
        self._received_count += 1
        self.events.publish(
            EventType.MESSAGE_RECEIVED,
            self._message_summary(request),
            source="communication",
        )

        client_version = ProtocolVersion.parse(request.protocol_version)
        if not self._server_version.compatible_with(client_version):
            self._protocol_mismatch_count += 1
            self.events.publish(
                EventType.PROTOCOL_MISMATCH,
                {
                    "sender": request.sender,
                    "client_version": request.protocol_version,
                    "server_version": str(self._server_version),
                },
                source="communication",
            )
            return self._respond_error(
                request,
                "PROTOCOL_MISMATCH",
                "Message protocol is incompatible with BX1",
            )
        if request.destination not in {"bx1", "robot"}:
            return self._respond_error(
                request,
                "WRONG_DESTINATION",
                "Message is not addressed to BX1",
            )
        if request.status != MessageStatus.REQUEST.value:
            return self._respond_error(
                request,
                "INVALID_STATUS",
                "Inbound command must have request status",
            )
        if request.sender not in self.INTERNAL_SENDERS:
            if not self.sessions.active(request.sender):
                return self._respond_error(
                    request,
                    "SESSION_REQUIRED",
                    "Client must register an active session",
                )
            self.sessions.heartbeat_client(request.sender)

        if request.command == "session.heartbeat":
            result = CommandResult(
                True,
                data=self.sessions.heartbeat_client(request.sender).as_dict(),
            )
        else:
            result = self.router.route(request.command, request.payload)
        return self._respond(request, result)

    def request(
        self,
        client_id: str,
        command: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        protocol_version: Optional[str] = None,
    ) -> Message:
        if not self.sessions.active(client_id):
            raise RuntimeError("client must register before sending a request")
        request = self.codec.new(
            protocol_version=protocol_version
            or self.sessions.session_for_client(client_id).protocol_version,  # type: ignore[union-attr]
            sender=client_id,
            destination="bx1",
            command=command,
            payload=payload,
            status=MessageStatus.REQUEST,
            clock=self._wall_clock,
        )
        response = self.receive(self.codec.encode(request))
        if response is None:
            raise RuntimeError("communication request produced no response")
        return response

    def receive_for(self, client_id: str) -> Optional[Message]:
        raw = self.message_bus.receive(client_id)
        return None if raw is None else self.codec.decode(raw)

    def process_next(self) -> Optional[Message]:
        return self.receive()

    def subscribe(
        self,
        topic: str,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        *,
        client_id: str = "local",
        deliver_initial: bool = True,
    ) -> str:
        if client_id != "local" and not self.sessions.active(client_id):
            raise RuntimeError("remote subscription requires an active session")
        return self.state_sync.subscribe(
            topic,
            client_id=client_id,
            callback=callback,
            deliver_initial=deliver_initial,
        )

    def unsubscribe(self, subscription_id: str) -> bool:
        return self.state_sync.unsubscribe(subscription_id)

    def publish(self, topic: str, value: Mapping[str, Any]) -> int:
        return self.state_sync.publish(topic, value)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "protocol_version": str(self._server_version),
            "registered": self.bx1.capabilities.capabilities(),
            "details": self.bx1.capabilities.diagnostics()["capabilities"],
            "services": self.bx1.services.names(),
            "commands": self.router.commands(),
            "subscriptions": sorted(self.state_sync.TOPICS),
            "transport": "in_memory",
        }

    def tick(self) -> Dict[str, Any]:
        return {
            "expired_sessions": self.sessions.expire_sessions(),
            "state_sync": self.state_sync.sync(),
        }

    def status(self) -> Dict[str, Any]:
        return {
            "service": "communication",
            "state": "READY" if self._config["enabled"] else "DISABLED",
            "protocol_version": str(self._server_version),
            "transport": "in_memory",
            "active_clients": self.sessions.status()["active_sessions"],
        }

    def health(self) -> Dict[str, Any]:
        enabled = bool(self._config["enabled"])
        return {
            "healthy": enabled,
            "available": enabled,
            "state": "READY" if enabled else "DISABLED",
            "reason": "In-memory communication ready" if enabled else "Communication disabled",
        }

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "received_count": self._received_count,
            "sent_count": self._sent_count,
            "invalid_count": self._invalid_count,
            "protocol_mismatch_count": self._protocol_mismatch_count,
            "message_bus": self.message_bus.diagnostics(),
            "sessions": self.sessions.diagnostics(),
            "router": self.router.diagnostics(),
            "state_sync": self.state_sync.diagnostics(),
            "network_used": False,
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _respond(self, request: Message, result: CommandResult) -> Message:
        return self.send(
            request.sender,
            request.command,
            {},
            sender="bx1",
            response=result.as_response(),
            status=MessageStatus.OK if result.ok else MessageStatus.ERROR,
            message_id=request.message_id,
        )

    def _respond_error(self, request: Message, code: str, error: str) -> Message:
        return self._respond(
            request,
            CommandResult(False, error_code=code, error=error),
        )

    def _deliver_update(
        self,
        client_id: str,
        topic: str,
        update: Mapping[str, Any],
    ) -> None:
        self.send(
            client_id,
            "state.%s" % topic,
            update,
            sender="bx1",
            status=MessageStatus.EVENT,
        )

    @staticmethod
    def _message_summary(message: Message) -> Dict[str, Any]:
        return {
            "protocol_version": message.protocol_version,
            "message_id": message.message_id,
            "sender": message.sender,
            "destination": message.destination,
            "command": message.command,
            "status": message.status,
        }
