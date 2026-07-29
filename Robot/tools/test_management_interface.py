#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
sys.path.insert(0, str(PYTHON_ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bx1_management.server import (  # noqa: E402
    ManagementApplication,
    ManagementServer,
    RELEASE_TAG,
    RELEASE_VERSION,
    SPA_ROUTES,
)
import qualify_bx1_alpha as qualification  # noqa: E402


def qualification_config():
    return json.loads(
        (PYTHON_ROOT / "config.alpha-qualification.json").read_text(
            encoding="utf-8"
        )
    )


class ManagementApplicationTests(unittest.TestCase):
    def test_status_supports_canary_qualification_without_hardware_ownership(self):
        application = ManagementApplication(qualification_config())
        status = application.status()
        self.assertTrue(status["ok"])
        self.assertFalse(status["state"]["hardware_ownership"])
        self.assertFalse(status["state"]["actuator_access"])
        self.assertEqual(status["state"]["bridge_mode"], "observer_only")
        bx1_os = status["bx1_os"]
        self.assertEqual(bx1_os["release_version"], RELEASE_VERSION)
        self.assertEqual(bx1_os["release_tag"], RELEASE_TAG)
        self.assertTrue(bx1_os["startup_validated"])
        management = bx1_os["management_interface"]
        self.assertEqual(management["id"], "bx1-os-management")
        self.assertTrue(management["architecture_only"])
        self.assertTrue(management["capabilities"])
        self.assertTrue(
            all(value is False for value in management["capabilities"].values())
        )
        runtime_checks = qualification._runtime_checks(
            status,
            bx1_os,
            bx1_os["startup"],
            "http://127.0.0.1:8089/api/status",
        )
        self.assertTrue(
            all(check.passed for check in runtime_checks),
            [check.name for check in runtime_checks if not check.passed],
        )

    def test_non_observer_configuration_is_rejected(self):
        config = qualification_config()
        config["observer_only"] = False
        with self.assertRaises(ValueError):
            ManagementApplication(config)

    def test_bootstrap_payload_contains_framework_sections_without_controls(self):
        payload = ManagementApplication(qualification_config()).bootstrap_payload()
        self.assertEqual(payload["interface"]["version"], RELEASE_VERSION)
        self.assertIn("system", payload)
        self.assertIn("services", payload)
        self.assertIn("deployment", payload)
        self.assertFalse(any(payload["interface"]["capabilities"].values()))


class ManagementHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = ManagementServer(
            ManagementApplication(qualification_config()),
            host="127.0.0.1",
            port=0,
        )
        self.server.start()
        self.base = "http://127.0.0.1:%s" % self.server.port

    def tearDown(self):
        self.server.stop()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=3) as response:
            return (
                response.status,
                response.headers.get_content_type(),
                response.read(),
            )

    def test_spa_routes_serve_only_the_new_management_document(self):
        for route in sorted(SPA_ROUTES):
            with self.subTest(route=route):
                status, content_type, body = self.get(route)
                self.assertEqual(status, 200)
                self.assertEqual(content_type, "text/html")
                text = body.decode("utf-8")
                self.assertIn("BX1 OS Management", text)
                self.assertNotIn("BX1 Robot Control 10.39", text)

    def test_assets_and_read_only_apis_are_available(self):
        for path, content_type in (
            ("/assets/styles.css", "text/css"),
            ("/assets/app.js", "text/javascript"),
            ("/api/status", "application/json"),
            ("/api/management/bootstrap", "application/json"),
            ("/api/core/state", "application/json"),
            ("/api/core/health", "application/json"),
            ("/api/core/plugins", "application/json"),
            ("/api/core/services", "application/json"),
            ("/api/core/system", "application/json"),
            ("/api/core/hardware", "application/json"),
            ("/api/core/hardware/inventory", "application/json"),
            ("/api/core/audio", "application/json"),
            ("/api/core/audio/devices", "application/json"),
            ("/api/core/robot-body", "application/json"),
            ("/api/core/robot-body/health", "application/json"),
            ("/api/runtime/modules", "application/json"),
            ("/api/runtime/widgets", "application/json"),
            ("/api/core/camera", "application/json"),
        ):
            with self.subTest(path=path):
                status, actual_type, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertEqual(actual_type, content_type)
                self.assertTrue(body)

    def test_unknown_route_and_management_action_fail_closed(self):
        with self.assertRaises(urllib.error.HTTPError) as missing:
            self.get("/not-a-management-route")
        self.assertEqual(missing.exception.code, 404)

        request = urllib.request.Request(
            self.base + "/api/actions/restart",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(rejected.exception.code, 501)
        body = json.loads(rejected.exception.read().decode("utf-8"))
        self.assertEqual(body["error"], "architecture_only")

    def test_reserved_existing_ui_port_is_rejected(self):
        with self.assertRaises(ValueError):
            ManagementServer(
                ManagementApplication(qualification_config()),
                host="127.0.0.1",
                port=8088,
            )

    def test_core_state_supports_incremental_updates(self):
        status, content_type, body = self.get("/api/core/state")
        payload = json.loads(body)
        revision = payload["revision"]
        self.server.application.core.state.set(
            "test.api", "changed", source="test"
        )
        status, content_type, body = self.get(
            "/api/core/state?since=%s" % revision
        )
        update = json.loads(body)
        self.assertEqual(update["schema"], "bx1.core.telemetry.update.v1")
        self.assertIn("test.api", [item["path"] for item in update["changes"]])


class ManagementAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static = PYTHON_ROOT / "bx1_management" / "static"
        cls.html = (cls.static / "index.html").read_text(encoding="utf-8")
        cls.css = (cls.static / "styles.css").read_text(encoding="utf-8")
        cls.javascript = (cls.static / "app.js").read_text(encoding="utf-8")

    def test_navigation_contains_all_required_pages(self):
        required = {
            "Dashboard",
            "System",
            "Services",
            "Hardware",
            "Camera",
            "Audio",
            "Brain",
            "Configuration",
            "Logs",
            "Deployment",
            "Diagnostics",
            "Updates",
            "About",
            "Modules",
        }
        for label in required:
            self.assertIn('label: "%s"' % label, self.javascript)

    def test_dashboard_contains_every_required_card_and_action(self):
        required = {
            "BX1 OS Version",
            "Robot Status",
            "Brain Status",
            "Current Mode",
            "Service Status",
            "CPU",
            "RAM",
            "Disk",
            "Temperature",
            "Network",
            "Robot IP",
            "Uptime",
            "Open Brain",
            "Open Existing Robot UI",
            "Restart BX1 OS",
            "Restart Robot",
            "Shutdown Robot",
        }
        for label in required:
            self.assertIn(label, self.javascript)

    def test_assets_are_responsive_dependency_free_and_separate(self):
        self.assertIn("@media (max-width: 880px)", self.css)
        self.assertIn('data-sidebar="expanded"', self.html)
        self.assertNotIn("bootstrap", self.html.lower())
        self.assertNotIn("https://", self.html)
        self.assertNotIn("web_control", self.javascript)
        server_source = (
            PYTHON_ROOT / "bx1_management" / "server.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from web_control", server_source)
        self.assertNotIn("import web_control", server_source)

    def test_management_ui_reads_only_core_apis(self):
        self.assertIn('"/api/core/state"', self.javascript)
        self.assertIn('"/api/core/health"', self.javascript)
        self.assertIn('"/api/core/plugins"', self.javascript)
        self.assertIn('"/api/core/services"', self.javascript)
        self.assertIn('"/api/core/system"', self.javascript)
        self.assertIn('"/api/core/hardware"', self.javascript)
        self.assertIn('"/api/core/audio"', self.javascript)
        self.assertIn('"/api/core/robot-body"', self.javascript)
        self.assertIn('"/api/core/camera"', self.javascript)
        self.assertNotIn('fetch("/api/management/bootstrap"', self.javascript)
        server_source = (
            PYTHON_ROOT / "bx1_management" / "server.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import platform", server_source)
        self.assertNotIn("import socket", server_source)

    def test_dedicated_unit_launches_management_application_only(self):
        unit = (ROOT / "service" / "bx1-os-alpha.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_bx1_os_management.sh", unit)
        self.assertNotIn("run_bx1_os_alpha.sh", unit)
        self.assertIn("BX1_WEB_PORT=8089", unit)
        self.assertNotIn("BX1_WEB_PORT=8088", unit)


if __name__ == "__main__":
    unittest.main()
