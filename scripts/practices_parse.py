"""Strict parsing helpers for the authoring-practices validator."""

from __future__ import annotations

import re
from typing import Any

import yaml

BASELINE_VERSION = 1
RULES = tuple(f"S{i}" for i in range(1, 10)) + ("A1", "A2", "R1")
NUMERIC_RULES = frozenset({"S1", "S2", "S7", "R1"})
TOOL_ENTRY_RE = re.compile(r"[^()\s]+(\([^()]*\))?")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
S7_ITEM = "missing '## Contents' immediately after optional frontmatter/title and blank lines"


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys at any nesting level."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue  # `<<` merges are flattened by the base class, as yaml.safe_load does
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in seen
            except TypeError:  # unhashable key; let the base class raise its own error
                break
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_unique_yaml(raw: str) -> Any:
    """yaml.safe_load equivalent that raises yaml.YAMLError on duplicate keys."""
    return yaml.load(raw, Loader=UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass


def parse_tools(value: Any) -> list[str]:
    """Parse list/scalar tools, preserving separators inside balanced parentheses."""
    if value is None:
        return []
    if isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries, token, depth = [], "", 0
        for ch in value:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError(f"malformed tools value (unbalanced ')'): {value!r}")
            if (ch == "," or ch.isspace()) and depth == 0:
                if token:
                    entries.append(token)
                token = ""
            else:
                token += ch
        if depth:
            raise ValueError(f"malformed tools value (unbalanced '('): {value!r}")
        if token:
            entries.append(token)
    else:
        raise ValueError(f"tools value must be list or string, got {type(value).__name__}")
    for entry in entries:
        if not isinstance(entry, str):
            raise ValueError(f"non-string tool entry: {entry!r}")
        if not TOOL_ENTRY_RE.fullmatch(entry):
            raise ValueError(f"malformed tool entry: {entry!r}")
        depth = 0
        for ch in entry:
            depth += (ch == "(") - (ch == ")")
            if depth < 0:
                raise ValueError(f"malformed tool entry (unbalanced ')'): {entry!r}")
        if depth:
            raise ValueError(f"malformed tool entry (unbalanced '('): {entry!r}")
    return entries


def has_early_contents(lines: list[str]) -> bool:
    """Require H2 Contents after optional frontmatter/H1, with only blank separators."""
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            return False
        start = end + 1
    seen_title = False
    for line in lines[start:]:
        if not line.strip():
            continue
        m = HEADING_RE.fullmatch(line)
        if not m:
            return False
        level, title = len(m.group(1)), m.group(2).strip().lower()
        if level == 1 and not seen_title:
            seen_title = True
            continue
        return level == 2 and title in ("contents", "table of contents")
    return False


def validate_baseline_shape(data: Any) -> list[dict[str, Any]]:
    """Validate baseline entries, including unique IDs and required numeric ceilings."""
    if not isinstance(data, dict):
        raise ValueError("baseline root must be a JSON object")
    if type(data.get("version")) is not int or data["version"] != BASELINE_VERSION:
        raise ValueError(f"baseline 'version' must be {BASELINE_VERSION}")
    entries = data.get("violations")
    if not isinstance(entries, list):
        raise ValueError("baseline 'violations' must be a list")
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError(f"baseline violation #{i} must be an object with a string 'id'")
        vid = entry["id"]
        parts = vid.split(":", 2)
        if len(parts) != 3 or parts[0] not in RULES or not all(parts):
            raise ValueError(f"baseline violation #{i} has invalid id: {vid!r}")
        if vid in seen:
            raise ValueError(f"duplicate baseline id: {vid}")
        seen.add(vid)
        if parts[0] in NUMERIC_RULES:
            if type(entry.get("size")) is not int or entry["size"] < 0:
                raise ValueError(f"baseline {vid} requires integer 'size' >= 0")
        elif "size" in entry:
            raise ValueError(f"baseline {vid} must not carry 'size' on a non-numeric rule")
    return entries
