#!/usr/bin/env python3
"""
Generate Codex-native custom agents under .codex/agents from ycc/agents.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from generate_codex_common import (
    PLUGIN_AGENTS_DIR,
    SRC_AGENTS_DIR,
    apply_codex_text_transforms,
    load_agent_aliases,
    parse_frontmatter,
)
from practices_parse import parse_tools

WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit", "Bash"})


def is_read_only(tools: object) -> bool:
    """True when an explicit tools list has no write-capable tool.

    Scoped ``Bash(...)`` counts as its Bash head, and any ``mcp__*`` entry
    counts as write-capable (fail-safe: an MCP server may expose mutating
    tools). No ycc read-only agent ships MCP tools today; if a read-only
    docs-lookup server is ever needed, allowlist its prefix here.
    """
    entries = parse_tools(tools)
    return bool(entries) and not any(
        entry.split("(", 1)[0].startswith("mcp__") or entry.split("(", 1)[0] in WRITE_TOOLS for entry in entries
    )


def encode_toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_agent_toml(name: str, description: str, developer_instructions: str, *, read_only: bool = False) -> str:
    lines = [
        f"name = {encode_toml_string(name)}",
        f"description = {encode_toml_string(description)}",
        *(['sandbox_mode = "read-only"'] if read_only else []),
        f"developer_instructions = {encode_toml_string(developer_instructions.strip())}",
        "",
    ]
    return "\n".join(lines)


def write_all(dest: Path, dry_run: bool) -> set[Path]:
    aliases = load_agent_aliases()
    written: set[Path] = set()

    for src in sorted(SRC_AGENTS_DIR.glob("*.md")):
        frontmatter, body = parse_frontmatter(src.read_text(encoding="utf-8"))
        name = str(frontmatter.get("name") or src.stem)
        description = apply_codex_text_transforms(
            str(frontmatter.get("description") or "").strip(),
            aliases,
        ).strip()
        instructions = apply_codex_text_transforms(body, aliases).strip()

        target = dest / f"{name}.toml"
        written.add(target.relative_to(dest))
        if dry_run:
            print(f"Would write {target.relative_to(dest)}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        read_only = is_read_only(frontmatter.get("tools"))
        target.write_text(
            build_agent_toml(name, description, instructions, read_only=read_only),
            encoding="utf-8",
        )

    if not dry_run:
        existing = sorted(path for path in dest.glob("*.toml"))
        for path in existing:
            if path.relative_to(dest) not in written:
                path.unlink()
    return written


def compare_trees(generated: Path, repo_dest: Path) -> list[str]:
    generated_files = {path.relative_to(generated) for path in generated.glob("*.toml")}
    repo_files = {path.relative_to(repo_dest) for path in repo_dest.glob("*.toml")} if repo_dest.is_dir() else set()

    diffs: list[str] = []
    for rel in sorted(generated_files | repo_files):
        left = generated / rel
        right = repo_dest / rel
        if rel not in repo_files:
            diffs.append(f"missing in repo: {rel}")
            continue
        if rel not in generated_files:
            diffs.append(f"extra in repo: {rel}")
            continue
        if left.read_bytes() != right.read_bytes():
            diffs.append(f"drift: {rel}")
    return diffs


def run_check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        write_all(temp_root, dry_run=False)
        diffs = compare_trees(temp_root, PLUGIN_AGENTS_DIR)
        if diffs:
            print(
                "Codex custom agents are out of date. Run: ./scripts/generate-codex-agents.sh",
                file=sys.stderr,
            )
            for diff in diffs:
                print(f"  {diff}", file=sys.stderr)
            return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if generated output drifts")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written")
    args = parser.parse_args()

    if args.check:
        if not PLUGIN_AGENTS_DIR.is_dir():
            print(
                f"Missing {PLUGIN_AGENTS_DIR}; run generator without --check first.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(run_check())

    if args.dry_run:
        write_all(PLUGIN_AGENTS_DIR, dry_run=True)
        return

    PLUGIN_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    write_all(PLUGIN_AGENTS_DIR, dry_run=False)
    count = sum(1 for _ in PLUGIN_AGENTS_DIR.glob("*.toml"))
    print(f"Wrote {count} files under {PLUGIN_AGENTS_DIR}")


if __name__ == "__main__":
    main()
