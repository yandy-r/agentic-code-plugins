#!/usr/bin/env bash
# Validate generated OMP native packages: byte/mode drift of every generated file, then the
# catalog, manifest, lockstep-version and closure policy for the checkout and for an export
# whose catalog includes unlisted included packages. No omp binary is needed.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -ne 0 ]]; then echo "Usage: $0" >&2; exit 1; fi
command -v python3 >/dev/null 2>&1 || { echo "validate-omp-packages.sh: python3 is required" >&2; exit 1; }

echo "== Sync check (generator --check) =="
python3 "${REPO_ROOT}/scripts/generate_omp_packages.py" --check

echo "== Native policy (checkout) =="
python3 "${REPO_ROOT}/scripts/validate_omp_native.py"

echo "== Native policy (export, unlisted packages included) =="
export_root="$(mktemp -d)"
trap 'rm -rf "${export_root}"' EXIT
python3 "${REPO_ROOT}/scripts/generate_omp_packages.py" --export "${export_root}" >/dev/null
python3 "${REPO_ROOT}/scripts/generate_omp_packages.py" --export "${export_root}" --check
python3 "${REPO_ROOT}/scripts/validate_omp_native.py" --export "${export_root}"

echo "OK: OMP native packages are in sync and pass catalog, manifest and closure policy."
