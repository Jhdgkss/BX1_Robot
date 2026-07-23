#!/usr/bin/env python3
"""BX1 compatibility entry point.

The Arduino body client application lives in python/main.py.  This wrapper lets
older scripts, manual tests and desktop launchers still run `python main.py`
from the project root.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
PY_DIR = ROOT_DIR / "python"
APP = PY_DIR / "main.py"

if not APP.exists():
    sys.stderr.write(f"[BX1] ERROR: Cannot find application entry point: {APP}\n")
    sys.stderr.write("[BX1] The project folder must contain python/main.py.\n")
    raise SystemExit(2)

sys.path.insert(0, str(PY_DIR))
os.chdir(str(PY_DIR))
runpy.run_path(str(APP), run_name="__main__")
