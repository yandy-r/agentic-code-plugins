#!/usr/bin/env python3
"""Read-only manifest identity, dependency and agent-preload policies for Claude packages.

Canonical ycc stays at ycc/; modeled native add-ons live at packages/claude/<key>.
The generator's drift check remains separate from these structural policies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from generate_codex_common import parse_frontmatter
from package_model import PackageModel, RuntimePackage, load_package_model

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(".claude-plugin/plugin.json")
MARKETPLACE = Path(".claude-plugin/marketplace.json")
COMPONENT_FILES = {"mcp": ".mcp.json", "hooks": "hooks/hooks.json"}


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def load_agent_skills(text: str) -> list[str]:
    """Read YAML scalar or list preloads using the existing generation parser."""
    if text.startswith("---\n") and "\n---\n" not in text[4:]:
        raise ValueError("unterminated agent frontmatter")
    try:
        frontmatter, _ = parse_frontmatter(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid agent frontmatter: {exc}") from exc
    value = frontmatter.get("skills", [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(skill, str) or not skill.strip() for skill in value):
        raise ValueError("agent skills must be a string or a list of nonempty strings")
    return [skill.strip() for skill in value]


def _closure(key: str, runtimes: dict[str, RuntimePackage], errors: list[str]) -> set[str]:
    """Follow modeled requires transitively, reporting cycles without recursing forever."""
    closure: set[str] = set()

    def visit(current: str, chain: tuple[str, ...]) -> None:
        if current in chain:
            errors.append(f"{key}: requires cycle: {' -> '.join((*chain, current))}")
            return
        if current in closure:
            return
        closure.add(current)
        for required in runtimes[current].requires:
            if required in runtimes:
                visit(required, (*chain, current))

    visit(key, ())
    return closure


def _catalog_errors(
    root: Path,
    roots: dict[str, Path],
    runtimes: dict[str, RuntimePackage],
    manifests: dict[str, dict[str, Any]],
    version: str | None,
) -> list[str]:
    path = root / MARKETPLACE
    try:
        catalog = load_object(path)
    except ValueError as exc:
        return [str(exc)]
    entries = catalog.get("plugins")
    if not isinstance(entries, list):
        return [f"{path}: expected a plugins list"]
    errors: list[str] = []
    seen: set[str] = set()
    by_root = {package_root.resolve(): key for key, package_root in roots.items()}
    for index, entry in enumerate(entries):
        where = f"{path}: plugins[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: expected a plugin object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}: expected a nonempty plugin name")
            continue
        if name in seen:
            errors.append(f"{where}: duplicate marketplace entry {name!r}")
        seen.add(name)
        source = entry.get("source")
        if not isinstance(source, str) or not source.strip() or Path(source).is_absolute():
            errors.append(f"{where}: expected a relative local source path")
            continue
        target = (root / source).resolve()
        if not target.is_relative_to(root.resolve()) or target not in by_root:
            errors.append(f"{where}: source {source!r} does not point at an included native Claude package")
            continue
        key = by_root[target]
        manifest = manifests.get(key)
        if name != key or (manifest is not None and name != manifest.get("name")):
            errors.append(f"{where}: marketplace entry name {name!r} does not match source manifest/package {key!r}")
        if not runtimes[key].listed:
            errors.append(f"{where}: unlisted package {key!r} must not appear in the marketplace")
        if "version" in entry and version is not None and entry["version"] != version:
            errors.append(f"{where}: marketplace version must match modeled version {version!r}")
    expected = {key for key, runtime in runtimes.items() if runtime.listed}
    if seen != expected:
        errors.append(f"{path}: expected exactly the listed native Claude packages {sorted(expected)}")
    return errors


def validate(root: Path, model: PackageModel) -> list[str]:
    """Validate a repository-shaped fixture without generating files or invoking Claude."""
    root = Path(root)
    errors: list[str] = []
    runtimes: dict[str, RuntimePackage] = {}
    roots: dict[str, Path] = {}
    for package in model.packages:
        runtime = model.lookup(package.key, "claude")
        if runtime is None or runtime.status != "included" or runtime.mechanism != "native":
            continue
        if Path(package.key).name != package.key or package.key in {".", "..", ""}:
            errors.append(f"unsafe native Claude package key: {package.key!r}")
            continue
        runtimes[package.key] = runtime
        roots[package.key] = root / (Path("ycc") if package.key == "ycc" else Path("packages/claude") / package.key)

    version_path = root / model.version_source
    version: str | None = None
    try:
        value = load_object(version_path).get("version")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{version_path}: missing nonempty version")
        else:
            version = value
    except ValueError as exc:
        errors.append(str(exc))

    names: dict[str, str] = {}
    manifests: dict[str, dict[str, Any]] = {}
    skills: dict[str, set[str]] = {}
    for key, runtime in runtimes.items():
        package_root = roots[key]
        manifest_path = package_root / MANIFEST
        try:
            manifest = load_object(manifest_path)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            manifests[key] = manifest
            name = manifest.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{manifest_path}: expected a nonempty manifest name")
            else:
                if name != key:
                    errors.append(f"{manifest_path}: manifest name {name!r} must match package key {key!r}")
                if name in names:
                    errors.append(
                        f"{manifest_path}: duplicate manifest name {name!r} already declared by {names[name]!r}"
                    )
                names[name] = key
            if version is not None and manifest.get("version") != version:
                errors.append(f"{manifest_path}: manifest version must match {model.version_source} ({version!r})")
            if manifest.get("dependencies", []) != list(runtime.requires):
                errors.append(f"{manifest_path}: dependencies must match modeled requires {list(runtime.requires)!r}")
        for dependency in runtime.requires:
            if dependency not in runtimes:
                errors.append(f"{key}: dependency {dependency!r} is not an included native Claude package")
        for component, layout in COMPONENT_FILES.items():
            if component in runtime.components and not (package_root / layout).is_file():
                errors.append(f"{package_root}: missing modeled {component} payload ({layout})")
        for component in ("skills", "agents"):
            if component in runtime.components and not (package_root / component).is_dir():
                errors.append(f"{package_root}: missing modeled {component}/ payload")
        # Skill IDs are directory names with actual SKILL.md payloads, not agent
        # names, component labels, or files from an unrelated canonical package.
        skills[key] = (
            {path.parent.name for path in (package_root / "skills").glob("*/SKILL.md") if path.is_file()}
            if "skills" in runtime.components
            else set()
        )

    errors.extend(_catalog_errors(root, roots, runtimes, manifests, version))
    for key, runtime in runtimes.items():
        closure = _closure(key, runtimes, errors)
        if "agents" not in runtime.components:
            continue
        for path in sorted((roots[key] / "agents").glob("*.md")):
            try:
                preloads = load_agent_skills(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(f"{path}: {exc}")
                continue
            for reference in preloads:
                if ":" in reference:
                    plugin, skill = reference.split(":", 1)
                    if plugin not in closure:
                        errors.append(
                            f"{path}: agent skill {reference!r} targets a plugin outside its requires closure"
                        )
                    elif skill not in skills.get(plugin, set()):
                        errors.append(f"{path}: missing agent skill {reference!r} in package {plugin!r}")
                elif reference not in skills[key]:
                    providers = sorted(target for target in closure - {key} if reference in skills[target])
                    if providers:
                        errors.append(
                            f"{path}: unqualified cross-package agent skill {reference!r}; "
                            f"use <plugin>:<skill> (providers: {providers})"
                        )
                    else:
                        errors.append(f"{path}: missing agent skill {reference!r} in package {key!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, help="Check a repository-shaped export instead of this repo")
    args = parser.parse_args(argv)
    root = args.output_root or REPO_ROOT
    try:
        model = load_package_model(root / "ycc/settings/packages.json", repo_root=root)
        errors = validate(root, model)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"validate_claude_native: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"validate_claude_native: {error}", file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
