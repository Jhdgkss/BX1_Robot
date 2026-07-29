#!/usr/bin/env python3
"""Create a safe BX1 v0.7 module skeleton; it never grants hardware access."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("--modules-root", type=Path, default=Path("Robot/modules"))
args = parser.parse_args()
identifier = args.name.strip().lower().replace("-", "_")
if not identifier.isidentifier():
    parser.error("name must become a lowercase Python identifier")
target = args.modules_root / identifier
target.mkdir(parents=True, exist_ok=False)
(target / "module.json").write_text(json.dumps({"schema": "bx1.module.manifest.v1", "id": identifier, "name": args.name, "version": "0.1.0", "entrypoint": "module.py:Module", "capabilities": ["events.publish"], "subscriptions": []}, indent=2) + "\n", encoding="utf-8")
(target / "module.py").write_text("class Module:\n    def start(self, context):\n        self.context = context\n    def health(self):\n        return {'state': 'healthy'}\n    def stop(self):\n        pass\n", encoding="utf-8")
print(target)
