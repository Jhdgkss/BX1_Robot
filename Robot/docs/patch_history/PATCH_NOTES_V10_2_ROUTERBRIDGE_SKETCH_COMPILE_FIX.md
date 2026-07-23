# BX1 Body Client v10.2 - RouterBridge / MCU Sketch Compile Fix

This release fixes the MCU sketch compile failure seen on UNO Q.

## Fixed

- `sketch/sketch.yaml` no longer forces `Arduino_RouterBridge (0.4.1)`.
- It now uses `Arduino_RouterBridge (0.4.2)`, matching the Zephyr platform requirement.
- The MCU sketch no longer includes `Arduino_Modulino.h`.
- The Modulino Movement IMU is read using `Arduino_LSM6DSOX` directly.
- This avoids the umbrella `Arduino_Modulino.h` dependency chain that pulled in `vl53l4cd_class.h`.
- Added:
  - `tools/compile_mcu_sketch.sh`
  - `tools/upload_mcu_sketch.sh`

## Recommended commands

```bash
cd ~/Arduino_Q_Client_V1

bash tools/install_on_uno_q.sh
bash tools/compile_mcu_sketch.sh
bash tools/upload_mcu_sketch.sh 192.168.68.54
```

Then restart the web app:

```bash
pkill -f "python.*main.py" 2>/dev/null || true
./START_BX1_WEB.sh
```

## Hardware model remains

- Main NeoPixel bus on D3.
- Human LED addresses:
  - Mouth = LED 1
  - Left eye = LED 2
  - Right eye = LED 3
- Servos:
  - Yaw = D5
  - Pitch = D6
  - Roll = D9
- Modulino Movement:
  - I2C/Qwiic, LSM6DSOX, expected address 0x6A.
- RS485 closed-loop steppers remain as future placeholders.
