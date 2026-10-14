#!/usr/bin/env bash
# Literal ${CLAUDE_PLUGIN_ROOT} paths in single-quoted strings are intentional.
# shellcheck disable=SC2016
#
# Behavioral tests for the release-model hygiene changes:
#   ycc/skills/init/scripts/profile-project.sh      (has_releasing_md)
#   ycc/skills/formatters/scripts/apply-ci.sh       (lint.yml push branches)
#   ycc/skills/init/templates/{CLAUDE.md,github/labels.md}.tmpl  (IF_RELEASE_MODEL)
#   git-cleanup skill, agent and rules               (release-model wiring)
#
# Every test runs in throwaway git repos under a temp dir with an isolated git
# config, so the caller's repositories and global git settings are never used.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE="${REPO_ROOT}/ycc/skills/init/scripts/profile-project.sh"
APPLY_CI="${REPO_ROOT}/ycc/skills/formatters/scripts/apply-ci.sh"
INIT_TEMPLATES="${REPO_ROOT}/ycc/skills/init/templates"
GIT_CLEANUP_SKILL="${REPO_ROOT}/ycc/skills/git-cleanup/SKILL.md"
GIT_CLEANUP_RULES="${REPO_ROOT}/ycc/skills/git-cleanup/references/active-code-rules.md"
GIT_CLEANUP_AGENT="${REPO_ROOT}/ycc/agents/git-cleanup.md"
POINTER_TARGETS="${REPO_ROOT}/ycc/skills/release-model/scripts/pointer-targets.sh"
PASS=0
FAIL=0

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

# Git hooks (pre-push runs validate.sh) export GIT_DIR, GIT_WORK_TREE,
# GIT_INDEX_FILE and friends. Left set, they would point every sandbox git
# call at the caller's repository, so clear all repo-local git variables.
while IFS= read -r git_var; do
  unset "$git_var"
done < <(git rev-parse --local-env-vars)
unset git_var

SANDBOX_ROOT="$(mktemp -d)"
trap 'rm -rf "${SANDBOX_ROOT}"' EXIT

# Isolated git identity/config for every git call in this script.
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="${SANDBOX_ROOT}/gitconfig"
cat >"${GIT_CONFIG_GLOBAL}" <<'EOF'
[user]
	name = ycc test
	email = ycc-test@example.invalid
[init]
	defaultBranch = main
[commit]
	gpgsign = false
[tag]
	gpgsign = false
EOF

ok() {
  PASS=$((PASS + 1))
  printf '%s[pass]%s %s\n' "${GREEN}" "${NC}" "$1"
}

ko() {
  FAIL=$((FAIL + 1))
  printf '%s[FAIL]%s %s\n' "${RED}" "${NC}" "$1"
  [[ -n "${2:-}" ]] && printf '       %s\n' "$2"
}

assert_eq() {
  local actual="$1" expected="$2" name="$3"
  if [[ "$actual" == "$expected" ]]; then
    ok "$name"
  else
    ko "$name" "expected: $(printf '%q' "$expected") got: $(printf '%q' "$actual")"
  fi
}

assert_contains() {
  local haystack="$1" needle="$2" name="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    ok "$name"
  else
    ko "$name" "missing: $needle"
  fi
}

assert_exit() {
  local actual="$1" expected="$2" name="$3"
  assert_eq "$actual" "$expected" "$name (exit $expected)"
}

# mkrepo — create a repo with one commit on main and a bare origin; echo path.
mkrepo() {
  local dir origin
  dir="$(mktemp -d "${SANDBOX_ROOT}/repo.XXXXXX")"
  origin="${dir}.origin.git"
  git init -q --bare "$origin"
  git -C "$dir" init -q
  # Refuse to continue if git resolved anything but the sandbox repo.
  if [[ "$(cd "$dir" && git rev-parse --absolute-git-dir)" != "${dir}/.git" ]]; then
    echo "test-release-hygiene: git did not resolve the sandbox repo; aborting" >&2
    exit 1
  fi
  echo "seed" >"${dir}/README.md"
  git -C "$dir" add README.md
  git -C "$dir" commit -q -m "chore: seed"
  git -C "$dir" remote add origin "$origin"
  git -C "$dir" push -q origin main 2>/dev/null
  git -C "$dir" remote set-head origin main >/dev/null 2>&1
  echo "$dir"
}

# get_key <output> <key> — value of key=value in output.
get_key() {
  printf '%s\n' "$1" | sed -n "s/^$2=//p"
}

# ---------------------------------------------------------------------------
# release-model — pointer-targets.sh (canonical @AGENTS.md vs legacy layout)
# ---------------------------------------------------------------------------

test_pointer_targets() {
  local target
  for target in .codex-plugin/ycc/skills .opencode-plugin/skills .agents-plugin/skills .cursor-plugin/skills; do
    if cmp -s "$POINTER_TARGETS" "$REPO_ROOT/$target/release-model/scripts/pointer-targets.sh"; then
      ok "pointer-targets: $target preserves cross-runtime filenames verbatim"
    else
      ko "pointer-targets: $target preserves cross-runtime filenames verbatim"
    fi
  done
  local dir out
  dir="$(mktemp -d "${SANDBOX_ROOT}/ptr.XXXXXX")"
  mkdir -p "${dir}/.github"

  # Legacy layout: standalone CLAUDE.md and AGENTS.md both get pointers.
  printf '# Legacy\n' >"${dir}/CLAUDE.md"
  printf '# Legacy agents\n' >"${dir}/AGENTS.md"
  printf '# Copilot\n' >"${dir}/.github/copilot-instructions.md"
  assert_eq "$(bash "$POINTER_TARGETS" --repo "$dir" | tr '\n' ' ')" \
    "CLAUDE.md AGENTS.md .github/copilot-instructions.md " \
    "pointer-targets: legacy layout lists all three files"

  # Canonical layout: CLAUDE.md imports AGENTS.md, so only AGENTS.md is listed.
  printf '@AGENTS.md\n\n# Claude notes\n' >"${dir}/CLAUDE.md"
  assert_eq "$(bash "$POINTER_TARGETS" --repo "$dir" | tr '\n' ' ')" \
    "AGENTS.md .github/copilot-instructions.md " \
    "pointer-targets: @AGENTS.md import drops CLAUDE.md"

  # The import must be live: comments, inline code, and fences do not count.
  printf '# Legacy\n<!-- @AGENTS.md -->\n`@AGENTS.md`\n\n```\n@AGENTS.md\n```\n' >"${dir}/CLAUDE.md"
  assert_eq "$(bash "$POINTER_TARGETS" --repo "$dir" | tr '\n' ' ')" \
    "CLAUDE.md AGENTS.md .github/copilot-instructions.md " \
    "pointer-targets: commented/inline/fenced @AGENTS.md is not an import"

  # Prose that merely mentions the token is not an import directive.
  printf '# Notes\nAdd @AGENTS.md later.\nSee `@AGENTS.md` and @AGENTS.md, too.\n' >"${dir}/CLAUDE.md"
  assert_eq "$(bash "$POINTER_TARGETS" --repo "$dir" | tr '\n' ' ')" \
    "CLAUDE.md AGENTS.md .github/copilot-instructions.md " \
    "pointer-targets: prose mention of @AGENTS.md is not an import"

  # Generated runtime bundles keep CLAUDE.md as the importer (target-repo file name).
  local bundle
  for bundle in .codex-plugin/ycc/skills .opencode-plugin/skills .agents-plugin/skills; do
    assert_contains "$(cat "$REPO_ROOT/$bundle/release-model/references/pointer-and-labels.md")" \
      "When \`CLAUDE.md\` imports \`AGENTS.md\`" \
      "pointer-targets: $bundle keeps CLAUDE.md as importer"
  done

  # A dangling import must fail loudly instead of silently skipping CLAUDE.md.
  printf '@AGENTS.md\n' >"${dir}/CLAUDE.md"
  rm "${dir}/AGENTS.md"
  if out="$(bash "$POINTER_TARGETS" --repo "$dir" 2>&1)"; then
    ko "pointer-targets: dangling import exits 1" "exit 0, output: ${out}"
  else
    ok "pointer-targets: dangling import exits 1"
  fi
}

# ---------------------------------------------------------------------------
# profile-project.sh — has_releasing_md
# ---------------------------------------------------------------------------

test_profile_releasing_md() {
  local repo out rc
  repo="$(mkrepo)"
  out="$(bash "$PROFILE" "$repo")"
  rc=$?
  assert_exit "$rc" 0 "profile: runs in a repo without RELEASING.md"
  assert_eq "$(get_key "$out" has_releasing_md)" "false" "profile: has_releasing_md=false without RELEASING.md"

  echo "# Releasing" >"${repo}/RELEASING.md"
  out="$(bash "$PROFILE" "$repo")"
  assert_eq "$(get_key "$out" has_releasing_md)" "true" "profile: has_releasing_md=true with a root RELEASING.md"

  rm "${repo}/RELEASING.md"
  mkdir -p "${repo}/docs"
  echo "# Releasing" >"${repo}/docs/RELEASING.md"
  out="$(bash "$PROFILE" "$repo")"
  assert_eq "$(get_key "$out" has_releasing_md)" "false" "profile: a nested RELEASING.md does not count"

  assert_eq "$(printf '%s\n' "$out" | grep -c '^has_releasing_md=')" "1" "profile: has_releasing_md is emitted once"
}

# ---------------------------------------------------------------------------
# apply-ci.sh — lint.yml push branches
# ---------------------------------------------------------------------------

# write_style_profile <path> — minimal formatters profile for apply-ci.sh.
write_style_profile() {
  printf '%s\n' "detect_shell=true" "detect_docs=false" >"$1"
}

# push_branches <lint.yml> — the on.push.branches value line.
push_branches() {
  sed -n '/^  push:/,/^[^ ]/s/^    branches: //p' "$1"
}

# yaml_push_branches <lint.yml> — on.push.branches parsed as YAML, comma-joined.
# Prints "skip" when PyYAML is unavailable.
yaml_push_branches() {
  python3 - "$1" <<'PYEOF'
import sys
try:
    import yaml
except ImportError:
    print("skip")
    sys.exit(0)
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
on = data.get("on", data.get(True))
print(",".join(on["push"]["branches"]))
PYEOF
}

test_apply_ci_default_branch() {
  local repo prof out rc lint parsed
  repo="$(mkrepo)"
  prof="${SANDBOX_ROOT}/style-profile.env"
  write_style_profile "$prof"
  out="$(bash "$APPLY_CI" --target "$repo" --profile-file "$prof" 2>&1)"
  rc=$?
  assert_exit "$rc" 0 "apply-ci: renders into a repo with origin/HEAD=main"
  lint="${repo}/.github/workflows/lint.yml"
  assert_eq "$(push_branches "$lint")" "[main, 'release/**']" "apply-ci: lint.yml pushes on main and release/**"
  if grep -qE '\{\{[#/]?[A-Z_]+\}\}' "$lint"; then
    ko "apply-ci: lint.yml has no unrendered template markers" "$(grep -nE '\{\{[#/]?[A-Z_]+\}\}' "$lint")"
  else
    ok "apply-ci: lint.yml has no unrendered template markers"
  fi
  assert_contains "$(cat "$lint")" "lint-shell:" "apply-ci: lint.yml keeps the enabled stack job"
  parsed="$(yaml_push_branches "$lint")"
  if [[ "$parsed" == "skip" ]]; then
    ok "apply-ci: lint.yml YAML parse skipped (no PyYAML)"
  else
    assert_eq "$parsed" "main,release/**" "apply-ci: lint.yml parses as YAML with the expected push branches"
  fi
  assert_contains "$(cat "${repo}/.github/workflows/lint-autofix.yml")" "branches: [main]" \
    "apply-ci: lint-autofix.yml still targets only the default branch"
}

test_apply_ci_custom_default_branch() {
  local repo prof rc
  repo="$(mkrepo)"
  git -C "$repo" switch -q -c develop
  git -C "$repo" push -q origin develop 2>/dev/null
  git -C "$repo" remote set-head origin develop >/dev/null 2>&1
  prof="${SANDBOX_ROOT}/style-profile.env"
  write_style_profile "$prof"
  bash "$APPLY_CI" --target "$repo" --profile-file "$prof" >/dev/null 2>&1
  rc=$?
  assert_exit "$rc" 0 "apply-ci: renders into a repo with origin/HEAD=develop"
  assert_eq "$(push_branches "${repo}/.github/workflows/lint.yml")" "[develop, 'release/**']" \
    "apply-ci: lint.yml follows origin/HEAD"
}

test_apply_ci_no_git() {
  local dir prof rc
  dir="$(mktemp -d "${SANDBOX_ROOT}/plain.XXXXXX")"
  prof="${SANDBOX_ROOT}/style-profile.env"
  write_style_profile "$prof"
  bash "$APPLY_CI" --target "$dir" --profile-file "$prof" --no-autofix >/dev/null 2>&1
  rc=$?
  assert_exit "$rc" 0 "apply-ci: renders into a directory that is not a git repo"
  assert_eq "$(push_branches "${dir}/.github/workflows/lint.yml")" "[main, 'release/**']" \
    "apply-ci: lint.yml falls back to main without origin/HEAD"
}

# ---------------------------------------------------------------------------
# init templates — IF_RELEASE_MODEL blocks
# ---------------------------------------------------------------------------

# block_body <file> <name> — text between {{#name}} and {{/name}} (exclusive).
block_body() {
  sed -n "/{{#$2}}/,/{{\/$2}}/p" "$1" | sed '1d;$d'
}

test_init_templates() {
  local tmpl opens closes
  for tmpl in "${INIT_TEMPLATES}/CLAUDE.md.tmpl" "${INIT_TEMPLATES}/github/labels.md.tmpl"; do
    opens="$(grep -c '{{#IF_RELEASE_MODEL}}' "$tmpl")"
    closes="$(grep -c '{{/IF_RELEASE_MODEL}}' "$tmpl")"
    if [[ "$opens" -ge 1 && "$opens" == "$closes" ]]; then
      ok "templates: $(basename "$tmpl") has balanced IF_RELEASE_MODEL blocks"
    else
      ko "templates: $(basename "$tmpl") has balanced IF_RELEASE_MODEL blocks" "opens=$opens closes=$closes"
    fi
  done
  assert_contains "$(block_body "${INIT_TEMPLATES}/CLAUDE.md.tmpl" IF_RELEASE_MODEL)" "## Branching & releases" \
    "templates: CLAUDE.md Branching & releases section is conditional"
  assert_contains "$(block_body "${INIT_TEMPLATES}/CLAUDE.md.tmpl" IF_RELEASE_MODEL)" "RELEASING.md" \
    "templates: CLAUDE.md section points at RELEASING.md"
  assert_contains "$(block_body "${INIT_TEMPLATES}/github/labels.md.tmpl" IF_RELEASE_MODEL)" 'gh label create "backport:' \
    "templates: labels.md backport family has a gh label create example"
}

# ---------------------------------------------------------------------------
# git-cleanup — release-model wiring stays consistent across skill/agent/rules
# ---------------------------------------------------------------------------

test_git_cleanup_wiring() {
  local file
  for file in "$GIT_CLEANUP_SKILL" "$GIT_CLEANUP_RULES"; do
    assert_contains "$(cat "$file")" '${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/release-state.sh' \
      "git-cleanup: $(basename "$file") reads release-state.sh by full path"
  done
  # Codex agents reject CLAUDE_PLUGIN_ROOT, so the skill passes the state in.
  assert_contains "$(cat "$GIT_CLEANUP_SKILL")" "release-state.sh get\` output with the other" \
    "git-cleanup: skill passes the release state to the agent"
  assert_contains "$(cat "$GIT_CLEANUP_AGENT")" "passes its" \
    "git-cleanup: agent consumes the caller's release state"
  for file in "$GIT_CLEANUP_SKILL" "$GIT_CLEANUP_AGENT" "$GIT_CLEANUP_RULES"; do
    assert_contains "$(cat "$file")" "frozen by RELEASING.md" \
      "git-cleanup: $(basename "$file") flags frozen branches"
    assert_contains "$(cat "$file")" "release-model --audit" \
      "git-cleanup: $(basename "$file") stops on a malformed state"
  done
  assert_contains "$(cat "$GIT_CLEANUP_SKILL")" "'Bash(\${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/release-state.sh:*)'" \
    "git-cleanup: skill allows running release-state.sh"
}

# The sync-merge pattern documented in the rules must match real git merge
# subjects on a topic branch and ignore ordinary commits.
test_git_cleanup_sync_merge_pattern() {
  local repo pattern out
  repo="$(mkrepo)"
  pattern="$(grep -o -- '--grep="[^"]*"' "$GIT_CLEANUP_RULES" | head -1)"
  pattern="${pattern#--grep=\"}"
  pattern="${pattern%\"}"
  pattern="${pattern//<trunk>/main}"
  if [[ -z "$pattern" ]]; then
    ko "git-cleanup: rules document a --grep sync-merge pattern"
    return
  fi
  ok "git-cleanup: rules document a --grep sync-merge pattern"
  git -C "$repo" switch -q -c feat/x
  git -C "$repo" commit -q --allow-empty -m "feat: one"
  git -C "$repo" switch -q main
  git -C "$repo" commit -q --allow-empty -m "fix: on main"
  git -C "$repo" push -q origin main 2>/dev/null
  git -C "$repo" switch -q feat/x
  git -C "$repo" merge -q --no-edit main
  git -C "$repo" switch -q main
  git -C "$repo" commit -q --allow-empty -m "fix: again"
  git -C "$repo" push -q origin main 2>/dev/null
  git -C "$repo" switch -q feat/x
  git -C "$repo" fetch -q origin
  git -C "$repo" merge -q --no-edit origin/main
  out="$(git -C "$repo" log --merges --since="90 days ago" --format='%s' -E --grep="$pattern" origin/main..feat/x)"
  assert_contains "$out" "Merge branch 'main' into feat/x" "git-cleanup: pattern matches a local trunk sync merge"
  assert_contains "$out" "Merge remote-tracking branch 'origin/main' into feat/x" \
    "git-cleanup: pattern matches a remote-tracking trunk sync merge"
  assert_eq "$(printf '%s\n' "$out" | grep -c .)" "2" "git-cleanup: pattern ignores ordinary commits"
}

test_profile_releasing_md
test_apply_ci_default_branch
test_apply_ci_custom_default_branch
test_apply_ci_no_git
test_init_templates
test_pointer_targets
test_git_cleanup_wiring
test_git_cleanup_sync_merge_pattern

echo
echo "release-hygiene tests: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
