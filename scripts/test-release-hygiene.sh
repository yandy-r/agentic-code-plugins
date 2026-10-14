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
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE="${REPO_ROOT}/ycc/skills/init/scripts/profile-project.sh"
APPLY_CI="${REPO_ROOT}/ycc/skills/formatters/scripts/apply-ci.sh"
INIT_TEMPLATES="${REPO_ROOT}/ycc/skills/init/templates"
INIT_SCRIPTS="${REPO_ROOT}/ycc/skills/init/scripts"
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

assert_le() {
  local actual="$1" limit="$2" name="$3"
  if [[ "$actual" -le "$limit" ]]; then
    ok "$name"
  else
    ko "$name" "expected <= ${limit}, got ${actual}"
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
  for tmpl in "${INIT_TEMPLATES}/AGENTS.md.tmpl" "${INIT_TEMPLATES}/github/labels.md.tmpl"; do
    opens="$(grep -c '{{#IF_RELEASE_MODEL}}' "$tmpl")"
    closes="$(grep -c '{{/IF_RELEASE_MODEL}}' "$tmpl")"
    if [[ "$opens" -ge 1 && "$opens" == "$closes" ]]; then
      ok "templates: $(basename "$tmpl") has balanced IF_RELEASE_MODEL blocks"
    else
      ko "templates: $(basename "$tmpl") has balanced IF_RELEASE_MODEL blocks" "opens=$opens closes=$closes"
    fi
  done
  assert_contains "$(block_body "${INIT_TEMPLATES}/AGENTS.md.tmpl" IF_RELEASE_MODEL)" "## Branching & releases" \
    "templates: AGENTS.md Branching & releases section is conditional"
  assert_contains "$(block_body "${INIT_TEMPLATES}/AGENTS.md.tmpl" IF_RELEASE_MODEL)" "RELEASING.md" \
    "templates: AGENTS.md section points at RELEASING.md"
  assert_contains "$(block_body "${INIT_TEMPLATES}/github/labels.md.tmpl" IF_RELEASE_MODEL)" 'gh label create "backport:' \
    "templates: labels.md backport family has a gh label create example"
}

# ---------------------------------------------------------------------------
# init — canonical AGENTS.md rules files (Node / Python / Go scratch repos)
# ---------------------------------------------------------------------------

# scratch_stack <node|python|go> — scratch git repo with that stack's manifest; echo path.
scratch_stack() {
  local dir
  dir="$(mktemp -d "${SANDBOX_ROOT}/stack.XXXXXX")"
  git -C "$dir" init -q
  case "$1" in
    node)
      echo '{"name":"demo","scripts":{"test":"vitest run","lint":"eslint .","build":"tsc"}}' >"${dir}/package.json"
      echo '{}' >"${dir}/tsconfig.json"
      ;;
    python) printf '[project]\nname = "demo"\n\n[tool.pytest.ini_options]\n\n[tool.ruff]\n' >"${dir}/pyproject.toml" ;;
    go) printf 'module example.com/demo\n' >"${dir}/go.mod" ;;
  esac
  echo "$dir"
}

# render <repo> <template> [render-template args...] — profile the repo, render to stdout.
render() {
  local repo="$1" tmpl="$2"
  shift 2
  bash "$PROFILE" "$repo" | bash "${INIT_SCRIPTS}/render-template.sh" --template "${INIT_TEMPLATES}/${tmpl}" "$@"
}

test_init_rules_shape() {
  local stack repo agents claude lines expect_test
  for stack in node python go; do
    repo="$(scratch_stack "$stack")"
    agents="$(render "$repo" AGENTS.md.tmpl --set "PROJECT_PURPOSE=Demo project.")"
    lines="$(printf '%s\n' "$agents" | wc -l | tr -d ' ')"
    if [[ "$lines" -le 100 ]]; then
      ok "init[$stack]: AGENTS.md is ${lines} lines (<=100)"
    else
      ko "init[$stack]: AGENTS.md is ${lines} lines (<=100)"
    fi
    case "$stack" in
      node) expect_test="npm test" ;;
      python) expect_test="pytest" ;;
      go) expect_test="go test ./..." ;;
    esac
    assert_contains "$agents" "$expect_test" "init[$stack]: AGENTS.md has the detected test command"
    assert_contains "$agents" "Conventional Commits 1.0.0" "init[$stack]: AGENTS.md carries the commits rule"
    if grep -q '^| `feat`' <<<"$agents" || grep -q 'Stack Overview' <<<"$agents" || grep -q '^## SHOULD' <<<"$agents"; then
      ko "init[$stack]: AGENTS.md has no types table, stack table or generic SHOULDs"
    else
      ok "init[$stack]: AGENTS.md has no types table, stack table or generic SHOULDs"
    fi
    if grep -q 'Branching & releases' <<<"$agents"; then
      ko "init[$stack]: Branching & releases is dropped without RELEASING.md"
    else
      ok "init[$stack]: Branching & releases is dropped without RELEASING.md"
    fi
    claude="$(render "$repo" CLAUDE.md.tmpl)"
    assert_eq "$claude" "@AGENTS.md" "init[$stack]: CLAUDE.md without Claude-only content is just @AGENTS.md"
  done

  # A Node repo without scripts, and a bare Python manifest, must not get guessed commands.
  repo="$(mktemp -d "${SANDBOX_ROOT}/bare.XXXXXX")"
  git -C "$repo" init -q
  echo '{"name":"bare","scripts":{"start":"node x"}}' >"${repo}/package.json"
  agents="$(render "$repo" AGENTS.md.tmpl --set "PROJECT_PURPOSE=Demo.")"
  if grep -q 'npm' <<<"$agents"; then ko "init[node-bare]: no npm commands without package scripts"; else ok "init[node-bare]: no npm commands without package scripts"; fi
  repo="$(mktemp -d "${SANDBOX_ROOT}/pybare.XXXXXX")"
  git -C "$repo" init -q
  printf '[project]\nname = "bare"\n' >"${repo}/pyproject.toml"
  agents="$(render "$repo" AGENTS.md.tmpl --set "PROJECT_PURPOSE=Demo.")"
  if grep -q 'pytest\|ruff' <<<"$agents"; then ko "init[python-bare]: no pytest/ruff without config signals"; else ok "init[python-bare]: no pytest/ruff without config signals"; fi

  # Unknown stacks never get an invented command.
  repo="$(mktemp -d "${SANDBOX_ROOT}/empty.XXXXXX")"
  git -C "$repo" init -q
  agents="$(render "$repo" AGENTS.md.tmpl --set "PROJECT_PURPOSE=Demo.")"
  assert_contains "$agents" "# not detected" "init[unknown]: undetected commands render as '# not detected'"

  # Claude-only content: short section after the import.
  claude="$(render "$repo" CLAUDE.md.tmpl --keep IF_CLAUDE_ONLY --set "CLAUDE_ONLY_NOTES=- Use /ycc: skills.")"
  assert_eq "$(printf '%s\n' "$claude" | head -n 1)" "@AGENTS.md" "init: CLAUDE.md starts with @AGENTS.md"
  lines="$(printf '%s\n' "$claude" | wc -l | tr -d ' ')"
  if [[ "$lines" -le 15 ]]; then ok "init: CLAUDE.md with notes is ${lines} lines (<=15)"; else ko "init: CLAUDE.md with notes is ${lines} lines (<=15)"; fi

  # Template line budget and the optional Cursor/Copilot/vendor files.
  lines="$(wc -l <"${INIT_TEMPLATES}/AGENTS.md.tmpl" | tr -d ' ')"
  if [[ "$lines" -le 80 ]]; then ok "templates: AGENTS.md.tmpl is ${lines} lines (<=80)"; else ko "templates: AGENTS.md.tmpl is ${lines} lines (<=80)"; fi
  assert_contains "$(cat "${INIT_TEMPLATES}/cursor-rule.mdc.tmpl")" "alwaysApply: false" \
    "templates: cursor rule is path-scoped, never always-apply"
  assert_contains "$(cat "${INIT_TEMPLATES}/github/copilot-instructions.md.tmpl")" "AGENTS.md" \
    "templates: copilot instructions point at AGENTS.md"
  assert_contains "$(cat "${INIT_TEMPLATES}/ai-rule.md.tmpl")" "AGENTS.md" "templates: vendor-neutral rule points at AGENTS.md"
  repo="$(scratch_stack go)"
  assert_contains "$(render "$repo" github/copilot-instructions.md.tmpl)" "go test ./..." \
    "init[go]: copilot instructions carry the detected commands"
  if [[ "$(wc -l <"${INIT_TEMPLATES}/github/copilot-instructions.md.tmpl")" -le 30 ]]; then
    ok "templates: copilot instructions stay a short pointer"
  else
    ko "templates: copilot instructions stay a short pointer"
  fi
}

# ---------------------------------------------------------------------------
# init --migrate-rules — dry-run first, nothing lost silently
# ---------------------------------------------------------------------------

# long_claude_repo — committed repo with a long CLAUDE.md and a legacy pointer AGENTS.md.
long_claude_repo() {
  local dir
  dir="$(mkrepo)"
  {
    printf '# demo — Agent Rules\n\nA demo.\n\n## Precedence\n\n1. User.\n\n## MUST / MUST NOT\n\n- Never commit secrets.\n\n'
    printf '## Claude-only notes\n\n- Use /ycc: skills.\n\n## Commands\n\n```bash\nnpm test\n## not a heading\n```\n'
  } >"${dir}/CLAUDE.md"
  printf '# demo\n\nThe canonical agent rules live in CLAUDE.md.\n' >"${dir}/AGENTS.md"
  git -C "$dir" add -A
  git -C "$dir" commit -q -m "chore: add rules"
  echo "$dir"
}

test_migrate_rules() {
  local repo out rc before after
  repo="$(long_claude_repo)"
  before="$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md && git status --porcelain | wc -l)"

  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  rc=$?
  assert_exit "$rc" 0 "migrate: dry-run succeeds"
  after="$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md && git status --porcelain | wc -l)"
  assert_eq "$after" "$before" "migrate: dry-run changes nothing"
  assert_contains "$out" "Section routing" "migrate: dry-run prints per-section routing"
  assert_contains "$out" "## Claude-only notes -> CLAUDE.md" "migrate: exact Claude heading stays in CLAUDE.md"
  assert_contains "$out" "## Precedence -> AGENTS.md" "migrate: Precedence moves instead of being dropped"
  assert_contains "$out" "Replaced pointer-style AGENTS.md" "migrate: replaced legacy pointer is shown"
  assert_contains "$out" "| The canonical agent rules live in CLAUDE.md." "migrate: replaced pointer text is printed in full"

  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" 2>&1)"
  rc=$?
  assert_exit "$rc" 1 "migrate: refuses to write without --dry-run or --yes"

  echo "local edit" >>"${repo}/CLAUDE.md"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes 2>&1)"
  rc=$?
  assert_exit "$rc" 1 "migrate: refuses to apply over uncommitted rules edits"
  assert_contains "$out" "uncommitted changes" "migrate: names the uncommitted-changes safeguard"
  git -C "$repo" checkout -q -- CLAUDE.md

  bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes >/dev/null
  assert_eq "$(head -n 1 "${repo}/CLAUDE.md")" "@AGENTS.md" "migrate: CLAUDE.md now starts with @AGENTS.md"
  assert_contains "$(cat "${repo}/CLAUDE.md")" "Claude-only notes" "migrate: Claude-only section stays in CLAUDE.md"
  assert_contains "$(cat "${repo}/AGENTS.md")" "Never commit secrets" "migrate: rules moved into AGENTS.md"
  assert_contains "$(cat "${repo}/AGENTS.md")" "## Precedence" "migrate: Precedence content preserved in AGENTS.md"
  assert_contains "$(cat "${repo}/AGENTS.md")" "## not a heading" "migrate: fenced '## ' lines do not split sections"
  assert_eq "$(find "${repo}" -maxdepth 1 -name '.*.migrate-*' | wc -l | tr -d ' ')" "0" "migrate: no temp files left behind"
  assert_eq "$(find "$(git -C "$repo" rev-parse --absolute-git-dir)/ycc-rule-backups" -maxdepth 1 -mindepth 1 | wc -l | tr -d ' ')" "1" \
    "migrate: apply wrote one backup of the original pair"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes)"
  assert_contains "$out" "already a @AGENTS.md pointer" "migrate: second run is a no-op"
}

# mig_repo <name> <claude-bytes-via-printf-format> [agents-bytes] — committed scratch repo.
mig_repo() {
  local dir="${SANDBOX_ROOT}/mig.$1"
  mkdir -p "$dir"
  git -C "$dir" init -q
  printf "%b" "$2" >"${dir}/CLAUDE.md"
  [[ -n "${3:-}" ]] && printf "%b" "$3" >"${dir}/AGENTS.md"
  git -C "$dir" add -A
  git -C "$dir" commit -q -m "chore: seed"
  echo "$dir"
}

test_migrate_import_detection() {
  local repo out
  # Already migrated, CRLF and BOM variants: must be a no-op, never a self-import rewrite.
  repo="$(mig_repo crlf '@AGENTS.md\r\n## Claude notes\r\n- foo\r\n' '# a\r\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes)"
  assert_contains "$out" "already a @AGENTS.md pointer" "migrate: CRLF @AGENTS.md is detected as migrated"
  assert_eq "$(tr -d '\r' <"${repo}/AGENTS.md")" "# a" "migrate: CRLF no-op leaves AGENTS.md alone"
  repo="$(mig_repo bom '\xef\xbb\xbf@AGENTS.md\n' '# a\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_contains "$out" "already a @AGENTS.md pointer" "migrate: BOM @AGENTS.md is detected as migrated"
  # Not imports: fenced, commented, inline code, prose. Each must still be migrated.
  repo="$(mig_repo fence '# r\n\n```\n@AGENTS.md\n```\n\n## Rules\n- x\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_contains "$out" "Migration plan" "migrate: fenced @AGENTS.md is not an import"
  repo="$(mig_repo comment '# r\n<!--\n@AGENTS.md\n-->\n## Rules\n- x\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_contains "$out" "Migration plan" "migrate: commented @AGENTS.md is not an import"
  repo="$(mig_repo prose '# r\nAdd @AGENTS.md later, see `@AGENTS.md`.\n## Rules\n- x\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_contains "$out" "Migration plan" "migrate: prose mention of @AGENTS.md is not an import"
  # Dangling import fails loudly (same contract as pointer-targets.sh).
  repo="$(mig_repo dangling '@AGENTS.md\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes 2>&1)"
  assert_eq "$?" "1" "migrate: dangling @AGENTS.md import exits 1"
  # Cross-check against the release-model helper (BOM support is an init extension).
  local case_dir expect got targets
  for case_dir in crlf fence comment prose; do
    # All compared fixtures need an existing AGENTS.md so a dangling import
    # is distinguishable from a negative detection result.
    if [[ ! -f "${SANDBOX_ROOT}/mig.${case_dir}/AGENTS.md" ]]; then
      printf '# a\n' >"${SANDBOX_ROOT}/mig.${case_dir}/AGENTS.md"
    fi
    targets="$(bash "$POINTER_TARGETS" --repo "${SANDBOX_ROOT}/mig.${case_dir}" | tr '\n' ' ')"
    out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "${SANDBOX_ROOT}/mig.${case_dir}" --dry-run)"
    if [[ "$targets" == *"CLAUDE.md"* ]]; then expect=none; else expect=import; fi
    if [[ "$out" == *"already a @AGENTS.md pointer"* ]]; then got=import; else got=none; fi
    assert_eq "$got" "$expect" "migrate: ${case_dir} import decision agrees with release-model pointer-targets.sh"
  done
}

test_migrate_routing() {
  local repo out
  repo="$(mig_repo route '# t\n\n## General\n- g\n\n# Claude Code setup\n- c-setup\n\n## Using the Claude API client\n- api-line\n\n## Hooks\n- plain hooks text\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_contains "$out" "# Claude Code setup -> CLAUDE.md" "migrate: mid-file H1 is its own section and Claude-only"
  assert_contains "$out" "## Using the Claude API client -> AGENTS.md (ambiguous" "migrate: substring 'claude' alone does not divert content"
  assert_contains "$out" "## Hooks -> AGENTS.md (ambiguous" "migrate: generic Hooks heading is reported, not guessed"
  assert_contains "$out" "Ambiguous headings routed to AGENTS.md" "migrate: ambiguous headings are listed for review"
  bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes >/dev/null
  assert_contains "$(cat "${repo}/CLAUDE.md")" "c-setup" "migrate: Claude-only H1 content lands in CLAUDE.md"
  assert_eq "$(grep -c 'c-setup' "${repo}/AGENTS.md" || true)" "0" "migrate: Claude-only content does not leak into AGENTS.md"
  assert_contains "$(cat "${repo}/AGENTS.md")" "api-line" "migrate: Claude-API project content stays tool-neutral"
  assert_contains "$(cat "${repo}/AGENTS.md")" "plain hooks text" "migrate: no content is dangling or lost"
}

test_migrate_agents_merge() {
  local repo out
  repo="$(mig_repo merge '# demo\n\n## Commands\n- from-claude\n\n## Extra\n- extra\n' '# demo\n\nCustom note mentioning CLAUDE.md.\n\n## Commands\n- from-agents\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_contains "$out" "Merge conflict preserved" "migrate: conflicting duplicate sections are reported"
  bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes >/dev/null
  assert_eq "$(grep -c '^# demo' "${repo}/AGENTS.md")" "1" "migrate: no duplicate H1 after merging into an existing AGENTS.md"
  assert_eq "$(grep -c '^## Commands' "${repo}/AGENTS.md")" "1" "migrate: no duplicate ## Commands heading"
  assert_contains "$(cat "${repo}/AGENTS.md")" "from-agents" "migrate: existing AGENTS.md rule preserved"
  assert_contains "$(cat "${repo}/AGENTS.md")" "from-claude" "migrate: conflicting CLAUDE.md rule retained, not dropped"
  assert_contains "$(cat "${repo}/AGENTS.md")" "Custom note mentioning CLAUDE.md" "migrate: AGENTS.md that merely mentions CLAUDE.md is never replaced"
}

test_migrate_safety() {
  local repo out dir sub rc
  # Non-git: refused without --allow-non-git; with it, a backup is written and the pair is migrated.
  dir="${SANDBOX_ROOT}/mig.nongit"
  mkdir -p "$dir"
  printf '# r\n\n## Rules\n- x\n' >"${dir}/CLAUDE.md"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$dir" --yes 2>&1)"
  assert_eq "$?" "1" "migrate: non-git target is refused by default"
  assert_eq "$(head -n 1 "${dir}/CLAUDE.md")" "# r" "migrate: refused non-git run changed nothing"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$dir" --yes --allow-non-git)"
  assert_contains "$out" "Backups written" "migrate: --allow-non-git writes backups first"
  assert_eq "$(find "${dir}/.ycc-rule-backups" -name CLAUDE.md | wc -l | tr -d ' ')" "1" "migrate: backup copy of CLAUDE.md exists"
  # Git-ignored rules files are not silently overwritten.
  repo="$(mig_repo ignored '# r\n\n## Rules\n- x\n')"
  printf 'CLAUDE.md\n' >"${repo}/.gitignore"
  git -C "$repo" rm -q --cached CLAUDE.md
  git -C "$repo" add .gitignore && git -C "$repo" commit -q -m "chore: ignore"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes 2>&1)"
  assert_eq "$?" "1" "migrate: git-ignored rules file is refused"
  # --repo that is a subdirectory of a parent repo is refused (git would scope to the parent).
  sub="${repo}/sub"
  mkdir -p "$sub"
  printf '# r\n\n## Rules\n- x\n' >"${sub}/CLAUDE.md"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$sub" --yes 2>&1)"
  assert_eq "$?" "1" "migrate: non-root --repo inside a parent repo is refused"
  # Symlinked rules file and read-only target leave the pair untouched.
  repo="$(mig_repo ro '# r\n\n## Rules\n- x\n')"
  chmod a-w "${repo}/CLAUDE.md"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes 2>&1)"
  rc=$?
  if [[ "$(id -u)" != "0" ]]; then
    assert_eq "$rc" "2" "migrate: unwritable CLAUDE.md fails before any write"
    assert_eq "$(find "${repo}" -maxdepth 1 -name AGENTS.md | wc -l | tr -d ' ')" "0" "migrate: failed run does not leave a partial pair"
  fi
  chmod u+w "${repo}/CLAUDE.md"
  repo="$(mig_repo rollback '# r\n\n## Rules\n- x\n' '# custom\n\n- original\n')"
  local before after
  before="$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md)"
  out="$(python3 - "$INIT_SCRIPTS" "$repo" <<'PYFAULT'
import importlib.util, sys
from pathlib import Path
scripts, repo = map(Path, sys.argv[1:])
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location("migration", scripts / "migrate-rules.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
real = module.os.replace
calls = 0
def fault(src, dst):
    global calls
    calls += 1
    if calls == 2:
        raise OSError("simulated second rename failure")
    return real(src, dst)
module.os.replace = fault
sys.argv = ["migrate-rules", "--repo", str(repo), "--yes"]
sys.exit(module.main())
PYFAULT
  )"
  assert_exit "$?" 2 "migrate: second rename failure is reported"
  after="$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md)"
  assert_eq "$after" "$before" "migrate: failed second rename restores both files byte-for-byte"
  repo="$(mig_repo 'with spaces' '# r\n\n## Rules\n- x\n')"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_exit "$?" 0 "migrate: repository paths with spaces are supported"
  ln -s CLAUDE.md "${repo}/AGENTS.md"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run 2>&1)"
  assert_exit "$?" 1 "migrate: symlinked AGENTS.md is refused"
}

test_init_generated_mirrors() {
  local mirror repo out
  for mirror in .cursor-plugin/skills .codex-plugin/ycc/skills .opencode-plugin/skills .agents-plugin/skills; do
    local scripts="${REPO_ROOT}/${mirror}/init/scripts"
    local f
    for f in migrate-rules.sh migrate-rules.py rules_file_lib.py render-template.sh render-template.py profile-project.sh rules-report.sh count-source-files.sh; do
      if cmp -s "${INIT_SCRIPTS}/${f}" "${scripts}/${f}"; then
        ok "mirror: ${mirror} init/${f} is byte-identical to source"
      else
        ko "mirror: ${mirror} init/${f} is byte-identical to source"
      fi
    done
    # EXECUTE the generated migrate script on a temp canonical repo; content must be preserved.
    repo="$(mig_repo "exec.$(echo "$mirror" | tr '/.' '__')" '# demo\n\n## MUST / MUST NOT\n- Never commit secrets.\n\n## Claude-only notes\n- notes-here\n' '# demo\n\nThe canonical agent rules live in CLAUDE.md.\n')"
    out="$(bash "${scripts}/migrate-rules.sh" --repo "$repo" --yes 2>&1)"
    assert_exit "$?" 0 "mirror: ${mirror} migrate-rules.sh applies"
    assert_eq "$(head -n 1 "${repo}/CLAUDE.md")" "@AGENTS.md" "mirror: ${mirror} CLAUDE.md is the @AGENTS.md importer"
    assert_contains "$(cat "${repo}/AGENTS.md")" "Never commit secrets" "mirror: ${mirror} rules moved into AGENTS.md, not overwritten"
    assert_contains "$(cat "${repo}/CLAUDE.md")" "notes-here" "mirror: ${mirror} Claude-only content kept in CLAUDE.md"
    if [[ "$(cat "${repo}/AGENTS.md")" == *"@AGENTS.md"* ]]; then
      ko "mirror: ${mirror} AGENTS.md never imports itself"
    else
      ok "mirror: ${mirror} AGENTS.md never imports itself"
    fi
    # The generated renderer works too and keeps CLAUDE.md as the importer name.
    out="$(printf 'project_name=demo\n' | bash "${scripts}/render-template.sh" --template CLAUDE.md.tmpl)"
    assert_eq "$out" "@AGENTS.md" "mirror: ${mirror} renderer emits the @AGENTS.md shim"
  done
}

test_init_renderer_hardening() {
  local out rc repo
  out="$(bash "${INIT_SCRIPTS}/render-template.sh" --template /etc/passwd </dev/null 2>&1)"
  assert_eq "$?" "1" "render: template outside the bundled templates dir is rejected"
  assert_contains "$out" "bundled templates" "render: rejection names the allowed root"
  # A fixture bundle gives the renderer its own allowed template root; never edit source.
  local fixture="${SANDBOX_ROOT}/fixture-init"
  mkdir -p "$fixture/scripts" "$fixture/templates"
  cp "${INIT_SCRIPTS}/render-template.py" "$fixture/scripts/render-template.py"
  printf '{{#IF_RUST}}\ntext\n{{/IF_TS}}\n' >"$fixture/templates/bad.tmpl"
  out="$(python3 "$fixture/scripts/render-template.py" --template bad.tmpl </dev/null 2>&1)"
  assert_eq "$?" "1" "render: mismatched block closer fails"
  assert_contains "$out" "mismatched closer" "render: error identifies the unmatched block"
  printf '{{PLACEHOLDER2}}\n' >"$fixture/templates/digits.tmpl"
  out="$(python3 "$fixture/scripts/render-template.py" --template digits.tmpl </dev/null 2>&1)"
  assert_eq "$?" "1" "render: unresolved placeholders containing digits fail"
  mkdir -p "${SANDBOX_ROOT}/tpl-escape"
  repo="$(scratch_stack go)"
  # Mismatched traversal probe path is unquoted on purpose (no globs); keep shellcheck quiet.
  # shellcheck disable=SC2086
  out="$(bash "$PROFILE" "$repo" | bash "${INIT_SCRIPTS}/render-template.sh" --template ../../../../../..${SANDBOX_ROOT}/tpl-escape 2>&1)"
  assert_eq "$?" "1" "render: path traversal out of templates dir is rejected"
  # Process-substitution profile is accepted.
  out="$(bash "${INIT_SCRIPTS}/render-template.sh" --template AGENTS.md.tmpl --profile <(bash "$PROFILE" "$repo") --set PROJECT_PURPOSE=x 2>&1)"
  assert_contains "$out" "go test ./..." "render: --profile accepts a process-substitution path"
  # Unknown stack: lefthook renders a valid config (no 'run: # ...'), usage doc explains it.
  repo="$(mktemp -d "${SANDBOX_ROOT}/unk.XXXXXX")"
  git -C "$repo" init -q
  out="$(bash "$PROFILE" "$repo" | bash "${INIT_SCRIPTS}/render-template.sh" --template git/lefthook.yml.tmpl)"
  if grep -qE '^\s*run:\s*#' <<<"$out"; then ko "render: lefthook never renders 'run: # not detected'"; else ok "render: lefthook never renders 'run: # not detected'"; fi
  assert_contains "$out" "no pre-push hook is configured" "render: lefthook documents the omitted pre-push hook"
  out="$(bash "$PROFILE" "$repo" | bash "${INIT_SCRIPTS}/render-template.sh" --template git/lefthook-usage.md.tmpl)"
  assert_contains "$out" "Not configured (no test command detected)" "render: lefthook usage doc states the hook status"
  out="$(bash "$PROFILE" "$repo" | bash "${INIT_SCRIPTS}/render-template.sh" --template github/pull_request_template.md.tmpl)"
  if grep -q 'not detected' <<<"$out"; then ko "render: PR template has no 'not detected' checklist item"; else ok "render: PR template has no 'not detected' checklist item"; fi
  # Detected stack keeps the real pre-push test command.
  repo="$(scratch_stack go)"
  out="$(bash "$PROFILE" "$repo" | bash "${INIT_SCRIPTS}/render-template.sh" --template git/lefthook.yml.tmpl)"
  assert_contains "$out" "run: go test ./..." "render: detected test command still drives pre-push"
  # Mixed profiles keep every component language (lefthook + gitignore).
  out="$(printf 'primary_language=mixed\nsecondary_languages=typescript,python\nproject_name=m\n' | bash "${INIT_SCRIPTS}/render-template.sh" --template git/lefthook.yml.tmpl)"
  assert_contains "$out" "biome" "render: mixed profile keeps the TypeScript block"
  assert_contains "$out" "ruff" "render: mixed profile keeps the Python block"
  out="$(printf 'primary_language=mixed\nsecondary_languages=typescript,python\nproject_name=m\n' | bash "${INIT_SCRIPTS}/render-template.sh" --template git/gitignore.tmpl)"
  assert_contains "$out" "__pycache__" "render: mixed gitignore includes Python entries"
  assert_contains "$out" "node_modules" "render: mixed gitignore includes Node entries"
  # No Bash 4-only constructs in the shell helpers (stock macOS bash 3.2).
  if grep -nE 'declare -A|mapfile|readarray|\$\{[A-Za-z_]+,,\}|\$\{[A-Za-z_]+\^\^\}' \
      "${INIT_SCRIPTS}/render-template.sh" "${INIT_SCRIPTS}/migrate-rules.sh" "${INIT_SCRIPTS}/rules-report.sh" >/dev/null; then
    ko "init helpers: shell entrypoints avoid Bash 4-only constructs"
  else
    ok "init helpers: shell entrypoints avoid Bash 4-only constructs"
  fi
}

test_profile_detection_robustness() {
  local d out
  # Comments mentioning pytest/ruff and a tests/ dir (unittest) must not stamp commands.
  d="$(mktemp -d "${SANDBOX_ROOT}/pyc.XXXXXX")"
  git -C "$d" init -q
  printf '# we do not use pytest or ruff\n[project]\nname = "x"\n' >"${d}/pyproject.toml"
  mkdir "${d}/tests"
  out="$(bash "$PROFILE" "$d")"
  assert_eq "$(get_key "$out" test_cmd)" "unknown" "profile: pytest in a comment / bare tests dir is not a signal"
  assert_eq "$(get_key "$out" lint_cmd)" "unknown" "profile: ruff in a comment is not a signal"
  d="$(mktemp -d "${SANDBOX_ROOT}/pyd.XXXXXX")"
  git -C "$d" init -q
  printf '[project]\nname = "x"\n[dependency-groups]\ndev = ["pytest>=8", "ruff"]\n[build-system]\nrequires = ["hatchling"]\n' >"${d}/pyproject.toml"
  out="$(bash "$PROFILE" "$d")"
  assert_eq "$(get_key "$out" test_cmd)" "pytest" "profile: a pytest dependency is a signal"
  assert_eq "$(get_key "$out" lint_cmd)" "ruff check ." "profile: a ruff dependency is a signal"
  # check / format:check are not stamped as lint.
  d="$(mktemp -d "${SANDBOX_ROOT}/jsc.XXXXXX")"
  git -C "$d" init -q
  echo '{"name":"x","scripts":{"check":"tsc","test":"vitest"}}' >"${d}/package.json"
  out="$(bash "$PROFILE" "$d")"
  assert_eq "$(get_key "$out" lint_cmd)" "unknown" "profile: a 'check' script is not stamped as lint"
  # golangci config selects golangci-lint.
  d="$(scratch_stack go)"
  touch "${d}/.golangci.yml"
  assert_eq "$(get_key "$(bash "$PROFILE" "$d")" lint_cmd)" "golangci-lint run" "profile: .golangci config selects golangci-lint"
  # Missing jq warns instead of silently emitting unknown commands.
  local bindir t src
  bindir="$(mktemp -d "${SANDBOX_ROOT}/bin.XXXXXX")"
  for t in bash sh find git wc tr head grep basename cat sed awk mktemp dirname pwd ls cut sort uniq mv cp chmod touch printf readlink date python3 env rm; do
    src="$(command -v "$t" 2>/dev/null)" && ln -sf "$src" "${bindir}/${t}"
  done
  d="$(scratch_stack node)"
  out="$(PATH="$bindir" bash "$PROFILE" "$d" 2>&1)"
  assert_contains "$out" "jq is unavailable" "profile: missing jq prints a warning"
}

test_rules_report() {
  local repo out i
  repo="$(mktemp -d "${SANDBOX_ROOT}/rep.XXXXXX")"
  printf 'one\ntwo\n' >"${repo}/AGENTS.md"
  : >"${repo}/CLAUDE.md"
  for i in $(seq 1 205); do echo "line $i" >>"${repo}/CLAUDE.md"; done
  out="$(bash "${INIT_SCRIPTS}/rules-report.sh" --repo "$repo")"
  assert_contains "$out" "AGENTS.md: 2 lines" "report: reports actual AGENTS.md line count"
  assert_contains "$out" "CLAUDE.md: 205 lines  WARNING: over 200 lines" "report: warns above 200 lines"
}

test_init_docs_claims() {
  local skill
  skill="$(cat "${REPO_ROOT}/ycc/skills/init/SKILL.md")"
  assert_contains "$skill" "2.1.277" "docs: CLAUDE.md omission names the Claude Code minimum version"
  assert_contains "$skill" "when available" "docs: Cursor AGENTS.md support is qualified"
  assert_contains "$skill" "does not rely on Copilot following the link" "docs: Copilot pointer does not assert link following"
  if grep -q "Cursor reads \`AGENTS.md\`, so" <<<"$skill"; then ko "docs: no unqualified Cursor claim"; else ok "docs: no unqualified Cursor claim"; fi
  assert_contains "$(cat "${INIT_TEMPLATES}/github/copilot-instructions.md.tmpl")" "Conventional Commits" \
    "templates: Copilot instructions carry repo-neutral essentials"
  if grep -rn 'CLAUDE.md / AGENTS.md' "${INIT_TEMPLATES}" >/dev/null; then ko "templates: no stale 'CLAUDE.md / AGENTS.md' wording"; else ok "templates: no stale 'CLAUDE.md / AGENTS.md' wording"; fi
}

# ---------------------------------------------------------------------------
# release-model after init — "Branching & releases" appears exactly once

# ---------------------------------------------------------------------------
# init --migrate-rules on the actual pre-1092 root rules shape
# ---------------------------------------------------------------------------

test_migrate_pre1092_dry_run() {
  local repo before after out live
  repo="$(mig_repo pre1092 '# placeholder\n')"
  if ! git -C "$REPO_ROOT" cat-file -e cd4c57c:CLAUDE.md 2>/dev/null; then
    printf '%s[skip]%s migrate[pre-1092]: commit cd4c57c not available (shallow clone)\n' "" ""
    return 0
  fi
  git -C "$REPO_ROOT" show cd4c57c:CLAUDE.md >"${repo}/CLAUDE.md"
  git -C "$REPO_ROOT" show cd4c57c:AGENTS.md >"${repo}/AGENTS.md"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "chore: pre-1092 rules"
  before="$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md && git status --porcelain | wc -l)"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --dry-run)"
  assert_exit "$?" 0 "migrate[pre-1092]: dry-run on the real pre-YAN-1092 rules succeeds"
  after="$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md && git status --porcelain | wc -l)"
  assert_eq "$after" "$before" "migrate[pre-1092]: dry run changes nothing"
  assert_contains "$out" "## Stack Overview -> AGENTS.md" "migrate[pre-1092]: legacy sections are routed, not deleted"
  assert_contains "$out" "Retired legacy directive" "migrate[pre-1092]: stale 'CLAUDE.md is canonical' directives are reported"
  bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes >/dev/null
  assert_eq "$(head -n 1 "${repo}/CLAUDE.md")" "@AGENTS.md" "migrate[pre-1092]: CLAUDE.md becomes the importer"
  live="$(awk '/<!--/{c=1} !c && /(`?CLAUDE\.md`? is the source of truth|canonical agent rules for this repository live in)/{n++} /-->/{c=0} END{print n+0}' "${repo}/AGENTS.md")"
  assert_eq "$live" "0" "migrate[pre-1092]: no live legacy 'CLAUDE.md is canonical' directive remains"
  assert_contains "$(cat "${repo}/AGENTS.md")" "## Stack Overview" "migrate[pre-1092]: moved content present in AGENTS.md"
  assert_le "$(awk '/^(```|~~~)/{f=!f; next} !f && /^# /{n++} END{print n+0}' "${repo}/AGENTS.md")" 1 "migrate[pre-1092]: at most one H1 outside fences in the merged AGENTS.md"
}

# ---------------------------------------------------------------------------

test_release_model_single_pointer() {
  local repo target before_count total
  repo="$(scratch_stack go)"
  # init output (CLAUDE.md absent, no RELEASING.md yet): the canonical file is AGENTS.md.
  render "$repo" AGENTS.md.tmpl --set "PROJECT_PURPOSE=Demo." >"${repo}/AGENTS.md"
  printf '@AGENTS.md\n' >"${repo}/CLAUDE.md"
  target="$(bash "$POINTER_TARGETS" --repo "$repo")"
  assert_eq "$target" "AGENTS.md" "release-model after init: canonical target is AGENTS.md only"
  # Simulate release-model Phase 4: append the section to the single target when absent.
  before_count="$(grep -c '^## Branching & releases' "${repo}/${target}" || true)"
  assert_eq "$before_count" "0" "release-model after init: section absent before the run"
  printf '\n## Branching & releases\n\n[`RELEASING.md`](RELEASING.md) pointer.\n' >>"${repo}/${target}"
  total="$(cat "${repo}/AGENTS.md" "${repo}/CLAUDE.md" | grep -c '^## Branching & releases' || true)"
  assert_eq "$total" "1" "release-model after init: Branching & releases appears exactly once"

  # init run after RELEASING.md exists renders the section itself; release-model then finds it.
  render "$repo" AGENTS.md.tmpl --set "PROJECT_PURPOSE=Demo." --keep IF_RELEASE_MODEL >"${repo}/AGENTS.md"
  target="$(bash "$POINTER_TARGETS" --repo "$repo")"
  assert_eq "$(grep -c '^## Branching & releases' "${repo}/${target}")" "1" \
    "init with RELEASING.md: section rendered once into the canonical file"
  assert_eq "$(grep -c '^## Branching & releases' "${repo}/CLAUDE.md" || true)" "0" \
    "init with RELEASING.md: CLAUDE.md never gets the section"

  # Legacy inverted layout: AGENTS.md is a pointer to CLAUDE.md, so CLAUDE.md stays canonical.
  printf '# demo\n\nThe canonical agent rules for this repository live in [`CLAUDE.md`](CLAUDE.md).\n' >"${repo}/AGENTS.md"
  printf '# demo\n\n## Commands\n' >"${repo}/CLAUDE.md"
  assert_contains "$(bash "$POINTER_TARGETS" --repo "$repo" | tr '\n' ' ')" "CLAUDE.md" \
    "pointer-targets: legacy inverted layout still lists CLAUDE.md"

  # Neither rules file: no output, nothing created.
  assert_eq "$(bash "$POINTER_TARGETS" --repo "$(mkrepo)" | wc -l | tr -d ' ')" "0" \
    "pointer-targets: no rules files -> no target"
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

# ---------------------------------------------------------------------------
# YAN-1115 / GH #273 — headless context injection + Phase 2 counting
# ---------------------------------------------------------------------------

test_headless_context_injection() {
  local init_skill="${REPO_ROOT}/ycc/skills/init/SKILL.md"
  local fmt_skill="${REPO_ROOT}/ycc/skills/formatters/SKILL.md"
  local init_probes fmt_probes
  init_probes="$(grep -n '!`' "$init_skill")"
  fmt_probes="$(grep -n '!`' "$fmt_skill")"
  assert_eq "$(printf '%s\n' "$init_probes" | wc -l | tr -d ' ')" "1"     "headless: init SKILL.md has exactly one context-injection command"
  assert_contains "$init_probes"     '!`${CLAUDE_PLUGIN_ROOT}/skills/init/scripts/profile-project.sh`'     "headless: init context injects the single scoped profiler"
  if grep -qE '(\||2>/dev/null|head|pwd|ls )' <<<"$init_probes"; then
    ko "headless: init context probe has no pipeline, head, pwd, ls, or redirect"
  else
    ok "headless: init context probe has no pipeline, head, pwd, ls, or redirect"
  fi
  assert_eq "$(printf '%s\n' "$fmt_probes" | wc -l | tr -d ' ')" "1"     "headless: formatters SKILL.md has exactly one context-injection command"
  assert_contains "$fmt_probes"     '!`${CLAUDE_PLUGIN_ROOT}/skills/formatters/scripts/profile-style.sh`'     "headless: formatters context injects the single scoped profiler"
  if grep -qE '(\||2>/dev/null|head|pwd)' <<<"$fmt_probes"; then
    ko "headless: formatters context probe has no pipeline, head, pwd, or redirect"
  else
    ok "headless: formatters context probe has no pipeline, head, pwd, or redirect"
  fi
  # allowed-tools must not grant broad find/head/wc/pwd.
  local s
  for s in "$init_skill" "$fmt_skill"; do
    if sed -n '2,/^---$/p' "$s" | grep -qE 'Bash\((find|head|wc|pwd):'; then
      ko "headless: $(basename "$(dirname "$s")") allowed-tools grants no find/head/wc/pwd"
    else
      ok "headless: $(basename "$(dirname "$s")") allowed-tools grants no find/head/wc/pwd"
    fi
  done
  # Full profile output survives (keys past line 20/30 are preserved).
  local out
  out="$(bash "$PROFILE" "$REPO_ROOT")"
  assert_contains "$out" "has_releasing_md=true" "headless: init profile preserves late key has_releasing_md"
  assert_contains "$out" "claude_md_imports_agents=true" "headless: init profile preserves claude_md_imports_agents"
  assert_contains "$out" "project_name=" "headless: init profile preserves final key project_name"
  out="$(bash "${REPO_ROOT}/ycc/skills/formatters/scripts/profile-style.sh" "$REPO_ROOT")"
  assert_contains "$out" "docs_target=" "headless: formatters profile preserves late key docs_target"
  assert_contains "$out" "project_root=" "headless: formatters profile includes project_root"
}

test_count_source_files() {
  local counter="${INIT_SCRIPTS}/count-source-files.sh" repo out rc i
  repo="$(mktemp -d "${SANDBOX_ROOT}/cnt.XXXXXX")"
  out="$(bash "$counter" --repo "$repo")"
  assert_contains "$out" "count=0" "counter: empty directory reports 0"
  assert_contains "$out" "capped=false" "counter: empty directory is not capped"
  printf 'x\n' >"${repo}/a.txt"; printf 'x\n' >"${repo}/b.txt"
  mkdir -p "${repo}/node_modules/pkg" "${repo}/.venv/lib" "${repo}/dist"
  for i in $(seq 1 60); do
    printf 'x\n' >"${repo}/node_modules/pkg/f${i}.js"
    printf 'x\n' >"${repo}/.venv/lib/f${i}.py"
    printf 'x\n' >"${repo}/dist/f${i}.js"
  done
  out="$(bash "$counter" --repo "$repo")"
  assert_contains "$out" "count=2" "counter: excludes node_modules/.venv/dist"
  assert_contains "$out" "capped=false" "counter: excluded trees do not trip the cap"
  git -C "$repo" init -q && mkdir -p "${repo}/.git/objects/xx"
  for i in $(seq 1 60); do printf 'x\n' >"${repo}/.git/objects/xx/o${i}"; done
  out="$(bash "$counter" --repo "$repo")"
  assert_contains "$out" "count=2" "counter: excludes .git objects"
  for i in $(seq 1 60); do printf 'x\n' >"${repo}/src${i}.rs"; done
  out="$(bash "$counter" --repo "$repo")"
  assert_contains "$out" "count=51" "counter: stops at 51 (cap+1 means >50)"
  assert_contains "$out" "capped=true" "counter: sets capped=true above 50"
  assert_contains "$out" "cap=50" "counter: reports cap=50"
  assert_eq "$(printf '%s\n' "$out" | wc -l | tr -d ' ')" "3" "counter: bounded 3-line output"
  # Unreadable directory before the cap surfaces on stderr and exits 1 (not suppressed).
  if [[ "$(id -u)" -ne 0 ]]; then
    local bad
    bad="$(mktemp -d "${SANDBOX_ROOT}/cntbad.XXXXXX")"
    mkdir "${bad}/locked" && printf 'x\n' >"${bad}/locked/secret.txt"
    chmod 000 "${bad}/locked"
    out="$(bash "$counter" --repo "$bad" 2>&1)" && rc=0 || rc=1
    chmod 700 "${bad}/locked"
    assert_eq "$rc" "1" "counter: unreadable directory fails loudly"
    assert_contains "$out" "cannot scan" "counter: unreadable directory error is visible"
    if grep -q '^count=' <<<"$out"; then
      ko "counter: unreadable directory emits no partial count"
    else
      ok "counter: unreadable directory emits no partial count"
    fi
  fi
  if grep -q "count-source-files.sh" "${REPO_ROOT}/ycc/skills/init/SKILL.md" \
     && ! grep -q 'find . -type f | head' "${REPO_ROOT}/ycc/skills/init/SKILL.md"; then
    ok "counter: Phase 2 uses count-source-files.sh instead of find|head|wc"
  else
    ko "counter: Phase 2 uses count-source-files.sh instead of find|head|wc"
  fi
}

# ---------------------------------------------------------------------------
# YAN-1116 / GH #274 — python3 3.11 guard, BOM parity, shared pointer helper
# ---------------------------------------------------------------------------

make_python_stub() {
  local dir="$1" version="$2" code="$3"
  mkdir -p "$dir"
  cat >"${dir}/python3" <<STUB
#!/bin/sh
case "\$1" in
  -V|--version) echo "Python ${version}"; exit 0 ;;
  *) exit ${code} ;;
esac
STUB
  chmod +x "${dir}/python3"
}

test_python311_guard() {
  local stubdir out err rc runner
  stubdir="$(mktemp -d "${SANDBOX_ROOT}/py310stub.XXXXXX")"
  make_python_stub "$stubdir" "3.10.12" 1
  for runner in "${INIT_SCRIPTS}/profile-project.sh" "${INIT_SCRIPTS}/render-template.sh" \
                "${INIT_SCRIPTS}/migrate-rules.sh" "${INIT_SCRIPTS}/count-source-files.sh" \
                "${REPO_ROOT}/ycc/skills/_shared/scripts/rules-pointer.sh" \
                "${REPO_ROOT}/ycc/skills/release-model/scripts/pointer-targets.sh"; do
    out="$(PATH="${stubdir}:${PATH}" bash "$runner" --repo "$REPO_ROOT" 2>"${SANDBOX_ROOT}/g.err")" && rc=0 || rc=1
    err="$(cat "${SANDBOX_ROOT}/g.err")"
    assert_eq "$rc" "1" "guard: $(basename "$runner") exits 1 on python3 3.10 stub"
    assert_eq "$out" "" "guard: $(basename "$runner") emits no partial stdout"
    assert_contains "$err" "3.11+" "guard: $(basename "$runner") names Python 3.11+"
    assert_contains "$err" "3.10.12" "guard: $(basename "$runner") names found version"
  done
  # Missing python3 on PATH also fails cleanly.
  local emptybin
  emptybin="$(mktemp -d "${SANDBOX_ROOT}/nopy.XXXXXX")"
  for cmd in bash dirname; do
    if command -v "$cmd" >/dev/null 2>&1; then ln -sf "$(command -v "$cmd")" "${emptybin}/${cmd}" 2>/dev/null || true; fi
  done
  out="$(PATH="$emptybin" /bin/bash "${INIT_SCRIPTS}/profile-project.sh" "$REPO_ROOT" 2>"${SANDBOX_ROOT}/nopy.err")" && rc=0 || rc=1
  assert_eq "$rc" "1" "guard: missing python3 exits 1"
  assert_eq "$out" "" "guard: missing python3 emits no partial stdout"
  assert_contains "$(cat "${SANDBOX_ROOT}/nopy.err")" "3.11+" "guard: missing python3 names 3.11+"
  # Real 3.10 (negative) and 3.11 (positive) via uv when available.
  local uv_bin real310 real311 realdir
  uv_bin="$(command -v uv || true)"
  if [[ -n "$uv_bin" ]]; then
    real310="$("$uv_bin" python find --no-python-downloads 3.10 2>/dev/null || true)"
    real311="$("$uv_bin" python find --no-python-downloads 3.11 2>/dev/null || true)"
    if [[ -n "$real310" ]]; then
      realdir="$(mktemp -d "${SANDBOX_ROOT}/py310real.XXXXXX")"
      ln -s "$real310" "${realdir}/python3"
      out="$(PATH="${realdir}:${PATH}" bash "$PROFILE" "$REPO_ROOT" 2>"${SANDBOX_ROOT}/r310.err")" && rc=0 || rc=1
      assert_eq "$rc" "1" "guard: real Python 3.10 aborts profile-project.sh"
      assert_eq "$out" "" "guard: real Python 3.10 emits no partial stdout"
      assert_contains "$(cat "${SANDBOX_ROOT}/r310.err")" "3.11+" "guard: real Python 3.10 stderr names 3.11+"
      out="$("$real310" "${INIT_SCRIPTS}/migrate-rules.py" --repo "$REPO_ROOT" --dry-run 2>&1)" && rc=0 || rc=1
      assert_eq "$rc" "1" "guard: real Python 3.10 direct migrate-rules.py aborts cleanly (no ImportError)"
      assert_contains "$out" "3.11+" "guard: real Python 3.10 direct migrate-rules.py names 3.11+"
      out="$("$real310" "${INIT_SCRIPTS}/render-template.py" --template CLAUDE.md.tmpl </dev/null 2>&1)" && rc=0 || rc=1
      assert_eq "$rc" "1" "guard: real Python 3.10 direct render-template.py aborts cleanly"
    fi
    if [[ -n "$real311" ]]; then
      realdir="$(mktemp -d "${SANDBOX_ROOT}/py311real.XXXXXX")"
      ln -s "$real311" "${realdir}/python3"
      out="$(PATH="${realdir}:${PATH}" bash "$PROFILE" "$REPO_ROOT")" && rc=0 || rc=1
      assert_eq "$rc" "0" "guard: real Python 3.11 runs profile-project.sh"
      assert_contains "$out" "project_name=" "guard: real Python 3.11 emits complete profile"
      out="$(printf 'project_name=demo\n' | PATH="${realdir}:${PATH}" bash "${INIT_SCRIPTS}/render-template.sh" --template CLAUDE.md.tmpl)" && rc=0 || rc=1
      assert_eq "$rc" "0" "guard: real Python 3.11 renders CLAUDE.md.tmpl"
      assert_eq "$out" "@AGENTS.md" "guard: real Python 3.11 shim output is @AGENTS.md"
    fi
  fi
}

test_bom_parser_parity() {
  local dir out rc
  dir="$(mktemp -d "${SANDBOX_ROOT}/bom.XXXXXX")"
  mkdir -p "${dir}/.github"
  printf '\xef\xbb\xbf@AGENTS.md\r\n\r\n# Notes\r\n' >"${dir}/CLAUDE.md"
  printf '\xef\xbb\xbf# Rules\n\n- Be kind\n' >"${dir}/AGENTS.md"
  printf '\xef\xbb\xbf# Copilot\n' >"${dir}/.github/copilot-instructions.md"
  out="$(bash "${REPO_ROOT}/ycc/skills/_shared/scripts/rules-pointer.sh" imports-agents --repo "$dir")"
  assert_eq "$out" "imports_agents=true" "bom: shared parser detects BOM+CRLF @AGENTS.md import"
  assert_eq "$(bash "$POINTER_TARGETS" --repo "$dir" | tr '\n' ' ')" \
    "AGENTS.md .github/copilot-instructions.md " "bom: pointer-targets drops BOM+CRLF importing CLAUDE.md"
  out="$(bash "$PROFILE" "$dir")"
  assert_contains "$out" "claude_md_imports_agents=true" "bom: profile-project reports claude_md_imports_agents=true"
  assert_contains "$out" "agents_md_is_pointer=false" "bom: custom BOM AGENTS.md is not a legacy pointer"
  printf '\xef\xbb\xbf# Agents\nThe canonical agent rules live in CLAUDE.md.\n' >"${dir}/AGENTS.md"
  out="$(bash "$PROFILE" "$dir")"
  assert_contains "$out" "agents_md_is_pointer=true" "bom: legacy pointer AGENTS.md with BOM is detected"
  # BOM-prefixedpyproject.toml + requirements.txt in Python profile detection.
  local pyrepo
  pyrepo="$(mktemp -d "${SANDBOX_ROOT}/bompy.XXXXXX")"
  printf '\xef\xbb\xbf[project]\nname = "x"\n[build-system]\nrequires = ["hatchling"]\n' >"${pyrepo}/pyproject.toml"
  printf '\xef\xbb\xbfpytest>=8.0\nruff>=0.4\n' >"${pyrepo}/requirements.txt"
  out="$(bash "$PROFILE" "$pyrepo")"
  assert_contains "$out" "test_cmd=pytest" "bom: BOM pyproject.toml + requirements.txt detects pytest"
  assert_contains "$out" "lint_cmd=ruff check ." "bom: BOM requirements.txt detects ruff"
  assert_contains "$out" "build_cmd=python -m build" "bom: BOM pyproject.toml detects build-system"
  # BOM-prefixed profile (stdin and file) + BOM-prefixed template in render-template.py.
  local pfile="${SANDBOX_ROOT}/bom.prof"
  printf '\xef\xbb\xbfproject_name=bomdemo\nproject_purpose=test\nprimary_language=go\ntest_cmd=go test ./...\nlint_cmd=go vet ./...\nbuild_cmd=go build ./...\n' >"$pfile"
  out="$(bash "${INIT_SCRIPTS}/render-template.sh" --template AGENTS.md.tmpl --profile "$pfile")"
  assert_contains "$out" "# bomdemo — Agent Rules" "bom: file profile first key project_name survives BOM"
  out="$(bash "${INIT_SCRIPTS}/render-template.sh" --template AGENTS.md.tmpl --profile - <"$pfile")"
  assert_contains "$out" "# bomdemo — Agent Rules" "bom: stdin profile first key project_name survives BOM"
  local fixture="${SANDBOX_ROOT}/fixture-bom"
  mkdir -p "$fixture/scripts" "$fixture/templates"
  cp "${INIT_SCRIPTS}/render-template.py" "$fixture/scripts/render-template.py"
  printf '\xef\xbb\xbf{{#IF_GO}}\nhello {{PROJECT_NAME}}\n{{/IF_GO}}\n' >"$fixture/templates/t.tmpl"
  out="$(python3 "$fixture/scripts/render-template.py" --template t.tmpl --profile "$pfile")"
  assert_eq "$out" "hello bomdemo" "bom: template leading BOM does not break first-line {{#IF_*}} block"
  # release-state + collect-signals BOM parity.
  local rel
  rel="$(mktemp -d "${SANDBOX_ROOT}/bomrel.XXXXXX")"
  git -C "$rel" init -q
  { printf '\xef\xbb\xbf'; bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state-update.sh" \
      --print-block --model trunk-only --trunk main; } >"${rel}/RELEASING.md"
  out="$(bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state.sh" --repo "$rel" get)" && rc=0 || rc=1
  assert_eq "$rc" "0" "bom: release-state get parses BOM RELEASING.md"
  assert_contains "$out" "model=trunk-only" "bom: release-state get reads model from BOM file"
  bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state.sh" --repo "$rel" check >/dev/null 2>&1 && rc=0 || rc=1
  assert_eq "$rc" "0" "bom: release-state check passes on BOM RELEASING.md"
  bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state-update.sh" --repo "$rel" --set-trunk master >/dev/null
  assert_eq "$(head -c 3 "${rel}/RELEASING.md")" "$(printf '\xef\xbb\xbf')" "bom: release-state-update preserves BOM"
  # Reviewer regression: BOM rewrite must stay byte-exact under a UTF-8 locale (gawk substr is char-based).
  local loc
  for loc in C.UTF-8 en_US.UTF-8; do
    bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state-update.sh" --repo "$rel" --set-trunk main >/dev/null
    LC_ALL="$loc" bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state-update.sh" --repo "$rel" --set-trunk trunk2 >/dev/null
    out="$(LC_ALL="$loc" bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state.sh" --repo "$rel" get)" && rc=0 || rc=1
    assert_eq "$rc" "0" "bom: ${loc} locale rewrite leaves a parseable state block"
    assert_contains "$out" "trunk=trunk2" "bom: ${loc} locale rewrite applied the change"
    assert_eq "$(head -c 3 "${rel}/RELEASING.md" | od -An -tx1 | tr -d ' \n')" "efbbbf" "bom: ${loc} locale rewrite keeps exactly one BOM"
    assert_eq "$(grep -c 'ycc-release-state$' "${rel}/RELEASING.md")" "1" "bom: ${loc} locale rewrite has no duplicated marker"
  done
  # CRLF + BOM combination keeps both.
  printf '\xef\xbb\xbf' >"${rel}/crlf.md"
  sed 's/$/\r/' <(bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state-update.sh" --print-block --model trunk-only --trunk main) >>"${rel}/crlf.md"
  cp "${rel}/RELEASING.md" "${rel}/RELEASING.bak" && cp "${rel}/crlf.md" "${rel}/RELEASING.md"
  LC_ALL=C.UTF-8 bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state-update.sh" --repo "$rel" --set-trunk crlf2 >/dev/null
  assert_contains "$(LC_ALL=C.UTF-8 bash "${REPO_ROOT}/ycc/skills/_shared/scripts/release-state.sh" --repo "$rel" get)" "trunk=crlf2" "bom: CRLF+BOM file rewrites cleanly under UTF-8 locale"
  cp "${rel}/RELEASING.bak" "${rel}/RELEASING.md"
  mkdir -p "${rel}/.github/workflows"
  printf '\xef\xbb\xbfon:\n  push:\n    branches: [main]\n' >"${rel}/.github/workflows/ci.yml"
  git -C "$rel" add -A && git -C "$rel" commit -qm init
  out="$(bash "${REPO_ROOT}/ycc/skills/release-model/scripts/collect-signals.sh" --repo "$rel")"
  assert_contains "$out" "ci_trigger_branches=main" "bom: collect-signals reads BOM workflow YAML"
}

test_shared_pointer_helper() {
  local helper="${REPO_ROOT}/ycc/skills/_shared/scripts/rules-pointer.sh" dir out rc
  assert_eq "$(bash "$helper" claude-md-shim)" "@AGENTS.md" "helper: claude-md-shim emits @AGENTS.md"
  out="$(bash "$helper" claude-md-shim --notes "- only claude")"
  assert_eq "$out" "$(printf '@AGENTS.md\n\n## Claude-only notes\n\n- only claude')" \
    "helper: claude-md-shim with notes matches CLAUDE.md.tmpl shape"
  out="$(printf 'project_name=x\n' | bash "${INIT_SCRIPTS}/render-template.sh" --template CLAUDE.md.tmpl --keep IF_CLAUDE_ONLY --set 'CLAUDE_ONLY_NOTES=- only claude')"
  assert_eq "$out" "$(bash "$helper" claude-md-shim --notes '- only claude')" \
    "helper: render-template CLAUDE.md.tmpl and claude-md-shim agree byte-for-byte"
  # Grep proof: both init and release-model call rules-pointer.sh; pointer rule is in one file.
  assert_contains "$(cat "${REPO_ROOT}/ycc/skills/release-model/scripts/pointer-targets.sh")" \
    "rules-pointer.sh" "helper: release-model pointer-targets.sh calls rules-pointer.sh"
  assert_contains "$(cat "${REPO_ROOT}/ycc/skills/init/scripts/profile-project.sh")" \
    "rules-pointer.sh" "helper: init profile-project.sh calls rules-pointer.sh"
  assert_contains "$(cat "${REPO_ROOT}/ycc/skills/init/templates/CLAUDE.md.tmpl")" \
    "{{CLAUDE_MD_SHIM}}" "helper: CLAUDE.md.tmpl sources shim token from shared constant"
  # Release-model targets query never creates or modifies files in a repo with no rules files.
  dir="$(mktemp -d "${SANDBOX_ROOT}/nomut.XXXXXX")"
  out="$(bash "$POINTER_TARGETS" --repo "$dir")" && rc=0 || rc=1
  assert_eq "$rc" "0" "helper: pointer-targets succeeds on repo with no rules files"
  assert_eq "$out" "" "helper: pointer-targets prints nothing when no rules files exist"
  if [[ -e "${dir}/AGENTS.md" || -e "${dir}/CLAUDE.md" ]]; then
    ko "helper: pointer-targets never creates missing rules files"
  else
    ok "helper: pointer-targets never creates missing rules files"
  fi
  # Cross-target closure: every generated bundle has the shared helper and working wrappers.
  local mirror shared_dir
  for mirror in .cursor-plugin/skills .codex-plugin/ycc/skills .opencode-plugin/skills .agents-plugin/skills; do
    case "$mirror" in
      .cursor-plugin/*) shared_dir="${REPO_ROOT}/.cursor-plugin/skills/_shared/scripts" ;;
      .codex-plugin/*)  shared_dir="${REPO_ROOT}/.codex-plugin/ycc/shared/scripts" ;;
      .opencode-plugin/*) shared_dir="${REPO_ROOT}/.opencode-plugin/shared/scripts" ;;
      .agents-plugin/*) shared_dir="${REPO_ROOT}/.agents-plugin/ycc-shared/scripts" ;;
    esac
    for f in rules_pointer.py rules-pointer.sh require-python.sh; do
      if cmp -s "${REPO_ROOT}/ycc/skills/_shared/scripts/${f}" "${shared_dir}/${f}"; then
        ok "closure: ${mirror} has byte-identical shared ${f}"
      else
        ko "closure: ${mirror} has byte-identical shared ${f}"
      fi
    done
    out="$(bash "${REPO_ROOT}/${mirror}/release-model/scripts/pointer-targets.sh" --repo "$REPO_ROOT")"
    assert_eq "$out" "AGENTS.md" "closure: ${mirror} pointer-targets.sh resolves shared helper and returns AGENTS.md"
    out="$(bash "${REPO_ROOT}/${mirror}/init/scripts/count-source-files.sh" --repo "$REPO_ROOT")"
    assert_contains "$out" "capped=true" "closure: ${mirror} count-source-files.sh runs via shared guard"
  done
}

test_profile_releasing_md
test_apply_ci_default_branch
test_apply_ci_custom_default_branch
test_apply_ci_no_git
test_init_templates
test_init_rules_shape
test_migrate_rules
test_migrate_import_detection
test_migrate_routing
test_migrate_agents_merge
test_migrate_safety
test_migrate_pre1092_dry_run
test_init_generated_mirrors
test_init_renderer_hardening
test_profile_detection_robustness
test_rules_report
test_init_docs_claims
test_release_model_single_pointer
test_pointer_targets
test_git_cleanup_wiring
test_git_cleanup_sync_merge_pattern
test_headless_context_injection
test_count_source_files
test_python311_guard
test_bom_parser_parity
test_shared_pointer_helper

echo
echo "release-hygiene tests: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
