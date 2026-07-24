from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, List

from bx1_capabilities.models import CapabilitySecurityError


SAFE_IMPORTS = {
    "dataclasses",
    "datetime",
    "hashlib",
    "json",
    "math",
    "re",
    "typing",
    "uuid",
}
PROHIBITED_IMPORTS = {"subprocess", "socket", "ctypes", "winreg", "importlib", "os", "sys", "pathlib", "shutil", "requests", "urllib", "pip"}
PROHIBITED_CALLS = {"eval", "exec", "compile", "__import__"}
SECRET_PATTERNS = (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), re.compile(r"(?i)(api[_-]?key|token|password)\s*=\s*['\"][^'\"]{8,}['\"]"))


def scan_text_for_secrets(text: str) -> List[str]:
    return ["Potential embedded secret detected."] if any(pattern.search(text) for pattern in SECRET_PATTERNS) else []


def scan_capability_source(path: Path) -> List[str]:
    text = Path(path).read_text(encoding="utf-8")
    errors = scan_text_for_secrets(text)
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise CapabilitySecurityError(f"Syntax error: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in PROHIBITED_IMPORTS or root not in SAFE_IMPORTS:
                    errors.append(f"Import is not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in PROHIBITED_IMPORTS or root not in SAFE_IMPORTS:
                errors.append(f"Import is not allowed: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in PROHIBITED_CALLS:
                errors.append(f"Call is not allowed: {name}")
            if name in {"system", "popen"}:
                errors.append(f"Shell/process call is not allowed: {name}")
            for keyword in getattr(node, "keywords", []):
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    errors.append("shell=True is not allowed.")
        elif isinstance(node, ast.Attribute):
            if node.attr in {"__dict__", "__class__", "__subclasses__", "__globals__"}:
                errors.append(f"Introspection attribute is not allowed: {node.attr}")
    if errors:
        raise CapabilitySecurityError("; ".join(errors))
    return []

