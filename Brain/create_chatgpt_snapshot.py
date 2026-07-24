from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import zipfile

EXCLUDED_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    "models",
    "backups",
    "image_outputs",
    "audio_outputs",
    "cache",
    "downloads",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".wav",
    ".mp3",
    ".flac",
    ".onnx",
    ".pt",
    ".pth",
    ".bin",
}

EXCLUDED_NAME_PREFIXES = (
    ".venv_broken_",
    "BX1_ChatGPT_Snapshot_",
)

def should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)

    for part in rel.parts:
        if part in EXCLUDED_DIRS:
            return True
        if part.startswith(".venv_broken_"):
            return True

    if path.is_file():
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            return True
        if path.name.startswith(EXCLUDED_NAME_PREFIXES):
            return True

    return False

def main() -> int:
    root = Path(__file__).resolve().parent
    if not (root / "main_pyqt.py").exists():
        print("ERROR: This helper must be placed in the Robot_Brain_V1_7_0 folder beside main_pyqt.py.")
        return 2

    snapshots_dir = root / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = snapshots_dir / f"BX1_ChatGPT_Snapshot_{stamp}.zip"

    added = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in root.rglob("*"):
            if path == output:
                continue
            if should_skip(path, root):
                continue
            if not path.is_file():
                continue

            rel = path.relative_to(root)
            archive.write(path, rel)
            added += 1

    print()
    print("Snapshot created successfully.")
    print(f"Files added: {added}")
    print(f"Output: {output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
