#!/usr/bin/env bash
# Cloud Agent repository bootstrap for the ycc ystack repo.
# Idempotent: safe to re-run against cached or partially prepared state.
#
# Mirrors the verification loop documented in CLAUDE.md / AGENTS.md:
#   - npm dev deps + git hooks (commitlint, lefthook)  -> `prepare`
#   - Python deps for generators/validators + linters  -> pyyaml, ruff, black, mypy
#   - pinned shellcheck (0.10.0) into repo-local tools/ -> shell linting
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "== install: node dev dependencies + git hooks =="
npm ci

echo "== install: Python tooling (pyyaml, ruff, black, mypy) =="
# pyyaml is imported by scripts/generate_*.py and the validators; ruff/black/mypy
# back `npm run lint` and the repo's Python style rules. Install for the user so
# the packages are importable by the same python3 the scripts invoke.
if ! python3 -m pip install --user --upgrade pyyaml ruff black mypy 2>/dev/null; then
  # Newer Debian/Ubuntu images mark the system interpreter externally managed.
  python3 -m pip install --user --upgrade --break-system-packages pyyaml ruff black mypy
fi

# Ensure user-installed console scripts (ruff, black, mypy) are on PATH for
# interactive and non-login shells started by the agent.
LOCAL_BIN="${HOME}/.local/bin"
if ! grep -qs 'HOME/.local/bin' "${HOME}/.bashrc" 2>/dev/null; then
  printf '\n# Added by ycc .cursor/install.sh\nexport PATH="$HOME/.local/bin:$PATH"\n' >>"${HOME}/.bashrc"
fi
export PATH="${LOCAL_BIN}:${PATH}"

echo "== install: pinned shellcheck =="
./scripts/install-shellcheck.sh

echo "== install: done =="
