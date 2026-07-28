# BX1 OS Deployment Guide

## Scope

This is the permanent transactional deployment process for BX1 OS releases.
The first supported milestone is **BX1 OS Alpha**.

Default Robot installation:

```text
/home/arduino/Arduino_Q_Client_V1
```

Default service:

```text
bx1-web.service
```

The service name is retained for compatibility. Its systemd description is
`BX1 OS Alpha Robot Body`.

## Safety guarantees

- Release hashes are verified before backup or installation.
- Deployment cannot start unless the existing `config.json` and service unit
  are present.
- The live service is not stopped until the backup has completed and passed
  archive/config/service validation.
- `config.json`, Brain settings, profiles, calibration, virtual environments,
  runtime data, models, logs and backups are not included in the payload.
- Wi-Fi and NetworkManager configuration are never read or modified.
- Firmware and `Robot/sketch/` are not included.
- Installation is qualified before being declared successful.
- Qualification failure automatically executes rollback.
- Rollback removes only paths listed in the signed-off release manifest before
  restoring the complete pre-deployment program archive.

## Build a release package

From the repository root:

```bash
python Robot/tools/build_bx1_release.py
```

Artifacts are written to `Deployment/`:

```text
bx1-os-alpha-<timestamp>.tar.gz
bx1-os-alpha-<timestamp>.tar.gz.sha256
bx1-os-alpha-<timestamp>.manifest.json
```

The manifest records:

- source Git commit;
- dirty/clean source state;
- creation time;
- every payload path, size, mode and SHA-256;
- protected user paths;
- target service and default installation;
- explicit confirmation that firmware is not included.

A release from a dirty worktree is clearly marked. For production releases,
build from a reviewed, committed tag.

## Transfer to the Robot

Example from a workstation:

```bash
scp Deployment/bx1-os-alpha-<timestamp>.tar.gz \
  arduino@BX1.local:/home/arduino/
scp Deployment/bx1-os-alpha-<timestamp>.tar.gz.sha256 \
  arduino@BX1.local:/home/arduino/
```

On the Robot:

```bash
cd /home/arduino
sha256sum -c bx1-os-alpha-<timestamp>.tar.gz.sha256
tar -xzf bx1-os-alpha-<timestamp>.tar.gz
cd bx1-os-alpha-<timestamp>
```

## Preflight without changes

```bash
./deploy_bx1_os.sh --dry-run
```

This verifies package hashes, install location, preserved configuration and
systemd availability. It does not create a backup, stop a service or copy a
file.

## Deploy

```bash
./deploy_bx1_os.sh
```

For a non-default installation:

```bash
./deploy_bx1_os.sh \
  --install-root /path/to/Arduino_Q_Client_V1 \
  --backup-root /path/to/Arduino_Q_Client_V1/backups \
  --service bx1-web.service \
  --service-user arduino
```

Do not use qualification overrides for the first Alpha deployment. The default
deployment requires the Hardware Bridge and Brain App to be available.

## Backup layout

Before changing the installation, deployment creates:

```text
<install-root>/backups/YYYYMMDD_HHMMSS_ALPHA/
    installation.tar.gz
    configuration/
        config.json
        robot_profile*.json
        *calibration*.json
    systemd/
        bx1-web.service
        bx1-web.service.d/       (when present)
    startup/
        main.py
        START_BX1_WEB.sh
        STOP_BX1_WEB.sh
        REPAIR_BX1_STARTUP.sh
        tools/
    deployment_manifest.json
    deployed_release_manifest.json
    qualification_report.json   (after qualification)
    deployment_report.json      (after success)
    rollback_report.json        (only after rollback)
```

`deployment_manifest.json` records the live Git commit, original service path,
service active/enabled state, installation root and saved configuration hash.

The program archive excludes `.venv`, runtime audio, models, logs, existing
backups, `.git` and bytecode. Those paths are not overwritten by deployment and
are not needed to restore the previous program.

## Installation sequence

```text
Verify package
    |
Validate target/config/service
    |
Create and validate backup
    |
Stop bx1-web.service
    |
Install payload (config excluded)
    |
Verify config hash unchanged
    |
Install rendered systemd unit
    |
daemon-reload + enable + restart
    |
Strict qualification
    |
    +-- PASS --> deployment report
    |
    +-- FAIL --> automatic rollback
```

## Qualification

The deployer runs:

```bash
python tools/qualify_bx1_alpha.py \
  --install-root /home/arduino/Arduino_Q_Client_V1 \
  --service-name bx1-web.service \
  --status-url http://127.0.0.1:8088/api/status
```

It verifies:

- BX1 Alpha bootstrap;
- required Service Registry entries and lifecycle;
- cooperative Scheduler activity;
- Event Bus;
- Diagnostics;
- in-memory Communication;
- Health Monitor;
- existing Hardware Bridge availability;
- configured Brain `/api/status`;
- Robot web interface;
- active and enabled existing runtime service.

Qualification is read-only. It does not send motor, servo, LED or firmware
commands.

Maintenance-only overrides exist for offline test environments:

```bash
--allow-hardware-unavailable
--allow-brain-offline
--skip-systemd
--snapshot-file <captured-status.json>
```

These must not be used to declare the first physical Alpha deployment
qualified.

## Manual rollback

Use the backup path printed by deployment:

```bash
./rollback_bx1_os.sh \
  --backup /home/arduino/Arduino_Q_Client_V1/backups/YYYYMMDD_HHMMSS_ALPHA
```

Validate a backup without changing the Robot:

```bash
./rollback_bx1_os.sh --backup <backup-path> --dry-run
```

Rollback:

1. validates the backup manifest, archive, service and release manifest;
2. stops the deployed service;
3. removes only release-manifest files;
4. safely extracts the prior installation;
5. restores the original service file and drop-ins;
6. restores enabled state;
7. restarts the previous service;
8. verifies the preserved configuration hash; and
9. creates `rollback_report.json`.

## Automatic rollback

After changes begin, any shell error, startup failure or failed qualification
invokes the rollback utility automatically. The previous service is restarted.
The backup remains available for manual recovery.

## Recovery if automatic rollback is interrupted

1. Do not delete the backup or extracted release directory.
2. Check the backup:

   ```bash
   ./rollback_bx1_os.sh --backup <backup-path> --dry-run
   ```

3. Run the rollback again without `--dry-run`.
4. Inspect:

   ```bash
   systemctl status bx1-web.service --no-pager -l
   journalctl -u bx1-web.service -n 150 --no-pager
   ```

5. Confirm the configuration checksum against
   `deployment_manifest.json`.

If the deployment shell is unavailable, use the copy inside the extracted
release package. Do not manually delete the installation directory.

## Troubleshooting

### Package verification fails

Re-transfer the archive and checksum. Do not deploy an archive with a hash or
payload mismatch.

### Backup fails

Check free space and ownership:

```bash
df -h /home/arduino
ls -ld /home/arduino/Arduino_Q_Client_V1/backups
```

No installation files have changed at this point.

### Service fails to start

Automatic rollback should run. Preserve:

```text
deployment_manifest.json
qualification_report.json
rollback_report.json
```

Review the service journal and startup report.

### Hardware Bridge qualification fails

Do not bypass it for the first deployment. Check `arduino-router`, the existing
Router RPC socket and the Robot diagnostics page. Deployment does not restart
or reconfigure the MCU.

### Brain qualification fails

Confirm the saved Brain URL, Windows Brain service, API key and network
reachability. Deployment does not change Brain or Wi-Fi settings.

### Web qualification fails

Inspect `bx1-web.service`, port 8088 and the service journal. A failed web check
causes rollback.

## Release governance recommendations

- Build official packages from a clean tagged commit.
- Store the archive, sidecar manifest, checksum and deployment report together.
- Never edit an extracted payload after manifest generation.
- Retain at least the last two qualified backups.
- Test rollback periodically, not only after a failed release.
- Require a stationary/no-motion physical qualification before Beta.
