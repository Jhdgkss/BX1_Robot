# BX1 OS Alpha v0.5.0 Release Notes

## Safe camera preview integration

BX1 OS Alpha v0.5.0 adds a dedicated Camera page for LEO and near-live,
read-only preview through the existing Robot Body camera owner. It preserves the
side-by-side architecture:

- Robot Body: `/home/arduino/Arduino_Q_Client_V1`, `bx1-web.service`, port 8088;
- BX1 OS: `/home/arduino/BX1_OS`, `bx1-os-alpha.service`, port 8089.

No Robot Body page, camera setting, service definition, motor, servo, GPIO or
audio control is changed.

The side-by-side Alpha installer does not patch
`/home/arduino/Arduino_Q_Client_V1`. Therefore, the two reviewed cached-frame
GET endpoints must be delivered through a separate Robot Body release/change
window before the v0.5.0 preview can become available on an existing robot. If
they are absent, BX1 OS stays safe and shows the Camera page as Offline.

## Included

- cached-only Robot Body snapshot and bounded MJPEG GET endpoints;
- fixed-loopback BX1 OS snapshot and stream proxy;
- Camera Core state, health and observer diagnostics;
- responsive Camera page with loading, offline, stale and reconnect states;
- automatic preview pause/resume on page visibility;
- physical camera node grouping and Advanced-only qcom-venus presentation;
- 8 FPS default, 15 FPS ceiling, one-frame queue and 2 MiB frame limit;
- automatic 5 FPS degradation when observed host CPU is at least 85%;
- LEO as the configured robot identity while BX1 remains the OS name;
- deterministic offline tests with mocked Body and hardware surfaces.

## Safety invariants

- Robot Body remains the sole physical camera owner.
- BX1 OS does not open any V4L2 node or create a capture object.
- Proxy upstreams are restricted to fixed GET paths on loopback port 8088.
- The legacy Robot Body UI and its legacy snapshot path are unchanged.
- All BX1 OS write methods remain disabled.
- Install-only remains the deployment default and does not start a service.
- Existing rollback and port-8088 protection remain in force.

## Release identity

- Version: `0.5.0`
- Tag: `BX1_OS_ALPHA_v0.5.0`
- Robot identity: `LEO`
- Deployment: side-by-side, observer-only

See [BX1_OS_CAMERA_INTEGRATION.md](BX1_OS_CAMERA_INTEGRATION.md) for the frame
flow, API schema, limits and failure handling.
