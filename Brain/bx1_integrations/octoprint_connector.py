from __future__ import annotations

import json
import logging
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests

from bx1_integrations.base import (
    BaseIntegration, ConnectionStatus, IntegrationCapability, IntegrationResult,
    IntegrationSettings, SafetyLevel,
)
from bx1_integrations.events import mask_secret_text


LOG = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT = 2.0
DEFAULT_REQUEST_TIMEOUT = 8.0


def normalise_octoprint_url(value: Any) -> str:
    """Accept hostnames, IPs and pasted Markdown links; return a clean server root."""
    text = str(value or "").strip()
    if "](" in text and text.endswith(")"):
        text = text.rsplit("](", 1)[1][:-1].strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    if path.lower().endswith("/api"):
        path = path[:-4]
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")


def migrate_octoprint_config(config: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """Copy legacy fields into integrations.octoprint without deleting unknown keys."""
    migrated = dict(config)
    integrations = dict(migrated.get("integrations") or {})
    octo = dict(integrations.get("octoprint") or {})
    candidates: List[Any] = list(octo.get("base_urls") or [])
    for key in ("octoprint_url", "octoprint_server_url"):
        if migrated.get(key):
            candidates.append(migrated[key])
    if octo.get("server_url"):
        candidates.append(octo["server_url"])
    urls: List[str] = []
    for candidate in candidates:
        value = normalise_octoprint_url(candidate)
        if value and value not in urls:
            urls.append(value)
    changed = bool(urls and urls != list(octo.get("base_urls") or []))
    if urls:
        octo["base_urls"] = urls
        octo.setdefault("enabled", True)
    integrations["octoprint"] = octo
    migrated["integrations"] = integrations
    return migrated, changed


class OctoPrintRequestError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OctoPrintConnector(BaseIntegration):
    integration_id = "octoprint"
    display_name = "OctoPrint"
    description = "Printer status and confirmed print controls with endpoint failover."
    version = "2.0"

    def __init__(self, settings: Optional[IntegrationSettings] = None, session: Any = None) -> None:
        super().__init__(settings)
        self.session = session or requests.Session()
        self.active_endpoint = ""
        self.endpoint_errors: Dict[str, str] = {}

    @property
    def configuration_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": "enabled", "type": "bool", "default": False},
            {"key": "base_urls", "type": "string_list", "label": "Base URLs"},
            {"key": "api_key", "type": "secret", "secret": True},
            {"key": "connect_timeout", "type": "float", "default": DEFAULT_CONNECT_TIMEOUT},
            {"key": "request_timeout", "type": "float", "default": DEFAULT_REQUEST_TIMEOUT},
            {"key": "printer_name", "type": "string", "required": False},
        ]

    def validate_configuration(self) -> List[str]:
        errors = []
        if not self.endpoints():
            errors.append("At least one OctoPrint address is required")
        if not self._api_key() and not self.settings.mock_mode:
            errors.append("OctoPrint API key is required")
        return errors

    @property
    def capabilities(self) -> List[IntegrationCapability]:
        return [
            IntegrationCapability("get_printer_status", "Get printer status"),
            IntegrationCapability("get_print_progress", "Get print progress"),
            IntegrationCapability("list_files", "List files"),
            IntegrationCapability("pause_print", "Pause print", SafetyLevel.CONTROL),
            IntegrationCapability("resume_print", "Resume print", SafetyLevel.CONTROL),
            IntegrationCapability("select_file", "Select file", SafetyLevel.CONTROL),
            IntegrationCapability("start_print", "Start print", SafetyLevel.SAFETY_CRITICAL),
            IntegrationCapability("cancel_print", "Cancel print", SafetyLevel.SAFETY_CRITICAL),
        ]

    def endpoints(self) -> List[str]:
        raw = self.settings.values.get("base_urls")
        if not raw:
            raw = [self.settings.values.get("server_url")]
        if isinstance(raw, str):
            raw = raw.replace(";", "\n").splitlines()
        result: List[str] = []
        for item in raw or []:
            url = normalise_octoprint_url(item)
            if url and url not in result:
                result.append(url)
        return result

    def _ordered_endpoints(self) -> List[str]:
        endpoints = self.endpoints()
        preferred = normalise_octoprint_url(
            self.settings.values.get("last_successful_endpoint") or
            self.settings.values.get("preferred_endpoint")
        )
        return ([preferred] if preferred in endpoints else []) + [item for item in endpoints if item != preferred]

    def _api_key(self) -> str:
        return str(self.settings.session_secrets.get("api_key") or "")

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "BX1BrainIntegrationHub/2.0"}
        if self._api_key():
            headers["X-Api-Key"] = self._api_key()
        return headers

    def _timeouts(self) -> tuple[float, float]:
        return (
            max(.2, float(self.settings.values.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT))),
            max(.2, float(self.settings.values.get("request_timeout", DEFAULT_REQUEST_TIMEOUT))),
        )

    def _classify_exception(self, exc: Exception) -> OctoPrintRequestError:
        if isinstance(exc, requests.Timeout):
            return OctoPrintRequestError("timeout", "Connection timed out")
        if isinstance(exc, requests.ConnectionError):
            low = str(exc).lower()
            if any(word in low for word in ("name resolution", "getaddrinfo", "nodename", "dns")):
                return OctoPrintRequestError("dns_resolution_failed", "Hostname could not be resolved")
            if "refused" in low:
                return OctoPrintRequestError("connection_refused", "Connection was refused")
            return OctoPrintRequestError("host_unreachable", "Host could not be reached")
        if isinstance(exc, (socket.gaierror,)):
            return OctoPrintRequestError("dns_resolution_failed", "Hostname could not be resolved")
        if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
            return OctoPrintRequestError("unexpected_response", "OctoPrint returned an unexpected response")
        return OctoPrintRequestError("octoprint_error", mask_secret_text(str(exc), [self._api_key()]))

    def _request_endpoint(self, endpoint: str, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(endpoint.rstrip("/") + "/", path.lstrip("/"))
        timeout = kwargs.pop("timeout", self._timeouts())
        try:
            response = self.session.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
            status = int(getattr(response, "status_code", 0) or 0)
            if status in (401, 403):
                raise OctoPrintRequestError("authentication_failed", f"OctoPrint rejected the API key (HTTP {status})")
            if status >= 400:
                raise OctoPrintRequestError("octoprint_http_error", f"OctoPrint returned HTTP {status}")
            content = getattr(response, "content", b"")
            if len(content) > MAX_RESPONSE_BYTES:
                raise OctoPrintRequestError("response_too_large", "OctoPrint response exceeded the safe size limit")
            return {} if not content else json.loads(content.decode("utf-8"))
        except OctoPrintRequestError:
            raise
        except Exception as exc:
            raise self._classify_exception(exc) from exc

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.settings.mock_mode:
            return self._mock_response(path)
        endpoints = self._ordered_endpoints()
        if not endpoints:
            raise OctoPrintRequestError("not_configured", "No OctoPrint address is configured")
        self.endpoint_errors = {}
        last_error = OctoPrintRequestError("unreachable", "Could not reach OctoPrint")
        for endpoint in endpoints:
            LOG.info("OctoPrint endpoint attempt: %s", endpoint)
            try:
                data = self._request_endpoint(endpoint, method, path, **kwargs)
                self.active_endpoint = endpoint
                self.settings.values["last_successful_endpoint"] = endpoint
                self.status = ConnectionStatus.CONNECTED
                LOG.info("OctoPrint selected endpoint: %s", endpoint)
                return data
            except OctoPrintRequestError as exc:
                last_error = exc
                self.endpoint_errors[endpoint] = str(exc)
                LOG.warning("OctoPrint endpoint failed (%s): %s", endpoint, exc.code)
        self.status = ConnectionStatus.ERROR
        if self.endpoint_errors and all("rejected the API key" in value for value in self.endpoint_errors.values()):
            raise OctoPrintRequestError("authentication_failed", "OctoPrint rejected the API key")
        if len(endpoints) == 1:
            raise last_error
        raise OctoPrintRequestError("all_endpoints_failed", f"Could not reach OctoPrint at any configured address ({last_error})")

    def _mock_response(self, path: str) -> Any:
        if "version" in path:
            return {"server": "1.10.0", "api": "0.1"}
        if "printer" in path:
            return {"state": {"text": "Operational"}, "temperature": {"tool0": {"actual": 205.2, "target": 210}, "bed": {"actual": 60.1, "target": 60}}}
        if "job" in path:
            return {"job": {"file": {"name": "demo.gcode"}}, "progress": {"completion": 42.5, "printTimeLeft": 1800}}
        if "files" in path:
            return {"files": [{"name": "demo.gcode", "path": "demo.gcode"}]}
        return {"ok": True}

    def health_check(self) -> IntegrationResult:
        try:
            data = self._request("GET", "/api/version")
            result = IntegrationResult(True, "health_check", {
                "server_version": data.get("server"), "active_endpoint": self.active_endpoint,
            }, "OctoPrint is reachable", summary="Printer service is reachable.", speakable="I can reach the printer.")
            return self._record_result(result)
        except OctoPrintRequestError as exc:
            return self._record_result(IntegrationResult(
                False, "health_check", {"endpoint_errors": dict(self.endpoint_errors)},
                str(exc), error_code=exc.code, summary="Could not reach the printer.",
                speakable="I could not reach the printer at any configured address.",
            ))

    def printer_status(self) -> Dict[str, Any]:
        printer = self._request("GET", "/api/printer")
        job = self._request("GET", "/api/job")
        temps = printer.get("temperature", {}) if isinstance(printer, dict) else {}
        state = printer.get("state", {}) if isinstance(printer, dict) else {}
        progress = job.get("progress", {}) if isinstance(job, dict) else {}
        file_info = (job.get("job", {}) if isinstance(job, dict) else {}).get("file", {})
        return {"state": state.get("text", "unknown"), "nozzle_temperature": temps.get("tool0", {}),
                "bed_temperature": temps.get("bed", {}), "current_job": file_info.get("name") or "",
                "progress": progress.get("completion"), "estimated_time_remaining": progress.get("printTimeLeft")}

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        params = params or {}
        try:
            if action_id in ("get_printer_status", "get_print_progress"):
                data = self.printer_status()
                state = str(data.get("state") or "unknown")
                return self._record_result(IntegrationResult(True, action_id, data, "Printer status loaded",
                    summary=f"Printer state: {state}.", speakable=f"The printer reports {state.lower()}."))
            if action_id == "list_files":
                data = self._request("GET", "/api/files")
                return self._record_result(IntegrationResult(True, action_id, data, "File list loaded", speakable="I loaded the printer file list."))
            if self.settings.mock_mode:
                return self._record_result(IntegrationResult(True, action_id, {"mock": True, "params": params}, f"Mock OctoPrint action: {action_id}"))
            commands = {
                "pause_print": ("POST", "/api/job", {"command": "pause", "action": "pause"}),
                "resume_print": ("POST", "/api/job", {"command": "pause", "action": "resume"}),
                "cancel_print": ("POST", "/api/job", {"command": "cancel"}),
                "start_print": ("POST", "/api/job", {"command": "start"}),
            }
            if action_id == "select_file":
                path = str(params.get("path") or "").lstrip("/")
                self._request("POST", f"/api/files/local/{path}", json={"command": "select", "print": False})
            elif action_id in commands:
                method, path, payload = commands[action_id]
                self._request(method, path, json=payload)
            else:
                return IntegrationResult(False, action_id, error_code="unknown_action", message=f"Unknown action: {action_id}")
            return self._record_result(IntegrationResult(True, action_id, message=f"OctoPrint confirmed {action_id}", speakable="The printer confirmed the command."))
        except OctoPrintRequestError as exc:
            return self._record_result(IntegrationResult(False, action_id, error_code=exc.code, message=str(exc),
                summary="The printer command was not confirmed.", speakable="I could not confirm that printer command."))
