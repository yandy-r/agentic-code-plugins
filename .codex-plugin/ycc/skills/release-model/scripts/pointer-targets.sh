#!/usr/bin/env bash
# Read-only selection of existing release-pointer files. Usage: pointer-targets.sh --repo DIR
# Prints repo-relative paths; exits 1 for invalid input or a dangling AGENTS.md import.
set -euo pipefail
if [[ "$#" -ne 2 || "$1" != "--repo" || ! -d "$2" ]]; then
  printf 'Usage: pointer-targets.sh --repo DIR\n' >&2
  exit 1
fi
python3 - "$2" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
claude = root / "AGENTS.md"
imports_agents = False
if claude.is_file():
    text = re.sub(r"<!--.*?-->", "", claude.read_text(encoding="utf-8"), flags=re.S)
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        line = re.sub(r"(`+).*?\1", "", line)
        if re.search(r"(?:^|\s)@(?:\./)?AGENTS\.md(?=$|\s|[,;])", line):
            imports_agents = True
            break

if imports_agents and not (root / "AGENTS.md").is_file():
    print("pointer-targets: AGENTS.md imports missing AGENTS.md; repair the import first", file=sys.stderr)
    sys.exit(1)

for rel in ("AGENTS.md", "AGENTS.md", ".github/copilot-instructions.md"):
    if rel == "AGENTS.md" and imports_agents:
        continue
    if (root / rel).is_file():
        print(rel)
PY
