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
  assert_contains "$out" "Content-loss list" "migrate: dry-run prints the content-loss list"
  assert_contains "$out" "## Precedence" "migrate: dropped Precedence section is listed"
  assert_contains "$out" "AGENTS.md pointer boilerplate" "migrate: replaced legacy pointer is listed"
  assert_contains "$out" "## MUST / MUST NOT" "migrate: diff shows MUST section moving"

  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" 2>&1)"
  rc=$?
  assert_exit "$rc" 1 "migrate: refuses to write without --dry-run or --yes"
  assert_eq "$(cd "$repo" && sha256sum CLAUDE.md AGENTS.md && git status --porcelain | wc -l)" "$before" \
    "migrate: refusal changes nothing"

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
  assert_contains "$(cat "${repo}/AGENTS.md")" "## not a heading" "migrate: fenced '## ' lines do not split sections"
  out="$(bash "${INIT_SCRIPTS}/migrate-rules.sh" --repo "$repo" --yes)"
  assert_contains "$out" "already a @AGENTS.md pointer" "migrate: second run is a no-op"
}

# ---------------------------------------------------------------------------
# release-model after init — "Branching & releases" appears exactly once
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

test_profile_releasing_md
test_apply_ci_default_branch
test_apply_ci_custom_default_branch
test_apply_ci_no_git
test_init_templates
test_init_rules_shape
test_migrate_rules
test_release_model_single_pointer
test_pointer_targets
test_git_cleanup_wiring
test_git_cleanup_sync_merge_pattern

echo
echo "release-hygiene tests: ${PASS} passed, ${FAIL} failed"
[[ "$FAIL" -eq 0 ]]
