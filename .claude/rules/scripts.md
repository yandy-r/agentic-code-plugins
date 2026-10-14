---
paths:
  - 'scripts/**'
  - 'ycc/skills/**/scripts/**'
---

# Script authoring

- Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail`, guards checking required
  inputs exist, stdout for results and stderr for errors, exit 0 on success and 1
  on error. Keep executable bits set and use `kebab-case.sh` names.
- Python: PEP 8, type hints on public API signatures; prefer `ruff` for linting and
  `mypy --strict` for type checking.
- Keep shared helper implementations under `ycc/skills/_shared/scripts/` rather
  than copying them between skills. Source paths and runtime plugin-root usage
  are documented in root `CLAUDE.md`.
- Add regression coverage for changed script behavior. Use the repository's
  existing `scripts/test_*` / `scripts/test-*` suites, not nonexistent npm tests.
