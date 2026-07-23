# BX1 hardware-control architecture — v10.37

1. Desktop Brain owns conversation, personality, web access and TTS.
2. UNO Q Linux owns hardware configuration and high-level behaviour in Python.
3. STM32 MCU runs a small Arduino/Zephyr RouterBridge shim for deterministic PWM, NeoPixel timing and Qwiic reads.
4. Modulino Movement is read on `Wire1` at `0x6A`.
5. Wheel outputs remain disabled and unarmed.

UNO Q's supported App Lab model currently pairs Linux Python with an Arduino sketch on the STM32 MCU. v10.37 therefore keeps changeable logic in Python and reduces the sketch to an I/O/RPC shim. `mcu_micropython/` is the migration target for a future supported MicroPython MCU runtime or a separate MicroPython controller.
