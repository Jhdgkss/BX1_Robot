from __future__ import annotations

import json
import math
import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


class MessageValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "INVALID_MESSAGE") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, order=True)
class ProtocolVersion:
    major: int
    minor: int
    patch: int

    PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

    @classmethod
    def parse(cls, value: Any) -> "ProtocolVersion":
        text = str(value).strip()
        match = cls.PATTERN.fullmatch(text)
        if match is None:
            raise MessageValidationError(
                "protocol_version must use MAJOR.MINOR.PATCH",
                code="INVALID_PROTOCOL_VERSION",
            )
        return cls(*(int(part) for part in match.groups()))

    def compatible_with(self, other: "ProtocolVersion") -> bool:
        return self.major == other.major

    def __str__(self) -> str:
        return "%d.%d.%d" % (self.major, self.minor, self.patch)


class MessageStatus(str, Enum):
    REQUEST = "request"
    OK = "ok"
    ERROR = "error"
    EVENT = "event"


@dataclass(frozen=True)
class Message:
    protocol_version: str
    message_id: str
    timestamp: float
    sender: str
    destination: str
    command: str
    payload: Mapping[str, Any]
    response: Any
    status: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "sender": self.sender,
            "destination": self.destination,
            "command": self.command,
            "payload": dict(self.payload),
            "response": self.response,
            "status": self.status,
        }


class MessageCodec:
    REQUIRED_FIELDS = {
        "protocol_version",
        "message_id",
        "timestamp",
        "sender",
        "destination",
        "command",
        "payload",
        "response",
        "status",
    }
    ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
    ENDPOINT_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
    COMMAND_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")

    def __init__(self, *, maximum_message_size: int = 65536) -> None:
        self.maximum_message_size = int(maximum_message_size)
        if self.maximum_message_size < 256:
            raise ValueError("maximum_message_size must be at least 256 bytes")

    def encode(self, message: Message) -> str:
        validated = self.validate(message.as_dict())
        try:
            encoded = json.dumps(
                validated.as_dict(),
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise MessageValidationError(
                "message contains non-JSON data: %s" % exc
            ) from exc
        if len(encoded.encode("utf-8")) > self.maximum_message_size:
            raise MessageValidationError(
                "message exceeds maximum size",
                code="MESSAGE_TOO_LARGE",
            )
        return encoded

    def decode(self, encoded: Any) -> Message:
        if isinstance(encoded, bytes):
            if len(encoded) > self.maximum_message_size:
                raise MessageValidationError(
                    "message exceeds maximum size",
                    code="MESSAGE_TOO_LARGE",
                )
            try:
                text = encoded.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MessageValidationError("message is not UTF-8") from exc
        elif isinstance(encoded, str):
            text = encoded
            if len(text.encode("utf-8")) > self.maximum_message_size:
                raise MessageValidationError(
                    "message exceeds maximum size",
                    code="MESSAGE_TOO_LARGE",
                )
        else:
            raise MessageValidationError("encoded message must be str or bytes")
        try:
            value = json.loads(text, object_pairs_hook=self._unique_object)
        except MessageValidationError:
            raise
        except (json.JSONDecodeError, TypeError) as exc:
            raise MessageValidationError("message is not valid JSON: %s" % exc) from exc
        return self.validate(value)

    def validate(self, value: Any) -> Message:
        if isinstance(value, Message):
            value = value.as_dict()
        if not isinstance(value, Mapping):
            raise MessageValidationError("message root must be an object")
        fields = set(value)
        missing = sorted(self.REQUIRED_FIELDS - fields)
        extra = sorted(fields - self.REQUIRED_FIELDS)
        if missing:
            raise MessageValidationError("missing message fields: %s" % ", ".join(missing))
        if extra:
            raise MessageValidationError("unknown message fields: %s" % ", ".join(extra))

        version = str(ProtocolVersion.parse(value["protocol_version"]))
        message_id = str(value["message_id"])
        if self.ID_PATTERN.fullmatch(message_id) is None:
            raise MessageValidationError("message_id has invalid format")
        timestamp = self._finite(value["timestamp"], "timestamp")
        if timestamp < 0.0:
            raise MessageValidationError("timestamp must not be negative")
        sender = self._endpoint(value["sender"], "sender")
        destination = self._endpoint(value["destination"], "destination")
        command = str(value["command"]).strip()
        if command != "GET capabilities" and self.COMMAND_PATTERN.fullmatch(command) is None:
            raise MessageValidationError("command has invalid format")
        payload = value["payload"]
        if not isinstance(payload, Mapping):
            raise MessageValidationError("payload must be an object")
        try:
            json.dumps(payload, allow_nan=False)
            json.dumps(value["response"], allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise MessageValidationError("payload/response is not JSON-safe: %s" % exc) from exc
        try:
            status = MessageStatus(str(value["status"])).value
        except ValueError as exc:
            raise MessageValidationError("status is not supported") from exc
        if status == MessageStatus.REQUEST.value and value["response"] is not None:
            raise MessageValidationError("request response must be null")

        return Message(
            version,
            message_id,
            timestamp,
            sender,
            destination,
            command,
            dict(payload),
            value["response"],
            status,
        )

    def new(
        self,
        *,
        protocol_version: str,
        sender: str,
        destination: str,
        command: str,
        payload: Optional[Mapping[str, Any]] = None,
        response: Any = None,
        status: MessageStatus = MessageStatus.REQUEST,
        message_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        clock: Callable[[], float] = time.time,
    ) -> Message:
        return self.validate(
            {
                "protocol_version": protocol_version,
                "message_id": message_id or uuid.uuid4().hex,
                "timestamp": clock() if timestamp is None else timestamp,
                "sender": sender,
                "destination": destination,
                "command": command,
                "payload": dict(payload or {}),
                "response": response,
                "status": status.value if isinstance(status, MessageStatus) else str(status),
            }
        )

    @staticmethod
    def _endpoint(value: Any, label: str) -> str:
        result = str(value).strip()
        if MessageCodec.ENDPOINT_PATTERN.fullmatch(result) is None:
            raise MessageValidationError("%s has invalid format" % label)
        return result

    @staticmethod
    def _finite(value: Any, label: str) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise MessageValidationError("%s must be numeric" % label) from exc
        if not math.isfinite(result):
            raise MessageValidationError("%s must be finite" % label)
        return result

    @staticmethod
    def _unique_object(pairs: list[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise MessageValidationError("duplicate JSON field: %s" % key)
            result[key] = value
        return result
