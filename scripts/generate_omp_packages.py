#!/usr/bin/env python3
"""Generate OMP (oh-my-pi) native packages and marketplace metadata from the package model (YAN-1171).

Each included native OMP row becomes a package root at packages/omp/<key>/ carrying:

- `.omp-plugin/plugin.json`: OMP keeps agent `model:` frontmatter only for roots with it;
- `.claude-plugin/plugin.json`: names the `/ycc:<skill>` command prefix under `--plugin-dir`
  and is the first manifest OMP reads for a relative source's install and upgrade version;
- `package.json`: the unique runtime package name OMP links under `plugins/node_modules/`;
- the component trees, staged through the existing generators (generate_omp_{skills,agents,commands});
- for an MCP-only row (ycc-mcp), a root `.mcp.json` holding the exact bytes of mcp-configs/mcp.json.
  OMP falls back to `<root>/.mcp.json` when no manifest declares `mcpServers` and names each
  server `<package>:<server>`. The source is audited for secret literals first, and `${VAR}`
  placeholders are never expanded here: OMP expands them when it starts a server.

All manifests and the catalog entry carry the lockstep version from the model's version source.

Selection keys on runtime == "omp" and mechanism == "native". Only included rows are emitted,
and only the {skills, agents, commands, shared} and {mcp} component sets have emitters here; an
included or listed row with any other set fails closed (hooks and rules are YAN-1174/1175).
The root `.omp-plugin/marketplace.json` is written only when a row is listed and holds exactly
the listed rows with fork-safe relative sources; otherwise it is removed. `--export DIR` writes
a repository-shaped tree outside the checkout whose catalog also lists unlisted included rows,
for the opt-in live harness (scripts/test-omp-native-packages.sh) and the export validation.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp_secret_audit import audit_no_secret_literals, load_mcp_config
from package_model import Package, PackageModel, RuntimePackage, load_package_model

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path("packages/omp")
CATALOG_DIR = Path(".omp-plugin")
MARKETPLACE_PATH = CATALOG_DIR / "marketplace.json"
OMP_MANIFEST = Path(".omp-plugin/plugin.json")
CLAUDE_MANIFEST = Path(".claude-plugin/plugin.json")
PACKAGE_JSON = Path("package.json")
MANIFESTS = (OMP_MANIFEST, CLAUDE_MANIFEST, PACKAGE_JSON)
SOURCE_PLUGIN_PATH = Path("ycc/.claude-plugin/plugin.json")
SOURCE_MCP_PATH = Path("mcp-configs/mcp.json")
MCP_CONFIG = Path(".mcp.json")
CATALOG_NAME = "ycc"
MIN_OMP_VERSION = "18.12.2"
CATALOG_DESCRIPTION = f"ycc development-workflow packages for oh-my-pi (omp >={MIN_OMP_VERSION})."

# The component sets with an emitter in this generator. Other sets are owned by the
# issues named here and fail closed until their emitters land.
WORKFLOW_COMPONENTS = frozenset({"skills", "agents", "commands", "shared"})
MCP_COMPONENTS = frozenset({"mcp"})
COMPONENT_OWNERS = {"hooks": "YAN-1174", "rules": "YAN-1175"}
COMPONENT_DIRS = ("skills", "agents", "commands")
# generate_omp_{skills,agents,commands} write one tree, always under this package root.
WORKFLOW_PACKAGE = "ycc"
COMPONENT_ROOT = OUTPUT_ROOT / WORKFLOW_PACKAGE


@dataclass(frozen=True)
class Payload:
    content: bytes
    # Permission bits written to disk. Component files keep the mode their generator
    # produced so this generator and generate_omp_{skills,agents,commands} never fight
    # over it; drift checks compare bytes and executable bits only (see check_payloads).
    mode: int = 0o644


ComponentSource = Callable[[Path], dict[Path, Payload]]


def omp_runtime(package: Package) -> RuntimePackage | None:
    return next((entry for entry in package.runtimes if entry.runtime == "omp"), None)


def package_root(package: Package) -> Path:
    if Path(package.key).name != package.key or package.key in {".", ".."}:
        raise ValueError(f"unsafe OMP package key: {package.key!r}")
    return OUTPUT_ROOT / package.key


def native_package_roots(packages: Iterable[Package]) -> tuple[Path, ...]:
    """Own every modeled native OMP root, so deferred and excluded rows are pruned."""
    return tuple(
        package_root(package)
        for package in packages
        if (runtime := omp_runtime(package)) is not None and runtime.mechanism == "native"
    )


def native_packages(packages: Iterable[Package]) -> tuple[Package, ...]:
    """Included native OMP rows; fail closed on any row this generator cannot emit."""
    selected: list[Package] = []
    for package in packages:
        runtime = omp_runtime(package)
        if runtime is None or runtime.mechanism != "native":
            continue
        where = f"packages.{package.key}.runtimes.omp"
        if runtime.listed and runtime.status != "included":
            raise ValueError(f"{where}: listed=true requires status included")
        if runtime.status != "included":
            continue
        components = frozenset(runtime.components)
        if components not in (WORKFLOW_COMPONENTS, MCP_COMPONENTS):
            unsupported = components - WORKFLOW_COMPONENTS - MCP_COMPONENTS or components
            owners = sorted({COMPONENT_OWNERS.get(component, "no planned issue") for component in unsupported})
            raise ValueError(
                f"{where}: no OMP emitter for components {sorted(components)} (owned by {', '.join(owners)}); "
                "keep the row deferred and unlisted until its emitter lands"
            )
        if components == WORKFLOW_COMPONENTS and package.key != WORKFLOW_PACKAGE:
            raise ValueError(f"{where}: the skills/agents/commands trees ship only in the {WORKFLOW_PACKAGE} package")
        package_root(package)
        selected.append(package)
    return tuple(selected)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_payload(value: Any) -> Payload:
    return Payload((json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def native_version(model: PackageModel, repo_root: Path = REPO_ROOT) -> str:
    source = read_json(repo_root / model.version_source)
    version = source.get("version") if isinstance(source, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{model.version_source}: missing nonempty version")
    return version


def manifest_author(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    source = read_json(repo_root / SOURCE_PLUGIN_PATH)
    author = source.get("author") if isinstance(source, dict) else None
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        raise ValueError(f"{SOURCE_PLUGIN_PATH}: missing author name")
    return {"name": author["name"]}


def build_marketplace(
    packages: Iterable[Package], version: str, author: dict[str, str], *, include_unlisted: bool = False
) -> dict[str, Any] | None:
    """The catalog of listed (or, for exports, all included) rows; None keeps it absent."""
    entries = [
        {
            "name": package.key,
            "source": f"./{package_root(package).as_posix()}",
            "description": package.description,
            "version": version,
        }
        for package in native_packages(packages)
        if include_unlisted or (runtime := omp_runtime(package)) is not None and runtime.listed
    ]
    if not entries:
        return None
    return {
        "name": CATALOG_NAME,
        "owner": author,
        "metadata": {"description": CATALOG_DESCRIPTION, "version": version},
        "plugins": entries,
    }


def manifest_payloads(packages: Iterable[Package], version: str, author: dict[str, str]) -> dict[Path, Payload]:
    output: dict[Path, Payload] = {}
    for package in packages:
        root = package_root(package)
        manifest = {"name": package.key, "version": version, "description": package.description, "author": author}
        output[root / OMP_MANIFEST] = json_payload(manifest)
        output[root / CLAUDE_MANIFEST] = json_payload(manifest)
        output[root / PACKAGE_JSON] = json_payload(
            {"name": package.key, "version": version, "description": package.description, "private": True}
        )
    return output


def is_mcp_package(package: Package) -> bool:
    runtime = omp_runtime(package)
    return runtime is not None and frozenset(runtime.components) == MCP_COMPONENTS


def mcp_source(repo_root: Path = REPO_ROOT) -> bytes:
    """The audited source bytes; parsed only to fail closed, never rewritten or expanded."""
    content = (repo_root / SOURCE_MCP_PATH).read_bytes()
    audit_no_secret_literals(load_mcp_config(content, SOURCE_MCP_PATH.as_posix()), SOURCE_MCP_PATH.as_posix())
    return content


def mcp_payloads(packages: Iterable[Package], repo_root: Path = REPO_ROOT) -> dict[Path, Payload]:
    roots = [package_root(package) for package in packages if is_mcp_package(package)]
    if not roots:
        return {}
    content = mcp_source(repo_root)
    return {root / MCP_CONFIG: Payload(content) for root in roots}


def component_payloads(root: Path) -> dict[Path, Payload]:
    """Stage the skills, agents and commands through their generators without touching the repo."""
    import generate_omp_agents as agents
    import generate_omp_commands as commands
    import generate_omp_skills as skills

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        skills.write_tree(staging / "skills", dry_run=False)
        agents.write_tree(staging / "agents", dry_run=False)
        commands.write_tree(staging / "commands", dry_run=False)
        return {
            root / path.relative_to(staging): Payload(path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }


def build_output(
    model: PackageModel,
    version: str,
    author: dict[str, str],
    *,
    include_unlisted: bool = False,
    components: ComponentSource = component_payloads,
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[Path, Payload], tuple[Path, ...]]:
    """Resolve the complete expected output and owned roots before any write.

    The ycc component trees are always expected: the sibling generators write them
    unconditionally, so a deferred ycc row only loses its manifests and catalog entry.
    """
    roots = tuple(dict.fromkeys((COMPONENT_ROOT, *native_package_roots(model.packages))))
    selected = native_packages(model.packages)
    output = manifest_payloads(selected, version, author)
    output.update(mcp_payloads(selected, repo_root))
    output.update(components(COMPONENT_ROOT))
    catalog = build_marketplace(model.packages, version, author, include_unlisted=include_unlisted)
    if catalog is not None:
        output[MARKETPLACE_PATH] = json_payload(catalog)
    return output, roots


# --- output plumbing (guard, write, prune, check) --------------------------


def guard_managed_paths(dest_root: Path, inventory: Iterable[Path], roots: Iterable[Path]) -> None:
    """Reject managed symlinks and file/directory conflicts before any mutation."""
    if dest_root.is_symlink() or (dest_root.exists() and not dest_root.is_dir()):
        raise ValueError(f"output root must be a non-symlink directory: {dest_root}")
    files = set(inventory) | {MARKETPLACE_PATH}
    owned = tuple(roots)
    for rel in (*files, *owned):
        for depth in range(1, len(rel.parts) + 1):
            prefix = Path(*rel.parts[:depth])
            path = dest_root / prefix
            if path.is_symlink():
                raise ValueError(f"managed-path symlink is not allowed: {prefix}")
            if prefix != rel and path.exists() and not path.is_dir():
                raise ValueError(f"managed parent is not a directory: {prefix}")
        if rel in files and (dest_root / rel).exists() and not (dest_root / rel).is_file():
            raise ValueError(f"managed output is not a regular file: {rel}")
    for rel in (*owned, CATALOG_DIR):
        path = dest_root / rel
        if path.exists() and not path.is_dir():
            raise ValueError(f"managed root is not a directory: {rel}")
        for directory, dirs, names in os.walk(path, followlinks=False):
            for name in dirs + names:
                candidate = Path(directory) / name
                if candidate.is_symlink():
                    raise ValueError(f"managed-path symlink is not allowed: {candidate.relative_to(dest_root)}")


def owned_files(dest_root: Path, roots: Iterable[Path]) -> set[Path]:
    """Every file under the owned package roots and the generator-owned catalog directory."""
    files: set[Path] = set()
    for rel in (*roots, CATALOG_DIR):
        if (dest_root / rel).is_dir():
            files.update(path.relative_to(dest_root) for path in (dest_root / rel).rglob("*") if path.is_file())
    return files


def extras(dest_root: Path, inventory: set[Path], roots: Iterable[Path]) -> set[Path]:
    found = owned_files(dest_root, roots) - inventory
    for rel in (*roots, CATALOG_DIR):
        root = dest_root / rel
        if not root.is_dir():
            continue
        for directory in (root, *root.rglob("*")):
            relative = directory.relative_to(dest_root)
            if directory.is_dir() and not any(relative in path.parents for path in inventory):
                found.add(relative)
    return found


def prune(dest_root: Path, inventory: set[Path], roots: Iterable[Path]) -> None:
    for rel in sorted(owned_files(dest_root, roots) - inventory):
        (dest_root / rel).unlink()
    for rel in (*roots, CATALOG_DIR):
        root = dest_root / rel
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if not any(root.iterdir()):
            root.rmdir()


def write_payloads(dest_root: Path, output: dict[Path, Payload], roots: tuple[Path, ...], dry_run: bool) -> set[Path]:
    inventory = set(output)
    guard_managed_paths(dest_root, inventory, roots)
    if dry_run:
        for rel in sorted(output):
            print(f"Would write {rel}")
        for rel in sorted(extras(dest_root, inventory, roots)):
            print(f"Would remove {rel}")
        return inventory
    for rel, payload in sorted(output.items()):
        path = dest_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != payload.content:
            path.write_bytes(payload.content)
        path.chmod(payload.mode)
    prune(dest_root, inventory, roots)
    return inventory


def check_payloads(dest_root: Path, output: dict[Path, Payload], roots: tuple[Path, ...]) -> list[str]:
    """Byte, executable-bit and extra-file drift for every generated OMP file.

    Like validate-omp-skills.sh, mode drift compares every execute bit, not the full mode:
    read/write bits follow the checkout umask.
    """
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
        if (path.stat().st_mode ^ payload.mode) & 0o111:
            diffs.append(f"executable-bit drift: {rel}")
    diffs.extend(f"extra in output: {rel}" for rel in sorted(extras(dest_root, inventory, roots)))
    return diffs


def expected_output(*, include_unlisted: bool = False) -> tuple[dict[Path, Payload], tuple[Path, ...]]:
    model = load_package_model()
    return build_output(model, native_version(model), manifest_author(), include_unlisted=include_unlisted)


def export_destination(dest_root: Path) -> Path:
    """An export must stay outside the checkout so it can never mix with repository output."""
    dest_root = dest_root.resolve()
    repo_root = REPO_ROOT.resolve()
    if dest_root == Path(dest_root.anchor):
        raise ValueError("export output must not be a filesystem root")
    if dest_root == repo_root or repo_root in dest_root.parents or dest_root in repo_root.parents:
        raise ValueError("export output must not overlap the repository")
    return dest_root


def run_check(dest_root: Path = REPO_ROOT, *, include_unlisted: bool = False) -> int:
    output, roots = expected_output(include_unlisted=include_unlisted)
    diffs = check_payloads(dest_root, output, roots)
    if diffs:
        print("OMP packages drift; run ./scripts/generate-omp-packages.sh", file=sys.stderr)
        for diff in diffs:
            print(f"  {diff}", file=sys.stderr)
    return int(bool(diffs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Exit 1 if generated output drifts (bytes, modes, extras)")
    modes.add_argument("--dry-run", action="store_true", help="Print what would be written or removed")
    parser.add_argument(
        "--export",
        type=Path,
        metavar="DIR",
        help="Write a repository-shaped tree outside the checkout; its catalog includes unlisted included rows",
    )
    args = parser.parse_args(argv)
    try:
        if args.export is not None:
            dest = export_destination(args.export)
            if args.check:
                return run_check(dest, include_unlisted=True)
            output, roots = expected_output(include_unlisted=True)
            write_payloads(dest, output, roots, args.dry_run)
            if not args.dry_run:
                print(f"Exported OMP packages under {dest}")
            return 0
        if args.check:
            return run_check()
        output, roots = expected_output()
        write_payloads(REPO_ROOT, output, roots, args.dry_run)
        if not args.dry_run:
            print(f"Wrote OMP native packages under {OUTPUT_ROOT}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"generate_omp_packages: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
