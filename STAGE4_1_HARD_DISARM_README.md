# BX1 / LEO Stage 4.1 - Hard DISARM + PC Balance Control

## Safety change

DISARM no longer relies on controller output becoming zero. The STM32 now:

1. invalidates any in-flight 100 Hz balance cycle;
2. sends zero-speed commands to both wheel drives;
3. sends MKS F7 emergency-stop to both addresses;
4. repeats the stop sequence;
5. sends F3=0 to disable both MKS drive outputs.

ARM performs all IMU/zero/arm-window safety checks first, then explicitly enables
both drives and reapplies SR_OPEN / 1800 mA immediately before arming.

Linux `BalanceController.disarm()` also reads actual MKS speed from both drives.
The PC receives `safety_stop_verified=true` only when:

- `armed == false`
- controller `output_rpm == 0`
- left actual RPM is within +/-1 RPM
- right actual RPM is within +/-1 RPM

If verification fails the GUI must instruct the operator to cut motor power.

## PC commands

- `balance.arm`
- `balance.disarm`
- `balance.status`

Remote ARM is enabled in Stage 4.1, but the MCU still rejects ARM unless the IMU
is healthy, axis mapping is confirmed, upright zero is valid, no blocking fault
exists and LEO is inside the arm window.

## Bench test

Keep wheels off the floor for the first test. Arm, create a small correction,
then DISARM. Both wheels must stop on the first DISARM. Repeat at least 10 times.
