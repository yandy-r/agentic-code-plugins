#!/usr/bin/env bash
# install.sh tests — cursor: settings, remove, base remove, slices.
#
# Runs alone (bash scripts/tests/install/cursor.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh sync: cursor =="

home="$(new_home)"
install_must_succeed "${home}" sync --target cursor --intent settings
assert_contains "$(cat "${home}/.cursor/cli-config.json")" '"claude-fable-5-1"' "cursor CLI model applied"

echo

echo "== install.sh remove: cursor settings and rules =="

home="$(new_home)"
cat > "${home}/.cursor/cli-config.json" <<'JSON'
{ "privacyMode": 1, "permissions": { "allow": ["Shell(ls)"], "deny": [] } }
JSON
install_must_succeed "${home}" sync --target cursor --intent settings,rules
install_must_succeed "${home}" remove --target cursor --intent settings,rules
merged="$(cat "${home}/.cursor/cli-config.json")"
assert_contains "${merged}" '"privacyMode": 1' "cursor remove keeps unmanaged keys"
assert_contains "${merged}" '"Shell(ls)"' "cursor remove keeps user permission entries"
assert_contains "${merged}" '"deny": []' "cursor remove keeps required permission keys"
assert_not_contains "${merged}" '"modelId"' "cursor remove drops managed model"
if [[ ! -L "${home}/.cursor/CLAUDE.md" ]]; then ok "cursor remove unlinks rules"; else ko "cursor remove unlinks rules"; fi


echo "== install.sh remove: cursor base =="

home="$(new_home)"
for unit in skills agents rules; do
    src="${REPO_ROOT}/packages/cursor/ycc/${unit}"
    [[ "${unit}" == "rules" ]] && src="${REPO_ROOT}/packages/cursor/ycc-rules/rules"
    mkdir -p "${home}/.cursor/${unit}"
    cp -R "${src}/." "${home}/.cursor/${unit}/"
done
mkdir -p "${home}/.cursor/skills/my-own-skill"
install_must_succeed "${home}" remove --target cursor --intent base
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
    src="${REPO_ROOT}/packages/cursor/ycc/${unit}"
    [[ "${unit}" == "rules" ]] && src="${REPO_ROOT}/packages/cursor/ycc-rules/rules"
    mkdir -p "${home}/.cursor/${unit}"
    cp -R "${src}/." "${home}/.cursor/${unit}/"
done
mkdir -p "${home}/.cursor/skills/my-own-skill"
install_must_succeed "${home}" remove --target cursor --intent skills
leftover="$(find "${home}/.cursor/skills" -mindepth 1 -maxdepth 1 -printf '%f\n')"
if [[ "${leftover}" == "my-own-skill" ]]; then ok "cursor skills remove drops only bundle skills"; else ko "cursor skills remove drops only bundle skills" "${leftover}"; fi
if [[ -n "$(ls -A "${home}/.cursor/agents")" && -n "$(ls -A "${home}/.cursor/rules")" ]]; then ok "cursor skills remove keeps agents + rules"; else ko "cursor skills remove keeps agents + rules"; fi

echo
echo "== install.sh rules: cursor provisions no global rules files =="

home="$(new_home)"
install_must_succeed "${home}" install --target cursor --only rules
out="${INSTALL_OUT}"
assert_contains "${out}" "Cursor Settings → Rules" "cursor rules prints manual User Rules guidance"
for f in CLAUDE.md AGENTS.md; do
    if [[ ! -e "${home}/.cursor/${f}" && ! -L "${home}/.cursor/${f}" ]]; then ok "cursor rules creates no ~/.cursor/${f}"; else ko "cursor rules creates no ~/.cursor/${f}"; fi
done

home="$(new_home)"
ln -s "${REPO_ROOT}/ycc/settings/rules/CLAUDE.md" "${home}/.cursor/CLAUDE.md"
ln -s "${REPO_ROOT}/ycc/settings/rules/AGENTS.md" "${home}/.cursor/AGENTS.md"
install_must_succeed "${home}" install --target cursor --only rules
if [[ -L "${home}/.cursor/CLAUDE.md" && -L "${home}/.cursor/AGENTS.md" ]]; then ok "cursor install leaves legacy links alone"; else ko "cursor install leaves legacy links alone"; fi
install_must_succeed "${home}" remove --target cursor --intent rules
for f in CLAUDE.md AGENTS.md; do
    if [[ ! -e "${home}/.cursor/${f}" && ! -L "${home}/.cursor/${f}" ]]; then ok "cursor remove unlinks legacy ~/.cursor/${f}"; else ko "cursor remove unlinks legacy ~/.cursor/${f}"; fi
done

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
