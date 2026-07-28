# BX1 Robot Body Camera Endpoint Patch v1.0.0

This package adds three GET-only cached-frame endpoints to the existing
production Robot Body:

- `GET /api/camera/status`
- `GET /api/camera/snapshot`
- `GET /api/camera/stream`

The endpoint implementation copies the latest shared JPEG while holding the
existing frame lock briefly, releases the lock, and only then writes to the
network. It never creates a capture object, opens a V4L2 node, changes camera
settings, or queues frames.

## Fixed scope

- Target: `/home/arduino/Arduino_Q_Client_V1`
- Service: `bx1-web.service`
- Port: `8088`
- Changed files: `python/main.py`, `python/web_control.py`,
  `python/camera_io.py`

The package does not contain the complete Robot Body project. It never writes
to `/home/arduino/BX1_OS`, changes `bx1-os-alpha.service`, or uses port 8089.

## Transfer and verify

From the repository root:

```bash
scp \
  Deployment/Robot_Body_Camera_Patch/bx1-robot-body-camera-patch-20260728_v1_0_0.tar.gz \
  Deployment/Robot_Body_Camera_Patch/bx1-robot-body-camera-patch-20260728_v1_0_0.tar.gz.sha256 \
  arduino@100.72.130.12:/home/arduino/
```

On the robot:

```bash
cd /home/arduino
sha256sum -c bx1-robot-body-camera-patch-20260728_v1_0_0.tar.gz.sha256
PATCH_STAGE="$(mktemp -d /home/arduino/bx1-camera-patch.XXXXXX)"
tar -xzf bx1-robot-body-camera-patch-20260728_v1_0_0.tar.gz \
  -C "$PATCH_STAGE"
cd "$PATCH_STAGE/bx1-robot-body-camera-patch-20260728_v1_0_0"
```

## Dry run

Dry-run is the default and makes no change:

```bash
./apply_robot_body_camera_patch.sh
./apply_robot_body_camera_patch.sh --dry-run
```

It requires Linux, confirms the fixed production root/service/port, compares
all three installed files against exact reviewed pre-patch SHA-256 values,
checks the existing status endpoint, records camera owners and confirms port
8088. Any unexpected source difference causes refusal.

## Install

Authenticate sudo, repeat dry-run, then explicitly install:

```bash
sudo -v
./apply_robot_body_camera_patch.sh --dry-run
sudo ./apply_robot_body_camera_patch.sh --install
```

The installer creates:

```text
/home/arduino/Robot_Body_Camera_Patch_backups/
  <YYYYMMDD_HHMMSS>_ROBOT_BODY_CAMERA_PATCH_v1_0_0/
```

That directory contains the exact original files, ownership/mode/hash metadata,
the pre-install baseline, staged files, deployment report, qualification report
and—if needed—rollback report. The installer restarts only
`bx1-web.service`. Qualification failure or restart failure automatically
restores the backup.

To install files without restarting production:

```bash
sudo ./apply_robot_body_camera_patch.sh --install --no-restart
```

This validates and installs the files but records qualification as
`pending_restart`. The running process continues serving its previous code until
a separately approved restart.

## Qualification

The normal install qualifies automatically. To repeat qualification, use the
baseline from the reported backup directory:

```bash
sudo ./qualify_robot_body_camera_patch.sh \
  --baseline /home/arduino/Robot_Body_Camera_Patch_backups/<BACKUP>/baseline.json
```

Qualification is observer-only. It performs GET requests, process/file
descriptor inspection and service-state reads. It does not move hardware,
record audio, play sound, send MCU traffic, or open camera devices.

## Rollback

Use the exact backup directory printed by installation:

```bash
sudo ./rollback_robot_body_camera_patch.sh \
  --backup /home/arduino/Robot_Body_Camera_Patch_backups/<BACKUP>
```

Rollback verifies the backup manifest and file hashes, restores the three exact
files with their prior permissions and ownership, validates Python syntax,
restarts only `bx1-web.service`, and verifies port 8088 plus `/api/status`.
BX1 OS files and service state are not modified.

If automatic rollback reports failure, do not make further changes. Preserve
the backup and all JSON reports for review.

