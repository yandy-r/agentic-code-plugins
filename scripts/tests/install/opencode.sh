#!/usr/bin/env bash
# install.sh tests — opencode: settings merge, remove, base remove, slices.
#
# Runs alone (bash scripts/tests/install/opencode.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh sync: opencode + cursor =="

home="$(new_home)"
cat > "${home}/.config/opencode/opencode.json" <<'JSON'
{
  "model": "9router/Frontier",
  "provider": { "9router": { "options": { "apiKey": "sk-local-secret" } } },
  "plugins": ["@user/local-plugin"]
}
JSON
run_install "${home}" sync --target opencode --intent settings,plugins >/dev/null
merged="$(cat "${home}/.config/opencode/opencode.json")"
assert_contains "${merged}" "sk-local-secret" "local provider credentials preserved"
assert_contains "${merged}" "@user/local-plugin" "local plugin preserved"
assert_contains "${merged}" "@prevalentware/opencode-goal-plugin" "repo plugin added"


echo "== install.sh remove: opencode settings and rules =="

home="$(new_home)"
cat > "${home}/.config/opencode/opencode.json" <<'JSON'
{
  "provider": { "9router": { "options": { "apiKey": "sk-local-secret" } } },
  "plugins": ["@user/local-plugin"]
}
JSON
run_install "${home}" sync --target opencode --intent settings,plugins,rules >/dev/null
run_install "${home}" remove --target opencode --intent settings,plugins,rules >/dev/null
merged="$(cat "${home}/.config/opencode/opencode.json")"
assert_contains "${merged}" "sk-local-secret" "opencode remove keeps provider credentials"
assert_contains "${merged}" "@user/local-plugin" "opencode remove keeps user plugin"
assert_not_contains "${merged}" "@prevalentware/opencode-goal-plugin" "opencode remove takes back repo plugin"
if [[ ! -L "${home}/.config/opencode/AGENTS.md" ]]; then ok "opencode remove unlinks AGENTS.md"; else ko "opencode remove unlinks AGENTS.md"; fi

echo

echo "== install.sh remove: opencode base =="

home="$(new_home)"
for unit in skills agents commands shared; do
    mkdir -p "${home}/.config/opencode/${unit}"
    cp -R "${REPO_ROOT}/.opencode-plugin/${unit}/." "${home}/.config/opencode/${unit}/"
done
run_install "${home}" remove --target opencode --intent base >/dev/null
leftover="$(find "${home}/.config/opencode" -mindepth 1 | head -3)"
if [[ -z "${leftover}" ]]; then ok "opencode base remove drops the bundle"; else ko "opencode base remove drops the bundle" "${leftover}"; fi


echo "== install.sh: opencode slices =="

home="$(new_home)"
HOME="${home}" YCC_MANAGED_CONFIG_STATE="${home}/.config/ycc/managed-config-state.json" \
    python3 "${REPO_ROOT}/scripts/install_slices.py" install --target opencode --slice skills >/dev/null
assert_contains "$(cat "${home}/.config/opencode/skills/releaser/SKILL.md")" "opencode/autoinvoke: 'false'" "opencode slice retains releaser manual invocation policy"
assert_not_contains "$(cat "${home}/.config/opencode/skills/init/SKILL.md")" 'opencode/autoinvoke' "opencode slice keeps init model-invocable"

home="$(new_home)"
for unit in skills agents commands shared; do
    mkdir -p "${home}/.config/opencode/${unit}"
    cp -R "${REPO_ROOT}/.opencode-plugin/${unit}/." "${home}/.config/opencode/${unit}/"
done
run_install "${home}" remove --target opencode --intent agents,commands >/dev/null
leftover="$(find "${home}/.config/opencode" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')"
if [[ "${leftover}" == "shared skills " ]]; then ok "opencode agents,commands remove keeps skills + shared"; else ko "opencode agents,commands remove keeps skills + shared" "${leftover}"; fi
run_install "${home}" remove --target opencode --intent skills >/dev/null
leftover="$(find "${home}/.config/opencode" -mindepth 1 | head -3)"
if [[ -z "${leftover}" ]]; then ok "opencode skills remove takes shared/ too"; else ko "opencode skills remove takes shared/ too" "${leftover}"; fi

# The slice helper directly (no generators): Codex skills land in
# ~/.codex/skills with plugin paths re-pointed there.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
