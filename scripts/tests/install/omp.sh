#!/usr/bin/env bash
# install.sh tests — omp: native install/re-run/remove through scripts/omp_install.py
# against the stateful fake omp (fake_omp.py), user and project scope, dry-run,
# package and mode gates, --target all skip, version preflight and intents.
#
# Runs alone (bash scripts/tests/install/omp.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# omp_state <home> — the helper's ownership state file.
omp_state() { printf '%s/.config/ycc/omp-native-install.json' "$1"; }
# omp_export <home> — the helper's local marketplace export.
omp_export() { printf '%s/.local/share/ycc/omp-marketplace' "$1"; }
# omp_log <home> — the shared stub call log (fake omp logs 'omp <args>').
omp_log() { cat "$1/claude-calls.log" 2>/dev/null || true; }
# omp_mutations <log text> — the mutating omp calls in a log excerpt.
omp_mutations() {
    grep -E '^omp plugin (marketplace (add|update|remove)|install|upgrade|uninstall|link)( |$)' <<< "$1" || true
}

echo "== install.sh install: omp user scope =="

home="$(new_home)"
install_must_succeed "${home}" install --target omp
out="${INSTALL_OUT}"
log="$(omp_log "${home}")"
assert_contains "${log}" "omp plugin install --scope user ycc@ycc" "omp install installs ycc@ycc at user scope"
assert_contains "${log}" "omp plugin marketplace add $(omp_export "${home}")" "omp install registers the local export marketplace"
assert_contains "${log}" "omp plugin install --scope user ycc-mcp@ycc" "omp install installs ycc-mcp@ycc at user scope"
assert_contains "${log}" "omp plugin install --scope user ycc-rules@ycc" "omp install installs ycc-rules@ycc at user scope by default"
assert_contains "${out}" "rules apply to new sessions (/new or restart)" "omp install says rules apply to new sessions"
assert_contains "$(cat "${home}/.fake-omp/plugins/installed_plugins.json" 2>/dev/null)" "ycc-rules@ycc" "fake omp registry holds ycc-rules@ycc"
if [[ -f "$(omp_export "${home}")/packages/omp/ycc-rules/.omp-plugin/plugin.json" ]]; then
    ok "omp export ships the ycc-rules package"
else
    ko "omp export ships the ycc-rules package"
fi
assert_contains "${out}" "MCP servers from ycc-mcp start only after a reload or restart" "omp install tells running sessions to reload for MCP"
assert_contains "${out}" " installed (user)" "omp install reports the installed package"
assert_contains "${out}" "OMP has no trust prompt" "omp install warns that OMP has no trust prompt"
assert_contains "${out}" "omp install complete." "omp install completes"
assert_contains "$(cat "$(omp_state "${home}")" 2>/dev/null)" '"package": "ycc"' "omp install records the ycc-owned install"
assert_contains "$(cat "${home}/.fake-omp/plugins/installed_plugins.json" 2>/dev/null)" "ycc@ycc" "fake omp registry holds ycc@ycc"
if [[ -f "$(omp_export "${home}")/packages/omp/ycc/.omp-plugin/plugin.json" ]]; then
    ok "omp install writes the local export"
else
    ko "omp install writes the local export" "$(find "$(omp_export "${home}")" -maxdepth 3 2>/dev/null | head -5)"
fi
if cmp -s "$(omp_export "${home}")/packages/omp/ycc-mcp/.mcp.json" "${REPO_ROOT}/mcp-configs/mcp.json"; then
    ok "omp export ships ycc-mcp .mcp.json byte-identical to mcp-configs/mcp.json"
else
    ko "omp export ships ycc-mcp .mcp.json byte-identical to mcp-configs/mcp.json"
fi

before="$(omp_log "${home}")"
install_must_succeed "${home}" install --target omp
after="$(omp_log "${home}")"
rerun_log="${after#"${before}"}"
assert_contains "${INSTALL_OUT}" " up to date (user)" "omp re-run reports up to date"
added="$(omp_mutations "${rerun_log}")"
if [[ -z "${added}" ]]; then ok "omp re-run makes no mutating omp calls"; else ko "omp re-run makes no mutating omp calls" "${added}"; fi
assert_not_contains "${INSTALL_OUT}" "exported OMP packages" "omp re-run keeps the unchanged export"

install_must_succeed "${home}" remove --target omp --only base
out="${INSTALL_OUT}"
log="$(omp_log "${home}")"
assert_contains "${log}" "omp plugin uninstall --scope user ycc@ycc" "omp remove uninstalls the user install"
assert_contains "${log}" "omp plugin uninstall --scope user ycc-mcp@ycc" "omp remove uninstalls the user ycc-mcp install"
assert_contains "${log}" "omp plugin uninstall --scope user ycc-rules@ycc" "omp remove uninstalls the user ycc-rules install"
assert_contains "${log}" "omp plugin marketplace remove ycc" "omp remove drops the ycc marketplace"
assert_contains "${out}" "[ok] removed $(omp_export "${home}")" "omp remove reports the export removal"
assert_not_contains "$(cat "${home}/.fake-omp/plugins/installed_plugins.json" 2>/dev/null)" "ycc@ycc" "omp remove empties the fake registry"
assert_not_contains "$(cat "${home}/.fake-omp/marketplaces.json" 2>/dev/null)" '"ycc"' "omp remove empties the fake marketplace registry"
if [[ ! -e "$(omp_export "${home}")" ]]; then ok "omp remove deletes the export"; else ko "omp remove deletes the export"; fi
if [[ ! -e "$(omp_state "${home}")" ]]; then ok "omp remove deletes the state file"; else ko "omp remove deletes the state file"; fi

echo
echo "== install.sh install: omp project scope =="

home="$(new_home)"
git -C "${home}/project" init -q
install_must_succeed "${home}" install --target omp --project
log="$(omp_log "${home}")"
assert_contains "${log}" "omp plugin install --scope project ycc@ycc" "omp --project installs at project scope"
assert_not_contains "${log}" "omp plugin install --scope user" "omp --project leaves user scope alone"
assert_contains "${INSTALL_OUT}" "a project install shadows your user install here" "omp --project explains the shadowing"
assert_contains "${log}" "omp plugin install --scope project ycc-mcp@ycc" "omp --project installs ycc-mcp at project scope"
registry="$(cat "${home}/project/.omp/plugins/installed_plugins.json" 2>/dev/null)"
assert_contains "${registry}" "ycc@ycc" "omp --project writes ycc to the fake project registry"
assert_contains "${registry}" "ycc-mcp@ycc" "omp --project writes ycc-mcp to the fake project registry"
assert_contains "${registry}" "ycc-rules@ycc" "omp --project writes ycc-rules to the fake project registry"
assert_contains "$(cat "$(omp_state "${home}")" 2>/dev/null)" '"scope": "project"' "omp --project records the project install"

install_must_succeed "${home}" remove --target omp --only base --project
log="$(omp_log "${home}")"
assert_contains "${log}" "omp plugin uninstall --scope project ycc@ycc" "omp remove --project uninstalls the project install"
assert_contains "${log}" "omp plugin marketplace remove ycc" "omp remove --project drops the ycc marketplace"
assert_not_contains "$(cat "${home}/project/.omp/plugins/installed_plugins.json" 2>/dev/null)" "ycc@ycc" "omp remove --project empties the project registry"
assert_contains "${log}" "omp plugin uninstall --scope project ycc-mcp@ycc" "omp remove --project uninstalls the project ycc-mcp install"
assert_contains "${log}" "omp plugin uninstall --scope project ycc-rules@ycc" "omp remove --project uninstalls the project ycc-rules install"
if [[ ! -e "$(omp_export "${home}")" && ! -e "$(omp_state "${home}")" ]]; then
    ok "omp remove --project deletes the export and state"
else
    ko "omp remove --project deletes the export and state"
fi

home="$(new_home)"
if out="$(run_install "${home}" install --target cursor --only base --project)"; then
    ko "--project still rejects cursor base"
else
    assert_contains "${out}" "project scope currently supports: mcp; omp: base" "--project still rejects cursor base"
fi

echo
echo "== install.sh: --dry-run =="

home="$(new_home)"
install_must_succeed "${home}" install --target omp --dry-run
out="${INSTALL_OUT}"
assert_contains "${out}" "[dry-run] would export OMP packages" "omp dry-run previews the export"
assert_contains "${out}" "[dry-run] would run: omp plugin marketplace add" "omp dry-run previews the marketplace add"
assert_contains "${out}" "[dry-run] would run: omp plugin install --scope user ycc@ycc" "omp dry-run previews the install"
assert_contains "${out}" "dry-run: skipping the OMP package build" "omp dry-run skips the package build"
added="$(omp_mutations "$(omp_log "${home}")")"
if [[ -z "${added}" ]]; then ok "omp dry-run makes no mutating omp calls"; else ko "omp dry-run makes no mutating omp calls" "${added}"; fi
if [[ ! -e "$(omp_state "${home}")" && ! -e "$(omp_export "${home}")" && ! -e "${home}/.fake-omp/marketplaces.json" ]]; then
    ok "omp dry-run writes no state, export or marketplace registry"
else
    ko "omp dry-run writes no state, export or marketplace registry"
fi

for target in codex all; do
    home="$(new_home)"
    if out="$(run_install "${home}" install --target "${target}" --dry-run)"; then
        ko "--dry-run rejected for --target ${target}"
    else
        assert_contains "${out}" "--dry-run is only supported by the omp target" "--dry-run rejected for --target ${target}"
    fi
    assert_not_contains "$(omp_log "${home}")" "omp plugin" "--target ${target} --dry-run rejection runs no omp plugin call"
done

echo
echo "== install.sh: omp package, mode and --target all gates =="

home="$(new_home)"
install_must_succeed "${home}" install --target omp --package ycc
assert_contains "$(omp_log "${home}")" "omp plugin install --scope user ycc@ycc" "omp --package ycc installs ycc@ycc"

home="$(new_home)"
install_must_succeed "${home}" install --target omp --package ycc-mcp
log="$(omp_log "${home}")"
assert_contains "${log}" "omp plugin install --scope user ycc-mcp@ycc" "omp --package ycc-mcp installs ycc-mcp@ycc"
assert_not_contains "${log}" "omp plugin install --scope user ycc@ycc" "omp --package ycc-mcp leaves ycc alone"
install_must_succeed "${home}" remove --target omp --only base
assert_contains "$(omp_log "${home}")" "omp plugin uninstall --scope user ycc-mcp@ycc" "omp remove uninstalls the ycc-mcp-only install"

home="$(new_home)"
if out="$(run_install "${home}" install --target omp --package ycc-hooks)"; then
    ko "omp --package ycc-hooks rejected as excluded"
else
    assert_contains "${out}" "package 'ycc-hooks' is excluded or opt-in for target 'omp'" "omp --package ycc-hooks rejected as excluded"
fi
assert_not_contains "$(omp_log "${home}")" "omp plugin install" "excluded package installs nothing"

home="$(new_home)"
if out="$(run_install "${home}" install --target omp --mode repo)"; then
    ko "--mode repo --target omp rejected while unlisted"
else
    assert_contains "${out}" "--mode repo is not supported by the omp target" "--mode repo --target omp rejected while unlisted"
    assert_contains "${out}" "omp needs a listed OMP package (YAN-1180)" "--mode repo rejection names YAN-1180"
fi

home="$(new_home)"
install_must_succeed "${home}" sync --target all --intent mcp
assert_contains "${INSTALL_OUT}" "--target all: skipping omp (needs omp >= 18.12.2 on PATH and a listed OMP package)" "--target all prints the omp skip line"
assert_not_contains "${INSTALL_OUT}" "omp sync complete" "--target all skips omp while unlisted"
assert_not_contains "$(omp_log "${home}")" "omp plugin" "--target all makes no omp plugin call"

echo
echo "== install.sh: omp version preflight =="

home="$(new_home)"
if out="$(FAKE_OMP_VERSION=18.12.1 run_install "${home}" install --target claude,omp --only base)"; then
    ko "old omp fails --target claude,omp"
else
    assert_contains "${out}" "omp >= 18.12.2 is required for --target omp" "old omp fails --target claude,omp"
    assert_contains "${out}" "omp 18.12.1 is older than 18.12.2" "old omp preflight names the version"
fi
assert_not_contains "${out}" "Claude sync complete" "omp preflight fails before claude runs"
log="$(omp_log "${home}")"
assert_not_contains "${log}" "plugin marketplace add" "omp preflight runs before any claude plugin call"
assert_not_contains "${log}" "omp plugin" "omp preflight makes no omp plugin call"

echo
echo "== install.sh sync: omp intents =="

home="$(new_home)"
install_must_succeed "${home}" sync --target omp --intent plugins
assert_contains "$(omp_log "${home}")" "omp plugin install --scope user ycc@ycc" "omp plugins intent maps to base"

echo
echo "== install.sh: omp settings and rules (user scope) =="

# omp_agent <home> — the fake omp agent dir ('omp config path').
omp_agent() { printf '%s/.fake-omp/agent' "$1"; }
omp_rules_src="${REPO_ROOT}/ycc/settings/rules/AGENTS.md"

# Dry-run previews settings and rules without 'omp config path' (it writes).
home="$(new_home)"
PI_CODING_AGENT_DIR="${home}/pi-agent" install_must_succeed "${home}" install --target omp --only settings,rules --dry-run
assert_contains "${INSTALL_OUT}" "would set /tools/approvalMode" "omp settings dry-run previews the merge"
assert_contains "${INSTALL_OUT}" "[dry-run] would link ${home}/pi-agent/AGENTS.md" "omp rules dry-run previews the link in the assumed agent dir"
assert_contains "${INSTALL_OUT}" "assuming the default omp agent dir" "omp dry-run labels the assumed agent dir"
assert_not_contains "$(omp_log "${home}")" "omp config path" "omp settings/rules dry-run never runs omp config path"
if [[ ! -e "${home}/pi-agent" && ! -e "$(omp_agent "${home}")" && ! -e "${home}/.config/ycc/managed-config-state.json" ]]; then
    ok "omp settings/rules dry-run writes nothing"
else
    ko "omp settings/rules dry-run writes nothing"
fi

# I1: --settings merges the managed leaves without any omp plugin call.
home="$(new_home)"
install_must_succeed "${home}" sync --target omp --intent settings
config="$(cat "$(omp_agent "${home}")/config.yml" 2>/dev/null)"
assert_contains "${config}" "approvalMode: write" "omp --settings writes tools.approvalMode"
for role in default slow task; do
    assert_contains "${config}" "  ${role}: " "omp --settings writes modelRoles.${role}"
done
assert_contains "${INSTALL_OUT}" "applied 4 managed update(s)" "omp --settings reports the merged leaves"
assert_not_contains "$(omp_log "${home}")" "omp plugin" "omp --settings makes no omp plugin call"

# I2: a user edit to a managed leaf survives a re-run.
agent="$(omp_agent "${home}")"
python3 - "${agent}/config.yml" <<'PY'
import sys, yaml
path = sys.argv[1]
data = yaml.safe_load(open(path, encoding="utf-8"))
data["modelRoles"]["slow"] = "openai/gpt-5.6-sol:low"
open(path, "w", encoding="utf-8").write(yaml.safe_dump(data, sort_keys=False))
PY
install_must_succeed "${home}" install --target omp --only settings
assert_contains "${INSTALL_OUT}" "kept your local value at /modelRoles/slow" "omp --settings re-run reports the kept edit"
assert_contains "$(cat "${agent}/config.yml")" "slow: openai/gpt-5.6-sol:low" "omp --settings re-run keeps the user edit"

# I3: --rules links AGENTS.md; a real file is refused and left unchanged.
install_must_succeed "${home}" install --target omp --only rules
if [[ -L "${agent}/AGENTS.md" && "$(readlink "${agent}/AGENTS.md")" == "${omp_rules_src}" ]]; then
    ok "omp --rules links AGENTS.md into the agent dir"
else
    ko "omp --rules links AGENTS.md into the agent dir"
fi
home2="$(new_home)"
mkdir -p "$(omp_agent "${home2}")"
printf 'mine\n' > "$(omp_agent "${home2}")/AGENTS.md"
if out="$(run_install "${home2}" install --target omp --only rules)"; then
    ko "omp --rules refuses a real AGENTS.md" "${out}"
else
    assert_contains "${out}" "refusing to replace user-authored rules file" "omp --rules refuses a real AGENTS.md"
fi
if [[ ! -L "$(omp_agent "${home2}")/AGENTS.md" && "$(cat "$(omp_agent "${home2}")/AGENTS.md")" == "mine" ]]; then
    ok "omp --rules leaves the real AGENTS.md unchanged"
else
    ko "omp --rules leaves the real AGENTS.md unchanged"
fi

# I4: --project with settings or rules is rejected before any write.
for flag in --settings --rules; do
    home2="$(new_home)"
    git -C "${home2}/project" init -q
    if out="$(run_install "${home2}" install --target omp --project "${flag}")"; then
        ko "omp --project ${flag} is rejected" "${out}"
    else
        assert_contains "${out}" "--project is not supported by step '${flag#--}' for target 'omp'" "omp --project ${flag} is rejected"
    fi
    if [[ ! -e "${home2}/project/.omp" && ! -e "$(omp_agent "${home2}")" ]]; then
        ok "omp --project ${flag} writes nothing"
    else
        ko "omp --project ${flag} writes nothing"
    fi
done

# Without PyYAML, the omp preflight fails with an install hint before any write.
home2="$(new_home)"
mkdir -p "${home2}/no-yaml"
printf 'raise ImportError("No module named yaml")\n' > "${home2}/no-yaml/yaml.py"
if out="$(PYTHONPATH="${home2}/no-yaml" run_install "${home2}" install --target omp --settings)"; then
    ko "omp without PyYAML fails" "${out}"
else
    assert_contains "${out}" "python3 -m pip install --user pyyaml" "omp without PyYAML names the install command"
    assert_not_contains "${out}" "Traceback" "omp without PyYAML prints no traceback"
fi
if [[ ! -e "$(omp_agent "${home2}")/config.yml" && -z "$(omp_log "${home2}")" ]]; then
    ok "omp without PyYAML writes nothing and makes no omp call"
else
    ko "omp without PyYAML writes nothing and makes no omp call"
fi

# --package never implies the opt-in settings or rules steps.
home2="$(new_home)"
install_must_succeed "${home2}" install --target omp --package ycc
if [[ ! -e "$(omp_agent "${home2}")/config.yml" && ! -e "$(omp_agent "${home2}")/AGENTS.md" ]]; then
    ok "omp --package ycc runs no settings or rules step"
else
    ko "omp --package ycc runs no settings or rules step"
fi

# I5: remove drops the unchanged leaves and the owned link, keeping the edit.
install_must_succeed "${home}" remove --target omp --intent settings,rules
config="$(cat "${agent}/config.yml" 2>/dev/null)"
assert_contains "${config}" "slow: openai/gpt-5.6-sol:low" "omp remove keeps the user-edited leaf"
assert_not_contains "${config}" "approvalMode" "omp remove drops the unchanged approvalMode leaf"
assert_not_contains "${config}" "default:" "omp remove drops the unchanged modelRoles.default leaf"
if [[ ! -e "${agent}/AGENTS.md" && ! -L "${agent}/AGENTS.md" ]]; then ok "omp remove unlinks AGENTS.md"; else ko "omp remove unlinks AGENTS.md"; fi
assert_not_contains "$(omp_log "${home}")" "omp plugin" "omp settings/rules remove makes no omp plugin call"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
