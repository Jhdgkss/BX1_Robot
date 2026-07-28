#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional


LIVE_ROOT = Path("/home/arduino/Arduino_Q_Client_V1").resolve(strict=False)
LIVE_SERVICE = "bx1-web.service"
DEFAULT_SERVICE = "bx1-os-alpha.service"
SYSTEMD_DIR = Path("/etc/systemd/system")
SAMPLE_PATHS = (
    "main.py",
    "START_BX1_WEB.sh",
    "python/main.py",
    "python/config.json",
)


class RollbackError(RuntimeError):
    pass


class CommandRunner:
    def run(
        self,
        command: Iterable[str],
        *,
        check: bool = False,
        privileged: bool = False,
        timeout: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        cmd = list(command)
        if privileged and os.geteuid() != 0:
            cmd.insert(0, "sudo")
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-1200:]
            raise RollbackError("%s failed: %s" % (" ".join(cmd), detail))
        return result


@dataclass
class RollbackOptions:
    backup_dir: Path
    dry_run: bool = False
    automatic: bool = False
    systemd_dir: Path = SYSTEMD_DIR
    privileged: bool = True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _installation_sample(root: Path) -> dict:
    digest = hashlib.sha256()
    entries = {}
    for relative in SAMPLE_PATHS:
        path = root / relative
        value = _sha256(path) if path.is_file() else "MISSING"
        entries[relative] = value
        digest.update(relative.encode("utf-8") + b"\0" + value.encode("ascii") + b"\n")
    return {"sha256": digest.hexdigest(), "files": entries}


def _active(runner: CommandRunner, service: str) -> bool:
    result = runner.run(["systemctl", "is-active", service], timeout=15)
    return result.returncode == 0 and result.stdout.strip() == "active"


def _enabled(runner: CommandRunner, service: str) -> bool:
    result = runner.run(["systemctl", "is-enabled", service], timeout=15)
    return result.returncode == 0 and result.stdout.strip() in {
        "enabled",
        "enabled-runtime",
        "linked",
        "linked-runtime",
    }


def _systemctl(
    runner: CommandRunner,
    service: str,
    *args: str,
    privileged: bool,
    check: bool = True,
) -> None:
    if service == LIVE_SERVICE:
        raise RollbackError("rollback safety guard blocked bx1-web.service")
    runner.run(
        ["systemctl", *args, service] if args[0] != "daemon-reload" else ["systemctl", "daemon-reload"],
        privileged=privileged,
        check=check,
        timeout=60,
    )


def rollback(
    options: RollbackOptions,
    *,
    runner: Optional[CommandRunner] = None,
) -> dict:
    command_runner = runner or CommandRunner()
    backup = options.backup_dir.expanduser().resolve(strict=True)
    manifest_path = backup / "deployment_manifest.json"
    if not manifest_path.is_file():
        raise RollbackError("deployment manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "bx1.deployment.backup.v2" or not manifest.get(
        "backup_complete"
    ):
        raise RollbackError("deployment backup is incomplete or unsupported")

    service = str(manifest.get("service_name", ""))
    if service != DEFAULT_SERVICE or service == LIVE_SERVICE:
        raise RollbackError("backup does not describe the dedicated Alpha service")
    root = Path(str(manifest["install_root"])).resolve(strict=False)
    if root == LIVE_ROOT or LIVE_ROOT in root.parents:
        raise RollbackError("backup install root resolves inside the live installation")

    previous_path_text = str(manifest.get("previous_installation_path", ""))
    previous = Path(previous_path_text) if previous_path_text else None
    if previous is not None:
        resolved_previous = previous.resolve(strict=False)
        if backup not in resolved_previous.parents:
            raise RollbackError("previous installation snapshot escaped backup root")
        previous = resolved_previous
    if manifest.get("install_root_existed") and (
        previous is None or not previous.is_dir()
    ):
        raise RollbackError("previous BX1_OS snapshot is missing")
    expected_previous_sample = manifest.get("previous_installation_sample", {})
    if manifest.get("install_root_existed") and (
        not isinstance(expected_previous_sample, dict)
        or _installation_sample(previous).get("sha256")
        != expected_previous_sample.get("sha256")
    ):
        raise RollbackError("previous BX1_OS snapshot checksum is invalid")
    service_backup_text = str(manifest.get("service_backup", ""))
    if service_backup_text:
        relative_backup = PurePosixPath(service_backup_text)
        if relative_backup.is_absolute() or ".." in relative_backup.parts:
            raise RollbackError("pre-existing service backup path is unsafe")
    if manifest.get("service_existed") and not service_backup_text:
        raise RollbackError("pre-existing service backup is missing")
    if service_backup_text and not (backup / service_backup_text).is_file():
        raise RollbackError("pre-existing service backup file is missing")
    if service_backup_text and _text_sha256(backup / service_backup_text) != str(
        manifest.get("service_backup_sha256", "")
    ):
        raise RollbackError("pre-existing service backup checksum is invalid")

    if options.dry_run:
        return {
            "status": "DRY_RUN_PASSED",
            "backup": str(backup),
            "install_root": str(root),
            "service_name": service,
            "changes_made": False,
        }

    if _active(command_runner, service):
        _systemctl(
            command_runner,
            service,
            "stop",
            privileged=options.privileged,
        )

    quarantined = ""
    if root.exists():
        quarantine = root.parent / (
            "%s.failed_%s" % (root.name, time.strftime("%Y%m%d_%H%M%S"))
        )
        if quarantine.exists():
            raise RollbackError("failed-install quarantine path already exists")
        shutil.move(str(root), str(quarantine))
        quarantined = str(quarantine)

    if manifest.get("install_root_existed") and previous is not None:
        shutil.move(str(previous), str(root))

    installed_unit = options.systemd_dir / service
    if manifest.get("service_existed"):
        original_fragment = Path(str(manifest.get("service_fragment_path", "")))
        if not str(original_fragment):
            raise RollbackError("original service fragment path is missing")
        allowed_unit_dirs = {
            options.systemd_dir.resolve(strict=False),
            Path("/lib/systemd/system"),
            Path("/usr/lib/systemd/system"),
        }
        if (
            original_fragment.name != service
            or original_fragment.parent.resolve(strict=False) not in allowed_unit_dirs
        ):
            raise RollbackError("original service fragment path is unsafe")
        if installed_unit != original_fragment and installed_unit.exists():
            command_runner.run(
                ["rm", "-f", str(installed_unit)],
                privileged=options.privileged,
                check=True,
            )
        command_runner.run(
            [
                "install",
                "-m",
                "0644",
                str(backup / service_backup_text),
                str(original_fragment),
            ],
            privileged=options.privileged,
            check=True,
        )
    elif installed_unit.exists() or options.privileged:
        command_runner.run(
            ["rm", "-f", str(installed_unit)],
            privileged=options.privileged,
            check=True,
        )

    _systemctl(
        command_runner,
        service,
        "daemon-reload",
        privileged=options.privileged,
    )

    if bool(manifest.get("service_was_enabled")):
        _systemctl(
            command_runner,
            service,
            "enable",
            privileged=options.privileged,
        )
    elif _enabled(command_runner, service):
        _systemctl(
            command_runner,
            service,
            "disable",
            privileged=options.privileged,
        )

    if bool(manifest.get("service_was_active")):
        _systemctl(
            command_runner,
            service,
            "start",
            privileged=options.privileged,
        )
    elif _active(command_runner, service):
        _systemctl(
            command_runner,
            service,
            "stop",
            privileged=options.privileged,
        )

    report = {
        "schema": "bx1.deployment.rollback.v2",
        "status": "ROLLED_BACK",
        "automatic": options.automatic,
        "completed_at": time.time(),
        "backup_location": str(backup),
        "install_root": str(root),
        "service_name": service,
        "failed_installation_quarantined": bool(quarantined),
        "quarantine_path": quarantined,
        "previous_installation_restored": bool(
            manifest.get("install_root_existed")
        ),
        "preexisting_unit_restored": bool(manifest.get("service_existed")),
        "prior_active_state_restored": bool(manifest.get("service_was_active")),
        "prior_enabled_state_restored": bool(manifest.get("service_was_enabled")),
        "live_service_touched": False,
    }
    (backup / "rollback_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback BX1 OS Alpha side-by-side")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--automatic", action="store_true")
    args = parser.parse_args()
    try:
        report = rollback(
            RollbackOptions(
                backup_dir=args.backup,
                dry_run=args.dry_run,
                automatic=args.automatic,
            )
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print("[BX1 ROLLBACK] ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
