# BX1 Body Client v10.4 - Router RPC Python Bridge

This release fixes the remaining reason why the web app could save hardware settings but could not drive LEDs/servos.

## Problem

The v10.3 MCU sketch compiles and uploads, but the Linux web app was still trying:

1. Arduino App Lab Bridge import
2. Serial fallback on `/dev/ttyACM*`

On UNO Q under SSH/systemd, the board commonly does not expose a local `/dev/ttyACM*` MCU serial port. The correct runtime path is the `arduino-router` Unix socket:

`/var/run/arduino-router.sock`

## Fixed

- Added `msgpack>=1.0.8` to `python/requirements.txt`.
- Added Router RPC support to `python/hardware_bridge.py`.
- Bridge priority is now:
  1. App Lab Bridge
  2. Router RPC via `/var/run/arduino-router.sock`
  3. Legacy serial fallback
- Added `tools/check_mcu_router_bridge.py`.

## Test

```bash
cd ~/Arduino_Q_Client_V1
bash tools/install_on_uno_q.sh
.venv/bin/python tools/check_mcu_router_bridge.py
```

If it passes, restart the web app:

```bash
bash tools/force_restart_web.sh
```

Then Hardware / GPIO should be able to apply registry and drive:

- Mouth LED zone on D3 LED 1
- Eyes zones on D3 LEDs 2 and 3
- Servos on D5/D6/D9 once enabled
- Modulino Movement telemetry once IMU is producing data
