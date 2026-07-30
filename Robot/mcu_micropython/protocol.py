"""BX1 MCU line-framed protocol (v1).

Frames are JSON objects terminated by LF.  The MCU never emits actuator
commands; all commands are explicitly diagnostic/telemetry operations.
"""
import json

PROTOCOL_VERSION = "bx1.mcu.v1"

def frame(kind, sequence, **payload):
    value = {"protocol": PROTOCOL_VERSION, "type": kind, "seq": int(sequence)}
    value.update(payload)
    return json.dumps(value, separators=(",", ":")) + "\n"

def encode_status(status, sequence=0):
    value = dict(status or {})
    value.setdefault("protocol", PROTOCOL_VERSION)
    value.setdefault("type", "status")
    value.setdefault("seq", int(sequence))
    return json.dumps(value, separators=(",", ":")) + "\n"

def decode_command(line):
    try:
        value = json.loads(line)
        return value if isinstance(value, dict) else None
    except Exception:
        return None
