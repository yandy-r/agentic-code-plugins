"""Entry selection for merge_managed_config.py (``--entries`` / ``--list-entries``).

Map-shaped managed rules (``deep`` and ``map-entries``: MCP servers, plugin
tables) hold named entries. A ``list-union`` rule with an ``item_key`` holds
keyed items (opencode plugin specifiers keyed by package name). Selecting
entries narrows a run to just those names: the source is filtered to them, and
ownership state outside them is hidden from planning so a partial sync or
remove never prunes the rest.

A rule with ``entry_key: "marketplace"`` is *derived*: it is never listed and
its names are not valid entries. It follows the selected entries through
``marketplace_of`` (``superpowers@claude-plugins-official`` selects the
``claude-plugins-official`` marketplace), and on removal a marketplace that an
enabled plugin still uses is retained.

``narrow_profile`` records a selection on each entry rule of the entry groups
as ``rule["selected"]``; every helper below reads it from there.

A rule with ``leaf_rules: True`` is owned per leaf, not per entry:
``expand_leaf_rules`` replaces it with one ``scalar`` rule per leaf of the
source and of the recorded state under it. Two owners can then share one
entry (the opencode catalog's ``agents.general.disabled`` beside the bundle's
``agents.general.model``) and each removes only its own leaves.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

ENTRY_POLICIES = ("deep", "map-entries")
ITEM_KEYS = ("package", "name")

Rule = dict[str, Any]
Hasher = Callable[[Any], str]


def is_entry_rule(rule: Rule) -> bool:
    """Map-shaped rules, and list-union rules whose items carry a key."""
    return rule["policy"] in ENTRY_POLICIES or (rule["policy"] == "list-union" and rule.get("item_key") in ITEM_KEYS)


def is_derived(rule: Rule) -> bool:
    """Rules selected through another rule's entry names (``entry_key``)."""
    return rule.get("entry_key") is not None


def selection(rule: Rule) -> frozenset[str] | None:
    """The names a selective run keeps for ``rule``; ``None`` means the whole rule."""
    selected = rule.get("selected")
    return selected if isinstance(selected, frozenset) else None


def _rules(profile: dict[str, Any], groups: list[str]) -> list[Rule]:
    return [rule for group in groups for rule in profile["groups"].get(group, [])]


def entry_rule_paths(profile: dict[str, Any], groups: list[str]) -> list[list[str]]:
    """Container paths of the selected groups' map-shaped rules."""
    return [list(rule["path"]) for rule in _rules(profile, groups) if rule["policy"] in ENTRY_POLICIES]


def marketplace_of(name: str) -> str | None:
    """Text after the last ``@`` of a ``plugin@marketplace`` name; ``None`` without one."""
    _, at, marketplace = name.rpartition("@")
    return marketplace if at and marketplace else None


def _strip_version(spec: str) -> str:
    """``@scope/pkg@1.2.3`` → ``@scope/pkg``, ``pkg@1.2.3`` → ``pkg``.

    The version starts at the first ``@`` after index 0 (index 0 is a scope marker).
    """
    cut = spec.find("@", 1)
    return spec[:cut] if cut > 0 else spec


def _package_key(spec: str) -> str | None:
    spec = spec.strip()
    if spec.startswith("npm:"):
        # npm aliases name a registry package: ``npm:@s/x@1`` ≡ ``npm:@s/x``.
        name = _strip_version(spec[len("npm:") :])
        return f"npm:{name}" if name else None
    if spec.startswith((".", "/", "~", "file:")):
        # Local paths carry no version.
        return spec.rstrip("/") or None
    if ":" in spec:
        # Git and URL specifiers pin a version with a ``#ref`` fragment.
        return spec.split("#", 1)[0].rstrip("/") or None
    return _strip_version(spec) or None


def item_key(rule: Rule, item: object) -> str | None:
    """Identity of a list item under ``rule["item_key"]``; ``None`` when unkeyed."""
    kind = rule.get("item_key")
    if kind == "package":
        spec = item if isinstance(item, str) else item.get("package") if isinstance(item, dict) else None
        return _package_key(spec) if isinstance(spec, str) else None
    if kind == "name":
        name = item.get("name") if isinstance(item, dict) else None
        return name if isinstance(name, str) and name else None
    return None


def _value(data: Any, path: list[str]) -> Any:
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _leaf_paths(path: list[str], value: Any) -> list[list[str]]:
    if isinstance(value, dict) and value:
        return [leaf for key, child in value.items() for leaf in _leaf_paths([*path, str(key)], child)]
    return [path]


def expand_leaf_rules(profile: dict[str, Any], source: dict[str, Any], owned: list[list[str]]) -> dict[str, Any]:
    """Copy of ``profile`` whose ``leaf_rules`` rules become per-leaf scalar rules.

    The leaves are those of the source under the rule path plus the ``owned``
    state paths under it, so a leaf the source no longer sets can still be
    removed. A rule with neither expands to no rules.
    """

    def expanded(rule: Rule) -> list[Rule]:
        if not rule.get("leaf_rules"):
            return [rule]
        prefix = list(rule["path"])
        value = _value(source, prefix)
        paths = _leaf_paths(prefix, value) if isinstance(value, dict) and value else []
        paths += [path for path in owned if len(path) > len(prefix) and path[: len(prefix)] == prefix]
        return [{"path": list(path), "policy": "scalar"} for path in dict.fromkeys(tuple(p) for p in paths)]

    return {
        **profile,
        "groups": {
            group: [leaf for rule in rules for leaf in expanded(rule)] for group, rules in profile["groups"].items()
        },
    }


def available_entries(profile: dict[str, Any], groups: list[str], source: dict[str, Any]) -> list[str]:
    """Entry names the source manages, in source order, without duplicates."""
    names: list[str] = []
    for rule in _rules(profile, groups):
        if not is_entry_rule(rule) or is_derived(rule):
            continue
        value = _value(source, rule["path"])
        if isinstance(value, dict):
            keys = [str(name) for name in value]
        elif isinstance(value, list) and rule["policy"] == "list-union":
            keys = [key for item in value if (key := item_key(rule, item)) is not None]
        else:
            keys = []
        names.extend(key for key in dict.fromkeys(keys) if key not in names)
    return names


def narrow_profile(profile: dict[str, Any], entry_groups: list[str], entries: list[str]) -> dict[str, Any]:
    """Copy of ``profile`` whose entry rules in ``entry_groups`` select ``entries``."""
    names = frozenset(entries)
    marketplaces = frozenset(market for name in entries if (market := marketplace_of(name)) is not None)

    def narrowed(group: str, rule: Rule) -> Rule:
        if group not in entry_groups or not is_entry_rule(rule):
            return rule
        return {**rule, "selected": marketplaces if is_derived(rule) else names}

    return {
        **profile,
        "groups": {group: [narrowed(group, rule) for rule in rules] for group, rules in profile["groups"].items()},
    }


def select_source_entries(profile: dict[str, Any], groups: list[str], source: dict[str, Any]) -> dict[str, Any]:
    """Copy of ``source`` whose selected containers keep only selected entries.

    A container the selection empties is dropped so a selective run never
    writes an empty map or list.
    """
    selected: dict[str, Any] = dict(source)
    for rule in _rules(profile, groups):
        chosen = selection(rule)
        if chosen is None:
            continue
        path = rule["path"]
        value = _value(selected, path)
        kept: dict[str, Any] | list[Any]
        if isinstance(value, dict):
            kept = {name: child for name, child in value.items() if name in chosen}
        elif isinstance(value, list) and rule["policy"] == "list-union":
            kept = [item for item in value if item_key(rule, item) in chosen]
        else:
            continue
        # Shallow-copy each dict along the path so the original stays intact.
        parent = selected
        for part in path[:-1]:
            parent[part] = dict(parent[part])
            parent = parent[part]
        if kept:
            parent[path[-1]] = kept
        else:
            del parent[path[-1]]
    return selected


def outside_selection(profile: dict[str, Any], groups: list[str], path: list[str]) -> bool:
    """True when ``path`` is inside a selected map container but not a selected entry.

    List pointers are never outside: their owned hashes are filtered by item key
    at plan time instead.
    """
    for rule in _rules(profile, groups):
        chosen = selection(rule)
        if chosen is None or rule["policy"] == "list-union":
            continue
        rule_path = rule["path"]
        if path[: len(rule_path)] == rule_path:
            return len(path) <= len(rule_path) or path[len(rule_path)] not in chosen
    return False


def selected_state(
    profile: dict[str, Any],
    groups: list[str],
    state_entry: dict[str, Any],
    parse_pointer: Callable[[str], list[str]],
) -> dict[str, Any]:
    """The part of ``state_entry`` a selected run may plan against."""
    return {
        key: value
        for key, value in state_entry.items()
        if not (key.startswith("/") and outside_selection(profile, groups, parse_pointer(key)))
    }


def plan_keyed_list(
    rule: Rule,
    current: list[Any],
    source_items: list[Any],
    owned: list[str],
    force: bool,
    value_hash: Hasher,
) -> tuple[list[Any], list[str], list[str]]:
    """Merge keyed source items into ``current``; a new version replaces ours.

    Per source item: an identical item present is a no-op; a same-key item this
    tool added (hash in ``owned``) is replaced in place and further owned
    same-key copies are dropped; a same-key item the user wrote is kept and
    reported (``force`` replaces it); otherwise the item is appended.
    Returns the merged list, the owned hashes still present in it, and the
    conflicting item keys.
    """
    merged = list(current)
    mine = set(owned)
    conflicts: list[str] = []
    for item in source_items:
        key = item_key(rule, item)
        if key is None:
            if item not in merged:
                merged.append(item)
                mine.add(value_hash(item))
            continue
        same = [index for index, existing in enumerate(merged) if item_key(rule, existing) == key]
        ours = [index for index in same if value_hash(merged[index]) in mine]
        identical = next((index for index in same if merged[index] == item), None)
        drop: list[int] = []
        if identical is not None:
            drop = [index for index in ours if index != identical]
        elif ours:
            merged[ours[0]] = item
            mine.add(value_hash(item))
            drop = ours[1:]
        elif same:
            if force:
                # Take the user's copy and any further same-key copies.
                merged[same[0]] = item
                mine.add(value_hash(item))
                drop = same[1:]
            else:
                conflicts.append(key)
        else:
            merged.append(item)
            mine.add(value_hash(item))
        merged = [existing for index, existing in enumerate(merged) if index not in drop]
    present = {value_hash(item) for item in merged}
    return merged, sorted(digest for digest in mine if digest in present), conflicts


def plan_keyed_list_removal(
    rule: Rule,
    current: list[Any],
    source_items: list[Any],
    owned: list[str],
    force: bool,
    retained: Mapping[str, str],
    value_hash: Hasher,
) -> tuple[list[Any], list[str], list[str | None], list[tuple[str, str]]]:
    """Take back keyed items this tool added, limited to the rule's selection.

    Owned items are removed; ``force`` also removes items sharing a repo item's
    key. A repo-keyed item the user wrote is a conflict. Items whose key is in
    ``retained`` (a marketplace still in use) stay. Returns kept items, owned
    hashes still present, conflict keys (``None`` for an unkeyed item) and
    ``(key, user)`` retention notes.
    """
    chosen = selection(rule)
    source_keys = {key for item in source_items if (key := item_key(rule, item)) is not None}
    mine = set(owned)
    kept: list[Any] = []
    conflicts: list[str | None] = []
    notes: list[tuple[str, str]] = []
    for item in current:
        key = item_key(rule, item)
        if chosen is not None and (key is None or key not in chosen):
            kept.append(item)
            continue
        repo_item = item in source_items or (key is not None and key in source_keys)
        takes = value_hash(item) in mine or (force and repo_item)
        if key is not None and key in retained and (takes or repo_item):
            kept.append(item)
            notes.append((key, retained[key]))
            continue
        if takes:
            continue
        kept.append(item)
        if repo_item:
            conflicts.append(key)
    present = {value_hash(item) for item in kept}
    return kept, sorted(digest for digest in mine if digest in present), conflicts, notes


def retained_marketplaces(
    profile: dict[str, Any], groups: list[str], destination: dict[str, Any], removing: set[tuple[str, ...]]
) -> dict[str, str]:
    """Marketplaces still used by a destination plugin that is not being removed.

    Maps each marketplace to the first such plugin (destination order). Only
    groups with a derived rule count, and only their primary map rules.
    """
    in_use: dict[str, str] = {}
    for group in groups:
        rules = profile["groups"].get(group, [])
        if not any(is_derived(rule) for rule in rules):
            continue
        for rule in rules:
            if is_derived(rule) or rule["policy"] not in ENTRY_POLICIES:
                continue
            container = _value(destination, rule["path"])
            if not isinstance(container, dict):
                continue
            for name in container:
                market = marketplace_of(str(name))
                if market is not None and (*rule["path"], name) not in removing:
                    in_use.setdefault(market, str(name))
    return in_use
