from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict

from bx1_capabilities.manifest import load_manifest
from bx1_capabilities.models import CapabilityRunResult


RUNNER_CODE = r"""
import contextlib
import importlib.util
import io
import json
import os
import sys

package_dir = sys.argv[1]
action = sys.argv[2]
payload = json.loads(sys.stdin.read() or "{}")
module_path = os.path.join(package_dir, "capability.py")
spec = importlib.util.spec_from_file_location("bx1_runtime_capability", module_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
for name in ("get_capability_metadata", "validate_settings", "execute", "shutdown"):
    if not hasattr(module, name):
        raise RuntimeError(f"Capability missing required function: {name}")
settings = payload.get("settings") or {}
parameters = payload.get("parameters") or {}
context = payload.get("context") or {}
module.validate_settings(settings)
stdout = io.StringIO()
stderr = io.StringIO()
try:
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = module.execute(action, parameters, context)
finally:
    with contextlib.suppress(Exception):
        module.shutdown()
print(json.dumps({"ok": True, "result": result or {}, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}))
"""


class CapabilityRunner:
    def run(self, package_dir: Path, action: str, parameters: Dict[str, Any] | None = None, context: Dict[str, Any] | None = None, settings: Dict[str, Any] | None = None, *, confirmed: bool = False) -> CapabilityRunResult:
        package_dir = Path(package_dir)
        manifest = load_manifest(package_dir / "manifest.json")
        action_meta = next((item for item in manifest.actions if item.action_id == action), None)
        if action_meta is None:
            return CapabilityRunResult(False, manifest.capability_id, action, error="unknown_action", message=f"Unknown action: {action}")
        if action_meta.confirmation_required and not confirmed:
            return CapabilityRunResult(False, manifest.capability_id, action, error="confirmation_required", message="Action requires confirmation.", requires_confirmation=True)
        started = time.perf_counter()
        env = {"PYTHONIOENCODING": "utf-8", "BX1_CAPABILITY_MODE": "1"}
        payload = {"parameters": parameters or {}, "context": context or {}, "settings": settings or {}}
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", RUNNER_CODE, str(package_dir), action],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=float(manifest.timeout_seconds),
                cwd=str(package_dir),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return CapabilityRunResult(False, manifest.capability_id, action, error="timeout", message="Capability execution timed out.", duration_s=time.perf_counter() - started, stdout=exc.stdout or "", stderr=exc.stderr or "")
        duration = time.perf_counter() - started
        if proc.returncode != 0:
            return CapabilityRunResult(False, manifest.capability_id, action, error="worker_failed", message="Capability worker failed.", duration_s=duration, stdout=proc.stdout, stderr=proc.stderr)
        try:
            envelope = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception as exc:
            return CapabilityRunResult(False, manifest.capability_id, action, error="bad_worker_output", message=str(exc), duration_s=duration, stdout=proc.stdout, stderr=proc.stderr)
        result = envelope.get("result") if isinstance(envelope, dict) else {}
        ok = bool(result.get("ok", envelope.get("ok", False))) if isinstance(result, dict) else bool(envelope.get("ok", False))
        return CapabilityRunResult(
            ok,
            manifest.capability_id,
            action,
            data=result if isinstance(result, dict) else {"value": result},
            message=str(result.get("message") or "" if isinstance(result, dict) else ""),
            error=str(result.get("error") or "" if isinstance(result, dict) else ""),
            duration_s=duration,
            stdout=str(envelope.get("stdout") or ""),
            stderr=str(envelope.get("stderr") or ""),
        )

