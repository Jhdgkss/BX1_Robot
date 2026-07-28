# BX1 OS Alpha v0.1.2 Release Notes

BX1 OS Alpha v0.1.2 is a qualification patch for the side-by-side,
install-only deployment introduced in v0.1.1.

## Corrected

- Replaced raw command-line substring process discovery with structured
  `/proc` inspection and canonical path matching.
- Excluded the exact qualifier PID and only a strictly verified current
  deployment-launcher ancestor.
- Added detailed, redacted process evidence and graceful handling of PID races
  and inaccessible `/proc` fields.
- Added an explicit check that the Alpha unit is loaded while remaining
  disabled and inactive after install-only.
- Added visible deployment stages, qualification heartbeat messages, bounded
  qualification execution, and preserved stdout/stderr logs.

## Unchanged safety invariants

- The default remains install-only.
- `/home/arduino/BX1_OS` remains the only Alpha target.
- `bx1-os-alpha.service` remains disabled and inactive after install-only.
- Port 8089 remains unused after install-only.
- `/home/arduino/Arduino_Q_Client_V1`, `bx1-web.service`, and port 8088 remain
  protected live resources.
- Qualification failure still triggers automatic rollback and preserves
  evidence.

Do not deploy this package over the live installation, substitute
`bx1-web.service`, or manually start the Alpha unit during install-only
qualification.
