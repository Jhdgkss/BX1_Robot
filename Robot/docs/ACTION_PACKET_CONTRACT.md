# BX1 action packet contract

The Brain App returns an `actions` list from `/api/chat` and `/api/vision`.

Example:

```json
{
  "actions": [
    {
      "id": "act_20260617120000_1",
      "schema": "bx1.actions.v1",
      "type": "set_head_pose",
      "args": {"yaw_deg": -35.0, "pitch_deg": 0.0},
      "dry_run": false
    }
  ]
}
```

Supported types:

## `stop_motion`

```json
{"type":"stop_motion","args":{}}
```

Immediately stops wheel movement.

## `drive`

```json
{"type":"drive","args":{"linear_mps":0.15,"angular_dps":0,"duration_s":0.5}}
```

UNO Q validation rejects this unless:

- `motor_armed=true`
- `safety_ok=true`
- robot has not fallen
- speed and duration are within local config limits

## `set_head_pose`

```json
{"type":"set_head_pose","args":{"yaw_deg":35,"pitch_deg":0}}
```

Limits:

- yaw: -60 to +60 degrees
- pitch: -35 to +35 degrees

## `set_eye_led`

```json
{"type":"set_eye_led","args":{"colour":"blue","brightness":0.45,"duration_s":5}}
```

Supported colours in the sketch: red, green, blue, white, amber, yellow, orange, purple, cyan, off.

## `play_tone`

```json
{"type":"play_tone","args":{"tone":"ack","duration_s":0.25}}
```

Uses `BUZZER_PIN` if enabled in the sketch.


## V5 note

The action packet is separate from body telemetry and camera data.  Camera frames and sensor packets are sent to the Brain App first; the Brain App may then return one or more high-level action packets.  The UNO Q body service must continue validating all packets locally before any actuator command reaches the MCU.

## Optional `expression` object from Brain App

The Brain App may also return a top-level `expression` object. This is not a raw actuator command; the UNO Q body client clamps it and converts it into safe LED/head actions.

```json
{
  "speech": "Done. The mouth LED is now doing something useful, for once.",
  "expression": {
    "mood": "dry_humour",
    "mouth_colour": "purple",
    "mouth_brightness": 0.32,
    "eye_colour": "cyan",
    "eye_brightness": 0.22,
    "yaw": 5,
    "pitch": 1.5,
    "roll": -4,
    "nods": 1,
    "duration_s": 4
  },
  "actions": []
}
```

If the Brain App does not return this object, the body client infers a safe expression locally from the spoken reply text.
