# BX1 OS Alpha Deployment Report

## Status

**v0.2.0 MANAGEMENT INTERFACE FRAMEWORK IN DEVELOPMENT**

No robot connection, file transfer, service operation or deployment was
performed while implementing this revision.

## v0.2.0 management milestone

BX1 OS now has a separate management application architecture for port 8089.
The dedicated Alpha service launches `bx1_management`; it does not launch,
import or modify the existing Robot Body web interface. All management actions
remain disabled in this framework release.

## v0.1.1 field finding and v0.1.2 correction

The v0.1.1 qualifier searched only `/proc/<pid>/cmdline`, excluded the PID
returned by `os.getpid()`, and classified any remaining command line containing
the literal Alpha install-root text. The field report exposed only PID 88939,
so its executable, working directory, parent and precise command line were not
recoverable from that report. The classification itself proves that PID 88939
was not equal to the qualifier PID seen by the code and that its command line
contained `/home/arduino/BX1_OS`.

v0.1.2 adds structured, PID-reuse-aware process inspection of `cmdline`, `exe`,
`cwd` and `stat`/parent relationships. It excludes the exact current qualifier
PID. A launcher can be excluded only when the installer passes its exact PID,
the PID is a current ancestor, and its command path identifies the packaged
Alpha deployment launcher. All exclusion and detection reasons are reported.
No process environment or open file descriptor content is read.

Qualification output is now retained in the backup directory and the deployer
prints flushed stage messages plus ten-second qualification heartbeats. The
qualification subprocess has a 180-second timeout with an explicit timeout
failure, while existing systemd, virtual-environment and dependency operations
retain bounded timeouts.

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
  active/enabled states exactly, quarantines failed installations and retains
  the backup evidence directory.

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

- v0.1.1 field qualification: failed on ambiguous process-isolation evidence
- v0.1.1 automatic rollback: observed successful
- v0.1.2 robot files installed: none
- v0.1.2 robot services changed: none
- v0.1.2 robot processes started: none
- Existing service interrupted by this work: no
- v0.1.2 qualification on robot: pending
- v0.1.2 robot staging: prohibited until this release is reviewed
