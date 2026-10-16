#!/usr/bin/env python3
"""Generate hidden Claude-native add-on packages from the package model."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from package_model import Package, PackageModel, RuntimePackage, load_package_model

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path("packages/claude")
SOURCE_PLUGIN_PATH = Path("ycc/.claude-plugin/plugin.json")
SOURCE_MCP_PATH = Path("mcp-configs/mcp.json")
SOURCE_SETTINGS_PATH = Path("ycc/settings/settings.json")
SOURCE_HOOK_PATH = Path("ycc/settings/hooks/worktree-create.sh")
INSTALLER_HOOK_COMMAND = "bash ~/.claude/hooks/worktree-create.sh"
PLUGIN_HOOK_COMMAND = 'bash "${CLAUDE_PLUGIN_ROOT}/hooks/worktree-create.sh"'
NATIVE_COMPONENTS = {frozenset({"mcp"}), frozenset({"hooks"}), frozenset()}


@dataclass(frozen=True)
class Payload:
    content: bytes
    executable: bool = False


def claude_runtime(package: Package) -> RuntimePackage | None:
    return next((entry for entry in package.runtimes if entry.runtime == "claude"), None)


def package_root(package: Package) -> Path:
    if Path(package.key).name != package.key or package.key in {".", ".."}:
        raise ValueError(f"unsafe native Claude package name: {package.key}")
    return OUTPUT_ROOT / package.key


def native_package_roots(packages: Iterable[Package]) -> tuple[Path, ...]:
    """Own modeled native add-ons, including excluded/deferred stale output."""
    return tuple(
        package_root(package)
        for package in packages
        if package.key != "ycc" and (runtime := claude_runtime(package)) is not None and runtime.mechanism == "native"
    )


def native_packages(packages: Iterable[Package]) -> tuple[Package, ...]:
    """Select included/native add-ons independently of catalog visibility."""
    selected: list[Package] = []
    for package in packages:
        runtime = claude_runtime(package)
        if package.key == "ycc" or runtime is None or runtime.status != "included" or runtime.mechanism != "native":
            continue
        if frozenset(runtime.components) not in NATIVE_COMPONENTS or (not runtime.components and not runtime.requires):
            raise ValueError(f"unsupported included native Claude components for {package.key}: {runtime.components}")
        package_root(package)
        selected.append(package)
    return tuple(selected)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_payload(value: Any) -> Payload:
    return Payload((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def native_version(model: PackageModel) -> str:
    source = read_json(REPO_ROOT / model.version_source)
    version = source.get("version") if isinstance(source, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{model.version_source}: missing nonempty version")
    return version


def hook_payloads() -> dict[Path, Payload]:
    """Relocate only explicitly supported registrations, preserving their options."""
    settings = read_json(REPO_ROOT / SOURCE_SETTINGS_PATH)
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks, dict):
        raise ValueError(f"{SOURCE_SETTINGS_PATH}: hooks must be an object")
    copies: dict[Path, Payload] = {}
    for event, groups in hooks.items():
        if event != "WorktreeCreate":
            raise ValueError(f"unsupported registered Claude hook event: {event}")
        if not isinstance(groups, list):
            raise ValueError(f"{event}: hook registrations must be an array")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"{event}: hook registration must contain a hooks array")
            for hook in group["hooks"]:
                if (
                    not isinstance(hook, dict)
                    or hook.get("type") != "command"
                    or hook.get("command") != INSTALLER_HOOK_COMMAND
                ):
                    raise ValueError(f"unsupported registered Claude hook command for {event}: {hook!r}")
                hook["command"] = PLUGIN_HOOK_COMMAND
                source = REPO_ROOT / SOURCE_HOOK_PATH
                copies[Path("hooks/worktree-create.sh")] = Payload(
                    source.read_bytes(), bool(source.stat().st_mode & stat.S_IXUSR)
                )
    return {Path("hooks/hooks.json"): json_payload({"hooks": hooks}), **copies}


def native_payloads(model: PackageModel, packages: Iterable[Package]) -> dict[Path, Payload]:
    """Resolve every source and metadata value before any destination mutation."""
    version = native_version(model)
    source = read_json(REPO_ROOT / SOURCE_PLUGIN_PATH)
    author = source.get("author") if isinstance(source, dict) else None
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        raise ValueError(f"{SOURCE_PLUGIN_PATH}: missing author name")
    output: dict[Path, Payload] = {}
    for package in packages:
        runtime = claude_runtime(package)
        assert runtime is not None
        root = package_root(package)
        manifest = {"name": package.key, "version": version, "description": package.description, "author": author}
        if runtime.requires:
            manifest["dependencies"] = list(runtime.requires)
        output[root / ".claude-plugin/plugin.json"] = json_payload(manifest)
        if runtime.components == ("mcp",):
            content = (REPO_ROOT / SOURCE_MCP_PATH).read_bytes()
            config = json.loads(content)
            if not isinstance(config, dict) or not isinstance(config.get("mcpServers"), dict):
                raise ValueError(f"{SOURCE_MCP_PATH}: missing mcpServers object")
            output[root / ".mcp.json"] = Payload(content)
        elif runtime.components == ("hooks",):
            output.update((root / rel, payload) for rel, payload in hook_payloads().items())
    return output


def guard_managed_paths(dest_root: Path, inventory: Iterable[Path], owned_roots: Iterable[Path]) -> None:
    """Reject managed symlinks and file/directory conflicts before writing."""
    if dest_root.is_symlink() or (dest_root.exists() and not dest_root.is_dir()):
        raise ValueError(f"output root must be a non-symlink directory: {dest_root}")
    files = set(inventory)
    roots = tuple(owned_roots)
    for rel in (*files, *roots):
        for depth in range(1, len(rel.parts) + 1):
            prefix = Path(*rel.parts[:depth])
            path = dest_root / prefix
            if path.is_symlink():
                raise ValueError(f"managed-path symlink is not allowed: {prefix}")
            if prefix != rel and path.exists() and not path.is_dir():
                raise ValueError(f"managed parent is not a directory: {prefix}")
        if rel in files and (dest_root / rel).exists() and not (dest_root / rel).is_file():
            raise ValueError(f"managed output is not a regular file: {rel}")
    for rel in roots:
        for directory, dirs, filenames in os.walk(dest_root / rel, followlinks=False):
            for name in dirs + filenames:
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError(f"managed-path symlink is not allowed: {path.relative_to(dest_root)}")


def native_owned_files(dest_root: Path, roots: Iterable[Path]) -> set[Path]:
    files: set[Path] = set()
    for rel in roots:
        root = dest_root / rel
        if root.is_file():
            files.add(rel)
        files.update(path.relative_to(dest_root) for path in root.rglob("*") if path.is_file())
    return files


def native_extras(dest_root: Path, inventory: set[Path], roots: Iterable[Path]) -> set[Path]:
    extras = native_owned_files(dest_root, roots) - inventory
    for rel in roots:
        root = dest_root / rel
        if root.exists() and not any(rel in path.parents for path in inventory):
            extras.add(rel)
        for directory in root.rglob("*"):
            relative = directory.relative_to(dest_root)
            if directory.is_dir() and not any(relative in path.parents for path in inventory):
                extras.add(relative)
    return extras


def prune_native_output(dest_root: Path, inventory: set[Path], roots: tuple[Path, ...]) -> None:
    for rel in sorted(native_owned_files(dest_root, roots) - inventory):
        (dest_root / rel).unlink()
    for rel in roots:
        root = dest_root / rel
        for path in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if root.is_dir() and not any(root.iterdir()) and not any(rel in path.parents for path in inventory):
            root.rmdir()


def write_all(dest_root: Path, dry_run: bool = False) -> set[Path]:
    model = load_package_model()
    roots = native_package_roots(model.packages)
    output = native_payloads(model, native_packages(model.packages))
    inventory = set(output)
    guard_managed_paths(dest_root, inventory, roots)
    if dry_run:
        for rel in sorted(output):
            print(f"Would write {rel}")
        for rel in sorted(native_extras(dest_root, inventory, roots)):
            print(f"Would remove {rel}")
        return inventory
    for rel, payload in sorted(output.items()):
        path = dest_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != payload.content:
            path.write_bytes(payload.content)
        path.chmod(0o755 if payload.executable else 0o644)
    prune_native_output(dest_root, inventory, roots)
    return inventory


def run_check(repo_root: Path | None = None) -> int:
    dest_root = REPO_ROOT if repo_root is None else repo_root
    model = load_package_model()
    roots = native_package_roots(model.packages)
    output = native_payloads(model, native_packages(model.packages))
    inventory = set(output)
    guard_managed_paths(dest_root, inventory, roots)
    diffs: list[str] = []
    for rel, payload in sorted(output.items()):
        path = dest_root / rel
        if not path.is_file():
            diffs.append(f"missing file: {rel}")
            continue
        if path.read_bytes() != payload.content:
            diffs.append(f"drift: {rel}")
        if bool(path.stat().st_mode & stat.S_IXUSR) != payload.executable:
            diffs.append(f"executable-bit drift: {rel}")
    diffs.extend(f"extra in output: {rel}" for rel in sorted(native_extras(dest_root, inventory, roots)))
    if diffs:
        print("Claude native packages are out of date. Run: ./scripts/generate-claude-packages.sh", file=sys.stderr)
        for diff in diffs:
            print(f"  {diff}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Exit 1 if generated output drifts")
    modes.add_argument("--dry-run", action="store_true", help="Print what would be written without mutation")
    args = parser.parse_args(argv)
    try:
        if args.check:
            return run_check()
        write_all(REPO_ROOT, args.dry_run)
        if not args.dry_run:
            print(f"Wrote Claude native packages under {OUTPUT_ROOT}")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"generate_claude_packages: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
