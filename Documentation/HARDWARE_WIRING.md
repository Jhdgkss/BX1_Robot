# Hardware Wiring and Provisional Allocation

Documented only; this file does not enforce or reconfigure GPIO.

| Interface | Allocation | Status |
|---|---|---|
| D3 | Addressable LED chain | Existing configured use |
| D9 | Head yaw servo | Existing configured use |
| D10 | Left neck/gimbal servo | Existing configured use |
| D11 | Right neck/gimbal servo | Existing configured use |
| I2C SDA/SCL (UNO Q Qwiic / `Wire1`) | Modulino Movement; proposed ToF sensor | IMU active, ToF uncommissioned |
| UART TX/RX | Proposed RS485 interface | Uncommissioned |
| One spare GPIO | Proposed RS485 DE/RE when manual direction is required | Unallocated |

The active IMU firmware expects an LSM6DSOX at `0x6A`, with `0x6B` accepted as a
secondary address. Confirm ToF address compatibility before connecting both.

## Unresolved before RS485 work

- Exact Makerbase driver model and protocol version.
- RS485 converter chip and logic voltage.
- Automatic or manual direction switching.
- Final A/B terminal polarity.
- Motor addresses.
- Bus baud rate, parity and stop bits.
- Whether RS485 update latency is adequate for balancing.

Wheel power and balance control remain outside this phase.
