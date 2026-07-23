# Modulino Movement correction — v10.37

The previous sketch used the global `IMU` object on the default I2C bus. v10.37 constructs the LSM6DSOX on UNO Q `Wire1/Qwiic` at `0x6A`, retries discovery every five seconds, exposes the bus/address/error in telemetry, and no longer marks the IMU healthy merely because the MCU bridge is online.

Expected evidence: MCU online, firmware 10.37, IMU bus Wire1/Qwiic, address 0x6A, and changing pitch/roll. Wheel drive remains disabled.
