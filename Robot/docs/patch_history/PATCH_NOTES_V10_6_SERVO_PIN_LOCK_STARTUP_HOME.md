# BX1 Body Client v10.6 - Servo Pin Lock + Startup Home

This release fixes two servo workflow issues.

## Fixed

- Hardware / GPIO no longer auto-refreshes over unsaved servo pin selections.
- If you select a servo pin, the form is marked dirty and refresh will not revert it to the saved D5/D6/D9 defaults.
- Saving clears the dirty flag and stores the selected pins.
- Applying the registry now reports that enabled servos have moved to Home.
- The Linux body client automatically applies the saved Hardware Registry on startup once the MCU bridge is ready.
- The MCU `bx1_config_done()` explicitly drives all enabled/attached servos to their configured Home angle.

## Required after install

Because the MCU sketch changed, compile and upload v10.6:

```bash
cd /home/arduino/Arduino_Q_Client_V1
bash tools/install_on_uno_q.sh
bash tools/compile_mcu_sketch.sh
arduino-cli upload -p 192.168.68.54 --fqbn arduino:zephyr:unoq sketch
.venv/bin/python tools/check_mcu_router_bridge.py
bash tools/force_restart_web.sh
```

## Safe first servo test

Enable only one servo first:

- Yaw enabled
- Pin D5, or the actual signal pin you are using
- Min -10, Home 0, Max +10

Then Save Hardware Registry, Apply Registry to MCU, Centre Head, Yaw Left, Yaw Right.
