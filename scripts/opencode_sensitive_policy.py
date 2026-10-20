#!/usr/bin/env python3
"""Sensitive-file policy for restricted ycc OpenCode V2 specialists.

Source of truth: ``ycc/settings/sensitive-files.json``. It names the agents
whose prompt contract forbids secret-bearing files and the path patterns that
count as sensitive. Two consumers read it:

- ``generate_opencode_agents.py`` appends native ``read``/``edit`` deny rules
  to each restricted agent's ``permissions`` (OpenCode evaluates the last
  matching rule, so these come last).
- The ycc sensitive-file guard plugin (``opencode_templates/sensitive-guard.js``)
  ships beside a copy of the registry and enforces the same patterns, with
  symlink resolution, on read/edit/write/patch/grep/glob/shell tool calls.

Pattern forms (all relative, no leading ``/`` or ``~``):

- ``name`` without ``/``: a file basename glob (``*`` stays within one segment).
- ``dir/``: every path that has a segment named ``dir``.
- ``a/b``: every path that ends with the segments ``a/b``.

``allow`` holds basename globs that override basename patterns only; a file
under a sensitive directory stays denied.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from generate_opencode_common import OPENCODE_PLUGIN_ROOT, REPO_ROOT, SRC_AGENTS_DIR

PermissionRule = dict[str, str]

POLICY_PATH = REPO_ROOT / "ycc" / "settings" / "sensitive-files.json"
GUARD_TEMPLATE_PATH = Path(__file__).resolve().parent / "opencode_templates" / "sensitive-guard.js"
# The guard is its own bundle unit (.opencode-plugin/ycc-sensitive-guard,
# installed as ~/.config/opencode/ycc-sensitive-guard). It ships with the
# agents it protects, so consolidating skills into ~/.agents/skills never drops
# it. OpenCode resolves a `./` plugins entry from the directory of the
# opencode.json that declares it and loads the directory's package.json entry.
GUARD_DIRNAME = "ycc-sensitive-guard"
GUARD_DIR = OPENCODE_PLUGIN_ROOT / GUARD_DIRNAME
GUARD_PLUGIN_SPEC = f"./{GUARD_DIRNAME}"

_KEYS = frozenset({"restricted_agents", "patterns", "allow"})
_PATTERN = re.compile(r"^[A-Za-z0-9._*-]+(?:/[A-Za-z0-9._-]+)*/?$")
_GUARDED_ACTIONS = ("read", "edit")


@dataclass(frozen=True)
class SensitivePolicy:
    """Validated sensitive-file registry."""

    restricted_agents: tuple[str, ...]
    patterns: tuple[str, ...]
    allow: tuple[str, ...]


def _string_list(data: dict[str, object], key: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{path}: {key} must be a non-empty list of non-empty strings")
    items = tuple(str(item) for item in value)
    if len(set(items)) != len(items):
        raise ValueError(f"{path}: {key} has duplicate entries")
    return items


def _validate_pattern(pattern: str, path: Path, *, basename_only: bool) -> None:
    if not _PATTERN.fullmatch(pattern) or "**" in pattern or pattern in {".", ".."}:
        raise ValueError(f"{path}: invalid sensitive-file pattern {pattern!r}")
    if "/" in pattern and ("*" in pattern or basename_only):
        raise ValueError(f"{path}: path patterns must be literal segments: {pattern!r}")


def load_policy(path: Path = POLICY_PATH, agents_dir: Path = SRC_AGENTS_DIR) -> SensitivePolicy:
    """Load and validate the registry; unknown agents fail fast."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise ValueError(f"{path}: expected exactly the keys {sorted(_KEYS)}")
    agents = _string_list(data, "restricted_agents", path)
    patterns = _string_list(data, "patterns", path)
    allow = _string_list(data, "allow", path)
    for pattern in patterns:
        _validate_pattern(pattern, path, basename_only=False)
    for pattern in allow:
        _validate_pattern(pattern, path, basename_only=True)
    missing = sorted(agent for agent in agents if not (agents_dir / f"{agent}.md").is_file())
    if missing:
        raise ValueError(f"{path}: restricted agents not found in {agents_dir}: {', '.join(missing)}")
    return SensitivePolicy(restricted_agents=agents, patterns=patterns, allow=allow)


def _native_resources(pattern: str) -> list[str]:
    """OpenCode wildcard resources for one pattern (`*` also matches `/`)."""
    if pattern.endswith("/"):
        name = pattern.rstrip("/")
        return [name, f"{name}/*", f"*/{name}", f"*/{name}/*"]
    if pattern.startswith("*"):
        return [pattern]
    return [pattern, f"*/{pattern}"]


# Shell commands no restricted agent may run: `git diff --no-index` compares
# arbitrary paths, including gitignored secret files.
SHELL_DENIES = ("git diff *--no-index*",)


def native_sensitive_rules(actions: set[str], policy: SensitivePolicy) -> list[PermissionRule]:
    """Ordered rules appended last to a restricted agent's permissions.

    The .env-family basename denies come first, then the allow exceptions
    (`*.env.example`), then every other basename deny and the directory and
    path-suffix denies, so an allowed name that is also a key file or sits under
    a sensitive directory stays denied (OpenCode uses the last matching rule).
    A restricted agent that may run shell commands also gets SHELL_DENIES.
    """
    guarded = [action for action in _GUARDED_ACTIONS if action in actions]
    env_names = [pattern for pattern in policy.patterns if "/" not in pattern and pattern.startswith(".env")]
    later = [pattern for pattern in policy.patterns if pattern not in env_names]

    def rules(patterns: list[str], effect: str) -> list[PermissionRule]:
        return [
            {"action": action, "resource": resource, "effect": effect}
            for action in guarded
            for pattern in patterns
            for resource in _native_resources(pattern)
        ]

    shell = [
        {"action": "shell", "resource": resource, "effect": "deny"} for resource in SHELL_DENIES if "shell" in actions
    ]
    return [*rules(env_names, "deny"), *rules(list(policy.allow), "allow"), *rules(later, "deny"), *shell]


def guard_payloads(policy_path: Path = POLICY_PATH) -> dict[Path, bytes]:
    """Files of the guard plugin directory, relative to that directory."""
    load_policy(policy_path)
    manifest = {
        "name": GUARD_DIRNAME,
        "private": True,
        "type": "module",
        "main": "index.js",
        "description": "ycc sensitive-file guard for restricted OpenCode V2 specialists.",
    }
    return {
        Path("index.js"): GUARD_TEMPLATE_PATH.read_bytes(),
        Path("policy.json"): policy_path.read_bytes(),
        Path("package.json"): (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
    }


def write_guard(dest: Path, dry_run: bool) -> set[Path]:
    """Write the guard plugin directory at ``dest`` and prune stray files."""
    payloads = guard_payloads()
    for rel, content in payloads.items():
        out = dest / rel
        if dry_run:
            print(f"Would write {out}")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.is_file() or out.read_bytes() != content:
            out.write_bytes(content)
    if not dry_run and dest.is_dir():
        for path in sorted(dest.rglob("*"), key=lambda path: len(path.parts), reverse=True):
            if path.is_file() or path.is_symlink():
                if path.relative_to(dest) not in payloads:
                    path.unlink()
            elif not any(path.iterdir()):
                path.rmdir()
    return set(payloads)


def guard_drift(dest: Path = GUARD_DIR) -> list[str]:
    """Differences between the committed guard directory and generation."""
    payloads = guard_payloads()
    present = {path.relative_to(dest) for path in dest.rglob("*") if path.is_file()} if dest.is_dir() else set()
    diffs = [f"missing in repo: {GUARD_DIRNAME}/{rel}" for rel in sorted(set(payloads) - present)]
    diffs += [f"extra in repo: {GUARD_DIRNAME}/{rel}" for rel in sorted(present - set(payloads))]
    diffs += [
        f"drift: {GUARD_DIRNAME}/{rel}"
        for rel in sorted(set(payloads) & present)
        if (dest / rel).read_bytes() != payloads[rel]
    ]
    return diffs
