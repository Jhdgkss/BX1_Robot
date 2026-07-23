# BX1 V5 body data packet contract

The UNO Q body service sends three independent classes of information to the desktop Brain App.

## 1. Body telemetry

Endpoint:

```text
POST /api/body_state
```

Payload:

```json
{
  "body_state": {
    "robot_id": "BX1",
    "source": "uno_q_robot_body",
    "received_at_robot": "2026-06-19T20:00:00+0100",
    "safety_ok": true,
    "fallen": false,
    "pitch_deg": 0.5,
    "roll_deg": -0.2,
    "yaw_deg": 90.0,
    "battery_v": 12.1,
    "front_distance_mm": 850,
    "camera": {"enabled": true, "device": "/dev/video0", "index": 0},
    "mic": {"voice_enabled": false, "backend": "vosk", "sample_rate": 16000},
    "location": {
      "schema": "bx1.location.v1",
      "mode": "static",
      "site": "workshop",
      "room": "bench",
      "zone": "test_area",
      "map": "default"
    },
    "sensors": {
      "imu_ok": true,
      "mcu_ok": true,
      "pitch_deg": 0.5,
      "roll_deg": -0.2,
      "front_distance_mm": 850,
      "obstacle": false
    }
  }
}
```

## 2. Raw camera frame

Endpoint:

```text
POST /api/vision_frame
```

This sends image data to the Brain App **without** forcing the LLM to analyse it.

```json
{
  "robot_id": "BX1",
  "image_base64": "...jpeg base64...",
  "mime_type": "image/jpeg",
  "body_state": {},
  "metadata": {
    "camera": "/dev/video0",
    "camera_index": 0,
    "captured_at": "2026-06-19T20:00:00+0100"
  }
}
```

## 3. Vision question

Endpoint:

```text
POST /api/vision
```

This sends the image plus a prompt and asks the Brain App vision model to analyse it.

```json
{
  "robot_id": "BX1",
  "message": "What can you see?",
  "image_base64": "...jpeg base64...",
  "body_state": {}
}
```

## Safety rule

The Brain App only returns high-level action packets.  The UNO Q body service validates them again before forwarding anything to the MCU.  The balance controller remains the final authority for wheel movement.
