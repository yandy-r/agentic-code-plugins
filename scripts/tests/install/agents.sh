#!/usr/bin/env bash
# install.sh tests — agents: ~/.agents/skills install/remove, foreign entries
# survive, plugins/ untouched, duplicate hint, --skills-home choice.
#
# Runs alone (bash scripts/tests/install/agents.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh install: agents =="

home="$(new_home)"
run_install "${home}" install --target agents >/dev/null
assert_not_contains "$(cat "${home}/.agents/skills/releaser/SKILL.md")" 'disable-model-invocation' "agents install omits unsupported releaser invocation policy"
assert_not_contains "$(cat "${home}/.agents/skills/init/SKILL.md")" 'disable-model-invocation' "agents install keeps init unrestricted"
assert_contains "$(cat "${home}/.agents/skills/releaser/SKILL.md")" 'Prepares external-project releases' "agents install keeps releaser description"
skill_count="$(find "${home}/.agents/skills" -mindepth 1 -maxdepth 1 -type d | wc -l)"
bundle_count="$(find "${REPO_ROOT}/.agents-plugin/skills" -mindepth 1 -maxdepth 1 -type d | wc -l)"
if [[ -f "${home}/.agents/skills/backport/SKILL.md" && "${skill_count}" -eq "${bundle_count}" ]]; then
    ok "agents install puts ycc skills into ~/.agents/skills"
else
    ko "agents install puts ycc skills into ~/.agents/skills" "${skill_count} skills, expected ${bundle_count}"
fi
if [[ -d "${home}/.agents/ycc-shared/references" && -d "${home}/.agents/ycc-shared/scripts" ]]; then
    ok "agents install puts shared helpers into ~/.agents/ycc-shared"
else
    ko "agents install puts shared helpers into ~/.agents/ycc-shared"
fi

echo
echo "== install.sh remove: agents keeps foreign entries =="

mkdir -p "${home}/.agents/skills/my-own"
printf 'mine\n' > "${home}/.agents/skills/my-own/SKILL.md"
mkdir -p "${home}/.agents/plugins/ycc"
printf 'foreign\n' > "${home}/.agents/plugins/ycc/plugin.json"
run_install "${home}" remove --target agents --only skills >/dev/null
if [[ ! -d "${home}/.agents/skills/backport" ]]; then ok "agents remove drops ycc skills"; else ko "agents remove drops ycc skills" "$(ls "${home}/.agents/skills")"; fi
if [[ ! -d "${home}/.agents/ycc-shared" ]]; then ok "agents remove drops ycc-shared"; else ko "agents remove drops ycc-shared"; fi
if [[ -f "${home}/.agents/skills/my-own/SKILL.md" ]]; then ok "agents remove keeps foreign skill my-own"; else ko "agents remove keeps foreign skill my-own"; fi
if [[ -f "${home}/.agents/plugins/ycc/plugin.json" ]]; then ok "agents remove leaves ~/.agents/plugins untouched"; else ko "agents remove leaves ~/.agents/plugins untouched"; fi

echo
echo "== install.sh install: agents duplicate hint =="

home="$(new_home)"
mkdir -p "${home}/.config/opencode/skills/backport"
out="$(run_install "${home}" install --target agents 2>&1)"
assert_contains "${out}" "may list them twice" "agents install warns when opencode native skills already hold ycc entries"

echo
echo "== install.sh: --skills-home agents consolidates shared skills =="

home="$(new_home)"
run_install "${home}" install --target codex,opencode --only base --skills-home agents >/dev/null
if [[ -f "${home}/.agents/skills/backport/SKILL.md" ]]; then ok "consolidated: skills land in ~/.agents/skills"; else ko "consolidated: skills land in ~/.agents/skills"; fi
if [[ ! -d "${home}/.config/opencode/skills" ]]; then ok "consolidated: no skills under ~/.config/opencode"; else ko "consolidated: no skills under ~/.config/opencode"; fi
if [[ ! -d "${home}/.config/opencode/shared" ]]; then ok "consolidated: no shared/ under ~/.config/opencode"; else ko "consolidated: no shared/ under ~/.config/opencode"; fi
if [[ -d "${home}/.config/opencode/agents" && -d "${home}/.config/opencode/commands" ]]; then
    ok "consolidated: opencode keeps its agents + commands"
else
    ko "consolidated: opencode keeps its agents + commands" "$(ls "${home}/.config/opencode" 2>/dev/null)"
fi
if [[ -n "$(find "${home}/.codex/agents" -mindepth 1 -print -quit 2>/dev/null)" ]]; then ok "consolidated: codex agents land in ~/.codex/agents"; else ko "consolidated: codex agents land in ~/.codex/agents"; fi
stub_log="$(cat "${home}/claude-calls.log" 2>/dev/null || true)"
assert_not_contains "${stub_log}" "plugin add" "consolidated: codex plugin is not registered"
if [[ ! -L "${home}/.codex/plugins/ycc" && ! -e "${home}/.agents/plugins/marketplace.json" ]]; then
    ok "consolidated: codex plugin link + marketplace entry skipped"
else
    ko "consolidated: codex plugin link + marketplace entry skipped"
fi

echo
echo "== install.sh: --skills-home native keeps per-tool skills =="

home="$(new_home)"
out="$(run_install "${home}" install --target codex,opencode --only base --skills-home native 2>&1)"
if [[ -d "${home}/.config/opencode/skills" ]]; then ok "native: opencode skills land in ~/.config/opencode/skills"; else ko "native: opencode skills land in ~/.config/opencode/skills"; fi
if [[ ! -e "${home}/.agents/skills" ]]; then ok "native: nothing under ~/.agents/skills"; else ko "native: nothing under ~/.agents/skills"; fi
assert_not_contains "${out}" "Recommended:" "native: no consolidation prompt text"

echo
echo "== install.sh: non-TTY overlap warning =="

home="$(new_home)"
out="$(run_install "${home}" install --target codex,opencode --only base 2>&1)"
assert_contains "${out}" "codex and opencode" "non-TTY overlap warning names the duplicate pair"
assert_contains "${out}" "pass --skills-home agents to consolidate" "non-TTY overlap warning suggests --skills-home agents"

echo
echo "== install.sh: cursor joins the overlap check =="

home="$(new_home)"
out="$(run_install "${home}" install --target cursor,opencode --only base 2>&1)"
assert_contains "${out}" "cursor and opencode" "non-TTY overlap warning names cursor"
home="$(new_home)"
run_install "${home}" install --target cursor,codex,opencode --only base --skills-home agents >/dev/null
if [[ -f "${home}/.agents/skills/backport/SKILL.md" && ! -d "${home}/.cursor/skills/backport" ]]; then
    ok "consolidated: cursor skills go to ~/.agents/skills only"
else
    ko "consolidated: cursor skills go to ~/.agents/skills only"
fi

echo
echo "== contract: every target declares ~/.agents/skills readership =="

(
    source_install_libs
    for t in "${ALL_TARGETS[@]}"; do
        declare -F "${t}_reads_agents_skills" >/dev/null || { echo "missing ${t}_reads_agents_skills"; continue; }
        if [[ "${t}" != agents ]] && "${t}_reads_agents_skills"; then
            declare -F "${t}_native_skills_dirs" >/dev/null || echo "missing ${t}_native_skills_dirs"
        fi
    done
) > "${SANDBOX_ROOT}/contract.out" 2>&1
contract="$(cat "${SANDBOX_ROOT}/contract.out")"
if [[ -z "${contract}" ]]; then ok "every target declares reads_agents_skills (+ native_skills_dirs)"; else ko "every target declares reads_agents_skills (+ native_skills_dirs)" "${contract}"; fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
