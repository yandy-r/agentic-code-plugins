#!/usr/bin/env python3
"""Read-only component and catalog policies for generated Codex packages.

The shell entrypoint runs generator --check first. These independent structural
policies also guard against regressions in the generated format, without Codex.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import generate_codex_plugin as generator
from codex_marketplace import validate_marketplace_catalog
from generate_codex_mcp import build_codex_mcp_config
from package_model import Package, load_package_model

FORBIDDEN_FIELDS = {"listed", "hooks", "status", "mechanism", "components", "runtimes"}


def require(condition: bool, path: Path, message: str) -> None:
    if not condition:
        raise ValueError(f"{path}: {message}")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), path, "expected a JSON object")
    return payload


def check_fields(payload: dict[str, Any], path: Path) -> None:
    leaked = FORBIDDEN_FIELDS.intersection(payload)
    require(not leaked, path, f"forbidden runtime/listing fields: {sorted(leaked)}")


def check_catalog_structure(catalog: dict[str, Any], path: Path) -> None:
    """Reject malformed Codex marketplace structure before exact generated-value gates."""
    try:
        validate_marketplace_catalog(catalog)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def check_startup_mcp(path: Path, payload: dict[str, Any]) -> None:
    servers = payload.get("mcpServers")
    require(isinstance(servers, dict), path, "expected an mcpServers object")
    for name in ("plan", "agent-native-plans"):
        require(
            name not in servers,
            path,
            f"local-files visual planning must not register the {name!r} startup MCP server",
        )


def check_package(root: Path, package: Package, version: str) -> None:
    package_root = root / ".codex-plugin" / package.key
    manifest_path = package_root / ".codex-plugin/plugin.json"
    manifest = load_json(manifest_path)
    require(manifest.get("name") == package.key, manifest_path, "incorrect package name")
    require(manifest.get("version") == version, manifest_path, f"expected canonical version {version!r}")
    check_fields(manifest, manifest_path)
    runtime = next(entry for entry in package.runtimes if entry.runtime == "codex")
    skills_only = set(runtime.components) == {"skills", "shared"}
    if skills_only:
        require(manifest.get("skills") == "./skills/", manifest_path, "expected skills: ./skills/")
        require("mcpServers" not in manifest, manifest_path, "skills-only package declares MCP")
        require(not (package_root / ".mcp.json").exists(), package_root, "skills-only package ships MCP")
        for directory in ("skills", "shared"):
            require((package_root / directory).is_dir(), package_root, f"missing {directory}/ payload")
    else:
        require("skills" not in manifest, manifest_path, "MCP-only package declares skills")
        require(manifest.get("mcpServers") == "./.mcp.json", manifest_path, "expected mcpServers: ./.mcp.json")
        for directory in ("skills", "shared"):
            require(not (package_root / directory).exists(), package_root, f"MCP-only package ships {directory}/")
        mcp_path = package_root / ".mcp.json"
        payload = load_json(mcp_path)
        require(
            payload == {"mcpServers": build_codex_mcp_config()["mcp_servers"]},
            mcp_path,
            "payload does not match the Codex MCP translation",
        )
        require("${" not in json.dumps(payload), mcp_path, "literal Claude interpolation survived translation")
        check_startup_mcp(mcp_path, payload)
    # Restrict package-root components, not bundled skill helper/reference names.
    allowed = {".codex-plugin", "skills", "shared"} if skills_only else {".codex-plugin", ".mcp.json"}
    for child in package_root.iterdir():
        require(child.name in allowed, child, "unexpected native package component (hooks are unsupported)")


def check_catalog(root: Path, packages: tuple[Package, ...], *, include_unlisted: bool = True) -> None:
    path = root / generator.NATIVE_MARKETPLACE
    catalog = load_json(path)
    check_catalog_structure(catalog, path)
    require(catalog.get("name") == "ycc", path, "native catalog must be named 'ycc'")
    check_fields(catalog, path)
    entries = catalog.get("plugins")
    require(isinstance(entries, list), path, "expected a plugins list")
    require(all(isinstance(entry, dict) for entry in entries), path, "expected plugin objects")
    names = [entry.get("name") for entry in entries]
    expected_catalog = generator.build_native_marketplace(packages, include_unlisted=include_unlisted)
    expected_names = {entry["name"] for entry in expected_catalog["plugins"]}
    require(
        len(names) == len(expected_names) and set(names) == expected_names,
        path,
        f"expected exactly the eligible included native packages {sorted(expected_names)}",
    )
    for entry in entries:
        check_fields(entry, path)
        name = entry["name"]
        source = entry.get("source")
        require(isinstance(source, dict), path, f"{name}: expected a local source object")
        package_root = root / ".codex-plugin" / name
        require(
            source == {"source": "local", "path": f"./.codex-plugin/{name}"},
            path,
            f"{name}: source must point exactly at its package root",
        )
        require(package_root.is_dir(), path, f"{name}: missing source package root")
        require(
            package_root.resolve().is_relative_to(root.resolve()),
            path,
            f"{name}: source resolves outside the export",
        )
    require(
        catalog == expected_catalog,
        path,
        "catalog differs from the model-driven native catalog",
    )


def validate(root: Path, native: bool) -> None:
    model = load_package_model()
    packages = generator.native_packages(model.packages)
    version = generator.native_version(model)
    if not native and (listing_error := generator.partial_codex_listing_error(model.packages)) is not None:
        raise ValueError(listing_error)
    listed = generator.build_repository_marketplace(packages)["name"] == "ycc"
    if native or listed:
        check_catalog(root, packages, include_unlisted=native)
        for package in packages:
            check_package(root, package, version)
        # Unrelated neighboring roots are deliberately outside generator ownership.
        # Excluded model packages, however, must not leak into the native export.
        included = {package.key for package in packages}
        for package in model.packages:
            runtime = model.lookup(package.key, "codex")
            if runtime is not None and runtime.mechanism == "native" and package.key not in included:
                path = root / ".codex-plugin" / package.key
                require(not path.exists(), path, "ineligible native package must not be emitted")
    else:
        legacy_path = root / ".codex-plugin/ycc/.codex-plugin/plugin.json"
        legacy = load_json(legacy_path)
        require(legacy.get("version") == version, legacy_path, f"expected canonical version {version!r}")
        require(legacy == generator.build_plugin_manifest(), legacy_path, "legacy combined manifest changed")
        check_fields(legacy, legacy_path)
        legacy_mcp = root / ".codex-plugin/ycc/.mcp.json"
        check_startup_mcp(legacy_mcp, load_json(legacy_mcp))
        catalog_path = root / generator.NATIVE_MARKETPLACE
        legacy_catalog = load_json(catalog_path)
        check_catalog_structure(legacy_catalog, catalog_path)
        require(
            legacy_catalog == generator.build_repo_marketplace(),
            catalog_path,
            "legacy discovered catalog changed",
        )
        for package in packages:
            runtime = model.lookup(package.key, "codex")
            if runtime is not None and set(runtime.components) == {"mcp"}:
                check_package(root, package, version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-output", type=Path, help="Check an explicit external native export")
    args = parser.parse_args()
    try:
        native = args.native_output is not None
        validate(args.native_output if native else generator.REPO_ROOT, native)
    except (OSError, ValueError) as exc:
        print(f"validate_codex_native: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
