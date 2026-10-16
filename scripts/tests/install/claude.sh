#!/usr/bin/env bash
# install.sh tests — claude: settings merge, mods, local edits, remove, slices.
#
# Runs alone (bash scripts/tests/install/claude.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh sync: claude settings merge =="

home="$(new_home)"
cat > "${home}/.claude/settings.json" <<'JSON'
{
  "tui": "fullscreen",
  "editorMode": "vim",
  "env": { "MY_LOCAL_TOKEN": "keep-me" }
}
JSON
install_must_succeed "${home}" sync --target claude --intent settings
out="${INSTALL_OUT}"
merged="$(cat "${home}/.claude/settings.json")"
assert_contains "${merged}" '"editorMode": "vim"' "unmanaged local key preserved"
assert_contains "${merged}" '"MY_LOCAL_TOKEN": "keep-me"' "unmanaged env leaf preserved"
assert_contains "${merged}" '"claude-fable-5-1"' "managed model applied"
assert_contains "${merged}" '"CLAUDE_CODE_SUBAGENT_MODEL": "opus[1m]"' "subagent model applied"

# The marketplace entry the Claude CLI writes must survive a settings sync;
# this is the regression the old copy-based flow could not avoid.
home="$(new_home)"
cat > "${home}/.claude/settings.json" <<'JSON'
{
  "extraKnownMarketplaces": {
    "cli-written": { "source": { "source": "github", "repo": "someone/else" } }
  }
}
JSON
install_must_succeed "${home}" sync --target claude --intent settings,plugins
merged="$(cat "${home}/.claude/settings.json")"
assert_contains "${merged}" '"cli-written"' "CLI-written marketplace entry preserved"
assert_contains "${merged}" '"ycc"' "repo marketplace entry added"

echo
echo "== install.sh sync: claude mods =="

home="$(new_home)"
install_must_succeed_stubbed "${home}" sync --target claude --intent mods
out="${INSTALL_OUT}"
calls="$(cat "${home}/claude-calls.log" 2>/dev/null)"
assert_contains "${calls}" "plugin marketplace add $(realpath "${REPO_ROOT}/ycc/mods") --scope user" "mods registers the ycc-mods marketplace from the checkout"
assert_contains "${calls}" "plugin install status-bar@ycc-mods --scope user" "mods installs each listed mod"
assert_not_contains "${calls}" "ycc@ycc" "mods does not run base"
assert_not_contains "${out}" "merge settings" "mods does not merge settings"
assert_contains "${out}" "Claude sync complete" "mods sync completes"

home="$(new_home)"
cat > "${home}/.claude/settings.json" <<'JSON'
{ "env": { "CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/mods/status-bar" } }
JSON
install_must_succeed_stubbed "${home}" sync --target claude --intent mods
out="${INSTALL_OUT}"
assert_contains "${out}" "also loads a 'status-bar' folder" "sideloaded copy of a mod is flagged"

home="$(new_home)"
install_must_succeed_stubbed "${home}" sync --target codex,cursor,opencode --intent mods
out="${INSTALL_OUT}"
assert_contains "${out}" "intent 'mods' is not supported by target 'codex'" "codex mods is a no-op"
assert_contains "${out}" "intent 'mods' is not supported by target 'opencode'" "opencode mods is a no-op"
assert_not_contains "$(cat "${home}/claude-calls.log" 2>/dev/null)" "plugin" "non-claude targets never call the claude CLI"

home="$(new_home)"
install_must_succeed_stubbed "${home}" install --target claude --only mods
out="${INSTALL_OUT}"
assert_not_contains "${out}" "is not valid for target 'claude'" "--only mods is valid for claude"
assert_contains "$(cat "${home}/claude-calls.log" 2>/dev/null)" "status-bar@ycc-mods" "install --only mods installs the mods"

echo
echo "== install.sh sync: local edits are respected =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings
python3 - "${home}/.claude/settings.json" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text())
data["model"] = "my-own-model"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
install_must_succeed "${home}" sync --target claude --intent settings
out="${INSTALL_OUT}"
assert_contains "${out}" "kept your local value at /model" "local edit preserved with warning"
assert_contains "$(cat "${home}/.claude/settings.json")" '"my-own-model"' "local model value intact"

install_must_succeed "${home}" sync --target claude --intent settings --force
out="${INSTALL_OUT}"
assert_contains "$(cat "${home}/.claude/settings.json")" '"claude-fable-5-1"' "--force restores repo value"

echo
echo "== install.sh remove: settings, rules, hooks, plugins =="

home="$(new_home)"
cat > "${home}/.claude/settings.json" <<'JSON'
{ "editorMode": "vim", "env": { "MY_LOCAL_TOKEN": "keep-me" } }
JSON
install_must_succeed "${home}" sync --target claude --intent settings,rules,hooks,plugins
install_must_succeed "${home}" remove --target claude --intent settings,rules,hooks,plugins
out="${INSTALL_OUT}"
assert_contains "${out}" "Claude remove complete" "claude remove of every config intent completes"
merged="$(cat "${home}/.claude/settings.json")"
assert_contains "${merged}" '"editorMode": "vim"' "claude remove keeps unmanaged keys"
assert_contains "${merged}" '"MY_LOCAL_TOKEN": "keep-me"' "claude remove keeps unmanaged env leaf"
assert_not_contains "${merged}" '"claude-fable-5-1"' "claude remove drops managed model"
assert_not_contains "${merged}" '"pluginMarketplaces"' "claude remove takes back appended list items"
assert_not_contains "${merged}" '"hooks"' "claude remove drops managed hooks"
for f in CLAUDE.md AGENTS.md hooks statusline-command.sh; do
    if [[ ! -e "${home}/.claude/${f}" && ! -L "${home}/.claude/${f}" ]]; then ok "claude remove cleans ~/.claude/${f}"; else ko "claude remove cleans ~/.claude/${f}"; fi
done

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings,plugins
python3 - "${home}/.claude/settings.json" <<'PY2'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
data = json.loads(p.read_text())
data["model"] = "my-own-model"
p.write_text(json.dumps(data, indent=2) + "\n")
PY2
install_must_succeed "${home}" remove --target claude --intent settings
out="${INSTALL_OUT}"
assert_contains "${out}" "kept your local value at /model" "remove keeps an edited managed value"
assert_contains "$(cat "${home}/.claude/settings.json")" '"enabledPlugins"' "remove --intent settings leaves the plugins group"
install_must_succeed "${home}" remove --target claude --intent settings,plugins --force
if [[ ! -e "${home}/.claude/settings.json" ]]; then ok "remove --force takes edited values too"; else ko "remove --force takes edited values too" "$(cat "${home}/.claude/settings.json")"; fi

home="$(new_home)"
echo "# mine" > "${home}/.claude/CLAUDE.md"
echo "custom" > "${home}/.claude/statusline-command.sh"
install_must_succeed "${home}" remove --target claude --intent rules,settings --force
out="${INSTALL_OUT}"
assert_contains "$(cat "${home}/.claude/CLAUDE.md")" "# mine" "remove never deletes a real rules file"
assert_contains "${out}" "not installed by ycc" "remove reports foreign rules file"
if [[ ! -e "${home}/.claude/statusline-command.sh" ]]; then ok "remove --force takes an edited statusline"; else ko "remove --force takes an edited statusline"; fi

home="$(new_home)"
echo "custom" > "${home}/.claude/statusline-command.sh"
install_must_succeed "${home}" remove --target claude --intent settings
out="${INSTALL_OUT}"
assert_contains "${out}" "kept ${home}/.claude/statusline-command.sh" "remove keeps an edited statusline"

echo "== install.sh remove: base and mods =="


home="$(new_home)"
install_must_succeed_stubbed "${home}" remove --target claude --intent base,mods
out="${INSTALL_OUT}"
calls="$(cat "${home}/claude-calls.log" 2>/dev/null)"
assert_contains "${calls}" "plugin uninstall ycc@ycc --scope user" "claude base remove uninstalls ycc"
assert_contains "${calls}" "plugin marketplace remove ycc --scope user" "claude base remove drops the ycc marketplace"
assert_contains "${calls}" "plugin uninstall status-bar@ycc-mods --scope user" "claude mods remove uninstalls each mod"
assert_contains "${calls}" "plugin marketplace remove ycc-mods --scope user" "claude mods remove drops the ycc-mods marketplace"
assert_contains "${out}" "Claude remove complete" "claude base/mods remove completes"

# Base installs are simulated (copies + links shaped like the real step) so
# the test never runs the generators.
echo "== install.sh: skills / agents / commands slices =="

# Claude slices need no generation, so they run for real in the sandbox.
home="$(new_home)"
mkdir -p "${home}/.claude/skills/my-own-skill"
install_must_succeed "${home}" install --target claude --only skills,agents,commands
out="${INSTALL_OUT}"
assert_not_contains "${out}" "register repo checkout" "claude slices do not run base"
for d in skills/git-workflow skills/clean skills/_shared agents/codebase-advisor.md; do
    if [[ -e "${home}/.claude/${d}" ]]; then ok "claude slice installs ~/.claude/${d}"; else ko "claude slice installs ~/.claude/${d}"; fi
done
if [[ ! -e "${home}/.claude/commands" ]]; then ok "claude commands slice installs no wrapper files"; else ko "claude commands slice installs no wrapper files"; fi
assert_contains "$(grep -c 'install standalone' <<<"${out}")" "2" "claude skills+commands install skills once (plus agents)"
if [[ ! -e "${home}/.claude/plugins" ]]; then ok "claude slices register no plugin"; else ko "claude slices register no plugin"; fi
skill="$(cat "${home}/.claude/skills/git-workflow/SKILL.md")"
assert_not_contains "${skill}" 'CLAUDE_PLUGIN_ROOT}/skills' "claude slice rewrites plugin-root paths"
assert_contains "${skill}" "${home}/.claude/skills/" "claude slice points paths at ~/.claude/skills"
assert_not_contains "$(cat "${home}/.claude/skills/clean/SKILL.md")" '/ycc:clean' "claude slice strips the ycc: namespace"
assert_contains "$(cat "${home}/.claude/skills/releaser/SKILL.md")" 'disable-model-invocation: true' "claude slice retains releaser manual invocation policy"
assert_not_contains "$(cat "${home}/.claude/skills/init/SKILL.md")" 'disable-model-invocation' "claude slice keeps init model-invocable"
if [[ -d "${home}/.claude/skills/my-own-skill" ]]; then ok "claude slice leaves user skills alone"; else ko "claude slice leaves user skills alone"; fi
install_must_succeed "${home}" install --target claude --only skills
out="${INSTALL_OUT}"
assert_contains "${out}" "entries up to date" "claude slice rerun is idempotent"

home="$(new_home)"
mkdir -p "${home}/.claude/skills/git-workflow" && echo "# mine" > "${home}/.claude/skills/git-workflow/SKILL.md"
out="$(run_install "${home}" install --target claude --only skills)"
assert_contains "${out}" "refusing to replace ${home}/.claude/skills/git-workflow" "claude slice refuses a foreign entry"
assert_contains "$(cat "${home}/.claude/skills/git-workflow/SKILL.md")" "# mine" "claude slice keeps the foreign entry"
install_must_succeed "${home}" install --target claude --only skills --force
assert_not_contains "$(cat "${home}/.claude/skills/git-workflow/SKILL.md")" "# mine" "claude slice --force replaces it"

install_must_succeed "${home}" remove --target claude --intent skills
if [[ ! -e "${home}/.claude/skills" ]]; then ok "claude skills remove takes back every entry"; else ko "claude skills remove takes back every entry" "$(ls "${home}/.claude/skills")"; fi

home="$(new_home)"
install_must_succeed "${home}" sync --target codex --intent commands
out="${INSTALL_OUT}"
assert_contains "${out}" "intent 'commands' is not supported by target 'codex'" "codex skips commands intent"
assert_not_contains "${out}" "Generate" "unsupported commands intent generates nothing"

home="$(new_home)"
install_must_succeed "${home}" install --target claude,cursor --only skills,commands --skills-home native
if [[ -e "${home}/.claude/skills/clean" && -e "${home}/.cursor/commands/clean.md" ]]; then ok "install --only commands runs on both supported targets"; else ko "install --only commands runs on both supported targets" "${INSTALL_OUT}"; fi

# Legacy wrappers: only names recorded in installed-units.json are retired,
# and only after the skills install succeeded.
echo "== install.sh: legacy claude command wrappers =="

legacy_home() {
    local h
    h="$(new_home)"
    mkdir -p "${h}/.claude/commands" "${h}/.config/ycc"
    echo "wrapper" > "${h}/.claude/commands/clean.md"
    echo "mine" > "${h}/.claude/commands/my-own.md"
    echo "mine too" > "${h}/.claude/commands/plan.md"   # unrecorded, same name as a skill
    printf '{"version": 1, "units": {"%s/.claude/commands": ["clean.md", "../escape.md"]}}\n' "${h}" \
        > "${h}/.config/ycc/installed-units.json"
    echo "outside" > "${h}/.claude/escape.md"
    echo "${h}"
}

home="$(legacy_home)"
install_must_succeed "${home}" install --target claude --only commands
out="${INSTALL_OUT}"
assert_contains "${out}" "retired 1 legacy command wrapper" "commands install retires recorded wrappers"
if [[ ! -e "${home}/.claude/commands/clean.md" ]]; then ok "recorded wrapper removed"; else ko "recorded wrapper removed"; fi
assert_contains "$(cat "${home}/.claude/commands/my-own.md" "${home}/.claude/commands/plan.md")" "mine too" "unrecorded command files kept"
if [[ -e "${home}/.claude/escape.md" ]]; then ok "recorded path traversal ignored"; else ko "recorded path traversal ignored"; fi
if [[ -e "${home}/.claude/skills/clean/SKILL.md" ]]; then ok "skills installed by commands alias"; else ko "skills installed by commands alias"; fi
assert_not_contains "$(cat "${home}/.config/ycc/installed-units.json")" ".claude/commands" "state forgets retired wrapper dir"

home="$(legacy_home)"
mkdir -p "${home}/.claude/skills/clean" && echo "# mine" > "${home}/.claude/skills/clean/SKILL.md"
out="$(run_install "${home}" install --target claude --only skills)"
assert_contains "${out}" "refusing to replace" "skills conflict reported"
if [[ -e "${home}/.claude/commands/clean.md" ]]; then ok "no wrapper cleanup after failed skills install"; else ko "no wrapper cleanup after failed skills install"; fi

home="$(legacy_home)"
rm -f "${home}/.claude/commands/my-own.md" "${home}/.claude/commands/plan.md"
install_must_succeed "${home}" install --target claude --only skills
if [[ ! -e "${home}/.claude/commands" ]]; then ok "emptied legacy commands dir removed"; else ko "emptied legacy commands dir removed"; fi

home="$(legacy_home)"
install_must_succeed "${home}" remove --target claude --only commands
out="${INSTALL_OUT}"
if [[ ! -e "${home}/.claude/commands/clean.md" && -e "${home}/.claude/commands/my-own.md" ]]; then ok "commands remove retires only recorded wrappers"; else ko "commands remove retires only recorded wrappers" "${out}"; fi

home="$(legacy_home)"
install_must_succeed "${home}" install --target claude --only agents
out="${INSTALL_OUT}"
if [[ -e "${home}/.claude/commands/clean.md" ]]; then ok "agents-only install leaves wrappers"; else ko "agents-only install leaves wrappers" "${out}"; fi
assert_contains "$(cat "${home}/.config/ycc/installed-units.json")" ".claude/commands" "agents-only install keeps wrapper state"

# A recorded name that is now a directory is user data: never removed.
home="$(legacy_home)"
rm -f "${home}/.claude/commands/clean.md"
mkdir "${home}/.claude/commands/clean.md"
echo "precious" > "${home}/.claude/commands/clean.md/user.txt"
install_must_succeed "${home}" install --target claude --only commands
out="${INSTALL_OUT}"
assert_contains "$(cat "${home}/.claude/commands/clean.md/user.txt" 2>/dev/null)" "precious" "recorded name replaced by a directory is preserved"
assert_contains "${out}" "kept ${home}/.claude/commands/clean.md: not a ycc wrapper file" "directory replacement reported"

# A recorded wrapper that is a symlink: only the link goes, never its target.
home="$(legacy_home)"
rm -f "${home}/.claude/commands/clean.md"
echo "external" > "${home}/external.md"
ln -s "${home}/external.md" "${home}/.claude/commands/clean.md"
install_must_succeed "${home}" install --target claude --only commands
if [[ ! -L "${home}/.claude/commands/clean.md" ]]; then ok "recorded symlink wrapper unlinked"; else ko "recorded symlink wrapper unlinked"; fi
assert_contains "$(cat "${home}/external.md" 2>/dev/null)" "external" "symlink wrapper target untouched"

# A symlinked commands dir is never removed or replaced; foreign files inside stay.
home="$(legacy_home)"
mv "${home}/.claude/commands" "${home}/ext-commands"
ln -s "${home}/ext-commands" "${home}/.claude/commands"
install_must_succeed "${home}" install --target claude --only commands
if [[ -L "${home}/.claude/commands" && -d "${home}/ext-commands" ]]; then ok "symlinked commands dir kept"; else ko "symlinked commands dir kept"; fi
assert_contains "$(cat "${home}/ext-commands/my-own.md" 2>/dev/null)" "mine" "symlinked commands dir keeps user files"

home="$(legacy_home)"
rm -f "${home}/.claude/commands/my-own.md" "${home}/.claude/commands/plan.md"
mv "${home}/.claude/commands" "${home}/ext-commands"
ln -s "${home}/ext-commands" "${home}/.claude/commands"
install_must_succeed "${home}" install --target claude --only commands
out="${INSTALL_OUT}"
if [[ -L "${home}/.claude/commands" && -d "${home}/ext-commands" && ! -e "${home}/ext-commands/clean.md" ]]; then ok "emptied symlinked commands dir kept"; else ko "emptied symlinked commands dir kept" "${out}"; fi

# Failed unlink retention: deterministic mock-based unit test (chmod is unreliable as root).
if out="$(python3 "${REPO_ROOT}/scripts/test_install_slices_legacy.py" 2>&1)"; then ok "failed unlink keeps name recorded, others removed"; else ko "failed unlink keeps name recorded, others removed" "${out}"; fi

# A copy the 'base' step mirrored is identical to the bundle, so a slice
# remove takes it back even without a recorded install.

echo
echo "== install.sh rules: claude links only CLAUDE.md, legacy links removable =="

home="$(new_home)"
install_must_succeed "${home}" install --target claude --only rules
if [[ -L "${home}/.claude/CLAUDE.md" && "$(readlink "${home}/.claude/CLAUDE.md")" == "${REPO_ROOT}/ycc/settings/rules/CLAUDE.md" ]]; then ok "claude rules links CLAUDE.md"; else ko "claude rules links CLAUDE.md"; fi
if [[ ! -e "${home}/.claude/AGENTS.md" && ! -L "${home}/.claude/AGENTS.md" ]]; then ok "claude rules no longer links the unread AGENTS.md"; else ko "claude rules no longer links the unread AGENTS.md"; fi

# A legacy AGENTS.md link survives install and is removed by remove; a real file never is.
home="$(new_home)"
ln -s "${REPO_ROOT}/ycc/settings/rules/AGENTS.md" "${home}/.claude/AGENTS.md"
install_must_succeed "${home}" install --target claude --only rules
if [[ -L "${home}/.claude/AGENTS.md" ]]; then ok "claude install leaves a legacy AGENTS.md link alone"; else ko "claude install leaves a legacy AGENTS.md link alone"; fi
install_must_succeed "${home}" remove --target claude --intent rules
if [[ ! -e "${home}/.claude/AGENTS.md" && ! -L "${home}/.claude/AGENTS.md" ]]; then ok "claude remove unlinks the legacy AGENTS.md link"; else ko "claude remove unlinks the legacy AGENTS.md link"; fi

home="$(new_home)"
echo "# mine" > "${home}/.claude/AGENTS.md"
install_must_succeed "${home}" remove --target claude --intent rules --force
assert_contains "$(cat "${home}/.claude/AGENTS.md" 2>/dev/null)" "# mine" "claude remove keeps a real AGENTS.md even with --force"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
