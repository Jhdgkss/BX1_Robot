from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class CapabilityError(Exception):
    pass


class CapabilityValidationError(CapabilityError):
    pass


class CapabilitySecurityError(CapabilityError):
    pass


class CapabilityPermission(str, Enum):
    NONE = "NONE"
    READ_LOCAL_DATA = "READ_LOCAL_DATA"
    WRITE_LOCAL_DATA = "WRITE_LOCAL_DATA"
    NETWORK_READ = "NETWORK_READ"
    NETWORK_CONTROL = "NETWORK_CONTROL"
    ROBOT_CONTROL = "ROBOT_CONTROL"
    HARDWARE_CONTROL = "HARDWARE_CONTROL"
    PROCESS_EXECUTION = "PROCESS_EXECUTION"


class CapabilityType(str, Enum):
    BEHAVIOUR = "behaviour"
    INTEGRATION = "integration"
    TOOL = "tool"
    HARDWARE = "hardware"


CAPABILITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
BROAD_TRIGGER_WORDS = {"hello", "hi", "help", "thanks", "yes", "no", "ok", "start", "stop", "run"}


@dataclass(frozen=True)
class CapabilityAction:
    action_id: str
    description: str = ""
    permissions: List[str] = field(default_factory=list)
    confirmation_required: bool = False


@dataclass(frozen=True)
class CapabilityManifest:
    capability_id: str
    display_name: str
    version: str
    description: str
    capability_type: str
    trigger_phrases: List[str]
    actions: List[CapabilityAction]
    permissions: List[str]
    confirmation_policy: Dict[str, Any]
    allowed_network_domains: List[str]
    allowed_file_paths: List[str]
    timeout_seconds: float
    dependencies: List[str]
    settings_schema: Dict[str, Any]
    ui_schema: Dict[str, Any]
    created_by: str
    created_timestamp: str
    minimum_brain_version: str
    checksum: str
    enabled_by_default: bool
    limitations: List[str]
    cannot_do: List[str]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityRecord:
    manifest: CapabilityManifest
    path: str
    state: str = "installed"


@dataclass(frozen=True)
class CapabilityRunResult:
    ok: bool
    capability_id: str
    action: str
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: str = ""
    duration_s: float = 0.0
    stdout: str = ""
    stderr: str = ""
    requires_confirmation: bool = False

