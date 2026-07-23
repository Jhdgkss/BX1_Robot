#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

try:
    import msgpack
except Exception as exc:
    print(f"RESULT: FAIL - msgpack unavailable: {exc}")
    raise SystemExit(2)

SOCKET_PATH = os.environ.get("BX1_ROUTER_SOCKET", "/var/run/arduino-router.sock")


def rpc_call(method: str, args=None, timeout: float = 2.5):
    args = [] if args is None else args
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
            for message in unpacker:
                if (
                    isinstance(message, (list, tuple))
                    and len(message) >= 4
                    and message[0] == 1
                    and message[1] == msgid
                ):
                    if message[2] is not None:
                        raise RuntimeError(str(message[2]))
                    return message[3]

    raise TimeoutError(f"timeout waiting for {method}")


if not Path(SOCKET_PATH).exists():
    print(f"RESULT: FAIL - router socket missing: {SOCKET_PATH}")
    raise SystemExit(1)

try:
    result = rpc_call("bx1_ping")
except Exception as exc:
    print(f"RESULT: FAIL - {exc}")
    raise SystemExit(1)

print(f"RESULT: PASS - {result}")
raise SystemExit(0)
