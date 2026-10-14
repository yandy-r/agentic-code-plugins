#!/usr/bin/env bash
# migrate-rules.sh --repo DIR [--dry-run|--yes] [--allow-non-git]
# Bash 3.2-compatible entrypoint; Python 3.11+ engine handles rules safely.
# Show --dry-run first; --yes applies after showing the complete diff/report.
# Only git repositories by default. --allow-non-git creates timestamped backups.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'migrate-rules: python3 required' >&2; exit 1; }
export PYTHONDONTWRITEBYTECODE=1
exec python3 "${SCRIPT_DIR}/migrate-rules.py" "$@"
