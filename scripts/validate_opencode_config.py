#!/usr/bin/env python3
"""
Assert .opencode-plugin/opencode.json is valid, V2-only OpenCode configuration.

OpenCode still serves the V1 JSON Schema from https://opencode.ai/config.json
(it describes `provider`, `agent`, `permission`, `plugin` and a flat `mcp`),
so that document cannot be used to validate a V2 file. This module encodes the
V2 shapes documented at https://opencode.ai/v2/docs/config and its linked
topic guides instead.

The bundle targets V2 exclusively. V1 keys are rejected by name with the V2
replacement rather than being silently accepted, because OpenCode's V1
compatibility layer would otherwise hide the mistake until runtime.

Usage:
    python3 scripts/validate_opencode_config.py <path-to-opencode.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from opencode_v2_agent_schema import validate_agent_schema, validate_permission_rules

EXPECTED_SCHEMA = "https://opencode.ai/config.json"

# Top-level keys documented for V2 (opencode.ai/v2/docs/config).
V2_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "$schema",
        "agents",
        "commands",
        "compaction",
        "default_agent",
        "experimental",
        "formatter",
        "lsp",
        "mcp",
        "media",
        "model",
        "permissions",
        "plugins",
        "providers",
        "references",
        "share",
        "shell",
        "skills",
        "snapshots",
        "tool_output",
        "update",
        "username",
        "warming",
        "watcher",
        "websearch",
        "worktree",
    }
)

# V1 keys and the V2 field that replaces them.
V1_TOP_LEVEL_RENAMES: dict[str, str] = {
    "agent": "agents",
    "autoshare": "share",
    "autoupdate": "update",
    "layout": "(removed in V2)",
    "mode": "agents",
    "permission": "permissions",
    "plugin": "plugins",
    "provider": "providers",
    "reference": "references",
    "snapshot": "snapshots",
    "tools": "permissions",
}

# Keys V2 accepts that the generated bundle must not carry. V2 resolves
# `instructions`, but the bundle omits it on purpose.
BUNDLE_FORBIDDEN_TOP_LEVEL_KEYS: dict[str, str] = {
    "instructions": (
        "bundle rules install as the global ~/.config/opencode/AGENTS.md, which V2 loads first; "
        "a relative entry such as AGENTS.md resolves from the workspace and loads the project AGENTS.md again"
    ),
}

V2_PROVIDER_KEYS: frozenset[str] = frozenset(
    {"name", "env", "package", "canonical", "settings", "headers", "body", "models"}
)

V1_PROVIDER_RENAMES: dict[str, str] = {
    "npm": "package",
    "options": "settings",
    "api": "settings.baseURL",
    "id": "the providers key itself",
    "whitelist": "models",
    "blacklist": "models[*].disabled",
}

V2_MODEL_KEYS: frozenset[str] = frozenset(
    {
        "modelID",
        "name",
        "family",
        "package",
        "settings",
        "headers",
        "body",
        "capabilities",
        "compatibility",
        "variants",
        "cost",
        "limit",
        "disabled",
    }
)

V1_MODEL_RENAMES: dict[str, str] = {
    "id": "modelID",
    "modalities": "capabilities",
    "attachment": "capabilities.input",
    "reasoning": "settings.reasoningEffort",
    "tool_call": "capabilities.tools",
    "options": "settings",
    "release_date": "(removed in V2)",
    "interleaved": "compatibility.reasoningField",
    "experimental": "(removed in V2)",
    "provider": "package",
}

V2_MCP_KEYS: frozenset[str] = frozenset({"servers", "timeout"})
V2_MCP_LOCAL_KEYS: frozenset[str] = frozenset(
    {"type", "command", "cwd", "environment", "disabled", "codemode", "timeout", "protocol"}
)
V2_MCP_REMOTE_KEYS: frozenset[str] = frozenset(
    {"type", "url", "headers", "oauth", "disabled", "codemode", "timeout", "protocol"}
)

# opencode expands {env:NAME}; a shell-style ${NAME} stays a literal string.
SHELL_PLACEHOLDER = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}|(?<![{\w])\$[A-Za-z_][A-Za-z0-9_]*")

MODEL_REFERENCE = re.compile(r"^(?P<provider>[^/#]+)/(?P<model>[^#]+)(?:#(?P<variant>.+))?$")


class ConfigErrors:
    """Accumulates validation failures so one run reports every problem."""

    def __init__(self) -> None:
        self._messages: list[str] = []

    def add(self, message: str) -> None:
        self._messages.append(message)

    def check_keys(self, where: str, payload: dict[str, Any], allowed: frozenset[str], renames: dict[str, str]) -> None:
        for key in payload:
            if key in renames:
                self.add(f"{where}.{key} is V1; use {renames[key]}")
            elif key not in allowed:
                self.add(f"{where}.{key} is not a documented V2 field")

    @property
    def messages(self) -> list[str]:
        return self._messages


def declared_variants(providers: dict[str, Any], provider: str, model: str) -> set[str] | None:
    """Return variant IDs declared for a model, or None when not locally declared.

    A model the bundle does not declare comes from the provider's own catalog,
    whose variants cannot be verified offline.
    """
    entry = providers.get(provider)
    if not isinstance(entry, dict):
        return None
    models = entry.get("models")
    if not isinstance(models, dict) or model not in models:
        return None
    model_entry = models[model]
    if not isinstance(model_entry, dict):
        return None
    variants = model_entry.get("variants")
    if not isinstance(variants, list):
        return set()
    return {str(item["id"]) for item in variants if isinstance(item, dict) and "id" in item}


def validate_model_reference(
    errors: ConfigErrors,
    where: str,
    value: Any,
    providers: dict[str, Any],
    *,
    allow_variant: bool,
) -> None:
    if isinstance(value, dict):
        # The expanded selector form is valid V2; its parts are self-describing.
        if "model" not in value or "providerID" not in value:
            errors.add(f"{where} object form requires providerID and model")
        return
    if not isinstance(value, str):
        errors.add(f"{where} must be a 'provider/model' string or selector object")
        return

    match = MODEL_REFERENCE.match(value)
    if not match:
        errors.add(f"{where}={value!r} is not a 'provider/model' reference")
        return

    variant = match.group("variant")
    if variant and not allow_variant:
        errors.add(f"{where}={value!r} carries #{variant}; the V2 root default does not retain a variant")
        return
    if not variant:
        return

    known = declared_variants(providers, match.group("provider"), match.group("model"))
    if known is not None and variant not in known:
        listed = ", ".join(sorted(known)) or "none"
        errors.add(f"{where}={value!r} selects an undeclared variant (declared: {listed})")


def validate_permissions(errors: ConfigErrors, where: str, value: Any) -> None:
    for message in validate_permission_rules(where, value):
        errors.add(message)


def validate_providers(errors: ConfigErrors, providers: Any) -> dict[str, Any]:
    if not isinstance(providers, dict) or not providers:
        errors.add("providers must be a non-empty object")
        return {}

    for name, entry in providers.items():
        where = f"providers.{name}"
        if not isinstance(entry, dict):
            errors.add(f"{where} must be an object")
            continue
        errors.check_keys(where, entry, V2_PROVIDER_KEYS, V1_PROVIDER_RENAMES)

        models = entry.get("models")
        if models is None:
            continue
        if not isinstance(models, dict) or not models:
            errors.add(f"{where}.models must be a non-empty object")
            continue

        for model_name, model_entry in models.items():
            model_where = f"{where}.models.{model_name}"
            if not isinstance(model_entry, dict):
                errors.add(f"{model_where} must be an object")
                continue
            errors.check_keys(model_where, model_entry, V2_MODEL_KEYS, V1_MODEL_RENAMES)
            validate_variants(errors, model_where, model_entry.get("variants"))
            validate_limit(errors, model_where, model_entry.get("limit"))

    return providers


def validate_variants(errors: ConfigErrors, where: str, variants: Any) -> None:
    if variants is None:
        return
    if not isinstance(variants, list):
        errors.add(f"{where}.variants must be a list of objects, each with an id")
        return
    seen: set[str] = set()
    for index, variant in enumerate(variants):
        label = f"{where}.variants[{index}]"
        if not isinstance(variant, dict):
            errors.add(f"{label} must be an object")
            continue
        identifier = variant.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.add(f"{label}.id must be a non-empty string")
            continue
        if identifier in seen:
            errors.add(f"{label}.id={identifier!r} is declared twice")
        seen.add(identifier)
        extra = set(variant) - {"id", "settings", "headers", "body", "disabled"}
        if extra:
            errors.add(f"{label} has unexpected fields: {', '.join(sorted(extra))}")


def validate_limit(errors: ConfigErrors, where: str, limit: Any) -> None:
    if limit is None:
        return
    if not isinstance(limit, dict):
        errors.add(f"{where}.limit must be an object")
        return
    for field in ("context", "output"):
        if not isinstance(limit.get(field), int):
            errors.add(f"{where}.limit.{field} must be an integer token count")


def validate_agents(errors: ConfigErrors, agents: Any, providers: dict[str, Any]) -> None:
    if agents is None:
        return
    if not isinstance(agents, dict):
        errors.add("agents must be an object keyed by agent ID")
        return

    for name, entry in agents.items():
        where = f"agents.{name}"
        if not isinstance(entry, dict):
            errors.add(f"{where} must be an object")
            continue
        for message in validate_agent_schema(where, entry):
            errors.add(message)
        if "model" in entry:
            validate_model_reference(errors, f"{where}.model", entry["model"], providers, allow_variant=True)


def validate_plugins(errors: ConfigErrors, plugins: Any) -> None:
    if not isinstance(plugins, list):
        errors.add("plugins must be a list")
        return
    for index, plugin in enumerate(plugins):
        label = f"plugins[{index}]"
        if isinstance(plugin, str):
            if not plugin.strip():
                errors.add(f"{label} must be a non-empty specifier")
            continue
        if isinstance(plugin, dict):
            if not isinstance(plugin.get("package"), str):
                errors.add(f"{label}.package must be a string")
            extra = set(plugin) - {"package", "options"}
            if extra:
                errors.add(f"{label} has unexpected fields: {', '.join(sorted(extra))}")
            continue
        errors.add(f"{label} must be a specifier string or a {{package, options}} object")


def validate_env_placeholders(errors: ConfigErrors, where: str, values: Any) -> None:
    if not isinstance(values, dict):
        errors.add(f"{where} must be an object of string values")
        return
    for key, value in values.items():
        if not isinstance(value, str):
            errors.add(f"{where}.{key} must be a string")
            continue
        if SHELL_PLACEHOLDER.search(value):
            errors.add(f"{where}.{key} uses a shell placeholder; V2 substitutes only {{env:NAME}}")


def validate_mcp(errors: ConfigErrors, mcp: Any) -> None:
    if mcp is None:
        return
    if not isinstance(mcp, dict):
        errors.add("mcp must be an object")
        return

    stray = sorted(set(mcp) - V2_MCP_KEYS)
    if stray:
        errors.add(f"mcp.{{{', '.join(stray)}}} sit directly under mcp; V2 nests servers under mcp.servers")

    servers = mcp.get("servers")
    if servers is None:
        return
    if not isinstance(servers, dict):
        errors.add("mcp.servers must be an object keyed by server name")
        return

    for name, entry in servers.items():
        where = f"mcp.servers.{name}"
        if not isinstance(entry, dict):
            errors.add(f"{where} must be an object")
            continue

        server_type = entry.get("type")
        if server_type == "local":
            errors.check_keys(where, entry, V2_MCP_LOCAL_KEYS, {"env": "environment", "enabled": "disabled"})
            command = entry.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
                errors.add(f"{where}.command must be a non-empty list of strings")
            if "environment" in entry:
                validate_env_placeholders(errors, f"{where}.environment", entry["environment"])
        elif server_type == "remote":
            errors.check_keys(where, entry, V2_MCP_REMOTE_KEYS, {"enabled": "disabled"})
            url = entry.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                errors.add(f"{where}.url must be an absolute http(s) endpoint")
            if "headers" in entry:
                validate_env_placeholders(errors, f"{where}.headers", entry["headers"])
        else:
            errors.add(f"{where}.type must be 'local' or 'remote' (got {server_type!r})")


def validate_config(data: Any) -> list[str]:
    errors = ConfigErrors()

    if not isinstance(data, dict):
        return ["opencode.json must contain a JSON object"]

    for key in data:
        if key in V1_TOP_LEVEL_RENAMES:
            errors.add(f"{key} is V1 config; use {V1_TOP_LEVEL_RENAMES[key]}")
        elif key in BUNDLE_FORBIDDEN_TOP_LEVEL_KEYS:
            errors.add(f"{key} must not be set in the bundle: {BUNDLE_FORBIDDEN_TOP_LEVEL_KEYS[key]}")
        elif key not in V2_TOP_LEVEL_KEYS:
            errors.add(f"{key} is not a documented V2 config field")

    if data.get("$schema") != EXPECTED_SCHEMA:
        errors.add(f"$schema={data.get('$schema')!r} (expected {EXPECTED_SCHEMA!r})")

    providers = validate_providers(errors, data.get("providers"))

    if "model" in data:
        validate_model_reference(errors, "model", data["model"], providers, allow_variant=False)
    else:
        errors.add("model is required so the bundle declares a default")

    if "permissions" in data:
        validate_permissions(errors, "permissions", data["permissions"])

    validate_agents(errors, data.get("agents"), providers)
    validate_plugins(errors, data.get("plugins"))
    validate_mcp(errors, data.get("mcp"))

    return errors.messages


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_opencode_config.py <path-to-opencode.json>")

    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"validate_opencode_config: {path} not found")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"validate_opencode_config: {path} is not valid JSON: {exc}") from exc

    errors = validate_config(data)
    if errors:
        print(f"{path} is not valid OpenCode V2 configuration:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        raise SystemExit(1)

    print(f"OK: {path.name} is valid OpenCode V2 configuration.")


if __name__ == "__main__":
    main()
