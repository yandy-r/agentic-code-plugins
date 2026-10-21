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
assert_contains "$(cat "$(omp_state "${home}")" 2>/dev/null)" '"scope": "project"' "omp --project records the project install"

install_must_succeed "${home}" remove --target omp --only base --project
log="$(omp_log "${home}")"
assert_contains "${log}" "omp plugin uninstall --scope project ycc@ycc" "omp remove --project uninstalls the project install"
assert_contains "${log}" "omp plugin marketplace remove ycc" "omp remove --project drops the ycc marketplace"
assert_not_contains "$(cat "${home}/project/.omp/plugins/installed_plugins.json" 2>/dev/null)" "ycc@ycc" "omp remove --project empties the project registry"
assert_contains "${log}" "omp plugin uninstall --scope project ycc-mcp@ycc" "omp remove --project uninstalls the project ycc-mcp install"
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
    ko "omp --package ycc-hooks rejected as deferred"
else
    assert_contains "${out}" "package 'ycc-hooks' is deferred or opt-in for target 'omp'" "omp --package ycc-hooks rejected as deferred"
fi
assert_not_contains "$(omp_log "${home}")" "omp plugin install" "deferred package installs nothing"

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

home="$(new_home)"
install_must_succeed "${home}" sync --target omp --intent settings
assert_contains "${INSTALL_OUT}" "intent 'settings' is not supported by target 'omp'" "omp settings intent warns not supported"
assert_contains "${INSTALL_OUT}" "omp target ran no steps" "omp settings intent runs no steps"
assert_not_contains "$(omp_log "${home}")" "omp plugin" "omp settings intent makes no omp plugin call"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
