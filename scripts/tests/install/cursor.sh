#!/usr/bin/env bash
# install.sh tests — cursor: settings, remove, base remove, slices.
#
# Runs alone (bash scripts/tests/install/cursor.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh sync: cursor =="

home="$(new_home)"
run_install "${home}" sync --target cursor --intent settings >/dev/null
assert_contains "$(cat "${home}/.cursor/cli-config.json")" '"claude-fable-5-1"' "cursor CLI model applied"

echo

echo "== install.sh remove: cursor settings and rules =="

home="$(new_home)"
cat > "${home}/.cursor/cli-config.json" <<'JSON'
{ "privacyMode": 1, "permissions": { "allow": ["Shell(ls)"], "deny": [] } }
JSON
run_install "${home}" sync --target cursor --intent settings,rules >/dev/null
run_install "${home}" remove --target cursor --intent settings,rules >/dev/null
merged="$(cat "${home}/.cursor/cli-config.json")"
assert_contains "${merged}" '"privacyMode": 1' "cursor remove keeps unmanaged keys"
assert_contains "${merged}" '"Shell(ls)"' "cursor remove keeps user permission entries"
assert_contains "${merged}" '"deny": []' "cursor remove keeps required permission keys"
assert_not_contains "${merged}" '"modelId"' "cursor remove drops managed model"
if [[ ! -L "${home}/.cursor/CLAUDE.md" ]]; then ok "cursor remove unlinks rules"; else ko "cursor remove unlinks rules"; fi


echo "== install.sh remove: cursor base =="

home="$(new_home)"
for unit in skills agents rules; do
    mkdir -p "${home}/.cursor/${unit}"
    cp -R "${REPO_ROOT}/.cursor-plugin/${unit}/." "${home}/.cursor/${unit}/"
done
mkdir -p "${home}/.cursor/skills/my-own-skill"
run_install "${home}" remove --target cursor --intent base >/dev/null
if [[ -d "${home}/.cursor/skills/my-own-skill" ]]; then ok "cursor base remove keeps user skills"; else ko "cursor base remove keeps user skills"; fi
leftover="$(find "${home}/.cursor/skills" -mindepth 1 -maxdepth 1 -printf '%f\n')"
if [[ "${leftover}" == "my-own-skill" ]]; then ok "cursor base remove drops bundle skills"; else ko "cursor base remove drops bundle skills" "${leftover}"; fi
if [[ ! -e "${home}/.cursor/agents" ]]; then ok "cursor base remove drops emptied agents dir"; else ko "cursor base remove drops emptied agents dir"; fi


echo "== install.sh: cursor slices =="

home="$(new_home)"
HOME="${home}" YCC_MANAGED_CONFIG_STATE="${home}/.config/ycc/managed-config-state.json" \
    python3 "${REPO_ROOT}/scripts/install_slices.py" install --target cursor --slice skills >/dev/null
assert_contains "$(cat "${home}/.cursor/skills/releaser/SKILL.md")" 'disable-model-invocation: true' "cursor slice retains releaser manual invocation policy"
assert_not_contains "$(cat "${home}/.cursor/skills/init/SKILL.md")" 'disable-model-invocation' "cursor slice keeps init model-invocable"

home="$(new_home)"
for unit in skills agents rules; do
    mkdir -p "${home}/.cursor/${unit}"
    cp -R "${REPO_ROOT}/.cursor-plugin/${unit}/." "${home}/.cursor/${unit}/"
done
mkdir -p "${home}/.cursor/skills/my-own-skill"
run_install "${home}" remove --target cursor --intent skills >/dev/null
leftover="$(find "${home}/.cursor/skills" -mindepth 1 -maxdepth 1 -printf '%f\n')"
if [[ "${leftover}" == "my-own-skill" ]]; then ok "cursor skills remove drops only bundle skills"; else ko "cursor skills remove drops only bundle skills" "${leftover}"; fi
if [[ -n "$(ls -A "${home}/.cursor/agents")" && -n "$(ls -A "${home}/.cursor/rules")" ]]; then ok "cursor skills remove keeps agents + rules"; else ko "cursor skills remove keeps agents + rules"; fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
