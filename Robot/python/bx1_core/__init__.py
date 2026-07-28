"""Permanent BX1 OS core-service foundation."""

from .bootstrap import (
    ALPHA_REQUIRED_SERVICES,
    BootstrapError,
    BootstrapResult,
    CompatibilityServiceAdapter,
    ServiceFactory,
    bootstrap_runtime,
)
from .diagnostics import DiagnosticsService
from .config import DEFAULT_CORE_CONFIGURATION, load_core_configuration
from .communication import (
    ClientSession,
    CommandResult,
    CommandRouter,
    CommunicationService,
    Message,
    MessageBus,
    MessageCodec,
    MessageStatus,
    MessageValidationError,
    ProtocolVersion,
    SessionManager,
    SessionState,
    StateSynchronizer,
    Subscription,
)
from .health import HealthMonitor
from .logging_service import LogLevel, LogRecord, LoggingService, ServiceLogger
from .root import BX1, create_bx1
from .scheduler import ScheduledTask, SchedulerService
from .service_registry import (
    ServiceLifecycleState,
    ServiceRegistration,
    ServiceRegistry,
)

__all__ = [
    "BX1",
    "ALPHA_REQUIRED_SERVICES",
    "BootstrapError",
    "BootstrapResult",
    "ClientSession",
    "CommandResult",
    "CommandRouter",
    "CommunicationService",
    "CompatibilityServiceAdapter",
    "DEFAULT_CORE_CONFIGURATION",
    "DiagnosticsService",
    "HealthMonitor",
    "LogLevel",
    "LogRecord",
    "LoggingService",
    "Message",
    "MessageBus",
    "MessageCodec",
    "MessageStatus",
    "MessageValidationError",
    "ProtocolVersion",
    "ScheduledTask",
    "SchedulerService",
    "ServiceLifecycleState",
    "ServiceLogger",
    "ServiceFactory",
    "ServiceRegistration",
    "ServiceRegistry",
    "SessionManager",
    "SessionState",
    "StateSynchronizer",
    "Subscription",
    "bootstrap_runtime",
    "create_bx1",
    "load_core_configuration",
]
