# BX1 Unified Installation Runbook

This is a controlled production cutover. Do not run the migration until the
preflight report, backup location and release manifest have been reviewed.

## Pre-flight / dry run

```sh
sudo /home/arduino/BX1/current/body/tools/preflight_bx1_unified.sh
sudo /home/arduino/BX1/current/body/tools/migrate_bx1_unified.sh --dry-run --version 0.10.3-voice-stability
```

The dry run performs no writes, service operations or renames.

## Prepare release

```sh
sudo /home/arduino/BX1/current/body/tools/migrate_bx1_unified.sh --prepare-only --version 0.10.3-voice-stability
```

Prepare-only stages files, validates syntax/imports and creates the immutable
release and manifest. It does not switch `current`, install units, stop old
services, or create compatibility links.

## Cutover

```sh
sudo /home/arduino/BX1/current/body/tools/migrate_bx1_unified.sh --version 0.10.3-voice-stability
```

Cutover verifies the backup, stops legacy services and manually launched
management, switches `current`, installs the three supervised units, and runs
automatic validation. A critical validation failure restores the pre-
unification legacy layout from the timestamped backup.

## Legacy-layout rollback

```sh
sudo /home/arduino/BX1/current/body/tools/rollback_bx1_legacy_layout.sh \
  /home/arduino/BX1/backups/pre-unified-<timestamp>
```

This restores the original directories, service units, configuration and
virtual environments from the pre-unification backup.
