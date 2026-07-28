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
from .core import BX1Core
from .events import CoreEvent, CoreEventBus, CoreEventType
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
from .health import (
    HealthMonitor,
    HealthState,
    PluginHealth,
    aggregate_plugin_health,
)
from .logging_service import LogLevel, LogRecord, LoggingService, ServiceLogger
from .root import BX1, create_bx1
from .registry import CoreServiceRegistry, PluginRegistry
from .scheduler import ScheduledTask, SchedulerService
from .service_registry import (
    ServiceLifecycleState,
    ServiceRegistration,
    ServiceRegistry,
)
from .state import DEFAULT_STATE, StateChange, StateStore
from .telemetry import TelemetryPublisher

__all__ = [
    "BX1",
    "BX1Core",
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
    "CoreEvent",
    "CoreEventBus",
    "CoreEventType",
    "CoreServiceRegistry",
    "HealthMonitor",
    "HealthState",
    "LogLevel",
    "LogRecord",
    "LoggingService",
    "Message",
    "MessageBus",
    "MessageCodec",
    "MessageStatus",
    "MessageValidationError",
    "ProtocolVersion",
    "PluginHealth",
    "PluginRegistry",
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
    "StateChange",
    "StateStore",
    "Subscription",
    "TelemetryPublisher",
    "DEFAULT_STATE",
    "aggregate_plugin_health",
    "bootstrap_runtime",
    "create_bx1",
    "load_core_configuration",
]
