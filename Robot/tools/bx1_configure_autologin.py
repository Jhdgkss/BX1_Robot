#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


def update_ini(path: Path, section: str, values: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    section_re = re.compile(r"^\s*\[([^]]+)\]\s*$")
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        match = section_re.match(line)
        if not match:
            continue
        if start is None and match.group(1).strip().lower() == section.lower():
            start = idx
            continue
        if start is not None:
            end = idx
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        start = len(lines) - 1
        end = len(lines)
    for key, value in values.items():
        key_re = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=", re.I)
        replaced = False
        for idx in range(start + 1, end):
            if key_re.match(lines[idx]):
                lines[idx] = f"{key}={value}"
                replaced = True
                break
        if not replaced:
            lines.insert(end, f"{key}={value}")
            end += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def backup(path: Path, backup_dir: Path) -> None:
    if path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)


def manager_name() -> str:
    service = Path("/etc/systemd/system/display-manager.service")
    try:
        target = os.path.basename(os.path.realpath(service))
    except OSError:
        target = ""
    low = target.lower()
    for name in ("gdm3", "gdm", "lightdm", "sddm", "lxdm"):
        if name in low:
            return name
    for name, path in (
        ("gdm3", Path("/etc/gdm3")),
        ("lightdm", Path("/etc/lightdm")),
        ("sddm", Path("/etc/sddm.conf.d")),
        ("lxdm", Path("/etc/lxdm")),
    ):
        if path.exists():
            return name
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--force-xorg", action="store_true")
    args = parser.parse_args()
    backup_dir = Path(args.backup_dir)
    manager = manager_name()

    if manager in {"gdm", "gdm3"}:
        candidates = [Path("/etc/gdm3/daemon.conf"), Path("/etc/gdm3/custom.conf"), Path("/etc/gdm/custom.conf")]
        path = next((item for item in candidates if item.exists()), candidates[0])
        backup(path, backup_dir)
        values = {"AutomaticLoginEnable": "true", "AutomaticLogin": args.user}
        if args.force_xorg:
            values["WaylandEnable"] = "false"
        update_ini(path, "daemon", values)
    elif manager == "lightdm":
        path = Path("/etc/lightdm/lightdm.conf.d/50-bx1-autologin.conf")
        backup(path, backup_dir)
        update_ini(path, "Seat:*", {"autologin-user": args.user, "autologin-user-timeout": "0"})
    elif manager == "sddm":
        path = Path("/etc/sddm.conf.d/50-bx1-autologin.conf")
        backup(path, backup_dir)
        update_ini(path, "Autologin", {"User": args.user, "Relogin": "true"})
    elif manager == "lxdm":
        path = Path("/etc/lxdm/lxdm.conf")
        backup(path, backup_dir)
        update_ini(path, "base", {"autologin": args.user})
    else:
        print("DISPLAY_MANAGER=unknown")
        print("CONFIG_PATH=")
        return 4

    print(f"DISPLAY_MANAGER={manager}")
    print(f"CONFIG_PATH={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
