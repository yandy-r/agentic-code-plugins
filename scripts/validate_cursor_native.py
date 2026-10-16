#!/usr/bin/env python3
"""Validate generated Cursor-native packages against the vendored schema and local-resource rules."""

from __future__ import annotations

import json
import re
import stat
import sys
from pathlib import Path

from generate_cursor_packages import (
    MIN_CURSOR_VERSION,
    OUTPUT_ROOT,
    REPO_ROOT,
    SCHEMA_DIR,
    SUPPORTED_HOOK_EVENTS,
    cursor_runtime,
    native_packages,
    native_version,
)
from jsonschema import Draft7Validator, FormatChecker
from package_model import load_package_model

ROOT_REF = re.compile(r"\$\{CURSOR_PLUGIN_ROOT\}/([^\s\"'`)>\]\\]+)")
HOME_REF = re.compile(r"(?:~|\$\{?HOME\}?)/\.cursor/([A-Za-z0-9_./-]+)")
INSTALLER_ONLY_HOME = ("agents/", "skills/", "mcp-library", "plugins/")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resource_target(ref: str) -> str:
    """Cut a reference to its literal prefix before any glob/brace/placeholder."""
    target = ref.split("#")[0].split(":")[0].rstrip(".,;/")
    literal = re.split(r"[*?[{<]", target, maxsplit=1)[0].rstrip("/")
    return literal


def resource_errors(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for ref in ROOT_REF.findall(text):
            target = _resource_target(ref)
            if not target:
                continue
            resolved = (root / target).resolve()
            if not resolved.is_relative_to(root.resolve()):
                errors.append(f"{path}: plugin reference escapes its package: {ref}")
                continue
            if resolved.exists():
                continue
            errors.append(f"{path}: unresolved ${{CURSOR_PLUGIN_ROOT}}/{target}")
        # HOME rules cover instruction-bearing files the runtime executes or
        # follows as commands (scripts, SKILL.md, agents, commands). Reference
        # docs that merely describe the file-copy installer contract are exempt.
        if not path.name.endswith((".sh", ".mdc")) and path.name not in {"SKILL.md"}:
            continue
        if "/_shared/references/" in path.as_posix():
            continue
        for ref in HOME_REF.findall(text):
            if ref.startswith(INSTALLER_ONLY_HOME):
                errors.append(f"{path}: installer-only $HOME/.cursor/{ref} cannot be the required native resource")
    return errors


def main() -> int:
    errors: list[str] = []
    model = load_package_model()
    validator = Draft7Validator(load(SCHEMA_DIR / "plugin.schema.json"), format_checker=FormatChecker())
    version = native_version(model)
    if (REPO_ROOT / ".cursor-plugin/marketplace.json").exists():
        errors.append(".cursor-plugin/marketplace.json must not exist before the listing flip")
    for package in native_packages(model.packages):
        runtime = cursor_runtime(package)
        assert runtime is not None
        root = REPO_ROOT / OUTPUT_ROOT / package.key
        manifest_path = root / ".cursor-plugin/plugin.json"
        if not manifest_path.is_file():
            errors.append(f"{manifest_path.relative_to(REPO_ROOT)}: missing")
            continue
        manifest = load(manifest_path)
        errors.extend(f"{manifest_path}: {error.message}" for error in validator.iter_errors(manifest))
        if manifest.get("name") != package.key or manifest.get("version") != version:
            errors.append(f"{manifest_path}: name/version must follow the package model")
        if manifest.get("minClientVersions") != {"cursor": MIN_CURSOR_VERSION}:
            errors.append(f"{manifest_path}: minClientVersions.cursor must be {MIN_CURSOR_VERSION}")
        if set(runtime.components) == {"hooks"}:
            hooks = load(root / "hooks/hooks.json")
            if set(hooks.get("hooks", {})) != SUPPORTED_HOOK_EVENTS:
                errors.append(f"{package.key}: hooks must register {sorted(SUPPORTED_HOOK_EVENTS)} only")
            script = root / "hooks/herdr-session-start.sh"
            if not script.is_file() or not script.stat().st_mode & stat.S_IXUSR:
                errors.append(f"{script}: must exist and be executable")
        if set(runtime.components) == {"mcp"}:
            declared = manifest.get("variables", {}).get("properties", {})
            used = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", (root / "mcp.json").read_text()))
            if set(declared) != used:
                errors.append(f"{package.key}: MCP placeholders must all be declared variables")
            if manifest.get("mcpServers") != "./mcp.json":
                errors.append(f"{package.key}: mcpServers must point at ./mcp.json")
        errors.extend(resource_errors(root))
    for error in errors:
        print(f"validate_cursor_native: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
