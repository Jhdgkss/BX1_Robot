#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from bx1_runtime import ModuleManager  # noqa: E402


class ModulePlatformTests(unittest.TestCase):
    def test_fallback_console_is_browser_session_only_and_installer_prepares_owned_dirs(self):
        app = (ROOT / "python" / "bx1_management" / "static" / "app.js").read_text(encoding="utf-8")
        deployer = (ROOT / "tools" / "deploy_bx1_os.py").read_text(encoding="utf-8")
        self.assertIn("Manual fallback conversation", app)
        self.assertIn("talk-repeat", app)
        self.assertIn("state.conversation", app)
        self.assertIn("/api/runtime/widgets", app)
        self.assertIn("os.chmod(directory, 0o750)", deployer)
        self.assertIn("os.chown(directory, account.pw_uid, account.pw_gid)", deployer)
    def make_zip(self, root: Path, identifier="user_widget") -> Path:
        source = root / "source"; source.mkdir()
        (source / "module.json").write_text(json.dumps({"schema":"bx1.module.manifest.v1","id":identifier,"name":"User widget","version":"1","entrypoint":"module.py:Module","capabilities":["widgets.publish","widgets.action"],"subscriptions":[]}), encoding="utf-8")
        (source / "module.py").write_text("class Module:\n def start(self,c):\n  c.widget({'id':'card','type':'metric','title':'Safe','placement':'dashboard','data':{'value':1}}); c.action('ping',lambda fields:{'ok':True})\n def health(self): return {'state':'healthy'}\n def stop(self): pass\n", encoding="utf-8")
        archive = root / "module.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            for item in source.iterdir(): bundle.write(item, item.name)
        return archive
    def test_install_persist_reload_controls_and_widgets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); user = root / "user"; manager = ModuleManager(root / "bundled", persistent_root=user)
            manager.install_zip(self.make_zip(root))
            self.assertTrue((user / "user_widget" / "module.json").is_file())
            self.assertEqual(manager.widgets_snapshot()["widgets"][0]["module_id"], "user_widget")
            self.assertTrue(manager.invoke_action("user_widget", "ping", {})["ok"])
            self.assertEqual(manager.set_enabled("user_widget", False)["modules"][0]["state"], "disabled")
            self.assertEqual(manager.set_enabled("user_widget", True)["modules"][0]["state"], "healthy")
            self.assertEqual(manager.remove("user_widget")["modules"], [])
    def test_zip_traversal_and_led_boundary_are_rejected_or_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle: bundle.writestr("../module.json", "{}")
            with self.assertRaises(ValueError): ModuleManager(root / "bundled", persistent_root=root / "user").install_zip(archive)
            manager = ModuleManager(ROOT / "modules", persistent_root=root / "user")
            manager.load_all(); battery = next(item for item in manager.snapshot()["modules"] if item["id"] == "battery_led")
            self.assertIn("led.status.request", battery["capabilities"])
            self.assertEqual(battery["health"]["led"], "status-request only")

if __name__ == "__main__": unittest.main()
