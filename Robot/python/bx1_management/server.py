#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bx1_core import BootstrapResult, bootstrap_runtime


RELEASE_VERSION = "0.2.0"
RELEASE_TAG = "BX1_OS_ALPHA_v0.2.0"
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
                    "schema": "bx1.management.interface.v1",
                    "state": "READY",
                    "architecture_only": True,
                    "capabilities": self.capabilities.as_dict(),
                },
            },
        }

    def bootstrap_payload(self) -> Dict[str, Any]:
        hostname = socket.gethostname()
        return {
            "schema": "bx1.management.bootstrap.v1",
            "interface": {
                "id": INTERFACE_ID,
                "name": "BX1 OS Management",
                "version": RELEASE_VERSION,
                "tag": RELEASE_TAG,
                "architecture_only": True,
                "capabilities": self.capabilities.as_dict(),
            },
            "robot": {
                "name": str(self.config.get("robot_name", "BX1")),
                "status": "Qualification",
                "mode": "Observer only",
                "hostname": hostname,
                "ip": "Detected by browser",
                "existing_ui_port": 8088,
                "management_port": int(self.config.get("web_port", 8089)),
            },
            "brain": {
                "status": "Not connected",
                "url": "",
            },
            "system": {
                "python": platform.python_version(),
                "os": platform.system() or "Unknown",
                "kernel": platform.release() or "Unknown",
                "architecture": platform.machine() or "Unknown",
                "hostname": hostname,
                "serial": "Pending integration",
                "update_channel": "alpha",
                "cpu": None,
                "ram": None,
                "disk": None,
                "temperature": None,
                "network": "Management interface online",
                "uptime_seconds": max(0, int(time.time() - self.started_at)),
            },
            "services": [
                {
                    "name": "bx1-os-alpha.service",
                    "description": "BX1 OS Alpha management service",
                    "state": "running",
                    "managed": True,
                },
                {
                    "name": "bx1-web.service",
                    "description": "Existing Robot Body interface (protected)",
                    "state": "external",
                    "managed": False,
                },
            ],
            "deployment": {
                "current_version": RELEASE_VERSION,
                "commit": "Provided by release manifest",
                "branch": "Provided by release manifest",
                "tag": RELEASE_TAG,
                "build_date": "Provided by release manifest",
                "previous_versions": [],
                "rollback_points": [],
                "qualification_history": [],
                "deployment_history": [],
            },
        }


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
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="bx1-management-http",
            daemon=True,
        )
        self.thread.start()

    def serve_forever(self) -> None:
        self.httpd = self._build_httpd()
        self.port = int(self.httpd.server_address[1])
        self.httpd.serve_forever()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=3)
        self.httpd = None
        self.thread = None

    def _build_httpd(self) -> ReusableThreadingHTTPServer:
        application = self.application
        static_root = self.static_root

        class Handler(BaseHTTPRequestHandler):
            server_version = "BX1OSManagement/0.2"

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
                path = urlparse(self.path).path
                if path == "/api/status":
                    self._json(HTTPStatus.OK, application.status())
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
                        "detail": "Management actions are not implemented in v0.2.0",
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
