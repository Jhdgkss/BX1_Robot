# BX1 OS v0.11.0 — Stable Live UI and MCU Foundation

The management UI renders a route once. Background telemetry updates bound
values and status indicators without replacing the active route, preserving
focus, dirty fields, sliders, recording progress and pending actions.

The MCU foundation is MicroPython-only and telemetry-only. The versioned
`bx1.mcu.v1` line protocol carries hello, heartbeat, status, I2C scan and IMU
sample frames. Safe startup inhibits wheels, RS485 transmit and servos. The
Robot Body owns the single MCU bridge and reconnects with bounded retries.

The Modulino Movement adapter reports detection, address, sample rate, raw
acceleration/angular-rate values and stale/error state. RS485 is discovery and
counter telemetry only; no motor command is emitted in this release.

Management endpoints are `/api/mcu/status`, `/api/mcu/rs485`, and the scoped
POST commands under `/api/mcu/` (`reconnect`, `request-status`, `scan-i2c`,
`start-imu-telemetry`, `stop-imu-telemetry`, and `clear-diagnostic-fault`).
