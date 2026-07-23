#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

import msgpack

SOCKET_PATH = os.environ.get("BX1_ROUTER_SOCKET", "/var/run/arduino-router.sock")


def rpc_call(method: str, args=None, timeout: float = 5.0):
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
                if isinstance(msg, (list, tuple)) and len(msg) >= 4 and msg[0] == 1 and msg[1] == msgid:
                    if msg[2] is not None:
                        raise RuntimeError(str(msg[2]))
                    return msg[3]
    raise TimeoutError(f"Timeout waiting for {method}")


def status(label: str):
    raw = rpc_call("bx1_get_status")
    data = json.loads(raw) if isinstance(raw, str) else raw
    print(f"\n{label}")
    print(" firmware:", data.get("firmware_version"))
    print(" mode:", data.get("mode"))
    print(" pins:", data.get("head_servo_pins"))
    print(" attached:", data.get("head_servo_attached"))
    print(" logical:", {
        "yaw": data.get("head_yaw_deg"),
        "pitch": data.get("head_pitch_deg"),
        "roll": data.get("head_roll_deg"),
    })
    print(" targets:", data.get("head_gimbal_targets_deg"))
    print(" pulse_us:", data.get("head_servo_pulse_us"))
    print(" attach_error:", data.get("head_servo_attach_error"))
    return data


if not Path(SOCKET_PATH).exists():
    raise SystemExit(f"Router socket not found: {SOCKET_PATH}")

print("BX1 v10.23 direct head RPC test")
print("Keep access to the servo power switch. Movement is limited to ±3° and 1450/1550 us.")

status("INITIAL")

poses = [
    ("CENTRE", 0.0, 0.0, 0.0),
    ("PITCH -3", 0.0, -3.0, 0.0),
    ("PITCH +3", 0.0, 3.0, 0.0),
    ("ROLL -3", 0.0, 0.0, -3.0),
    ("ROLL +3", 0.0, 0.0, 3.0),
    ("YAW -3", -3.0, 0.0, 0.0),
    ("YAW +3", 3.0, 0.0, 0.0),
    ("CENTRE", 0.0, 0.0, 0.0),
]

for label, yaw, pitch, roll in poses:
    result = rpc_call("bx1_set_head_pose", [yaw, pitch, roll])
    print(f"\n{label}: rpc={result}")
    time.sleep(1.2)
    status(label)

print("\nIndividual servo pulse test (50 us each side of neutral):")
for name in ("head_yaw", "gimbal_left", "gimbal_right"):
    for pulse in (1450, 1550, 1500):
        result = rpc_call("bx1_test_servo_us", [name, pulse])
        print(f" {name} {pulse} us: {result}")
        time.sleep(1.0)

status("FINAL")
print("\nComplete.")
