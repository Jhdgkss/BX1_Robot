#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent


def load_tool(name: str, filename: str):
    path = ROOT / "tools" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


qualification = load_tool("qualify_bx1_alpha", "qualify_bx1_alpha.py")
builder = load_tool("bx1_release_builder_test", "build_bx1_release.py")
deployment = load_tool("bx1_side_deployment_test", "deploy_bx1_os.py")
rollback_tool = load_tool("rollback_bx1_os", "rollback_bx1_os.py")


class FakeRunner:
    def __init__(self, systemd_dir: Path, live_unit: Path) -> None:
        self.systemd_dir = systemd_dir
        self.systemd_dir.mkdir(parents=True, exist_ok=True)
        self.states = {
            "bx1-web.service": {
                "exists": True,
                "active": True,
                "enabled": True,
                "fragment": live_unit,
            },
            "bx1-os-alpha.service": {
                "exists": False,
                "active": False,
                "enabled": False,
                "fragment": self.systemd_dir / "bx1-os-alpha.service",
            },
        }
        self.commands = []

    def run(
        self,
        command,
        *,
        check=False,
        privileged=False,
        timeout=120,
        progress_label="",
        progress_interval=10,
    ):
        del privileged, timeout, progress_label, progress_interval
        cmd = list(command)
        self.commands.append(cmd)
        rc, out, err = 0, "", ""
        if cmd[:2] == ["systemctl", "show"]:
            service = cmd[2]
            prop = cmd[4]
            state = self.states[service]
            if prop == "FragmentPath":
                out = str(state["fragment"]) if state["exists"] else ""
            elif prop == "LoadState":
                out = "loaded" if state["exists"] else "not-found"
        elif cmd[:2] == ["systemctl", "is-active"]:
            state = self.states[cmd[2]]
            out, rc = ("active", 0) if state["active"] else ("inactive", 3)
        elif cmd[:2] == ["systemctl", "is-enabled"]:
            state = self.states[cmd[2]]
            out, rc = ("enabled", 0) if state["enabled"] else ("disabled", 1)
        elif cmd[:2] == ["systemctl", "cat"]:
            state = self.states[cmd[2]]
            if state["exists"] and Path(state["fragment"]).is_file():
                out = Path(state["fragment"]).read_text(encoding="utf-8")
            else:
                rc, err = 1, "not found"
        elif cmd[:2] == ["systemctl", "stop"]:
            self.states[cmd[2]]["active"] = False
        elif cmd[:2] == ["systemctl", "start"]:
            self.states[cmd[2]]["active"] = True
        elif cmd[:2] == ["systemctl", "disable"]:
            self.states[cmd[2]]["enabled"] = False
        elif cmd[:2] == ["systemctl", "enable"]:
            self.states[cmd[2]]["enabled"] = True
        elif cmd[:2] == ["systemctl", "daemon-reload"]:
            unit = self.systemd_dir / "bx1-os-alpha.service"
            self.states["bx1-os-alpha.service"]["exists"] = unit.is_file()
            self.states["bx1-os-alpha.service"]["fragment"] = unit
        elif cmd[0] == "systemd-analyze":
            pass
        elif cmd[0] == "chown":
            pass
        elif cmd[0] == "install":
            target = Path(cmd[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(cmd[-2]), target)
        elif cmd[:2] == ["rm", "-f"]:
            Path(cmd[2]).unlink(missing_ok=True)
        elif cmd[0] == "cat":
            out = Path(cmd[1]).read_text(encoding="utf-8")
        else:
            rc, err = 127, "unexpected fake command: %r" % cmd
        result = subprocess.CompletedProcess(cmd, rc, out, err)
        if check and rc:
            raise RuntimeError(err)
        return result


def valid_snapshot():
    required = [
        "events",
        "capabilities",
        "logging",
        "scheduler",
        "led",
        "drive",
        "range",
        "battery",
        "power",
        "diagnostics",
        "health",
        "communication",
        "runtime_hardware",
    ]
    isolation = {
        "actuators_blocked": True,
        "camera_blocked": True,
        "gpio_blocked": True,
        "hardware_bridge_blocked": True,
        "leds_blocked": True,
        "microphone_blocked": True,
        "servos_blocked": True,
        "wheels_blocked": True,
    }
    return {
        "ok": True,
        "bx1_os": {
            "milestone": "BX1 OS Alpha",
            "release_version": "0.2.0",
            "release_tag": "BX1_OS_ALPHA_v0.2.0",
            "qualification_mode": True,
            "observer_only": True,
            "observer_isolation": isolation,
            "startup_validated": True,
            "startup": {
                "schema": "bx1.runtime.startup.v1",
                "success": True,
                "required_services": required,
                "registered_services": required,
            },
            "service_registry": {
                "state": "READY",
                "registered_count": len(required),
                "running_count": len(required),
            },
            "scheduler": {"state": "READY", "tick_count": 4},
            "events": {"state": "READY"},
            "diagnostics": {"state": "READY"},
            "communication": {"state": "READY", "transport": "in_memory"},
            "health": {"state": "READY", "check_count": 2},
            "management_interface": {
                "id": "bx1-os-management",
                "state": "READY",
                "architecture_only": True,
                "capabilities": {
                    "service_control": False,
                    "host_power_control": False,
                    "configuration_write": False,
                    "log_streaming": False,
                    "update_installation": False,
                    "deployment_rollback": False,
                },
            },
        },
        "state": {
            "observer_only": True,
            "hardware_ownership": False,
            "actuator_access": False,
            "bridge_mode": "observer_only",
        },
    }


class ReleaseBuilderTests(unittest.TestCase):
    def test_package_is_side_by_side_hashed_and_excludes_live_service(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive, _, manifest = builder.build_release(
                REPOSITORY,
                Path(temporary) / "output",
                timestamp="20260728_120000",
            )
            self.assertEqual(manifest["default_install_root"], "/home/arduino/BX1_OS")
            self.assertEqual(manifest["target_service"], "bx1-os-alpha.service")
            self.assertEqual(manifest["release_version"], "0.2.0")
            self.assertEqual(manifest["release_tag"], "BX1_OS_ALPHA_v0.2.0")
            self.assertEqual(manifest["default_web_port"], 8089)
            self.assertTrue(manifest["side_by_side"])
            paths = {item["path"] for item in manifest["files"]}
            self.assertIn("service/bx1-os-alpha.service", paths)
            self.assertIn("python/config.alpha-qualification.json", paths)
            self.assertIn("tools/deploy_bx1_os.py", paths)
            self.assertIn("python/bx1_management/server.py", paths)
            self.assertIn("python/bx1_management/static/index.html", paths)
            self.assertIn("python/bx1_management/static/styles.css", paths)
            self.assertIn("python/bx1_management/static/app.js", paths)
            self.assertNotIn("service/bx1-web.service", paths)
            self.assertNotIn("tools/install_bx1_web_service.sh", paths)
            self.assertNotIn("START_BX1_WEB.sh", paths)
            self.assertNotIn("STOP_BX1_WEB.sh", paths)
            self.assertNotIn("REPAIR_BX1_STARTUP.sh", paths)
            self.assertNotIn("tools/run_bx1_os_alpha.sh", paths)
            self.assertIn("tools/run_bx1_os_management.sh", paths)
            self.assertFalse(any(path.startswith("sketch/") for path in paths))
            extracted = Path(temporary) / "extracted"
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted)
            report = qualification.verify_release(
                extracted / manifest["release_id"]
            )
            self.assertTrue(report["valid"])


class GuardTests(unittest.TestCase):
    def test_reserved_root_service_and_port_are_rejected(self):
        with self.assertRaises(deployment.DeploymentError):
            deployment.validate_side_by_side_target(
                Path("/home/arduino/Arduino_Q_Client_V1"),
                "bx1-os-alpha.service",
                8089,
            )
        with self.assertRaises(deployment.DeploymentError):
            deployment.validate_side_by_side_target(
                Path("/home/arduino/Arduino_Q_Client_V1/nested"),
                "bx1-os-alpha.service",
                8089,
            )
        with self.assertRaises(deployment.DeploymentError):
            deployment.validate_side_by_side_target(
                Path("/home/arduino/BX1_OS"), "bx1-web.service", 8089
            )
        with self.assertRaises(deployment.DeploymentError):
            deployment.validate_side_by_side_target(
                Path("/home/arduino/BX1_OS"), "bx1-os-alpha.service", 8088
            )

    def test_symlink_into_live_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            live = base / "live"
            live.mkdir()
            link = base / "link"
            try:
                link.symlink_to(live, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable")
            with self.assertRaises(deployment.DeploymentError):
                deployment.validate_side_by_side_target(
                    link / "nested",
                    "bx1-os-alpha.service",
                    8089,
                    live_root=live,
                )


class CommandRunnerTests(unittest.TestCase):
    def test_progress_command_timeout_is_bounded_and_preserves_output(self):
        result = deployment.CommandRunner().run(
            [
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(5)",
            ],
            timeout=1,
            progress_label="controlled timeout test",
            progress_interval=1,
        )
        self.assertEqual(result.returncode, 124)
        self.assertIn("started", result.stdout)
        self.assertIn("Timed out after 1s", result.stderr)


class DeploymentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.live = self.base / "Arduino_Q_Client_V1"
        (self.live / "python").mkdir(parents=True)
        for relative in deployment.SAMPLE_PATHS:
            path = self.live / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("live:%s\n" % relative, encoding="utf-8")
        self.live_before = deployment.installation_sample(self.live)
        self.live_unit = self.base / "bx1-web.service"
        self.live_unit.write_text("LIVE UNIT\n", encoding="utf-8")
        self.systemd = self.base / "systemd"
        self.runner = FakeRunner(self.systemd, self.live_unit)
        archive, _, manifest = builder.build_release(
            REPOSITORY,
            self.base / "release",
            timestamp="20260728_test",
        )
        extracted = self.base / "extracted"
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(extracted)
        self.release_root = extracted / manifest["release_id"]
        self.root = self.base / "BX1_OS"
        self.backups = self.base / "backups"
        self.patchers = [
            mock.patch.object(deployment, "LIVE_ROOT", self.live),
            mock.patch.object(deployment, "url_healthy", return_value=True),
            mock.patch.object(deployment, "port_in_use", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()

    def options(self, **updates):
        values = dict(
            release_root=self.release_root,
            install_root=self.root,
            backup_root=self.backups,
            systemd_dir=self.systemd,
            service_user="arduino",
            install_dependencies=False,
            run_qualification=False,
            privileged=False,
        )
        values.update(updates)
        return deployment.DeployOptions(**values)

    def test_fresh_install_only_creates_isolated_inactive_disabled_install(self):
        report = deployment.SideBySideDeployer(
            self.options(), runner=self.runner
        ).deploy()
        self.assertEqual(report["status"], "INSTALLED_INACTIVE")
        self.assertTrue((self.root / ".venv/bin/python").is_file())
        config = json.loads(
            (self.root / "python/config.json").read_text(encoding="utf-8")
        )
        self.assertTrue(config["observer_only"])
        self.assertEqual(config["web_port"], 8089)
        self.assertFalse(self.runner.states["bx1-os-alpha.service"]["active"])
        self.assertFalse(self.runner.states["bx1-os-alpha.service"]["enabled"])
        mutating_live = [
            command
            for command in self.runner.commands
            if command[:2]
            in (
                ["systemctl", "stop"],
                ["systemctl", "start"],
                ["systemctl", "enable"],
                ["systemctl", "disable"],
            )
            and command[-1] == "bx1-web.service"
        ]
        self.assertEqual(mutating_live, [])
        self.assertEqual(deployment.installation_sample(self.live), self.live_before)

    def test_dry_run_makes_no_changes(self):
        before_commands = len(self.runner.commands)
        report = deployment.SideBySideDeployer(
            self.options(dry_run=True), runner=self.runner
        ).deploy()
        self.assertEqual(report["status"], "DRY_RUN_PASSED")
        self.assertFalse(self.root.exists())
        self.assertFalse(self.backups.exists())
        commands = self.runner.commands[before_commands:]
        self.assertFalse(
            any(
                command[:2]
                in (
                    ["systemctl", "stop"],
                    ["systemctl", "start"],
                    ["systemctl", "enable"],
                    ["systemctl", "disable"],
                )
                for command in commands
            )
        )

    def test_canary_uses_8089_and_never_enables_service(self):
        report = deployment.SideBySideDeployer(
            self.options(mode="start-canary"), runner=self.runner
        ).deploy()
        self.assertEqual(report["status"], "CANARY_RUNNING")
        self.assertTrue(self.runner.states["bx1-os-alpha.service"]["active"])
        self.assertFalse(self.runner.states["bx1-os-alpha.service"]["enabled"])
        unit = (self.systemd / "bx1-os-alpha.service").read_text(encoding="utf-8")
        self.assertIn("BX1_WEB_PORT=8089", unit)
        self.assertNotIn("BX1_WEB_PORT=8088", unit)

    def test_rollback_removes_new_unit_and_quarantines_fresh_install(self):
        report = deployment.SideBySideDeployer(
            self.options(), runner=self.runner
        ).deploy()
        result = rollback_tool.rollback(
            rollback_tool.RollbackOptions(
                backup_dir=Path(report["backup_location"]),
                systemd_dir=self.systemd,
                privileged=False,
            ),
            runner=self.runner,
        )
        self.assertFalse(self.root.exists())
        self.assertFalse((self.systemd / "bx1-os-alpha.service").exists())
        self.assertTrue(result["failed_installation_quarantined"])
        self.assertFalse(self.runner.states["bx1-os-alpha.service"]["active"])

    def test_rollback_restores_preexisting_active_enabled_and_files(self):
        self.root.mkdir()
        (self.root / "old-marker").write_text("previous\n", encoding="utf-8")
        alpha_unit = self.systemd / "bx1-os-alpha.service"
        alpha_unit.write_text("PREVIOUS ALPHA UNIT\n", encoding="utf-8")
        state = self.runner.states["bx1-os-alpha.service"]
        state.update(
            {"exists": True, "active": True, "enabled": True, "fragment": alpha_unit}
        )
        report = deployment.SideBySideDeployer(
            self.options(), runner=self.runner
        ).deploy()
        rollback_tool.rollback(
            rollback_tool.RollbackOptions(
                backup_dir=Path(report["backup_location"]),
                systemd_dir=self.systemd,
                privileged=False,
            ),
            runner=self.runner,
        )
        self.assertEqual((self.root / "old-marker").read_text(), "previous\n")
        self.assertEqual(alpha_unit.read_text(), "PREVIOUS ALPHA UNIT\n")
        self.assertTrue(state["active"])
        self.assertTrue(state["enabled"])

    def test_rollback_keeps_preexisting_inactive_service_inactive(self):
        self.root.mkdir()
        (self.root / "old-marker").write_text("previous\n", encoding="utf-8")
        alpha_unit = self.systemd / "bx1-os-alpha.service"
        alpha_unit.write_text("PREVIOUS ALPHA UNIT\n", encoding="utf-8")
        state = self.runner.states["bx1-os-alpha.service"]
        state.update(
            {"exists": True, "active": False, "enabled": False, "fragment": alpha_unit}
        )
        report = deployment.SideBySideDeployer(
            self.options(), runner=self.runner
        ).deploy()
        rollback_tool.rollback(
            rollback_tool.RollbackOptions(
                backup_dir=Path(report["backup_location"]),
                systemd_dir=self.systemd,
                privileged=False,
            ),
            runner=self.runner,
        )
        self.assertFalse(state["active"])
        self.assertFalse(state["enabled"])

    def test_rollback_restores_preexisting_active_but_disabled_state(self):
        self.root.mkdir()
        (self.root / "old-marker").write_text("previous\n", encoding="utf-8")
        alpha_unit = self.systemd / "bx1-os-alpha.service"
        alpha_unit.write_text("PREVIOUS ALPHA UNIT\n", encoding="utf-8")
        state = self.runner.states["bx1-os-alpha.service"]
        state.update(
            {"exists": True, "active": True, "enabled": False, "fragment": alpha_unit}
        )
        report = deployment.SideBySideDeployer(
            self.options(), runner=self.runner
        ).deploy()
        rollback_tool.rollback(
            rollback_tool.RollbackOptions(
                backup_dir=Path(report["backup_location"]),
                systemd_dir=self.systemd,
                privileged=False,
            ),
            runner=self.runner,
        )
        self.assertTrue(state["active"])
        self.assertFalse(state["enabled"])
        self.assertEqual(alpha_unit.read_text(), "PREVIOUS ALPHA UNIT\n")

    def test_qualification_failure_triggers_safe_automatic_rollback(self):
        def fail_qualification(deployer, baseline_path):
            del baseline_path
            (deployer.backup_dir / "qualification_report.json").write_text(
                '{"passed": false}\n', encoding="utf-8"
            )
            raise deployment.DeploymentError("controlled qualification failure")

        with mock.patch.object(
            deployment.SideBySideDeployer,
            "_qualify",
            autospec=True,
            side_effect=fail_qualification,
        ):
            with self.assertRaises(deployment.DeploymentError):
                deployment.SideBySideDeployer(
                    self.options(run_qualification=True), runner=self.runner
                ).deploy()

        backups = list(self.backups.iterdir())
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertFalse(self.root.exists())
        self.assertFalse((self.systemd / "bx1-os-alpha.service").exists())
        self.assertTrue((backup / "deployment_manifest.json").is_file())
        self.assertTrue((backup / "qualification_report.json").is_file())
        self.assertTrue((backup / "rollback_report.json").is_file())
        self.assertEqual(deployment.installation_sample(self.live), self.live_before)
        self.assertFalse(
            any(
                command[:2] in (["systemctl", "stop"], ["systemctl", "disable"])
                and command[-1] == "bx1-web.service"
                for command in self.runner.commands
            )
        )


class ObserverIsolationTests(unittest.TestCase):
    def test_observer_bridge_blocks_every_action(self):
        sys.path.insert(0, str(ROOT / "python"))
        try:
            from hardware_bridge import ObserverOnlyHardwareBridge

            bridge = ObserverOnlyHardwareBridge({})
            result = bridge.send_action({"type": "set_head_pose"})
            self.assertFalse(result.ok)
            self.assertTrue(result.value["blocked"])
            state = bridge.get_status()
            self.assertFalse(state["hardware_ownership"])
            self.assertFalse(state["actuator_access"])
            self.assertEqual(state["bridge_mode"], "observer_only")
        finally:
            sys.path.remove(str(ROOT / "python"))

    def test_dedicated_unit_has_no_live_resource_references(self):
        unit = (ROOT / "service" / "bx1-os-alpha.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("WorkingDirectory=/home/arduino/BX1_OS", unit)
        self.assertIn("BX1_WEB_PORT=8089", unit)
        self.assertIn("BX1_OBSERVER_ONLY=1", unit)
        self.assertIn("PrivateDevices=yes", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("ExecStart=/home/arduino/BX1_OS/tools/run_bx1_os_management.sh", unit)
        self.assertNotIn("run_bx1_os_alpha.sh", unit)
        self.assertNotIn("Arduino_Q_Client_V1", unit)
        self.assertNotIn("bx1-web.service", unit)
        self.assertNotIn("BX1_WEB_PORT=8088", unit)


class QualificationTests(unittest.TestCase):
    def _fixture(self, base: Path):
        live = base / "Arduino_Q_Client_V1"
        install = base / "BX1_OS"
        (live / "python").mkdir(parents=True)
        (install / "python").mkdir(parents=True)
        for relative in qualification.SAMPLE_PATHS:
            path = live / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("live:%s\n" % relative, encoding="utf-8")
        shutil.copyfile(
            ROOT / "python" / "config.alpha-qualification.json",
            install / "python" / "config.json",
        )
        baseline = {
            "old_service_definition_sha256": "definition",
            "old_installation_sample": qualification.installation_sample(live),
        }
        return live, install, baseline

    def test_install_only_requires_disabled_inactive_and_unused_canary_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            live, install, baseline = self._fixture(Path(temporary))
            with (
                mock.patch.object(qualification, "LIVE_ROOT", live),
                mock.patch.object(qualification, "_get_json", return_value={"ok": True}),
                mock.patch.object(qualification, "_port_in_use", return_value=False),
                mock.patch.object(
                    qualification,
                    "_processes_using_root",
                    return_value=empty_process_evidence(install),
                ),
            ):
                report = qualification.qualify(
                    install_root=install,
                    service_name="bx1-os-alpha.service",
                    status_url="http://127.0.0.1:8089/api/status",
                    mode="install-only",
                    baseline=baseline,
                    skip_systemd=True,
                )
            self.assertTrue(report["passed"])
            names = {check["name"] for check in report["checks"]}
            self.assertIn("Live Port 8088", names)
            self.assertIn("Canary Port 8089", names)
            self.assertIn("BX1_OS Process Isolation", names)

    def test_canary_accepts_observer_only_without_hardware_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            live, install, baseline = self._fixture(Path(temporary))
            with (
                mock.patch.object(qualification, "LIVE_ROOT", live),
                mock.patch.object(qualification, "_get_json", return_value={"ok": True}),
                mock.patch.object(qualification, "_port_in_use", return_value=True),
                mock.patch.object(
                    qualification,
                    "_processes_using_root",
                    return_value={
                        **empty_process_evidence(install),
                        "matching_pids": [123],
                        "matching_processes": [{"pid": 123}],
                    },
                ),
            ):
                report = qualification.qualify(
                    install_root=install,
                    service_name="bx1-os-alpha.service",
                    status_url="http://127.0.0.1:8089/api/status",
                    mode="canary",
                    baseline=baseline,
                    snapshot=valid_snapshot(),
                    skip_systemd=True,
                )
            self.assertTrue(report["passed"])
            self.assertFalse(report["hardware_bridge_ownership_required"])
            self.assertFalse(report["actuator_access_required"])

    def test_install_only_service_port_and_live_health_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            live, install, baseline = self._fixture(Path(temporary))
            definition = "LIVE UNIT"
            baseline["old_service_definition_sha256"] = qualification.hashlib.sha256(
                definition.encode("utf-8")
            ).hexdigest()

            def qualify_state(*, active=False, enabled=False, loaded=True, live_active=True,
                              port_used=False, live_healthy=True):
                def fake_run(command):
                    if command[:2] == ["systemctl", "is-active"]:
                        selected = active if command[2] == "bx1-os-alpha.service" else live_active
                        return command_result("active" if selected else "inactive", 0 if selected else 3)
                    if command[:2] == ["systemctl", "is-enabled"]:
                        return command_result("enabled" if enabled else "disabled", 0 if enabled else 1)
                    if command[:2] == ["systemctl", "cat"]:
                        return command_result(definition)
                    if command[:2] == ["systemctl", "show"]:
                        return command_result("loaded" if loaded else "not-found")
                    raise AssertionError(command)

                with (
                    mock.patch.object(qualification, "LIVE_ROOT", live),
                    mock.patch.object(qualification, "_run", side_effect=fake_run),
                    mock.patch.object(
                        qualification,
                        "_get_json",
                        side_effect=(lambda *args, **kwargs: {"ok": True})
                        if live_healthy
                        else RuntimeError("unhealthy"),
                    ),
                    mock.patch.object(qualification, "_port_in_use", return_value=port_used),
                    mock.patch.object(
                        qualification,
                        "_processes_using_root",
                        return_value=empty_process_evidence(install),
                    ),
                ):
                    return qualification.qualify(
                        install_root=install,
                        service_name="bx1-os-alpha.service",
                        status_url="http://127.0.0.1:8089/api/status",
                        mode="install-only",
                        baseline=baseline,
                    )

            self.assertTrue(qualify_state()["passed"])
            for values in (
                {"active": True},
                {"enabled": True},
                {"loaded": False},
                {"port_used": True},
                {"live_active": False},
                {"live_healthy": False},
            ):
                with self.subTest(values=values):
                    self.assertFalse(qualify_state(**values)["passed"])


def command_result(stdout="", returncode=0, stderr=""):
    return {
        "command": [],
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def empty_process_evidence(root):
    return {
        "qualifier_pid": 100,
        "qualifier_parent_pid": 99,
        "install_root": str(Path(root).resolve(strict=False)),
        "examined_process_count": 0,
        "proc_root_available": True,
        "matching_pids": [],
        "matching_processes": [],
        "excluded_pids": [],
        "excluded_processes": [],
        "inspection_errors": [],
    }


def process_record(pid, *, ppid=1, argv=(), exe="", cwd=""):
    return {
        "pid": pid,
        "ppid": ppid,
        "start_time": str(pid * 10),
        "argv": list(argv),
        "exe": str(exe),
        "cwd": str(cwd),
    }


class ProcessIsolationTests(unittest.TestCase):
    def scan(
        self,
        records,
        *,
        qualifier_pid=100,
        qualifier_parent_pid=99,
        launcher_pid=None,
        launcher_path=None,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            proc_root = Path(temporary)
            for pid in records:
                (proc_root / str(pid)).mkdir()

            def read_record(entry, pid):
                value = records[pid]
                if isinstance(value, Exception):
                    return None, [
                        {"pid": pid, "field": "stat", "error": type(value).__name__}
                    ]
                return value, []

            with mock.patch.object(
                qualification, "_read_process_record", side_effect=read_record
            ):
                return qualification._processes_using_root(
                    Path("/home/arduino/BX1_OS"),
                    proc_root=proc_root,
                    qualifier_pid=qualifier_pid,
                    qualifier_parent_pid=qualifier_parent_pid,
                    launcher_pid=launcher_pid,
                    launcher_path=launcher_path,
                )

    def test_current_qualifier_is_excluded_with_reason(self):
        root = Path("/home/arduino/BX1_OS")
        evidence = self.scan(
            {
                100: process_record(
                    100,
                    ppid=99,
                    argv=(str(root / ".venv/bin/python"), str(root / "tools/qualify_bx1_alpha.py")),
                    exe=root / ".venv/bin/python",
                    cwd=root,
                )
            }
        )
        self.assertEqual(evidence["matching_pids"], [])
        self.assertEqual(evidence["excluded_pids"], [100])
        self.assertEqual(
            evidence["excluded_processes"][0]["reason"],
            "current_qualifier_process",
        )

    def test_only_verified_current_launcher_ancestor_is_excluded(self):
        root = Path("/home/arduino/BX1_OS")
        launcher_path = Path.cwd() / "verified-release" / "tools" / "deploy_bx1_os.py"
        launcher = process_record(
            99,
            ppid=50,
            argv=(
                "python3",
                str(launcher_path),
                "--install-root",
                "/home/arduino/BX1_OS",
            ),
            exe="/usr/bin/python3",
            cwd=Path.cwd(),
        )
        evidence = self.scan(
            {99: launcher, 50: process_record(50, ppid=1, argv=("bash",), exe="/bin/bash")},
            launcher_pid=99,
            launcher_path=launcher_path,
        )
        self.assertEqual(evidence["matching_pids"], [])
        self.assertEqual(evidence["excluded_pids"], [99])
        unrelated = self.scan(
            {99: launcher},
            qualifier_parent_pid=50,
            launcher_pid=99,
            launcher_path=launcher_path,
        )
        self.assertEqual(unrelated["matching_pids"], [99])

    def test_unrelated_alpha_process_detection_reasons(self):
        root = Path("/home/arduino/BX1_OS")
        posix_root = "/home/arduino/BX1_OS"
        cases = {
            "script": process_record(
                201, argv=("python3", posix_root + "/tools/test_alpha.py"), exe="/usr/bin/python3"
            ),
            "executable": process_record(
                202, argv=(str(root / "bin/worker"),), exe=root / "bin/worker"
            ),
            "cwd": process_record(203, argv=("sleep", "60"), exe="/usr/bin/sleep", cwd=root),
            "web": process_record(
                204, argv=("python3", posix_root + "/python/main.py"), exe="/usr/bin/python3"
            ),
            "bridge": process_record(
                205, argv=("python3", posix_root + "/python/hardware_bridge.py"), exe="/usr/bin/python3"
            ),
            "shell_code": process_record(
                206, argv=("bash", str(root / "tools/run_bx1_os_alpha.sh")), exe="/bin/bash", cwd=root
            ),
            "management": process_record(
                207,
                argv=(
                    "/home/arduino/BX1_OS/.venv/bin/python",
                    "-m",
                    "bx1_management",
                ),
                exe="/usr/bin/python3",
                cwd=root,
            ),
        }
        evidence = self.scan({record["pid"]: record for record in cases.values()})
        self.assertEqual(
            evidence["matching_pids"], [201, 202, 203, 204, 205, 206, 207]
        )
        reasons = {
            item["pid"]: set(item["match_reasons"])
            for item in evidence["matching_processes"]
        }
        self.assertIn("command_path_inside_install_root", reasons[201])
        self.assertIn("executable_inside_install_root", reasons[202])
        self.assertIn("working_directory_inside_install_root", reasons[203])
        self.assertIn("alpha_web_runtime", reasons[204])
        self.assertIn("alpha_hardware_bridge", reasons[205])
        self.assertIn("bx1_management_runtime", reasons[207])

    def test_harmless_shell_cwd_is_not_runtime_but_relative_alpha_code_is(self):
        root = Path("/home/arduino/BX1_OS")
        harmless = process_record(210, argv=("bash",), exe="/bin/bash", cwd=root)
        executing = process_record(
            211, argv=("bash", "tools/run_bx1_os_alpha.sh"), exe="/bin/bash", cwd=root
        )
        evidence = self.scan({210: harmless, 211: executing})
        self.assertEqual(evidence["matching_pids"], [211])

    def test_disappearing_or_unreadable_process_is_reported_without_crash(self):
        evidence = self.scan({301: FileNotFoundError(), 302: PermissionError()})
        self.assertEqual(evidence["matching_pids"], [])
        self.assertEqual(evidence["examined_process_count"], 2)
        self.assertEqual(len(evidence["inspection_errors"]), 2)


if __name__ == "__main__":
    unittest.main()
