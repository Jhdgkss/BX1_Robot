# BX1 Body Client v9.9 - Serial MCU Bridge for GPIO/NeoPixel/Servos

This update fixes the next layer after v9.8.

The Hardware/GPIO page can now save the mouth LED as D3, but the physical LED still will not move if the Python web app is running from SSH/systemd because Arduino App Lab Bridge is not available in that runtime.

v9.9 adds a serial fallback bridge:

- Python hardware bridge tries Arduino App Lab first.
- If App Lab is unavailable, it uses pyserial over `/dev/ttyACM*`, `/dev/ttyUSB*`, or `/dev/serial/by-id/*`.
- MCU sketch accepts simple serial commands:
  - `BX1_STATUS`
  - `BX1_ACTION:{json}`
  - `BX1_ESTOP:0/1`
- New diagnostics:
  - `tools/check_mcu_serial_bridge.py`
  - `tools/test_mouth_led_d3.py`

Important: the updated sketch must be uploaded to the Arduino MCU side. The Linux web page alone cannot drive Arduino D3 until the MCU sketch is running.
