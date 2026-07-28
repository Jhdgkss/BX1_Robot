# BX1 OS Alpha v0.5.0 Side-by-Side Deployment Guide

## Scope and invariant

BX1 OS Alpha qualification is a separate installation:

```text
Live installation:       /home/arduino/Arduino_Q_Client_V1
Live service:            bx1-web.service
Live port:               8088

Alpha installation:      /home/arduino/BX1_OS
Alpha service:           bx1-os-alpha.service
Alpha qualification port: 8089
```

The Alpha workflow must never replace, stop, restart, enable, disable, rewrite,
or otherwise alter `bx1-web.service` or the live installation. Replacing
`bx1-web.service` during Alpha qualification is explicitly prohibited.

The generated release manifest is marked `side_by_side: true` and contains
only `bx1-os-alpha.service`. The legacy `bx1-web.service` unit and its installer
are excluded from the Alpha payload.

## Deployment modes

The default mode is `--install-only`.

| Mode | Result |
|---|---|
| `--install-only` | Install/update BX1 OS, install its unit, and leave the unit disabled and inactive. This is the default when no mode is supplied. |
| `--no-start` | Explicit synonym for the safe inactive installation result. |
| `--start-canary` | Install/update BX1 OS and manually start `bx1-os-alpha.service` on port 8089. It remains disabled. |

The mode flags are mutually exclusive.

Do not manually start `bx1-os-alpha.service` during install-only deployment or
qualification. Install-only intentionally leaves the unit loaded, disabled and
inactive, with no process under `/home/arduino/BX1_OS` and no listener on 8089.

## Safety guards

Canonical path and reserved-resource checks reject:

- `/home/arduino/Arduino_Q_Client_V1`;
- any path resolving inside that installation, including through a symlink;
- `bx1-web.service`;
- port `8088`;
- unsafe service names and unsafe root paths;
- a backup root inside `/home/arduino/BX1_OS`; and
- a release without the side-by-side manifest marker.

Preflight also requires the existing service and its port 8088 status endpoint
to be healthy. It records the live unit-definition checksum and hashes a fixed
sample of live startup/configuration files.

## Observer-only qualification profile

Fresh installation generates `python/config.json` from the reviewed
`python/config.alpha-qualification.json` template. It contains no API key or
other secret.

Qualification mode:

- binds only to `0.0.0.0:8089`;
- replaces the legacy hardware bridge with a non-owning bridge;
- blocks servo, wheel, LED, GPIO and other actuator commands;
- disables hardware startup application and servo homing;
- disables direct camera capture, microphone, speech, autonomous expression and
  idle life;
- disables kiosk startup;
- uses the new installation's `runtime/`, `logs/`, `cache/` and `runtime/tmp/`;
- uses `/run/bx1-os-alpha/service.pid`; and
- reports observer isolation through `/api/status`.

The systemd unit also uses a private device namespace. v0.5.0 camera preview is
not direct camera access: it proxies cached frames from fixed Robot Body GET
endpoints on loopback port 8088. The Alpha service still cannot see or open
V4L2 nodes. Enabling direct camera or microphone access requires a separately
reviewed configuration and unit change; it is not part of Alpha qualification.
The Alpha installer does not add those GET endpoints to the protected live
installation. If the current Robot Body release does not provide them, schedule
a separate reviewed Body update; the BX1 OS preview will remain safely Offline
until that prerequisite is met.

## Build

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

Official staging packages should be built from a reviewed, clean commit.

## Transfer and verify

v0.5.0 uses the release basename
`bx1-os-alpha-20260728_v0_5_0`. From the repository root:

```bash
scp Deployment/bx1-os-alpha-20260728_v0_5_0.tar.gz \
  Deployment/bx1-os-alpha-20260728_v0_5_0.tar.gz.sha256 \
  arduino@100.72.130.12:/home/arduino/
```

On the robot:

```bash
cd /home/arduino
sha256sum -c bx1-os-alpha-20260728_v0_5_0.tar.gz.sha256
BX1_STAGE="$(mktemp -d /home/arduino/bx1-os-alpha-v0.5.0-staging.XXXXXX)"
tar -xzf bx1-os-alpha-20260728_v0_5_0.tar.gz \
  -C "$BX1_STAGE"
cd "$BX1_STAGE/bx1-os-alpha-20260728_v0_5_0"
```

## Read-only dry run

```bash
./deploy_bx1_os.sh --dry-run --install-only
```

Dry-run verifies the signed payload, canonical safety guards, live service
health, live definition/sample baseline and canary-port state. It creates no
directory, backup, virtual environment, unit, report or process.

## Install-only workflow

```bash
./deploy_bx1_os.sh --install-only
```

The installer:

1. captures the live invariants and any prior Alpha installation/unit state;
2. stages only manifest-listed files;
3. generates the observer-only configuration without secrets;
4. creates `/home/arduino/BX1_OS/.venv`;
5. installs `python/requirements.txt` into that isolated environment;
6. creates separate runtime/log/cache/temp directories;
7. validates `bx1-os-alpha.service` with `systemd-analyze verify`;
8. atomically places the staged installation at `/home/arduino/BX1_OS`;
9. installs only `/etc/systemd/system/bx1-os-alpha.service`;
10. leaves that unit disabled and inactive; and
11. qualifies that port 8089 is unused and no BX1_OS process is running.

The v0.1.2 process check snapshots `/proc`, excludes the qualifier's exact PID,
and records command path, executable, working directory and parent evidence.
It does not exclude unrelated Python, shell, deployment, user or ancestor
processes. A deployment launcher is excluded only when its exact PID is passed
by the installer, it is an ancestor, and its command path is the packaged
`deploy_bx1_os.py` or `deploy_bx1_os.sh`.

Backups live outside the installation:

```text
/home/arduino/BX1_OS_backups/YYYYMMDD_HHMMSS_ALPHA_SIDE_BY_SIDE/
```

Retain the printed backup path.

`--no-start` may be used when an explicit no-start command is preferred:

```bash
./deploy_bx1_os.sh --no-start
```

Before the real install, authenticate sudo separately so an authentication
prompt cannot be mistaken for deployment inactivity:

```bash
sudo -v
./deploy_bx1_os.sh --install-only
```

Verify the expected install-only state:

```bash
test -d /home/arduino/BX1_OS
systemctl show bx1-os-alpha.service -p LoadState -p ActiveState -p SubState
systemctl is-enabled bx1-os-alpha.service
systemctl is-active bx1-web.service
curl --fail --silent http://127.0.0.1:8088/api/status >/dev/null
sudo ss -ltnp | grep -E ':(8088|8089)[[:space:]]'
pgrep -af /home/arduino/BX1_OS || true
```

Expected: Alpha is `loaded`, `inactive/dead`, and `disabled`; the live service
is `active`; 8088 listens; 8089 does not; and `pgrep` prints no Alpha process.
The last deployment output prints the exact backup/report directory.

## Canary workflow

Canary startup is a separate approval gate:

```bash
./deploy_bx1_os.sh --start-canary
```

This performs the same transactional installation and then:

- confirms port 8089 is unused;
- starts only `bx1-os-alpha.service`;
- leaves it disabled;
- queries `http://127.0.0.1:8089/api/status`;
- validates BX1 core services and observer isolation; and
- revalidates the live service, port 8088, unit checksum and file sample.

Useful read-only checks:

```bash
systemctl status bx1-web.service --no-pager -l
systemctl status bx1-os-alpha.service --no-pager -l
systemctl is-enabled bx1-os-alpha.service
curl --fail http://127.0.0.1:8088/api/status
curl --fail http://127.0.0.1:8089/api/status
```

The expected Alpha canary state is `active` and `disabled`.

## Activation gate

Alpha qualification does not authorise boot-time activation or replacement of
the live application. Do not run:

```text
systemctl enable bx1-os-alpha.service
systemctl disable bx1-web.service
systemctl stop bx1-web.service
```

Permanent activation requires a later reviewed migration plan and explicit
approval.

## Rollback

Validate a backup without changes:

```bash
./rollback_bx1_os.sh \
  --backup /home/arduino/BX1_OS_backups/<backup> \
  --dry-run
```

Run rollback:

```bash
./rollback_bx1_os.sh \
  --backup /home/arduino/BX1_OS_backups/<backup>
```

Rollback:

1. validates the v2 backup manifest and dedicated Alpha service name;
2. stops only `bx1-os-alpha.service`;
3. moves the failed/current BX1 OS installation to a timestamped quarantine;
4. restores any previous `/home/arduino/BX1_OS` directory snapshot;
5. removes a newly created Alpha unit or restores a pre-existing Alpha unit;
6. restores the prior Alpha enabled state;
7. restores the prior Alpha active state, leaving inactive units inactive; and
8. writes `rollback_report.json`.

It contains a hard guard against `bx1-web.service`.

Automatic rollback runs on any qualification failure. The backup evidence
directory is retained, including:

```text
deployment_manifest.json
qualification_report.json
qualification_stdout.log
qualification_stderr.log
rollback_report.json
```

Inspect the reports with:

```bash
python3 -m json.tool /home/arduino/BX1_OS_backups/<backup>/qualification_report.json
python3 -m json.tool /home/arduino/BX1_OS_backups/<backup>/rollback_report.json
```

If qualification fails, do not start the Alpha service. Confirm that the
automatic rollback report says `ROLLED_BACK`, recheck the live service and
ports, preserve the entire backup directory, and investigate before retrying.

## Qualification evidence

Install-only qualification checks:

- Alpha unit disabled and inactive;
- port 8089 unused;
- no process running from `/home/arduino/BX1_OS`;
- observer-only configuration active;
- `bx1-web.service` still active;
- port 8088 healthy;
- live unit-definition checksum unchanged; and
- sampled live installation checksum unchanged.

Canary qualification additionally checks BX1 bootstrap, service registry,
scheduler, event bus, diagnostics, in-memory communication, health monitor,
port 8089 status and reported observer-only hardware isolation. Hardware bridge
ownership and actuator access are never required.

## v0.1.2 qualification correction

v0.1.1 recorded only PIDs whose raw command line contained the install-root
text. Its evidence did not include the qualifier PID, parent, executable,
working directory or reason, so a qualification-related PID could not be
distinguished after the event. v0.1.2 retains strict runtime detection while
excluding only the exact current qualifier and a packaged, explicitly
identified current launcher ancestor. It also tolerates `/proc` entries
disappearing or becoming unreadable and records those inspection errors
without aborting the qualifier.

## Troubleshooting

- **Process-isolation match:** inspect `matching_processes`, `match_reasons`,
  command line, executable, working directory and parent in the qualification
  report. Stop only the unrelated Alpha process; never add a broad exclusion.
- **Port 8089 already used:** identify the listener with
  `sudo ss -ltnp 'sport = :8089'`; do not stop port 8088 or the live service.
- **Alpha service active:** run `sudo systemctl stop bx1-os-alpha.service`,
  confirm it is disabled, then repeat the reviewed install-only workflow.
- **Live service unhealthy:** stop Alpha staging work and restore the live
  robot's health through its separately approved operational procedure.
- **Qualification timeout:** inspect the preserved qualification stdout and
  stderr logs. The deployer emits ten-second progress messages and fails the
  qualification after 180 seconds.
- **Rollback failure:** do not delete or move the backup or quarantine
  directories. Capture `systemctl show bx1-os-alpha.service`, both port states,
  and the deployment logs for manual review.

Never use `/home/arduino/Arduino_Q_Client_V1` as the Alpha install root and
never use `bx1-web.service` as the Alpha service name.
