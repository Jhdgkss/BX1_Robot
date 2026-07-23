#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import msgpack
except Exception as exc:
    print("RESULT: FAIL - msgpack is not installed:", exc)
    print("Run: .venv/bin/pip install msgpack")
    raise SystemExit(1)

SOCKET_PATH = os.environ.get("BX1_ROUTER_SOCKET", "/var/run/arduino-router.sock")

print("BX1 Router RPC Bridge Check")
print("=" * 44)
print(f"Python: {sys.executable}")
print(f"Socket: {SOCKET_PATH}")
print()

if not Path(SOCKET_PATH).exists():
    print("RESULT: FAIL - arduino-router socket not found.")
    print("Try:")
    print("  systemctl status arduino-router --no-pager")
    print("  sudo systemctl restart arduino-router")
    raise SystemExit(1)


def rpc_call(method: str, args=None, timeout=4.0):
    if args is None:
        args = []
    msgid = int(time.time() * 1000) % 1000000
    req = [0, msgid, method, args]
    unpacker = msgpack.Unpacker(raw=False)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(SOCKET_PATH)
        sock.sendall(msgpack.packb(req, use_bin_type=True))
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            unpacker.feed(chunk)
            for msg in unpacker:
                if isinstance(msg, (list, tuple)) and len(msg) >= 4:
                    if msg[0] == 1 and msg[1] == msgid:
                        if msg[2] is not None:
                            raise RuntimeError(str(msg[2]))
                        return msg[3]
    raise TimeoutError(f"Timeout waiting for response to {method}")


try:
    status = rpc_call("bx1_get_status")
    print("bx1_get_status returned:")
    print(status if isinstance(status, str) else json.dumps(status, indent=2))
except Exception as exc:
    print("RESULT: FAIL - Router call failed:", exc)
    print()
    print("Useful diagnostics:")
    print("  systemctl status arduino-router --no-pager")
    print("  journalctl -u arduino-router -n 80 --no-pager")
    print()
    print("This usually means the MCU sketch is not running or did not register bx1_get_status with Bridge.provide().")
    raise SystemExit(1)

try:
    action = {"type": "set_led_zone", "zone": "mouth", "colour": "cyan", "brightness": 0.2}
    result = rpc_call("bx1_set_command", [json.dumps(action, separators=(',', ':'))])
    print()
    print("bx1_set_command returned:", result)
except Exception as exc:
    print()
    print("WARNING: Status worked but test command failed:", exc)
    raise SystemExit(2)


try:
    print()
    print("Testing compact v10.23 non-destructive hardware RPC...")
    print("  led bus D3, count 100, limit 0.20")
    print("  mouth zone LED 1")
    rpc_call("bx1_config_led_bus", [3, 100, 0.2])
    rpc_call("bx1_config_led_zone", ["mouth", 1, 1])
    rpc_call("bx1_config_led_zone", ["left_eye", 2, 2])
    rpc_call("bx1_config_led_zone", ["right_eye", 3, 3])
    rpc_call("bx1_config_head_limits", [-10.0, 0.0, 10.0, -10.0, 0.0, 10.0])
    rpc_call("bx1_config_head_mix", [1.0, 1.0, 1, -1, 1, 1])
    rpc_call("bx1_config_done", [])
    result = rpc_call("bx1_set_command", [json.dumps({"type":"set_led_zone","args":{"zone":"mouth","colour":"cyan","brightness":0.2}}, separators=(',', ':'))])
    direct_head = rpc_call("bx1_set_head_pose", [0.0, 0.0, 0.0])
    print("compact hardware config returned OK; mouth cyan command:", result)
    print("direct head RPC returned:", direct_head)
except Exception as exc:
    print()
    print("WARNING: Router status works, but v10.21 compact hardware/gimbal config failed:", exc)
    raise SystemExit(2)


print()
print("RESULT: PASS - Router RPC can reach the MCU sketch and v10.23 direct head RPC.")
