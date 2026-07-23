# BX1 Body Client v10.0 - Hardware Registry / LED Zone Map

This release replaces the old one-function-one-pin GPIO table with a proper hardware registry.

## Key changes

- One addressable LED bus can now host many logical robot zones.
- Default LED bus: Arduino D3, 100 pixels, brightness limit 0.20.
- Default zones use human-friendly LED addresses:
  - Mouth: LED 1
  - Left eye: LED 2
  - Right eye: LED 3
  - Chest/status: LED 4-19, disabled by default
  - Status strip: LED 20-29, disabled by default
- Servos are separate devices with their own pins and movement limits:
  - Head yaw: D5, disabled by default
  - Head pitch: D6, disabled by default
  - Head roll: D9, disabled by default
- Modulino Movement is listed as an I2C/Qwiic sensor at 0x6A.
- Future RS485 closed-loop wheel steppers are represented as a drive bus placeholder.

## Important

The Linux web app can save the registry immediately. Physical output still requires the MCU sketch to be uploaded and the UNO Q Linux-to-MCU bridge to be available.

The current UNO Q appears as a network board, not a /dev/ttyACM serial device, so RouterBridge / Arduino App Lab is the preferred bridge path for physical MCU I/O.
