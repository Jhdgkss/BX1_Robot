from __future__ import annotations

import glob
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from hardware_freshness import HardwareFreshnessTracker

try:
    from arduino.app_utils import Bridge  # type: ignore
    ARDUINO_APP_LAB_AVAILABLE = True
except Exception:
    Bridge = None  # type: ignore
    ARDUINO_APP_LAB_AVAILABLE = False

try:
    import msgpack  # type: ignore
    MSGPACK_AVAILABLE = True
except Exception:
    msgpack = None  # type: ignore
    MSGPACK_AVAILABLE = False

try:
    import serial  # type: ignore
    SERIAL_AVAILABLE = True
except Exception:
    serial = None  # type: ignore
    SERIAL_AVAILABLE = False


@dataclass
class BridgeCallResult:
    ok: bool
    value: Any = None
    error: str = ""


class ObserverOnlyHardwareBridge:
    """Non-owning bridge used by the side-by-side Alpha qualification service.

    It never opens a serial device, connects to Router RPC, imports GPIO drivers,
    polls the MCU, or forwards an actuator command.
    """

    BLOCK_REASON = "BX1 OS Alpha observer-only isolation blocks hardware ownership"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.available = False
        self.last_error = self.BLOCK_REASON
        self.last_state: Dict[str, Any] = {
            "mcu_ok": False,
            "bridge_available": False,
            "mcu_transport_connected": False,
            "bridge_mode": "observer_only",
            "observer_only": True,
            "hardware_ownership": False,
            "actuator_access": False,
            "safety_ok": True,
            "mode": "alpha_qualification",
            "bridge_error": self.BLOCK_REASON,
        }

    def call(self, method: str, *args: Any) -> BridgeCallResult:
        return BridgeCallResult(False, None, f"{self.BLOCK_REASON}: {method}")

    def send_action(self, action: Dict[str, Any]) -> BridgeCallResult:
        action_type = str(action.get("type", "unknown"))
        return BridgeCallResult(
            False,
            {"blocked": True, "observer_only": True, "action_type": action_type},
            f"{self.BLOCK_REASON}: {action_type}",
        )

    def get_status(self) -> Dict[str, Any]:
        state = dict(self.last_state)
        state["timestamp_linux"] = time.time()
        return state

    def validate_cached_status(
        self,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        current = dict(state or self.last_state)
        current.update(self.last_state)
        current["timestamp_linux"] = time.time()
        return current


class RouterRpcClient:
    """Tiny MessagePack-RPC client for the UNO Q arduino-router daemon.

    The UNO Q Router RPC socket is normally:
        /var/run/arduino-router.sock

    Message format:
        request  = [0, msgid, method, [args...]]
        response = [1, msgid, error, result]
    """

    def __init__(self, socket_path: str = "/var/run/arduino-router.sock", timeout_s: float = 2.5) -> None:
        self.socket_path = socket_path
        self.timeout_s = timeout_s
        self._msgid = 0
        self._lock = threading.Lock()
        # Serialize complete Router transactions. The MCU processes one RPC at a
        # time; status polling, LED-state updates and configuration calls used to
        # overlap and cause intermittent timeouts even though the bridge was healthy.
        self._io_lock = threading.Lock()

    def available(self) -> bool:
        return MSGPACK_AVAILABLE and os.path.exists(self.socket_path)

    def call(self, method: str, *args: Any) -> BridgeCallResult:
        with self._io_lock:
            return self._call_serialized(method, *args)

    def _call_serialized(self, method: str, *args: Any) -> BridgeCallResult:
        if not MSGPACK_AVAILABLE or msgpack is None:
            return BridgeCallResult(False, None, "msgpack is not installed in the Python venv.")
        if not os.path.exists(self.socket_path):
            return BridgeCallResult(False, None, f"arduino-router socket not found: {self.socket_path}")

        with self._lock:
            self._msgid += 1
            msgid = self._msgid

        request = [0, msgid, method, list(args)]
        unpacker = msgpack.Unpacker(raw=False)

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(self.socket_path)
                sock.sendall(msgpack.packb(request, use_bin_type=True))

                deadline = time.time() + self.timeout_s
                while time.time() < deadline:
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    unpacker.feed(chunk)
                    for msg in unpacker:
                        if not isinstance(msg, (list, tuple)) or len(msg) < 4:
                            continue
                        msg_type, resp_id, error, result = msg[0], msg[1], msg[2], msg[3]
                        if msg_type != 1 or resp_id != msgid:
                            continue
                        if error is not None:
                            return BridgeCallResult(False, None, str(error))
                        return BridgeCallResult(True, result, "")

                return BridgeCallResult(False, None, f"Timeout waiting for Router RPC response: method={method}")

        except Exception as exc:
            return BridgeCallResult(False, None, f"Router RPC error calling {method}: {exc}")


class BX1HardwareBridge:
    """Bridge from UNO Q Linux/Python side to the Arduino MCU.

    v10.4 priority order:
      1. Arduino App Lab Bridge, if running inside App Lab.
      2. Arduino Router RPC via /var/run/arduino-router.sock.
      3. Legacy serial fallback, only for boards that expose /dev/ttyACM*.

    On UNO Q under SSH/systemd, Router RPC is the normal route. The board often
    appears as a network target rather than a local serial port, so serial-only
    checks can fail even when the MCU and arduino-router are correct.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, *, clock=time.monotonic) -> None:
        config = config or {}
        self.app_lab_available = ARDUINO_APP_LAB_AVAILABLE
        self.router_socket_path = os.environ.get("BX1_ROUTER_SOCKET", "/var/run/arduino-router.sock")
        self.router = RouterRpcClient(self.router_socket_path, timeout_s=float(os.environ.get("BX1_ROUTER_TIMEOUT", "3.0")))
        self.router_available = self.router.available()
        self.serial_available = SERIAL_AVAILABLE
        self.serial_port: Optional[str] = None
        self.serial_baud = int(os.environ.get("BX1_MCU_BAUD", "115200"))
        self._serial = None
        self._serial_lock = threading.Lock()
        self.last_error = ""
        self.available = bool(self.app_lab_available or self.router_available or self.serial_available)
        self.freshness = HardwareFreshnessTracker(
            warning_ms=float(config.get("hardware_freshness_warning_ms", 1500.0)),
            stale_ms=float(config.get("hardware_freshness_stale_ms", 3000.0)),
            clock=clock,
        )
        self.last_state: Dict[str, Any] = {
            "mcu_ok": False,
            "bridge_available": self.available,
            "bridge_mode": (
                "app_lab" if self.app_lab_available else
                ("router_rpc" if self.router_available else ("serial" if self.serial_available else "none"))
            ),
            "router_available": self.router_available,
            "router_socket": self.router_socket_path,
            "serial_available": self.serial_available,
            "serial_port": None,
            "safety_ok": True,
            "mode": "linux_only",
        }

    # ---------------- App Lab path ----------------
    def _call_app_lab(self, method: str, *args: Any) -> BridgeCallResult:
        if not self.app_lab_available or Bridge is None:
            return BridgeCallResult(False, None, "Arduino App Lab Bridge is not available in this runtime.")
        try:
            result = Bridge.call(method, *args)
            if hasattr(result, "result"):
                try:
                    value = result.result()
                except TypeError:
                    holder = None
                    ok = result.result(holder)  # type: ignore[misc]
                    value = holder if ok else None
            else:
                value = result
            self.last_error = ""
            return BridgeCallResult(True, value, "")
        except Exception as exc:
            self.last_error = str(exc)
            return BridgeCallResult(False, None, str(exc))

    # ---------------- Router RPC path ----------------
    def _call_router(self, method: str, *args: Any) -> BridgeCallResult:
        # Re-check because arduino-router may start after the Python app.
        self.router_available = self.router.available()
        if not self.router_available:
            if not MSGPACK_AVAILABLE:
                return BridgeCallResult(False, None, "msgpack is not installed.")
            return BridgeCallResult(False, None, f"arduino-router socket not found: {self.router_socket_path}")
        return self.router.call(method, *args)

    # ---------------- Serial fallback path ----------------
    def _candidate_ports(self) -> List[str]:
        env_port = os.environ.get("BX1_MCU_SERIAL_PORT", "").strip()
        ports: List[str] = []
        if env_port:
            ports.append(env_port)
        for pattern in (
            "/dev/serial/by-id/*",
            "/dev/ttyACM*",
            "/dev/ttyUSB*",
            "/dev/ttyAMA*",
        ):
            ports.extend(sorted(glob.glob(pattern)))
        seen = set()
        out: List[str] = []
        for p in ports:
            if p not in seen:
                out.append(p)
                seen.add(p)
        return out

    def _open_serial(self):
        if not SERIAL_AVAILABLE or serial is None:
            raise RuntimeError("pyserial is not installed. Run: .venv/bin/pip install pyserial")
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    return self._serial
            except Exception:
                pass
            self._serial = None

        last_exc = ""
        for port in self._candidate_ports():
            try:
                ser = serial.Serial(port, self.serial_baud, timeout=1.5, write_timeout=1.5)
                self.serial_port = port
                time.sleep(1.8)
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except Exception:
                    pass
                self._serial = ser
                return ser
            except Exception as exc:
                last_exc = f"{port}: {exc}"
        raise RuntimeError("No Arduino MCU serial port found. Candidates tried: " + ", ".join(self._candidate_ports()) + (f"; last error: {last_exc}" if last_exc else ""))

    def _serial_request(self, line: str, expect_prefix: str, timeout_s: float = 2.5) -> BridgeCallResult:
        if not SERIAL_AVAILABLE:
            return BridgeCallResult(False, None, "pyserial is not installed in the UNO Q Python venv.")
        with self._serial_lock:
            try:
                ser = self._open_serial()
                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass
                ser.write((line.rstrip("\n") + "\n").encode("utf-8"))
                ser.flush()
                deadline = time.time() + timeout_s
                junk: List[str] = []
                while time.time() < deadline:
                    raw = ser.readline()
                    if not raw:
                        continue
                    text = raw.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    if text.startswith(expect_prefix):
                        payload = text[len(expect_prefix):]
                        return BridgeCallResult(True, payload, "")
                    if expect_prefix == "BX1_STATUS:" and text.startswith("{"):
                        return BridgeCallResult(True, text, "")
                    junk.append(text[:160])
                return BridgeCallResult(False, None, f"Serial timeout waiting for {expect_prefix}; port={self.serial_port}; last lines={junk[-5:]}")
            except Exception as exc:
                try:
                    if self._serial is not None:
                        self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self.last_error = str(exc)
                return BridgeCallResult(False, None, str(exc))

    def _call_serial(self, method: str, *args: Any) -> BridgeCallResult:
        if method == "bx1_get_status":
            return self._serial_request("BX1_STATUS", "BX1_STATUS:", timeout_s=3.0)
        if method == "bx1_set_command":
            action_json = str(args[0]) if args else "{}"
            return self._serial_request("BX1_ACTION:" + action_json, "BX1_OK:", timeout_s=3.0)
        if method == "bx1_set_estop":
            val = "1" if bool(args[0]) else "0"
            return self._serial_request("BX1_ESTOP:" + val, "BX1_OK:", timeout_s=2.0)
        return BridgeCallResult(False, None, f"Unsupported serial bridge method: {method}")

    # ---------------- Public bridge API ----------------
    def _router_method_missing_error(self, method: str, router_error: str) -> str:
        return (
            f"MCU bridge method '{method}' is not registered with arduino-router. "
            "This normally means the Arduino MCU sketch is missing, still running an older BX1 sketch, "
            "or arduino-router has not refreshed after upload. Run: ./APPLY_BX1_V10_37_HARDWARE_FIX.sh "
            "then check: ./.venv/bin/python tools/check_mcu_router_bridge.py. "
            f"Router error was: {router_error}"
        )

    def _looks_like_router_method_missing(self, error: str) -> bool:
        low = str(error or "").lower()
        return (
            "method" in low and "not available" in low
        ) or (
            "not registered" in low
        ) or (
            "unknown method" in low
        )

    def call(self, method: str, *args: Any) -> BridgeCallResult:
        errors: List[str] = []

        if self.app_lab_available:
            res = self._call_app_lab(method, *args)
            if res.ok:
                self.last_state["bridge_mode"] = "app_lab"
                return res
            errors.append("app_lab: " + res.error)

        # Router RPC is the normal SSH/systemd path on UNO Q.  If the router is
        # reachable but says a BX1 method is missing, serial fallback is not useful
        # on UNO Q under Linux/systemd; it just buries the real cause under
        # "No Arduino MCU serial port found".  Return a clear flash-sketch error.
        res = self._call_router(method, *args)
        if res.ok:
            self.last_state["bridge_mode"] = "router_rpc"
            self.last_state["router_available"] = True
            self.last_state["router_socket"] = self.router_socket_path
            self.last_state["bridge_error"] = ""
            return res
        errors.append("router_rpc: " + res.error)
        if self.router.available() and self._looks_like_router_method_missing(res.error):
            msg = self._router_method_missing_error(method, res.error)
            self.last_error = msg
            self.last_state.update({
                "mcu_ok": False,
                "bridge_mode": "router_rpc_method_missing",
                "bridge_error": msg,
                "router_available": True,
                "router_socket": self.router_socket_path,
                "mcu_repair_hint": "Flash the current BX1 MCU sketch and restart arduino-router.",
            })
            return BridgeCallResult(False, None, msg)

        if self.serial_available:
            res = self._call_serial(method, *args)
            if res.ok:
                self.last_state["bridge_mode"] = "serial"
                self.last_state["serial_port"] = self.serial_port
                self.last_state["bridge_error"] = ""
                return res
            errors.append("serial: " + res.error)

        msg = "; ".join(e for e in errors if e) or "No hardware bridge available."
        self.last_error = msg
        return BridgeCallResult(False, None, msg)

    def get_status(self) -> Dict[str, Any]:
        res = self.call("bx1_get_status")
        if not res.ok:
            state = dict(self.last_state)
            state.update({
                "mcu_ok": False,
                "bridge_available": bool(self.app_lab_available or self.router.available() or self.serial_available),
                "bridge_error": res.error,
                "bridge_mode": self.last_state.get("bridge_mode", "router_rpc" if self.router.available() else "serial"),
                "router_available": self.router.available(),
                "router_socket": self.router_socket_path,
                "serial_available": self.serial_available,
                "serial_port": self.serial_port,
                "timestamp_linux": time.time(),
            })
            state = self.freshness.evaluate(state, transport_connected=False)
            self.last_state = state
            return state

        raw = res.value
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if isinstance(raw, str):
                state = json.loads(raw)
            elif isinstance(raw, dict):
                state = raw
            else:
                state = {"mcu_raw": raw}
            state.setdefault("mcu_ok", True)
            state.setdefault("bridge_available", True)
            state.setdefault("bridge_mode", self.last_state.get("bridge_mode", "router_rpc"))
            state.setdefault("router_available", self.router.available())
            state.setdefault("router_socket", self.router_socket_path)
            state.setdefault("serial_port", self.serial_port)
            state["timestamp_linux"] = time.time()
            state = self.freshness.evaluate(state, transport_connected=True)
            self.last_state = state
            return state
        except Exception as exc:
            state = {
                "mcu_ok": False,
                "bridge_available": bool(self.app_lab_available or self.router.available() or self.serial_available),
                "bridge_mode": self.last_state.get("bridge_mode", "router_rpc"),
                "router_available": self.router.available(),
                "router_socket": self.router_socket_path,
                "serial_available": self.serial_available,
                "serial_port": self.serial_port,
                "bridge_parse_error": str(exc),
                "mcu_raw": str(raw)[:500],
                "timestamp_linux": time.time(),
            }
            state = self.freshness.evaluate(state, transport_connected=False)
            self.last_state = state
            return state

    def validate_cached_status(self, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Age an existing payload without treating the read itself as a new frame."""
        current = dict(state or self.last_state)
        connected = bool(current.get("mcu_transport_connected", current.get("bridge_available", False)))
        validated = self.freshness.evaluate(current, transport_connected=connected)
        if state is None or state is self.last_state:
            self.last_state = validated
        return validated


    def _send_hardware_config_small_rpc(self, action: Dict[str, Any]) -> BridgeCallResult:
        """Apply configure_hardware_v2 using several tiny Router RPC calls.

        Arduino RouterBridge has a small MessagePack/RPC payload limit. Sending
        the whole flattened hardware registry as one JSON string can fail with:
            [6, 'message size exceeds the limit']

        So v10.21 applies hardware config through compact direct RPC calls, including the two-servo head mixer.
        """
        errors: List[str] = []
        results: List[Any] = []

        def call_step(method: str, *args: Any) -> bool:
            res = self.call(method, *args)
            if res.ok:
                results.append({"method": method, "args": list(args), "value": res.value})
                return True
            errors.append(f"{method}: {res.error}")
            return False

        ok = True
        ok = call_step(
            "bx1_config_led_bus",
            int(action.get("led_bus_pin", -1)),
            int(action.get("led_bus_count", 1)),
            float(action.get("led_bus_brightness_limit", 0.2)),
        ) and ok

        for zone, start_key, end_key in [
            ("mouth", "zone_mouth_start", "zone_mouth_end"),
            ("left_eye", "zone_left_eye_start", "zone_left_eye_end"),
            ("right_eye", "zone_right_eye_start", "zone_right_eye_end"),
            ("chest", "zone_chest_start", "zone_chest_end"),
            ("status", "zone_status_start", "zone_status_end"),
        ]:
            ok = call_step(
                "bx1_config_led_zone",
                zone,
                int(action.get(start_key, -1)),
                int(action.get(end_key, -1)),
            ) and ok

        for name, pkey, minkey, homekey, maxkey, invkey in [
            ("head_yaw", "head_yaw_pin", "head_yaw_min_deg", "head_yaw_home_deg", "head_yaw_max_deg", "head_yaw_invert"),
            ("gimbal_left", "head_gimbal_left_pin", "head_gimbal_left_min_deg", "head_gimbal_left_home_deg", "head_gimbal_left_max_deg", "head_gimbal_left_invert"),
            ("gimbal_right", "head_gimbal_right_pin", "head_gimbal_right_min_deg", "head_gimbal_right_home_deg", "head_gimbal_right_max_deg", "head_gimbal_right_invert"),
        ]:
            ok = call_step(
                "bx1_config_servo",
                name,
                int(action.get(pkey, -1)),
                float(action.get(minkey, 0)),
                float(action.get(homekey, 0)),
                float(action.get(maxkey, 0)),
                int(action.get(invkey, 0)),
            ) and ok

        ok = call_step(
            "bx1_config_head_limits",
            float(action.get("head_pitch_min_deg", -10.0)), float(action.get("head_pitch_home_deg", 0.0)), float(action.get("head_pitch_max_deg", 10.0)),
            float(action.get("head_roll_min_deg", -10.0)), float(action.get("head_roll_home_deg", 0.0)), float(action.get("head_roll_max_deg", 10.0)),
        ) and ok
        ok = call_step(
            "bx1_config_head_mix",
            float(action.get("head_pitch_gain", 1.0)), float(action.get("head_roll_gain", 1.0)),
            int(action.get("head_left_pitch_sign", 1)), int(action.get("head_right_pitch_sign", -1)),
            int(action.get("head_left_roll_sign", 1)), int(action.get("head_right_roll_sign", 1)),
        ) and ok
        ok = call_step(
            "bx1_config_servo_quiet",
            int(action.get("servo_quiet_release_enabled", 1)),
            int(action.get("servo_release_after_ms", 1200)),
            int(action.get("servo_pulse_deadband_us", 4)),
        ) and ok

        ok = call_step("bx1_config_done") and ok

        if ok:
            return BridgeCallResult(True, {"mode": "small_rpc", "steps": results}, "")
        return BridgeCallResult(False, {"mode": "small_rpc", "steps": results}, "; ".join(errors))

    def send_action(self, action: Dict[str, Any]) -> BridgeCallResult:
        action_type = str(action.get("type", ""))

        if action_type == "configure_hardware_v2":
            small = self._send_hardware_config_small_rpc(action)
            if small.ok:
                return small
            # Fall back to the old JSON command only if the sketch does not yet
            # provide the direct hardware-configuration RPC methods.
            fallback_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
            fallback = self.call("bx1_set_command", fallback_json)
            if fallback.ok:
                return BridgeCallResult(True, {"mode": "json_fallback", "small_rpc_error": small.error, "fallback": fallback.value}, "")
            return BridgeCallResult(False, small.value, small.error + "; json_fallback: " + fallback.error)

        if action_type == "set_head_pose":
            args = action.get("args") if isinstance(action.get("args"), dict) else {}
            yaw = float(args.get("yaw_deg", 0.0) or 0.0)
            pitch = float(args.get("pitch_deg", 0.0) or 0.0)
            roll = float(args.get("roll_deg", args.get("tilt_deg", 0.0)) or 0.0)
            direct = self.call("bx1_set_head_pose", yaw, pitch, roll)
            if direct.ok:
                return BridgeCallResult(True, {"mode": "direct_head_rpc", "applied": direct.value, "yaw_deg": yaw, "pitch_deg": pitch, "roll_deg": roll}, "")
            # Compatibility with older MCU firmware.
            fallback_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
            fallback = self.call("bx1_set_command", fallback_json)
            if fallback.ok:
                return BridgeCallResult(True, {"mode": "json_fallback", "direct_error": direct.error, "fallback": fallback.value}, "")
            return BridgeCallResult(False, None, direct.error + "; json_fallback: " + fallback.error)

        if action_type == "set_led_zone":
            args = action.get("args") if isinstance(action.get("args"), dict) else {}
            zone = str(args.get("zone", "mouth") or "mouth")
            colour = str(args.get("colour", args.get("color", "off")) or "off")
            brightness = max(0.0, min(1.0, float(args.get("brightness", 0.0) or 0.0)))
            direct = self.call("bx1_set_led_zone", zone, colour, brightness)
            if direct.ok:
                return BridgeCallResult(True, {"mode": "direct_led_rpc", "applied": direct.value, "zone": zone, "colour": colour, "brightness": brightness}, "")
            # Compatibility with MCU v10.23 and earlier. Mouth animation is less
            # responsive through JSON, but ordinary state changes still work.
            fallback_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
            fallback = self.call("bx1_set_command", fallback_json)
            if fallback.ok:
                return BridgeCallResult(True, {"mode": "json_fallback", "direct_error": direct.error, "fallback": fallback.value}, "")
            return BridgeCallResult(False, None, direct.error + "; json_fallback: " + fallback.error)

        action_json = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        return self.call("bx1_set_command", action_json)

    def set_estop(self, enabled: bool) -> BridgeCallResult:
        return self.call("bx1_set_estop", bool(enabled))
