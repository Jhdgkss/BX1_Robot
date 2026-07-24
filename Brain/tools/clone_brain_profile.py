from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_").lower()


def rewrite_profile_paths(value: Any, source: str, target: str) -> Any:
    """Make copied runtime references portable and point them at the target profile."""
    if isinstance(value, dict):
        return {key: rewrite_profile_paths(item, source, target) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_profile_paths(item, source, target) for item in value]
    if not isinstance(value, str) or not value:
        return value

    # Convert absolute or relative references ending in runtime/<source>/... into
    # project-relative runtime/<target>/... paths. This prevents a copied voice
    # profile retaining an obsolete absolute project folder.
    marker = re.compile(rf"(?:^|.*[\\/])runtime[\\/]+{re.escape(source)}(?:[\\/]+(?P<tail>.*))?$", re.IGNORECASE)
    match = marker.match(value.strip())
    if match:
        tail = (match.group("tail") or "").replace("\\", "/").lstrip("/")
        return f"runtime/{target}" + (f"/{tail}" if tail else "")

    return re.sub(
        rf"(?i)(?<![A-Za-z0-9_-])runtime[\\/]+{re.escape(source)}(?=[\\/]|$)",
        f"runtime/{target}",
        value,
    )


def update_json_profile(path: Path, source: str, target: str, robot_name: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = rewrite_profile_paths(data, source, target)
    if path.name.startswith("app_config_"):
        data["brain_profile"] = target
        if robot_name:
            data["robot_name"] = robot_name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clone one Robot Brain configuration/runtime profile into another.")
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--robot-name", default="")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    source, target = safe_slug(args.source), safe_slug(args.target)
    if not source or not target or source == target:
        raise SystemExit("Source and target profiles must be different valid names.")

    config_dir = root / "config"
    runtime_dir = root / "runtime"
    pairs = [
        (config_dir / f"app_config_{source}.json", config_dir / f"app_config_{target}.json"),
        (config_dir / f"secrets_{source}.local.json", config_dir / f"secrets_{target}.local.json"),
    ]

    for src, dst in pairs:
        if not src.exists():
            continue
        if dst.exists() and not args.overwrite:
            print(f"Kept existing: {dst}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if dst.suffix.lower() == ".json":
            update_json_profile(dst, source, target, args.robot_name.strip())
        print(f"Created: {dst}")

    src_runtime, dst_runtime = runtime_dir / source, runtime_dir / target
    if src_runtime.exists() and (args.overwrite or not dst_runtime.exists()):
        if dst_runtime.exists():
            shutil.rmtree(dst_runtime)
        shutil.copytree(src_runtime, dst_runtime)
        print(f"Copied runtime: {src_runtime} -> {dst_runtime}")
    elif src_runtime.exists():
        print(f"Kept existing runtime: {dst_runtime}")
    else:
        dst_runtime.mkdir(parents=True, exist_ok=True)
        print(f"Created empty runtime: {dst_runtime}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
