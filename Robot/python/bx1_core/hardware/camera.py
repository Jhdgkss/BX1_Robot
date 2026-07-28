from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib.parse import urlparse

from .device import DeviceHealth, DeviceRecord, HardwareEnvironment


@dataclass(frozen=True)
class CameraFrame:
    jpeg: bytes
    sequence: int
    timestamp: str
    age_ms: Optional[float]
    width: Optional[int]
    height: Optional[int]
    received_at: float

    @property
    def resolution(self) -> str:
        return (
            "%sx%s" % (self.width, self.height)
            if self.width and self.height
            else "unknown"
        )


class CameraProxyError(RuntimeError):
    def __init__(self, error: str, *, status: int = 502) -> None:
        super().__init__(error)
        self.error = str(error)
        self.status = int(status)


class RobotBodyCameraClient:
    """Fixed-loopback, GET-only proxy for Robot Body-owned cached frames."""

    SNAPSHOT_PATH = "/api/camera/snapshot"
    STREAM_PATH = "/api/camera/stream"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8088",
        *,
        timeout: float = 1.0,
        opener: Optional[Callable[..., Any]] = None,
        clock: Callable[[], float] = time.time,
        max_frame_bytes: int = 2 * 1024 * 1024,
        default_fps: float = 8.0,
        max_fps: float = 15.0,
    ) -> None:
        parsed = urlparse(str(base_url))
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.port != 8088
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "Camera proxy is restricted to loopback Robot Body port 8088"
            )
        self.base_url = str(base_url).rstrip("/")
        self.timeout = max(0.05, min(float(timeout), 2.0))
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self.max_frame_bytes = max(
            64 * 1024, min(int(max_frame_bytes), 8 * 1024 * 1024)
        )
        self.max_fps = max(1.0, min(float(max_fps), 15.0))
        self.default_fps = max(
            1.0, min(float(default_fps), self.max_fps)
        )
        self._stream_gate = threading.Lock()
        self._status_lock = threading.Lock()
        self._last_frame: Optional[CameraFrame] = None
        self._stream_active = False
        self._stream_started_at = 0.0
        self._stream_bytes = 0
        self._stream_disconnects = 0
        self._last_error = ""

    def snapshot(self) -> CameraFrame:
        request = urllib.request.Request(
            self.base_url + self.SNAPSHOT_PATH,
            method="GET",
            headers={
                "Accept": "image/jpeg",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                content_type = str(
                    response.headers.get("Content-Type", "")
                ).lower()
                raw = response.read(self.max_frame_bytes + 1)
                headers = response.headers
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                raise CameraProxyError(
                    "robot_body_frame_unavailable", status=503
                ) from exc
            raise CameraProxyError(
                "robot_body_snapshot_http_%s" % exc.code
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise CameraProxyError("robot_body_snapshot_timeout") from exc
        except urllib.error.URLError as exc:
            error = (
                "robot_body_snapshot_timeout"
                if isinstance(exc.reason, (TimeoutError, socket.timeout))
                else "robot_body_snapshot_unavailable"
            )
            raise CameraProxyError(error) from exc
        except OSError as exc:
            raise CameraProxyError(
                "robot_body_snapshot_unavailable"
            ) from exc
        if not content_type.startswith("image/jpeg"):
            raise CameraProxyError("robot_body_snapshot_not_jpeg")
        if len(raw) > self.max_frame_bytes:
            raise CameraProxyError("robot_body_snapshot_too_large")
        if not _valid_jpeg(raw):
            raise CameraProxyError("robot_body_snapshot_malformed_jpeg")
        width, height = _jpeg_dimensions(raw)
        frame = CameraFrame(
            jpeg=bytes(raw),
            sequence=_header_int(
                headers.get("X-BX1-Frame-Sequence"), default=0
            ),
            timestamp=str(
                headers.get("X-BX1-Frame-Timestamp", "")
            ),
            age_ms=_header_float(headers.get("X-BX1-Frame-Age-Ms")),
            width=width,
            height=height,
            received_at=self.clock(),
        )
        with self._status_lock:
            self._last_frame = frame
            self._last_error = ""
        return frame

    def relay_stream(
        self,
        *,
        on_open: Callable[[str], None],
        writer: Callable[[bytes], None],
        fps: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self._stream_gate.acquire(blocking=False):
            raise CameraProxyError("camera_proxy_stream_busy", status=503)
        selected_fps = max(
            1.0,
            min(
                self.max_fps,
                self.default_fps if fps is None else float(fps),
            ),
        )
        request = urllib.request.Request(
            "%s%s?fps=%.2f"
            % (self.base_url, self.STREAM_PATH, selected_fps),
            method="GET",
            headers={"Accept": "multipart/x-mixed-replace"},
        )
        started = self.clock()
        with self._status_lock:
            self._stream_active = True
            self._stream_started_at = started
            self._last_error = ""
        relayed = 0
        browser_disconnected = False
        try:
            try:
                response_context = self.opener(
                    request, timeout=self.timeout
                )
            except urllib.error.HTTPError as exc:
                raise CameraProxyError(
                    "robot_body_stream_unavailable",
                    status=503 if exc.code == 503 else 502,
                ) from exc
            except (TimeoutError, socket.timeout) as exc:
                raise CameraProxyError(
                    "robot_body_stream_timeout"
                ) from exc
            except urllib.error.URLError as exc:
                raise CameraProxyError(
                    "robot_body_stream_unavailable"
                ) from exc
            with response_context as response:
                content_type = str(
                    response.headers.get("Content-Type", "")
                )
                if not content_type.lower().startswith(
                    "multipart/x-mixed-replace"
                ) or "boundary=frame" not in content_type.lower():
                    raise CameraProxyError(
                        "robot_body_stream_malformed"
                    )
                on_open(content_type)
                while True:
                    try:
                        chunk = response.read(64 * 1024)
                    except (TimeoutError, socket.timeout) as exc:
                        raise CameraProxyError(
                            "robot_body_stream_timeout"
                        ) from exc
                    if not chunk:
                        break
                    try:
                        writer(bytes(chunk))
                    except (
                        BrokenPipeError,
                        ConnectionResetError,
                        ConnectionAbortedError,
                        OSError,
                    ):
                        browser_disconnected = True
                        break
                    relayed += len(chunk)
            return {
                "ok": True,
                "bytes_relayed": relayed,
                "browser_disconnected": browser_disconnected,
            }
        except CameraProxyError as exc:
            with self._status_lock:
                self._last_error = exc.error
            raise
        finally:
            with self._status_lock:
                self._stream_active = False
                self._stream_bytes += relayed
                if browser_disconnected:
                    self._stream_disconnects += 1
            self._stream_gate.release()

    def status(self) -> Dict[str, Any]:
        with self._status_lock:
            frame = self._last_frame
            return {
                "proxy_available": True,
                "source": "Existing Robot Body",
                "owner": "bx1-web.service",
                "strategy": "single_upstream_mjpeg",
                "streaming": self._stream_active,
                "stream_started_at": self._stream_started_at or None,
                "stream_bytes": self._stream_bytes,
                "browser_disconnects": self._stream_disconnects,
                "last_error": self._last_error,
                "last_snapshot_received_at": (
                    frame.received_at if frame else None
                ),
                "last_snapshot_sequence": (
                    frame.sequence if frame else None
                ),
                "maximum_fps": self.max_fps,
                "default_fps": self.default_fps,
                "maximum_frame_bytes": self.max_frame_bytes,
                "queue_depth": 1,
                "drop_old_frames": True,
                "device_nodes_opened": False,
                "capture_created": False,
                "settings_changed": False,
            }


class CameraAdapter:
    name = "camera"

    def __init__(self, environment: HardwareEnvironment) -> None:
        self.environment = environment

    def discover(self, robot_body: Mapping[str, Any]) -> List[DeviceRecord]:
        timestamp = self.environment.clock()
        dev_nodes, dev_error = self.environment.glob(
            self.environment.dev_root, "video*"
        )
        sys_nodes, sys_error = self.environment.glob(
            self.environment.sys_root / "class" / "video4linux", "video*"
        )
        names = sorted({item.name for item in (*dev_nodes, *sys_nodes)})
        records = []
        body_camera = self._mapping(robot_body.get("camera"))
        configured = str(body_camera.get("device", ""))
        owned_by_body = bool(robot_body.get("connected")) and bool(
            body_camera.get("configured")
            or configured
            or str(body_camera.get("state", "")).lower()
            in {"online", "running", "active", "busy"}
        )
        for name in names:
            node = self.environment.dev_root / name
            node_visible, _ = self.environment.exists(node)
            sys_device = (
                self.environment.sys_root
                / "class"
                / "video4linux"
                / name
            )
            friendly, _ = self.environment.read_text(sys_device / "name")
            driver = ""
            driver_path = sys_device / "device" / "driver"
            driver_exists, _ = self.environment.exists(driver_path)
            if driver_exists:
                try:
                    driver = driver_path.resolve().name
                except OSError:
                    pass
            owners = self.environment.owners(node)
            owned = bool(owners) or owned_by_body
            usb_identity = self._usb_identity(sys_device)
            internal = self._internal_device(
                friendly.strip() or name,
                driver,
            )
            group_id = self._group_id(name, usb_identity, internal)
            records.append(
                DeviceRecord(
                    device_id="camera:%s" % name,
                    name=friendly.strip() or name,
                    category="camera",
                    present=True,
                    available=node_visible and not owned,
                    ownership=(
                        self._ownership(owners)
                        if owners
                        else "bx1-web.service"
                        if owned_by_body
                        else "unclaimed"
                    ),
                    health=DeviceHealth(
                        "owned_elsewhere" if owned else "detected",
                        (
                            "Device is in use; stream was not opened"
                            if owned
                            else "Camera detected in sysfs; device node is hidden"
                            if not node_visible
                            else "Device node detected without opening it"
                        ),
                    ),
                    details={
                        "device_node": str(node),
                        "device_node_visible": node_visible,
                        "driver": driver or "unknown",
                        "usb_identity": usb_identity,
                        "physical_group_id": group_id,
                        "user_visible": not internal,
                        "internal_video_device": internal,
                        "configured": self._configured(
                            configured, node, name
                        ),
                        "supported_formats": [],
                        "format_query": "not_run_while_observer_only",
                        "owners": owners,
                    },
                    last_seen=timestamp,
                    capabilities={
                        "metadata": True,
                        "streaming": False,
                        "control": False,
                    },
                    source="sysfs + Existing Robot Body",
                )
            )
        if not records and configured:
            records.append(
                DeviceRecord(
                    device_id="camera:configured",
                    name=configured,
                    category="camera",
                    present=False,
                    available=False,
                    ownership=(
                        "bx1-web.service"
                        if robot_body.get("connected")
                        else "unknown"
                    ),
                    health=DeviceHealth(
                        "unavailable",
                        "Configured by Existing Robot Body but not detected",
                    ),
                    details={"configured": True, "device_node": configured},
                    last_seen=timestamp if robot_body.get("connected") else None,
                    error=dev_error or sys_error or "device_not_detected",
                    capabilities={"control": False, "streaming": False},
                    source="Existing Robot Body",
                )
            )
        return records

    def summarise(
        self,
        records: List[DeviceRecord],
        robot_body: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        """Group V4L2 nodes while retaining raw records in the inventory."""
        groups: Dict[str, List[DeviceRecord]] = {}
        for record in records:
            if not bool(record.details.get("user_visible", True)):
                continue
            group_id = str(
                record.details.get(
                    "physical_group_id", record.device_id
                )
            )
            groups.setdefault(group_id, []).append(record)
        body_camera = self._mapping(robot_body.get("camera"))
        preview = self._mapping(body_camera.get("preview"))
        result = []
        for group_id, nodes in sorted(groups.items()):
            primary = next(
                (
                    item
                    for item in nodes
                    if bool(item.details.get("configured"))
                ),
                nodes[0],
            )
            usb = self._mapping(primary.details.get("usb_identity"))
            is_logitech = (
                str(usb.get("vendor", "")).lower() == "046d"
                and str(usb.get("product", "")).lower() == "0825"
            )
            owner = (
                "bx1-web.service"
                if robot_body.get("connected")
                else primary.ownership
            )
            health_state = (
                "online"
                if preview.get("preview_available")
                else "owned_elsewhere"
                if owner == "bx1-web.service"
                else primary.health.state
            )
            result.append(
                {
                    "device_id": "camera-group:%s" % group_id,
                    "name": (
                        "Logitech UVC Camera"
                        if is_logitech
                        else primary.name
                    ),
                    "category": "camera",
                    "present": any(item.present for item in nodes),
                    "available": bool(
                        preview.get("preview_available")
                    ),
                    "ownership": owner,
                    "health": DeviceHealth(
                        health_state,
                        "Physical capture remains owned by Robot Body",
                    ).as_dict(),
                    "details": {
                        "usb_identity": usb,
                        "underlying_nodes": [
                            item.details.get("device_node")
                            for item in nodes
                        ],
                        "primary_node": primary.details.get(
                            "device_node"
                        ),
                        "configured": any(
                            bool(item.details.get("configured"))
                            for item in nodes
                        ),
                        "preview_available": bool(
                            preview.get("preview_available")
                        ),
                        "streaming": bool(preview.get("streaming")),
                        "resolution": preview.get(
                            "resolution", "unknown"
                        ),
                        "frame_age_ms": preview.get("frame_age_ms"),
                    },
                    "last_seen": primary.last_seen,
                    "error": str(preview.get("error", "")),
                    "telemetry": dict(preview),
                    "capabilities": {
                        "preview_proxy": True,
                        "physical_capture": False,
                        "control": False,
                    },
                    "source": "Existing Robot Body + sysfs",
                    "control": "blocked",
                }
            )
        return result

    def _usb_identity(self, sys_device: Any) -> Mapping[str, str]:
        current = sys_device / "device"
        for _ in range(6):
            vendor, _ = self.environment.read_text(current / "idVendor")
            product, _ = self.environment.read_text(current / "idProduct")
            if vendor.strip() or product.strip():
                return {
                    "vendor": vendor.strip() or "unavailable",
                    "product": product.strip() or "unavailable",
                }
            current = current / ".."
        return {"vendor": "unavailable", "product": "unavailable"}

    @staticmethod
    def _configured(configured: str, node: Any, name: str) -> bool:
        return configured in {
            str(node),
            name,
            name.removeprefix("video"),
        }

    @staticmethod
    def _internal_device(name: str, driver: str) -> bool:
        value = ("%s %s" % (name, driver)).lower()
        return (
            "qcom-venus" in value
            or "venus decoder" in value
            or "venus encoder" in value
            or ("venus" in value and "video" in value)
        )

    @staticmethod
    def _group_id(
        name: str,
        usb_identity: Mapping[str, Any],
        internal: bool,
    ) -> str:
        vendor = str(usb_identity.get("vendor", "")).lower()
        product = str(usb_identity.get("product", "")).lower()
        if vendor not in {"", "unavailable"} and product not in {
            "",
            "unavailable",
        }:
            return "usb:%s:%s" % (vendor, product)
        return "internal:%s" % name if internal else "node:%s" % name

    @staticmethod
    def _mapping(value: Any) -> dict:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _ownership(owners: List[Mapping[str, Any]]) -> str:
        services = [str(item.get("service")) for item in owners if item.get("service")]
        return services[0] if services else "owned_elsewhere"


def _valid_jpeg(value: bytes) -> bool:
    return (
        len(value) >= 4
        and value.startswith(b"\xff\xd8")
        and value.endswith(b"\xff\xd9")
    )


def _jpeg_dimensions(
    value: bytes,
) -> tuple[Optional[int], Optional[int]]:
    if not _valid_jpeg(value):
        return None, None
    offset = 2
    frames = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while offset + 4 <= len(value):
        if value[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(value) and value[offset] == 0xFF:
            offset += 1
        if offset >= len(value):
            break
        marker = value[offset]
        offset += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(value):
            break
        length = int.from_bytes(value[offset : offset + 2], "big")
        if length < 2 or offset + length > len(value):
            break
        if marker in frames and length >= 7:
            height = int.from_bytes(
                value[offset + 3 : offset + 5], "big"
            )
            width = int.from_bytes(
                value[offset + 5 : offset + 7], "big"
            )
            return width or None, height or None
        offset += length
    return None, None


def _header_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(default)


def _header_float(value: Any) -> Optional[float]:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
