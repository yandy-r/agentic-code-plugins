#!/usr/bin/env python3
"""
Generate opencode-native agents under .opencode-plugin/agents from ycc/agents.

opencode reads agents from <workspace>/.opencode/agents/<name>.md or
~/.config/opencode/agents/<name>.md. The filename stem becomes the agent
name; ``name`` in frontmatter is not required (and is dropped here).

Authoritative opencode agent frontmatter (per opencode.ai/v2/docs/agents):
    description (required), mode, model, system, permissions, steps, hidden,
    color, disabled, request.

This generator performs:
1. Strips `name` / `title` / unknown Claude-specific fields.
2. Drops `model` entirely (see below).
3. Converts Claude tool allowlists to ordered OpenCode V2 `permissions` rules.
   Agents listed in ycc/settings/sensitive-files.json additionally get native
   `read`/`edit` denies for sensitive paths, appended last. The guard plugin
   that enforces the same policy on every tool call is written beside the
   agents as .opencode-plugin/ycc-sensitive-guard, so the two always ship
   together.
4. Rewrites body text with opencode-native phrasing via
   apply_opencode_text_transforms.
5. Normalizes Claude color names to opencode-valid hex colors.

Model policy
------------
These files describe agent *behavior* and must stay provider-agnostic. Pinning
`model:` here would hard-code one provider into 50+ generated files, so every
user whose catalog differs (a different gateway, local models, another vendor)
would have to edit the whole tree. OpenCode falls back to the parent session's
model when the field is absent, and a user who wants a specific model or effort
for one agent sets it in `opencode.json` under `agents.<id>.model`, which merges
with these definitions by agent ID.

Source of truth: ycc/agents/*.md.
"""

from __future__ import annotations

import argparse
import filecmp
import re
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

from generate_opencode_common import (
    OPENCODE_AGENTS_DIR,
    SRC_AGENTS_DIR,
    apply_opencode_text_transforms,
    dump_frontmatter,
    load_agent_aliases,
    normalize_agent_color,
    parse_frontmatter,
)
from generate_opencode_dispatch import (
    project_opencode_dispatch,
    project_opencode_dispatch_description,
)
from opencode_sensitive_policy import (
    GUARD_DIR,
    GUARDED_SEARCH_TOOLS,
    SensitivePolicy,
    guard_drift,
    load_policy,
    native_sensitive_rules,
    write_guard,
)

PermissionRule = dict[str, str]

NATIVE_ACTIONS: dict[str, str] = {
    "read": "read",
    "notebookread": "read",
    "write": "edit",
    "edit": "edit",
    "multiedit": "edit",
    "notebookedit": "edit",
    "grep": "grep",
    "glob": "glob",
    "ls": "glob",
    "bash": "shell",
    "shell": "shell",
    "webfetch": "webfetch",
    "websearch": "websearch",
    "task": "subagent",
    "agent": "subagent",
    "subagent": "subagent",
    "askuserquestion": "question",
    "question": "question",
}

IGNORED_TOOLS: frozenset[str] = frozenset(
    {
        "bashoutput",
        "exitplanmode",
        "killbash",
        "sendmessage",
        "slashcommand",
        "taskcreate",
        "taskget",
        "tasklist",
        "taskupdate",
        "teamcreate",
        "teamdelete",
        "todowrite",
    }
)

DENY_ALL: PermissionRule = {"action": "*", "resource": "*", "effect": "deny"}
EXTERNAL_DIRECTORY_ASK: PermissionRule = {
    "action": "external_directory",
    "resource": "*",
    "effect": "ask",
}
FILESYSTEM_ACTIONS: frozenset[str] = frozenset(
    {"read", "edit", "glob", "grep", "shell", *GUARDED_SEARCH_TOOLS.values()}
)
# These restore OpenCode's sensitive-file defaults for the `read` action only.
# Agents in the sensitive-file registry replace them with path denies; other
# discovery actions retain their native V2 semantics and are emitted only
# when the canonical source agent explicitly requests them.
SENSITIVE_READ_GUARDS: tuple[PermissionRule, ...] = (
    {"action": "read", "resource": "*.env", "effect": "ask"},
    {"action": "read", "resource": "*.env.*", "effect": "ask"},
    {"action": "read", "resource": "*.env.example", "effect": "allow"},
)
SKILL_REFERENCE = re.compile(r"\bskill:\s*([a-z][a-z0-9-]*)", re.IGNORECASE)


def _split_tool_specs(value: str) -> list[str]:
    """Split a comma-delimited Claude tool list without splitting scopes."""
    specs: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(f"unbalanced tool scope: {value!r}")
        elif character == "," and depth == 0:
            if spec := value[start:index].strip():
                specs.append(spec)
            start = index + 1
    if depth != 0:
        raise ValueError(f"unbalanced tool scope: {value!r}")
    if spec := value[start:].strip():
        specs.append(spec)
    return specs


def _enabled_tool_specs(value: object) -> list[str]:
    """Return enabled Claude tool specifications from every supported form."""
    if isinstance(value, str):
        return _split_tool_specs(value)
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise ValueError("tools list entries must be strings")
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        specs: list[str] = []
        for key, enabled in value.items():
            if not isinstance(key, str) or not isinstance(enabled, bool):
                raise ValueError("tools mapping must use string keys and boolean values")
            if enabled:
                specs.append(key)
        return specs
    raise ValueError("tools must be a string, list, or boolean mapping")


def _normalize_mcp_action(tool_name: str) -> str:
    """Translate a Claude MCP tool identifier to an OpenCode action pattern."""
    server, separator, tool = tool_name.removeprefix("mcp__").partition("__")
    if not separator or not server or not tool:
        raise ValueError(f"invalid Claude MCP tool name: {tool_name!r}")

    def normalize_component(component: str) -> str:
        # OpenCode keeps case, hyphens, and underscores in MCP action names.
        # Wildcards are permission selectors rather than literal tool-name
        # characters, so preserve them while sanitizing the remaining input.
        return re.sub(r"[^a-zA-Z0-9_*?-]", "_", component)

    return f"{normalize_component(server)}_{normalize_component(tool)}"


def _shell_resource(scope: str) -> str:
    """Translate Claude's command:arguments scope into raw shell text."""
    command, separator, arguments = scope.partition(":")
    command = command.strip()
    arguments = arguments.strip()
    if not command:
        raise ValueError(f"empty Bash scope: {scope!r}")
    if command.startswith("git -C * "):
        # OpenCode has a separate workdir input, so represent scoped Git
        # commands by their native subcommand resources.
        command = f"git {command.removeprefix('git -C * ')}"
    if not separator:
        return command
    return f"{command} {arguments}".rstrip()


def _rules_for_tool(spec: str) -> list[PermissionRule]:
    """Return native OpenCode allow rules for one Claude tool specification."""
    head = spec.split("(", 1)[0].strip()
    if not head:
        raise ValueError("tool names must not be empty")
    normalized_head = head.casefold()
    if normalized_head in IGNORED_TOOLS:
        return []
    has_scope = "(" in spec or ")" in spec
    if has_scope and normalized_head != "bash":
        raise ValueError(f"only Bash scopes can be translated without widening access: {spec!r}")
    if normalized_head == "bash" and has_scope:
        if not spec.endswith(")"):
            raise ValueError(f"unbalanced Bash scope: {spec!r}")
        scope = spec.split("(", 1)[1][:-1].strip()
        if not scope:
            raise ValueError(f"empty Bash scope: {spec!r}")
        return [{"action": "shell", "resource": _shell_resource(scope), "effect": "allow"}]

    action = NATIVE_ACTIONS.get(normalized_head)
    if action is None:
        action = _normalize_mcp_action(head) if head.startswith("mcp__") else head.lower()
    return [{"action": action, "resource": "*", "effect": "allow"}]


def _referenced_skill_ids(body: str) -> list[str]:
    """Return bundle skill IDs explicitly referenced by an agent prompt."""
    skill_ids: list[str] = []
    for match in SKILL_REFERENCE.finditer(body):
        skill_id = match.group(1).lower()
        if skill_id not in skill_ids:
            skill_ids.append(skill_id)
    return skill_ids


def _apply_agent_specific_text_transforms(stem: str, body: str) -> str:
    """Adapt prompts whose safe tool invocation differs on OpenCode."""
    if stem != "backport-conflict-resolver":
        return body

    body = body.replace(
        "In `WORKTREE`, read the source change:",
        "Read the source change with each shell call's `workdir` set to `WORKTREE`:",
    )
    return body.replace("git -C <WORKTREE>", "git")


def convert_tools_to_permissions(
    value: object,
    *,
    skill_ids: Iterable[str] = (),
    sensitive_policy: SensitivePolicy | None = None,
) -> list[PermissionRule]:
    """Translate a Claude tool allowlist to ordered OpenCode V2 rules.

    With ``sensitive_policy`` the agent is restricted: its sensitive-path
    denies for `read`/`edit` are appended last so no earlier allow (and no
    host default) can override them, and `grep`/`glob` are granted as the
    guard's own search tools (GUARDED_SEARCH_TOOLS), so the agent has no
    search tool when the guard is not loaded.
    """
    permissions: list[PermissionRule] = [DENY_ALL.copy()]
    seen: set[tuple[str, str, str]] = {("*", "*", "deny")}
    for spec in _enabled_tool_specs(value):
        for rule in _rules_for_tool(spec):
            if sensitive_policy is not None:
                rule["action"] = GUARDED_SEARCH_TOOLS.get(rule["action"], rule["action"])
            key = (rule["action"], rule["resource"], rule["effect"])
            if key not in seen:
                permissions.append(rule)
                seen.add(key)

    for skill_id in skill_ids:
        rule = {"action": "skill", "resource": skill_id, "effect": "allow"}
        key = (rule["action"], rule["resource"], rule["effect"])
        if key not in seen:
            permissions.append(rule)
            seen.add(key)

    allowed_actions = {rule["action"] for rule in permissions if rule["effect"] == "allow"}
    if allowed_actions & FILESYSTEM_ACTIONS:
        permissions.append(EXTERNAL_DIRECTORY_ASK.copy())
    if sensitive_policy is not None:
        permissions.extend(native_sensitive_rules(allowed_actions, sensitive_policy))
    elif "read" in allowed_actions:
        permissions.extend(rule.copy() for rule in SENSITIVE_READ_GUARDS)
    return permissions


def transform_agent(stem: str, raw: str, aliases: dict[str, str], policy: SensitivePolicy | None = None) -> str:
    """Translate one canonical Claude agent into OpenCode Markdown."""
    frontmatter, body = parse_frontmatter(raw)

    # Description is required by opencode. Fall back to the filename stem as a
    # last-resort placeholder so the generator never emits a frontmatter
    # missing the required field — a validator flags empty descriptions.
    description = str(frontmatter.get("description") or "").strip()
    transformed_description = apply_opencode_text_transforms(description, aliases).strip()
    transformed_description = project_opencode_dispatch_description(transformed_description)
    if not transformed_description:
        transformed_description = f"{stem} agent"

    payload: dict[str, object] = {
        "description": transformed_description,
        # Every generated ycc specialist is launched through the subagent tool.
        # OpenCode V2 defaults custom agents to `primary` when mode is omitted.
        "mode": "subagent",
    }

    # `model` is deliberately never emitted. These agent files define behavior,
    # not runtime model policy: a pinned `provider/model` would hard-code one
    # provider into 50+ portable files and break every user whose catalog
    # differs. OpenCode falls back to the parent session's model when the field
    # is absent, and per-machine overrides belong in opencode.json's `agents`
    # block, which merges with these definitions by agent ID.

    if "tools" in frontmatter:
        policy = load_policy() if policy is None else policy
        payload["permissions"] = convert_tools_to_permissions(
            frontmatter["tools"],
            skill_ids=_referenced_skill_ids(body),
            sensitive_policy=policy if stem in policy.restricted_agents else None,
        )

    raw_color = frontmatter.get("color")
    if raw_color not in (None, "", []):
        color = normalize_agent_color(raw_color)
        if color:
            payload["color"] = color
        else:
            print(
                f"generate_opencode_agents: WARN unmapped color '{raw_color}' on {stem}.md — dropping color field",
                file=sys.stderr,
            )

    for passthrough in ("steps", "hidden", "disabled", "request"):
        if passthrough in frontmatter and frontmatter[passthrough] not in (None, "", []):
            payload[passthrough] = frontmatter[passthrough]
    if "disabled" not in payload and "disable" in frontmatter:
        payload["disabled"] = bool(frontmatter["disable"])

    transformed_body = apply_opencode_text_transforms(body, aliases)
    transformed_body = _apply_agent_specific_text_transforms(stem, transformed_body)
    transformed_body = project_opencode_dispatch(transformed_body, f"agents/{stem}.md")
    return dump_frontmatter(payload) + transformed_body


def write_all(dest: Path, dry_run: bool) -> set[Path]:
    """Generate every canonical agent under ``dest`` and return its paths."""
    aliases = load_agent_aliases()
    policy = load_policy()
    written: set[Path] = set()

    for src in sorted(SRC_AGENTS_DIR.glob("*.md")):
        stem = src.stem
        output = transform_agent(stem, src.read_text(encoding="utf-8"), aliases, policy)
        target = dest / f"{stem}.md"
        written.add(target.relative_to(dest))
        if dry_run:
            print(f"Would write {target.relative_to(dest)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")

    if not dry_run:
        existing = sorted(dest.glob("*.md"))
        for path in existing:
            if path.relative_to(dest) not in written:
                path.unlink()
    return written


def compare_trees(generated: Path, repo_dest: Path) -> list[str]:
    """Return generated/committed tree drift descriptions."""
    gen_files = {path.relative_to(generated) for path in generated.glob("*.md")}
    repo_files = {path.relative_to(repo_dest) for path in repo_dest.glob("*.md")} if repo_dest.is_dir() else set()

    diffs: list[str] = []
    for rel in sorted(gen_files | repo_files):
        if rel not in repo_files:
            diffs.append(f"missing in repo: {rel}")
            continue
        if rel not in gen_files:
            diffs.append(f"extra in repo: {rel}")
            continue
        if not filecmp.cmp(generated / rel, repo_dest / rel, shallow=False):
            diffs.append(f"drift: {rel}")
    return diffs


def run_check() -> int:
    """Return nonzero when committed OpenCode agents differ from generation."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        write_all(temp_root, dry_run=False)
        diffs = compare_trees(temp_root, OPENCODE_AGENTS_DIR) + guard_drift()
        if diffs:
            print(
                "opencode agents are out of date. Run: ./scripts/generate-opencode-agents.sh",
                file=sys.stderr,
            )
            for diff in diffs:
                print(f"  {diff}", file=sys.stderr)
            return 1
    return 0


def main() -> None:
    """Run OpenCode agent generation or drift checking from CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if generated output drifts")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written")
    args = parser.parse_args()

    if args.check:
        if not OPENCODE_AGENTS_DIR.is_dir():
            print(
                f"Missing {OPENCODE_AGENTS_DIR}; run generator without --check first.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(run_check())

    if args.dry_run:
        write_all(OPENCODE_AGENTS_DIR, dry_run=True)
        write_guard(GUARD_DIR, dry_run=True)
        return

    OPENCODE_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    write_all(OPENCODE_AGENTS_DIR, dry_run=False)
    write_guard(GUARD_DIR, dry_run=False)
    count = sum(1 for _ in OPENCODE_AGENTS_DIR.glob("*.md"))
    print(f"Wrote {count} files under {OPENCODE_AGENTS_DIR} and the guard plugin under {GUARD_DIR}")


if __name__ == "__main__":
    main()
