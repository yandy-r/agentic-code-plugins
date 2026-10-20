#!/usr/bin/env bash
# Generate OMP skills from ycc/skills (see scripts/generate_omp_skills.py).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/generate_omp_skills.py" "$@"
