#!/usr/bin/env bash
# Tests for scripts/lib/validate-scope.sh: the changed-path -> target mapping
# and the push-base detection behind `validate.sh --changed`.
#
# The git cases run in throwaway repos under a temp dir with an isolated git
# config, so the caller's repositories and global git settings are never used.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/validate-scope.sh
source "${SCRIPT_DIR}/lib/validate-scope.sh"

PASS=0
FAIL=0

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

ok() {
    PASS=$((PASS + 1))
    printf '%s[pass]%s %s\n' "${GREEN}" "${NC}" "$1"
}

ko() {
    FAIL=$((FAIL + 1))
    printf '%s[FAIL]%s %s\n' "${RED}" "${NC}" "$1"
    [[ -n "${2:-}" ]] && printf '       %s\n' "$2"
}

# expect_targets <name> <expected targets> <path>... — the paths select exactly
# the expected space-separated targets.
expect_targets() {
    local name="$1" expected="$2"
    shift 2
    local actual
    actual="$(printf '%s\n' "$@" | validate_scope_select | tr '\n' ' ')"
    actual="${actual% }"
    if [[ "${actual}" == "${expected}" ]]; then
        ok "${name}"
    else
        ko "${name}" "expected '${expected}', got '${actual}'"
    fi
}

ALL="${VALIDATE_TARGETS[*]}"
BUNDLES="inventory cursor codex opencode agents claude-native cursor-native codex-native packages release practices"

echo "== path -> target mapping =="

expect_targets "docs and repo meta select nothing" "" \
    docs/plans/demo/plan.md docs/research/notes.md CONTRIBUTING.md .github/pull_request_template.md .gitignore
expect_targets "no changed paths select nothing" ""
expect_targets "README.md selects inventory" "inventory" README.md
expect_targets "skill source selects the bundle targets, not config" "${BUNDLES}" ycc/skills/init/SKILL.md
expect_targets "agent source selects the bundle targets" "${BUNDLES}" ycc/agents/planner.md
expect_targets "generated Codex bundle selects content, native and parity" "codex codex-native packages" .codex-plugin/ycc/skills/init/SKILL.md
expect_targets "generated Claude aggregate selects generator, native and parity" "claude claude-native packages" packages/claude/ycc-all/.claude-plugin/plugin.json
expect_targets "generated Claude MCP selects generator, native and parity" "claude claude-native packages" packages/claude/ycc-mcp/.mcp.json
expect_targets "generated Cursor package selects content, native and parity" "cursor cursor-native packages" packages/cursor/ycc-mcp/mcp.json
expect_targets "Cursor installer fallback selects content, native and config" "cursor cursor-native config" packages/cursor/installer-fallback/config/cli-config.json
expect_targets "Cursor native wrapper selects content, native and config" "cursor cursor-native config" scripts/generate-cursor-packages.sh
expect_targets "Cursor native validator selects content, native and config" "cursor cursor-native config" scripts/validate-cursor-packages.sh
expect_targets "Cursor native policy selects content, native and config" "cursor cursor-native config" scripts/validate_cursor_native.py
expect_targets "Cursor native policy tests select content, native and config" "cursor cursor-native config" scripts/test_validate_cursor_native.py
expect_targets "Cursor generator selects content, native and config" "cursor cursor-native config" scripts/generate_cursor_packages.py
expect_targets "Cursor resources select content, native and config" "cursor cursor-native config" scripts/cursor_native_resources.py
expect_targets "Cursor package tests select content, native and config" "cursor cursor-native config" scripts/test_generate_cursor_packages.py
expect_targets "unrelated package output selects everything" "${ALL}" packages/other/ycc-mcp/mcp.json
expect_targets "Cursor hook source selects everything" "${ALL}" ycc/settings/cursor/herdr-session-start.sh
expect_targets "vendored Cursor schemas select cursor native and config" "cursor cursor-native config" scripts/vendor/cursor/plugin.schema.json
expect_targets "Claude generator selects claude native" "claude claude-native" scripts/generate_claude_packages.py
expect_targets "Claude validator selects claude native" "claude claude-native" scripts/validate-claude-packages.sh
expect_targets "Claude native policy selects claude native" "claude claude-native" scripts/validate_claude_native.py
expect_targets "Claude native policy tests select claude native" "claude claude-native" scripts/test_validate_claude_native.py
expect_targets "Codex generator selects codex native and config" "codex codex-native config" scripts/generate_codex_plugin.py
expect_targets "Codex validator selects codex native and config" "codex codex-native config" scripts/validate-codex-plugin.sh
expect_targets "Codex native policy selects codex native and config" "codex codex-native config" scripts/validate_codex_native.py
expect_targets "Codex native tests select codex native and config" "codex codex-native config" scripts/test_validate_codex_native.py
expect_targets "Codex generator tests selects codex native and config" "codex codex-native config" scripts/test_generate_codex_plugin.py
expect_targets "Codex catalog helper selects native and config" "codex-native config" scripts/codex_marketplace.py
expect_targets "Codex catalog tests select native and config" "codex-native config" scripts/test_codex_marketplace.py
expect_targets "Codex catalog selects agents native and packages" "agents codex-native packages" .agents/plugins/marketplace.json
expect_targets "Codex in-repo payload selects content, native and parity" "codex codex-native packages" .codex-plugin/ycc-mcp/.mcp.json
expect_targets "Claude generator wrapper selects generator and native" "claude claude-native" scripts/generate-claude-packages.sh
expect_targets "Claude generator tests select generator and native" "claude claude-native" scripts/test_generate_claude_packages.py
expect_targets "Claude smoke driver selects generator and native" "claude claude-native" scripts/claude_native_smoke.py
expect_targets "Claude live harness selects generator and native" "claude claude-native" scripts/test-claude-native-packages.sh
expect_targets "Claude marketplace selects native, JSON and parity" "claude-native json packages" .claude-plugin/marketplace.json
expect_targets "install.sh selects config" "config" install.sh
expect_targets "install tests select config" "config" scripts/tests/install/codex.sh
expect_targets "install target libs also select the coverage validators" "opencode agents config" \
    scripts/lib/install/targets/agents.sh
expect_targets "mods select mods and the install tests" "config mods" ycc/mods/README.md
expect_targets "release tests select release" "release" scripts/test-release-model.sh
expect_targets "plan-workflow validator test selects inventory" "inventory" scripts/test-plan-workflow-validators.sh
expect_targets "rename wrapper selects inventory" "inventory" scripts/rename-repo.sh
expect_targets "rename engine selects inventory" "inventory" scripts/rename_repo.py
expect_targets "rename shell tests select inventory" "inventory" scripts/test-rename-repo.sh
expect_targets "rename Python tests select inventory" "inventory" scripts/test_rename_repo.py
expect_targets "practices baseline selects practices" "practices" scripts/practices-baseline.json
expect_targets "claude rules select practices" "practices" .claude/rules/scripts.md
expect_targets "non-md claude rules file selects practices" "practices" .claude/rules/sub/notes.txt
expect_targets "practices rules module selects practices" "practices" scripts/practices_rules.py
expect_targets "package parity validator selects packages" "packages" scripts/validate_packages.py
expect_targets "package parity tests select packages" "packages" scripts/test_validate_packages.py
expect_targets "live install docs select packages" "packages" docs/install/cursor.md
expect_targets "v6 install drafts select packages before docs catch-all" "packages" docs/install/v6/codex.md
expect_targets "install doc indexes select packages" "packages" docs/install/README.md docs/install/v6/README.md
expect_targets "install ID validator selects packages" "packages" scripts/validate_install_doc_ids.py
expect_targets "install ID tests select packages" "packages" scripts/test_validate_install_doc_ids.py
expect_targets "settings select everything" "${ALL}" ycc/settings/models.json
expect_targets "package model selects content, native, generators and parity" "cursor codex opencode claude claude-native cursor-native codex-native packages" scripts/package_model.py
expect_targets "package graph builder selects packages" "packages" scripts/build_package_graph.py
expect_targets "package graph extractor selects packages" "packages" scripts/package_graph_extract.py
expect_targets "package graph tests select packages" "packages" scripts/test_package_graph.py
expect_targets "generators select everything" "${ALL}" scripts/generate_codex_skills.py
expect_targets "validate.sh selects everything" "${ALL}" scripts/validate.sh
expect_targets "the scope lib selects everything" "${ALL}" scripts/lib/validate-scope.sh
expect_targets "unrecognised paths select everything" "${ALL}" some/new/file.txt
expect_targets "CLAUDE.md selects everything" "${ALL}" CLAUDE.md
expect_targets "mixed paths union in target order" "inventory config mods" \
    ycc/mods/README.md docs/research/notes.md README.md
expect_targets "one unrecognised path widens a narrow set" "${ALL}" docs/README.md pyproject.toml

unknown=""
while IFS= read -r path; do
    for target in $(validate_scope_targets_for_path "${path}"); do
        [[ "${target}" == "all" || " ${ALL} " == *" ${target} "* ]] || unknown+="${path}:${target} "
    done
done < <(git -C "${REPO_ROOT}" ls-files)
if [[ -z "${unknown}" ]]; then
    ok "every tracked path maps to known targets"
else
    ko "every tracked path maps to known targets" "${unknown}"
fi

echo
echo "== push base and changed paths =="

# Git hooks (pre-push runs validate.sh) export GIT_DIR and friends; left set,
# they would point every sandbox git call at the caller's repository.
while IFS= read -r git_var; do
    unset "${git_var}"
done < <(git rev-parse --local-env-vars)
unset git_var

SANDBOX_ROOT="$(mktemp -d)"
trap 'rm -rf "${SANDBOX_ROOT}"' EXIT

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="${SANDBOX_ROOT}/gitconfig"
cat >"${GIT_CONFIG_GLOBAL}" <<'CFG'
[user]
	name = ycc test
	email = ycc-test@example.invalid
[init]
	defaultBranch = main
[commit]
	gpgsign = false
CFG

origin="${SANDBOX_ROOT}/origin.git"
work="${SANDBOX_ROOT}/work"
git init --quiet --bare "${origin}"
git init --quiet "${work}"
git -C "${work}" remote add origin "${origin}"
mkdir -p "${work}/docs" "${work}/ycc/skills/demo"
printf 'one\n' >"${work}/docs/a.md"
printf 'one\n' >"${work}/ycc/skills/demo/SKILL.md"
printf 'one\n' >"${work}/install.sh"
git -C "${work}" add -A
git -C "${work}" commit --quiet -m "chore: seed"

if validate_scope_base "${work}" >/dev/null; then
    ko "no push destination means no base"
else
    ok "no push destination means no base"
fi

git -C "${work}" push --quiet -u origin main
pushed="$(git -C "${work}" rev-parse HEAD)"

printf 'two\n' >"${work}/docs/a.md"
git -C "${work}" commit --quiet -am "docs: edit"
git -C "${work}" mv install.sh setup.sh
git -C "${work}" commit --quiet -m "chore: rename"
printf 'dirty\n' >"${work}/ycc/skills/demo/SKILL.md"

base="$(validate_scope_base "${work}")"
if [[ "${base}" == "${pushed}" ]]; then
    ok "base is the last pushed commit of the tracked branch"
else
    ko "base is the last pushed commit of the tracked branch" "expected ${pushed}, got ${base}"
fi

changed="$(validate_scope_changed_paths "${work}" "${base}" | sort | tr '\n' ' ')"
expected="docs/a.md install.sh setup.sh ycc/skills/demo/SKILL.md "
if [[ "${changed}" == "${expected}" ]]; then
    ok "changed paths cover commits, both sides of a rename and uncommitted edits"
else
    ko "changed paths cover commits, both sides of a rename and uncommitted edits" "got: ${changed}"
fi

git -C "${work}" checkout --quiet -- ycc/skills/demo/SKILL.md
git -C "${work}" checkout --quiet -b feature
printf 'three\n' >"${work}/docs/a.md"
git -C "${work}" commit --quiet -am "docs: branch edit"
base="$(validate_scope_base "${work}")"
if [[ "${base}" == "${pushed}" ]]; then
    ok "an unpushed branch falls back to the remote default branch"
else
    ko "an unpushed branch falls back to the remote default branch" "expected ${pushed}, got ${base}"
fi

echo
printf 'test-validate-scope: %d passed, %d failed\n' "${PASS}" "${FAIL}"
[[ ${FAIL} -eq 0 ]]
