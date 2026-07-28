from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from ..health import HealthState
from .base import CorePlugin


class DeploymentPlugin(CorePlugin):
    name = "deployment"
    version = "1.0"

    def update(self) -> None:
        context = self._require_context()
        manifest = self._manifest(context.install_root / "release_manifest.json")
        config = context.config
        values = {
            "deployment.version": str(
                manifest.get(
                    "release_version",
                    config.get(
                        "bx1_os_release_version",
                        os.environ.get("BX1_OS_RELEASE_VERSION", "unknown"),
                    ),
                )
            ),
            "deployment.tag": str(
                manifest.get(
                    "source_git_tag",
                    manifest.get(
                        "release_tag",
                        config.get("bx1_os_release_tag", "unknown"),
                    ),
                )
                or config.get("bx1_os_release_tag", "unknown")
            ),
            "deployment.branch": str(
                manifest.get("source_git_branch", "unavailable")
            ),
            "deployment.commit": str(
                manifest.get("source_git_commit", "unavailable")
            ),
            "deployment.build_date": str(
                manifest.get("created_at", "unavailable")
            ),
        }
        context.state.set_many(values, source="plugin.deployment")
        self._set_health(
            HealthState.HEALTHY,
            {
                "reason": (
                    "Release manifest loaded"
                    if manifest
                    else "Release metadata loaded from reviewed configuration"
                ),
                "manifest_available": bool(manifest),
            },
        )

    @staticmethod
    def _manifest(path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}


PLUGIN_CLASS = DeploymentPlugin
