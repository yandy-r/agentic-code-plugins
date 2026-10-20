#!/usr/bin/env bash
# Ensure packages/omp/ycc/commands matches generator output, covers every public skill once,
# and carries no Claude-only residue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_omp_commands.py" --check

echo "== Content policy (generated commands) =="
# `--check` already proves every public skill has exactly one command and nothing else is
# generated. Beyond that: each command's `description` and `argument-hint` equal the
# generated OMP skill's, the body reads `skill://<name>` and passes `$ARGUMENTS`, and no
# file carries `CLAUDE_PLUGIN_ROOT`, `/ycc:` or bare `ycc:` references.
PYTHONPATH="${REPO_ROOT}/scripts" python3 - "${REPO_ROOT}" <<'PY'
import re
import sys
from pathlib import Path

from generate_codex_common import parse_frontmatter

repo = Path(sys.argv[1])
skills = repo / "packages/omp/ycc/skills"
dest = repo / "packages/omp/ycc/commands"
forbidden = re.compile(r"CLAUDE_PLUGIN_ROOT|/ycc:|\bycc:")
bad = False

def fail(message: str) -> None:
    global bad
    print(message, file=sys.stderr)
    bad = True

for path in sorted(dest.glob("*.md")):
    text = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    skill_file = skills / path.stem / "SKILL.md"
    skill, _ = parse_frontmatter(skill_file.read_text(encoding="utf-8")) if skill_file.is_file() else ({}, "")
    for key in ("description", "argument-hint"):
        if frontmatter.get(key) != skill.get(key):
            fail(f"{path}: {key} differs from {skill_file}")
    if f"skill://{path.stem}`" not in body or "$ARGUMENTS" not in body:
        fail(f"{path}: body must read skill://{path.stem} and pass $ARGUMENTS")
    for number, line in enumerate(text.splitlines(), 1):
        if forbidden.search(line):
            fail(f"FORBIDDEN pattern in {path}:{number}: {line.strip()}")
sys.exit(1 if bad else 0)
PY

echo "OK: packages/omp/ycc/commands is in sync and passes content policy."
