#!/usr/bin/env bash
# Ensure packages/cursor/ycc/skills matches generator output and has no banned Claude-only residue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_DIR="${REPO_ROOT}/packages/cursor/ycc/skills"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_cursor_skills.py" --check

echo "== Content policy (generated skills) =="
# Allow-list: these files are copied verbatim by the Cursor generator because
# they describe all three deployment targets. The same Claude-specific
# references the content policy normally forbids are intentional here.
# Must mirror VERBATIM_SKILL_FILES in scripts/generate_cursor_skills.py.
VERBATIM=(
  "${SKILLS_DIR}/init/scripts/migrate-rules.sh"
  "${SKILLS_DIR}/init/scripts/migrate-rules.py"
  "${SKILLS_DIR}/init/scripts/profile-project.sh"
  "${SKILLS_DIR}/init/scripts/render-template.sh"
  "${SKILLS_DIR}/init/scripts/render-template.py"
  "${SKILLS_DIR}/init/scripts/rules-report.sh"
  "${SKILLS_DIR}/init/scripts/rules_file_lib.py"
  "${SKILLS_DIR}/_shared/references/target-capability-matrix.md"
  "${SKILLS_DIR}/hooks-workflow/references/support-notes.md"
  "${SKILLS_DIR}/compatibility-audit/scripts/audit-install-assumptions.sh"
  "${SKILLS_DIR}/compatibility-audit/scripts/audit-target-features.sh"
  "${SKILLS_DIR}/compatibility-audit/references/reading-the-report.md"
)
is_verbatim() {
  local f="$1" v
  for v in "${VERBATIM[@]}"; do
    [[ "$f" == "$v" ]] && return 0
  done
  return 1
}

BAD=0
while IFS= read -r -d '' f; do
  if is_verbatim "$f"; then
    continue
  fi
  if grep -qE '/ycc:|~/.claude/|\bycc:|CLAUDE_PLUGIN_ROOT|\$\{HOME\}/\.claude/|\$HOME/\.claude/' "$f" 2>/dev/null; then
    echo "FORBIDDEN pattern in $f:" >&2
    grep -nE '/ycc:|~/.claude/|\bycc:|CLAUDE_PLUGIN_ROOT|\$\{HOME\}/\.claude/|\$HOME/\.claude/' "$f" >&2 || true
    BAD=1
  fi
  if grep -q 'mcp\*\*' "$f" 2>/dev/null; then
    echo "Malformed mcp** token in $f:" >&2
    grep -n 'mcp\*\*' "$f" >&2 || true
    BAD=1
  fi
done < <(find "$SKILLS_DIR" -type f -print0)

if [[ "$BAD" -ne 0 ]]; then
  echo "validate-cursor-skills.sh: content policy failed." >&2
  exit 1
fi

echo "OK: packages/cursor/ycc/skills is in sync and passes content policy."
