#!/usr/bin/env python3
"""Add or remove the ycc entry in Codex's marketplace file.

Called by scripts/lib/install/targets/codex.sh:

    codex_marketplace.py merge <dest> <local|repo> [<plugin_src>]
    codex_marketplace.py remove <dest>

Local plugin paths resolve from the marketplace root (the directory holding
.agents/plugins/marketplace.json, i.e. $HOME), so they must start with ``./``,
e.g. ``./.agents/plugins/ycc``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MARKETPLACE_NAME = "local-ycc-plugins"
INTERFACE = {"displayName": "Local YCC Plugins"}
SCAFFOLD = {"name": MARKETPLACE_NAME, "interface": INTERFACE, "plugins": []}
USAGE = "usage: codex_marketplace.py merge <dest> <local|repo> [<plugin_src>] | remove <dest>"


def _is_ycc(item: object) -> bool:
    return isinstance(item, dict) and item.get("name") == "ycc"


def build_entry(mode: str, plugin_src: str) -> dict[str, Any]:
    if mode == "local":
        if not plugin_src.startswith("./"):
            sys.stderr.write("error: Codex local plugin source path must start with ./\n")
            sys.exit(1)
        source_block = {"source": "local", "path": plugin_src}
    elif mode == "repo":
        source_block = {
            "source": "git-subdir",
            "url": "https://github.com/yandy-r/claude-plugins.git",
            "path": "./.codex-plugin/ycc",
            "ref": "main",
        }
    else:
        sys.stderr.write(f"error: unsupported mode '{mode}'\n")
        sys.exit(1)
    return {
        "name": "ycc",
        "source": source_block,
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }


def merge(dest_path: Path, mode: str, plugin_src: str) -> None:
    entry = build_entry(mode, plugin_src)

    if dest_path.exists():
        with open(dest_path, encoding="utf-8") as handle:
            current = json.load(handle)
        if not isinstance(current, dict):
            raise SystemExit(f"{dest_path} must contain a JSON object")
    else:
        current = {}

    name = current.get("name")
    marketplace_name = name if isinstance(name, str) and name.strip() else MARKETPLACE_NAME
    interface = current.get("interface")
    if interface is None:
        interface = dict(INTERFACE)
    elif not isinstance(interface, dict):
        raise SystemExit(f"{dest_path}: interface must be an object when present")

    plugins = current.get("plugins")
    if plugins is None:
        plugins = []
    elif not isinstance(plugins, list):
        raise SystemExit(f"{dest_path}: plugins must be an array when present")

    for index, item in enumerate(plugins):
        if _is_ycc(item):
            plugins[index] = entry
            break
    else:
        plugins.append(entry)

    merged = {**current, "name": marketplace_name, "interface": interface, "plugins": plugins}
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def remove(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list) or not any(_is_ycc(p) for p in plugins):
        print(f"  [ok] nothing to remove: {path}")
        return
    data["plugins"] = [p for p in plugins if not _is_ycc(p)]
    if data == SCAFFOLD:
        path.unlink()
        print(f"  [ok] removed {path} (only the ycc entry was left)")
    else:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  [ok] removed the ycc entry from {path}")


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "merge":
        merge(Path(argv[1]), argv[2], argv[3] if len(argv) > 3 else "")
        return 0
    if len(argv) == 2 and argv[0] == "remove":
        remove(Path(argv[1]))
        return 0
    sys.stderr.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
