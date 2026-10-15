#!/usr/bin/env python3
"""Immutable package-model loading and stdlib-only schema/semantic validation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = REPO_ROOT / "ycc/settings/packages.json"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "ycc/settings/packages.schema.json"


class PackageModelError(ValueError):
    """An unreadable, malformed, or invalid package model or schema."""


@dataclass(frozen=True)
class RuntimePackage:
    runtime: str
    status: str
    listed: bool
    mechanism: str
    components: tuple[str, ...]
    requires: tuple[str, ...]
    target_release: str
    experimental: bool
    opt_in: bool
    evidence: tuple[str, ...]
    gates: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class Package:
    key: str
    description: str
    version_policy: str
    runtimes: tuple[RuntimePackage, ...]


@dataclass(frozen=True)
class PackageModel:
    schema_version: int
    version_source: str
    packages: tuple[Package, ...]

    def lookup(self, package: str, runtime: str) -> RuntimePackage | None:
        """Return one runtime entry, or None when it is absent."""
        return next((r for p in self.packages if p.key == package for r in p.runtimes if r.runtime == runtime), None)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageModelError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as exc:
        raise PackageModelError(f"{path}: invalid or unreadable JSON: {exc}") from exc


def load_package_schema(path: Path = DEFAULT_SCHEMA_PATH) -> dict[str, Any]:
    """Load a local 2020-12 schema, rejecting duplicate keys and invalid shapes."""
    schema = _read_json(Path(path))
    if not isinstance(schema, dict) or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise PackageModelError(f"{path}: expected a JSON Schema 2020-12 object")
    _check_schema(schema, schema)
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        raise PackageModelError(f"{path}: expected an object schema with properties")
    return schema


def _check_schema(node: Any, root: Mapping[str, Any]) -> None:
    """Check the deliberately small schema vocabulary used by this manifest."""
    if not isinstance(node, dict):
        raise PackageModelError("schema nodes must be objects")
    allowed = {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "propertyNames",
        "additionalProperties",
        "items",
        "uniqueItems",
        "minLength",
        "minProperties",
    }
    if set(node) - allowed:
        raise PackageModelError(f"unsupported schema keywords: {sorted(set(node) - allowed)}")
    if "type" in node and node["type"] not in ("object", "array", "string", "integer", "boolean"):
        raise PackageModelError("unsupported schema type")
    for key in ("minLength", "minProperties"):
        if key in node and (type(node[key]) is not int or node[key] < 0):
            raise PackageModelError(f"schema {key} must be a non-negative integer")
    if "uniqueItems" in node and not isinstance(node["uniqueItems"], bool):
        raise PackageModelError("schema uniqueItems must be boolean")
    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        raise PackageModelError("schema enum must be a non-empty array")
    if "required" in node:
        required = node["required"]
        if not isinstance(required, list) or not all(isinstance(k, str) for k in required):
            raise PackageModelError("schema required must be a string array")
        if len(set(required)) != len(required):
            raise PackageModelError("schema required contains duplicates")
    for key in ("properties", "$defs"):
        if key in node:
            if not isinstance(node[key], dict):
                raise PackageModelError(f"schema {key} must be an object")
            for child in node[key].values():
                _check_schema(child, root)
    for key in ("items", "propertyNames", "additionalProperties"):
        if key in node and not (key == "additionalProperties" and isinstance(node[key], bool)):
            _check_schema(node[key], root)
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/") or ref[8:] not in root.get("$defs", {}):
            raise PackageModelError(f"unresolved or unsupported schema reference: {ref!r}")


def _schema_errors(value: Any, node: Mapping[str, Any], root: Mapping[str, Any], where: str) -> list[str]:
    errors: list[str] = []
    if "$ref" in node:
        return _schema_errors(value, root["$defs"][node["$ref"][8:]], root, where)
    kind = node.get("type")
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
    }
    if kind and not valid[kind]:
        return [f"{where}: expected {kind}"]
    if "const" in node and (type(value) is not type(node["const"]) or value != node["const"]):
        errors.append(f"{where}: expected const {node['const']!r}")
    if "enum" in node and value not in node["enum"]:
        errors.append(f"{where}: expected one of {node['enum']!r}")
    if isinstance(value, str) and len(value.strip()) < node.get("minLength", 0):
        errors.append(f"{where}: expected non-empty string")
    if isinstance(value, list):
        if node.get("uniqueItems") and any(v in value[:i] for i, v in enumerate(value)):
            errors.append(f"{where}: duplicate array entries")
        for index, item in enumerate(value):
            errors.extend(_schema_errors(item, node.get("items", {}), root, f"{where}[{index}]"))
    if isinstance(value, dict):
        if len(value) < node.get("minProperties", 0):
            errors.append(f"{where}: expected non-empty object")
        for key in node.get("required", []):
            if key not in value:
                errors.append(f"{where}.{key}: missing required field")
        for key, item in value.items():
            if "propertyNames" in node:
                errors.extend(_schema_errors(key, node["propertyNames"], root, f"{where} key {key!r}"))
            child = node.get("properties", {}).get(key, node.get("additionalProperties", True))
            if child is False:
                errors.append(f"{where}.{key}: unknown field")
            elif isinstance(child, dict):
                errors.extend(_schema_errors(item, child, root, f"{where}.{key}"))
    return errors


def _evidence_errors(paths: list[str], repo_root: Path | None, where: str) -> list[str]:
    errors: list[str] = []
    for item in paths:
        path = PurePosixPath(item)
        if not item or "\\" in item or path.is_absolute() or PureWindowsPath(item).drive or ".." in path.parts:
            errors.append(f"{where}: unsafe evidence path {item!r}")
            continue
        if repo_root is not None:
            try:
                resolved = (repo_root / item).resolve()
                resolved.relative_to(repo_root.resolve())
                if not resolved.is_file():
                    errors.append(f"{where}: evidence file does not exist: {item!r}")
            except (OSError, ValueError, RuntimeError):
                errors.append(f"{where}: evidence path escapes repository or cannot resolve: {item!r}")
    return errors


def validate_package_model(
    data: Any, *, repo_root: Path | None = None, schema: Mapping[str, Any] | None = None
) -> list[str]:
    """Return schema and cross-field errors, optionally checking on-disk evidence."""
    try:
        active_schema = load_package_schema() if schema is None else schema
        _check_schema(dict(active_schema), active_schema)
        errors = _schema_errors(data, active_schema, active_schema, "manifest")
    except (PackageModelError, KeyError, TypeError, RecursionError) as exc:
        return [f"invalid package schema: {exc}"]
    if errors:
        return errors  # Semantic checks only run on structurally valid values.
    packages = data["packages"]
    for package_key, package in packages.items():
        for runtime, entry in package["runtimes"].items():
            where = f"packages.{package_key}.runtimes.{runtime}"
            requires = entry["requires"]
            if not entry["components"] and not requires:
                errors.append(f"{where}: components must be non-empty unless requires is non-empty")
            if requires and (runtime != "claude" or entry["mechanism"] != "native"):
                errors.append(f"{where}: requires is only allowed for claude native packages")
            for required in requires:
                target = packages.get(required, {}).get("runtimes", {}).get("claude", {})
                if required == package_key:
                    errors.append(f"{where}: self-dependency is forbidden")
                if target.get("status") != "included" or target.get("mechanism") != "native":
                    errors.append(f"{where}: requires {required!r} must exist as an included native claude package")
            if entry["listed"] and (entry["status"] != "included" or entry["mechanism"] != "native"):
                errors.append(f"{where}: listed=true requires included native package (not excluded/deferred)")
            if entry["status"] == "deferred" and entry["target_release"] == "v6.0.0":
                errors.append(f"{where}: deferred package must target a later release")
            if package_key == "installer-fallback" and (entry["mechanism"] != "file-copy" or entry["listed"]):
                errors.append(f"{where}: installer-fallback must use file-copy and listed=false")
            errors.extend(_evidence_errors(entry["evidence"], repo_root, where))
    return errors


def _model(data: dict[str, Any]) -> PackageModel:
    packages: list[Package] = []
    for key, package in data["packages"].items():
        runtimes: list[RuntimePackage] = []
        for runtime, raw in package["runtimes"].items():
            entry = dict(raw)
            for field in ("components", "requires", "evidence", "gates"):
                entry[field] = tuple(entry[field])
            runtimes.append(RuntimePackage(runtime=runtime, **entry))
        packages.append(Package(key, package["description"], package["version_policy"], tuple(runtimes)))
    return PackageModel(data["schema_version"], data["version_source"], tuple(packages))


def load_package_model(path: Path = DEFAULT_MANIFEST_PATH, *, repo_root: Path | None = None) -> PackageModel:
    """Load a validated, immutable model; default evidence root is this repository."""
    data = _read_json(Path(path))
    errors = validate_package_model(data, repo_root=REPO_ROOT if repo_root is None else repo_root)
    if errors:
        raise PackageModelError(f"{path}:\n" + "\n".join(errors))
    return _model(data)


def main(argv: list[str] | None = None) -> int:
    """Validate schema and manifest without modifying any files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--check", action="store_true", help="Validate only (also the default).")
    args = parser.parse_args(argv)
    try:
        schema = load_package_schema(args.schema)
        errors = validate_package_model(_read_json(args.manifest), repo_root=REPO_ROOT, schema=schema)
        if errors:
            raise PackageModelError("\n".join(errors))
    except PackageModelError as exc:
        print(f"package_model: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {args.manifest} matches {args.schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
