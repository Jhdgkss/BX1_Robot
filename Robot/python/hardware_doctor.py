from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional


class BX1HardwareDoctor:
    """Deterministic hardware health monitor and bounded repair helper.

    The doctor may inspect the bridge and restart the approved arduino-router
    service.  It never compiles or flashes firmware automatically.  Diagnostic
    sketches are generated from fixed templates for review and manual approval.
    """

    ALLOWED_SERVICES = {"arduino-router", "bx1-web.service", "bx1-robot-body.service"}
    ALLOWED_TEMPLATES = {"bridge_probe", "heartbeat_probe", "imu_probe"}

    def __init__(self, hardware: Any, project_root: Path, config: dict[str, Any],
                 logger: Optional[Callable[[str, str, Optional[dict[str, Any]]], None]] = None) -> None:
        self.hardware = hardware
        self.project_root = Path(project_root)
        self.config = config
        self.logger = logger
        self.lock = threading.Lock()
        self.history: deque[dict[str, Any]] = deque(maxlen=100)
        self.consecutive_failures = 0
        self.last_recovery_mono = 0.0
        self.last_generated_sketch = ""
        self.snapshot_data: dict[str, Any] = {
            "enabled": bool(config.get("hardware_doctor_enabled", True)),
            "state": "not_run",
            "severity": "unknown",
            "summary": "Hardware doctor has not run yet.",
            "automatic_flashing": False,
            "last_run_at": "",
            "last_recovery_at": "",
            "recovery_count": 0,
            "consecutive_failures": 0,
            "evidence": {},
            "recommendations": [],
        }

    def _log(self, kind: str, message: str, data: Optional[dict[str, Any]] = None) -> None:
        if self.logger:
            try:
                self.logger(kind, message, data)
                return
            except Exception:
                pass
        print(f"[hardware-doctor] {message}")

    @staticmethod
    def _run(cmd: list[str], timeout: float = 8.0) -> dict[str, Any]:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
            return {"ok": proc.returncode == 0, "returncode": proc.returncode,
                    "stdout": (proc.stdout or "")[-2000:], "stderr": (proc.stderr or "")[-2000:], "command": cmd}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "command": cmd}

    def _service_state(self, service: str) -> dict[str, Any]:
        if shutil.which("systemctl") is None:
            return {"available": False, "active": None, "state": "systemctl unavailable"}
        report = self._run(["systemctl", "is-active", service], timeout=4.0)
        state = str(report.get("stdout") or report.get("stderr") or "unknown").strip().splitlines()
        value = state[-1] if state else "unknown"
        return {"available": True, "active": value == "active", "state": value, "report": report}

    def diagnose(self, body_state: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        state = dict(body_state or self.hardware.get_status() or {})
        if body_state is not None and hasattr(self.hardware, "validate_cached_status"):
            state = dict(self.hardware.validate_cached_status(state))
        router_socket = str(getattr(self.hardware, "router_socket_path", "/var/run/arduino-router.sock"))
        socket_exists = os.path.exists(router_socket)
        socket_connectable = False
        socket_error = ""
        if socket_exists:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.5)
                    sock.connect(router_socket)
                    socket_connectable = True
            except Exception as exc:
                socket_error = str(exc)
        router_service = self._service_state("arduino-router")
        compile_tool = self.project_root / "tools" / "compile_mcu_sketch.sh"
        upload_tool = self.project_root / "tools" / "upload_mcu_sketch.sh"
        transport_connected = bool(state.get("mcu_transport_connected", state.get("bridge_available", False)))
        mcu_fresh = bool(state.get("mcu_heartbeat_fresh", False))
        mcu_ok = bool(state.get("mcu_ok", False))
        imu_present = bool(state.get("imu_present", False))
        imu_initialised = bool(state.get("imu_initialised", False))
        imu_sample_fresh = bool(state.get("imu_sample_fresh", False))
        imu_healthy = bool(state.get("imu_healthy", state.get("imu_ok", False)))
        bridge_mode = str(state.get("bridge_mode", "unknown"))
        bridge_error = str(state.get("bridge_error") or state.get("mcu_error") or "")
        protocol = state.get("protocol_version")
        firmware = state.get("firmware_version") or state.get("sketch_version")

        severity = "ok"
        summary = "MCU bridge and firmware heartbeat are healthy."
        recommendations: list[str] = []
        if not socket_exists:
            severity = "critical"
            summary = "The arduino-router socket is missing, so Linux cannot reach the MCU bridge."
            recommendations = ["Restart arduino-router.", "Check the MCU sketch if the socket does not return."]
        elif not socket_connectable:
            severity = "critical"
            summary = "The arduino-router socket exists but is not accepting connections."
            recommendations = ["Restart arduino-router.", "Check for a stale router process or socket permissions."]
        elif not transport_connected:
            severity = "fault"
            if "not registered" in bridge_error.lower() or "not available" in bridge_error.lower() or "method" in bridge_error.lower():
                summary = "The router is reachable but the BX1 MCU RPC methods are missing. The MCU is probably running an old or failed sketch."
                recommendations = ["Compile the current BX1 sketch.", "Flash only after reviewing the build and putting the robot in maintenance mode."]
            else:
                summary = "The router is reachable but the MCU status call failed."
                recommendations = ["Run a fresh bridge diagnosis.", "Restart arduino-router once, then inspect the MCU sketch and power if the fault remains."]
        elif not mcu_fresh:
            severity = "fault"
            summary = str(state.get("mcu_health_reason") or "MCU heartbeat is stale.")
            recommendations = ["Inspect Router RPC polling and MCU heartbeat without restarting services."]
        elif protocol and str(protocol) not in {"bx1.mcu.v1", "1", "1.0"}:
            severity = "warning"
            summary = f"The MCU is responding, but protocol version {protocol!r} is not the expected BX1 protocol."
            recommendations = ["Compare the desktop/body protocol with the flashed MCU sketch before enabling motion."]
        elif not imu_present or not imu_initialised or not imu_sample_fresh or not imu_healthy:
            severity = "warning"
            summary = str(state.get("imu_health_reason") or "The Modulino Movement is not healthy.")
            recommendations = [
                "Reseat the Qwiic cable at the UNO Q and Modulino Movement.",
                "Confirm the module is powered and address 0x6A is not duplicated.",
                "Run the review-only IMU probe if the fault remains.",
            ]

        if severity in {"critical", "fault"}:
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        evidence = {
            "mcu_ok": mcu_ok,
            "mcu_transport_connected": transport_connected,
            "mcu_heartbeat_fresh": mcu_fresh,
            "mcu_last_update_age_ms": state.get("mcu_last_update_age_ms"),
            "mcu_data_stale": bool(state.get("mcu_data_stale", True)),
            "mcu_health_reason": state.get("mcu_health_reason"),
            "bridge_mode": bridge_mode,
            "bridge_error": bridge_error,
            "router_socket": router_socket,
            "router_socket_exists": socket_exists,
            "router_socket_connectable": socket_connectable,
            "router_socket_error": socket_error,
            "router_service": router_service,
            "firmware_version": firmware,
            "protocol_version": protocol,
            "build_id": state.get("build_id"),
            "maintenance_mode": state.get("maintenance_mode"),
            "imu_ok": imu_healthy,
            "imu_present": imu_present,
            "imu_initialised": imu_initialised,
            "imu_sample_fresh": imu_sample_fresh,
            "imu_sample_age_ms": state.get("imu_sample_age_ms"),
            "imu_data_stale": bool(state.get("imu_data_stale", True)),
            "imu_healthy": imu_healthy,
            "imu_health_reason": state.get("imu_health_reason"),
            "imu_error": state.get("imu_error"),
            "imu_source": state.get("imu_source"),
            "imu_bus": state.get("imu_bus"),
            "imu_address": state.get("imu_address"),
            "compile_tool_present": compile_tool.exists(),
            "upload_tool_present": upload_tool.exists(),
            "automatic_flashing": False,
        }
        report = {
            "enabled": bool(self.config.get("hardware_doctor_enabled", True)),
            "state": "healthy" if severity == "ok" else "fault_detected",
            "severity": severity,
            "summary": summary,
            "last_run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "consecutive_failures": self.consecutive_failures,
            "evidence": evidence,
            "recommendations": recommendations,
            "automatic_flashing": False,
            "last_generated_sketch": self.last_generated_sketch,
        }
        with self.lock:
            previous = dict(self.snapshot_data)
            report["last_recovery_at"] = previous.get("last_recovery_at", "")
            report["recovery_count"] = int(previous.get("recovery_count", 0) or 0)
            self.snapshot_data = report
            self.history.append(dict(report))
        return report

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            out = dict(self.snapshot_data)
            out["history"] = list(self.history)[-10:]
        return out

    def safe_recover(self, reason: str = "manual", force: bool = False) -> dict[str, Any]:
        cooldown = max(30.0, float(self.config.get("hardware_doctor_recovery_cooldown_s", 90.0) or 90.0))
        now = time.monotonic()
        if not force and now - self.last_recovery_mono < cooldown:
            return {"ok": False, "skipped": True, "reason": "recovery cooldown active",
                    "remaining_s": round(cooldown - (now - self.last_recovery_mono), 1)}
        service = "arduino-router"
        if service not in self.ALLOWED_SERVICES:
            return {"ok": False, "error": "service is not allowlisted"}
        before = self.diagnose()
        result = self._run(["systemctl", "restart", service], timeout=15.0)
        if not result.get("ok") and shutil.which("sudo"):
            result = self._run(["sudo", "-n", "systemctl", "restart", service], timeout=15.0)
        self.last_recovery_mono = now
        time.sleep(1.2)
        after = self.diagnose()
        ok = bool(result.get("ok")) and after.get("severity") not in {"critical"}
        with self.lock:
            self.snapshot_data["last_recovery_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            self.snapshot_data["recovery_count"] = int(self.snapshot_data.get("recovery_count", 0) or 0) + 1
            self.snapshot_data["last_recovery_reason"] = reason
        self._log("doctor" if ok else "error", f"Hardware Doctor recovery {'completed' if ok else 'failed'}: {reason}", {"before": before, "after": after, "service": result})
        return {"ok": ok, "action": "restart arduino-router", "reason": reason,
                "service_result": result, "before": before, "after": after, "automatic_flashing": False}

    def maybe_auto_recover(self, report: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        report = report or self.snapshot()
        if not bool(self.config.get("hardware_doctor_auto_recovery_enabled", True)):
            return None
        threshold = max(2, int(self.config.get("hardware_doctor_failure_threshold", 3) or 3))
        if int(report.get("consecutive_failures", 0) or 0) < threshold:
            return None
        evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
        bridge_error = str(evidence.get("bridge_error") or "").lower()
        socket_exists = bool(evidence.get("router_socket_exists"))
        socket_connectable = bool(evidence.get("router_socket_connectable"))
        # Restarting arduino-router cannot add RPC methods to an old/failed MCU
        # sketch. It only removes the socket temporarily and interrupts speech/LED
        # activity. Leave this fault stable for the explicit MCU repair workflow.
        if socket_exists and socket_connectable and any(token in bridge_error for token in (
            "not registered", "not available", "method", "old or failed sketch",
        )):
            return None
        # Automatic recovery is reserved for an actual router/socket failure.
        if socket_exists and socket_connectable:
            return None
        return self.safe_recover(reason=f"automatic router recovery after {threshold} failed checks")

    def generate_sketch(self, template: str, note: str = "") -> dict[str, Any]:
        name = str(template or "").strip().lower()
        if name not in self.ALLOWED_TEMPLATES:
            return {"ok": False, "error": f"Unknown template. Allowed: {sorted(self.ALLOWED_TEMPLATES)}"}
        # Arduino CLI expects the primary .ino filename to match its immediate
        # sketch folder. Keep the timestamp one level above that folder.
        batch_dir = self.project_root / "runtime" / "doctor" / "generated_sketches" / time.strftime("%Y%m%d_%H%M%S")
        out_dir = batch_dir / name
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.ino"
        safe_note = str(note or "").replace("*/", "* /")[:400]
        templates = {
            "bridge_probe": self._bridge_probe_template(safe_note),
            "heartbeat_probe": self._heartbeat_probe_template(safe_note),
            "imu_probe": self._imu_probe_template(safe_note),
        }
        path.write_text(templates[name], encoding="utf-8")
        manifest = {
            "schema": "bx1.diagnostic_sketch.v1", "template": name,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "sketch": str(path), "approved": False, "compiled": False, "flashed": False,
            "safety": "Generated from a fixed diagnostic template. No motor outputs. Review and approve before compiling or flashing.",
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.last_generated_sketch = str(path)
        with self.lock:
            self.snapshot_data["last_generated_sketch"] = str(path)
        self._log("doctor", f"Generated review-only MCU diagnostic sketch: {name}", manifest)
        return {"ok": True, **manifest, "automatic_flashing": False}

    @staticmethod
    def _bridge_probe_template(note: str) -> str:
        return f'''/* BX1 generated bridge probe. Review only; no motor outputs.\nNote: {note}\n*/\n#include <Arduino.h>\n#include <Arduino_RouterBridge.h>\nunsigned long sequenceNo = 0;\nString bx1_probe_status() {{\n  return String("{{\\\"ok\\\":true,\\\"probe\\\":\\\"bridge\\\",\\\"sequence\\\":") + String(sequenceNo) + "}}";\n}}\nvoid setup() {{ Serial.begin(115200); Bridge.begin(); Bridge.provide("bx1_probe_status", bx1_probe_status); }}\nvoid loop() {{ sequenceNo++; delay(250); }}\n'''

    @staticmethod
    def _heartbeat_probe_template(note: str) -> str:
        return f'''/* BX1 generated heartbeat probe. Review only; no motor outputs.\nNote: {note}\n*/\n#include <Arduino.h>\n#include <Arduino_RouterBridge.h>\nunsigned long bootMs = 0;\nString bx1_get_status() {{\n  return String("{{\\\"mcu_ok\\\":true,\\\"firmware_version\\\":\\\"diagnostic-heartbeat-1\\\",\\\"protocol_version\\\":\\\"bx1.mcu.v1\\\",\\\"uptime_ms\\\":") + String(millis()-bootMs) + ",\\\"maintenance_mode\\\":true}}";\n}}\nvoid setup() {{ bootMs=millis(); Serial.begin(115200); Bridge.begin(); Bridge.provide("bx1_get_status", bx1_get_status); }}\nvoid loop() {{ delay(20); }}\n'''

    @staticmethod
    def _imu_probe_template(note: str) -> str:
        return f'''/* BX1 generated Modulino Movement probe. Review only; no motor outputs.
Note: {note}
*/
#include <Arduino.h>
#include <Wire.h>
#include <Arduino_RouterBridge.h>
#include <Arduino_LSM6DSOX.h>
LSM6DSOXClass movementImu(Wire1, 0x6A);
bool imuOk=false; float ax=0, ay=0, az=0, gx=0, gy=0, gz=0;
String bx1_get_status() {{
  if (imuOk) {{
    if (movementImu.accelerationAvailable()) movementImu.readAcceleration(ax,ay,az);
    if (movementImu.gyroscopeAvailable()) movementImu.readGyroscope(gx,gy,gz);
  }}
  return String("{{\"mcu_ok\":true,\"probe\":\"modulino_movement\",\"imu_ok\":") + (imuOk?"true":"false") + ",\"imu_bus\":\"Wire1/Qwiic\",\"imu_address\":\"0x6A\",\"ax\":" + String(ax,4) + ",\"ay\":" + String(ay,4) + ",\"az\":" + String(az,4) + ",\"gx\":" + String(gx,3) + ",\"gy\":" + String(gy,3) + ",\"gz\":" + String(gz,3) + ",\"maintenance_mode\":true}}";
}}
void setup() {{ Serial.begin(115200); Wire1.begin(); Wire1.setClock(100000); imuOk=movementImu.begin(); Bridge.begin(); Bridge.provide("bx1_get_status", bx1_get_status); }}
void loop() {{ delay(20); }}
'''
