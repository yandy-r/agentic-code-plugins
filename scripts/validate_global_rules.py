#!/usr/bin/env python3
"""Check shipped global rules budgets and known substitution artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RULES_LINE_CAP = 120
RUNTIME_RE = re.compile(r"\b(?:claude(?: code)?|cursor|codex|opencode)\b", re.IGNORECASE)
RUNTIME_LIST_RE = re.compile(
    r"\b(?:claude(?: code)?|cursor|codex|opencode)\b"
    r"(?:\s*,\s*(?:and\s+)?\b(?:claude(?: code)?|cursor|codex|opencode)\b)+",
    re.IGNORECASE,
)


def rules_errors(text: str) -> list[str]:
    """Return violations in a source or generated global rules file."""
    errors: list[str] = []
    if not text.strip():
        errors.append("rules file is empty")
    if len(text.splitlines()) > RULES_LINE_CAP:
        errors.append(f"rules file exceeds {RULES_LINE_CAP} lines")
    if re.search(r"`AGENTS\.md`\s*/\s*`AGENTS\.md`", text):
        errors.append("duplicated AGENTS.md filename pair")
    if re.search(r"\bgraphify\b", text, re.IGNORECASE):
        errors.append("personal graphify rules must not be shipped")
    for group in RUNTIME_LIST_RE.findall(text):
        names = [name.lower().removesuffix(" code") for name in RUNTIME_RE.findall(group)]
        if len(names) != len(set(names)):
            errors.append("repeated runtime name in one list")
            break
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        if not path.is_file():
            print(f"{path}: required rules file missing", file=sys.stderr)
            failed = True
            continue
        for error in rules_errors(path.read_text(encoding="utf-8")):
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
