#!/usr/bin/env python3
"""
Merge repo-managed configuration keys into a user's runtime config file.

The installer historically COPIED whole config files into ``~/.claude``,
``~/.codex``, ``~/.config/opencode`` and friends, which forced a choice between
clobbering per-machine edits (``--force``) and refusing to install at all. This
helper replaces that with an additive merge: only the keys this repo declares as
*managed* are written, and every other key in the destination is preserved
byte-for-byte where the format allows.

Ownership tracking
------------------
Each managed leaf records the SHA-256 of the value this tool last applied, in
``~/.config/ycc/managed-config-state.json``. On a later run:

* destination leaf missing            → write the repo value
* destination matches last-applied    → repo value wins (user never touched it)
* destination differs from last-applied → user edit wins, warn, skip
* no recorded state and values differ → user value wins, warn, skip

``--force`` makes the repo value win in every case. State stores hashes only,
never values, so tokens in a user's config never leak into the state file.

Formats
-------
JSON destinations are parsed, merged and re-serialized. TOML destinations are
patched textually (validated with ``tomllib`` before and after) so comments,
ordering, quoting and unmanaged tables survive — Python ships no TOML writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from managed_config_entries import available_entries, select_source_entries, selected_state
from managed_config_legacy import plan_legacy_migration

REPO_ROOT = Path(__file__).resolve().parent.parent

STATE_PATH = Path(
    os.environ.get("YCC_MANAGED_CONFIG_STATE")
    or (Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "ycc" / "managed-config-state.json")
)

# Merge policies:
#   scalar       — one managed leaf (``model``, ``effortLevel``, ...)
#   object       — every leaf of the source object is managed individually;
#                  unknown sibling leaves in the destination are preserved
#   map-entries  — named scalar entries; unknown entries are preserved
#   deep         — recursively manage leaves inside named entries (MCP servers,
#                  providers, plugin tables) while preserving unknown siblings
#   list-union   — append missing source values, preserve destination order.
#                  Items this tool appended are recorded (by hash) so --remove
#                  can take back exactly those; ``keep_empty`` keeps the key as
#                  ``[]`` after removal for tools that require it.
PROFILES: dict[str, dict[str, Any]] = {
    "claude-settings": {
        "format": "json",
        "groups": {
            "settings": [
                {"path": ["env"], "policy": "object"},
                {"path": ["attribution"], "policy": "object"},
                {"path": ["permissions"], "policy": "object"},
                {"path": ["statusLine"], "policy": "object"},
                {"path": ["model"], "policy": "scalar"},
                {"path": ["modelSettings"], "policy": "object"},
                {"path": ["alwaysThinkingEnabled"], "policy": "scalar"},
                {"path": ["effortLevel"], "policy": "scalar"},
                {"path": ["skipDangerousModePermissionPrompt"], "policy": "scalar"},
                {"path": ["skipAutoPermissionPrompt"], "policy": "scalar"},
            ],
            "hooks": [
                {"path": ["hooks"], "policy": "map-entries"},
            ],
            "plugins": [
                {"path": ["enabledPlugins"], "policy": "map-entries"},
                {"path": ["extraKnownMarketplaces"], "policy": "map-entries"},
                {"path": ["pluginMarketplaces"], "policy": "list-union"},
            ],
        },
    },
    "claude-mcp": {
        "format": "json",
        "groups": {
            "mcp": [
                {"path": ["mcpServers"], "policy": "deep"},
            ],
        },
    },
    # Cursor's mcp.json uses the same mcpServers shape as Claude Code.
    "cursor-mcp": {
        "format": "json",
        "groups": {
            "mcp": [
                {"path": ["mcpServers"], "policy": "deep"},
            ],
        },
    },
    "cursor-cli": {
        "format": "json",
        "groups": {
            "settings": [
                {"path": ["version"], "policy": "scalar"},
                {"path": ["model"], "policy": "object"},
                {"path": ["hasChangedDefaultModel"], "policy": "scalar"},
                {"path": ["editor"], "policy": "object"},
                # Cursor treats permissions.allow/deny as required; seed them
                # without managing their contents (list-union never removes).
                {"path": ["permissions", "allow"], "policy": "list-union", "keep_empty": True},
                {"path": ["permissions", "deny"], "policy": "list-union", "keep_empty": True},
            ],
        },
    },
    "codex-config": {
        "format": "toml",
        "groups": {
            # [projects.*] and [apps.*] are deliberately unmanaged: they hold
            # machine-local trust decisions and account-specific connector IDs.
            "settings": [
                {"path": ["personality"], "policy": "scalar"},
                {"path": ["model"], "policy": "scalar"},
                {"path": ["model_reasoning_effort"], "policy": "scalar"},
                {"path": ["model_context_window"], "policy": "scalar"},
                {"path": ["model_auto_compact_token_limit"], "policy": "scalar"},
                {"path": ["plan_mode_reasoning_effort"], "policy": "scalar"},
                {"path": ["approval_policy"], "policy": "scalar"},
                {"path": ["approvals_reviewer"], "policy": "scalar"},
                {"path": ["sandbox_mode"], "policy": "scalar"},
                {"path": ["sandbox_workspace_write"], "policy": "object"},
                {"path": ["service_tier"], "policy": "scalar"},
                {"path": ["agents"], "policy": "object"},
                {"path": ["features"], "policy": "object"},
            ],
            "mcp": [
                {"path": ["mcp_servers"], "policy": "deep"},
            ],
            "plugins": [
                {"path": ["plugins"], "policy": "deep"},
            ],
        },
    },
    "opencode-config": {
        "format": "json",
        # opencode parses its config as JSONC (comments, trailing commas).
        "jsonc": True,
        "groups": {
            "settings": [
                {"path": ["$schema"], "policy": "scalar"},
                {"path": ["model"], "policy": "scalar"},
                {"path": ["agents"], "policy": "deep"},
                {"path": ["providers"], "policy": "deep"},
                # Scoped to the one leaf the bundle sets so other user-owned
                # `experimental` toggles are never adopted or deleted.
                {"path": ["experimental", "subagent_depth"], "policy": "scalar"},
            ],
            "mcp": [
                {"path": ["mcp", "servers"], "policy": "deep"},
            ],
            "plugins": [
                {"path": ["plugins"], "policy": "list-union"},
            ],
        },
    },
}


# State field listing the hashes of list-union items this tool appended.
ADDED_ITEMS_KEY = "added_item_sha256"


def _scan_outside_strings(text: str, handle: Callable[[str, int], tuple[str, int]]) -> str:
    """Copy text, letting handle(text, i) rewrite spans that start outside strings."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                out.append(text[i : i + 2])
                i += 2
                continue
            in_string = ch != '"'
            out.append(ch)
            i += 1
        elif ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        else:
            emitted, i = handle(text, i)
            out.append(emitted)
    return "".join(out)


def _drop_comment(text: str, i: int) -> tuple[str, int]:
    if text.startswith("//", i):
        newline = text.find("\n", i)
        return "", len(text) if newline < 0 else newline
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        if end < 0:
            raise MergeError("unterminated /* comment */")
        return "", end + 2
    return text[i], i + 1


def _drop_trailing_comma(text: str, i: int) -> tuple[str, int]:
    if text[i] == "," and text[i + 1 :].lstrip()[:1] in ("}", "]"):
        return "", i + 1
    return text[i], i + 1


def strip_jsonc(text: str) -> str:
    """Drop // and /* */ comments, then trailing commas, outside JSON strings."""
    return _scan_outside_strings(_scan_outside_strings(text, _drop_comment), _drop_trailing_comma)


def load_json_config(raw: str, path: Path, profile: dict[str, Any]) -> Any:
    """Parse a destination config; JSONC profiles accept comments + trailing commas."""
    if not raw.strip():
        return {}
    if not profile.get("jsonc"):
        return json.loads(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    data = json.loads(strip_jsonc(raw))
    print(f"  [!!] {path} is JSONC (comments or trailing commas); they are dropped when it is rewritten")
    return data


class MergeError(RuntimeError):
    """Raised for user-facing failures that must abort before any write."""


def load_source(path: Path, profile: dict[str, Any]) -> dict[str, Any]:
    """Parse the repo-managed source config (JSON or TOML by suffix, else the profile's format)."""
    text = path.read_text(encoding="utf-8")
    is_json = path.suffix == ".json" or (path.suffix != ".toml" and profile["format"] == "json")
    source = json.loads(text) if is_json else tomllib.loads(text)
    if not isinstance(source, dict):
        raise MergeError(f"{path}: expected an object at the root")
    return source


def value_hash(value: Any) -> str:
    """Stable hash of a value; identity only, never the value itself."""
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def pointer(path: list[str]) -> str:
    """Render a leaf path as a slash-delimited pointer for state and logs."""
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in path)


def flatten_leaves(path: list[str], value: Any, policy: str) -> list[tuple[list[str], Any]]:
    """Expand one managed rule into the concrete leaves it governs."""
    if policy in {"object", "deep"} and isinstance(value, dict) and value:
        leaves: list[tuple[list[str], Any]] = []
        for key, child in value.items():
            leaves.extend(flatten_leaves([*path, key], child, policy))
        return leaves
    if policy == "map-entries" and isinstance(value, dict):
        return [([*path, key], child) for key, child in value.items()]
    return [(path, value)]


def read_nested(data: Any, path: list[str]) -> tuple[bool, Any]:
    """Return ``(found, value)`` for a nested path within parsed data."""
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def write_nested(data: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a nested path, creating intermediate objects as needed."""
    current = data
    for part in path[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[path[-1]] = value


def union_lists(destination: list[Any], source: list[Any]) -> list[Any]:
    """Append missing source entries, preserving destination order."""
    merged = list(destination)
    for item in source:
        if item not in merged:
            merged.append(item)
    return merged


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A corrupt state file must not block installs; ownership simply falls
        # back to the conservative "preserve the user's value" branch.
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(STATE_PATH, json.dumps(state, indent=2, sort_keys=True) + "\n")


def adopt_matching_values(
    profile: dict[str, Any],
    groups: list[str],
    source: dict[str, Any],
    destination_path: Path,
    state_entry: dict[str, Any],
) -> bool:
    """Record source values already present in the destination as tool-owned.

    First-run configs often already equal the repo. Recording that equality is
    essential: otherwise a future repo update looks like a local edit and is
    conservatively skipped forever.
    """
    if profile["format"] == "json":
        destination = load_json_config(destination_path.read_text(encoding="utf-8"), destination_path, profile)
    else:
        destination = tomllib.loads(destination_path.read_text(encoding="utf-8"))

    changed = False
    for path, source_value in collect_managed_leaves(profile, groups, source):
        if policy_for(profile, groups, path) == "list-union":
            continue
        found, current_value = read_nested(destination, path)
        if found and current_value == source_value:
            key = pointer(path)
            wanted = {"last_applied_sha256": value_hash(source_value)}
            if state_entry.get(key) != wanted:
                state_entry[key] = wanted
                changed = True
    return changed


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename into place.

    A symlink at ``path`` is replaced by the rename, so the link target (often
    a repo file) is never written through. The target's permission bits are
    carried over so a restrictive mode on a credential-bearing config survives.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else None
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(handle.name, mode)
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def collect_managed_leaves(
    profile: dict[str, Any],
    groups: list[str],
    source: dict[str, Any],
) -> list[tuple[list[str], Any]]:
    """Resolve the requested groups into concrete managed leaves."""
    available = profile["groups"]
    leaves: list[tuple[list[str], Any]] = []
    for group in groups:
        rules = available.get(group)
        if rules is None:
            raise MergeError(f"unknown group '{group}' (valid: {', '.join(sorted(available))})")
        for rule in rules:
            found, value = read_nested(source, rule["path"])
            if not found:
                continue
            if rule["policy"] == "list-union":
                leaves.append((rule["path"], value))
                continue
            leaves.extend(flatten_leaves(rule["path"], value, rule["policy"]))
    return leaves


def parse_pointer(key: str) -> list[str]:
    """Inverse of ``pointer``."""
    return [part.replace("~1", "/").replace("~0", "~") for part in key.lstrip("/").split("/")]


def path_is_managed(profile: dict[str, Any], groups: list[str], path: list[str]) -> bool:
    """True when the leaf falls under one of the selected managed rules."""
    for group in groups:
        for rule in profile["groups"].get(group, []):
            if path[: len(rule["path"])] == rule["path"]:
                return True
    return False


def delete_nested(data: dict[str, Any], path: list[str]) -> None:
    """Remove a nested key, pruning parent objects that become empty."""
    parents: list[tuple[dict[str, Any], str]] = []
    current: Any = data
    for part in path[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        parents.append((current, part))
        current = current[part]
    if not isinstance(current, dict) or path[-1] not in current:
        return
    del current[path[-1]]
    for parent, key in reversed(parents):
        if isinstance(parent.get(key), dict) and not parent[key]:
            del parent[key]


def policy_for(profile: dict[str, Any], groups: list[str], path: list[str]) -> str:
    """Find the policy whose rule path prefixes this leaf."""
    for group in groups:
        for rule in profile["groups"].get(group, []):
            if path[: len(rule["path"])] == rule["path"]:
                return str(rule["policy"])
    return "scalar"


def plan_merge(
    profile: dict[str, Any],
    groups: list[str],
    source: dict[str, Any],
    destination: dict[str, Any],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[list[tuple[list[str], Any]], list[str], list[list[str]], dict[str, list[str]]]:
    """Decide, per managed leaf, whether the repo value may be applied.

    Returns updates, conflicts, stale managed leaves to delete, and the hashes
    of list-union items appended per list pointer.
    """
    updates: list[tuple[list[str], Any]] = []
    conflicts: list[str] = []
    managed_now: set[str] = set()
    list_additions: dict[str, list[str]] = {}

    for path, source_value in collect_managed_leaves(profile, groups, source):
        managed_now.add(pointer(path))
        found, current_value = read_nested(destination, path)
        key = pointer(path)

        if policy_for(profile, groups, path) == "list-union":
            current_list = current_value if found and isinstance(current_value, list) else []
            merged = union_lists(current_list, source_value if isinstance(source_value, list) else [source_value])
            # A missing destination path still needs the key written, even when
            # the merged list is empty (Cursor requires permissions.allow/deny).
            if merged != current_list or not found:
                updates.append((path, merged))
                list_additions[key] = [value_hash(item) for item in merged if item not in current_list]
            continue

        if not found:
            updates.append((path, source_value))
            continue
        if current_value == source_value:
            continue
        if force:
            updates.append((path, source_value))
            continue

        last_applied = state_entry.get(key, {}).get("last_applied_sha256")
        if last_applied is not None and last_applied == value_hash(current_value):
            # Destination still holds exactly what this tool wrote, so the repo
            # owns it and may update it.
            updates.append((path, source_value))
            continue

        conflicts.append(key)

    deletions: list[list[str]] = []
    for key, ownership in state_entry.items():
        if key in managed_now or not key.startswith("/"):
            continue
        path = parse_pointer(key)
        # Delete only keys inside a selected managed rule and only when the
        # current value still matches what this tool last wrote. User edits and
        # never-managed siblings survive.
        policy = policy_for(profile, groups, path)
        if policy == "scalar" and not path_is_managed(profile, groups, path):
            continue
        found, current_value = read_nested(destination, path)
        last_applied = ownership.get("last_applied_sha256") if isinstance(ownership, dict) else None
        if found and last_applied == value_hash(current_value):
            deletions.append(path)

    # Narrow migration: a recognized legacy GitHub MCP entry (this repo's old
    # npm/remote defaults) is repo history, not a user edit, so the native
    # stdio entry wins and its incompatible connection/auth fields are removed.
    migration_updates, migration_deletions, preserved = plan_legacy_migration(
        profile, groups, source, destination, force
    )
    planned = {pointer(path) for path, _ in updates}
    removed = {pointer(path) for path in deletions}
    for path, value in migration_updates:
        key = pointer(path)
        if key not in planned:
            updates.append((path, value))
            planned.add(key)
        if key in conflicts:
            conflicts.remove(key)
    for path in migration_deletions:
        key = pointer(path)
        if key not in removed:
            deletions.append(path)
            removed.add(key)
    # A custom GitHub connection is left wholly untouched (without --force).
    updates = [(p, v) for p, v in updates if not any(p[: len(b)] == b for b in preserved)]
    deletions = [p for p in deletions if not any(p[: len(b)] == b for b in preserved)]

    return updates, conflicts, deletions, list_additions


# ---------------------------------------------------------------------------
# TOML text patching
#
# tomllib parses but cannot serialize, and a hand-rolled writer would destroy
# comments, ordering and quoting. Instead we locate the exact byte span of each
# managed assignment and replace only that span.
# ---------------------------------------------------------------------------

TOML_TABLE_RE = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*(?:#.*)?$")
TOML_KEY_RE = re.compile(
    r"^\s*((?:[A-Za-z0-9_-]+|\"[^\"]*\"|'[^']*')(?:\s*\.\s*(?:[A-Za-z0-9_-]+|\"[^\"]*\"|'[^']*'))*)\s*="
)


def split_toml_key(raw: str) -> list[str]:
    """Split a possibly dotted, possibly quoted TOML key into segments."""
    parts: list[str] = []
    for chunk in re.findall(r"\"[^\"]*\"|'[^']*'|[^.\s]+", raw):
        if chunk[:1] in {'"', "'"}:
            parts.append(chunk[1:-1])
        else:
            parts.append(chunk)
    return parts


def format_toml_value(value: Any) -> str:
    """Render a Python value as TOML. Mirrors the JSON subset we manage."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(format_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{format_toml_key(k)} = {format_toml_value(v)}" for k, v in value.items()) + " }"
    raise MergeError(f"cannot render TOML value of type {type(value).__name__}")


def format_toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key, ensure_ascii=False)


def format_toml_path(path: list[str]) -> str:
    return ".".join(format_toml_key(part) for part in path)


def scan_toml_assignments(lines: list[str]) -> dict[tuple[str, ...], tuple[int, int]]:
    """Map each assignment's full key path to its ``[start, end)`` line span.

    Multi-line values (arrays, multi-line strings) are handled by extending the
    span until the accumulated text parses as TOML again.
    """
    spans: dict[tuple[str, ...], tuple[int, int]] = {}
    table: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        table_match = TOML_TABLE_RE.match(line)
        if table_match:
            table = split_toml_key(table_match.group(1))
            index += 1
            continue

        key_match = TOML_KEY_RE.match(line)
        if not key_match:
            index += 1
            continue

        end = index + 1
        while end <= len(lines):
            candidate = "".join(lines[index:end])
            try:
                tomllib.loads(candidate)
                break
            except tomllib.TOMLDecodeError:
                end += 1
        else:
            raise MergeError(f"could not determine the end of the TOML assignment starting at line {index + 1}")

        spans[tuple(table + split_toml_key(key_match.group(1)))] = (index, end)
        index = end

    return spans


def repair_duplicate_managed_toml(text: str, managed_paths: list[list[str]]) -> str:
    """Remove duplicate managed assignments/tables so ``--force`` can recover.

    Recovery is intentionally narrow: only paths supplied by the selected
    profile groups are eligible, and a duplicated table is removed only when
    every assignment in each occurrence is managed. The normal merge then
    writes the source-of-truth values back atomically. Unrelated malformed TOML
    remains an error.
    """
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    managed = {tuple(path) for path in managed_paths}
    occurrences: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    table_headers: dict[tuple[str, ...], list[int]] = {}
    table: tuple[str, ...] = ()
    covered_assignment_lines: set[int] = set()
    index = 0

    while index < len(lines):
        line = lines[index]
        table_match = TOML_TABLE_RE.match(line)
        if table_match:
            table = tuple(split_toml_key(table_match.group(1)))
            table_headers.setdefault(table, []).append(index)
            index += 1
            continue

        key_match = TOML_KEY_RE.match(line)
        if not key_match:
            index += 1
            continue

        end = index + 1
        while end <= len(lines):
            try:
                tomllib.loads("".join(lines[index:end]))
                break
            except tomllib.TOMLDecodeError:
                end += 1
        else:
            return text

        path = (*table, *split_toml_key(key_match.group(1)))
        occurrences.setdefault(path, []).append((index, end))
        covered_assignment_lines.update(range(index, end))
        index = end

    duplicate_paths = {path for path, spans in occurrences.items() if len(spans) > 1 and path in managed}
    if not duplicate_paths:
        return text

    duplicate_tables = {
        table_path
        for table_path, headers in table_headers.items()
        if len(headers) > 1 and any(path[:-1] == table_path for path in duplicate_paths)
    }

    header_indexes = sorted(index for indexes in table_headers.values() for index in indexes)
    remove_lines: set[int] = set()

    for table_path in duplicate_tables:
        for header_index in table_headers[table_path]:
            next_header = next((candidate for candidate in header_indexes if candidate > header_index), len(lines))
            for line_index in range(header_index + 1, next_header):
                stripped = lines[line_index].strip()
                if not stripped or stripped.startswith("#") or line_index in covered_assignment_lines:
                    continue
                return text

            section_paths = {
                path
                for path, spans in occurrences.items()
                if any(header_index < start < next_header for start, _ in spans)
            }
            if not section_paths.issubset(managed):
                return text

            remove_lines.add(header_index)
            for path in section_paths:
                for start, end in occurrences[path]:
                    if header_index < start < next_header:
                        remove_lines.update(range(start, end))

    for path in duplicate_paths:
        if path[:-1] in duplicate_tables:
            continue
        for start, end in occurrences[path]:
            remove_lines.update(range(start, end))

    return "".join(line for line_index, line in enumerate(lines) if line_index not in remove_lines)


def table_end_line(lines: list[str], table: list[str]) -> int | None:
    """Return the insertion point at the end of an existing table's body."""
    target = tuple(table)
    in_table = False
    last_content = None

    for index, line in enumerate(lines):
        table_match = TOML_TABLE_RE.match(line)
        if table_match:
            if in_table:
                return (last_content + 1) if last_content is not None else index
            in_table = tuple(split_toml_key(table_match.group(1))) == target
            if in_table:
                last_content = index
            continue
        if in_table and line.strip() and not line.strip().startswith("#"):
            last_content = index

    if in_table:
        return (last_content + 1) if last_content is not None else len(lines)
    return None


def split_inline_deletions(
    text: str, deletions: list[list[str]], destination: dict[str, Any]
) -> tuple[list[list[str]], list[tuple[list[str], Any]]]:
    """Turn deletions inside an inline-table assignment into a rewrite of that assignment.

    Siblings stay; a table left empty is deleted whole. Other deletions pass through.
    """
    spans = scan_toml_assignments(text.splitlines(keepends=True))
    plain: list[list[str]] = []
    holders: dict[tuple[str, ...], dict[str, Any]] = {}
    for path in deletions:
        parent = next((tuple(path[:n]) for n in range(len(path) - 1, 0, -1) if tuple(path[:n]) in spans), None)
        value = read_nested(destination, list(parent))[1] if parent else None
        if parent is None or not isinstance(value, dict):
            plain.append(path)
            continue
        holder = holders.setdefault(parent, {"v": json.loads(json.dumps(value))})
        delete_nested(holder, ["v", *path[len(parent) :]])
    rewrites: list[tuple[list[str], Any]] = []
    for parent, holder in holders.items():
        if "v" in holder:
            rewrites.append((list(parent), holder["v"]))
        else:
            plain.append(list(parent))
    return plain, rewrites


def apply_toml_updates(
    text: str,
    updates: list[tuple[list[str], Any]],
    deletions: list[list[str]] | None = None,
) -> str:
    """Patch managed assignments in place, leaving all other bytes untouched.

    Deletions drop the assignment or whole table subtree at each path.
    """
    if deletions:
        text = delete_toml_entries(text, deletions)
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    # Apply bottom-up so earlier spans keep their indices valid.
    replacements: list[tuple[int, int, str]] = []
    root_appends: list[str] = []
    appends: dict[tuple[str, ...], list[str]] = {}
    new_tables: dict[tuple[str, ...], list[str]] = {}

    spans = scan_toml_assignments(lines)

    for path, value in updates:
        key = tuple(path)
        rendered = f"{format_toml_key(path[-1])} = {format_toml_value(value)}\n"

        if key in spans:
            start, end = spans[key]
            replacements.append((start, end, rendered))
            continue

        table = key[:-1]
        if not table:
            root_appends.append(rendered)
            continue

        if table_end_line(lines, list(table)) is not None:
            appends.setdefault(table, []).append(rendered)
        else:
            new_tables.setdefault(table, []).append(rendered)

    if root_appends:
        # Root keys must land above the first table header, otherwise TOML
        # would read them as members of the last table in the file.
        insert_at = next(
            (index for index, line in enumerate(lines) if TOML_TABLE_RE.match(line)),
            len(lines),
        )
        replacements.append((insert_at, insert_at, "".join(root_appends)))

    for table, rendered_lines in appends.items():
        insert_at = table_end_line(lines, list(table))
        assert insert_at is not None
        replacements.append((insert_at, insert_at, "".join(rendered_lines)))

    for start, end, rendered in sorted(replacements, key=lambda item: item[0], reverse=True):
        lines[start:end] = [rendered] if rendered else []

    tail = ""
    for table, rendered_lines in new_tables.items():
        tail += f"\n[{format_toml_path(list(table))}]\n" + "".join(rendered_lines)

    return "".join(lines) + tail


def entry_policy_rules(profile: dict[str, Any], groups: list[str]) -> list[dict[str, Any]]:
    """All rules of the selected groups; unknown groups are an error."""
    available = profile["groups"]
    rules: list[dict[str, Any]] = []
    for group in groups:
        group_rules = available.get(group)
        if group_rules is None:
            raise MergeError(f"unknown group '{group}' (valid: {', '.join(sorted(available))})")
        rules.extend(group_rules)
    return rules


def plan_list_removals(
    rules: list[dict[str, Any]],
    source: dict[str, Any],
    destination: dict[str, Any],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[list[tuple[list[str], list[Any]]], list[list[str]], list[str], list[str]]:
    """Take back list-union items this tool appended.

    Items are owned when their hash was recorded at merge time; ``force`` also
    takes every item that equals a repo value. A list left empty is deleted
    unless its rule says ``keep_empty``. Returns list rewrites, paths to
    delete, conflicts and spent state keys.
    """
    rewrites: list[tuple[list[str], list[Any]]] = []
    deletes: list[list[str]] = []
    conflicts: list[str] = []
    spent: list[str] = []
    for rule in rules:
        path = rule["path"]
        key = pointer(path)
        found, current = read_nested(destination, path)
        if not found or not isinstance(current, list):
            if key in state_entry:
                spent.append(key)
            continue
        _, source_value = read_nested(source, path)
        source_items = source_value if isinstance(source_value, list) else []
        owned_hashes = set(state_entry.get(key, {}).get(ADDED_ITEMS_KEY, []))
        kept = [
            item for item in current if value_hash(item) not in owned_hashes and not (force and item in source_items)
        ]
        if any(item in source_items for item in kept):
            conflicts.append(key)
        if key in state_entry:
            spent.append(key)
        keep_key = bool(kept) or bool(rule.get("keep_empty"))
        # An empty list is dropped only when this tool emptied or seeded it.
        if kept == current and (keep_key or key not in state_entry):
            continue
        if keep_key:
            rewrites.append((path, kept))
        else:
            deletes.append(path)
    return rewrites, deletes, conflicts, spent


def plan_remove(
    profile: dict[str, Any],
    groups: list[str],
    source: dict[str, Any],
    destination: dict[str, Any],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[list[list[str]], list[tuple[list[str], list[Any]]], list[str], list[str]]:
    """Decide which managed entries can be deleted from the destination.

    Returns entry paths to delete, list-union rewrites, conflicts and the
    state keys that no longer track anything.
    """
    rules = entry_policy_rules(profile, groups)
    list_rules = [rule for rule in rules if rule["policy"] == "list-union"]
    managed = [rule for rule in rules if rule["policy"] != "list-union"]

    candidates: dict[tuple[str, ...], dict[str, Any]] = {}
    for rule in managed:
        found, value = read_nested(source, rule["path"])
        if not found:
            continue
        if rule["policy"] == "scalar":
            candidates[tuple(rule["path"])] = {
                "path": list(rule["path"]),
                "source_value": value,
                "policy": rule["policy"],
            }
        elif isinstance(value, dict) and value:
            for child_key, child_value in value.items():
                entry = [*rule["path"], child_key]
                candidates[tuple(entry)] = {
                    "path": entry,
                    "source_value": child_value,
                    "policy": rule["policy"],
                }

    for key in state_entry:
        if not key.startswith("/"):
            continue
        path = parse_pointer(key)
        best: dict[str, Any] | None = None
        for rule in managed:
            if path[: len(rule["path"])] == rule["path"] and (best is None or len(rule["path"]) > len(best["path"])):
                best = rule
        if best is None:
            continue
        if len(path) <= len(best["path"]):
            entry = list(best["path"])
        else:
            entry = [*best["path"], path[len(best["path"])]]
        candidates.setdefault(
            tuple(entry),
            {"path": entry, "source_value": None, "policy": best["policy"]},
        )

    to_remove: list[list[str]] = []
    conflicts: list[str] = []
    stale_keys: list[str] = []
    for entry_key in sorted(candidates, key=lambda parts: pointer(list(parts))):
        candidate = candidates[entry_key]
        entry_path = candidate["path"]
        under = [
            key for key in state_entry if key.startswith("/") and parse_pointer(key)[: len(entry_path)] == entry_path
        ]
        found, dest_value = read_nested(destination, entry_path)
        if not found:
            stale_keys.extend(under)
            continue
        source_value = candidate["source_value"]
        if source_value is not None and dest_value == source_value:
            owned = True
        else:
            leaves = flatten_leaves(entry_path, dest_value, str(candidate["policy"]))
            owned = bool(leaves) and all(
                state_entry.get(pointer(leaf_path), {}).get("last_applied_sha256") == value_hash(leaf_value)
                for leaf_path, leaf_value in leaves
            )
        if owned or force:
            to_remove.append(entry_path)
            stale_keys.extend(under)
        else:
            conflicts.append(pointer(entry_path))

    rewrites, list_deletes, list_conflicts, spent = plan_list_removals(
        list_rules, source, destination, state_entry, force
    )
    to_remove.extend(list_deletes)
    conflicts.extend(list_conflicts)
    stale_keys.extend(spent)
    return to_remove, rewrites, conflicts, sorted(set(stale_keys))


def remove_json(
    source: dict[str, Any],
    destination_path: Path,
    profile: dict[str, Any],
    groups: list[str],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[str | None, list[list[str]], list[str], list[str]]:
    if not destination_path.exists():
        return None, [], [], []
    raw = destination_path.read_text(encoding="utf-8").strip()
    destination = load_json_config(raw, destination_path, profile)
    if not isinstance(destination, dict):
        raise MergeError(f"{destination_path}: expected a JSON object at the root")

    to_remove, rewrites, conflicts, stale_keys = plan_remove(profile, groups, source, destination, state_entry, force)
    if not to_remove and not rewrites:
        return None, [], conflicts, stale_keys

    pruned = json.loads(json.dumps(destination))
    for path in to_remove:
        delete_nested(pruned, path)
    for path, items in rewrites:
        write_nested(pruned, path, items)
    changed = to_remove + [path for path, _ in rewrites]
    return json.dumps(pruned, indent=2, ensure_ascii=False) + "\n", changed, conflicts, stale_keys


def delete_toml_entries(text: str, entries: list[list[str]]) -> str:
    """Drop every table and assignment at or below the given paths.

    A path inside an inline-table value is one assignment, so callers route
    those through split_inline_deletions first.
    """
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    prefixes = [tuple(entry) for entry in entries]

    def under(path: tuple[str, ...]) -> bool:
        return any(path[: len(prefix)] == prefix for prefix in prefixes)

    headers = [
        (index, tuple(split_toml_key(match.group(1))))
        for index, line in enumerate(lines)
        if (match := TOML_TABLE_RE.match(line))
    ]
    bounds = [index for index, _ in headers] + [len(lines)]
    remove: set[int] = set()
    for position, (index, table) in enumerate(headers):
        if under(table):
            remove.update(range(index, bounds[position + 1]))
    for path, (start, end) in scan_toml_assignments(lines).items():
        if under(path):
            remove.update(range(start, end))
    return "".join(line for index, line in enumerate(lines) if index not in remove)


def remove_toml(
    source: dict[str, Any],
    destination_path: Path,
    profile: dict[str, Any],
    groups: list[str],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[str | None, list[list[str]], list[str], list[str]]:
    if not destination_path.exists():
        return None, [], [], []
    destination_text = destination_path.read_text(encoding="utf-8")
    destination = tomllib.loads(destination_text)

    to_remove, rewrites, conflicts, stale_keys = plan_remove(profile, groups, source, destination, state_entry, force)
    if not to_remove and not rewrites:
        return None, [], conflicts, stale_keys

    rendered = delete_toml_entries(destination_text, to_remove)
    if rewrites:
        rendered = apply_toml_updates(rendered, list(rewrites))
    # Re-parse so a bad patch can never reach the user's config.
    reparsed = tomllib.loads(rendered)
    for path in to_remove:
        if read_nested(reparsed, path)[0]:
            raise MergeError(f"TOML remove verification failed for {pointer(path)}")
    for path, items in rewrites:
        if read_nested(reparsed, path) != (True, items):
            raise MergeError(f"TOML remove verification failed for {pointer(path)}")
    return rendered, to_remove + [path for path, _ in rewrites], conflicts, stale_keys


def is_empty_config(value: Any) -> bool:
    """True for a dict containing nothing but (recursively) empty dicts."""
    return isinstance(value, dict) and all(is_empty_config(child) for child in value.values())


def rendered_is_empty(profile: dict[str, Any], rendered: str) -> bool:
    """Whether a post-removal file holds nothing worth keeping on disk.

    Empty ``keep_empty`` lists are tool scaffolding, not content.
    """
    if profile["format"] == "json":
        data = json.loads(rendered)
        for rules in profile["groups"].values():
            for rule in rules:
                if rule.get("keep_empty") and read_nested(data, rule["path"]) == (True, []):
                    delete_nested(data, rule["path"])
        return data == {}
    # Only bare (now empty) table headers may remain; comments are user content.
    only_headers = all(not line.strip() or TOML_TABLE_RE.match(line) for line in rendered.splitlines())
    return only_headers and is_empty_config(tomllib.loads(rendered))


def merge_json(
    source: dict[str, Any],
    destination_path: Path,
    profile: dict[str, Any],
    groups: list[str],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[str | None, list[tuple[list[str], Any]], list[str], list[list[str]], dict[str, list[str]]]:

    if destination_path.exists():
        raw = destination_path.read_text(encoding="utf-8").strip()
        destination = load_json_config(raw, destination_path, profile)
        if not isinstance(destination, dict):
            raise MergeError(f"{destination_path}: expected a JSON object at the root")
    else:
        destination = {}

    updates, conflicts, deletions, additions = plan_merge(profile, groups, source, destination, state_entry, force)
    if not updates and not deletions:
        return None, updates, conflicts, deletions, additions

    merged = json.loads(json.dumps(destination))
    for path, value in updates:
        write_nested(merged, path, value)
    for path in deletions:
        delete_nested(merged, path)
    return json.dumps(merged, indent=2, ensure_ascii=False) + "\n", updates, conflicts, deletions, additions


def merge_toml(
    source: dict[str, Any],
    destination_path: Path,
    profile: dict[str, Any],
    groups: list[str],
    state_entry: dict[str, Any],
    force: bool,
) -> tuple[str | None, list[tuple[list[str], Any]], list[str], list[list[str]], dict[str, list[str]]]:

    if destination_path.exists():
        destination_text = destination_path.read_text(encoding="utf-8")
        try:
            destination = tomllib.loads(destination_text)
        except tomllib.TOMLDecodeError:
            if not force:
                raise
            managed_paths = [path for path, _ in collect_managed_leaves(profile, groups, source)]
            destination_text = repair_duplicate_managed_toml(destination_text, managed_paths)
            destination = tomllib.loads(destination_text)
    else:
        destination_text = ""
        destination = {}

    updates, conflicts, deletions, additions = plan_merge(profile, groups, source, destination, state_entry, force)
    if not updates and not deletions:
        return None, updates, conflicts, deletions, additions

    plain_deletions, inline_rewrites = split_inline_deletions(destination_text, deletions, destination)
    merged_text = apply_toml_updates(destination_text, [*updates, *inline_rewrites], plain_deletions)

    # Re-parse so a bad patch can never reach the user's config.
    reparsed = tomllib.loads(merged_text)
    for path, value in updates:
        found, actual = read_nested(reparsed, path)
        if not found or actual != value:
            raise MergeError(f"TOML merge verification failed for {pointer(path)}")
    for path in deletions:
        if read_nested(reparsed, path)[0]:
            raise MergeError(f"TOML cannot remove {pointer(path)} (inline table?); edit it by hand")

    return merged_text, updates, conflicts, deletions, additions


def run_remove(
    args: argparse.Namespace,
    profile: dict[str, Any],
    groups: list[str],
    source: dict[str, Any],
    destination_path: Path,
    state: dict[str, Any],
    state_key: str,
    state_entry: dict[str, Any],
    plan_state: dict[str, Any],
) -> int:
    """Remove tool-owned managed entries; user-edited entries need --force."""
    label = f"({args.profile}: {', '.join(groups)})"
    remove = remove_json if profile["format"] == "json" else remove_toml
    try:
        rendered, removed, conflicts, stale_keys = remove(
            source, destination_path, profile, groups, plan_state, args.force
        )
    except (MergeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"merge_managed_config: {error}", file=sys.stderr)
        return 1

    for conflict in conflicts:
        print(f"  [!!] kept your local value at {conflict} (re-run with --force to remove it)")

    if args.dry_run:
        for path in removed:
            print(f"  would remove {pointer(path)}")
        return 0

    for key in stale_keys:
        state_entry.pop(key, None)
    if state_entry:
        state[state_key] = state_entry
    else:
        state.pop(state_key, None)

    if rendered is None:
        if stale_keys:
            save_state(state)
        print(f"  [ok] nothing to remove: {destination_path} {label}")
        return 0

    original_bytes = destination_path.read_bytes()
    original_mode = destination_path.stat().st_mode & 0o777
    original_link = os.readlink(destination_path) if destination_path.is_symlink() else None
    empty = rendered_is_empty(profile, rendered)
    if empty:
        destination_path.unlink()
    else:
        atomic_write(destination_path, rendered)
    try:
        save_state(state)
    except BaseException:
        destination_path.unlink(missing_ok=True)
        if original_link is not None:
            destination_path.symlink_to(original_link)
        else:
            destination_path.write_bytes(original_bytes)
            destination_path.chmod(original_mode)
        raise

    noun = "entry" if len(removed) == 1 else "entries"
    print(f"  [ok] removed {len(removed)} managed {noun} from {destination_path} {label}")
    if empty:
        print(f"  [ok] removed empty file {destination_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES), help="Managed-key profile to apply")
    parser.add_argument("--source", required=True, type=Path, help="Repo-managed config file")
    parser.add_argument("--destination", required=True, type=Path, help="User config file to merge into")
    parser.add_argument("--groups", required=True, help="Comma-separated managed key groups")
    parser.add_argument("--force", action="store_true", help="Let repo values win over conflicting local edits")
    parser.add_argument("--dry-run", action="store_true", help="Report the merge without writing anything")
    parser.add_argument("--remove", action="store_true", help="Remove managed entries instead of merging them")
    parser.add_argument(
        "--entries",
        help="Comma-separated entry names (e.g. MCP servers) to restrict the run to; other entries are left alone",
    )
    parser.add_argument(
        "--list-entries",
        action="store_true",
        help="Print the entry names the source manages for --groups, one per line, and exit",
    )
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    groups = [group.strip() for group in args.groups.split(",") if group.strip()]
    if not groups:
        print("merge_managed_config: --groups requires at least one group", file=sys.stderr)
        return 1

    source_path = args.source if args.source.is_absolute() else (REPO_ROOT / args.source)
    destination_path = args.destination.expanduser()

    if not source_path.is_file():
        print(f"merge_managed_config: source not found: {source_path}", file=sys.stderr)
        return 1
    try:
        source = load_source(source_path, profile)
    except (MergeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"merge_managed_config: {error}", file=sys.stderr)
        return 1

    managed_entries = available_entries(profile, groups, source)
    if args.list_entries:
        for name in managed_entries:
            print(name)
        return 0
    entries: list[str] | None = None
    if args.entries is not None:
        entries = [name.strip() for name in args.entries.split(",") if name.strip()]
        unknown = [name for name in entries if name not in managed_entries]
        if not entries or unknown:
            print(
                f"merge_managed_config: unknown entries {', '.join(unknown) or '(none given)'} "
                f"(managed: {', '.join(managed_entries) or 'none'})",
                file=sys.stderr,
            )
            return 1
        source = select_source_entries(profile, groups, source, entries)

    # Read a symlinked destination through its target but do not mutate it yet.
    # Validation, merge planning, and --dry-run must remain side-effect free.
    replaced_symlink = destination_path.is_symlink()

    state = load_state()
    state_key = f"{args.profile}:{destination_path}"
    state_entry = state.get(state_key, {})
    if not isinstance(state_entry, dict):
        state_entry = {}
    # Plan against the selected entries only; writes still go to the full entry.
    plan_state = (
        state_entry if entries is None else selected_state(profile, groups, state_entry, entries, parse_pointer)
    )

    if args.remove:
        return run_remove(args, profile, groups, source, destination_path, state, state_key, state_entry, plan_state)

    merge = merge_json if profile["format"] == "json" else merge_toml
    try:
        rendered, updates, conflicts, deletions, additions = merge(
            source, destination_path, profile, groups, plan_state, args.force
        )
    except (MergeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"merge_managed_config: {error}", file=sys.stderr)
        return 1

    for conflict in conflicts:
        print(f"  [!!] kept your local value at {conflict} (re-run with --force to take the repo value)")

    if rendered is None:
        if (
            not args.dry_run
            and destination_path.exists()
            and adopt_matching_values(profile, groups, source, destination_path, state_entry)
        ):
            state[state_key] = state_entry
            save_state(state)
        print(f"  [ok] up-to-date: {destination_path} ({args.profile}: {', '.join(groups)})")
        return 0

    if args.dry_run:
        for path, _ in updates:
            print(f"  would set {pointer(path)}")
        for path in deletions:
            print(f"  would remove {pointer(path)}")
        if replaced_symlink:
            print(f"  would replace symlink with a real file: {destination_path}")
        return 0

    # Prepare state before committing the config. If writing state fails after
    # the config rename, restore the original bytes (or remove the new file),
    # keeping config and ownership metadata consistent.
    managed_keys = {pointer(path) for path, _ in collect_managed_leaves(profile, groups, source)}
    for path, value in updates:
        key = pointer(path)
        if key not in managed_keys:
            # Migration rewrites of user-owned extras (e.g. env_vars) stay user-owned.
            continue
        ownership: dict[str, Any] = {"last_applied_sha256": value_hash(value)}
        if key in additions:
            previous = state_entry.get(key, {}).get(ADDED_ITEMS_KEY, [])
            ownership[ADDED_ITEMS_KEY] = sorted({*previous, *additions[key]})
        state_entry[key] = ownership
    for path in deletions:
        state_entry.pop(pointer(path), None)
    state[state_key] = state_entry

    original_bytes = destination_path.read_bytes() if destination_path.exists() else None
    original_mode = destination_path.stat().st_mode & 0o777 if destination_path.exists() else None
    original_link = os.readlink(destination_path) if replaced_symlink else None

    # Only now, after parsing and planning have succeeded, does anything on
    # disk change. atomic_write replaces the symlink itself via rename.
    atomic_write(destination_path, rendered)
    try:
        save_state(state)
    except BaseException:
        destination_path.unlink(missing_ok=True)
        if original_link is not None:
            destination_path.symlink_to(original_link)
        elif original_bytes is not None:
            destination_path.write_bytes(original_bytes)
            if original_mode is not None:
                destination_path.chmod(original_mode)
        raise

    if replaced_symlink:
        print(f"  [!!] replaced symlink with a real file: {destination_path}")

    print(
        f"  [ok] applied {len(updates)} managed update(s) and {len(deletions)} removal(s) "
        f"to {destination_path} ({args.profile}: {', '.join(groups)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
