#!/usr/bin/env python3
"""
Build Codex's managed MCP server set from mcp-configs/mcp.json.

mcp-configs/mcp.json is the one server list every target ships. Codex needs
its own shape (``[mcp_servers.<name>]`` in config.toml), so each server is
translated here; servers that .codex-plugin/config/config.toml defines under
``[mcp_servers.*]`` replace the translation whole (Codex-only extras such as
``bearer_token_env_var`` and per-tool ``approval_mode``).

Translation (Claude Code shape -> Codex):
- local  ``command``/``args`` kept; ``env`` values that only reference the
  same-named variable (``"X": "${X}"``) become ``env_vars`` pass-through,
  other literals stay in ``env``. ``envFile`` has no Codex equivalent.
- remote ``url`` kept, ``headers`` -> ``http_headers``; ``type`` dropped.

The result is written as JSON (``{"mcp_servers": {...}}``) for the installer's
merge helper, which patches it into the user's TOML config.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from generate_codex_common import CODEX_PLUGIN_CONTAINER, SOURCE_MCP_PATH

CODEX_CONFIG_PATH = CODEX_PLUGIN_CONTAINER / "config" / "config.toml"
CODEX_MCP_PATH = CODEX_PLUGIN_CONTAINER / "config" / "mcp-servers.json"

ENV_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class CodexMcpError(ValueError):
    """A server in mcp.json cannot be expressed in Codex's config shape."""


def translate_env(name: str, env: dict[str, str]) -> dict[str, Any]:
    """Split Claude ``env`` into Codex ``env_vars`` (pass-through) and ``env``."""
    passthrough: list[str] = []
    literal: dict[str, str] = {}
    for key, value in env.items():
        match = ENV_REFERENCE.match(str(value))
        if match and match.group(1) == key:
            passthrough.append(key)
        elif "${" in str(value):
            raise CodexMcpError(
                f"server '{name}': env {key}={value} renames a variable, which Codex cannot express; "
                f"define [mcp_servers.{name}] in {CODEX_CONFIG_PATH.name} instead"
            )
        else:
            literal[key] = value
    out: dict[str, Any] = {}
    if passthrough:
        out["env_vars"] = passthrough
    if literal:
        out["env"] = literal
    return out


def translate_server(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Translate one Claude Code MCP server entry to Codex's shape."""
    if "url" in raw:
        entry: dict[str, Any] = {"url": raw["url"]}
        if raw.get("headers"):
            entry["http_headers"] = raw["headers"]
        return entry
    if not isinstance(raw.get("command"), str):
        raise CodexMcpError(f"server '{name}': needs a 'url' or a string 'command'")
    entry = {"command": raw["command"]}
    if raw.get("args"):
        entry["args"] = list(raw["args"])
    entry.update(translate_env(name, raw.get("env") or {}))
    return entry


def build_codex_mcp_servers(source: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Every source server, in source order, with Codex overrides applied by name."""
    servers: dict[str, Any] = {}
    for name, raw in source.items():
        servers[name] = overrides[name] if name in overrides else translate_server(name, raw)
    for name, override in overrides.items():
        servers.setdefault(name, override)
    return servers


def build_codex_mcp_config() -> dict[str, Any]:
    source = json.loads(SOURCE_MCP_PATH.read_text(encoding="utf-8")).get("mcpServers", {})
    overrides = tomllib.loads(CODEX_CONFIG_PATH.read_text(encoding="utf-8")).get("mcp_servers", {})
    return {"mcp_servers": build_codex_mcp_servers(source, overrides)}


def write_codex_mcp_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_codex_mcp_config(), indent=2) + "\n", encoding="utf-8")
