#!/usr/bin/env python3
from __future__ import annotations

import glob
import json
import os
import sys
import time

try:
    import serial
except Exception as exc:
    print(f"ERROR: pyserial is not installed: {exc}")
    print("Run: .venv/bin/pip install pyserial")
    raise SystemExit(2)

PORTS = []
if os.environ.get("BX1_MCU_SERIAL_PORT"):
    PORTS.append(os.environ["BX1_MCU_SERIAL_PORT"])
for pat in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*", "/dev/ttyAMA*"):
    PORTS.extend(sorted(glob.glob(pat)))
# de-dupe
PORTS = list(dict.fromkeys(PORTS))

print("BX1 MCU Serial Bridge Check")
print("=" * 36)
print("Candidate ports:", PORTS or "none")

if not PORTS:
    print("RESULT: FAIL - no serial ports found")
    raise SystemExit(1)

for port in PORTS:
    print(f"\nTrying {port}...")
    try:
        with serial.Serial(port, 115200, timeout=2, write_timeout=2) as ser:
            time.sleep(1.8)
            ser.reset_input_buffer()
            ser.write(b"BX1_STATUS\n")
            ser.flush()
            deadline = time.time() + 4.0
            lines = []
            while time.time() < deadline:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                lines.append(line)
                print("  RX:", line[:200])
                if line.startswith("BX1_STATUS:"):
                    payload = line[len("BX1_STATUS:"):]
                    try:
                        data = json.loads(payload)
                        print("\nRESULT: PASS")
                        print("Port:", port)
                        print(json.dumps(data, indent=2))
                        raise SystemExit(0)
                    except Exception as exc:
                        print("RESULT: FAIL - status was not valid JSON:", exc)
                        raise SystemExit(1)
            print("  Timeout. Last lines:", lines[-5:])
    except SystemExit:
        raise
    except Exception as exc:
        print("  Failed:", exc)

print("\nRESULT: FAIL - no MCU responded to BX1_STATUS")
raise SystemExit(1)
