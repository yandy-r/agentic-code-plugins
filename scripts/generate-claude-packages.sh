#!/usr/bin/env bash
# Generate hidden Claude-native add-on packages.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/generate_claude_packages.py" "$@"
