# BX1 OS Alpha Deployment Report

## Status

**SIDE-BY-SIDE IMPLEMENTATION COMPLETE — ROBOT STAGING PENDING**

No robot connection, file transfer, service operation or deployment was
performed while implementing this revision.

## Corrected architecture

- Live installation remains `/home/arduino/Arduino_Q_Client_V1`.
- Live service remains `bx1-web.service` on port 8088.
- Alpha installs at `/home/arduino/BX1_OS`.
- Alpha uses `bx1-os-alpha.service` on port 8089.
- Default deployment mode is install-only.
- Install-only leaves the Alpha service disabled and inactive.
- Canary mode starts only the Alpha service and never enables it.
- The Alpha release payload excludes `bx1-web.service` and its installer.

## Safety implementation

- Canonical-path guards reject the live root and descendants.
- Reserved service and port guards reject `bx1-web.service` and port 8088.
- Fresh installation creates an isolated virtual environment and reviewed
  secret-free configuration.
- Observer-only runtime blocks hardware bridge, GPIO and actuator ownership.
- Camera, microphone, speech, kiosk, autonomous motion and idle behaviour are
  disabled.
- Baseline and post-install qualification protect the live unit definition,
  sampled live files, service health and port 8088.
- Rollback understands absent/pre-existing directories and units, restores
  active/enabled states exactly, and quarantines failed installations.

## Required robot-side approval gates

1. Read-only SSH baseline.
2. Release checksum verification and deployment dry-run.
3. Install-only deployment.
4. Review install-only qualification report.
5. Separately approve observer-only canary startup.
6. Review canary qualification before any later activation discussion.

Enabling the Alpha unit or replacing/stopping `bx1-web.service` is outside the
Alpha qualification scope and prohibited.

## Deployment outcome

- Robot files installed: none
- Robot services changed: none
- Robot processes started: none
- Existing service interrupted: no
- Qualification on robot: pending
- Rollback on robot: not used
