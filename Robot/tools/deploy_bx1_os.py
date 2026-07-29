#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Mapping, Optional

from qualify_bx1_alpha import verify_release


LIVE_ROOT = Path("/home/arduino/Arduino_Q_Client_V1")
LIVE_SERVICE = "bx1-web.service"
LIVE_PORT = 8088
DEFAULT_ROOT = Path("/home/arduino/BX1_OS")
DEFAULT_SERVICE = "bx1-os-alpha.service"
DEFAULT_PORT = 8089
RELEASE_VERSION = "0.7.1-developer-preview"
RELEASE_TAG = "BX1_OS_v0.7.1_modular_runtime_developer_platform"
DEFAULT_BACKUP_ROOT = Path("/home/arduino/BX1_OS_backups")
SYSTEMD_DIR = Path("/etc/systemd/system")
SAMPLE_PATHS = (
    "main.py",
    "START_BX1_WEB.sh",
    "python/main.py",
    "python/config.json",
)


class DeploymentError(RuntimeError):
    pass


def _subprocess_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


class CommandRunner:
    def run(
        self,
        command: Iterable[str],
        *,
        check: bool = False,
        privileged: bool = False,
        timeout: int = 120,
        progress_label: str = "",
        progress_interval: int = 10,
    ) -> subprocess.CompletedProcess[str]:
        cmd = list(command)
        if privileged and getattr(os, "geteuid", lambda: 1)() != 0:
            cmd.insert(0, "sudo")
        if progress_label:
            started = time.monotonic()
            process = subprocess.Popen(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            timed_out = False
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    process.kill()
                    stdout, stderr = process.communicate()
                    break
                try:
                    stdout, stderr = process.communicate(
                        timeout=min(float(progress_interval), remaining)
                    )
                    break
                except subprocess.TimeoutExpired:
                    print(
                        "[BX1 DEPLOY] %s still running (%.0fs elapsed)"
                        % (progress_label, time.monotonic() - started),
                        flush=True,
                    )
            result = subprocess.CompletedProcess(
                cmd,
                124 if timed_out else process.returncode,
                stdout,
                (stderr or "")
                + (
                    "\nTimed out after %ss while %s" % (timeout, progress_label)
                    if timed_out
                    else ""
                ),
            )
        else:
            try:
                result = subprocess.run(
                    cmd,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                result = subprocess.CompletedProcess(
                    cmd,
                    124,
                    _subprocess_text(exc.stdout),
                    _subprocess_text(exc.stderr) + "\nTimed out after %ss" % timeout,
                )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-1200:]
            raise DeploymentError("%s failed: %s" % (" ".join(cmd), detail))
        return result


@dataclass
class DeployOptions:
    release_root: Path
    install_root: Path = DEFAULT_ROOT
    backup_root: Path = DEFAULT_BACKUP_ROOT
    service_name: str = DEFAULT_SERVICE
    service_user: str = "arduino"
    web_port: int = DEFAULT_PORT
    mode: str = "install-only"
    status_url: str = "http://127.0.0.1:8089/api/status"
    old_status_url: str = "http://127.0.0.1:8088/api/status"
    dry_run: bool = False
    systemd_dir: Path = SYSTEMD_DIR
    install_dependencies: bool = True
    run_qualification: bool = True
    privileged: bool = True


def canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def validate_side_by_side_target(
    install_root: Path,
    service_name: str,
    web_port: int,
    *,
    live_root: Path = LIVE_ROOT,
) -> Path:
    root = canonical(install_root)
    live = canonical(live_root)
    if root == live or live in root.parents:
        raise DeploymentError("install root resolves inside the live installation")
    if service_name == LIVE_SERVICE:
        raise DeploymentError("bx1-web.service is reserved for the live installation")
    if service_name != DEFAULT_SERVICE:
        raise DeploymentError("Alpha side-by-side service must be bx1-os-alpha.service")
    if not service_name.endswith(".service") or Path(service_name).name != service_name:
        raise DeploymentError("side-by-side service name is invalid")
    if int(web_port) == LIVE_PORT:
        raise DeploymentError("port 8088 is reserved for the live installation")
    if not 1 <= int(web_port) <= 65535:
        raise DeploymentError("web port is outside the valid TCP range")
    if root == Path("/") or len(root.parts) < 3:
        raise DeploymentError("install root is unsafe")
    if install_root.is_symlink():
        raise DeploymentError("install root must not be a symbolic link")
    return root


def validate_local_status_url(url: str, expected_port: int) -> None:
    parsed = urlparse(str(url))
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != int(expected_port)
    ):
        raise DeploymentError(
            "status URL must use local HTTP port %s" % expected_port
        )


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installation_sample(root: Path) -> Dict[str, Any]:
    digest = hashlib.sha256()
    entries: Dict[str, str] = {}
    for relative in SAMPLE_PATHS:
        path = root / Path(relative)
        value = hash_bytes(path.read_bytes()) if path.is_file() else "MISSING"
        entries[relative] = value
        digest.update(relative.encode("utf-8") + b"\0" + value.encode("ascii") + b"\n")
    return {"sha256": digest.hexdigest(), "files": entries}


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, int(port))) == 0


def url_healthy(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status < 400
    except Exception:
        return False


def _systemctl_value(
    runner: CommandRunner,
    service: str,
    property_name: str,
) -> str:
    result = runner.run(
        ["systemctl", "show", service, "-p", property_name, "--value"],
        timeout=15,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def service_state(runner: CommandRunner, service: str) -> Dict[str, Any]:
    fragment = _systemctl_value(runner, service, "FragmentPath")
    load_state = _systemctl_value(runner, service, "LoadState")
    active = runner.run(["systemctl", "is-active", service], timeout=15)
    enabled = runner.run(["systemctl", "is-enabled", service], timeout=15)
    cat = runner.run(["systemctl", "cat", service], timeout=15)
    return {
        "exists": load_state == "loaded" and bool(fragment),
        "fragment_path": fragment,
        "active": active.returncode == 0 and active.stdout.strip() == "active",
        "enabled": enabled.returncode == 0
        and enabled.stdout.strip() in {"enabled", "enabled-runtime", "linked", "linked-runtime"},
        "definition_sha256": hash_bytes(cat.stdout.strip().encode("utf-8"))
        if cat.returncode == 0
        else "",
    }


def _safe_release_path(value: Any) -> PurePosixPath:
    relative = PurePosixPath(str(value))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise DeploymentError("unsafe release path: %s" % value)
    return relative


class SideBySideDeployer:
    def __init__(
        self,
        options: DeployOptions,
        *,
        runner: Optional[CommandRunner] = None,
    ) -> None:
        self.options = options
        self.runner = runner or CommandRunner()
        self.root = validate_side_by_side_target(
            options.install_root,
            options.service_name,
            options.web_port,
        )
        self.backup_root = canonical(options.backup_root)
        if self.backup_root == self.root or self.root in self.backup_root.parents:
            raise DeploymentError("backup root must be outside the installation root")
        live = canonical(LIVE_ROOT)
        if self.backup_root == live or live in self.backup_root.parents:
            raise DeploymentError("backup root must not be inside the live installation")
        if options.mode not in {"install-only", "no-start", "start-canary"}:
            raise DeploymentError("unsupported deployment mode")
        if options.service_user != "arduino":
            raise DeploymentError("Alpha side-by-side service user must be arduino")
        validate_local_status_url(options.old_status_url, LIVE_PORT)
        validate_local_status_url(options.status_url, options.web_port)
        self.release_root = canonical(options.release_root)
        self.release: Dict[str, Any] = {}
        self.backup_dir: Optional[Path] = None
        self.staging_dir: Optional[Path] = None
        self.changes_started = False
        self.started_monotonic = time.monotonic()

    def _report_stage(self, message: str) -> None:
        print(
            "[BX1 DEPLOY] %s (%.1fs elapsed)"
            % (message, time.monotonic() - self.started_monotonic),
            flush=True,
        )

    def preflight(self) -> Dict[str, Any]:
        verification = verify_release(self.release_root)
        if not verification.get("valid"):
            raise DeploymentError(
                "release verification failed: %s"
                % "; ".join(verification.get("failures", []))
            )
        self.release = dict(verification["release"])
        if (
            self.release.get("release_version") != RELEASE_VERSION
            or self.release.get("release_tag") != RELEASE_TAG
        ):
            raise DeploymentError("release manifest version/tag is not BX1 OS v0.7.1 modular runtime developer platform")
        if self.release.get("target_service") != DEFAULT_SERVICE:
            raise DeploymentError("release manifest does not target bx1-os-alpha.service")
        if canonical(Path(self.release.get("default_install_root", ""))) != canonical(
            DEFAULT_ROOT
        ):
            raise DeploymentError("release manifest is not a side-by-side release")
        if not self.release.get("side_by_side"):
            raise DeploymentError("release manifest lacks the side-by-side safety marker")
        analyze = self.runner.run(["systemd-analyze", "--version"], timeout=15)
        if analyze.returncode != 0:
            raise DeploymentError("systemd-analyze is required for unit verification")

        old_state = service_state(self.runner, LIVE_SERVICE)
        if not old_state["exists"] or not old_state["definition_sha256"]:
            raise DeploymentError("live bx1-web.service definition is unavailable")
        if not old_state["active"]:
            raise DeploymentError("live bx1-web.service is not active")
        if not url_healthy(self.options.old_status_url):
            raise DeploymentError("live port 8088 health endpoint is not healthy")

        target_state = service_state(self.runner, self.options.service_name)
        baseline = {
            "schema": "bx1.deployment.baseline.v2",
            "release_version": RELEASE_VERSION,
            "release_tag": RELEASE_TAG,
            "created_at": time.time(),
            "live_install_root": str(canonical(LIVE_ROOT)),
            "live_service": LIVE_SERVICE,
            "live_port": LIVE_PORT,
            "old_service_definition_sha256": old_state["definition_sha256"],
            "old_installation_sample": installation_sample(canonical(LIVE_ROOT)),
            "old_service_active": old_state["active"],
            "old_service_enabled": old_state["enabled"],
            "old_health_url": self.options.old_status_url,
            "old_health_passed": True,
            "canary_port": self.options.web_port,
            "canary_port_was_unused": not port_in_use(self.options.web_port),
            "target_service_before": target_state,
        }
        if self.options.mode == "start-canary" and not baseline["canary_port_was_unused"]:
            raise DeploymentError("canary port %s is already in use" % self.options.web_port)
        return baseline

    def _create_backup(self, baseline: Mapping[str, Any]) -> Dict[str, Any]:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.backup_dir = self.backup_root / ("%s_ALPHA_SIDE_BY_SIDE" % stamp)
        if self.backup_dir.exists():
            raise DeploymentError("backup path already exists")
        self.backup_dir.mkdir(parents=True)
        systemd_backup = self.backup_dir / "systemd"
        systemd_backup.mkdir()

        target_state = dict(baseline["target_service_before"])
        unit_content = ""
        fragment = str(target_state.get("fragment_path", ""))
        if target_state.get("exists") and fragment:
            unit_path = Path(fragment)
            allowed_unit_dirs = {
                canonical(self.options.systemd_dir),
                Path("/lib/systemd/system"),
                Path("/usr/lib/systemd/system"),
            }
            if (
                unit_path.name != self.options.service_name
                or canonical(unit_path.parent) not in allowed_unit_dirs
            ):
                raise DeploymentError("pre-existing Alpha unit fragment path is unsafe")
            if unit_path.is_file():
                unit_content = unit_path.read_text(encoding="utf-8")
            else:
                result = self.runner.run(
                    ["cat", fragment],
                    privileged=self.options.privileged,
                    check=True,
                )
                unit_content = result.stdout
            (systemd_backup / self.options.service_name).write_text(
                unit_content,
                encoding="utf-8",
            )

        manifest = {
            "schema": "bx1.deployment.backup.v2",
            "release_version": RELEASE_VERSION,
            "release_tag": RELEASE_TAG,
            "created_at": time.time(),
            "backup_complete": True,
            "install_root": str(self.root),
            "install_root_existed": self.root.exists(),
            "previous_installation_sample": (
                installation_sample(self.root) if self.root.exists() else {}
            ),
            "previous_installation_path": "",
            "service_name": self.options.service_name,
            "service_existed": bool(target_state.get("exists")),
            "service_fragment_path": fragment,
            "service_was_active": bool(target_state.get("active")),
            "service_was_enabled": bool(target_state.get("enabled")),
            "service_backup": (
                "systemd/%s" % self.options.service_name if unit_content else ""
            ),
            "service_backup_sha256": (
                hash_bytes(unit_content.encode("utf-8")) if unit_content else ""
            ),
            "baseline": dict(baseline),
            "release_manifest": self.release,
        }
        self._write_manifest(manifest)
        return manifest

    def _write_manifest(self, manifest: Mapping[str, Any]) -> None:
        if self.backup_dir is None:
            raise DeploymentError("backup directory is unavailable")
        (self.backup_dir / "deployment_manifest.json").write_text(
            json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _stage_payload(self) -> Path:
        parent = self.root.parent
        parent.mkdir(parents=True, exist_ok=True)
        self.staging_dir = Path(
            tempfile.mkdtemp(prefix=".%s.staging." % self.root.name, dir=parent)
        )
        for entry in self.release.get("files", []):
            relative = _safe_release_path(entry.get("path", ""))
            source = self.release_root / "payload" / Path(*relative.parts)
            target = self.staging_dir / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(int(entry.get("mode", 0o644)))

        release_metadata = self.staging_dir / "release_manifest.json"
        release_metadata.write_text(
            json.dumps(self.release, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        release_metadata.chmod(0o644)

        template = self.staging_dir / "python" / "config.alpha-qualification.json"
        config = self.staging_dir / "python" / "config.json"
        if not template.is_file():
            raise DeploymentError("reviewed Alpha qualification template is missing")
        template_value = json.loads(template.read_text(encoding="utf-8"))
        if (
            not template_value.get("observer_only")
            or int(template_value.get("web_port", 0)) != DEFAULT_PORT
        ):
            raise DeploymentError("Alpha qualification template failed safety validation")
        config.write_text(
            json.dumps(template_value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        config.chmod(0o600)
        # The install launcher is intentionally run with sudo, but the service
        # itself runs as arduino.  Keep the generated machine-local config
        # private while making it readable by exactly that service account.
        if os.name == "posix" and self.options.privileged:
            if os.geteuid() != 0:
                raise DeploymentError(
                    "privileged deployment must run as root to set config ownership"
                )
            import pwd

            account = pwd.getpwnam(self.options.service_user)
            os.chown(config, account.pw_uid, account.pw_gid)
        for relative in ("runtime", "runtime/tmp", "logs", "cache"):
            directory = self.staging_dir / relative
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o750)
            if os.name == "posix" and self.options.privileged:
                os.chown(directory, account.pw_uid, account.pw_gid)
        return self.staging_dir

    def _create_venv(self, staging: Path) -> None:
        if not self.options.install_dependencies:
            (staging / ".venv" / "bin").mkdir(parents=True)
            (staging / ".venv" / "bin" / "python").write_text(
                "# test environment\n",
                encoding="utf-8",
            )
            return
        self.runner.run(
            ["python3", "-m", "venv", str(staging / ".venv")],
            check=True,
            timeout=300,
            progress_label="virtual environment creation",
            progress_interval=10,
        )
        python_bin = staging / ".venv" / "bin" / "python"
        self.runner.run(
            [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "-r",
                str(staging / "python" / "requirements.txt"),
            ],
            check=True,
            timeout=900,
            progress_label="dependency installation",
            progress_interval=15,
        )

    def _render_unit(self, staging: Path) -> Path:
        source = staging / "service" / "bx1-os-alpha.service"
        text = source.read_text(encoding="utf-8")
        text = text.replace("/home/arduino/BX1_OS", str(self.root))
        text = text.replace("BX1_WEB_PORT=8089", "BX1_WEB_PORT=%s" % self.options.web_port)
        text = text.replace(
            "User=arduino\nGroup=arduino",
            "User=%s\nGroup=%s" % (self.options.service_user, self.options.service_user),
        )
        if LIVE_SERVICE in text or str(canonical(LIVE_ROOT)) in text or "BX1_WEB_PORT=8088" in text:
            raise DeploymentError("rendered unit references reserved live resources")
        source.write_text(text, encoding="utf-8")
        return source

    def _systemctl(self, *args: str, check: bool = True) -> None:
        if LIVE_SERVICE in args:
            raise DeploymentError("internal safety guard blocked bx1-web.service")
        self.runner.run(
            ["systemctl", *args],
            check=check,
            privileged=self.options.privileged,
            timeout=60,
        )

    def _qualify(self, baseline_path: Path) -> None:
        if not self.options.run_qualification:
            return
        command = [
            str(self.root / ".venv" / "bin" / "python"),
            str(self.root / "tools" / "qualify_bx1_alpha.py"),
            "--mode",
            "canary" if self.options.mode == "start-canary" else "install-only",
            "--install-root",
            str(self.root),
            "--service-name",
            self.options.service_name,
            "--status-url",
            self.options.status_url,
            "--old-status-url",
            self.options.old_status_url,
            "--web-port",
            str(self.options.web_port),
            "--baseline",
            str(baseline_path),
            "--output",
            str(self.backup_dir / "qualification_report.json"),
            "--launcher-pid",
            str(os.getpid()),
            "--launcher-path",
            str(Path(__file__).resolve()),
        ]
        self._report_stage("qualification started")
        result = self.runner.run(
            command,
            check=False,
            timeout=180,
            progress_label="Alpha qualification",
            progress_interval=10,
        )
        (self.backup_dir / "qualification_stdout.log").write_text(
            result.stdout or "", encoding="utf-8"
        )
        (self.backup_dir / "qualification_stderr.log").write_text(
            result.stderr or "", encoding="utf-8"
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-1200:]
            raise DeploymentError(
                "Alpha qualification failed (exit %s): %s"
                % (result.returncode, detail or "see preserved qualification logs")
            )
        self._report_stage("qualification passed")

    def deploy(self) -> Dict[str, Any]:
        self._report_stage("preflight checks started")
        baseline = self.preflight()
        self._report_stage("preflight checks passed")
        if self.options.dry_run:
            return {
                "status": "DRY_RUN_PASSED",
                "mode": self.options.mode,
                "install_root": str(self.root),
                "service_name": self.options.service_name,
                "web_port": self.options.web_port,
                "changes_made": False,
            }

        self._report_stage("creating rollback baseline")
        manifest = self._create_backup(baseline)
        try:
            self._report_stage("staging release payload")
            staging = self._stage_payload()
            self._report_stage("creating isolated virtual environment")
            self._create_venv(staging)
            unit_source = self._render_unit(staging)

            prior_state = dict(baseline["target_service_before"])
            if prior_state.get("active"):
                self._systemctl("stop", self.options.service_name)
                self.changes_started = True

            if self.root.exists():
                previous = self.backup_dir / "previous_installation"
                shutil.move(str(self.root), str(previous))
                self.changes_started = True
                manifest["previous_installation_path"] = str(previous)
                self._write_manifest(manifest)
            shutil.move(str(staging), str(self.root))
            self.staging_dir = None
            self.changes_started = True

            self._report_stage("validating and installing dedicated Alpha unit")
            installed_source = self.root / unit_source.relative_to(staging)
            verify = self.runner.run(
                ["systemd-analyze", "verify", str(installed_source)],
                timeout=60,
            )
            if verify.returncode != 0:
                raise DeploymentError(
                    "systemd unit verification failed: %s"
                    % (verify.stderr or verify.stdout).strip()[-1200:]
                )
            self.runner.run(
                ["chown", "-R", "%s:%s" % (self.options.service_user, self.options.service_user), str(self.root)],
                check=True,
                privileged=self.options.privileged,
                timeout=120,
                progress_label="Alpha installation ownership update",
                progress_interval=10,
            )
            installed_unit = self.options.systemd_dir / self.options.service_name
            self.runner.run(
                ["install", "-m", "0644", str(installed_source), str(installed_unit)],
                check=True,
                privileged=self.options.privileged,
            )
            self._systemctl("daemon-reload")

            current = service_state(self.runner, self.options.service_name)
            if self.options.mode in {"install-only", "no-start"}:
                if current["active"]:
                    self._systemctl("stop", self.options.service_name)
                if current["enabled"]:
                    self._systemctl("disable", self.options.service_name)
            else:
                if current["enabled"]:
                    self._systemctl("disable", self.options.service_name)
                if port_in_use(self.options.web_port):
                    raise DeploymentError("canary port became busy before service start")
                self._systemctl("start", self.options.service_name)

            baseline_path = self.backup_dir / "deployment_manifest.json"
            self._qualify(baseline_path)
            report = {
                "schema": "bx1.deployment.report.v2",
                "release_version": RELEASE_VERSION,
                "release_tag": RELEASE_TAG,
                "status": "CANARY_RUNNING"
                if self.options.mode == "start-canary"
                else "INSTALLED_INACTIVE",
                "mode": self.options.mode,
                "completed_at": time.time(),
                "install_root": str(self.root),
                "service_name": self.options.service_name,
                "web_port": self.options.web_port,
                "backup_location": str(self.backup_dir),
                "service_enabled": False,
                "live_installation_changed": False,
                "live_service_changed": False,
            }
            (self.backup_dir / "deployment_report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return report
        except Exception as deployment_error:
            self._quarantine_staging()
            if self.changes_started and self.backup_dir is not None:
                try:
                    self._report_stage("deployment failed; automatic rollback started")
                    from rollback_bx1_os import RollbackOptions, rollback

                    rollback(
                        RollbackOptions(
                            backup_dir=self.backup_dir,
                            automatic=True,
                            systemd_dir=self.options.systemd_dir,
                            privileged=self.options.privileged,
                        ),
                        runner=self.runner,
                    )
                    self._report_stage("automatic rollback completed")
                except Exception as rollback_error:
                    (self.backup_dir / "rollback_report.json").write_text(
                        json.dumps(
                            {
                                "schema": "bx1.deployment.rollback.v2",
                                "release_version": RELEASE_VERSION,
                                "status": "ROLLBACK_FAILED",
                                "automatic": True,
                                "completed_at": time.time(),
                                "backup_location": str(self.backup_dir),
                                "deployment_error": str(deployment_error),
                                "rollback_error": str(rollback_error),
                                "live_service_touched": False,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    raise DeploymentError(
                        "deployment failed and automatic rollback also failed: %s"
                        % rollback_error
                    ) from deployment_error
            raise

    def _quarantine_staging(self) -> None:
        if self.staging_dir is None or not self.staging_dir.exists():
            return
        failed = self.root.parent / (
            "%s.failed_%s" % (self.root.name, time.strftime("%Y%m%d_%H%M%S"))
        )
        shutil.move(str(self.staging_dir), str(failed))
        self.staging_dir = None


def _mode_from_args(args: argparse.Namespace) -> str:
    selected = [
        name
        for name, enabled in (
            ("install-only", args.install_only),
            ("no-start", args.no_start),
            ("start-canary", args.start_canary),
        )
        if enabled
    ]
    if len(selected) > 1:
        raise DeploymentError("deployment modes are mutually exclusive")
    return selected[0] if selected else "install-only"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy BX1 OS Alpha side-by-side")
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--service-user", default="arduino")
    parser.add_argument("--web-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--status-url", default="http://127.0.0.1:8089/api/status")
    parser.add_argument("--old-status-url", default="http://127.0.0.1:8088/api/status")
    parser.add_argument("--install-only", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--start-canary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        options = DeployOptions(
            release_root=args.release_root,
            install_root=args.install_root,
            backup_root=args.backup_root,
            service_name=args.service,
            service_user=args.service_user,
            web_port=args.web_port,
            mode=_mode_from_args(args),
            status_url=args.status_url,
            old_status_url=args.old_status_url,
            dry_run=args.dry_run,
        )
        report = SideBySideDeployer(options).deploy()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print("[BX1 DEPLOY] ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
