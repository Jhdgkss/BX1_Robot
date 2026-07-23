# BX1 Body Client v10.3 - HardwareServo / Zephyr Servo Compile Fix

This release fixes the next MCU compile error:

`fatal error: Servo.h: No such file or directory`

The UNO Q Zephyr core should use `Arduino_HardwareServo`, not the classic AVR-style `Servo.h` library.

## Changes

- Replaced `#include <Servo.h>` with `#include <Arduino_HardwareServo.h>`.
- Replaced `Servo` objects with `HardwareServo` objects.
- Kept the same servo API calls:
  - `attach(pin)`
  - `detach()`
  - `writeMicroseconds(us)`
- Updated `sketch/sketch.yaml` to include:
  - `Arduino_HardwareServo (0.0.1)`
- Updated `tools/compile_mcu_sketch.sh` to install:
  - `Arduino_HardwareServo@0.0.1`
- Updated web/starter version text to v10.3.
- Added `tools/force_restart_web.sh`.

## Install / compile

```bash
cd ~/Arduino_Q_Client_V1

bash tools/install_on_uno_q.sh
bash tools/compile_mcu_sketch.sh
```

If compile succeeds:

```bash
bash tools/upload_mcu_sketch.sh 192.168.68.54
```

Then restart the web app:

```bash
bash tools/force_restart_web.sh
```

## Notes

If upload prompts for a password, use the Linux password for the `arduino` user on BX1.

If upload fails with a missing `.bin`, compile did not succeed first.
