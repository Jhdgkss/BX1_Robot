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
from urllib import error, request

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bx1_core import BX1Core, BootstrapResult, bootstrap_runtime
from bx1_core.hardware import (
    CameraFrame,
    CameraProxyError,
    RobotBodyCameraClient,
)
from bx1_management.voice_vertical import VoiceTimeline, VoiceVerticalSlice
from bx1_runtime import ModuleManager


RELEASE_VERSION = "0.7.7-body-speaker-echo-suppression"
RELEASE_TAG = "BX1_OS_v0.7.7_body_speaker_echo_suppression"
INTERFACE_ID = "bx1-os-management"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_CONFIG = Path(
    os.environ.get("BX1_BODY_CONFIG", "/home/arduino/BX1_OS/python/config.json")
)
SPA_ROUTES = {
    "/",
    "/about",
    "/audio",
    "/brain",
    "/camera",
    "/configuration",
    "/dashboard",
    "/deployment",
    "/diagnostics",
    "/hardware",
    "/logs",
    "/modules",
    "/services",
    "/system",
    "/updates",
    "/voice",
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


class SharedLiveVoiceConsole:
    """Bounded RAM-only shared transcript for every 8089 browser client."""

    def __init__(self, limit: int = 200) -> None:
        self._items: list[Dict[str, Any]] = []
        self._limit = max(10, min(200, int(limit)))
        self._lock = threading.RLock()
        self._next_id = 1
        self._last_heard = ""
        self._last_state = ""
        self._last_failure = ""
        self._last_reply = ""
        self._receiver: Dict[str, Any] = {"last_received_at": None, "last_success_at": None, "last_error": "not_received"}

    def _append(self, kind: str, source: str, text: str) -> None:
        text = str(text or "").strip()[:400]
        if not text:
            return
        with self._lock:
            self._items.append({"id": self._next_id, "timestamp": time.time(), "kind": kind, "source": source[:40], "text": text})
            self._next_id += 1
            self._items = self._items[-self._limit:]

    def observe_body(self, payload: Mapping[str, Any]) -> None:
        received = time.time()
        audio = payload.get("audio") if isinstance(payload.get("audio"), Mapping) else {}
        recognition = payload.get("recognition") if isinstance(payload.get("recognition"), Mapping) else {}
        with self._lock:
            self._receiver.update({"last_received_at": received, "body_sample_at": audio.get("timestamp"), "body_sample_age_seconds": audio.get("age_seconds"), "body_available": bool(audio.get("available")), "last_error": ""})
            if payload.get("ok"):
                self._receiver["last_success_at"] = received
            else:
                self._receiver["last_error"] = str(payload.get("error") or "body_metadata_failed")[:160]
        # Only Body-confirmed accepted requests enter the shared user transcript.
        # Discarded/noisy audio, including robot-speaker echo, remains metadata.
        heard = str(recognition.get("last_accepted_request") or "").strip()
        reply = str(recognition.get("latest_reply") or "").strip()
        state = str(audio.get("state_detail") or audio.get("state") or "unavailable").strip()
        failure = str(recognition.get("rejection_reason") or audio.get("last_failure_reason") or "").strip()
        if heard and heard != self._last_heard:
            self._last_heard = heard; self._append("stt", "Recognised speech", heard)
        if reply and reply != getattr(self, "_last_reply", ""):
            self._last_reply = reply; self._append("reply", "LEO / Brain", reply)
        if state and state != self._last_state:
            self._last_state = state; self._append("system", "Voice state", state)
        if failure and failure != self._last_failure:
            self._last_failure = failure; self._append("failure", "Voice failure", failure)

    def add(self, kind: str, source: str, text: str) -> None:
        self._append(kind, source, text)

    def clear(self) -> Dict[str, Any]:
        with self._lock:
            # Keep the observed fingerprints so clearing does not immediately
            # reinsert the same Body snapshot on the next browser poll.
            self._items.clear()
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"ok": True, "schema": "bx1.live_voice_console.v1", "items": list(self._items), "limit": self._limit, "receiver": dict(self._receiver), "storage": "temporary_memory_only_cleared_on_restart"}


class ManagementApplication:
    """Read-only application model for the management UI framework."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        bootstrap: Optional[BootstrapResult] = None,
        core: Optional[BX1Core] = None,
        camera_client: Optional[RobotBodyCameraClient] = None,
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
        camera_config = dict(self.config.get("camera_proxy", {}))
        self.camera_client = camera_client or RobotBodyCameraClient(
            timeout=float(camera_config.get("timeout_seconds", 1.0)),
            max_frame_bytes=int(
                camera_config.get("maximum_frame_bytes", 2 * 1024 * 1024)
            ),
            default_fps=float(camera_config.get("default_fps", 8.0)),
            max_fps=float(camera_config.get("maximum_fps", 15.0)),
        )
        self.core = core or BX1Core(
            self.config,
            install_root=Path(
                self.config.get("install_root", "/home/arduino/BX1_OS")
            ),
            service_provider=self._service_projection,
        )
        voice_config = dict(self.config.get("voice_vertical_slice", {}))
        self.voice_timeline = VoiceTimeline(limit=int(voice_config.get("event_limit", 250)))
        self.voice = VoiceVerticalSlice(
            self.voice_timeline,
            body_url=str(self.config.get("hardware_observer", {}).get("robot_body_url", "http://127.0.0.1:8088")),
            probe_timeout=float(voice_config.get("body_probe_timeout_seconds", 5.0)),
            request_timeout=float(voice_config.get("body_request_timeout_seconds", 240.0)),
        )
        self.live_voice_console = SharedLiveVoiceConsole(limit=200)
        modules_root = Path(self.config.get("modules_root", Path(__file__).resolve().parents[2] / "modules"))
        persistent_root = Path(self.config.get("persistent_modules_root", "/home/arduino/BX1_modules"))
        self.modules = ModuleManager(modules_root, persistent_root=persistent_root, event_limit=int(self.config.get("runtime", {}).get("event_queue_limit", 128)), led_request=self._body_led_request)
        self.modules.load_all()
        self.core.state.set_many(
            {
                "management.id": INTERFACE_ID,
                "management.name": "BX1 OS Management",
                "management.runtime_preview": True,
                "management.read_only": True,
                "management.capabilities": self.capabilities.as_dict(),
                "management.port": int(self.config.get("web_port", 8089)),
                "management.existing_ui_port": 8088,
                "robot.name": str(self.config.get("robot_name", "LEO")),
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
        body = self.core.robot_body_snapshot().get("robot_body", {})
        body_value = body.get("value", body) if isinstance(body, Mapping) else {}
        endpoint = self.voice.update_brain_endpoint(body_value if isinstance(body_value, Mapping) else {})
        isolation = dict(self.config.get("observer_isolation", {}))
        installed_version = self.core.state.get("deployment.version") or self.config.get("bx1_os_release_version") or RELEASE_VERSION
        installed_tag = self.core.state.get("deployment.tag") or self.config.get("bx1_os_release_tag") or RELEASE_TAG
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
                "release_version": installed_version,
                "release_tag": installed_tag,
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
                "voice_vertical_slice": {
                    "schema": "bx1.voice.vertical_slice.v1",
                    "brain_endpoint": endpoint,
                    "timeline": self.voice_timeline.snapshot(),
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
                "name": robot.get("name", "LEO"),
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

    def core_hardware(self) -> Dict[str, Any]:
        return self.core.hardware_snapshot()

    def core_hardware_inventory(self) -> Dict[str, Any]:
        return self.core.hardware_inventory_snapshot()

    def core_audio(self) -> Dict[str, Any]:
        return self.core.audio_snapshot()

    def core_audio_devices(self) -> Dict[str, Any]:
        return self.core.audio_devices_snapshot()

    def core_robot_body(self) -> Dict[str, Any]:
        return self.core.robot_body_snapshot()

    def core_robot_body_health(self) -> Dict[str, Any]:
        return self.core.robot_body_health_snapshot()

    def runtime_modules(self) -> Dict[str, Any]:
        return self.modules.snapshot()

    def runtime_widgets(self) -> Dict[str, Any]:
        return self.modules.widgets_snapshot()

    def runtime_install(self, archive: bytes) -> Dict[str, Any]:
        if not archive or len(archive) > 2 * 1024 * 1024:
            raise ValueError("invalid_module_archive")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as stream:
            stream.write(archive)
            path = Path(stream.name)
        try:
            return self.modules.install_zip(path)
        finally:
            path.unlink(missing_ok=True)

    def _body_led_request(self, value: Mapping[str, Any]) -> Dict[str, Any]:
        """High-level, loopback-only Body request; Body remains the hardware authority."""
        payload = {key: value.get(key) for key in ("module_id", "target", "colour", "effect")}
        try:
            req = request.Request("http://127.0.0.1:8088/api/bx1-os/led-status", data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=1.5) as response:
                result = json.loads(response.read(4096).decode("utf-8"))
            return dict(result) if isinstance(result, Mapping) and bool(result.get("ok")) else {"ok": False, "state": "unavailable", "reason": "Body LED capability unavailable"}
        except (error.HTTPError, error.URLError, TimeoutError, ValueError, OSError):
            return {"ok": False, "state": "unavailable", "reason": "Body LED capability unavailable"}

    def body_audio_bridge(self) -> Dict[str, Any]:
        """Fetch Body-owned, metadata-only audio diagnostics without opening ALSA."""
        try:
            with request.urlopen("http://127.0.0.1:8088/api/bx1-os/audio-bridge", timeout=1.2) as response:
                payload = json.loads(response.read(16384).decode("utf-8"))
            result = dict(payload) if isinstance(payload, Mapping) else {"ok": False, "error": "invalid_body_audio_metadata"}
            self.live_voice_console.observe_body(result)
            result["receiver"] = self.live_voice_console.snapshot()["receiver"]
            return result
        except (error.HTTPError, error.URLError, TimeoutError, ValueError, OSError) as exc:
            result = {"ok": False, "error": "Body audio metadata unavailable", "detail": str(exc), "boundary": "Robot Body owns microphone capture; BX1 OS did not open a device."}
            self.live_voice_console.observe_body(result)
            result["receiver"] = self.live_voice_console.snapshot()["receiver"]
            return result

    def live_voice_console_snapshot(self) -> Dict[str, Any]:
        return self.live_voice_console.snapshot()

    def update_body_audio_bridge(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        payload = {"settings": dict(values.get("settings", values))}
        try:
            req = request.Request("http://127.0.0.1:8088/api/bx1-os/audio-bridge/settings", data=json.dumps(payload).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=3.0) as response:
                value = json.loads(response.read(16384).decode("utf-8"))
            return dict(value) if isinstance(value, Mapping) else {"ok": False, "error": "invalid_body_audio_response"}
        except error.HTTPError as exc:
            return {"ok": False, "error": f"Body rejected audio settings ({exc.code})"}
        except (error.URLError, TimeoutError, ValueError, OSError) as exc:
            return {"ok": False, "error": "Body audio settings unavailable", "detail": str(exc)}

    def body_voice_settings(self) -> Dict[str, Any]:
        try:
            with request.urlopen("http://127.0.0.1:8088/api/bx1-os/voice-settings/v1", timeout=2.0) as response:
                payload = json.loads(response.read(16384).decode("utf-8"))
            return dict(payload) if isinstance(payload, Mapping) else {"ok": False, "error": "invalid_body_voice_settings"}
        except (error.HTTPError, error.URLError, TimeoutError, ValueError, OSError) as exc:
            return {"ok": False, "error": "Body voice settings unavailable", "detail": str(exc)}

    def update_body_voice_settings(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        payload = {"settings": dict(values.get("settings", values))}
        try:
            req = request.Request("http://127.0.0.1:8088/api/bx1-os/voice-settings/v1", data=json.dumps(payload).encode("utf-8"), method="PUT", headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=3.0) as response:
                value = json.loads(response.read(16384).decode("utf-8"))
            return dict(value) if isinstance(value, Mapping) else {"ok": False, "error": "invalid_body_voice_settings_response"}
        except error.HTTPError as exc:
            return {"ok": False, "error": f"Body rejected voice settings ({exc.code})"}
        except (error.URLError, TimeoutError, ValueError, OSError) as exc:
            return {"ok": False, "error": "Body voice settings unavailable", "detail": str(exc)}

    def voice_status(self) -> Dict[str, Any]:
        body = self.core.robot_body_snapshot().get("robot_body", {})
        body_value = body.get("value", body) if isinstance(body, Mapping) else {}
        endpoint = self.voice.update_brain_endpoint(body_value if isinstance(body_value, Mapping) else {})
        timeline = self.voice_timeline.snapshot()
        sessions = {
            str(item.get("session_id")): self.voice.session_state(str(item.get("session_id")))
            for item in timeline.get("events", [])[-30:]
            if item.get("session_id")
        }
        return {
            "ok": True,
            "brain_endpoint": endpoint,
            "brain": self.voice.connection_snapshot(),
            "sessions": sessions,
            **timeline,
        }

    def core_camera(self) -> Dict[str, Any]:
        payload = self.core.camera_snapshot()
        proxy = self.camera_client.status()
        cpu = self._cpu_percent()
        proxy["performance_state"] = (
            "degraded_cpu" if cpu is not None and cpu >= 85.0 else "normal"
        )
        proxy["effective_fps_limit"] = (
            min(5.0, float(proxy.get("maximum_fps", 15.0)))
            if cpu is not None and cpu >= 85.0
            else float(proxy.get("maximum_fps", 15.0))
        )
        proxy["cpu_percent"] = cpu
        payload["proxy"] = proxy
        return payload

    def camera_frame(self) -> CameraFrame:
        return self.camera_client.snapshot()

    def relay_camera_stream(
        self,
        *,
        on_open: Any,
        writer: Any,
        fps: Optional[float],
    ) -> Dict[str, Any]:
        cpu = self._cpu_percent()
        if cpu is not None and cpu >= 85.0:
            fps = min(5.0, 5.0 if fps is None else float(fps))
        return self.camera_client.relay_stream(
            on_open=on_open,
            writer=writer,
            fps=fps,
        )

    def _cpu_percent(self) -> Optional[float]:
        value = self.core.state.get("system.cpu")
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

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
        self.application.modules.stop()
        self.httpd = None
        self.thread = None

    def _build_httpd(self) -> ReusableThreadingHTTPServer:
        application = self.application
        static_root = self.static_root

        class Handler(BaseHTTPRequestHandler):
            server_version = "BX1OSManagement/0.5"

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
                extra_headers: Optional[Mapping[str, str]] = None,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "SAMEORIGIN")
                self.send_header("Referrer-Policy", "no-referrer")
                for name, value in (extra_headers or {}).items():
                    self.send_header(str(name), str(value))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, value: Mapping[str, Any]) -> None:
                self._send(
                    status,
                    (json.dumps(dict(value), sort_keys=True) + "\n").encode("utf-8"),
                    "application/json; charset=utf-8",
                )

            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length < 0 or length > 65536:
                    raise ValueError("request_too_large")
                raw = self.rfile.read(length) if length else b"{}"
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, Mapping):
                    raise ValueError("request_must_be_object")
                return dict(value)

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
                if path == "/api/core/hardware":
                    self._json(HTTPStatus.OK, application.core_hardware())
                    return
                if path == "/api/core/hardware/inventory":
                    self._json(
                        HTTPStatus.OK,
                        application.core_hardware_inventory(),
                    )
                    return
                if path == "/api/core/audio":
                    self._json(HTTPStatus.OK, application.core_audio())
                    return
                if path == "/api/core/audio/devices":
                    self._json(
                        HTTPStatus.OK, application.core_audio_devices()
                    )
                    return
                if path == "/api/audio/bridge":
                    self._json(HTTPStatus.OK, application.body_audio_bridge())
                    return
                if path == "/api/audio/voice-settings/v1":
                    self._json(HTTPStatus.OK, application.body_voice_settings())
                    return
                if path == "/api/voice/console":
                    self._json(HTTPStatus.OK, application.live_voice_console_snapshot())
                    return
                if path == "/api/core/robot-body":
                    self._json(
                        HTTPStatus.OK, application.core_robot_body()
                    )
                    return
                if path == "/api/core/robot-body/health":
                    self._json(
                        HTTPStatus.OK,
                        application.core_robot_body_health(),
                    )
                    return
                if path == "/api/runtime/modules":
                    self._json(HTTPStatus.OK, application.runtime_modules())
                    return
                if path == "/api/runtime/widgets":
                    self._json(HTTPStatus.OK, application.runtime_widgets())
                    return
                if path == "/api/voice/status":
                    self._json(HTTPStatus.OK, application.voice_status())
                    return
                if path == "/api/voice/timeline":
                    self._json(HTTPStatus.OK, application.voice_timeline.snapshot())
                    return
                if path == "/api/voice/diagnostics":
                    self._json(HTTPStatus.OK, application.voice_status())
                    return
                if path == "/api/core/camera":
                    self._json(HTTPStatus.OK, application.core_camera())
                    return
                if path == "/api/core/camera/snapshot":
                    try:
                        frame = application.camera_frame()
                    except CameraProxyError as exc:
                        self._json(
                            exc.status,
                            {
                                "ok": False,
                                "error": exc.error,
                                "source": "Existing Robot Body",
                            },
                        )
                        return
                    headers = {
                        "X-BX1-Frame-Sequence": str(frame.sequence),
                        "X-BX1-Frame-Timestamp": frame.timestamp,
                        "X-BX1-Frame-Age-Ms": str(
                            "" if frame.age_ms is None else frame.age_ms
                        ),
                        "X-BX1-Frame-Resolution": frame.resolution,
                        "X-BX1-Camera-Owner": "bx1-web.service",
                    }
                    self._send(
                        HTTPStatus.OK,
                        frame.jpeg,
                        "image/jpeg",
                        extra_headers=headers,
                    )
                    return
                if path == "/api/core/camera/stream":
                    query = parse_qs(request.query)
                    raw_fps = query.get("fps", [None])[0]
                    try:
                        fps = None if raw_fps is None else float(raw_fps)
                    except ValueError:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"ok": False, "error": "invalid_fps"},
                        )
                        return
                    opened = False

                    def open_stream(content_type: str) -> None:
                        nonlocal opened
                        self.send_response(HTTPStatus.OK)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Pragma", "no-cache")
                        self.send_header("Connection", "close")
                        self.send_header(
                            "X-BX1-Camera-Owner", "bx1-web.service"
                        )
                        self.send_header(
                            "X-BX1-Camera-Access", "read-only-proxy"
                        )
                        self.end_headers()
                        opened = True

                    def write_stream(chunk: bytes) -> None:
                        self.wfile.write(chunk)
                        self.wfile.flush()

                    try:
                        application.relay_camera_stream(
                            on_open=open_stream,
                            writer=write_stream,
                            fps=fps,
                        )
                    except CameraProxyError as exc:
                        if not opened:
                            self._json(
                                exc.status,
                                {
                                    "ok": False,
                                    "error": exc.error,
                                    "source": "Existing Robot Body",
                                },
                            )
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

            def _reject_write(self, *, body_consumed: bool = False) -> None:
                length = min(
                    max(0, int(self.headers.get("Content-Length", "0") or "0")),
                    1024 * 1024,
                )
                if length and not body_consumed:
                    self.rfile.read(length)
                self._json(
                    HTTPStatus.NOT_IMPLEMENTED,
                    {
                        "ok": False,
                        "error": "architecture_only",
                        "detail": "BX1 OS v0.6.1-development allows only the scoped voice diagnostic routes",
                    },
                )

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                try:
                    if path == "/api/runtime/modules/install":
                        length = int(self.headers.get("Content-Length", "0") or "0")
                        if length < 1 or length > 2 * 1024 * 1024:
                            raise ValueError("invalid_module_archive")
                        self._json(HTTPStatus.OK, application.runtime_install(self.rfile.read(length)))
                        return
                    body = self._read_json()
                    if path == "/api/runtime/modules/reload":
                        self._json(HTTPStatus.OK, application.modules.reload())
                        return
                    if path == "/api/runtime/modules/clear-faults":
                        self._json(HTTPStatus.OK, application.modules.clear_faults())
                        return
                    if path.startswith("/api/runtime/modules/"):
                        parts = path.split("/")
                        if len(parts) == 6 and parts[5] in {"enable", "disable", "remove"}:
                            operation, module_id = parts[5], parts[4]
                            result = application.modules.remove(module_id) if operation == "remove" else application.modules.set_enabled(module_id, operation == "enable")
                            self._json(HTTPStatus.OK, result)
                            return
                        if len(parts) == 7 and parts[5] == "actions":
                            self._json(HTTPStatus.OK, application.modules.invoke_action(parts[4], parts[6], body.get("fields", {})))
                            return
                    if path == "/api/voice/events":
                        if self.client_address[0] not in {"127.0.0.1", "::1"}:
                            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "voice_events_loopback_only"})
                            return
                        self._json(HTTPStatus.ACCEPTED, {"ok": True, "event": application.voice_timeline.record(body, source="robot_body")})
                        return
                    if path == "/api/audio/bridge/settings":
                        result = application.update_body_audio_bridge(body)
                        self._json(HTTPStatus.OK if result.get("ok") else HTTPStatus.SERVICE_UNAVAILABLE, result)
                        return
                    if path == "/api/voice/typed-test":
                        typed = str(body.get("text") or "")
                        application.live_voice_console.add("manual", "John", typed)
                        result = application.voice.typed_test(typed)
                        if result.get("ok"):
                            application.live_voice_console.add("reply", "LEO / Brain", str(result.get("reply") or "Reply is playing through the Body speaker."))
                        else:
                            application.live_voice_console.add("failure", "Voice failure", str(result.get("error") or "typed route failed"))
                        self._json(HTTPStatus.OK if result.get("ok") else HTTPStatus.SERVICE_UNAVAILABLE, result)
                        return
                    if path == "/api/voice/console/clear":
                        self._json(HTTPStatus.OK, application.live_voice_console.clear())
                        return
                    if path == "/api/voice/brain-test":
                        result = application.voice.brain_probe()
                        # Connectivity outcomes are diagnostic states, not a UI command
                        # failure.  Keep the response readable so the page can show
                        # Connected, Degraded or Not connected without guessing.
                        self._json(HTTPStatus.OK, result)
                        return
                    if path == "/api/voice/faults/clear":
                        self._json(HTTPStatus.OK, application.voice_timeline.clear_observer_faults())
                        return
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                self._reject_write(body_consumed=True)

            def do_PUT(self) -> None:  # noqa: N802
                if urlparse(self.path).path == "/api/audio/voice-settings/v1":
                    try:
                        result = application.update_body_voice_settings(self._read_json())
                        self._json(HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST, result)
                    except (ValueError, json.JSONDecodeError) as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                self._reject_write()

            def do_PATCH(self) -> None:  # noqa: N802
                self._reject_write()

            def do_DELETE(self) -> None:  # noqa: N802
                self._reject_write()

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
