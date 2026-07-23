# BX1 MicroPython Hardware Reference

This directory is the editable MicroPython implementation requested for BX1. It separates the IMU, head servos, LEDs, protocol and future wheel interface into small files.

## Important UNO Q limitation

The UNO Q currently exposes its STM32U585 MCU through **Arduino Core on Zephyr** and Arduino Bridge. The supported App Lab pairing is Linux Python plus a small Arduino MCU sketch. Therefore this folder is a reference/portable implementation and is **not flashed by the v10.37 installer**. The running system keeps high-level behaviour, configuration and tuning in Python and uses `sketch/sketch.ino` only as the minimal real-time I/O/RPC shim.

When an officially supported MicroPython/Bridge runtime becomes available for the UNO Q MCU, these modules are the migration target. They can also run on a separate MicroPython-capable controller.

Wheel output is intentionally unarmed.
