# BX1 OS Alpha Deployment Report

## Status

**RELEASE SOURCE READY — ROBOT-SIDE EXECUTION PENDING**

The permanent deployment, rollback and qualification system has been created
and tested locally. Direct access to the BX1 Robot filesystem and systemd is
not available in this workspace, so no files were copied to the Robot and no
service was restarted.

## Source

- Branch: `feature/bx1-os-phase-1`
- Release tag: `BX1_OS_ALPHA_v0.1`
- Source commit: recorded by the generated release manifest
- Source worktree requirement: clean
- Milestone: BX1 OS Alpha

Generated archives, manifests and checksums live under the ignored
`Deployment/` directory. They are built after the release commit is created so
the manifest records the clean release source rather than a pre-commit working
tree.

## Local package verification

- Release:
  `bx1-os-alpha-20260728_alpha1`
- Archive:
  `Deployment/bx1-os-alpha-20260728_alpha1.tar.gz`
- Archive SHA-256: recorded in the generated `.sha256` file
- Manifest:
  `Deployment/bx1-os-alpha-20260728_alpha1.manifest.json`
- Release manifest generation: passed
- Per-file SHA-256 verification: 78/78 passed
- Tamper-detection test: passed
- Firmware included: no
- User `config.json` included: no
- Brain/Wi-Fi/calibration overwrite paths: none

## Robot-side steps remaining

1. Transfer the generated archive and checksum to the Robot.
2. Verify the archive checksum.
3. Extract the release.
4. Run `./deploy_bx1_os.sh --dry-run`.
5. Confirm the Brain App and existing Hardware Bridge are available.
6. Run `./deploy_bx1_os.sh`.
7. Retain the printed backup location and generated reports.

## Deployment outcome

- Backup location: not yet created
- Files installed: none
- Services updated: none
- Qualification: not run on Robot
- Rollback: not used
- Deployment status: pending direct Robot access
