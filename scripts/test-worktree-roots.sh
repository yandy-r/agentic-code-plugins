#!/usr/bin/env bash
# test-worktree-roots.sh — per-runtime repo-local worktree roots (YAN-1111 / GH #271).
#
# Verifies, against every generated bundle's own worktree-paths.sh /
# setup-worktree.sh / list-worktrees.sh, using throwaway scratch repos:
#   - default root per bundle (claude/codex/cursor/opencode/agents)
#   - agents bundle runtime selection + .agents fallback (nested/unknown)
#   - YCC_WORKTREE_ROOT override (absolute, relative, ~, spaces)
#   - setup-worktree.sh parent + idempotency + list-worktrees.sh
#   - paths with spaces
#   - home rewrites preserved (~/.claude/ -> per-target home) next to worktree roots
#   - gitignore template and generated bundles ignore every root
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/ycc-worktree-roots.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

FAILED=0
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILED=1; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then pass "$label"; else fail "$label: expected '$expected' got '$actual'"; fi
}

# bundle-name -> shared scripts dir
declare -A BUNDLES=(
  [claude]="${REPO_ROOT}/ycc/skills/_shared/scripts"
  [codex]="${REPO_ROOT}/.codex-plugin/ycc/shared/scripts"
  [cursor]="${REPO_ROOT}/.cursor-plugin/skills/_shared/scripts"
  [opencode]="${REPO_ROOT}/.opencode-plugin/shared/scripts"
  [agents]="${REPO_ROOT}/.agents-plugin/ycc-shared/scripts"
)
# bundle-name -> expected default root dir name
declare -A EXPECTED=([claude]=.claude [codex]=.codex [cursor]=.cursor [opencode]=.opencode [agents]=.agents)

CLEAN_ENV=(env -u YCC_WORKTREE_ROOT -u OPENCODE -u CLAUDECODE -u CODEX_THREAD_ID)

make_repo() {
  local dir="$1"
  mkdir -p "$dir"
  git -C "$dir" init -q -b main
  git -C "$dir" -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m init
}

default_root() { # <bundle> <repo> [extra env assignments...]
  local bundle="$1" repo="$2"
  shift 2
  (cd "$repo" && "${CLEAN_ENV[@]}" "$@" bash -c 'source "$1"; ycc_worktree_root' _ "${BUNDLES[$bundle]}/worktree-paths.sh")
}

for bundle in claude codex cursor opencode agents; do
  [[ -f "${BUNDLES[$bundle]}/worktree-paths.sh" ]] || { fail "$bundle: worktree-paths.sh missing"; continue; }
  repo="${SCRATCH}/repo-${bundle}"
  make_repo "$repo"
  canon="$(cd "$repo" && pwd -P)"
  assert_eq "$bundle default root" "${canon}/${EXPECTED[$bundle]}/worktrees" "$(default_root "$bundle" "$repo")"
done

# Agents bundle: runtime selection with .agents fallback.
repo="${SCRATCH}/repo-agents"
canon="$(cd "$repo" && pwd -P)"
assert_eq "agents: OPENCODE=1 -> .opencode" "${canon}/.opencode/worktrees" "$(default_root agents "$repo" OPENCODE=1)"
assert_eq "agents: CLAUDECODE=1 -> .claude" "${canon}/.claude/worktrees" "$(default_root agents "$repo" CLAUDECODE=1)"
assert_eq "agents: CODEX_THREAD_ID -> .codex" "${canon}/.codex/worktrees" "$(default_root agents "$repo" CODEX_THREAD_ID=t1)"
assert_eq "agents: nested markers -> .agents" "${canon}/.agents/worktrees" "$(default_root agents "$repo" OPENCODE=1 CLAUDECODE=1)"
assert_eq "agents: OPENCODE=0 ignored -> .agents" "${canon}/.agents/worktrees" "$(default_root agents "$repo" OPENCODE=0)"
assert_eq "agents: empty CODEX_THREAD_ID -> .agents" "${canon}/.agents/worktrees" "$(default_root agents "$repo" CODEX_THREAD_ID=)"
assert_eq "agents: unsupported CURSOR_AGENT -> .agents" "${canon}/.agents/worktrees" "$(default_root agents "$repo" CURSOR_AGENT=1)"

# Non-agents bundles must NOT be influenced by runtime markers.
for bundle in claude codex cursor opencode; do
  repo="${SCRATCH}/repo-${bundle}"
  canon="$(cd "$repo" && pwd -P)"
  assert_eq "$bundle ignores runtime markers" "${canon}/${EXPECTED[$bundle]}/worktrees" "$(default_root "$bundle" "$repo" OPENCODE=1 CLAUDECODE=1)"
done

# setup-worktree.sh / list-worktrees.sh / override / spaces / idempotency.
for bundle in claude codex cursor opencode agents; do
  scripts="${BUNDLES[$bundle]}"
  repo="${SCRATCH}/with space/repo-${bundle}"
  make_repo "$repo"
  canon="$(cd "$repo" && pwd -P)"
  name="$(basename "$repo")"
  expected_path="${canon}/${EXPECTED[$bundle]}/worktrees/${name}-feat-one"

  got="$(cd "$repo" && "${CLEAN_ENV[@]}" bash "${scripts}/setup-worktree.sh" parent "$name" feat-one 2>/dev/null)"
  assert_eq "$bundle setup parent path (spaces)" "$expected_path" "$got"
  [[ -e "${expected_path}/.git" ]] && pass "$bundle worktree created" || fail "$bundle worktree not created"

  again="$(cd "$repo" && "${CLEAN_ENV[@]}" bash "${scripts}/setup-worktree.sh" parent "$name" feat-one 2>/dev/null)"
  assert_eq "$bundle setup idempotent" "$expected_path" "$again"

  listed="$(cd "$repo" && "${CLEAN_ENV[@]}" bash "${scripts}/list-worktrees.sh" "$name" feat-one)"
  grep -qF "${EXPECTED[$bundle]}/worktrees/${name}-feat-one" <<<"$listed" \
    && pass "$bundle list-worktrees sees root" || fail "$bundle list-worktrees missing root: $listed"

  # Absolute override
  override="${SCRATCH}/override root/${bundle}"
  got="$(cd "$repo" && env -u OPENCODE -u CLAUDECODE -u CODEX_THREAD_ID YCC_WORKTREE_ROOT="$override" bash "${scripts}/setup-worktree.sh" parent "$name" feat-two 2>/dev/null)"
  assert_eq "$bundle absolute override" "${override}/${name}-feat-two" "$got"

  # Relative override resolves against repo root
  got="$(cd "$repo" && env -u OPENCODE -u CLAUDECODE -u CODEX_THREAD_ID YCC_WORKTREE_ROOT="rel/wt" bash "${scripts}/setup-worktree.sh" parent "$name" feat-three 2>/dev/null)"
  assert_eq "$bundle relative override" "${canon}/rel/wt/${name}-feat-three" "$got"

  # ~ override
  got="$(cd "$repo" && env -u OPENCODE -u CLAUDECODE -u CODEX_THREAD_ID HOME="${SCRATCH}/home" YCC_WORKTREE_ROOT="~/wt" bash -c 'source "$1"; ycc_worktree_root' _ "${scripts}/worktree-paths.sh")"
  assert_eq "$bundle ~ override" "${SCRATCH}/home/wt" "$got"
done

# Home rewrites preserved: ~/.claude/ still retargets to each runtime's user-global home.
check_home() { # <label> <file> <expected-substring> <forbidden-substring>
  local label="$1" file="$2" want="$3" bad="$4"
  if [[ ! -f "$file" ]]; then fail "$label: missing $file"; return; fi
  grep -qF -- "$want" "$file" && pass "$label has '$want'" || fail "$label lacks '$want'"
  if grep -qF -- "$bad" "$file"; then fail "$label contains forbidden '$bad'"; else pass "$label free of '$bad'"; fi
}
# git-cleanup/SKILL.md names both ~/.claude-worktrees/ (legacy) and a user-global ~/.claude/ path.
check_home "opencode home rewrite" "${REPO_ROOT}/.opencode-plugin/shared/references/worktree-strategy.md" ".opencode/worktrees" ".config/opencode/.opencode"
check_home "opencode worktree-paths" "${REPO_ROOT}/.opencode-plugin/shared/scripts/worktree-paths.sh" ".opencode/worktrees" ".config/opencode/worktrees"
if grep -rqF '~''/.config/opencode/' "${REPO_ROOT}/.opencode-plugin/skills" 2>/dev/null; then
  pass "opencode ~/.config/opencode/ home rewrite preserved"
else
  fail "opencode ~/.config/opencode/ home rewrite lost"
fi
if grep -rqF '~''/.cursor/' "${REPO_ROOT}/.cursor-plugin/skills" 2>/dev/null; then pass "cursor ~/.cursor/ home rewrite preserved"; else fail "cursor home rewrite lost"; fi
if grep -rqF '~''/.codex/' "${REPO_ROOT}/.codex-plugin/ycc/skills" 2>/dev/null; then pass "codex ~/.codex/ home rewrite preserved"; else fail "codex home rewrite lost"; fi

# No generated bundle may contain the retired opencode root as a live default.
if grep -rn 'config/opencode/worktrees' "${REPO_ROOT}/.opencode-plugin" "${REPO_ROOT}/.codex-plugin" "${REPO_ROOT}/.cursor-plugin" "${REPO_ROOT}/.agents-plugin" \
  | grep -v 'worktree-strategy.md' | grep -q .; then
  fail "retired .config/opencode/worktrees default still present in a bundle"
else
  pass "no live .config/opencode/worktrees default in bundles"
fi

# Claude WorktreeCreate hook (ycc/settings/hooks/worktree-create.sh) direct smoke tests.
HOOK_SH="${REPO_ROOT}/ycc/settings/hooks/worktree-create.sh"
hook_repo="${SCRATCH}/with space/hook-repo"
make_repo "$hook_repo"
hook_canon="$(cd "$hook_repo" && pwd -P)"
hook_name="$(basename "$hook_repo")"

run_hook() { # <slug> [extra env assignments...]
  local slug="$1"
  shift
  printf '{"name":"%s","cwd":"%s","session_id":"s1","hook_event_name":"WorktreeCreate"}' "$slug" "$hook_canon" \
    | "${CLEAN_ENV[@]}" "$@" bash "$HOOK_SH" 2>/dev/null
}

assert_eq "hook default root (spaces in cwd)" \
  "${hook_canon}/.claude/worktrees/${hook_name}-hook-default" \
  "$(run_hook hook-default)"
[[ -e "${hook_canon}/.claude/worktrees/${hook_name}-hook-default/.git" ]] \
  && pass "hook default created worktree" || fail "hook default missing .git"

assert_eq "hook ~ override" \
  "${SCRATCH}/hook-home/wt/${hook_name}-hook-tilde" \
  "$(run_hook hook-tilde HOME="${SCRATCH}/hook-home" YCC_WORKTREE_ROOT="~/wt")"
assert_eq "hook bare ~ override" \
  "${SCRATCH}/hook-bare-home/${hook_name}-hook-bare" \
  "$(run_hook hook-bare HOME="${SCRATCH}/hook-bare-home" YCC_WORKTREE_ROOT="~")"
assert_eq "hook relative override (with space)" \
  "${hook_canon}/rel wt/${hook_name}-hook-rel" \
  "$(run_hook hook-rel YCC_WORKTREE_ROOT="rel wt")"
assert_eq "hook absolute override (with space)" \
  "${SCRATCH}/hook abs root/${hook_name}-hook-abs" \
  "$(run_hook hook-abs YCC_WORKTREE_ROOT="${SCRATCH}/hook abs root")"

# worktree-strategy.md: outside the protected evidence block, target rewrites apply.
for strat in \
  "${REPO_ROOT}/.codex-plugin/ycc/shared/references/worktree-strategy.md" \
  "${REPO_ROOT}/.cursor-plugin/skills/_shared/references/worktree-strategy.md" \
  "${REPO_ROOT}/.opencode-plugin/shared/references/worktree-strategy.md" \
  "${REPO_ROOT}/.agents-plugin/ycc-shared/references/worktree-strategy.md"; do
  if grep -qE 'ycc:|ycc/skills/|Agent\(isolation|<!-- ycc:verbatim-block' "$strat"; then
    fail "${strat#"$REPO_ROOT"/} leaked unrewritten source token or marker"
  else
    pass "${strat#"$REPO_ROOT"/} rewritten cleanly outside verbatim block"
  fi
done

# Gitignore coverage: repo .gitignore + init template (source and every bundle).
ROOTS=(.claude/worktrees/ .opencode/worktrees/ .codex/worktrees/ .cursor/worktrees/ .agents/worktrees/)
for f in \
  "${REPO_ROOT}/.gitignore" \
  "${REPO_ROOT}/ycc/skills/init/templates/git/gitignore.tmpl" \
  "${REPO_ROOT}/.codex-plugin/ycc/skills/init/templates/git/gitignore.tmpl" \
  "${REPO_ROOT}/.cursor-plugin/skills/init/templates/git/gitignore.tmpl" \
  "${REPO_ROOT}/.opencode-plugin/skills/init/templates/git/gitignore.tmpl" \
  "${REPO_ROOT}/.agents-plugin/skills/init/templates/git/gitignore.tmpl"; do
  for r in "${ROOTS[@]}"; do
    grep -qxF "$r" "$f" && pass "$(basename "$(dirname "$f")")/$(basename "$f") ignores $r" || fail "${f#"$REPO_ROOT"/} missing $r"
  done
done

if [[ "$FAILED" -ne 0 ]]; then
  echo "test-worktree-roots.sh: FAILED" >&2
  exit 1
fi
echo "test-worktree-roots.sh: all checks passed"
