#!/usr/bin/env bash
# Ensure plugins/ycc/skills matches generator output and strips Claude-only residue.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_DIR="${REPO_ROOT}/.codex-plugin/ycc/skills"
SHARED_DIR="${REPO_ROOT}/.codex-plugin/ycc/shared"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_codex_skills.py" --check

echo "== Skill invocation policy regressions =="
python3 "${REPO_ROOT}/scripts/test_skill_invocation_policy.py"

echo "== Frontmatter lint =="
python3 - <<'PY' "${SKILLS_DIR}" "${REPO_ROOT}"
import re
import sys
from pathlib import Path

import yaml

repo = Path(sys.argv[2])
sys.path.insert(0, str(repo / "scripts"))
from generate_codex_common import model_invocation_disabled, parse_frontmatter

root = Path(sys.argv[1])
errors = 0
for path in sorted(root.rglob("SKILL.md")):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        print(f"MISSING frontmatter: {path}", file=sys.stderr)
        errors += 1
        continue
    data = yaml.safe_load(match.group(1)) or {}
    source, _ = parse_frontmatter((repo / "ycc/skills" / path.parent.name / "SKILL.md").read_text(encoding="utf-8"))
    disabled = model_invocation_disabled(source, path.parent.name)
    sidecar = path.parent / "agents/openai.yaml"
    if sidecar.exists() != disabled:
        print(f"INVOCATION policy sidecar presence mismatch: {sidecar}", file=sys.stderr)
        errors += 1
    elif disabled:
        policy = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
        if not isinstance(policy, dict) or not isinstance(policy.get("policy"), dict) or policy["policy"].get("allow_implicit_invocation") is not False:
            print(f"INVALID invocation policy: {sidecar}", file=sys.stderr)
            errors += 1
    if set(data) - {"name", "description", "license", "allowed-tools", "metadata"}:
        print(f"UNEXPECTED frontmatter keys in {path}: {sorted(set(data) - {'name', 'description', 'license', 'allowed-tools', 'metadata'})}", file=sys.stderr)
        errors += 1
    if "name" not in data or "description" not in data:
        print(f"MISSING required skill keys in {path}", file=sys.stderr)
        errors += 1
    elif len(data["description"]) > 1024:
        print(f"DESCRIPTION too long in {path}: {len(data['description'])} chars", file=sys.stderr)
        errors += 1
if errors:
    sys.exit(1)
PY

echo "== Content policy (generated skills) =="
# Allow-list: these files are copied verbatim by the Codex generator because
# they describe all three deployment targets. The same Claude-specific
# references the content policy normally forbids are intentional here.
# Must mirror VERBATIM_SKILL_FILES in scripts/generate_codex_common.py.
VERBATIM=(
  "${SKILLS_DIR}/init/scripts/migrate-rules.sh"
  "${SKILLS_DIR}/init/scripts/migrate-rules.py"
  "${SKILLS_DIR}/init/scripts/rules_file_lib.py"
  "${SKILLS_DIR}/init/scripts/render-template.sh"
  "${SKILLS_DIR}/init/scripts/render-template.py"
  "${SKILLS_DIR}/init/scripts/profile-project.sh"
  "${SKILLS_DIR}/init/scripts/rules-report.sh"
  "${SHARED_DIR}/references/target-capability-matrix.md"
  "${SKILLS_DIR}/hooks-workflow/references/support-notes.md"
  "${SKILLS_DIR}/hooks-workflow/scripts/build-hook-config.sh"
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

is_bundle_release_file() {
  local rel="${1#"${SKILLS_DIR}/"}"
  [[ "$rel" == bundle-release/* ]]
}

# check_rewrite_regressions <file>... — one interpreter for every file; a
# python3 spawn per generated file dominated this script's runtime.
check_rewrite_regressions() {
  python3 - "$@" <<'PY'
import re
import sys
from pathlib import Path

name_token = r"(?<![A-Za-z0-9_])`?name=`?"
checks = (
    ("duplicated name= AND name=", re.compile(rf"{name_token}\s+AND\s+{name_token}", re.IGNORECASE)),
    ("duplicated name= + name=", re.compile(rf"{name_token}\s*\+\s*{name_token}")),
    ("duplicated both name= and name=", re.compile(rf"\bboth\s+{name_token}\s+and\s+{name_token}", re.IGNORECASE)),
    ("duplicated comma-separated name=, name=", re.compile(rf"{name_token}\s*,\s*{name_token}")),
    ("duplicated Codex runtime list", re.compile(r"Codex, Cursor, and Codex")),
    ("ambiguous Codex-only team-mode wording", re.compile(r"--team.*Codex[- ]only|Codex[- ]only.*--team")),
)

failed = False
for path in map(Path, sys.argv[1:]):
    compact = re.sub(r"\s+", " ", path.read_text(encoding="utf-8", errors="ignore"))
    for label, pattern in checks:
        if pattern.search(compact):
            print(f"BROKEN Codex rewrite in {path}: {label}", file=sys.stderr)
            failed = True
sys.exit(1 if failed else 0)
PY
}

strip_scaffold_paths() {
  sed -E 's#\$\{CLAUDE_PLUGIN_ROOT\}/skills/\{\{[A-Z_]+\}\}/##g' "$1" 2>/dev/null
}

BAD=0
POLICY_FILES=()
while IFS= read -r -d '' f; do
  if is_verbatim "$f"; then
    continue
  fi
  if is_bundle_release_file "$f"; then
    # bundle-release intentionally manages Claude plugin metadata as the
    # source-of-truth version surface, even from generated Codex skills.
    pattern='/ycc:|\bycc:|CLAUDE_PLUGIN_ROOT|~/.claude/|TeamCreate|TeamDelete|TaskCreate|TaskUpdate|TaskList|TaskGet|SendMessage|AskUserQuestion|TodoWrite|subagent_type:'
  else
    pattern='/ycc:|\bycc:|CLAUDE_PLUGIN_ROOT|~/.claude/|\.claude-plugin/|TeamCreate|TeamDelete|TaskCreate|TaskUpdate|TaskList|TaskGet|SendMessage|AskUserQuestion|TodoWrite|subagent_type:'
  fi
  # Scaffold placeholders (`${CLAUDE_PLUGIN_ROOT}/skills/{{NAME}}/`) describe the
  # Claude-source skill a template will create; the native generator keeps them.
  if strip_scaffold_paths "$f" | grep -qE "$pattern"; then
    echo "FORBIDDEN pattern in $f:" >&2
    strip_scaffold_paths "$f" | grep -nE "$pattern" >&2 || true
    BAD=1
  fi
  POLICY_FILES+=("$f")
done < <(find "$SKILLS_DIR" "$SHARED_DIR" -type f -print0)

if [[ ${#POLICY_FILES[@]} -gt 0 ]] && ! check_rewrite_regressions "${POLICY_FILES[@]}"; then
  BAD=1
fi

if [[ "$BAD" -ne 0 ]]; then
  echo "validate-codex-skills.sh: content policy failed." >&2
  exit 1
fi

echo "OK: .codex-plugin/ycc/skills is in sync and passes Codex-native lint."
