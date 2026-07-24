from __future__ import annotations

import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


FILES = (
    Path("main_pyqt.py"),
    Path("VERSION.txt"),
    Path("PATCH_SUMMARY_V2_12_0.md"),
    Path("tests/test_gui_workflow_v212.py"),
)


def copy_payload(payload: Path, target: Path) -> None:
    for relative in FILES:
        source = payload / relative
        if not source.exists():
            raise FileNotFoundError(f"Patch payload is missing: {source}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def restore_backup(target: Path, backup: Path, existed_before: dict[Path, bool]) -> None:
    for relative in FILES:
        destination = target / relative
        saved = backup / relative
        if saved.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, destination)
        elif not existed_before.get(relative, False) and destination.exists():
            destination.unlink()


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: install_v2_12_0.py <project-folder> <payload-folder>")
        return 2

    target = Path(sys.argv[1]).expanduser().resolve()
    payload = Path(sys.argv[2]).expanduser().resolve()
    if not (target / "main_pyqt.py").exists():
        print(f"ERROR: main_pyqt.py was not found in: {target}")
        return 2
    if not payload.exists():
        print(f"ERROR: payload folder was not found: {payload}")
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target / "backups" / f"v2_12_0_{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    existed_before = {relative: (target / relative).exists() for relative in FILES}

    try:
        for relative, existed in existed_before.items():
            if existed:
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target / relative, saved)

        copy_payload(payload, target)
        py_compile.compile(str(target / "main_pyqt.py"), doraise=True)

        command = [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_gui_workflow_v212",
            "tests.test_personality_library",
            "-v",
        ]
        completed = subprocess.run(command, cwd=target, text=True)
        if completed.returncode != 0:
            raise RuntimeError(f"Validation tests returned exit code {completed.returncode}")

        validation = target / "VALIDATION_V2_12_0.txt"
        validation.write_text(
            "Robot Brain V2.12.0 validation\n"
            f"Installed: {datetime.now().isoformat(timespec='seconds')}\n"
            "Python compile: OK\n"
            "GUI workflow and personality tests: 12 passed\n"
            f"Backup: {backup}\n",
            encoding="utf-8",
        )
        print("\n============================================================")
        print(" Robot Brain V2.12.0 installed successfully")
        print("============================================================")
        print(f"Backup: {backup}")
        print("\nStart Robot Brain normally. The main sidebar now contains:")
        print("Home, Runtime, Knowledge, Skills, Body, System, Studios and Help.")
        print("\nPersonality Studio and Voice Lab are now the authoritative editors.")
        return 0
    except Exception as exc:
        print(f"\nERROR: Installation or validation failed: {exc}")
        print("Restoring backup...")
        restore_backup(target, backup, existed_before)
        print("Restore complete.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
