#!/usr/bin/env bash
# Validate canonical ycc and the generated hidden Claude packages.
#
# The generator --check is the critical policy gate: it rebuilds the expected
# tree from the package model and canonical sources and reports missing,
# changed, extra and executable-bit drift without mutating the checkout.
# When the claude CLI is on PATH, also run 'claude plugin validate' for every
# native package; without it, print an explicit NOTICE and skip only that
# optional check.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -ne 0 ]]; then
    echo "Usage: $0" >&2
    exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "validate-claude-packages.sh: python3 is required" >&2; exit 1; }

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_claude_packages.py" --check

echo "== Native policy =="
python3 "${REPO_ROOT}/scripts/validate_claude_native.py"

# Included/native Claude roots include canonical ycc/, which is never duplicated
# under packages/claude/ but must receive the same optional CLI validation.
mapfile -t PACKAGE_ROOTS < <(python3 - "${SCRIPT_DIR}" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
from package_model import load_package_model
from validate_packages import package_root

model = load_package_model()
for package in model.packages:
    for runtime in package.runtimes:
        if (
            runtime.runtime == "claude"
            and runtime.status == "included"
            and runtime.mechanism == "native"
        ):
            print(package_root(package.key, "claude"))
PY
)

if [[ ${#PACKAGE_ROOTS[@]} -eq 0 ]]; then
    echo "validate-claude-packages.sh: no native Claude packages in the package model" >&2
    exit 1
fi

for package_root in "${PACKAGE_ROOTS[@]}"; do
    if [[ ! -f "${REPO_ROOT}/${package_root}/.claude-plugin/plugin.json" ]]; then
        echo "validate-claude-packages.sh: missing native package: ${package_root}" >&2
        exit 1
    fi
done

if command -v claude >/dev/null 2>&1; then
    echo "== claude plugin validate =="
    for package_root in "${PACKAGE_ROOTS[@]}"; do
        echo "claude plugin validate ${package_root}"
        claude plugin validate "${REPO_ROOT}/${package_root}" >/dev/null || {
            echo "validate-claude-packages.sh: 'claude plugin validate' failed for ${package_root}" >&2
            exit 1
        }
    done
else
    echo "NOTICE: claude CLI not on PATH; skipping 'claude plugin validate' for native Claude packages"
fi

echo "OK: Claude packages are in sync and valid."
