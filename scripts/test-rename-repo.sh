#!/usr/bin/env bash
# Tests for scripts/rename-repo.sh: executes the disposable-fixture suite in
# scripts/test_rename_repo.py (the real checkout is never modified).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/test_rename_repo.py" "$@"
