#!/usr/bin/env python3
"""List or merge the MCP servers bundled beside this helper into a project mcp.json.

Only the selected server definitions are written; other servers and top-level
keys are preserved. Bare plugin ``${VAR}`` placeholders become standalone
``${env:VAR}`` references without reading the environment. Existing ``${env:VAR}``
references stay unchanged. A differing existing server is a conflict unless
``--force`` is given.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

BUNDLED = Path(__file__).resolve().parent / "mcp.json"


def load_servers(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        raise ValueError(f"{path}: missing mcpServers object")
    return servers


def transport(server: dict[str, Any]) -> str:
    return str(server.get("type") or ("stdio" if "command" in server else "unknown"))


BUNDLED_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def standalone(value: Any) -> Any:
    """Rewrite bare ``${VAR}`` to ``${env:VAR}`` for standalone Cursor config."""
    if isinstance(value, str):
        return BUNDLED_PLACEHOLDER.sub(r"${env:\1}", value)
    if isinstance(value, dict):
        return {key: standalone(item) for key, item in value.items()}
    if isinstance(value, list):
        return [standalone(item) for item in value]
    return value


def standalone_servers(bundled: dict[str, Any]) -> dict[str, Any]:
    return {name: standalone(server) for name, server in bundled.items()}


def catalog(servers: dict[str, Any]) -> str:
    lines = ["# Available MCP Servers", ""]
    lines += [f"- **{name}**: {transport(server)}" for name, server in sorted(servers.items())]
    lines += ["", "---", f"**Total MCPs available**: {len(servers)}"]
    return "\n".join(lines) + "\n"


def merge(
    bundled: dict[str, Any], names: list[str], destination: Path, force: bool
) -> tuple[dict[str, Any], list[str]]:
    bundled = standalone_servers(bundled)
    unknown = sorted(set(names) - set(bundled))
    if unknown:
        raise ValueError(f"unknown MCP server(s): {', '.join(unknown)}")
    existing: dict[str, Any] = {}
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError(f"{destination}: expected a JSON object")
    servers = existing.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{destination}: mcpServers must be an object")
    conflicts = [name for name in names if name in servers and servers[name] != bundled[name] and not force]
    if conflicts:
        raise ValueError(f"existing server differs (use --force after review): {', '.join(sorted(conflicts))}")
    changed = [name for name in names if servers.get(name) != bundled[name]]
    merged = {**existing, "mcpServers": {**servers, **{name: bundled[name] for name in names}}}
    return merged, changed


def write_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mcp.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("servers", nargs="*", help="bundled server names to add")
    parser.add_argument("--catalog", action="store_true", help="print the bundled catalog and exit")
    parser.add_argument("--destination", default=".cursor/mcp.json", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        bundled = load_servers(BUNDLED)
        if args.catalog:
            sys.stdout.write(catalog(bundled))
            return 0
        if not args.servers:
            raise ValueError("select at least one bundled MCP server")
        merged, changed = merge(bundled, args.servers, args.destination, args.force)
        for name in changed:
            print(f"{'Would add' if args.dry_run else 'Added'} {name} -> {args.destination}")
        if not args.dry_run and changed:
            write_atomic(args.destination, merged)
        return 0
    except (OSError, ValueError) as exc:
        print(f"select-mcp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
