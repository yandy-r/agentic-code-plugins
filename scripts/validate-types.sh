#!/usr/bin/env bash
# Type-check the covered scripts with `mypy --strict`, using the [tool.mypy]
# config in pyproject.toml (its `files` list is the covered module set).
#
# mypy comes from `python3 -m mypy` when it and every stub match the pins in
# scripts/requirements-mypy.txt (CI installs that file), else from
# `uvx --with-requirements scripts/requirements-mypy.txt`. Without either it
# fails with an install hint; it never skips.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQUIREMENTS="scripts/requirements-mypy.txt"

cd "${REPO_ROOT}"

pin="$(sed -n 's/^mypy==\([^[:space:]]*\).*/\1/p' "${REQUIREMENTS}")"
if [[ -z "${pin}" ]]; then
    echo "validate-types.sh: no mypy== pin in ${REQUIREMENTS}" >&2
    exit 1
fi

# The local runner is used only when every pin (mypy and its stub packages) is
# installed at exactly the pinned version.
installed="$(python3 -m mypy --version 2>/dev/null | awk '{print $2}' || true)"
if [[ "${installed}" == "${pin}" ]] && python3 - "${REQUIREMENTS}" <<'PY'
import sys
from importlib.metadata import PackageNotFoundError, version

for line in open(sys.argv[1], encoding="utf-8"):
    req = line.split("#", 1)[0].strip()
    if not req:
        continue
    name, _, pinned = req.partition("==")
    try:
        if version(name.strip()) != pinned.strip():
            sys.exit(1)
    except PackageNotFoundError:
        sys.exit(1)
PY
then
    echo "validate-types.sh: python3 -m mypy ${installed}"
    exec python3 -m mypy
fi

if command -v uvx >/dev/null 2>&1; then
    echo "validate-types.sh: uvx mypy ${pin} (python3 -m mypy is ${installed:-not installed})"
    exec uvx --from "mypy==${pin}" --with-requirements "${REQUIREMENTS}" mypy
fi

echo "validate-types.sh: mypy ${pin} not found (python3 -m mypy is ${installed:-not installed}) and uvx is unavailable" >&2
echo "validate-types.sh: install it with: python3 -m pip install -r ${REQUIREMENTS}" >&2
exit 1
