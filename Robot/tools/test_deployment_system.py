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
    ):
        del privileged, timeout
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
            self.assertEqual(manifest["default_web_port"], 8089)
            self.assertTrue(manifest["side_by_side"])
            paths = {item["path"] for item in manifest["files"]}
            self.assertIn("service/bx1-os-alpha.service", paths)
            self.assertIn("python/config.alpha-qualification.json", paths)
            self.assertIn("tools/deploy_bx1_os.py", paths)
            self.assertNotIn("service/bx1-web.service", paths)
            self.assertNotIn("tools/install_bx1_web_service.sh", paths)
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
                mock.patch.object(qualification, "_processes_using_root", return_value=[]),
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
                mock.patch.object(qualification, "_processes_using_root", return_value=[123]),
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


if __name__ == "__main__":
    unittest.main()
