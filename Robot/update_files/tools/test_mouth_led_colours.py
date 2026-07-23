#!/usr/bin/env python3
"""Cycle BX1 mouth LED 1 through four colours using the repaired web endpoint."""
from __future__ import annotations
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8088"


def post(payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + "/api/hardware_test",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


for name, colour in [("RED", "#ff0000"), ("GREEN", "#00ff00"), ("BLUE", "#0000ff"), ("WHITE", "#ffffff"), ("CYAN", "#00ffff")]:
    result = post({"role": "led_range", "start_led": 1, "end_led": 1, "colour_hex": colour, "brightness": 0.20})
    print(name, json.dumps(result, indent=2)[:1200])
    time.sleep(2)
