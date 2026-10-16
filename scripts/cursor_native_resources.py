"""Cursor native-only init resources.

The checked-in native package carries package-local init resources. The file-copy
installer keeps its original ``~/.cursor`` bytes by projecting these files back
from ``ycc/skills`` at install time, so no second checked-in tree exists.
"""

from __future__ import annotations

from pathlib import Path

INIT_FILES = (
    Path("init/SKILL.md"),
    Path("init/scripts/generate-agent-catalog.sh"),
    Path("init/scripts/generate-mcp-catalog.sh"),
)

MCP_HELPER = "${CURSOR_PLUGIN_ROOT}/resources/mcp/select-mcp.py"

SKILL_REPLACEMENTS = (
    ("${HOME}/.cursor/mcp-library/generate-mcp-config.sh", MCP_HELPER),
    (
        "- Show the planned `.mcp.json` content.",
        f"- Show the planned `.cursor/mcp.json` changes: `{MCP_HELPER} --dry-run <selected-mcps>` (writes nothing).",
    ),
    (
        "Create `.claude/agents/` if needed; copy selected agent files from `${HOME}/.cursor/agents/`.",
        "The helper merges only the selected definitions from the package's bundled MCP configuration into the\n"
        "project's `.cursor/mcp.json`, keeps unrelated servers and keys, rewrites plugin `${VAR}` placeholders to\n"
        "standalone `${env:VAR}` references without reading the environment, keeps existing `${env:VAR}` unchanged,\n"
        "and refuses to overwrite a differing server unless `--force` is given after the user confirms. It is the\n"
        "project-level fallback and does not require the optional `ycc-mcp` package; avoid enabling the same\n"
        "server in both places.\n\n"
        "Create `.cursor/agents/` if needed; copy selected agent files from `${CURSOR_PLUGIN_ROOT}/agents/`.",
    ),
)

AGENT_CATALOG_REPLACEMENTS = (
    ("# Scans ~/.cursor/agents/ (", "# Scans the package-local agents/ directory ("),
    (
        'AGENTS_DIR="${AGENTS_DIR:-${HOME}/.cursor/agents}"',
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'AGENTS_DIR="${AGENTS_DIR:-${SCRIPT_DIR}/../../../agents}"',
    ),
)

MCP_CATALOG = """#!/usr/bin/env bash
# generate-mcp-catalog.sh
# Lists the MCP servers bundled with this package (resources/mcp/mcp.json).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/../../../resources/mcp/select-mcp.py" --catalog
"""


def _replace_all(text: str, replacements: tuple[tuple[str, str], ...], rel: Path) -> str:
    for old, new in replacements:
        if old not in text:
            raise ValueError(f"native init projection drifted: {rel} no longer contains {old!r}")
        text = text.replace(old, new)
    return text


def native_text(text: str, rel: Path) -> str:
    """Return the package-local form of one installer-oriented init file."""
    if rel == INIT_FILES[0]:
        return _replace_all(text, SKILL_REPLACEMENTS, rel)
    if rel == INIT_FILES[1]:
        return _replace_all(text, AGENT_CATALOG_REPLACEMENTS, rel)
    if rel == INIT_FILES[2]:
        return MCP_CATALOG
    raise ValueError(f"not a native init resource: {rel}")


def restore_installer_init(skills_root: Path) -> None:
    """Rewrite packaged init files under ``skills_root`` with their file-copy bytes."""
    import generate_cursor_skills as skills

    for rel in INIT_FILES:
        target = skills_root / rel
        if not target.is_file():
            continue
        source = skills.SRC_DIR / rel
        target.write_text(skills.transform_text_content(source.read_text(encoding="utf-8"), rel), encoding="utf-8")
        target.chmod(source.stat().st_mode & 0o777)
