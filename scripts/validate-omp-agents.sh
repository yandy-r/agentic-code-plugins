#!/usr/bin/env bash
# Ensure packages/omp/ycc/agents matches generator output and has no Claude-only residue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_omp_agents.py" --check

echo "== Content policy (generated agents) =="
# Each source agent appears exactly once; frontmatter holds only OMP keys, OMP tool
# IDs and role aliases (OUTPUT_FRONTMATTER_KEYS / TOOL_MAP / MODEL_MAP in
# scripts/generate_omp_agents.py are imported, never copied); bodies carry no Claude
# plugin paths, ycc: references, `Bash(<cmd>:*)` scopes or backticked Claude tool names.
PYTHONPATH="${REPO_ROOT}/scripts" python3 - "${REPO_ROOT}" <<'PY'
import re
import sys
from pathlib import Path

from generate_codex_common import parse_frontmatter
from generate_omp_agents import MODEL_MAP, OMP_TOOL_IDS, OUTPUT_FRONTMATTER_KEYS, TOOL_MAP

repo = Path(sys.argv[1])
src = repo / "ycc/agents"
dest = repo / "packages/omp/ycc/agents"
claude_tools = "|".join(sorted(map(re.escape, TOOL_MAP), key=len, reverse=True))
forbidden = re.compile(r"CLAUDE_PLUGIN_ROOT|/ycc:|\bycc:|\bBash\(|`(?:" + claude_tools + r")`")
models = {alias for alias in MODEL_MAP.values() if alias is not None}
bad = False


def fail(message: str) -> None:
    global bad
    print(message, file=sys.stderr)
    bad = True


source_stems = {p.stem for p in src.glob("*.md")}
generated = sorted(p for p in dest.rglob("*") if p.is_file())
generated_stems = {p.stem for p in generated if p.parent == dest and p.suffix == ".md"}
for stem in sorted(source_stems - generated_stems):
    fail(f"missing generated agent {dest / stem}.md")
for path in generated:
    if path.parent != dest or path.stem not in source_stems:
        fail(f"generated file has no source agent: {path}")

names: dict[str, Path] = {}
for path in generated:
    text = path.read_text(encoding="utf-8")
    frontmatter, _ = parse_frontmatter(text)
    extra = sorted(set(frontmatter) - set(OUTPUT_FRONTMATTER_KEYS))
    if extra:
        fail(f"{path}: non-OMP frontmatter key(s): {', '.join(extra)}")
    name = frontmatter.get("name")
    if not isinstance(name, str) or not isinstance(frontmatter.get("description"), str):
        fail(f"{path}: name and description must be strings")
    elif name in names:
        fail(f"{path}: duplicate agent name '{name}' (also {names[name]})")
    else:
        names[name] = path
    tools = frontmatter.get("tools", [])
    if not isinstance(tools, list) or any(tool not in OMP_TOOL_IDS for tool in tools):
        fail(f"{path}: tools must list OMP tool IDs only, got {tools!r}")
    elif len(tools) != len(set(tools)):
        fail(f"{path}: duplicate tool IDs in {tools!r}")
    if "model" in frontmatter and frontmatter["model"] not in models:
        fail(f"{path}: model must be one of {sorted(models)}, got {frontmatter['model']!r}")
    for number, line in enumerate(text.splitlines(), 1):
        if forbidden.search(line) or "mcp**" in line:
            fail(f"FORBIDDEN pattern in {path}:{number}: {line.strip()}")
sys.exit(1 if bad else 0)
PY

echo "OK: packages/omp/ycc/agents is in sync and passes content policy."
