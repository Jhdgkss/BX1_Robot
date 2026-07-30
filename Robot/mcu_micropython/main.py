"""BX1 MicroPython telemetry firmware.

Safe-start firmware: no wheel, RS485, servo or LED outputs are enabled.  The
serial protocol remains useful while the Robot Body brings up the MCU.
"""
import sys
import time
import config
from movement_imu import MovementIMU
from protocol import PROTOCOL_VERSION, decode_command, frame

try:
    import machine
except ImportError:
    machine = None

imu = MovementIMU()
sequence = 0
boot_ms = time.ticks_ms()
imu_enabled = False
sample_rate_hz = max(1, min(100, int(getattr(config, "LOOP_HZ", 50))))
last_imu_ms = 0
last_heartbeat_ms = 0
last_status_ms = 0
last_reading = None

def emit(kind, **payload):
    global sequence
    sequence += 1
    sys.stdout.write(frame(kind, sequence, timestamp_ms=time.ticks_ms(), **payload))

def safe_status():
    age = None if last_reading is None else max(0, time.ticks_diff(time.ticks_ms(), last_imu_ms))
    return {
        "firmware_version": "0.11.0-micropython",
        "protocol_version": PROTOCOL_VERSION,
        "uptime_ms": time.ticks_diff(time.ticks_ms(), boot_ms),
        "reset_reason": getattr(machine, "reset_cause", lambda: None)() if machine else None,
        "safe_mode": True,
        "actuator_inhibit": True,
        "rs485_tx_inhibited": True,
        "wheel_commands_enabled": False,
        "servo_commands_enabled": False,
        "heartbeat_sequence": sequence,
        "imu": {
            "detected": bool(imu.sensor), "initialised": bool(imu.sensor),
            "address": hex(getattr(config, "IMU_ADDRESS", 0)),
            "sample_rate_hz": sample_rate_hz, "sample_age_ms": age,
            "sample": last_reading, "error": imu.error or "",
        },
        "rs485": {"available": False, "tx_inhibited": True, "rx_count": 0, "tx_count": 0, "errors": 0},
    }

def handle(command):
    global imu_enabled, sample_rate_hz
    if not command:
        emit("fault", code="malformed_frame", message="invalid JSON object")
        return
    name = str(command.get("command") or command.get("type") or "")
    req = command.get("seq", 0)
    if name in ("identify", "request_status", "status"):
        emit("ack", request_seq=req, command=name, ok=True)
        emit("status", **safe_status())
    elif name == "scan_i2c":
        emit("ack", request_seq=req, command=name, ok=True)
        emit("i2c_scan", addresses=[hex(getattr(config, "IMU_ADDRESS", 0))] if imu.sensor else [], ok=bool(imu.sensor), error=imu.error or "")
    elif name == "start_imu_telemetry":
        imu_enabled = True
        sample_rate_hz = max(1, min(100, int(command.get("sample_rate_hz", sample_rate_hz))))
        emit("ack", request_seq=req, command=name, ok=True, sample_rate_hz=sample_rate_hz)
    elif name == "stop_imu_telemetry":
        imu_enabled = False
        emit("ack", request_seq=req, command=name, ok=True)
    elif name == "set_imu_sample_rate":
        sample_rate_hz = max(1, min(100, int(command.get("sample_rate_hz", sample_rate_hz))))
        emit("ack", request_seq=req, command=name, ok=True, sample_rate_hz=sample_rate_hz)
    elif name in ("enter_safe_mode", "clear_diagnostic_fault"):
        emit("ack", request_seq=req, command=name, ok=True, actuator_inhibit=True)
    else:
        emit("ack", request_seq=req, command=name, ok=False, error="unsupported_command")

imu.begin()
emit("hello", firmware_version="0.11.0-micropython", protocol_version=PROTOCOL_VERSION, safe_mode=True, actuator_inhibit=True)
emit("status", **safe_status())

while True:
    now = time.ticks_ms()
    # Non-blocking stdin is not available on every MicroPython port; poll only
    # when select is provided by the board runtime.
    try:
        import uselect
        poll = uselect.poll(); poll.register(sys.stdin, uselect.POLLIN)
        if poll.poll(0):
            handle(decode_command(sys.stdin.readline()))
    except Exception:
        pass
    if time.ticks_diff(now, last_heartbeat_ms) >= 1000:
        last_heartbeat_ms = now
        emit("heartbeat", uptime_ms=time.ticks_diff(now, boot_ms), safe_mode=True, actuator_inhibit=True)
    if imu_enabled and time.ticks_diff(now, last_imu_ms) >= int(1000 / sample_rate_hz):
        last_imu_ms = now
        reading = imu.read()
        if reading is None:
            emit("fault", code="imu_read_failed", message=imu.error or "IMU read failed")
        else:
            last_reading = reading
            emit("imu_sample", sample=reading, sample_rate_hz=sample_rate_hz)
    if time.ticks_diff(now, last_status_ms) >= 5000:
        last_status_ms = now
        emit("status", **safe_status())
    time.sleep_ms(5)
