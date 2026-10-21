"""Secret-literal audit for MCP configurations, shared by the native package generators.

A credential-like key (``authorization`` or a name containing one of SECRET_KEY_TOKENS)
must hold exactly one ``${VAR}`` placeholder, optionally behind a Bearer/Basic/Token
scheme. The audit never expands environment variables: generated files keep the
placeholder bytes verbatim.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

SECRET_KEY_TOKENS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "auth",
    "bearer",
    "credential",
)
AUTH_SCHEMES = frozenset({"bearer", "basic", "token"})
PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def load_mcp_config(content: bytes | str, where: str) -> dict[str, Any]:
    """Parse an MCP configuration strictly: duplicate keys and a missing mcpServers object fail."""
    try:
        config = json.loads(content, object_pairs_hook=_unique_object)
    except ValueError as exc:
        raise ValueError(f"{where}: invalid JSON: {exc}") from exc
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers"), dict):
        raise ValueError(f"{where}: missing mcpServers object")
    return config


def _scalar_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _scalar_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _scalar_strings(child)


def _audit_credential(value: str, where: str, path: str, key: str) -> None:
    """A credential may be one exact ${VAR}, or an auth scheme plus one ${VAR}."""
    scheme, separator, rest = value.partition(" ")
    remainder = rest if scheme.lower() in AUTH_SCHEMES and separator else value
    if remainder and PLACEHOLDER.fullmatch(remainder) is None:
        raise ValueError(f"{where}: {path}.{key} looks like a secret literal; use a ${{VAR}} placeholder")


def audit_no_secret_literals(config: dict[str, Any], where: str) -> None:
    """Reject literal credential material in an MCP configuration."""

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                name = key.lower().replace("-", "_")
                if isinstance(child, str) and (
                    name == "authorization" or any(token in name for token in SECRET_KEY_TOKENS)
                ):
                    _audit_credential(child, where, path, key)
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(config, "$")


def collect_variables(config: dict[str, Any]) -> list[str]:
    """Names of ${VAR} placeholders in the MCP config, in first-seen order."""
    names: list[str] = []
    for value in _scalar_strings(config):
        for match in PLACEHOLDER.finditer(value):
            if match.group(1) not in names:
                names.append(match.group(1))
    return names
