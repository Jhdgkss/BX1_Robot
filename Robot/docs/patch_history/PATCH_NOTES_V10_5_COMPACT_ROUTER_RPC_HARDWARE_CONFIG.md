# BX1 Body Client v10.5 - Compact Router RPC Hardware Config

This release fixes the v10.4 Apply Registry failure:

`router_rpc: [6, 'message size exceeds the limit']`

## Cause

The web app was sending the whole flattened hardware registry as one JSON string through `bx1_set_command`.
The UNO Q RouterBridge path works, but the single message was too large for the RPC message limit.

## Fixed

The Python bridge now applies hardware configuration as several tiny RPC calls:

- `bx1_config_led_bus(pin, count, brightness_limit)`
- `bx1_config_led_zone(zone, start_led, end_led)`
- `bx1_config_servo(name, pin, min_deg, home_deg, max_deg, invert)`
- `bx1_config_done()`

The MCU sketch now provides those functions through `Bridge.provide()`.

Normal action commands remain logical:

- `set_led_zone`
- `set_head_pose`
- `drive`
- `stop_motion`

## Required steps

Because the MCU sketch changed, you must compile and upload v10.5:

```bash
cd ~/Arduino_Q_Client_V1
bash tools/install_on_uno_q.sh
bash tools/compile_mcu_sketch.sh
arduino-cli upload -p 192.168.68.54 --fqbn arduino:zephyr:unoq sketch
```

Then test:

```bash
.venv/bin/python tools/check_mcu_router_bridge.py
```

Then restart web:

```bash
bash tools/force_restart_web.sh
```
