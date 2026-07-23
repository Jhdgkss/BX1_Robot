# Patch Notes — BX1 UNO Q Body Client v10.21

## Added

- Two-servo push-pull head-gimbal mixer for logical pitch and roll.
- Independent yaw servo remains unchanged.
- Physical left/right gimbal servo pin, home, travel and inversion controls.
- Logical pitch/roll limits, gains and four configurable mixing signs.
- MCU RPCs `bx1_config_head_limits` and `bx1_config_head_mix`.
- MCU telemetry for physical gimbal targets and active mixer configuration.
- Full `#RRGGBB` colour support in MCU LED-zone commands.
- LED state profile editor with colour pickers for every zone and runtime state.
- Automatic LED states for listening, thinking, talking, vision, diagnostics and faults.
- Talking-mouth colour sourced from the user-selected speaking profile.

## Fixed

- Hardware Doctor navigation omitted from the client-side page list.
- Old Arduino App Lab example could retake the MCU after reboot.
- Permanent bridge repair now registers BX1 MCU Runtime as the default app.
- Hardware Doctor can receive narrowly restricted permission to restart `arduino-router` non-interactively.

## Safety

- Drive outputs remain disabled.
- Gimbal bench-test buttons use ±3 degree logical moves.
- Generated diagnostic sketches are still not compiled or flashed autonomously.
- Servo commands now use 1500 µs as neutral at approximately 10 µs/degree, so configured degree limits remain genuine small travel limits rather than being expanded across the entire 900–2100 µs pulse range.
