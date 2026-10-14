#!/usr/bin/env bash
# Ensure .opencode-plugin/commands matches generator output and has no
# Claude-only residue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMMANDS_DIR="${REPO_ROOT}/.opencode-plugin/commands"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_opencode_commands.py" --check

echo "== Frontmatter lint =="
python3 - <<'PY' "${COMMANDS_DIR}" "${REPO_ROOT}"
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(sys.argv[2]) / "scripts"))
from generate_opencode_commands import description_budget_errors

root = Path(sys.argv[1])
# opencode command frontmatter keys (per opencode.ai/docs/commands).
ALLOWED = {"description", "agent", "model", "subtask"}
errors = 0
# Always-loaded command listing shares the skill listing budget (YAN-1083 / YAN-1102).
for message in description_budget_errors(root):
    print(message, file=sys.stderr)
    errors += 1
for path in sorted(root.glob("*.md")):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        print(f"MISSING frontmatter: {path}", file=sys.stderr)
        errors += 1
        continue
    data = yaml.safe_load(match.group(1)) or {}
    unknown = set(data) - ALLOWED
    if unknown:
        print(f"UNEXPECTED frontmatter keys in {path}: {sorted(unknown)}", file=sys.stderr)
        errors += 1
    description = str(data.get("description") or "").strip()
    if not description:
        print(f"MISSING required 'description' in {path}", file=sys.stderr)
        errors += 1
    subtask = data.get("subtask")
    if subtask is not None and not isinstance(subtask, bool):
        print(f"SUBTASK must be boolean (got {type(subtask).__name__}) in {path}", file=sys.stderr)
        errors += 1
if errors:
    sys.exit(1)
PY

echo "== Content policy (generated commands) =="
BAD=0
while IFS= read -r -d '' f; do
  if grep -qE '/ycc:|\bycc:|CLAUDE_PLUGIN_ROOT|~/\.claude/|\.claude-plugin/|TeamCreate|TeamDelete|TaskCreate|TaskUpdate|TaskList|TaskGet|SendMessage|AskUserQuestion|TodoWrite|subagent_type:' "$f" 2>/dev/null; then
    echo "FORBIDDEN pattern in $f:" >&2
    grep -nE '/ycc:|\bycc:|CLAUDE_PLUGIN_ROOT|~/\.claude/|\.claude-plugin/|TeamCreate|TeamDelete|TaskCreate|TaskUpdate|TaskList|TaskGet|SendMessage|AskUserQuestion|TodoWrite|subagent_type:' "$f" >&2 || true
    BAD=1
  fi
done < <(find "$COMMANDS_DIR" -maxdepth 1 -name '*.md' -print0)

if [[ "$BAD" -ne 0 ]]; then
  echo "validate-opencode-commands.sh: content policy failed." >&2
  exit 1
fi

echo "== Native V2 dispatch content policy =="
python3 "${REPO_ROOT}/scripts/validate_opencode_dispatch.py" "${COMMANDS_DIR}"

echo "OK: .opencode-plugin/commands is in sync and passes opencode-native lint."
