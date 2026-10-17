#!/usr/bin/env bash
# install.sh tests — bundle build: every target that ships a generated bundle
# regenerates, validates and formats it before syncing, and
# YCC_INSTALL_SKIP_BUILD=1 installs the committed bundle instead.
#
# Runs alone (bash scripts/tests/install/build.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Generator/validator passes a native base install runs, per target.
declare -A BUILD_PASSES=(
    [cursor]="agents skills rules"
    [codex]="skills plugin"
    [opencode]="skills agents commands plugin"
    [agents]="skills"
)

# codex_bundle_landed <home> — the legacy layout symlinks the plugin; a listed
# repository installs ycc@ycc through the (stubbed) Codex CLI instead.
codex_bundle_landed() {
    if repo_codex_native; then
        grep -q "codex plugin add ycc@ycc" "$1/claude-calls.log" 2>/dev/null
    else
        [[ -L "$1/.codex/plugins/ycc" ]]
    fi
}

echo "== install.sh install: base builds each bundle before syncing =="

home="$(new_home)"
install_must_succeed_build "${home}" install --target cursor,codex,opencode,agents --only base --skills-home native
out="${INSTALL_OUT}"
ok "base install with the real build succeeds"
for target in cursor codex opencode agents; do
    for pass in ${BUILD_PASSES[${target}]}; do
        assert_contains "${out}" "Running generate-${target}-${pass}.sh" "${target} build runs generate-${target}-${pass}.sh"
        assert_contains "${out}" "Running validate-${target}-${pass}.sh" "${target} build runs validate-${target}-${pass}.sh"
    done
done
assert_contains "${out}" "Running scripts/style.sh format --modified" "build formats modified repository files"
assert_not_contains "${out}" "Skipping" "real build skips nothing"
if [[ -f "${home}/.cursor/skills/backport/SKILL.md" && -f "${home}/.config/opencode/skills/backport/SKILL.md" \
    && -f "${home}/.agents/skills/backport/SKILL.md" ]] && codex_bundle_landed "${home}"; then
    ok "built bundles land in every target"
else
    ko "built bundles land in every target"
fi

echo
echo "== install.sh install: YCC_INSTALL_SKIP_BUILD=1 installs the committed bundle =="

home="$(new_home)"
YCC_INSTALL_SKIP_BUILD=1 install_must_succeed "${home}" install --target cursor,codex,opencode,agents --only base --skills-home native
out="${INSTALL_OUT}"
for target in cursor codex opencode agents; do
    for pass in ${BUILD_PASSES[${target}]}; do
        assert_contains "${out}" "Skipping generate-${target}-${pass}.sh" "skip-build skips generate-${target}-${pass}.sh"
        assert_contains "${out}" "Skipping validate-${target}-${pass}.sh" "skip-build skips validate-${target}-${pass}.sh"
    done
done
assert_contains "${out}" "Skipping repository formatting" "skip-build skips the repo style pass"
assert_not_contains "${out}" "Running " "skip-build runs no build script"
if [[ -f "${home}/.cursor/skills/backport/SKILL.md" && -f "${home}/.config/opencode/skills/backport/SKILL.md" \
    && -f "${home}/.agents/skills/backport/SKILL.md" ]] && codex_bundle_landed "${home}"; then
    ok "skip-build still syncs every target"
else
    ko "skip-build still syncs every target"
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
