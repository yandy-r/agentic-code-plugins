#!/usr/bin/env python3
"""Read-only policy checks for generated OMP native packages and their catalog (YAN-1171).

The shell entrypoint (validate-omp-packages.sh) runs generator --check first, which proves
byte and mode parity of every generated file. These checks are independent of the generator's
output and need no omp binary. They mirror omp 18.12.x's own catalog parser
(marketplace/fetcher.ts parseMarketplaceCatalog) and install rules:

- catalog: required name, owner.name and plugins; valid name segments; `./` string sources
  that resolve to a package root; exactly the listed rows (or, for `--export`, every
  included row); absent when nothing is listed;
- manifests: `.omp-plugin/plugin.json`, `.claude-plugin/plugin.json` and package.json per
  included row, each named after the package key, with the lockstep version that the catalog
  entry and metadata also carry; unique, valid runtime package names;
- closure: the ycc root holds only manifests and skills/agents/commands; every source skill,
  agent and the shared stub ship; every command has its skill; every skill:// reference resolves.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import generate_omp_packages as generator
from package_model import Package, PackageModel, load_package_model

# omp marketplace/types.ts NAME_RE / MAX_NAME_LENGTH, manager.ts RUNTIME_PACKAGE_NAME_RE.
NAME_SEGMENT = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$")
MAX_NAME_LENGTH = 64
RUNTIME_PACKAGE_NAME = re.compile(r"^(?:@[a-zA-Z0-9][a-zA-Z0-9._~-]*/)?[a-zA-Z0-9][a-zA-Z0-9._~-]*$")
ROOT_ENTRIES = frozenset({".omp-plugin", ".claude-plugin", "package.json", *generator.COMPONENT_DIRS})
SKILL_REF = re.compile(r"skill://([A-Za-z0-9][A-Za-z0-9-]*)(/[^\s`'\"()\[\]|,;<>]*)?")
PATTERN_CHARS = frozenset("*?[]{}$<>")
SKILL_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable or malformed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def valid_name(name: object) -> bool:
    return isinstance(name, str) and len(name) <= MAX_NAME_LENGTH and NAME_SEGMENT.match(name) is not None


def catalog_errors(root: Path, model: PackageModel, version: str, *, export: bool) -> list[str]:
    path = root / generator.MARKETPLACE_PATH
    packages = generator.native_packages(model.packages)
    expected = {
        package.key
        for package in packages
        if export or (runtime := generator.omp_runtime(package)) is not None and runtime.listed
    }
    if not expected:
        return [f"{generator.MARKETPLACE_PATH} must not exist when no OMP package is listed"] if path.exists() else []
    if not path.is_file():
        return [f"{generator.MARKETPLACE_PATH}: missing catalog for listed OMP packages {sorted(expected)}"]
    try:
        catalog = load_object(path)
    except ValueError as exc:
        return [str(exc)]
    errors: list[str] = []
    where = generator.MARKETPLACE_PATH
    if not valid_name(catalog.get("name")):
        errors.append(f"{where}: name must be a valid OMP name segment")
    owner = catalog.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str) or not owner["name"].strip():
        errors.append(f"{where}: owner.name is required")
    metadata = catalog.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("version") != version:
        errors.append(f"{where}: metadata.version must be the lockstep version {version}")
    entries = catalog.get("plugins")
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        return [*errors, f"{where}: plugins must be an array of objects"]
    names = [entry.get("name") for entry in entries]
    if not all(isinstance(name, str) for name in names):
        return [*errors, f"{where}: plugin names must be strings, got {names}"]
    if len(names) != len(expected) or set(names) != expected:
        scope = "included" if export else "listed"
        errors.append(f"{where}: plugins must be exactly the {scope} OMP packages {sorted(expected)}, got {names}")
    if len({str(name).lower() for name in names}) != len(names):
        errors.append(f"{where}: plugin names collide case-insensitively")
    for entry in entries:
        name = entry.get("name")
        label = f"{where}: plugins[{name!r}]"
        if not valid_name(name):
            errors.append(f"{label}: name must be a valid OMP name segment")
            continue
        source = entry.get("source")
        expected_source = f"./{(generator.OUTPUT_ROOT / str(name)).as_posix()}"
        if source != expected_source:
            errors.append(f"{label}: source must be the relative string {expected_source!r}")
        elif not (root / str(source)).is_dir():
            errors.append(f"{label}: source {source} is not a directory")
        if entry.get("version") != version:
            errors.append(f"{label}: version must be the lockstep version {version}")
    return errors


def manifest_errors(root: Path, packages: tuple[Package, ...], version: str) -> list[str]:
    errors: list[str] = []
    runtime_names: dict[str, str] = {}
    for package in packages:
        package_root = generator.package_root(package)
        for manifest in generator.MANIFESTS:
            rel = package_root / manifest
            try:
                payload = load_object(root / rel)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if payload.get("name") != package.key:
                errors.append(f"{rel}: name must be the package key {package.key!r}")
            if payload.get("version") != version:
                errors.append(f"{rel}: version must be the lockstep version {version}")
            if manifest == generator.PACKAGE_JSON:
                name = payload.get("name")
                if not isinstance(name, str) or not RUNTIME_PACKAGE_NAME.match(name):
                    errors.append(f"{rel}: name is not a valid OMP runtime package name")
                elif (owner := runtime_names.setdefault(name.lower(), package.key)) != package.key:
                    errors.append(f"{rel}: runtime package name {name!r} collides with package {owner!r}")
    return errors


def inactive_root_errors(root: Path, model: PackageModel, packages: tuple[Package, ...]) -> list[str]:
    """A deferred or excluded row must not ship manifests (it would be installable by path)."""
    active = {package.key for package in packages}
    errors: list[str] = []
    for package_root in generator.native_package_roots(model.packages):
        if package_root.name in active:
            continue
        for manifest in generator.MANIFESTS:
            if (root / package_root / manifest).exists():
                errors.append(f"{package_root / manifest}: manifest for a row that is not included")
        if package_root != generator.COMPONENT_ROOT and (root / package_root).exists():
            errors.append(f"{package_root}: root for a row that is not included")
    return errors


def skill_names(skills_dir: Path) -> dict[str, Path]:
    names: dict[str, Path] = {}
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        match = SKILL_NAME.search(skill_file.read_text(encoding="utf-8"))
        names[match.group(1) if match else skill_file.parent.name] = skill_file.parent
    return names


def closure_errors(root: Path, source_root: Path, *, has_manifests: bool) -> list[str]:
    errors: list[str] = []
    package_root = root / generator.COMPONENT_ROOT
    rel = generator.COMPONENT_ROOT
    if not package_root.is_dir():
        return [f"{rel}: missing package root"]
    allowed = ROOT_ENTRIES if has_manifests else frozenset(generator.COMPONENT_DIRS)
    for entry in sorted(package_root.iterdir()):
        if entry.name not in allowed:
            errors.append(f"{rel / entry.name}: unexpected entry outside the component trees and manifests")
    skills_dir = package_root / "skills"
    for source in sorted((source_root / "ycc/skills").glob("*/SKILL.md")):
        if not (skills_dir / source.parent.name / "SKILL.md").is_file():
            errors.append(f"{rel}/skills/{source.parent.name}/SKILL.md: missing generated skill")
    for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()) if skills_dir.is_dir() else []:
        if not (skill_dir / "SKILL.md").is_file():
            errors.append(f"{rel}/skills/{skill_dir.name}: skill directory has no SKILL.md")
    if (source_root / "ycc/skills/_shared").is_dir() and not (skills_dir / "_shared/SKILL.md").is_file():
        errors.append(f"{rel}/skills/_shared/SKILL.md: missing shared-resource skill stub")
    for source_agent in sorted((source_root / "ycc/agents").glob("*.md")):
        if not (package_root / "agents" / source_agent.name).is_file():
            errors.append(f"{rel}/agents/{source_agent.name}: missing generated agent")
    names = skill_names(skills_dir)
    for command in sorted((package_root / "commands").glob("*.md")):
        if command.stem not in names:
            errors.append(f"{rel}/commands/{command.name}: no skill named {command.stem!r}")
    for path in sorted(p for p in package_root.rglob("*") if p.is_file()):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in SKILL_REF.finditer(text):
            name, tail = match.group(1), (match.group(2) or "/").split("#", 1)[0].rstrip(".:")
            if name not in names:
                errors.append(f"{path.relative_to(root)}: {match.group(0)} names no packaged skill")
            elif not PATTERN_CHARS.intersection(tail) and not (names[name] / tail.lstrip("/")).exists():
                errors.append(f"{path.relative_to(root)}: {match.group(0)} does not resolve inside the package")
    return errors


def validate(root: Path, model: PackageModel, *, source_root: Path | None = None, export: bool = False) -> list[str]:
    """Every OMP package policy violation under ``root`` (a checkout, or an export with ``export``)."""
    source = root if source_root is None else source_root
    version = generator.native_version(model, source)
    packages = generator.native_packages(model.packages)
    errors = catalog_errors(root, model, version, export=export)
    errors.extend(manifest_errors(root, packages, version))
    errors.extend(inactive_root_errors(root, model, packages))
    has_manifests = generator.WORKFLOW_PACKAGE in {package.key for package in packages}
    errors.extend(closure_errors(root, source, has_manifests=has_manifests))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", type=Path, metavar="DIR", help="Validate an export from generate_omp_packages.py")
    args = parser.parse_args(argv)
    root = generator.REPO_ROOT
    try:
        model = load_package_model(root / "ycc/settings/packages.json", repo_root=root)
        if args.export is not None:
            errors = validate(args.export.resolve(), model, source_root=root, export=True)
        else:
            errors = validate(root, model)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"validate_omp_native: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"validate_omp_native: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
