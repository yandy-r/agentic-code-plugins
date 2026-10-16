#!/usr/bin/env bash
# Ensure packages/cursor/ycc/agents matches generator output and has no banned Claude-only residue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENTS_DIR="${REPO_ROOT}/packages/cursor/ycc/agents"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_cursor_agents.py" --check

echo "== Content policy (generated agents) =="
# Fail if obvious Claude-plugin residue remains in Cursor output
BAD=0
while IFS= read -r -d '' f; do
  if grep -qE '/ycc:|~/.claude/|\bycc:' "$f" 2>/dev/null; then
    echo "FORBIDDEN pattern in $f:" >&2
    grep -nE '/ycc:|~/.claude/|\bycc:' "$f" >&2 || true
    BAD=1
  fi
  if grep -q 'mcp\*\*' "$f" 2>/dev/null; then
    echo "Malformed mcp** token in $f:" >&2
    grep -n 'mcp\*\*' "$f" >&2 || true
    BAD=1
  fi
done < <(find "$AGENTS_DIR" -maxdepth 1 -name '*.md' -print0)

if [[ "$BAD" -ne 0 ]]; then
  echo "validate-cursor-agents.sh: content policy failed." >&2
  exit 1
fi

echo "== Model policy (generated agents) =="
python3 - "$AGENTS_DIR" <<'PY'
import re
import sys
from pathlib import Path

agents_dir = Path(sys.argv[1])
legacy = {"opus", "sonnet", "haiku"}

def parse_model(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^\s*model\s*:\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip("'\"")
    return None

errors: list[str] = []
for path in sorted(agents_dir.glob("*.md")):
    model = parse_model(path)
    if model is None:
        errors.append(f"missing model frontmatter in {path.name}")
        continue
    if model in legacy:
        errors.append(f"legacy shorthand model in {path.name}: {model}")
        continue
    if model in {"inherit", "fast"}:
        continue
    # Cursor model IDs may carry bracketed parameters, e.g.
    # claude-opus-5[effort=high,context=1m] (see cursor.com/docs/subagents).
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*(?:\[[A-Za-z0-9=,._-]*\])?", model):
        continue
    errors.append(f"unsupported model token in {path.name}: {model}")

if errors:
    print("validate-cursor-agents.sh: model policy failed.", file=sys.stderr)
    for err in errors:
        print(f"  {err}", file=sys.stderr)
    raise SystemExit(1)
PY

echo "OK: packages/cursor/ycc/agents is in sync and passes content policy."
