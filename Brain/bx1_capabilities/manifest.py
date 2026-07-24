from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from bx1_capabilities.models import (
    BROAD_TRIGGER_WORDS,
    CAPABILITY_ID_RE,
    CapabilityAction,
    CapabilityManifest,
    CapabilityPermission,
    CapabilityType,
    CapabilityValidationError,
)


REQUIRED_MANIFEST_FIELDS = (
    "capability_id",
    "display_name",
    "version",
    "description",
    "capability_type",
    "trigger_phrases",
    "actions",
    "permissions",
    "confirmation_policy",
    "allowed_network_domains",
    "allowed_file_paths",
    "timeout_seconds",
    "dependencies",
    "settings_schema",
    "ui_schema",
    "created_by",
    "created_timestamp",
    "minimum_brain_version",
    "checksum",
    "enabled_by_default",
    "limitations",
    "cannot_do",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_trigger_phrase(phrase: str) -> str:
    text = re.sub(r"\s+", " ", str(phrase or "").strip())
    if len(text) < 8:
        raise CapabilityValidationError(f"Trigger phrase is too short: {text!r}")
    if text.lower() in BROAD_TRIGGER_WORDS or len(text.split()) < 3 and not text.startswith("@"):
        raise CapabilityValidationError(f"Trigger phrase is too broad: {text!r}")
    return text


def _as_list(value: Any, field: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CapabilityValidationError(f"{field} must be a list.")
    return value


def validate_ui_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        raise CapabilityValidationError("ui_schema must be an object.")
    allowed_controls = {"text", "secret", "checkbox", "dropdown", "multiline", "approved_item_list", "action_button", "status", "activity_log"}
    controls = schema.get("controls", [])
    if controls is None:
        controls = []
    if not isinstance(controls, list):
        raise CapabilityValidationError("ui_schema.controls must be a list.")
    for index, control in enumerate(controls):
        if not isinstance(control, dict):
            raise CapabilityValidationError(f"ui_schema.controls[{index}] must be an object.")
        control_type = str(control.get("type") or "")
        if control_type not in allowed_controls:
            raise CapabilityValidationError(f"Unsupported UI control type: {control_type}")
        if any(key in control for key in ("python", "script", "callback", "code")):
            raise CapabilityValidationError("Executable UI definitions are not allowed.")
    return dict(schema)


def validate_manifest_dict(data: Dict[str, Any]) -> CapabilityManifest:
    if not isinstance(data, dict):
        raise CapabilityValidationError("manifest.json must contain an object.")
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in data]
    if missing:
        raise CapabilityValidationError("Missing manifest fields: " + ", ".join(missing))
    capability_id = str(data["capability_id"]).strip()
    if not CAPABILITY_ID_RE.match(capability_id):
        raise CapabilityValidationError("capability_id must be lowercase snake_case, 3-64 characters.")
    capability_type = str(data["capability_type"]).strip()
    if capability_type not in {item.value for item in CapabilityType}:
        raise CapabilityValidationError("capability_type is invalid.")
    version = str(data["version"]).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9_.-]+)?", version):
        raise CapabilityValidationError("version must be a dotted version label.")
    permissions = [str(item).strip() for item in _as_list(data.get("permissions"), "permissions") if str(item).strip()]
    if not permissions:
        permissions = [CapabilityPermission.NONE.value]
    valid_permissions = {item.value for item in CapabilityPermission}
    invalid_permissions = [item for item in permissions if item not in valid_permissions]
    if invalid_permissions:
        raise CapabilityValidationError("Invalid permissions: " + ", ".join(invalid_permissions))
    dependencies = [str(item).strip() for item in _as_list(data.get("dependencies"), "dependencies") if str(item).strip()]
    if dependencies:
        raise CapabilityValidationError("External dependencies are not supported in Phase 2.")
    trigger_phrases = [validate_trigger_phrase(item) for item in _as_list(data.get("trigger_phrases"), "trigger_phrases")]
    actions_raw = _as_list(data.get("actions"), "actions")
    if not actions_raw:
        raise CapabilityValidationError("At least one action is required.")
    actions: List[CapabilityAction] = []
    for index, item in enumerate(actions_raw):
        if not isinstance(item, dict):
            raise CapabilityValidationError(f"actions[{index}] must be an object.")
        action_id = str(item.get("action_id") or item.get("id") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", action_id):
            raise CapabilityValidationError(f"Invalid action_id: {action_id!r}")
        action_permissions = [str(p).strip() for p in item.get("permissions", []) if str(p).strip()]
        for permission in action_permissions:
            if permission not in valid_permissions:
                raise CapabilityValidationError(f"Invalid action permission: {permission}")
        actions.append(CapabilityAction(action_id, str(item.get("description") or ""), action_permissions, bool(item.get("confirmation_required", False))))
    timeout = float(data.get("timeout_seconds") or 5)
    if timeout <= 0 or timeout > 30:
        raise CapabilityValidationError("timeout_seconds must be between 0 and 30.")
    domains = [str(item).strip().lower() for item in _as_list(data.get("allowed_network_domains"), "allowed_network_domains") if str(item).strip()]
    for domain in domains:
        if "/" in domain or "\\" in domain or "://" in domain:
            raise CapabilityValidationError(f"Network domain must be a hostname only: {domain}")
    return CapabilityManifest(
        capability_id=capability_id,
        display_name=str(data["display_name"]).strip(),
        version=version,
        description=str(data["description"]).strip(),
        capability_type=capability_type,
        trigger_phrases=trigger_phrases,
        actions=actions,
        permissions=permissions,
        confirmation_policy=dict(data.get("confirmation_policy") or {}),
        allowed_network_domains=domains,
        allowed_file_paths=[str(item).strip() for item in _as_list(data.get("allowed_file_paths"), "allowed_file_paths") if str(item).strip()],
        timeout_seconds=timeout,
        dependencies=dependencies,
        settings_schema=dict(data.get("settings_schema") or {}),
        ui_schema=validate_ui_schema(dict(data.get("ui_schema") or {})),
        created_by=str(data["created_by"]).strip(),
        created_timestamp=str(data["created_timestamp"]).strip(),
        minimum_brain_version=str(data["minimum_brain_version"]).strip(),
        checksum=str(data["checksum"]).strip(),
        enabled_by_default=bool(data["enabled_by_default"]),
        limitations=[str(item) for item in _as_list(data.get("limitations"), "limitations")],
        cannot_do=[str(item) for item in _as_list(data.get("cannot_do"), "cannot_do")],
        raw=dict(data),
    )


def load_manifest(path: Path) -> CapabilityManifest:
    return validate_manifest_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def manifest_with_checksum(manifest: Dict[str, Any], capability_py: Path) -> Dict[str, Any]:
    updated = dict(manifest)
    updated["checksum"] = sha256_file(capability_py)
    return updated

