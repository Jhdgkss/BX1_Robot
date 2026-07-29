# BX1 OS v0.7.2 Operator Integration

## Touchscreen ownership and target

LEO currently has two kiosk units. `bx1-touchscreen.service` is the active
launcher and points Chromium at the legacy Body URL `http://127.0.0.1:8088`.
`bx1-kiosk.service` is an obsolete auto-restarting unit whose executable is
missing. v0.7.2 ships a replacement `bx1-touchscreen.service` that waits for
`bx1-os-alpha.service` and opens `http://127.0.0.1:8089/dashboard`.

The dashboard retains a clear `Open legacy Robot Body UI (8088)` fallback link.
The obsolete `bx1-kiosk.service` is not altered by the OS installer; retire it
only in an explicitly approved operator-maintenance step.

## Camera evidence and fix

Read-only live checks on 2026-07-29 showed:

- Body `GET /api/camera_snapshot.jpg` returned JPEG HTTP 200.
- OS `GET /api/core/camera/snapshot` returned 502 with
  `robot_body_snapshot_http_404`.
- The OS proxy requested the obsolete `/api/camera/snapshot` Body route.

v0.7.2 changes the OS proxy to the live Body cached-JPEG contract
`/api/camera_snapshot.jpg`. Capture remains exclusively in Robot Body. The
Body does not expose the optional MJPEG route, so the OS stream endpoint still
reports unavailable; the dashboard snapshot preview is the supported path.

## Deployment notes

Install the packaged touchscreen unit, run `systemctl daemon-reload`, then
restart only `bx1-touchscreen.service` in a separately approved maintenance
step. The OS update must not restart `bx1-web.service`; it changes no camera,
Body configuration or hardware control path.
