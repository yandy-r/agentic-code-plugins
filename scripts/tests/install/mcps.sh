#!/usr/bin/env bash
# install.sh tests — MCP server selection: --mcps for sync/install/remove on
# every MCP-capable target, list-mcps, and the --mcps completions.
#
# Runs alone (bash scripts/tests/install/mcps.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh list-mcps =="

home="$(new_home)"
install_must_succeed "${home}" list-mcps
out="${INSTALL_OUT}"
assert_contains "${out}" "github" "list-mcps lists shared servers"
assert_contains "${out}" "linear-personal" "list-mcps includes linear-personal"
# Parity: every MCP-capable target manages the same servers.
install_must_succeed "${home}" list-mcps
all_names="${INSTALL_OUT}"
for t in claude cursor codex opencode; do
    install_must_succeed "${home}" list-mcps --target "${t}"
    out="${INSTALL_OUT}"
    if [[ "${out}" == "${all_names}" ]]; then ok "${t} manages every MCP server"; else ko "${t} manages every MCP server" "${out}"; fi
done
install_must_succeed "${home}" list-mcps --target agents
out="${INSTALL_OUT}"
if [[ -z "${out}" ]]; then ok "list-mcps skips targets without an mcp step"; else ko "list-mcps skips targets without an mcp step"; fi
out="$(run_install "${home}" list-mcps --target bogus)"
assert_contains "${out}" "Unknown target: bogus" "list-mcps validates targets"

echo
echo "== install.sh --mcps: validation =="

home="$(new_home)"
out="$(run_install "${home}" sync --target claude --intent settings --mcps github)"
assert_contains "${out}" "--mcps needs the mcp step" "--mcps without the mcp intent rejected"

home="$(new_home)"
out="$(run_install "${home}" sync --target claude --intent mcp --mcps github,bogus)"
assert_contains "${out}" "unknown MCP server 'bogus'" "unknown --mcps name rejected"
if [[ ! -e "${home}/project/.mcp.json" ]]; then ok "rejected --mcps writes nothing"; else ko "rejected --mcps writes nothing"; fi

home="$(new_home)"
out="$(run_install "${home}" sync --target claude --intent mcp --mcps "github,,linear")"
assert_contains "${out}" "--mcps contains an empty value" "empty --mcps item rejected"

echo
echo "== install.sh --mcps: every MCP-capable target =="

home="$(new_home)"
install_must_succeed "${home}" sync --target all --intent mcp --mcps github,linear-personal
for f in .mcp.json .cursor/mcp.json opencode.json; do
    merged="$(cat "${home}/project/${f}" 2>/dev/null)"
    assert_contains "${merged}" '"github"' "--mcps writes github to ${f}"
    assert_contains "${merged}" '"linear-personal"' "--mcps writes linear-personal to ${f}"
    assert_not_contains "${merged}" '"stripe"' "--mcps skips unselected servers in ${f}"
done
merged="$(cat "${home}/project/.codex/config.toml")"
assert_contains "${merged}" "[mcp_servers.linear-personal]" "--mcps writes linear-personal to codex"
assert_contains "${merged}" 'command = "github-mcp-server"' "codex keeps its native github override"
assert_not_contains "${merged}" "bearer_token_env_var" "codex github has no PAT mapping"
assert_not_contains "${merged}" "[mcp_servers.stripe]" "codex skips unselected servers"

home="$(new_home)"
install_must_succeed "${home}" sync --target codex --intent mcp --mcps xero
assert_contains "$(cat "${home}/project/.codex/config.toml")" 'env_vars = ["XERO_CLIENT_ID", "XERO_CLIENT_SECRET"]' \
    "codex passes env references through as env_vars"

home="$(new_home)"
install_must_succeed "${home}" install --target claude --only mcp --global --mcps github
assert_not_contains "$(cat "${home}/.claude.json")" '"playwright"' "install --only mcp honors --mcps"

echo
echo "== install.sh --mcps: partial sync and remove =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent mcp
install_must_succeed "${home}" sync --target claude --intent mcp --mcps github
assert_contains "$(cat "${home}/project/.mcp.json")" '"stripe"' "partial sync keeps other managed servers"
install_must_succeed "${home}" remove --target claude --intent mcp --mcps stripe
merged="$(cat "${home}/project/.mcp.json")"
assert_not_contains "${merged}" '"stripe"' "remove --mcps drops the selected server"
assert_contains "${merged}" '"github"' "remove --mcps keeps the others"

echo
echo "== --mcps completion =="

for f in _ycc ycc.bash ycc.fish; do
    assert_contains "$(cat "${REPO_ROOT}/scripts/completions/${f}")" "list-mcps" "${f} completes --mcps from list-mcps"
done
out="$(PATH="${REPO_ROOT}:${PATH}" bash -c 'source "$1"
    COMP_WORDS=(install.sh sync --target codex --intent mcp --mcps github,li); COMP_CWORD=7; _ycc; echo "${COMPREPLY[*]}"' \
    _ "${REPO_ROOT}/scripts/completions/ycc.bash")"
assert_contains "${out}" "github,linear-personal" "bash completes --mcps for the line's --target"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
