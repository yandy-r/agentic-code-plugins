#!/usr/bin/env bash
# Validate the generated hidden Claude packages under packages/claude/.
#
# The generator --check is the critical policy gate: it rebuilds the expected
# tree from the package model and canonical sources and reports missing,
# changed, extra and executable-bit drift without mutating the checkout.
# When the claude CLI is on PATH, also run 'claude plugin validate' for every
# generated package; without it, print an explicit NOTICE and skip only that
# optional check.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_ROOT="${REPO_ROOT}/packages/claude"

if [[ $# -ne 0 ]]; then
    echo "Usage: $0" >&2
    exit 2
fi

command -v python3 >/dev/null 2>&1 || { echo "validate-claude-packages.sh: python3 is required" >&2; exit 1; }

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_claude_packages.py" --check

# Generated roots are the included/native Claude packages other than the
# canonical ycc package, which stays at ycc/ and is never duplicated here.
mapfile -t PACKAGE_KEYS < <(python3 - "${SCRIPT_DIR}" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from package_model import load_package_model

model = load_package_model()
for package in model.packages:
    for runtime in package.runtimes:
        if (
            runtime.runtime == "claude"
            and runtime.status == "included"
            and runtime.mechanism == "native"
            and package.key != "ycc"
        ):
            print(package.key)
PY
)

if [[ ${#PACKAGE_KEYS[@]} -eq 0 ]]; then
    echo "validate-claude-packages.sh: no generated Claude packages in the package model" >&2
    exit 1
fi

for key in "${PACKAGE_KEYS[@]}"; do
    if [[ ! -f "${OUTPUT_ROOT}/${key}/.claude-plugin/plugin.json" ]]; then
        echo "validate-claude-packages.sh: missing generated package: packages/claude/${key}" >&2
        exit 1
    fi
done

if command -v claude >/dev/null 2>&1; then
    echo "== claude plugin validate =="
    for key in "${PACKAGE_KEYS[@]}"; do
        echo "claude plugin validate packages/claude/${key}"
        claude plugin validate "${OUTPUT_ROOT}/${key}" >/dev/null || {
            echo "validate-claude-packages.sh: 'claude plugin validate' failed for packages/claude/${key}" >&2
            exit 1
        }
    done
else
    echo "NOTICE: claude CLI not on PATH; skipping 'claude plugin validate' for generated Claude packages"
fi

echo "OK: Claude packages are in sync and valid."
