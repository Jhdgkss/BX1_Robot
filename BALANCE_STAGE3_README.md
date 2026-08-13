# BX1 / LEO Stage 3 - IMU + Local Balance Bench Test

This stage adds the first real balancing controller without auto-starting wheel motion.

## What changed

- Arduino Modulino Movement / LSM6DSOX is restored on the UNO Q MCU.
- IMU is sampled through Arduino's LSM6DSOX library on the UNO Q Qwiic bus.
- A complementary pitch estimate and pitch-rate signal are maintained on the MCU.
- A PD balance loop runs locally at 100 Hz when explicitly armed.
- Balance wheel commands use the existing Makerbase F6 RS485 speed path with no per-command response.
- Startup is always DISARMED.
- An upright `zero` is mandatory before every fresh MCU boot can arm.
- Arm is refused outside ±5 degrees from the captured zero.
- Falling past ±25 degrees automatically disarms and stops the wheels.
- Stale IMU data automatically disarms and stops the wheels.
- While balance is armed, normal RS485 commissioning/readback commands are locked out so a blocking motor read cannot stall the real-time loop.
- `balance_control/balance_test.py` provides bench telemetry, tuning, arm/disarm and CSV capture.

## Important first test

Keep both wheels off the floor.

```bash
cd ~/BX1_Dev
source .venv/bin/activate
python -m balance_control.balance_test
```

Then use this order:

```text
gyrozero
zero
watch 10 0.1
```

Tilt the body slightly forward and backward. Pitch must change smoothly. Next, while the robot is still securely supported and the wheels are free:

```text
arm
```

Only make a very small tilt. The wheels must move in the direction that chases the fall. If they move away from the fall:

```text
DISARM
sign -1
```

Then repeat upright `zero` and the supported arm test.

Do not put the robot on the floor until the correction direction is proven with the wheels clear and the controller can recover small hand-induced tilts without immediately reaching its 120 RPM clamp.

## Initial tuning values

- Kp = 8.0 RPM/degree
- Kd = 0.25 RPM/(degree/second)
- max output = 120 RPM
- hard fall cutoff = 25 degrees
- arm window = 5 degrees

These are intentionally conservative bench values, not claimed final gains.

## Telemetry capture

From the balance console:

```text
capture 15 0.1
```

CSV files are written under `runtime/balance_logs/`. This gives us a reproducible data file for tuning instead of relying on terminal output.

## Stepper motor telemetry capture

The existing commissioning console can now save the motor readback that was previously only printed by `watch`:

```bash
python -m motor_control.manual_motor_test
```

For example, with both wheels still off the floor:

```text
f 60
capture both 5 0.1
stop
```

This writes a CSV under `runtime/motor_logs/` containing actual RPM, robot-signed RPM, angle error, motor state and protection state for both drives. Balance must be DISARMED while this diagnostic readback runs.

## Stage 3.1 IMU discovery update

The MCU now explicitly starts the UNO Q Qwiic bus (`Wire1`) and probes both legal
Modulino Movement LSM6DSOX addresses (`0x6A` and `0x6B`) before initialising the
sensor. The balance console reports the probe results if the IMU cannot start.

The present vertical sensor mounting must be axis-mapped from raw accelerometer
and gyroscope readings before balance is armed. Do not assume the current X/Y/Z
orientation is correct. When the module is later mounted horizontally, update the
orientation mapping and repeat the same raw-axis check.


## Stage 3.2 - measured vertical IMU mapping

Raw commissioning data captured on 2026-08-09 confirmed the current vertical Modulino Movement mounting:

- Robot upright gravity: approximately **sensor -X**.
- Robot fore/aft lean gravity component: **sensor Y**.
- Robot pitch angular-rate axis: **sensor Z**.
- Accelerometer pitch estimate: `atan2(Y, -X)`.
- Gyro pitch rate: `Z`.

Across the supplied two raw runs, accelerometer Y changed by about 0.163 g while Z changed by only 0.039 g, and gyro Z spanned about 18.86 deg/s compared with about 1.10 deg/s on X and 0.92 deg/s on Y. This is sufficiently distinct to confirm the present pitch-axis mapping.

`axis_mapping_confirmed` is therefore true for the **current vertical mounting only**. If the sensor is later rotated to the planned horizontal mounting, set it false, repeat the raw mapping test, update the axes, regenerate the MCU header, and reflash before arming.

The balance controller still always starts DISARMED. The first armed test must be with both wheels clear of the floor so `output_sign` can be verified safely.


## Stage 3.3 gyro calibration fix

Stage 3.3 corrects gyro-zero calibration for the measured vertical IMU mapping.
When `pitch_axis` is `z`, `gyrozero` now averages gyro Z rather than gyro Y.
The controller still starts DISARMED and must be explicitly armed.

For the first motor reaction bench test, keep both wheels clear of the floor, run
`gyrozero`, `zero`, set `maxrpm 40`, verify the robot is within the arm window, then
use `arm`.  While DISARMED, `out` is deliberately forced to 0 RPM.


## Stage 3.4 config validator fix
Linux hardware config validation now accepts pitch_axis z, matching the MCU generator and the measured vertical IMU mapping. No MCU firmware logic change is required for this fix.


## Stage 3.6 measured low-speed resonance map

At SR_OPEN / 1800 mA, the physical wheel tests measured 1-2 RPM smooth, 3-5 RPM jerky (4 RPM worst), and 6 RPM upward smooth. Stage 3.6 therefore preserves 1-2 RPM and maps only the 3-5 RPM band to 6 RPM. Kd remains disabled pending gyro-rate bias correction.
