"""
BX1 Project File / Cleanup Utility
==================================

Place this file in the BX1_Dev project root.

Run:
    python generate_project_file_list_v2.py

Functions:
    1 - Generate PROJECT_FILES.txt
    2 - Analyse Python files for possible unused files
    3 - Backup possible unused Python files
    4 - Backup and remove selected possible-unused files

IMPORTANT
---------
"Unused" can never be determined perfectly from static Python analysis.
Dynamic imports, plugins, files loaded by name, tests and deployment tools
can all appear unused when they are actually required.

For that reason:
    - Nothing is removed automatically.
    - Analysis is a DRY RUN.
    - Removal requires an explicit selection.
    - Files are copied to a timestamped backup before removal.
"""

from __future__ import annotations

import ast
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


# ============================================================
# PROJECT SETTINGS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_ROOT / "PROJECT_FILES.txt"

ARCHIVE_ROOT = PROJECT_ROOT / "_archive_unused"

# These are the known application entry points.
# Add another file here if a new executable entry point is introduced.
ENTRY_POINTS = {
    "Master_Main_GUI.py",
    "Master_Main.py",
}

# Files that must never be offered for automatic cleanup.
PROTECTED_FILES = {
    Path(__file__).name,
    "PROJECT_FILES.txt",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
}

# Entire folders that are ignored.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "node_modules",
    "_archive_unused",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".log",
}

# Filenames that commonly represent old copies.
# They are only marked as cleanup candidates; they are not deleted.
BACKUP_NAME_HINTS = (
    "_old",
    "_backup",
    "_bak",
    "_copy",
    "_fixed",
    "_updated",
    "_test",
)

# Names such as:
#     Master_Main(1).py
#     config(2).py
# are often duplicate downloads.
DUPLICATE_COPY_PATTERN_CHARS = ("(", ")")


# ============================================================
# GENERAL FILE HELPERS
# ============================================================

def relative(path: Path) -> Path:
    return path.relative_to(PROJECT_ROOT)


def should_include(path: Path) -> bool:
    try:
        rel = relative(path)
    except ValueError:
        return False

    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False

    if path.name in {OUTPUT_FILE.name}:
        return False

    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False

    return path.is_file()


def project_files() -> List[Path]:
    return sorted(
        (
            path
            for path in PROJECT_ROOT.rglob("*")
            if should_include(path)
        ),
        key=lambda path: str(relative(path)).lower(),
    )


def python_files() -> List[Path]:
    return [
        path
        for path in project_files()
        if path.suffix.lower() == ".py"
    ]


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.1f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


# ============================================================
# PYTHON MODULE MAPPING
# ============================================================

def module_name_for_file(path: Path) -> Optional[str]:
    """
    Convert:
        settings/config.py       -> settings.config
        GUI/gui_main.py          -> GUI.gui_main
        sound_effects.py         -> sound_effects
        GUI/__init__.py          -> GUI
    """
    if path.suffix.lower() != ".py":
        return None

    rel = relative(path)

    parts = list(rel.with_suffix("").parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]

    if not parts:
        return None

    return ".".join(parts)


def build_module_map(files: Iterable[Path]) -> Dict[str, Path]:
    result: Dict[str, Path] = {}

    for path in files:
        module = module_name_for_file(path)

        if module:
            result[module] = path

    return result


def package_for_file(path: Path) -> str:
    module = module_name_for_file(path) or ""

    if path.name == "__init__.py":
        return module

    if "." in module:
        return module.rsplit(".", 1)[0]

    return ""


# ============================================================
# IMPORT ANALYSIS
# ============================================================

def resolve_relative_import(
    current_file: Path,
    node: ast.ImportFrom,
) -> Optional[str]:
    """
    Resolve relative imports such as:
        from .gui_controller import GUIController
        from ..settings import config
    """
    if node.level <= 0:
        return node.module

    package = package_for_file(current_file)

    package_parts = package.split(".") if package else []

    # level=1 means current package, level=2 means parent package, etc.
    climb = node.level - 1

    if climb > len(package_parts):
        return None

    if climb:
        package_parts = package_parts[:-climb]

    if node.module:
        package_parts.extend(node.module.split("."))

    return ".".join(part for part in package_parts if part)


def imported_local_modules(
    path: Path,
    module_map: Dict[str, Path],
) -> Set[str]:
    """
    Return local project modules referenced by a Python file.
    """
    found: Set[str] = set()

    try:
        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        tree = ast.parse(source, filename=str(path))
    except Exception:
        return found

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name

                # Exact module.
                if name in module_map:
                    found.add(name)

                # Importing a package can imply its __init__.py.
                pieces = name.split(".")
                for count in range(1, len(pieces)):
                    parent = ".".join(pieces[:count])
                    if parent in module_map:
                        found.add(parent)

        elif isinstance(node, ast.ImportFrom):
            base = resolve_relative_import(
                path,
                node,
            )

            if base and base in module_map:
                found.add(base)

            # "from settings import config" often references
            # settings.config rather than only settings.
            for alias in node.names:
                if alias.name == "*":
                    continue

                candidate = (
                    f"{base}.{alias.name}"
                    if base
                    else alias.name
                )

                if candidate in module_map:
                    found.add(candidate)

    return found


def dependency_graph(
    files: List[Path],
) -> Tuple[
    Dict[str, Path],
    Dict[str, Set[str]],
]:
    module_map = build_module_map(files)

    graph: Dict[str, Set[str]] = {}

    for module, path in module_map.items():
        graph[module] = imported_local_modules(
            path,
            module_map,
        )

    return module_map, graph


def entry_modules(
    module_map: Dict[str, Path],
) -> Set[str]:
    entries: Set[str] = set()

    for module, path in module_map.items():
        if relative(path).as_posix() in ENTRY_POINTS:
            entries.add(module)

    return entries


def reachable_modules(
    graph: Dict[str, Set[str]],
    starts: Set[str],
) -> Set[str]:
    reached: Set[str] = set()
    stack = list(starts)

    while stack:
        module = stack.pop()

        if module in reached:
            continue

        reached.add(module)

        for dependency in graph.get(module, set()):
            if dependency not in reached:
                stack.append(dependency)

    return reached


# ============================================================
# CLEANUP CANDIDATE ANALYSIS
# ============================================================

def looks_like_old_copy(path: Path) -> bool:
    stem = path.stem.lower()

    if any(hint in stem for hint in BACKUP_NAME_HINTS):
        return True

    if all(char in path.name for char in DUPLICATE_COPY_PATTERN_CHARS):
        return True

    return False


def analyse_python_usage():
    files = python_files()
    module_map, graph = dependency_graph(files)

    entries = entry_modules(module_map)

    reached = reachable_modules(
        graph,
        entries,
    )

    used_paths = {
        module_map[module]
        for module in reached
        if module in module_map
    }

    candidates = []

    for path in files:
        rel = relative(path)

        if rel.as_posix() in ENTRY_POINTS:
            continue

        if path.name in PROTECTED_FILES:
            continue

        # Package __init__.py files are kept by default.
        if path.name == "__init__.py":
            continue

        if path not in used_paths:
            reasons = [
                "not reachable from configured entry points"
            ]

            if looks_like_old_copy(path):
                reasons.append(
                    "filename also looks like an old/duplicate copy"
                )

            candidates.append(
                {
                    "path": path,
                    "relative": rel,
                    "reasons": reasons,
                }
            )

    return {
        "files": files,
        "module_map": module_map,
        "graph": graph,
        "entries": entries,
        "reached": reached,
        "used_paths": used_paths,
        "candidates": candidates,
    }


# ============================================================
# MANIFEST
# ============================================================

def generate_manifest():
    files = project_files()

    analysis = analyse_python_usage()

    used_paths = analysis["used_paths"]

    candidate_paths = {
        item["path"]
        for item in analysis["candidates"]
    }

    lines = [
        "BX1_DEV PROJECT FILE MANIFEST",
        "=" * 80,
        "",
        f"Project root : {PROJECT_ROOT}",
        f"Generated    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Files found  : {len(files)}",
        "",
        "Python status:",
        "  USED       = reachable from configured Python entry points",
        "  CANDIDATE  = not found in that static dependency chain",
        "  -          = non-Python file / not analysed",
        "",
        "IMPORTANT:",
        "CANDIDATE does not prove that a file is unused.",
        "Dynamic imports and external/deployment scripts cannot always be detected.",
        "",
    ]

    current_folder = None

    for path in files:
        rel = relative(path)
        folder = str(rel.parent)

        if folder == ".":
            folder = "[PROJECT ROOT]"

        if folder != current_folder:
            lines.append("")
            lines.append(folder)
            lines.append("-" * len(folder))
            current_folder = folder

        if path.suffix.lower() == ".py":
            if path in candidate_paths:
                status = "CANDIDATE"
            elif path in used_paths or rel.as_posix() in ENTRY_POINTS:
                status = "USED"
            else:
                status = "KEEP"
        else:
            status = "-"

        try:
            size = format_size(
                path.stat().st_size
            )
        except OSError:
            size = "unknown"

        lines.append(
            f"[{status:<9}] "
            f"{rel.name:<52} "
            f"{size:>12}"
        )

    lines.extend(
        [
            "",
            "=" * 80,
            "End of manifest",
            "",
        ]
    )

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print("Project file manifest created:")
    print(OUTPUT_FILE)
    print()
    print(f"{len(files)} files listed.")
    print()


# ============================================================
# DISPLAY CANDIDATES
# ============================================================

def show_candidates(analysis=None):
    if analysis is None:
        analysis = analyse_python_usage()

    candidates = analysis["candidates"]

    print()
    print("=" * 80)
    print("POSSIBLE UNUSED PYTHON FILES")
    print("=" * 80)
    print()

    print("Entry points:")
    for entry in sorted(ENTRY_POINTS):
        print(f"  - {entry}")

    print()

    if not candidates:
        print("No possible-unused Python files were found.")
        print()
        return analysis

    print(
        "These are candidates only. "
        "Static analysis cannot guarantee that they are unused."
    )
    print()

    for index, item in enumerate(
        candidates,
        start=1,
    ):
        print(
            f"{index:>3}. "
            f"{item['relative']}"
        )

        for reason in item["reasons"]:
            print(
                f"     - {reason}"
            )

    print()

    return analysis


# ============================================================
# BACKUP / REMOVE
# ============================================================

def parse_selection(
    text: str,
    candidate_count: int,
) -> List[int]:
    """
    Accept:
        1
        1,3,5
        2-6
        all
    """
    value = text.strip().lower()

    if value == "all":
        return list(
            range(candidate_count)
        )

    selected: Set[int] = set()

    for part in value.split(","):
        part = part.strip()

        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split(
                "-",
                1,
            )

            start = int(start_text)
            end = int(end_text)

            if start > end:
                start, end = end, start

            for number in range(
                start,
                end + 1,
            ):
                if 1 <= number <= candidate_count:
                    selected.add(number - 1)

        else:
            number = int(part)

            if 1 <= number <= candidate_count:
                selected.add(number - 1)

    return sorted(selected)


def choose_candidates(
    analysis,
) -> List[dict]:
    candidates = analysis["candidates"]

    if not candidates:
        return []

    print(
        "Select file numbers to process."
    )
    print(
        "Examples: 1   1,3,5   2-6   all"
    )
    print(
        "Press Enter to cancel."
    )
    print()

    selection = input(
        "Selection > "
    ).strip()

    if not selection:
        return []

    try:
        indexes = parse_selection(
            selection,
            len(candidates),
        )
    except ValueError:
        print()
        print("Invalid selection.")
        return []

    return [
        candidates[index]
        for index in indexes
    ]


def make_archive_folder() -> Path:
    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    archive = ARCHIVE_ROOT / stamp
    archive.mkdir(
        parents=True,
        exist_ok=False,
    )

    return archive


def backup_items(
    items: List[dict],
    *,
    remove_originals: bool,
):
    if not items:
        print()
        print("Nothing selected.")
        print()
        return

    print()
    print("Selected files:")
    for item in items:
        print(
            f"  - {item['relative']}"
        )

    print()

    if remove_originals:
        print(
            "Mode: BACKUP THEN REMOVE ORIGINALS"
        )
    else:
        print(
            "Mode: BACKUP ONLY"
        )

    print()

    confirmation = input(
        "Type YES to continue > "
    ).strip()

    if confirmation != "YES":
        print()
        print("Cancelled. No files changed.")
        print()
        return

    archive = make_archive_folder()

    manifest_lines = [
        "BX1 UNUSED FILE BACKUP",
        "=" * 70,
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        f"Original project: {PROJECT_ROOT}",
        "",
    ]

    copied = []

    try:
        for item in items:
            source = item["path"]
            rel = item["relative"]

            destination = archive / rel
            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                source,
                destination,
            )

            copied.append(
                (source, destination)
            )

            manifest_lines.append(
                f"{rel}"
            )

        backup_manifest = (
            archive
            / "BACKUP_MANIFEST.txt"
        )

        backup_manifest.write_text(
            "\n".join(manifest_lines) + "\n",
            encoding="utf-8",
        )

        if remove_originals:
            # Only remove originals after every backup copy succeeded.
            for source, _destination in copied:
                source.unlink()

        print()
        print(
            f"Backup created: {archive}"
        )

        if remove_originals:
            print(
                f"{len(copied)} original file(s) removed "
                "after successful backup."
            )
        else:
            print(
                f"{len(copied)} file(s) backed up. "
                "Originals were left untouched."
            )

        print()

    except Exception as exc:
        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )
        print(
            "No additional originals will be removed."
        )
        print()


# ============================================================
# MENU
# ============================================================

def main():
    while True:
        print()
        print("=" * 70)
        print("BX1 PROJECT FILE / CLEANUP UTILITY")
        print("=" * 70)
        print()
        print("1 - Generate project file manifest")
        print("2 - Analyse possible unused Python files")
        print("3 - Backup selected possible-unused files")
        print("4 - Backup AND remove selected possible-unused files")
        print("5 - Exit")
        print()

        choice = input(
            "Option > "
        ).strip()

        if choice == "1":
            generate_manifest()

        elif choice == "2":
            show_candidates()

        elif choice in {"3", "4"}:
            analysis = show_candidates()
            selected = choose_candidates(
                analysis
            )

            backup_items(
                selected,
                remove_originals=(
                    choice == "4"
                ),
            )

            # Regenerate manifest after an actual removal.
            if choice == "4":
                generate_manifest()

        elif choice == "5":
            print()
            print("Finished.")
            print()
            break

        else:
            print()
            print("Please choose 1 to 5.")
            print()


if __name__ == "__main__":
    main()