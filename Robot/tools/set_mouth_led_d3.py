#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
config_path = root / "python" / "config.json"
config = json.loads(config_path.read_text(encoding="utf-8"))
hw = config.setdefault("hardware_map", {})
mouth = hw.setdefault("mouth_led", {
    "label": "Mouth LED strip",
    "role": "mouth",
    "device_type": "neopixel",
})
mouth.update({
    "label": "Mouth LED strip",
    "role": "mouth",
    "device_type": "neopixel",
    "enabled": True,
    "pin": 3,
    "count": 1,
    "brightness": 0.20,
    "colour": "cyan",
})
config["app_version"] = "v9.8-hardware-pin-dropdown-map"
config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
print("Saved mouth LED as NeoPixel on Arduino D3, count=1, brightness=0.20")
print(config_path)
