#!/usr/bin/env bash
# Unified validate entrypoint — run every validator that guards the ycc
# source-of-truth directory and its generated Cursor/Codex/opencode bundles.
#
# Usage:
#   ./scripts/validate.sh                       # all targets
#   ./scripts/validate.sh --only inventory      # single target
#   ./scripts/validate.sh --only cursor,codex   # comma-separated subset
#
# Targets: inventory, cursor, codex, opencode, agents, json, config, release, mods, practices
#   - inventory  validates ycc skill frontmatter and the shared inventory
#   - json       validates .claude-plugin/marketplace.json plus ycc/.claude-plugin/plugin.json
#   - config     tests the managed-config merge helper and install.sh sync CLI
#   - release    runs every scripts/test-release-*.sh (release-model state scripts,
#                RELEASING.md template, signal collector), stopping at the first failure
#   - mods       validates the Claude Code mods under ycc/mods and their marketplace
#   - practices  ratchets skill/agent/rule authoring practices against
#                scripts/practices-baseline.json (unit tests + validator + optional
#                `claude plugin validate`)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VALID_TARGETS=(inventory cursor codex opencode agents json config release mods practices)
TARGETS=("${VALID_TARGETS[@]}")

usage() {
    cat <<EOF
Usage: $(basename "$0") [--only <targets>]

Run every validator for the ycc source-of-truth directory and its generated
Cursor / Codex / opencode bundles and managed configuration sync.

Options:
  --only <targets>   Comma-separated subset (valid: ${VALID_TARGETS[*]})
  -h, --help         Show this help

Examples:
  $(basename "$0")
  $(basename "$0") --only inventory
  $(basename "$0") --only cursor,codex
  $(basename "$0") --only json
  $(basename "$0") --only practices
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --only)
            [[ $# -lt 2 ]] && { echo "validate.sh: --only requires an argument" >&2; exit 1; }
            IFS=',' read -r -a TARGETS <<<"$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "validate.sh: unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

for target in "${TARGETS[@]}"; do
    valid=0
    for v in "${VALID_TARGETS[@]}"; do
        [[ "$target" == "$v" ]] && valid=1 && break
    done
    if [[ "$valid" -eq 0 ]]; then
        echo "validate.sh: unknown target '$target' (valid: ${VALID_TARGETS[*]})" >&2
        exit 1
    fi
done

fail() {
    echo "validate.sh: FAILED at '$1'" >&2
    exit 1
}

run_target() {
    case "$1" in
        inventory)
            echo "== validate: inventory =="
            "${REPO_ROOT}/scripts/validate-inventory.sh" || fail "validate-inventory.sh"
            echo "== validate: ycc skill frontmatter =="
            "${REPO_ROOT}/scripts/validate-ycc-skills.sh" || fail "validate-ycc-skills.sh"
            echo "== validate: formatter bundle smoke =="
            "${REPO_ROOT}/scripts/validate-formatters-bundle.sh" || fail "validate-formatters-bundle.sh"
            echo "== validate: style.sh Node CLI resolution =="
            "${REPO_ROOT}/scripts/validate-style-node-tools.sh" || fail "validate-style-node-tools.sh"
            ;;
        cursor)
            echo "== validate: cursor agents =="
            "${REPO_ROOT}/scripts/validate-cursor-agents.sh" || fail "validate-cursor-agents.sh"
            echo "== validate: cursor skills =="
            "${REPO_ROOT}/scripts/validate-cursor-skills.sh" || fail "validate-cursor-skills.sh"
            echo "== validate: cursor rules =="
            "${REPO_ROOT}/scripts/validate-cursor-rules.sh" || fail "validate-cursor-rules.sh"
            ;;
        codex)
            echo "== validate: codex skills =="
            "${REPO_ROOT}/scripts/validate-codex-skills.sh" || fail "validate-codex-skills.sh"
            echo "== validate: codex agents =="
            "${REPO_ROOT}/scripts/validate-codex-agents.sh" || fail "validate-codex-agents.sh"
            echo "== validate: codex plugin =="
            "${REPO_ROOT}/scripts/validate-codex-plugin.sh" || fail "validate-codex-plugin.sh"
            ;;
        opencode)
            echo "== validate: opencode skills =="
            "${REPO_ROOT}/scripts/validate-opencode-skills.sh" || fail "validate-opencode-skills.sh"
            echo "== validate: opencode agents =="
            "${REPO_ROOT}/scripts/validate-opencode-agents.sh" || fail "validate-opencode-agents.sh"
            echo "== validate: opencode commands =="
            "${REPO_ROOT}/scripts/validate-opencode-commands.sh" || fail "validate-opencode-commands.sh"
            echo "== validate: opencode plugin =="
            "${REPO_ROOT}/scripts/validate-opencode-plugin.sh" || fail "validate-opencode-plugin.sh"
            echo "== validate: opencode install coverage =="
            "${REPO_ROOT}/scripts/validate-opencode-install-coverage.sh" || fail "validate-opencode-install-coverage.sh"
            echo "== validate: opencode V2 config rules =="
            (cd "${REPO_ROOT}/scripts" && python3 test_validate_opencode_config.py) \
                || fail "test_validate_opencode_config.py"
            echo "== validate: opencode V2 agent permission generation =="
            (cd "${REPO_ROOT}/scripts" && python3 test_generate_opencode_agents.py) \
                || fail "test_generate_opencode_agents.py"
            ;;
        agents)
            echo "== validate: agents skills =="
            "${REPO_ROOT}/scripts/validate-agents-skills.sh" || fail "validate-agents-skills.sh"
            echo "== validate: agents install coverage =="
            "${REPO_ROOT}/scripts/validate-agents-install-coverage.sh" || fail "validate-agents-install-coverage.sh"
            ;;
        config)
            echo "== validate: model/effort declarations =="
            python3 "${REPO_ROOT}/scripts/validate-model-settings.py" || fail "validate-model-settings.py"
            echo "== validate: managed-config merge helper =="
            python3 "${REPO_ROOT}/scripts/test_merge_managed_config.py" || fail "test_merge_managed_config.py"
            python3 "${REPO_ROOT}/scripts/test_managed_config_entries.py" || fail "test_managed_config_entries.py"
            python3 "${REPO_ROOT}/scripts/test_generate_codex_mcp.py" || fail "test_generate_codex_mcp.py"
            echo "== validate: codex marketplace helper =="
            python3 "${REPO_ROOT}/scripts/test_codex_marketplace.py" || fail "test_codex_marketplace.py"
            echo "== validate: install sync CLI =="
            "${REPO_ROOT}/scripts/test-install-sync.sh" || fail "test-install-sync.sh"
            ;;
        release)
            local release_test
            for release_test in "${REPO_ROOT}"/scripts/test-release-*.sh; do
                [[ -e "${release_test}" ]] || fail "no scripts/test-release-*.sh found"
                echo "== validate: $(basename "${release_test}") =="
                "${release_test}" || fail "$(basename "${release_test}")"
            done
            ;;
        mods)
            echo "== validate: claude mods =="
            "${REPO_ROOT}/scripts/validate-mods.sh" || fail "validate-mods.sh"
            ;;
        practices)
            echo "== validate: practices unit tests =="
            python3 "${REPO_ROOT}/scripts/test_validate_practices.py" || fail "test_validate_practices.py"
            echo "== validate: practices ratchet =="
            "${REPO_ROOT}/scripts/validate-practices.sh" || fail "validate-practices.sh"
            ;;
        json)
            echo "== validate: marketplace and plugin manifests =="
            python3 -m json.tool "${REPO_ROOT}/.claude-plugin/marketplace.json" > /dev/null \
                || fail ".claude-plugin/marketplace.json"
            python3 -m json.tool "${REPO_ROOT}/ycc/.claude-plugin/plugin.json" > /dev/null \
                || fail "ycc/.claude-plugin/plugin.json"
            echo "OK: manifest JSON is valid."
            echo "== validate: hooks symlink =="
            "${REPO_ROOT}/scripts/validate-hooks.sh" || fail "validate-hooks.sh"
            ;;
    esac
}

for target in "${TARGETS[@]}"; do
    run_target "${target}"
done

echo "validate.sh: done (${TARGETS[*]})"
