# BX1 touchscreen orientation fix — v10.43

The screen image and touch controller are separate devices. Rotating only the
screen leaves the touch coordinates in their original orientation, so a finger
movement appears at the wrong angle and buttons cannot be selected.

Version 10.43 reads the current xrandr screen rotation and applies the matching
Coordinate Transformation Matrix to the detected touchscreen. Detection uses
udev's `ID_INPUT_TOUCHSCREEN=1` property first, with common controller names as
a fallback. Calibration runs at every kiosk start.

Runtime configuration is stored in:

```text
/home/arduino/Arduino_Q_Client_V1/runtime/touchscreen.env
```

Recommended settings:

```text
BX1_TOUCH_ROTATION=keep
BX1_TOUCH_INPUT_ROTATION=auto
BX1_TOUCH_OUTPUT=auto
BX1_TOUCH_DEVICE=auto
```

Manual commands:

```bash
cd /home/arduino/Arduino_Q_Client_V1
DISPLAY=:0 tools/bx1_touchscreen_calibrate.sh --list
DISPLAY=:0 tools/bx1_touchscreen_calibrate.sh --rotation auto
```

If automatic orientation is 90 degrees the wrong way, test one explicit value:

```bash
DISPLAY=:0 tools/bx1_touchscreen_calibrate.sh --rotation right
DISPLAY=:0 tools/bx1_touchscreen_calibrate.sh --rotation left
```
