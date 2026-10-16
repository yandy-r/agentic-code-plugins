"""Command-level hook pruning for merge_managed_config.py (``--prune-hook-commands``).

A Claude Code ``hooks`` event is an array of wrapper groups::

    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "..."}]}]

Plain ``--remove`` treats a whole event as one managed entry, so an event the
user extended or edited is kept untouched. Pruning instead removes only the
exact hook objects the repo source declares, leaving independent user hooks,
wrapper metadata and locally edited commands alone.

Ownership proof: the state file records the SHA-256 of the event array this
tool last applied. When it equals the hash of the *current source* event, the
source's hook objects were provably written by the installer, so exact copies
of them are installer-managed even if the user later added or edited other
entries. Without that proof (no state, or a source that changed since) the
event is left alone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HookPrune:
    """Outcome of pruning one hooks event."""

    proven: bool
    removed: int = 0
    # Hooks kept that may be edited copies of managed ones (exact managed hook
    # under changed wrapper metadata, or leftovers beside a missing managed hook).
    uncertain: int = 0
    remaining: list[Any] = field(default_factory=list)


def _wrapper_hooks(group: Any) -> list[Any] | None:
    if isinstance(group, dict) and isinstance(group.get("hooks"), list):
        return group["hooks"]
    return None


def _metadata(group: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in group.items() if key != "hooks"}


def _covers(metadata: dict[str, Any], wanted: dict[str, Any]) -> bool:
    """True when ``metadata`` carries every field of ``wanted`` unchanged."""
    return all(key in metadata and metadata[key] == value for key, value in wanted.items())


def prune_event(
    source_event: Any,
    dest_event: Any,
    state_sha: Any,
    hasher: Callable[[Any], str],
) -> HookPrune:
    """Remove exact managed hook objects from ``dest_event``.

    ``remaining`` is the pruned event array. A wrapper is only touched when its
    non-``hooks`` fields still cover a managed source wrapper's fields; it is
    dropped only when pruning emptied it and those fields are exactly the
    source wrapper's. Every other group is kept verbatim.
    """
    if (
        not isinstance(source_event, list)
        or not isinstance(dest_event, list)
        or not isinstance(state_sha, str)
        or state_sha != hasher(source_event)
    ):
        return HookPrune(proven=False)

    managed: list[tuple[dict[str, Any], list[Any]]] = []
    for group in source_event:
        hooks = _wrapper_hooks(group)
        if hooks is None:
            continue
        commands = [
            hook
            for hook in hooks
            if isinstance(hook, dict) and hook.get("type") == "command" and isinstance(hook.get("command"), str)
        ]
        if commands:
            managed.append((_metadata(group), commands))
    if not managed:
        return HookPrune(proven=False)
    all_managed = [hook for _, hooks in managed for hook in hooks]
    present = [hook for group in dest_event if (hooks := _wrapper_hooks(group)) for hook in hooks]
    any_missing = any(hook not in present for hook in all_managed)
    result = HookPrune(proven=True)
    # The event state proves one installed occurrence per source hook, not every
    # byte-identical user copy: each source occurrence is consumed at most once.
    available = [(source_meta, hook) for source_meta, source_hooks in managed for hook in source_hooks]
    for group in dest_event:
        hooks = _wrapper_hooks(group)
        if hooks is None:
            result.remaining.append(group)
            continue
        metadata = _metadata(group)
        matching = [
            (source_meta, source_hooks) for source_meta, source_hooks in managed if _covers(metadata, source_meta)
        ]
        kept = []
        for hook in hooks:
            owner = next(
                (
                    index
                    for index, (source_meta, owned) in enumerate(available)
                    if owned == hook and _covers(metadata, source_meta)
                ),
                None,
            )
            if owner is None:
                kept.append(hook)
            else:
                available.pop(owner)
        result.removed += len(hooks) - len(kept)
        result.uncertain += sum(1 for hook in kept if hook in all_managed)
        if any_missing:
            result.uncertain += sum(1 for hook in kept if hook not in all_managed)
        emptied = bool(hooks) and not kept
        if emptied and any(source_meta == metadata for source_meta, _ in matching):
            continue
        result.remaining.append(group if len(kept) == len(hooks) else {**group, "hooks": kept})
    return result
