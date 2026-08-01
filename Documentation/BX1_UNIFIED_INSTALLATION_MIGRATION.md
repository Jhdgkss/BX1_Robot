# BX1 Unified Installation Migration Plan

## Target

The robot will have one immutable release root:

```text
/home/arduino/BX1/
  current -> releases/<version>
  releases/<version>/{body,management,shared,manifest.json}
  config/ runtime/ logs/ backups/ staging/
  venvs/{body,management}
```

Robot Body and BX1 Management are released together. Configuration, captures,
logs and runtime state remain outside the release so a rollback does not erase
operator data. The Windows Brain remains separate and is recorded as a
compatible component in `manifest.json`.

## Active-service migration

Replace the historical `bx1-web.service` and `bx1-os-alpha.service` launch
paths with:

- `bx1-body.service` — `/home/arduino/BX1/current/body`
- `bx1-management.service` — `/home/arduino/BX1/current/management`
- `bx1-touchscreen.service` — `/home/arduino/BX1/current/management`

Every unit uses the immutable `current` symlink, external configuration and
external runtime/log paths. Management must be supervised by systemd; manual
`nohup` launch is not part of the target operation.

## Staged migration

1. Run `preflight_bx1_unified.sh` and the migration `--dry-run`; resolve every
   blocking condition before continuing.
2. Confirm the robot backup, service state, ports and one serial/audio owner.
3. Copy both legacy trees into `/home/arduino/BX1/staging/<version>-<timestamp>`.
4. Validate Python syntax using the Body and Management virtual environments.
5. Copy configuration and preserve runtime/log/capture directories outside the
   release.
6. Create the immutable release and `manifest.json` with file hashes.
7. Atomically switch `current` using a temporary symlink and `mv -T`.
8. Install and reload the three supervised units.
9. Create compatibility symlinks only after the release is complete:
   `Arduino_Q_Client_V1 -> BX1/current/body` and `BX1_OS -> BX1/current/management`.
10. Restart Body, Management and touchscreen, then verify ports 8088/8089 and
   health endpoints.

The implementation is [migrate_bx1_unified.sh](../Robot/tools/migrate_bx1_unified.sh).
It is a preparation artifact and has not been run remotely.

The read-only preflight and post-cutover validator are
[preflight_bx1_unified.sh](../Robot/tools/preflight_bx1_unified.sh) and
[validate_bx1_unified.sh](../Robot/tools/validate_bx1_unified.sh).

## Rollback

Select the previous release with:

```sh
sudo /home/arduino/BX1/current/body/tools/rollback_bx1_unified.sh <previous-version>
```

The rollback switches only the `current` symlink and restarts the supervised
services. External configuration, runtime data, logs and recordings remain in
place. The pre-migration legacy trees are retained under the timestamped
backup until explicitly retired.

## Compatibility risks

- Existing scripts and historical documents still contain legacy paths; they
  must be treated as archival or updated to use `BX1_ROOT` before operational
  use.
- Python virtual environments may contain absolute interpreter paths. The
  migration preserves them as separate `venvs/body` and `venvs/management`
  links; rebuilding may be required if the old environments are not portable.
- Configuration files may contain absolute runtime paths and must be reviewed
  before the first release switch.
- The compatibility symlinks are transitional and must not be used as service
  WorkingDirectory values.

## Legacy-path inventory

Active runtime defaults and service templates reference both
`/home/arduino/Arduino_Q_Client_V1` and `/home/arduino/BX1_OS`. Historical
release notes, patch payloads and tests also contain those strings. The
installer and new units use `/home/arduino/BX1`; archival material is not
rewritten in this migration pass.
