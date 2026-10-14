#!/usr/bin/env bash
# render-template.sh — thin Bash 3.2-compatible wrapper around render-template.py.
# Renders a bundled init template to stdout from profile-project.sh output.
# Never writes files. See render-template.py for flags, blocks and exit codes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'render-template: python3 required' >&2; exit 1; }
export PYTHONDONTWRITEBYTECODE=1
exec python3 "${SCRIPT_DIR}/render-template.py" "$@"
