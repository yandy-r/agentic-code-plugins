#!/usr/bin/env python3
"""Shared library for the ycc init rules-file helpers.

Kept self-contained on purpose: the skill bundles copy this file verbatim into
every runtime (Codex, opencode, agents, Cursor), and migrate-rules.py /
render-template.py load it from their own directory. Do not import anything
outside the standard library.

``detect_agents_import`` mirrors the parser in
ycc/skills/release-model/scripts/pointer-targets.sh (PR #263): only a
STANDALONE ``@AGENTS.md`` line counts as a live import. Prose mentions,
HTML comments, inline code and fenced code blocks do not. CRLF line endings
and a UTF-8 BOM are tolerated. The two implementations must stay in sync;
scripts/test-release-hygiene.sh cross-checks them.
"""

from __future__ import annotations

import re
from pathlib import Path

IMPORT_RE = re.compile(r"^\s*@(?:\./)?AGENTS\.md\s*$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def read_text_relaxed(path: Path) -> tuple[str, bool]:
    """Read a rules file tolerating a UTF-8 BOM.

    Returns ``(text_without_bom, had_bom)``.
    """
    raw = path.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    return raw.decode("utf-8"), had_bom


def detect_agents_import(text: str) -> bool:
    """True when ``text`` contains a live standalone ``@AGENTS.md`` import.

    Semantics (must match pointer-targets.sh):

    * HTML comments are stripped before scanning.
    * Lines inside fenced code blocks (``` or ~~~, matching open/close) never
      count.
    * Only a line consisting solely of ``@AGENTS.md`` (optionally ``@./AGENTS.md``,
      with surrounding whitespace) is an import.
    * ``\\r`` line endings are normalised first.
    """
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    text = COMMENT_RE.sub("", text)
    fence = ""
    for line in text.split("\n"):
        marker = FENCE_RE.match(line)
        if marker:
            if not fence:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        if IMPORT_RE.fullmatch(line):
            return True
    return False


def detect_eol(text: str) -> str:
    """Return the dominant line ending of ``text`` ('\n' or '\r\n')."""
    return "\r\n" if text.count("\r\n") >= text.count("\n") - text.count("\r\n") else "\n"


def split_sections(text: str) -> list[list[str]]:
    """Split ``text`` into sections at markdown H1/H2 headings outside fences.

    The preamble (everything before the first heading, normally the title and
    intro) is returned as the first section. A heading that appears mid-file
    starts its own section, so an H1 like ``# Claude Code setup`` cannot be
    swallowed by the preceding section.
    """
    lines = text.split("\n")
    sections: list[list[str]] = []
    current: list[str] = []
    fence = ""
    for line in lines:
        stripped_bare = line.replace("\r", "")
        marker = FENCE_RE.match(stripped_bare)
        if marker:
            if not fence:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = ""
            current.append(line)
            continue
        is_heading = not fence and re.match(r"^#{1,2} \S", stripped_bare) is not None
        if is_heading and current:
            sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    return sections


def heading_of(section: list[str]) -> str | None:
    """The ``#``/``##`` heading line of a section, or None for the preamble."""
    first = section[0].replace("\r", "") if section else ""
    if re.match(r"^#{1,2} \S", first):
        return first
    return None
