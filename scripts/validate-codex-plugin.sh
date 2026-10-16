#!/usr/bin/env bash
# Check legacy/dormant metadata or an explicit, read-only native export.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GENERATOR_ARGS=(--check)
POLICY_ARGS=()
case "$#" in
    0) ;;
    2)
        if [[ "$1" != "--native-output" || -z "$2" ]]; then
            echo "Usage: $0 [--native-output DIR]" >&2
            exit 2
        fi
        GENERATOR_ARGS+=(--native-output "$2")
        POLICY_ARGS+=(--native-output "$2")
        ;;
    *)
        echo "Usage: $0 [--native-output DIR]" >&2
        exit 2
        ;;
esac

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_codex_plugin.py" "${GENERATOR_ARGS[@]}"

echo "== JSON, component ownership, version and local-files MCP policies =="
python3 "${REPO_ROOT}/scripts/validate_codex_native.py" "${POLICY_ARGS[@]}"

echo "== Local-files skill policy =="
LOCAL_PLAN_DOCS=(
    "${REPO_ROOT}/ycc/skills/visual-plan/SKILL.md"
    "${REPO_ROOT}/ycc/skills/visual-recap/SKILL.md"
    "${REPO_ROOT}/ycc/skills/_shared/references/agent-native-setup.md"
    "${REPO_ROOT}"/ycc/skills/visual-plan/references/*.md
    "${REPO_ROOT}"/ycc/skills/visual-recap/references/*.md
)
if grep -En 'Bash\(plan:\*\)|(^|`)plan (blocks|local (check|serve|verify|preview))' "${LOCAL_PLAN_DOCS[@]}"; then
    echo "Local-files visual planning must use the pinned Agent-Native npx command." >&2
    exit 1
fi
if grep -En 'Connected:.*get-plan-blocks|call `get-plan-blocks`' \
    "${REPO_ROOT}/ycc/skills/visual-recap/SKILL.md"; then
    echo "Local-only visual recap must not depend on the Plan MCP connector." >&2
    exit 1
fi

echo "OK: Codex plugin metadata is in sync and satisfies package policies."
