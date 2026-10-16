#!/usr/bin/env bash
# preflight-enhanced-agents.sh
#
# Verifies that agent files required by `prp-plan --enhanced` are present
# in the running plugin bundle. Exits 0 if all required agents are present;
# exits 1 with a clear error if any required agent is missing.
#
# Usage:
#   preflight-enhanced-agents.sh [<plugin-root>]
#
# Args:
#   plugin-root — optional absolute path to the plugin root (the directory
#                 containing `agents/`, `skills/`, etc.). When omitted, the
#                 script derives the root from its own install location
#                 (3 directories up from this file).
#
# Exit codes:
#   0 - All required agents present (optional agents may or may not be present)
#   1 - One or more required agents are missing
#   2 - Plugin root could not be resolved or does not exist

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve plugin root
# ---------------------------------------------------------------------------

if [[ -n "${1:-}" ]]; then
  PLUGIN_ROOT="$1"
else
  # Script lives at <plugin-root>/skills/prp-plan/scripts/<this-file>.
  # Three directories up from this file is the plugin root.
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
fi

if [[ -z "${PLUGIN_ROOT}" || ! -d "${PLUGIN_ROOT}" ]]; then
  printf 'Error: plugin root must be an existing directory (got: %s)\n' \
    "${PLUGIN_ROOT}" >&2
  exit 2
fi

AGENTS_DIR="${PLUGIN_ROOT}/agents"

if [[ ! -d "${AGENTS_DIR}" ]]; then
  printf 'Error: expected agents directory not found at %s\n' "${AGENTS_DIR}" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Agent lists
# ---------------------------------------------------------------------------

# Required: script exits 1 if any of these are absent.
REQUIRED_AGENTS=(
  "prp-researcher"
)

# Optional: script prints a notice but continues if any of these are absent.
OPTIONAL_AGENTS=(
  "research-specialist"
)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

MISSING_REQUIRED=()

check_required_agent() {
  local name="$1"
  local path="${AGENTS_DIR}/${name}.md"
  if [[ ! -f "${path}" ]]; then
    printf 'Error: --enhanced mode requires agent '\''%s'\'' but %s was not found.\n' \
      "${name}" "${path}" >&2
    MISSING_REQUIRED+=("${name}")
  fi
}

check_optional_agent() {
  local name="$1"
  local path="${AGENTS_DIR}/${name}.md"
  if [[ ! -f "${path}" ]]; then
    printf 'Notice: optional enhanced-mode agent '\''%s'\'' not found at %s (will fall back to prp-researcher).\n' \
      "${name}" "${path}" >&2
  fi
}

# ---------------------------------------------------------------------------
# Run checks — collect all failures before exiting
# ---------------------------------------------------------------------------

for agent in "${REQUIRED_AGENTS[@]}"; do
  check_required_agent "${agent}"
done

for agent in "${OPTIONAL_AGENTS[@]}"; do
  check_optional_agent "${agent}"
done

# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

if [[ ${#MISSING_REQUIRED[@]} -gt 0 ]]; then
  exit 1
fi

printf 'preflight-enhanced-agents: OK (%d required, %d optional checked)\n' \
  "${#REQUIRED_AGENTS[@]}" "${#OPTIONAL_AGENTS[@]}"
exit 0
