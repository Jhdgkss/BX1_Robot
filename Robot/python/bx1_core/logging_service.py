from __future__ import annotations

import copy
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional


class LogLevel(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


@dataclass(frozen=True)
class LogRecord:
    timestamp: float
    level: str
    service: str
    message: str
    context: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["context"] = dict(self.context)
        return value


class ServiceLogger:
    def __init__(self, logging_service: "LoggingService", service: str) -> None:
        self._logging = logging_service
        self._service = str(service)

    def debug(self, message: str, **context: Any) -> Optional[LogRecord]:
        return self._logging.debug(message, service=self._service, **context)

    def info(self, message: str, **context: Any) -> Optional[LogRecord]:
        return self._logging.info(message, service=self._service, **context)

    def warning(self, message: str, **context: Any) -> Optional[LogRecord]:
        return self._logging.warning(message, service=self._service, **context)

    def error(self, message: str, **context: Any) -> Optional[LogRecord]:
        return self._logging.error(message, service=self._service, **context)


class LoggingService:
    """Structured in-memory logging with injectable future sinks."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = {
            "enabled": True,
            "level": "INFO",
            "buffer_size": 1000,
            "file_logging_enabled": False,
            "file_path": "",
            **dict(config or {}),
        }
        self._clock = clock
        self._level = self._parse_level(self._config["level"])
        self._records: Deque[LogRecord] = deque(
            maxlen=max(1, int(self._config["buffer_size"]))
        )
        self._sinks: Dict[str, Callable[[LogRecord], None]] = {}
        self._sink_failures = 0

    def debug(self, message: str, *, service: str = "bx1", **context: Any) -> Optional[LogRecord]:
        return self._log(LogLevel.DEBUG, service, message, context)

    def info(self, message: str, *, service: str = "bx1", **context: Any) -> Optional[LogRecord]:
        return self._log(LogLevel.INFO, service, message, context)

    def warning(self, message: str, *, service: str = "bx1", **context: Any) -> Optional[LogRecord]:
        return self._log(LogLevel.WARNING, service, message, context)

    def error(self, message: str, *, service: str = "bx1", **context: Any) -> Optional[LogRecord]:
        return self._log(LogLevel.ERROR, service, message, context)

    def service(self, service: str) -> ServiceLogger:
        return ServiceLogger(self, str(service).strip())

    def records(
        self,
        *,
        service: Optional[str] = None,
        minimum_level: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        threshold = None if minimum_level is None else self._parse_level(minimum_level)
        result = []
        for item in self._records:
            if service is not None and item.service != service:
                continue
            if threshold is not None and self._parse_level(item.level) < threshold:
                continue
            result.append(item.as_dict())
        return result

    def add_sink(self, name: str, sink: Callable[[LogRecord], None]) -> None:
        if not callable(sink):
            raise TypeError("log sink must be callable")
        key = str(name).strip()
        if not key:
            raise ValueError("log sink name must not be empty")
        self._sinks[key] = sink

    def remove_sink(self, name: str) -> bool:
        return self._sinks.pop(str(name).strip(), None) is not None

    def status(self) -> Dict[str, Any]:
        return {
            "service": "logging",
            "state": "READY" if self._config["enabled"] else "DISABLED",
            "record_count": len(self._records),
            "level": self._level.name,
        }

    def health(self) -> Dict[str, Any]:
        state = self.status()["state"]
        return {
            "healthy": state == "READY",
            "available": state == "READY",
            "state": state,
            "reason": "Logging service ready" if state == "READY" else "Logging disabled",
        }

    def diagnostics(self) -> Dict[str, Any]:
        counts = Counter(record.level for record in self._records)
        services = Counter(record.service for record in self._records)
        return {
            "record_count": len(self._records),
            "levels": dict(counts),
            "services": dict(services),
            "sink_count": len(self._sinks),
            "sink_failures": self._sink_failures,
            "file_logging_active": False,
        }

    def configuration(self) -> Dict[str, Any]:
        return copy.deepcopy(self._config)

    def _log(
        self,
        level: LogLevel,
        service: str,
        message: str,
        context: Mapping[str, Any],
    ) -> Optional[LogRecord]:
        if not self._config["enabled"] or level < self._level:
            return None
        record = LogRecord(
            self._clock(),
            level.name,
            str(service).strip() or "bx1",
            str(message),
            dict(context),
        )
        self._records.append(record)
        for sink in list(self._sinks.values()):
            try:
                sink(record)
            except Exception:
                self._sink_failures += 1
        return record

    @staticmethod
    def _parse_level(value: Any) -> LogLevel:
        if isinstance(value, LogLevel):
            return value
        if isinstance(value, int):
            return LogLevel(value)
        try:
            return LogLevel[str(value).strip().upper()]
        except KeyError as exc:
            raise ValueError("unsupported log level: %s" % value) from exc
