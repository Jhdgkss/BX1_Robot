from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import List

from bx1_capabilities.models import CapabilitySecurityError, CapabilityValidationError


MAX_PACKAGE_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
REQUIRED_FILES = ("manifest.json", "capability.py", "tests.py", "README.md")
EXCLUDED_PARTS = {".git", "__pycache__", ".venv", "venv", "env", ".pytest_cache", "node_modules"}
FORBIDDEN_SUFFIXES = {".exe", ".bat", ".cmd", ".ps1", ".pem", ".key", ".pfx", ".pyc", ".pyo"}


def safe_relative_path(value: str) -> str:
    path = str(value or "").replace("\\", "/").strip()
    if not path or path.startswith("/") or path.startswith("~") or re.match(r"^[A-Za-z]:", path) or ".." in path.split("/"):
        raise CapabilityValidationError(f"Unsafe package path: {value}")
    if any(part in EXCLUDED_PARTS for part in path.split("/")):
        raise CapabilityValidationError(f"Excluded package path: {value}")
    if Path(path).suffix.lower() in FORBIDDEN_SUFFIXES:
        raise CapabilityValidationError(f"Forbidden package file type: {value}")
    return path


def validate_package_folder(folder: Path) -> None:
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise CapabilityValidationError(f"Capability folder not found: {folder}")
    for required in REQUIRED_FILES:
        if not (folder / required).is_file():
            raise CapabilityValidationError(f"Capability package missing {required}.")
    for root, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        root_path = Path(root)
        kept_dirs = []
        for dirname in dirs:
            if dirname in EXCLUDED_PARTS:
                continue
            rel = safe_relative_path(str((root_path / dirname).relative_to(folder)))
            child = root_path / dirname
            if child.is_symlink():
                if not child.resolve().is_relative_to(folder):
                    raise CapabilitySecurityError(f"Symlink escapes package: {rel}")
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for filename in files:
            child = root_path / filename
            rel = safe_relative_path(str(child.relative_to(folder)))
            if child.is_symlink():
                if not child.resolve().is_relative_to(folder):
                    raise CapabilitySecurityError(f"Symlink escapes package: {rel}")
                continue
            if child.stat().st_size > MAX_FILE_BYTES:
                raise CapabilityValidationError(f"Capability file is too large: {rel}")


def import_zip_to_folder(zip_path: Path, destination_root: Path) -> Path:
    zip_path = Path(zip_path)
    if zip_path.stat().st_size > MAX_PACKAGE_BYTES:
        raise CapabilityValidationError("Capability archive exceeds size limit.")
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        roots = {safe_relative_path(name).split("/", 1)[0] for name in names if not name.endswith("/")}
        if len(roots) != 1:
            raise CapabilityValidationError("Capability archive must contain exactly one top-level folder.")
        root = next(iter(roots))
        target = Path(destination_root) / root
        if target.exists():
            shutil.rmtree(target)
        for info in archive.infolist():
            name = safe_relative_path(info.filename)
            if name in seen:
                raise CapabilityValidationError(f"Duplicate archive entry: {name}")
            seen.add(name)
            if info.is_dir():
                continue
            if info.file_size > MAX_FILE_BYTES:
                raise CapabilityValidationError(f"Archive entry is too large: {name}")
            out = (Path(destination_root) / name).resolve()
            if not out.is_relative_to(Path(destination_root).resolve()):
                raise CapabilityValidationError(f"Archive entry escapes destination: {name}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(info))
    validate_package_folder(target)
    return target


def export_folder_to_zip(folder: Path, output_zip: Path) -> Path:
    validate_package_folder(folder)
    folder = Path(folder).resolve()
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            package_rel = path.relative_to(folder)
            if any(part in EXCLUDED_PARTS for part in package_rel.parts):
                continue
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                continue
            rel = safe_relative_path(str(path.relative_to(folder.parent)))
            archive.write(path, rel)
    return output_zip
