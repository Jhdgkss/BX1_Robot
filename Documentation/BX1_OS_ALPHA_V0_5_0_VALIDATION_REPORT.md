# BX1 OS Alpha v0.5.0 Validation Report

## Result

Release validation was performed offline against mocked camera and Robot Body
surfaces. No robot or physical camera was accessed. The relevant Python suite
completed with 186 passing tests and one Windows-only symlink test skipped
because directory symlink creation was unavailable. The phase-one diagnostic
also passed.

## Safety validation scope

- cached-only Robot Body snapshot and MJPEG paths;
- BX1 OS allowlisted loopback proxy and timeout handling;
- malformed, unavailable and stale frames;
- browser disconnect and stream-gate cleanup;
- camera node grouping and internal-device filtering;
- no camera node opens, capture creation or camera-setting writes;
- read-only HTTP method enforcement;
- port 8088 and deployment rollback compatibility;
- UI loading, offline, stale, pause, resume and reconnect framework;
- CPU, frame-size, frame-rate and queue limits.

## Validation commands

```text
python Robot/tools/test_camera_preview_integration.py
python Robot/tools/test_hardware_audio_integration.py
python Robot/tools/test_management_interface.py
python Robot/tools/test_bx1_core_telemetry.py
python Robot/tools/test_deployment_system.py
python -m compileall -q Robot/python Robot/tools
python -m json.tool Robot/python/config.alpha-qualification.json
bash -n Robot/tools/deploy_bx1_os.sh
bash -n Robot/tools/rollback_bx1_os.sh
bash -n Robot/tools/run_bx1_os_management.sh
git diff --check
```

## Release artifact verification

Clean-state packaging is the final release step. The generated sidecar manifest
and final release report are the authoritative record for the commit, tag,
SHA-256 and payload count because embedding an archive's own checksum inside its
payload would be self-referential.

The packaging gate requires:

- `source_worktree_dirty: false`;
- `source_git_tag: BX1_OS_ALPHA_v0.5.0`;
- every payload SHA-256 to verify;
- the archive SHA-256 sidecar to match;
- no `bx1-web.service` unit or legacy installer payload;
- no executable deployment target under
  `/home/arduino/Arduino_Q_Client_V1`; and
- a clean worktree after artifact generation.

Shell syntax was validated with Git for Windows Bash. Visual browser capture was
unavailable in the execution environment; responsive and lifecycle states were
validated through static UI tests.
