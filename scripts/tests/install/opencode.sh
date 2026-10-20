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
install_must_succeed "${home}" sync --target opencode --intent settings,plugins
merged="$(cat "${home}/.config/opencode/opencode.json")"
assert_contains "${merged}" "sk-local-secret" "local provider credentials preserved"
assert_contains "${merged}" "@user/local-plugin" "local plugin preserved"
assert_contains "${merged}" "@prevalentware/opencode-goal-plugin" "repo plugin added"
assert_contains "${merged}" "./ycc-sensitive-guard" "sensitive-file guard plugin entry added"
if [[ -f "${home}/.config/opencode/ycc-sensitive-guard/index.js" && -f "${home}/.config/opencode/ycc-sensitive-guard/policy.json" ]]; then
    ok "plugins group installs the guard directory its entry loads"
else
    ko "plugins group installs the guard directory its entry loads"
fi


echo "== install.sh remove: opencode settings and rules =="

home="$(new_home)"
cat > "${home}/.config/opencode/opencode.json" <<'JSON'
{
  "provider": { "9router": { "options": { "apiKey": "sk-local-secret" } } },
  "plugins": ["@user/local-plugin"]
}
JSON
install_must_succeed "${home}" sync --target opencode --intent settings,plugins,rules
install_must_succeed "${home}" remove --target opencode --intent settings,plugins,rules
merged="$(cat "${home}/.config/opencode/opencode.json")"
assert_contains "${merged}" "sk-local-secret" "opencode remove keeps provider credentials"
assert_contains "${merged}" "@user/local-plugin" "opencode remove keeps user plugin"
assert_not_contains "${merged}" "@prevalentware/opencode-goal-plugin" "opencode remove takes back repo plugin"
assert_not_contains "${merged}" "./ycc-sensitive-guard" "opencode remove takes back the guard plugin entry"
if [[ ! -e "${home}/.config/opencode/ycc-sensitive-guard" ]]; then ok "opencode remove takes back the guard directory"; else ko "opencode remove takes back the guard directory"; fi
if [[ ! -L "${home}/.config/opencode/AGENTS.md" ]]; then ok "opencode remove unlinks AGENTS.md"; else ko "opencode remove unlinks AGENTS.md"; fi

echo

echo "== install.sh remove: opencode base =="

home="$(new_home)"
for unit in skills agents commands shared ycc-sensitive-guard; do
    mkdir -p "${home}/.config/opencode/${unit}"
    cp -R "${REPO_ROOT}/.opencode-plugin/${unit}/." "${home}/.config/opencode/${unit}/"
done
install_must_succeed "${home}" remove --target opencode --intent base
leftover="$(find "${home}/.config/opencode" -mindepth 1 | head -3)"
if [[ -z "${leftover}" ]]; then ok "opencode base remove drops the bundle"; else ko "opencode base remove drops the bundle" "${leftover}"; fi

echo "== install.sh: opencode guard under --skills-home agents =="

home="$(new_home)"
install_must_succeed "${home}" install --target opencode --only base,settings --skills-home agents
merged="$(cat "${home}/.config/opencode/opencode.json")"
assert_contains "${merged}" "./ycc-sensitive-guard" "consolidated: opencode.json loads the guard"
if [[ ! -d "${home}/.config/opencode/shared" && -f "${home}/.config/opencode/ycc-sensitive-guard/index.js" ]]; then
    ok "consolidated: guard installed although shared/ is not"
else
    ko "consolidated: guard installed although shared/ is not" "$(ls "${home}/.config/opencode" 2>/dev/null | tr '\n' ' ')"
fi
install_must_succeed "${home}" remove --target opencode --only base --skills-home agents
if [[ -f "${home}/.config/opencode/ycc-sensitive-guard/index.js" ]]; then
    ok "base remove keeps the guard while opencode.json still loads it"
else
    ko "base remove keeps the guard while opencode.json still loads it"
fi
install_must_succeed "${home}" remove --target opencode --only settings --skills-home agents
assert_not_contains "$(cat "${home}/.config/opencode/opencode.json" 2>/dev/null || true)" "./ycc-sensitive-guard" "consolidated: settings remove takes back the guard entry"
if [[ ! -e "${home}/.config/opencode/ycc-sensitive-guard" ]]; then ok "consolidated: settings remove takes back the guard"; else ko "consolidated: settings remove takes back the guard"; fi


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
install_must_succeed "${home}" remove --target opencode --intent agents,commands
leftover="$(find "${home}/.config/opencode" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | tr '\n' ' ')"
if [[ "${leftover}" == "shared skills " ]]; then ok "opencode agents,commands remove keeps skills + shared"; else ko "opencode agents,commands remove keeps skills + shared" "${leftover}"; fi
install_must_succeed "${home}" remove --target opencode --intent skills
leftover="$(find "${home}/.config/opencode" -mindepth 1 | head -3)"
if [[ -z "${leftover}" ]]; then ok "opencode skills remove takes shared/ too"; else ko "opencode skills remove takes shared/ too" "${leftover}"; fi

# The slice helper directly (no generators): Codex skills land in
# ~/.codex/skills with plugin paths re-pointed there.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
