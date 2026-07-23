#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "python" / "config.json"

def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["hardware_registry"] = {
        "schema": "bx1.hardware_registry.v1",
        "led_buses": {"main": {"label": "Main addressable LED chain", "type": "neopixel", "enabled": True, "data_pin": 3, "total_pixels": 100, "brightness_limit": 0.20, "colour_order": "GRB", "human_addressing": True}},
        "led_zones": {
            "mouth": {"label": "Mouth", "bus": "main", "enabled": True, "start": 1, "end": 1, "default_colour": "cyan", "brightness": 0.20},
            "left_eye": {"label": "Left eye", "bus": "main", "enabled": True, "start": 2, "end": 2, "default_colour": "blue", "brightness": 0.25},
            "right_eye": {"label": "Right eye", "bus": "main", "enabled": True, "start": 3, "end": 3, "default_colour": "blue", "brightness": 0.25},
            "chest": {"label": "Chest / status", "bus": "main", "enabled": False, "start": 4, "end": 19, "default_colour": "cyan", "brightness": 0.20},
            "status": {"label": "Status strip", "bus": "main", "enabled": False, "start": 20, "end": 29, "default_colour": "amber", "brightness": 0.20}
        },
        "servos": {
            "head_yaw": {"label": "Head rotation / yaw", "enabled": False, "pin": 5, "min_deg": -20, "home_deg": 0, "max_deg": 20, "invert": False, "speed_deg_s": 90},
            "head_pitch": {"label": "Head up/down / pitch", "enabled": False, "pin": 6, "min_deg": -10, "home_deg": 0, "max_deg": 10, "invert": False, "speed_deg_s": 90},
            "head_roll": {"label": "Head tilt / roll", "enabled": False, "pin": 9, "min_deg": -10, "home_deg": 0, "max_deg": 10, "invert": False, "speed_deg_s": 90}
        },
        "sensors": {"modulino_movement": {"label": "Arduino Modulino Movement IMU", "enabled": True, "bus": "i2c_qwiic", "i2c_address": "0x6A", "use_for": ["pitch", "roll", "gyro", "motion_awareness"]}},
        "drive_buses": {"rs485_wheels": {"label": "Future RS485 closed-loop wheel steppers", "enabled": False, "adapter": "usb_rs485_or_uart_rs485", "port": "", "baud": 115200, "left_motor_id": 1, "right_motor_id": 2, "max_linear_mps": 0.25, "max_angular_dps": 60, "safety_timeout_ms": 500}}
    }
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("Configured BX1 v10 hardware registry:")
    print(" - Main NeoPixel bus: D3, 100 pixels")
    print(" - Mouth: LED 1")
    print(" - Left eye: LED 2")
    print(" - Right eye: LED 3")
    print(" - Servos planned: yaw D5, pitch D6, roll D9, disabled until bench tested")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
