from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bx1_services.robot_release_builder import ReleaseBuildOptions, RobotReleaseBuilder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a BX1 Robot Linux release package.")
    parser.add_argument("--source", required=True, help="Explicit Robot Linux source directory.")
    parser.add_argument("--output", required=True, help="Output directory for the release package and sidecars.")
    parser.add_argument("--version", default="", help="Optional version override; must match a source declaration when declarations exist.")
    parser.add_argument("--acknowledge-version-conflict", action="store_true", help="Acknowledge detected version conflicts before using an override.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing release with the same version.")
    parser.add_argument("--yes", action="store_true", help="Confirm package creation non-interactively.")
    args = parser.parse_args(argv)

    builder = RobotReleaseBuilder()
    source_info = builder.inspect_source(Path(args.source))
    print(f"Source: {source_info.source_dir}")
    print(f"Detected version: {source_info.detected_version or 'not found'}")
    for declaration in source_info.declarations:
        print(f"Version declaration: {declaration.path} = {declaration.version}")
    for warning in source_info.warnings + source_info.conflicts:
        print(f"Warning: {warning}")
    if not args.yes:
        response = input("Create this Robot release package? Type YES to continue: ").strip()
        if response != "YES":
            print("Cancelled.")
            return 2
    result = builder.build(
        ReleaseBuildOptions(
            source_dir=Path(args.source),
            output_dir=Path(args.output),
            version_override=args.version,
            acknowledge_version_conflict=args.acknowledge_version_conflict,
            overwrite=args.overwrite,
        ),
        progress=lambda message: print(message),
    )
    print(f"Package: {result.package_path}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Checksums: {result.checksums_path}")
    print(f"Archive SHA256: {result.archive_sha256}")
    print(f"Content checksum: {result.content_checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
