# Hardware mapping notes

## Current supported hardware

### Arduino Modulino Movement

The MCU sketch reads the Modulino Movement using the Arduino Modulino library:

- acceleration: X/Y/Z in g
- gyroscope: roll/pitch/yaw in degrees per second
- calculated tilt estimate: `pitch_deg`, `roll_deg`

The telemetry is exposed to Python using:

```cpp
Bridge.provide("bx1_get_status", bx1_get_status);
```

## Head servos

In `sketch/sketch.ino`, set these only after bench testing:

```cpp
#define HEAD_YAW_SERVO_PIN   -1
#define HEAD_PITCH_SERVO_PIN -1
```

`-1` means disabled.

## Eye LEDs / NeoPixels

Default is disabled:

```cpp
#define BX1_USE_NEOPIXEL 0
```

When wired and the library is installed, set it to `1` and set:

```cpp
#define EYE_PIXEL_PIN 6
#define EYE_PIXEL_COUNT 24
```

## Wheel motors

Wheel drive is intentionally stubbed:

```cpp
#define BX1_ENABLE_DRIVE_OUTPUTS 0
```

Do not enable drive outputs until the real motor driver details are confirmed. For your closed-loop steppers, the correct next step is to add the RS485 command function inside:

```cpp
void applyDrive(float linearMps, float angularDps, float durationS)
```

The Brain App and UNO Q both limit the movement, but the MCU still remains the final authority.


## V9.4 runtime hardware map

The preferred workflow is now:

1. Open the UNO Q web page.
2. Go to **Hardware / GPIO**.
3. Enable one device at a time.
4. Enter the GPIO/pin assignment.
5. Press **Save Hardware Map**.
6. Press **Apply Hardware Map to MCU**.
7. Bench-test that one device.

The saved JSON lives in:

```text
python/config.json
```

The current starter roles are:

| Role | Device | Notes |
|---|---|---|
| `head_yaw` | Servo | Independent head rotation left/right |
| `gimbal_left` | Servo | Left side of the push-pull pitch/roll linkage |
| `gimbal_right` | Servo | Right side of the push-pull pitch/roll linkage |
| `left_eye` / `right_eye` | NeoPixel zones | Individually addressable eye zones on the shared LED bus |
| `mouth` | NeoPixel zone | Mouth zone; audio-reactive while talking |
| `chest` / `status` | NeoPixel zones | Optional state/status lighting |

The MCU action packet for head movement supports:

```json
{"type":"set_head_pose","args":{"yaw_deg":0,"pitch_deg":0,"roll_deg":0}}
```

The MCU action packet for LEDs supports:

```json
{"type":"set_led","args":{"target":"eyes","colour":"blue","brightness":0.4}}
```

Targets can be `eyes`, `mouth`, or `all`.

NeoPixel support requires the Adafruit NeoPixel library. If the sketch fails to compile because `Adafruit_NeoPixel.h` is missing, install that library or temporarily set:

```cpp
#define BX1_USE_NEOPIXEL 0
```


## v10.21 mixed head kinematics

`pitch_deg` and `roll_deg` are logical axes. They are not mapped one-to-one to physical servos. The MCU mixes both values into `gimbal_left` and `gimbal_right` using configurable gains and signs. Calibrate physical homes/limits before attaching the linkage rods or use the ±3° bench-test buttons.

LED state colours are edited on the **LED States** page. Each state can define a separate `#RRGGBB` colour and brightness for every zone.
