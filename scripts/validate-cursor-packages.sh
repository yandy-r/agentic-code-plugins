#!/usr/bin/env bash
# Validate generated Cursor-native packages against the vendored official schema.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -ne 0 ]]; then echo "Usage: $0" >&2; exit 1; fi
command -v python3 >/dev/null 2>&1 || { echo "validate-cursor-packages.sh: python3 is required" >&2; exit 1; }

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_cursor_packages.py" --check || { echo "Native packages are out of date" >&2; exit 1; }

echo "== Native policy =="
python3 "${REPO_ROOT}/scripts/validate_cursor_native.py" || exit 1

echo "OK: Cursor native packages are in sync and pass schema + policy."
