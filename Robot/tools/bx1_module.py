#!/usr/bin/env python3
"""PC workflow: package a module directory, or install its ZIP into a module root."""
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from bx1_runtime import ModuleManager  # noqa: E402

parser = argparse.ArgumentParser()
sub = parser.add_subparsers(dest="command", required=True)
package = sub.add_parser("package"); package.add_argument("module_dir", type=Path); package.add_argument("archive", type=Path)
install = sub.add_parser("install"); install.add_argument("archive", type=Path); install.add_argument("--modules-root", type=Path, default=Path("/home/arduino/BX1_modules")); install.add_argument("--bundled-root", type=Path, default=ROOT / "modules")
args = parser.parse_args()
if args.command == "package":
    source = args.module_dir.resolve()
    if not (source / "module.json").is_file(): parser.error("module_dir must contain module.json")
    with zipfile.ZipFile(args.archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(source.rglob("*")):
            if item.is_file() and "__pycache__" not in item.parts: bundle.write(item, item.relative_to(source).as_posix())
    print(args.archive)
else:
    manager = ModuleManager(args.bundled_root, persistent_root=args.modules_root)
    print(manager.install_zip(args.archive))
