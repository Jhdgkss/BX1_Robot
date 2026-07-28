#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import parse_qs, urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bx1_core import BX1Core, BootstrapResult, bootstrap_runtime


RELEASE_VERSION = "0.3.0"
RELEASE_TAG = "BX1_OS_ALPHA_v0.3.0"
INTERFACE_ID = "bx1-os-management"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_CONFIG = Path(
    os.environ.get("BX1_BODY_CONFIG", "/home/arduino/BX1_OS/python/config.json")
)
SPA_ROUTES = {
    "/",
    "/about",
    "/brain",
    "/configuration",
    "/dashboard",
    "/deployment",
    "/diagnostics",
    "/hardware",
    "/logs",
    "/services",
    "/system",
    "/updates",
}
STATIC_FILES = {
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


@dataclass(frozen=True)
class InterfaceCapabilities:
    service_control: bool = False
    host_power_control: bool = False
    configuration_write: bool = False
    log_streaming: bool = False
    update_installation: bool = False
    deployment_rollback: bool = False

    def as_dict(self) -> Dict[str, bool]:
        return {
            "service_control": self.service_control,
            "host_power_control": self.host_power_control,
            "configuration_write": self.configuration_write,
            "log_streaming": self.log_streaming,
            "update_installation": self.update_installation,
            "deployment_rollback": self.deployment_rollback,
        }


class ManagementApplication:
    """Read-only application model for the management UI framework."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        bootstrap: Optional[BootstrapResult] = None,
        started_at: Optional[float] = None,
    ) -> None:
        self.config = dict(config)
        if not self.config.get("qualification_mode") or not self.config.get(
            "observer_only"
        ):
            raise ValueError(
                "BX1 OS Management Interface requires qualification observer mode"
            )
        self.started_at = time.time() if started_at is None else float(started_at)
        self.bootstrap = bootstrap or bootstrap_runtime(self.config)
        self.capabilities = InterfaceCapabilities()
        self.core = BX1Core(
            self.config,
            install_root=Path(
                self.config.get("install_root", "/home/arduino/BX1_OS")
            ),
            service_provider=self._service_projection,
        )
        self.core.state.set_many(
            {
                "management.id": INTERFACE_ID,
                "management.name": "BX1 OS Management",
                "management.read_only": True,
                "management.capabilities": self.capabilities.as_dict(),
                "management.port": int(self.config.get("web_port", 8089)),
                "management.existing_ui_port": 8088,
                "robot.name": str(self.config.get("robot_name", "BX1")),
            },
            source="management.registration",
        )

    @classmethod
    def from_config_file(cls, config_path: Path) -> "ManagementApplication":
        value = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("management configuration must be a JSON object")
        return cls(value)

    def status(self) -> Dict[str, Any]:
        bx1 = self.bootstrap.bx1
        bx1.tick()
        bx1.health.check()
        self.core.update()
        isolation = dict(self.config.get("observer_isolation", {}))
        return {
            "ok": True,
            "service": INTERFACE_ID,
            "state": {
                "observer_only": True,
                "hardware_ownership": False,
                "actuator_access": False,
                "bridge_mode": "observer_only",
            },
            "bx1_os": {
                "milestone": "BX1 OS Alpha",
                "release_version": RELEASE_VERSION,
                "release_tag": RELEASE_TAG,
                "qualification_mode": True,
                "observer_only": True,
                "observer_isolation": isolation,
                "startup_validated": bool(self.bootstrap.report.get("success")),
                "startup": self.bootstrap.report,
                "status": bx1.status(),
                "service_registry": bx1.services.status(),
                "events": bx1.events.status(),
                "communication": bx1.communication.status(),
                "scheduler": bx1.scheduler.status(),
                "diagnostics": bx1.diagnostics.status(),
                "health": bx1.health.status(),
                "management_interface": {
                    "id": INTERFACE_ID,
                    "schema": "bx1.management.interface.v2",
                    "state": "READY",
                    "architecture_only": True,
                    "core_telemetry": True,
                    "capabilities": self.capabilities.as_dict(),
                },
            },
        }

    def bootstrap_payload(self) -> Dict[str, Any]:
        """Compatibility projection built only from the Core state snapshot."""
        state = self.core.state_snapshot()["state"]
        deployment = state.get("deployment", {})
        system = state.get("system", {})
        network = state.get("network", {})
        robot = state.get("robot", {})
        brain = state.get("brain", {})
        management = state.get("management", {})
        return {
            "schema": "bx1.management.bootstrap.v2",
            "interface": {
                "id": INTERFACE_ID,
                "name": "BX1 OS Management",
                "version": deployment.get("version", RELEASE_VERSION),
                "tag": deployment.get("tag", RELEASE_TAG),
                "architecture_only": True,
                "capabilities": management.get(
                    "capabilities", self.capabilities.as_dict()
                ),
            },
            "robot": {
                "name": robot.get("name", "BX1"),
                "status": robot.get("state", "unknown"),
                "mode": robot.get("mode", "observer_only"),
                "hostname": system.get("hostname", "Unknown"),
                "ip": network.get("ip"),
                "existing_ui_port": management.get("existing_ui_port", 8088),
                "management_port": management.get("port", 8089),
            },
            "brain": {
                "status": "Connected" if brain.get("connected") else "Not connected",
                "url": "",
            },
            "system": {
                "python": system.get("python"),
                "os": system.get("os"),
                "kernel": system.get("kernel"),
                "architecture": system.get("architecture"),
                "hostname": system.get("hostname"),
                "serial": system.get("serial"),
                "update_channel": "alpha",
                "cpu": system.get("cpu"),
                "ram": system.get("memory"),
                "disk": system.get("disk"),
                "temperature": system.get("temperature"),
                "network": network.get("state"),
                "uptime_seconds": system.get("uptime", 0),
            },
            "services": state.get("services", {}).get("items", []),
            "deployment": {
                "current_version": deployment.get("version"),
                "commit": deployment.get("commit"),
                "branch": deployment.get("branch"),
                "tag": deployment.get("tag"),
                "build_date": deployment.get("build_date"),
                "previous_versions": [],
                "rollback_points": [],
                "qualification_history": [],
                "deployment_history": [],
            },
        }

    def core_state(self, since_revision: Optional[int] = None) -> Dict[str, Any]:
        if since_revision is None:
            return self.core.state_snapshot()
        return self.core.telemetry.updates(since_revision)

    def core_health(self) -> Dict[str, Any]:
        return self.core.health_snapshot()

    def core_plugins(self) -> Dict[str, Any]:
        return self.core.plugin_snapshot()

    def core_services(self) -> Dict[str, Any]:
        return self.core.service_snapshot()

    def core_system(self) -> Dict[str, Any]:
        return self.core.system_snapshot()

    def _service_projection(self) -> list[Dict[str, Any]]:
        bx1 = self.bootstrap.bx1
        services = [
            {
                "name": "bx1-os-alpha.service",
                "description": "BX1 OS Alpha management and Core service",
                "state": "running",
                "managed": True,
            },
            {
                "name": "bx1-web.service",
                "description": "Existing Robot Body interface (protected)",
                "state": "external",
                "managed": False,
            },
        ]
        for name in bx1.services.names():
            registration = bx1.services.registration(name)
            services.append(
                {
                    "name": "core/%s" % name,
                    "description": type(registration.service).__name__,
                    "state": registration.state.value.lower(),
                    "managed": True,
                }
            )
        return services


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ManagementServer:
    def __init__(
        self,
        application: ManagementApplication,
        *,
        host: str = "0.0.0.0",
        port: int = 8089,
        static_root: Path = STATIC_ROOT,
    ) -> None:
        if int(port) == 8088:
            raise ValueError("port 8088 is reserved for the existing Robot UI")
        self.application = application
        self.host = str(host)
        self.port = int(port)
        self.static_root = static_root.resolve(strict=True)
        self.httpd: Optional[ReusableThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.httpd = self._build_httpd()
        self.port = int(self.httpd.server_address[1])
        self.application.core.start()
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="bx1-management-http",
            daemon=True,
        )
        self.thread.start()

    def serve_forever(self) -> None:
        self.httpd = self._build_httpd()
        self.port = int(self.httpd.server_address[1])
        self.application.core.start()
        try:
            self.httpd.serve_forever()
        finally:
            self.application.core.stop()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=3)
        self.application.core.stop()
        self.httpd = None
        self.thread = None

    def _build_httpd(self) -> ReusableThreadingHTTPServer:
        application = self.application
        static_root = self.static_root

        class Handler(BaseHTTPRequestHandler):
            server_version = "BX1OSManagement/0.3"

            def log_message(self, fmt: str, *args: Any) -> None:
                if os.environ.get("BX1_MANAGEMENT_HTTP_LOG") == "1":
                    super().log_message(fmt, *args)

            def _send(
                self,
                status: int,
                body: bytes,
                content_type: str,
                *,
                cache: str = "no-store",
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "SAMEORIGIN")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, value: Mapping[str, Any]) -> None:
                self._send(
                    status,
                    (json.dumps(dict(value), sort_keys=True) + "\n").encode("utf-8"),
                    "application/json; charset=utf-8",
                )

            def do_GET(self) -> None:  # noqa: N802
                request = urlparse(self.path)
                path = request.path
                if path == "/api/status":
                    self._json(HTTPStatus.OK, application.status())
                    return
                if path == "/api/core/state":
                    query = parse_qs(request.query)
                    raw_since = query.get("since", [None])[0]
                    try:
                        since = None if raw_since is None else int(raw_since)
                    except ValueError:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"ok": False, "error": "invalid_revision"},
                        )
                        return
                    self._json(HTTPStatus.OK, application.core_state(since))
                    return
                if path == "/api/core/health":
                    self._json(HTTPStatus.OK, application.core_health())
                    return
                if path == "/api/core/plugins":
                    self._json(HTTPStatus.OK, application.core_plugins())
                    return
                if path == "/api/core/services":
                    self._json(HTTPStatus.OK, application.core_services())
                    return
                if path == "/api/core/system":
                    self._json(HTTPStatus.OK, application.core_system())
                    return
                if path == "/api/management/bootstrap":
                    self._json(HTTPStatus.OK, application.bootstrap_payload())
                    return
                if path in STATIC_FILES:
                    filename, content_type = STATIC_FILES[path]
                    body = (static_root / filename).read_bytes()
                    self._send(
                        HTTPStatus.OK,
                        body,
                        content_type,
                        cache="public, max-age=300",
                    )
                    return
                if path in SPA_ROUTES:
                    self._send(
                        HTTPStatus.OK,
                        (static_root / "index.html").read_bytes(),
                        "text/html; charset=utf-8",
                    )
                    return
                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"ok": False, "error": "route_not_found"},
                )

            def do_POST(self) -> None:  # noqa: N802
                length = min(
                    max(0, int(self.headers.get("Content-Length", "0") or "0")),
                    1024 * 1024,
                )
                if length:
                    self.rfile.read(length)
                self._json(
                    HTTPStatus.NOT_IMPLEMENTED,
                    {
                        "ok": False,
                        "error": "architecture_only",
                        "detail": "Management actions are not implemented in v0.3.0",
                    },
                )

        return ReusableThreadingHTTPServer((self.host, self.port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve BX1 OS Management Interface")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--host", default=os.environ.get("BX1_WEB_HOST", "0.0.0.0")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("BX1_WEB_PORT", "8089"))
    )
    args = parser.parse_args()
    if args.port == 8088:
        parser.error("port 8088 is reserved for the existing Robot UI")
    application = ManagementApplication.from_config_file(args.config)
    server = ManagementServer(application, host=args.host, port=args.port)
    print(
        "[BX1 OS] Management Interface v%s listening on %s:%s"
        % (RELEASE_VERSION, args.host, args.port),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        if server.httpd is not None:
            server.httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
