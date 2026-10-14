#!/usr/bin/env bash
# Run the practices ratchet and optional Claude plugin validation.
# PRACTICES_ROOT overrides the repository root for isolated fixture checks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${PRACTICES_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

for required in \
    "${SCRIPT_DIR}/validate_practices.py" \
    "${SCRIPT_DIR}/practices_parse.py" \
    "${SCRIPT_DIR}/practices_rules.py" \
    "${REPO_ROOT}/scripts/practices-baseline.json" \
    "${REPO_ROOT}/ycc"; do
    if [[ ! -e "${required}" ]]; then
        echo "validate-practices.sh: required input missing: ${required}" >&2
        exit 1
    fi
done

python3 "${SCRIPT_DIR}/validate_practices.py" --root "${REPO_ROOT}"

if command -v claude >/dev/null 2>&1; then
    echo "== claude plugin validate =="
    claude plugin validate "${REPO_ROOT}/ycc"
else
    echo "NOTICE: claude CLI not on PATH; skipping 'claude plugin validate'"
fi
