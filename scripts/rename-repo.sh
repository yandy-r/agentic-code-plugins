#!/usr/bin/env bash
# Rewrite owner/repo references in allowlisted source files after a GitHub repo rename.
# Usage: rename-repo.sh --from owner/repo --to owner/repo [--dry-run]
# Edits file contents only: no GitHub host rename, no git remote changes, no sync/regeneration.
# See --help for the file allowlist and matching rules.
set -euo pipefail
SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "${SCRIPT_DIR}/rename_repo.py" "$@"
