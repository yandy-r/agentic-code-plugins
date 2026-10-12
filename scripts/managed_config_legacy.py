"""Plan only the GitHub MCP move from known npm/remote defaults to native stdio."""

from __future__ import annotations

import re

from managed_config_entries import entry_rule_paths

ConfigValue = str | int | float | bool | None | list["ConfigValue"] | dict[str, "ConfigValue"]
MCP_PATHS = (["mcpServers"], ["mcp_servers"], ["mcp", "servers"])
REMOTE_URL = "https://api.githubcopilot.com/mcp"
PAT_KEYS = {"GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_API_TOKEN"}
CONNECTION_KEYS = ("command", "args", "type")
LEGACY_KEYS = (
    "url",
    "headers",
    "http_headers",
    "env_http_headers",
    "bearer_token_env_var",
    "oauth",
    "envFile",
)
MISSING = object()


def _entry(data: object, path: list[str]) -> object:
    for part in path:
        data = data.get(part, MISSING) if isinstance(data, dict) else MISSING
    return data


def _argv(entry: dict[str, ConfigValue]) -> list[ConfigValue] | None:
    command = entry.get("command")
    if isinstance(command, list):
        # An extra args field changes the invocation; not a known default.
        return command if not entry.get("args") else None
    args = entry.get("args", [])
    return [command, *args] if isinstance(args, list) else None


def plan_legacy_migration(
    profile: dict[str, ConfigValue],
    groups: list[str],
    source: dict[str, ConfigValue],
    destination: dict[str, ConfigValue],
    force: bool,
) -> tuple[list[tuple[list[str], ConfigValue]], list[list[str]], list[list[str]]]:
    """Return updates, deletions and custom entries to leave entirely untouched.

    Selection already filters source. Only a native stdio source enables this
    exception to normal leaf ownership; --force explicitly opts custom entries in.
    """
    updates: list[tuple[list[str], ConfigValue]] = []
    deletions: list[list[str]] = []
    preserved: list[list[str]] = []
    for container in entry_rule_paths(profile, groups):
        if container not in MCP_PATHS:
            continue
        base = [*container, "github"]
        wanted = _entry(source, base)
        current = _entry(destination, base)
        if not isinstance(wanted, dict) or _argv(wanted) != ["github-mcp-server", "stdio"]:
            continue
        if current is MISSING:
            continue
        if not isinstance(current, dict):
            if not force:
                preserved.append(base)
            continue
        argv = _argv(current)
        npm = (
            isinstance(argv, list)
            and argv[:1] == ["npx"]
            and (len(argv) == 2 or (len(argv) == 3 and argv[1] == "-y"))
            and isinstance(argv[-1], str)
            and re.fullmatch(r"@modelcontextprotocol/server-github(?:@[^\s]+)?", argv[-1]) is not None
            and "url" not in current
        )
        url = current.get("url")
        remote = (
            "command" not in current
            and "args" not in current
            and isinstance(url, str)
            and url.rstrip("/") == REMOTE_URL
        )
        if not (force or npm or remote):
            # Even matching native argv with auth/transport overrides is custom.
            env_vars = current.get("env_vars")
            auth_override = (
                any(key in current for key in LEGACY_KEYS)
                or any(
                    isinstance(current.get(key), dict) and PAT_KEYS.intersection(current[key])
                    for key in ("env", "environment")
                )
                or (isinstance(env_vars, list) and any(isinstance(name, str) and name in PAT_KEYS for name in env_vars))
            )
            if (
                argv != ["github-mcp-server", "stdio"]
                or auth_override
                or current.get("type") not in (None, "local", "stdio")
            ):
                preserved.append(base)
            continue
        updates.extend(
            ([*base, key], wanted[key]) for key in CONNECTION_KEYS if key in wanted and current.get(key) != wanted[key]
        )
        # Transport keys absent from the native shape cannot survive conversion.
        deletions.extend(
            [*base, key] for key in (*LEGACY_KEYS, *CONNECTION_KEYS) if key in current and key not in wanted
        )
        for key in ("env", "environment"):
            env = current.get(key)
            if isinstance(env, dict):
                deletions.extend([*base, key, name] for name in PAT_KEYS if name in env)
        env_vars = current.get("env_vars")
        if isinstance(env_vars, list) and any(name in PAT_KEYS for name in env_vars if isinstance(name, str)):
            kept = [name for name in env_vars if not isinstance(name, str) or name not in PAT_KEYS]
            if kept:
                updates.append(([*base, "env_vars"], kept))
            else:
                deletions.append([*base, "env_vars"])
    return updates, deletions, preserved
