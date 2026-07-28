# BX1 Implementation Roadmap

Every gate requires review before proceeding. Existing voice, UI and body
functionality is a regression baseline throughout.

## 1. Baseline and documentation

- Scope: current-system map, wiring record, audio baseline and read-only IMU evidence.
- Likely files: `Documentation/*`, `Robot/tools/*`, active MCU telemetry sketch.
- Tests: offline unit/import tests, current non-destructive suites, diagnostic dry runs.
- Acceptance: maps name actual code; paired audio WAV/JSON; IMU scan/sample report.
- Risks: microphone ownership conflict; confusing legacy and active sketch copies.
- Disabled: wheels, balance, RS485 writes, firmware auto-flash, automatic gain.

## 2. IMU repair and deterministic sensor service

- Scope: verify active repair on hardware; timestamped fixed-rate sampling and fault state.
- Likely files: `Robot/sketch/sketch.ino`, `hardware_bridge.py`, tests.
- Tests: I2C scan, rate/jitter/stale/fault-injection and axis-orientation checks.
- Acceptance: stable reviewed sample rate, explicit init/read faults, known axis mapping.
- Risks: bus contention, cable/power faults and wrong orientation.
- Disabled: balance and wheel output.

## 3. Shared Brain/Robot protocol

- Scope: versioned commands, telemetry, acknowledgements, IDs and compatibility rules.
- Likely files: `Brain/bx1_modules/bx1_protocol.py`, Robot client/main and contract docs.
- Tests: schemas, malformed/stale/duplicate commands and version negotiation.
- Acceptance: both sides reject incompatible or invalid packets explicitly.
- Risks: breaking existing Brain communication.
- Disabled: new motion execution.

## 4. Robot safety state machine

- Scope: boot, safe, degraded, maintenance, estop and command-timeout states.
- Likely files: MCU sketch, Robot safety/config/telemetry modules.
- Tests: transitions, watchdogs, reset/estop and sensor-loss simulation.
- Acceptance: motion cannot arm without all prerequisites; faults are latched/observable.
- Risks: unsafe transition or hidden fallback.
- Disabled: physical wheel commands.

## 5. RS485 converter and Makerbase bench-test driver

- Scope: identify hardware/protocol and test one disconnected or unloaded driver.
- Likely files: new Robot MCU RS485 driver, config and bench tool.
- Tests: electrical levels, direction timing, framing, CRC, timeout and read-only queries.
- Acceptance: documented converter/driver/protocol and repeatable no-load exchange.
- Risks: voltage, polarity, bus collision and unintended motor motion.
- Disabled: chassis-mounted drive, balancing and automatic deployment.

## 6. Dry-run balance controller

- Scope: controller consumes recorded/live IMU and produces logged commands only.
- Likely files: Robot controller/simulation modules and telemetry.
- Tests: replay, saturation, timing jitter, sensor dropout and sign conventions.
- Acceptance: deterministic bounded outputs with zero motor transport.
- Risks: wrong gains, axes, signs or timing assumptions.
- Disabled: RS485 transmit and motor enable.

## 7. Restrained physical balance testing

- Scope: reviewed controller on a mechanically restrained chassis with human estop.
- Likely files: approved gains/config and test procedure.
- Tests: low-authority staged energisation, timeout, estop and sensor-loss trials.
- Acceptance: signed test record and safe shutdown in every injected fault.
- Risks: high-current motion, falls and mechanical injury/damage.
- Disabled: autonomous/unrestrained movement.

## 8. ToF sensor integration

- Scope: commission eye sensor on shared I2C, address and rate management.
- Likely files: MCU sensor service, wiring/config and telemetry.
- Tests: coexistence scan, range/invalid/stale tests and IMU jitter regression.
- Acceptance: reliable distance telemetry without degrading IMU service.
- Risks: I2C address/pull-up/contention and field-of-view errors.
- Disabled: automatic navigation response.

## 9. Active head scanning

- Scope: bounded scan behaviours using distance/vision goals.
- Likely files: Brain goals; Robot head command validator and behaviour scheduler.
- Tests: soft limits, rate/timeout, collision envelope and D9 audio-noise regression.
- Acceptance: safe interruptible scans within calibrated limits.
- Risks: linkage collision and yaw-servo microphone interference.
- Disabled: wheel following.

## 10. Brain world model and navigation skills

- Scope: fuse perception into a world model and issue high-level navigation goals.
- Likely files: Brain perception/memory/skill modules and shared protocol.
- Tests: simulation, stale-world handling, contradictory observations and safe rejection.
- Acceptance: explainable goals; Robot remains final safety authority.
- Risks: perception error and stale or overconfident planning.
- Disabled: unsupervised physical navigation until separately approved.
