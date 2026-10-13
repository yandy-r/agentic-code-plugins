#!/usr/bin/env bash
# Ensure Codex plugin metadata matches generator output and parses as JSON.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_codex_plugin.py" --check

echo "== JSON lint =="
python3 -m json.tool "${REPO_ROOT}/.codex-plugin/ycc/.codex-plugin/plugin.json" >/dev/null
python3 -m json.tool "${REPO_ROOT}/.codex-plugin/ycc/.mcp.json" >/dev/null
python3 -m json.tool "${REPO_ROOT}/.agents/plugins/marketplace.json" >/dev/null

echo "== Local-files MCP policy =="
python3 - "${REPO_ROOT}/.codex-plugin/ycc/.mcp.json" <<'PY'
import json
import sys
from pathlib import Path

mcp_path = Path(sys.argv[1])
servers = json.loads(mcp_path.read_text(encoding="utf-8")).get("mcpServers", {})
forbidden_names = ("plan", "agent-native-plans")
registered_name = next((name for name in forbidden_names if name in servers), None)
error = (
    f"{mcp_path}: local-files visual planning must not register "
    f"the {registered_name!r} startup MCP server"
)
raise SystemExit(error if registered_name else 0)
PY

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

echo "OK: Codex plugin metadata is in sync and valid JSON."
