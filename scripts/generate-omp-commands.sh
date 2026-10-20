#!/usr/bin/env bash
# Generate OMP command entrypoints from public ycc/skills (see scripts/generate_omp_commands.py).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/generate_omp_commands.py" "$@"
