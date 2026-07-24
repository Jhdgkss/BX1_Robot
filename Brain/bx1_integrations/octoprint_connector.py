from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from bx1_integrations.base import BaseIntegration, IntegrationCapability, IntegrationResult, IntegrationSettings, SafetyLevel
from bx1_integrations.events import mask_secret_text


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 8.0


class OctoPrintConnector(BaseIntegration):
    integration_id = "octoprint"
    display_name = "OctoPrint"

    def __init__(self, settings: Optional[IntegrationSettings] = None, session: Any = None) -> None:
        super().__init__(settings)
        self.session = session or requests.Session()

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

    def _base_url(self) -> str:
        return str(self.settings.values.get("server_url") or "").rstrip("/") + "/"

    def _api_key(self) -> str:
        return str(self.settings.session_secrets.get("api_key") or "")

    def _headers(self) -> Dict[str, str]:
        api_key = self._api_key()
        headers = {"User-Agent": "BX1BrainIntegrationHub/1.0"}
        if api_key:
            headers["X-Api-Key"] = api_key
        bearer = str(self.settings.session_secrets.get("bearer_token") or "")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.settings.mock_mode:
            return self._mock_response(path)
        url = urljoin(self._base_url(), path.lstrip("/"))
        timeout = float(kwargs.pop("timeout", DEFAULT_TIMEOUT))
        response = self.session.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        if int(getattr(response, "status_code", 0) or 0) >= 400:
            raise RuntimeError(f"OctoPrint HTTP {response.status_code}")
        content = getattr(response, "content", b"")
        if len(content) > MAX_RESPONSE_BYTES:
            raise RuntimeError("OctoPrint response exceeded size limit")
        if not content:
            return {}
        return json.loads(content.decode("utf-8"))

    def _mock_response(self, path: str) -> Any:
        if "version" in path:
            return {"server": "1.10.0", "api": "0.1"}
        if "printer" in path:
            return {"state": {"text": "Operational"}, "temperature": {"tool0": {"actual": 205.2, "target": 210}, "bed": {"actual": 60.1, "target": 60}}}
        if "job" in path:
            return {"job": {"file": {"name": "demo.gcode"}, "estimatedPrintTime": 3600}, "progress": {"completion": 42.5, "printTimeLeft": 1800}}
        if "files" in path:
            return {"files": [{"name": "demo.gcode", "path": "demo.gcode"}]}
        return {"ok": True}

    def health_check(self) -> IntegrationResult:
        try:
            data = self._request("GET", "/api/version")
            warning = ""
            if not self._api_key() and not self.settings.mock_mode:
                warning = "OctoPrint API key is missing; disabled access control would be a security risk."
            return IntegrationResult(True, "health_check", data, warning or "OctoPrint reachable")
        except requests.Timeout:
            return IntegrationResult(False, "health_check", error_code="timeout", message="OctoPrint request timed out")
        except Exception as exc:
            return IntegrationResult(False, "health_check", error_code="octoprint_error", message=mask_secret_text(str(exc), [self._api_key()]))

    def printer_status(self) -> Dict[str, Any]:
        printer = self._request("GET", "/api/printer")
        job = self._request("GET", "/api/job")
        temps = printer.get("temperature", {}) if isinstance(printer, dict) else {}
        state = printer.get("state", {}) if isinstance(printer, dict) else {}
        progress = job.get("progress", {}) if isinstance(job, dict) else {}
        file_info = (job.get("job", {}) if isinstance(job, dict) else {}).get("file", {})
        return {
            "state": state.get("text", "unknown"),
            "nozzle_temperature": temps.get("tool0", {}),
            "bed_temperature": temps.get("bed", {}),
            "current_job": file_info.get("name") or "",
            "progress": progress.get("completion"),
            "estimated_time_remaining": progress.get("printTimeLeft"),
        }

    def list_files(self) -> Dict[str, Any]:
        return self._request("GET", "/api/files")

    def execute_action(self, action_id: str, params: Optional[Dict[str, Any]] = None, *, initiated_by_ai: bool = False, confirmed: bool = False) -> IntegrationResult:
        params = params or {}
        try:
            if action_id in ("get_printer_status", "get_print_progress"):
                return IntegrationResult(True, action_id, self.printer_status(), "Printer status loaded")
            if action_id == "list_files":
                return IntegrationResult(True, action_id, self.list_files(), "File list loaded")
            if self.settings.mock_mode:
                return IntegrationResult(True, action_id, {"mock": True, "params": params}, f"Mock OctoPrint action: {action_id}")
            if action_id == "pause_print":
                self._request("POST", "/api/job", json={"command": "pause", "action": "pause"})
            elif action_id == "resume_print":
                self._request("POST", "/api/job", json={"command": "pause", "action": "resume"})
            elif action_id == "cancel_print":
                self._request("POST", "/api/job", json={"command": "cancel"})
            elif action_id == "select_file":
                path = str(params.get("path") or "")
                self._request("POST", f"/api/files/local/{path}", json={"command": "select", "print": False})
            elif action_id == "start_print":
                self._request("POST", "/api/job", json={"command": "start"})
            else:
                return IntegrationResult(False, action_id, error_code="unknown_action", message=f"Unknown action: {action_id}")
            return IntegrationResult(True, action_id, message=f"OctoPrint action completed: {action_id}")
        except requests.Timeout:
            return IntegrationResult(False, action_id, error_code="timeout", message="OctoPrint request timed out")
        except Exception as exc:
            return IntegrationResult(False, action_id, error_code="octoprint_error", message=mask_secret_text(str(exc), [self._api_key()]))

