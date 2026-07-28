# BX1 Production Reconciliation — 2026-07-28

## Result

The tracked Robot Body active/support source now matches the read-only
production baseline at `/home/arduino/Arduino_Q_Client_V1`, version `10.39`.
The normalized manifest comparison reports zero missing, extra or changed
paths.

This reconciliation changed Git only. It did not deploy or copy files to the
robot, change a service, start or stop a process, open a listener, flash the
MCU, or modify machine configuration.

## Source boundaries

| Role | Canonical source |
|---|---|
| Production Robot Body | Reconciled tracked active/support files under `Robot/`, identified by `Robot/VERSION.txt` and the production baseline manifest |
| BX1 supervisory OS | `Robot/python/bx1.py`, `bx1_core/`, `bx1_management/`, `hardware_services/`, Alpha service/configuration and deployment tools |
| Machine configuration | Untracked local `Robot/python/config.json`, `robot_profile.json` and `user_settings.json` |
| Historical or staged material | `Body_*`, `payload*`, `update_files/`, legacy launchers and the v1.0.0 camera patch package |

## Imported production baseline

The non-private content differences found by the audit were reconciled from the
live version `10.39` installation:

- `python/camera_io.py`
- `python/config.example.json`
- `python/config.fresh.json`
- `python/hardware_bridge.py`
- `python/hardware_doctor.py`
- `python/main.py`
- `python/web_control.py`
- `service/bx1-web.service`
- `sketch/sketch.ino`
- `tools/check_web_health.sh`
- `tools/install_bx1_web_service.sh`
- `VERSION.txt`

`python/config.json` was deliberately not imported. Its local copy was
preserved and removed from Git authority.

## Evidence

The redacted baseline is
`Documentation/production-baselines/BX1_ROBOT_BODY_v10.39_20260728.manifest.json`.
It records SHA-256, normalized deployable mode, size and source classification
for 376 non-private files. Twenty-five private paths were excluded before
hashing. The manifest contains no file contents or private values.

Comparison classes `active,support`:

| Measure | Result |
|---|---:|
| Version | `10.39` = `10.39` |
| Missing paths | 0 |
| Extra paths | 0 |
| Changed paths | 0 |
| Match | true |

## Remaining gates

The v1.0.0 camera patch remains a staged historical artefact. It was generated
against the pre-reconciliation Git runtime, not the verified live `main.py` and
`web_control.py`, and must not be deployed. A replacement patch must be
generated from this baseline and qualified independently.

The current Alpha release remains a canary, not a completed production kernel.
Its next official package must be built from a clean, reviewed, correctly
tagged commit; pass package reconstruction, install-only, rollback and
observer-isolation validation; and preserve the production service and port
8088. Hardware commissioning and any boot-time activation remain separate
approval gates.
