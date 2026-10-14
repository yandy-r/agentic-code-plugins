#!/usr/bin/env bash
# Ensure opencode plugin metadata (opencode.json + AGENTS.md) matches generator
# output and parses as JSON / valid Markdown.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUNDLE_ROOT="${REPO_ROOT}/.opencode-plugin"

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_opencode_plugin.py" --check

echo "== JSON lint =="
python3 -m json.tool "${BUNDLE_ROOT}/opencode.json" >/dev/null

echo "== OpenCode V2 config assertions =="
python3 "${REPO_ROOT}/scripts/validate_opencode_config.py" "${BUNDLE_ROOT}/opencode.json"

echo "== Bundle plugin assertions =="
python3 - <<'PY' "${BUNDLE_ROOT}/opencode.json"
import json
import sys
from pathlib import Path

# Bundle-specific requirements, separate from generic V2 config validity.
REQUIRED_PLUGIN = "@prevalentware/opencode-goal-plugin"

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
plugins = data.get("plugins", [])
names = {entry if isinstance(entry, str) else entry.get("package") for entry in plugins}

if REQUIRED_PLUGIN not in names:
    print(f"  plugins must include {REQUIRED_PLUGIN!r}", file=sys.stderr)
    sys.exit(1)
PY

echo "== AGENTS.md existence =="
if [[ ! -f "${BUNDLE_ROOT}/AGENTS.md" ]]; then
  echo "MISSING ${BUNDLE_ROOT}/AGENTS.md" >&2
  exit 1
fi

echo "== Global rules budgets and artifact assertions =="
python3 "${REPO_ROOT}/scripts/validate_global_rules.py" \
  "${REPO_ROOT}/ycc/settings/rules/CLAUDE.md" "${BUNDLE_ROOT}/AGENTS.md"
python3 "${REPO_ROOT}/scripts/test_generate_opencode_plugin.py"

echo "OK: opencode plugin metadata is in sync and valid."
