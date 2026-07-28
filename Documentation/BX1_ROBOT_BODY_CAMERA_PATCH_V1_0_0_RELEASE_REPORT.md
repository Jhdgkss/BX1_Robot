# BX1 Robot Body Camera Patch v1.0.0 Release Report

## Purpose

This is a separate, minimal production Robot Body patch supporting BX1 OS Alpha
v0.5.0 safe camera preview. It does not replace or reinstall the Robot Body
project and does not modify BX1 OS.

## Exact production changes

| File | Reason |
|---|---|
| `Robot/python/main.py` | Adds sequence/timing metadata, bounded cached-frame copying, status projection and bounded preview-client accounting around the existing shared JPEG buffer. |
| `Robot/python/web_control.py` | Adds GET-only status, cached snapshot and bounded MJPEG routes. Network transmission occurs after the frame-copy lock is released. |
| `Robot/python/camera_io.py` | Adds metadata-only JPEG dimension parsing without decoding or camera access. |

No service unit, configuration, camera setting, hardware bridge, audio, MCU,
servo, motor, LED, GPIO, Brain or BX1 OS file is part of the production
changed-file payload.

## Endpoint behavior

- `GET /api/camera/status` always returns bounded JSON status.
- `GET /api/camera/snapshot` returns the newest cached JPEG or `503`.
- `GET /api/camera/stream` serves the newest cached JPEG as MJPEG or returns
  `503` when no frame exists.

The implementation:

- never creates `cv2.VideoCapture`;
- never opens `/dev/video0` or `/dev/video1`;
- never changes resolution, frame rate, exposure, focus or format;
- copies immutable frame bytes under a short lock;
- releases the lock before HTTP writes;
- keeps no frame queue;
- caps frames at 2 MiB by default with an 8 MiB hard ceiling;
- caps preview clients at four by default with a hard ceiling of eight; and
- leaves all existing routes and hardware behavior intact.

## Installer and rollback

The installer defaults to dry-run and has fixed targets:

```text
/home/arduino/Arduino_Q_Client_V1
bx1-web.service
8088
```

It verifies exact pre-patch hashes from `BX1_OS_ALPHA_v0.4.0`, backs up the
three files with ownership/mode/hash evidence, stages and compiles replacements,
uses atomic file replacement, restarts only `bx1-web.service`, waits for port
8088 plus `/api/status`, and runs observer-only qualification. A restart or
qualification failure triggers automatic restoration.

Backups are retained under:

```text
/home/arduino/Robot_Body_Camera_Patch_backups/
  <YYYYMMDD_HHMMSS>_ROBOT_BODY_CAMERA_PATCH_v1_0_0/
```

Rollback restores only those three exact files and never writes to
`/home/arduino/BX1_OS`.

## Qualification coverage

Qualification checks:

- production service, UI, port and status health;
- camera status, snapshot and MJPEG behavior;
- MJPEG disconnect cleanup;
- camera device-owner fingerprints and counts;
- unchanged BX1 OS service and port-8089 state;
- microphone, STT and IMU status availability; and
- absence of new active faults.

It requests no servo, motor, speaker, microphone, LED, GPIO, MCU or camera
action.

## Offline validation

The focused suite covers cached-frame absence, valid/stale JPEGs, snapshot,
MJPEG, disconnect, multiple clients, lock release, memory/client bounds,
capture/device/settings prohibition, existing API compatibility, dry-run,
mismatch refusal, backup, automatic rollback, explicit rollback, protected
port/service state and minimal package scope.

Generated artifact hashes, commit identity and exact package file counts are
recorded in the external release manifest, checksum sidecar and final release
response. Generated deployment artifacts remain excluded from Git according to
repository policy.

