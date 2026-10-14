#!/usr/bin/env bash
# install.sh tests — codex: config merge, remove, base remove + plugin CLI, slices.
#
# Runs alone (bash scripts/tests/install/codex.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh sync: codex config merge =="

home="$(new_home)"
cat > "${home}/.codex/config.toml" <<'TOML'
# local machine notes
model = "gpt-5.6-sol"

[projects."/home/me/secret-project"]
trust_level = "trusted"

[mcp_servers.internal]
url = "https://internal.example"
TOML
install_must_succeed "${home}" sync --target codex --intent settings,mcp --force
out="${INSTALL_OUT}"
merged="$(cat "${home}/.codex/config.toml")"
assert_contains "${merged}" "# local machine notes" "TOML comment preserved"
assert_contains "${merged}" '[projects."/home/me/secret-project"]' "trusted project preserved"
assert_contains "${merged}" "[mcp_servers.internal]" "local MCP server preserved"
assert_contains "${merged}" 'model = "gpt-6-astra"' "managed model applied"
assert_contains "${merged}" 'default_subagent_model = "gpt-5.6-sol"' "subagent model applied"

if python3 -c "import tomllib,sys,pathlib; tomllib.loads(pathlib.Path(sys.argv[1]).read_text())" "${home}/.codex/config.toml"; then
    ok "merged config.toml still parses"
else
    ko "merged config.toml still parses"
fi

echo

echo "== install.sh remove: codex settings and rules =="

home="$(new_home)"
cat > "${home}/.codex/config.toml" <<'TOML'
# local machine notes
[projects."/home/me/secret-project"]
trust_level = "trusted"
TOML
install_must_succeed "${home}" sync --target codex --intent settings,plugins,rules
install_must_succeed "${home}" remove --target codex --intent settings,plugins,rules
merged="$(cat "${home}/.codex/config.toml")"
assert_contains "${merged}" "# local machine notes" "codex settings remove keeps comments"
assert_contains "${merged}" '[projects."/home/me/secret-project"]' "codex settings remove keeps trusted projects"
assert_not_contains "${merged}" "model =" "codex settings remove drops managed model"
assert_not_contains "${merged}" "[plugins." "codex plugins remove drops managed plugin tables"
for f in .codex/rules/default.rules .codex/CLAUDE.md .codex/AGENTS.md; do
    if [[ ! -L "${home}/${f}" ]]; then ok "codex remove unlinks ${f}"; else ko "codex remove unlinks ${f}"; fi
done


echo "== install.sh install: codex base mirrors custom agents =="

home="$(new_home)"
mkdir -p "${home}/.codex/agents"
echo 'name = "mine"' > "${home}/.codex/agents/mine.toml"
install_must_succeed "${home}" install --target codex --only base --skills-home native
out="${INSTALL_OUT}"
if [[ -f "${home}/.codex/agents/mine.toml" ]]; then ok "codex native base install keeps user agents"; else ko "codex native base install keeps user agents"; fi
first_agent="$(find "${REPO_ROOT}/.codex-plugin/agents" -maxdepth 1 -name '*.toml' -printf '%f\n' | sort | head -n 1)"
if [[ -n "${first_agent}" && -f "${home}/.codex/agents/${first_agent}" ]]; then ok "codex native base install populates ~/.codex/agents"; else ko "codex native base install populates ~/.codex/agents" "${out}"; fi
if [[ "$(find "${home}/.codex/agents" -maxdepth 1 -name '*.toml' ! -name mine.toml 2>/dev/null | wc -l)" -eq "$(find "${REPO_ROOT}/.codex-plugin/agents" -maxdepth 1 -name '*.toml' | wc -l)" ]]; then ok "codex native base install mirrors every custom agent"; else ko "codex native base install mirrors every custom agent"; fi
assert_contains "${out}" "Sync custom agents" "codex native base install runs the agents sync step"
assert_contains "${out}" "(skills agents plugin)" "codex native base install runs the agents generator pass"
last_step="$(grep -oE '\[[0-9]+/[0-9]+\]' <<< "${out}" | tail -n 1)"
if [[ "${last_step}" == "[6/6]" ]]; then ok "codex native base install numbers its steps to the total"; else ko "codex native base install numbers its steps to the total" "last step: ${last_step}"; fi

install_must_succeed "${home}" remove --target codex --intent base
if [[ "$(find "${home}/.codex/agents" -mindepth 1 -maxdepth 1 -printf '%f\n')" == "mine.toml" ]]; then ok "codex base remove after install keeps only user agents"; else ko "codex base remove after install keeps only user agents"; fi
assert_not_contains "$(cat "${home}/.config/ycc/installed-units.json" 2>/dev/null)" ".codex/agents" "codex base remove forgets the tracked agents"

# Upgrade over an older untracked mirror (the pre-tracking rsync flow).
home="$(new_home)"
mkdir -p "${home}/.codex/agents"
cp -R "${REPO_ROOT}/.codex-plugin/agents/." "${home}/.codex/agents/"
install_must_succeed "${home}" install --target codex --only base --skills-home native
out="${INSTALL_OUT}"
assert_not_contains "${out}" "refusing to replace" "codex native base install adopts an older untracked mirror"

echo

echo "== install.sh remove: codex base =="

home="$(new_home)"
mkdir -p "${home}/.codex/plugins/cache/local-ycc-plugins/ycc/skills" "${home}/.agents/plugins" "${home}/.codex/agents"
ln -s "${REPO_REAL}/.codex-plugin/ycc" "${home}/.codex/plugins/ycc"
ln -s "${REPO_REAL}/.codex-plugin/ycc" "${home}/.agents/plugins/ycc"
cp -R "${REPO_ROOT}/.codex-plugin/agents/." "${home}/.codex/agents/"
echo 'name = "mine"' > "${home}/.codex/agents/mine.toml"
cat > "${home}/.agents/plugins/marketplace.json" <<'JSON'
{
  "name": "local-ycc-plugins",
  "interface": { "displayName": "Local YCC Plugins" },
  "plugins": [{ "name": "ycc", "source": { "source": "local", "path": "./plugins/ycc" } }, { "name": "other" }]
}
JSON
install_must_succeed "${home}" remove --target codex --intent base
assert_contains "$(cat "${home}/claude-calls.log" 2>/dev/null)" "codex plugin remove ycc@local-ycc-plugins" "codex base remove uninstalls through the codex CLI"
for f in .codex/plugins/ycc .agents/plugins/ycc .codex/plugins/cache/local-ycc-plugins; do
    if [[ ! -e "${home}/${f}" && ! -L "${home}/${f}" ]]; then ok "codex base remove cleans ${f}"; else ko "codex base remove cleans ${f}"; fi
done
if [[ "$(find "${home}/.codex/agents" -mindepth 1 -maxdepth 1 -printf '%f\n')" == "mine.toml" ]]; then ok "codex base remove keeps only user agents"; else ko "codex base remove keeps only user agents"; fi
merged="$(cat "${home}/.agents/plugins/marketplace.json")"
assert_contains "${merged}" '"other"' "codex base remove keeps other marketplace plugins"
assert_not_contains "${merged}" '"ycc"' "codex base remove drops the ycc marketplace entry"

home="$(new_home)"
mkdir -p "${home}/.agents/plugins"
cat > "${home}/.agents/plugins/marketplace.json" <<'JSON'
{ "name": "local-ycc-plugins", "interface": { "displayName": "Local YCC Plugins" }, "plugins": [{ "name": "ycc" }] }
JSON
install_must_succeed "${home}" remove --target codex --intent base
if [[ ! -e "${home}/.agents/plugins/marketplace.json" ]]; then ok "codex base remove deletes a marketplace left empty"; else ko "codex base remove deletes a marketplace left empty"; fi

home="$(new_home)"
mkdir -p "${home}/.codex/plugins"
ln -s /elsewhere "${home}/.codex/plugins/ycc"
install_must_succeed "${home}" remove --target codex --intent base
out="${INSTALL_OUT}"
if [[ -L "${home}/.codex/plugins/ycc" ]]; then ok "codex base remove keeps a foreign link"; else ko "codex base remove keeps a foreign link"; fi

# Codex plugin install through the CLI (lib level; the full base step runs
# the generators). The legacy flat cache must go so Codex's versioned
# snapshot is the only copy.
home="$(new_home)"
mkdir -p "${home}/.codex/plugins/cache/local-ycc-plugins/ycc/.codex-plugin" "${home}/.agents/plugins"
echo '{ "name": "local-ycc-plugins", "plugins": [] }' > "${home}/.agents/plugins/marketplace.json"
out="$(cd "${home}" && HOME="${home}" PATH="${STUB_BIN}:${PATH}" CLAUDE_STUB_LOG="${home}/claude-calls.log" bash -c '
    info() { echo "[ok] $1"; }; warn() { echo "[!!] $1"; }; err() { echo "[err] $1"; }
    SCRIPT_DIR="$1"; source "$1/scripts/lib/install/targets/codex.sh"; install_codex_plugin' _ "${REPO_ROOT}" 2>&1)"
assert_contains "$(cat "${home}/claude-calls.log" 2>/dev/null)" "codex plugin add ycc@local-ycc-plugins" "codex base installs ycc through the codex CLI"
if [[ ! -e "${home}/.codex/plugins/cache/local-ycc-plugins/ycc" ]]; then ok "codex base drops the legacy flat cache"; else ko "codex base drops the legacy flat cache" "${out}"; fi
assert_contains "$(cat "${REPO_ROOT}/scripts/lib/install/targets/codex.sh")" 'merge_codex_marketplace_json "local" "./.agents/plugins/ycc"' "codex marketplace path resolves from the marketplace root"

echo

echo "== install.sh: codex slices =="

home="$(new_home)"
HOME="${home}" YCC_MANAGED_CONFIG_STATE="${home}/.config/ycc/managed-config-state.json" \
    python3 "${REPO_ROOT}/scripts/install_slices.py" install --target codex --slice skills >/dev/null
if [[ -f "${home}/.codex/skills/git-workflow/SKILL.md" && -d "${home}/.codex/skills/_shared/scripts" ]]; then ok "codex skills slice installs into ~/.codex/skills"; else ko "codex skills slice installs into ~/.codex/skills"; fi
if [[ ! -e "${home}/.codex/plugins" ]]; then ok "codex skills slice links no plugin"; else ko "codex skills slice links no plugin"; fi
assert_contains "$(cat "${home}/.codex/skills/releaser/agents/openai.yaml")" 'allow_implicit_invocation: false' "codex slice copies nested releaser invocation policy"
if [[ ! -e "${home}/.codex/skills/init/agents/openai.yaml" ]]; then ok "codex slice keeps init model-invocable"; else ko "codex slice keeps init model-invocable"; fi
if ! grep -rq '[~]/.codex/plugins/ycc/s' "${home}/.codex/skills"; then ok "codex skills slice re-points plugin paths"; else ko "codex skills slice re-points plugin paths"; fi
if ! grep -rq '\.\./\.\./\.\./shared/' "${home}/.codex/skills"; then ok "codex skills slice re-points relative shared paths"; else ko "codex skills slice re-points relative shared paths"; fi

# Codex slices are standalone: removing them never touches the plugin.
home="$(new_home)"
mkdir -p "${home}/.agents/plugins" "${home}/.codex/agents" "${home}/.codex/plugins"
ln -s "${REPO_REAL}/.codex-plugin/ycc" "${home}/.codex/plugins/ycc"
cp -R "${REPO_ROOT}/.codex-plugin/agents/." "${home}/.codex/agents/"
echo 'name = "mine"' > "${home}/.codex/agents/mine.toml"
echo '{ "name": "local-ycc-plugins", "plugins": [{ "name": "ycc" }] }' > "${home}/.agents/plugins/marketplace.json"
install_must_succeed "${home}" remove --target codex --intent agents,skills
if [[ "$(find "${home}/.codex/agents" -mindepth 1 -printf '%f\n')" == "mine.toml" ]]; then ok "codex agents remove keeps only user agents"; else ko "codex agents remove keeps only user agents"; fi
if [[ -L "${home}/.codex/plugins/ycc" ]]; then ok "codex slice remove keeps the plugin link"; else ko "codex slice remove keeps the plugin link"; fi
assert_contains "$(cat "${home}/.agents/plugins/marketplace.json")" '"ycc"' "codex slice remove keeps the marketplace entry"

echo

echo "== install.sh rules: codex links only AGENTS.md, legacy CLAUDE.md link removable =="

home="$(new_home)"
install_must_succeed "${home}" install --target codex --only rules
if [[ -L "${home}/.codex/AGENTS.md" && "$(readlink "${home}/.codex/AGENTS.md")" == "${REPO_ROOT}/ycc/settings/rules/AGENTS.md" ]]; then ok "codex rules links AGENTS.md"; else ko "codex rules links AGENTS.md"; fi
if [[ -L "${home}/.codex/rules/default.rules" ]]; then ok "codex rules still links default.rules"; else ko "codex rules still links default.rules"; fi
if [[ ! -e "${home}/.codex/CLAUDE.md" && ! -L "${home}/.codex/CLAUDE.md" ]]; then ok "codex rules no longer links the unread CLAUDE.md"; else ko "codex rules no longer links the unread CLAUDE.md"; fi
assert_contains "$(readlink -f "${home}/.codex/AGENTS.md" | xargs wc -l | awk '{print ($1 <= 120) ? "within-budget" : "over-budget"}')" "within-budget" "codex AGENTS.md resolves to a within-budget body"

home="$(new_home)"
ln -s "${REPO_ROOT}/ycc/settings/rules/CLAUDE.md" "${home}/.codex/CLAUDE.md"
install_must_succeed "${home}" remove --target codex --intent rules
if [[ ! -e "${home}/.codex/CLAUDE.md" && ! -L "${home}/.codex/CLAUDE.md" ]]; then ok "codex remove unlinks the legacy CLAUDE.md link"; else ko "codex remove unlinks the legacy CLAUDE.md link"; fi

home="$(new_home)"
echo "# mine" > "${home}/.codex/AGENTS.md"
out="$(run_install "${home}" install --target codex --only rules)"
assert_contains "${out}" "refusing to replace user-authored rules file" "codex rules refuses a real AGENTS.md without --force"
assert_contains "$(cat "${home}/.codex/AGENTS.md")" "# mine" "codex rules keeps the real AGENTS.md"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
