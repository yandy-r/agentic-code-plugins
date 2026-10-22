#!/usr/bin/env python3
"""Generate OMP (oh-my-pi) native packages and marketplace metadata from the package model (YAN-1171).

Each included native OMP row becomes a package root at packages/omp/<key>/ carrying:

- `.omp-plugin/plugin.json`: OMP keeps agent `model:` frontmatter only for roots with it;
- `.claude-plugin/plugin.json`: names the `/ycc:<skill>` command prefix under `--plugin-dir`
  and is the first manifest OMP reads for a relative source's install and upgrade version;
- `package.json`: the unique runtime package name OMP links under `plugins/node_modules/`;
- the component trees, staged through the existing generators (generate_omp_{skills,agents,commands});
- for an MCP-only row (ycc-mcp), a root `.mcp.json` built from mcp-configs/mcp.json. OMP falls
  back to `<root>/.mcp.json` when no manifest declares `mcpServers` and names each server
  `<package>:<server>`. OMP keeps only the first of servers with an equivalent connection
  (isSameMCPConnection), so a later http/sse server sharing an earlier one's connection gets
  `ycc-server=<name>` appended to its url query (YAN-1291: its own endpoint and OAuth login);
  a stdio duplicate fails closed. Unchanged sources keep their exact bytes. The result is
  audited for secret literals, and `${VAR}` placeholders are never expanded here: OMP expands
  them when it starts a server.
- for a rules-only row (ycc-rules), a flat `rules/` tree of `ycc-<family>-<stem>.md` files rendered
  from ycc/rules by generate_omp_rules.
- for the ycc row, the agent scope guard (YAN-1250): `extensions/scope-guard.ts`, copied from
  scripts/omp_templates/scope-guard.ts, and `extensions/agent-scopes.json`, the per-agent shell
  prefixes and MCP tools generate_omp_agents renders from ycc/agents (the same data renders each
  agent's `## Shell scope (OMP)` section). package.json declares it in `omp.extensions`, so OMP
  loads it at session start and blocks out-of-scope `bash` and MCP calls in ycc subagents. Both
  files ship with the component trees, so the agents never ship without their guard.
All manifests and the catalog entry carry the lockstep version from the model's version source.

Selection keys on runtime == "omp" and mechanism == "native". Only included rows are emitted,
and only the {skills, agents, commands, shared}, {mcp} and {rules} component sets have emitters
here; an included or listed row with any other set fails closed. Hooks never get an OMP emitter
(herdr's own integration; ADR 0002, YAN-1174); the scope guard is the one OMP extension ycc
ships; rules ship flat in `ycc-rules` (YAN-1175).
The root `.omp-plugin/marketplace.json` is written only when a row is listed and holds exactly
the listed rows with fork-safe relative sources; otherwise it is removed. `--export DIR` writes
a repository-shaped tree outside the checkout whose catalog also lists unlisted included rows,
for the opt-in live harness (scripts/test-omp-native-packages.sh) and the export validation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

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
RULES_DIR = Path("rules")
SOURCE_RULES_PATH = Path("ycc/rules")
CATALOG_NAME = "ycc"
MIN_OMP_VERSION = "18.12.2"
CATALOG_DESCRIPTION = f"ycc development-workflow packages for oh-my-pi (omp >={MIN_OMP_VERSION})."

# The component sets with an emitter in this generator. Any other set fails closed with the
# reason named here.
WORKFLOW_COMPONENTS = frozenset({"skills", "agents", "commands", "shared"})
MCP_COMPONENTS = frozenset({"mcp"})
RULES_COMPONENTS = frozenset({"rules"})
EMITTED_COMPONENT_SETS = (WORKFLOW_COMPONENTS, MCP_COMPONENTS, RULES_COMPONENTS)
COMPONENT_REASONS: dict[str, str] = {
    "hooks": (
        "ycc ships no OMP hooks: herdr session reporting is herdr's own OMP integration "
        "(`herdr integration install omp`) and WorktreeCreate has no OMP event (ADR 0002, YAN-1174); "
        "keep the row excluded and unlisted"
    ),
}
NO_PLANNED_EMITTER = "no planned issue; keep the row deferred and unlisted"
COMPONENT_DIRS = ("skills", "agents", "commands")
# generate_omp_{skills,agents,commands} write one tree, always under this package root.
WORKFLOW_PACKAGE = "ycc"
COMPONENT_ROOT = OUTPUT_ROOT / WORKFLOW_PACKAGE
# The agent scope guard (YAN-1250), shipped beside the component trees in the ycc root.
EXTENSION_DIR = Path("extensions")
SCOPE_GUARD = EXTENSION_DIR / "scope-guard.ts"
AGENT_SCOPES = EXTENSION_DIR / "agent-scopes.json"
SCOPE_GUARD_TEMPLATE = Path("scripts/omp_templates/scope-guard.ts")
SCOPE_SCHEMA_VERSION = 1
EXTENSION_ENTRIES = [f"./{SCOPE_GUARD.as_posix()}"]


@dataclass(frozen=True)
class Payload:
    content: bytes
    # Permission bits written to disk. Component files keep the mode their generator
    # produced so this generator and generate_omp_{skills,agents,commands} never fight
    # over it; drift checks compare bytes and executable bits only (see check_payloads).
    mode: int = 0o644


ComponentSource = Callable[[Path], dict[Path, Payload]]
GuardSource = Callable[[Path, list[str]], dict[Path, Payload]]


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
        if components not in EMITTED_COMPONENT_SETS:
            unsupported = components - WORKFLOW_COMPONENTS - MCP_COMPONENTS - RULES_COMPONENTS or components
            reasons = "; ".join(
                sorted({COMPONENT_REASONS.get(component, NO_PLANNED_EMITTER) for component in unsupported})
            )
            raise ValueError(f"{where}: no OMP emitter for components {sorted(components)}: {reasons}")
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
        package_json: dict[str, Any] = {
            "name": package.key,
            "version": version,
            "description": package.description,
            "private": True,
        }
        if package.key == WORKFLOW_PACKAGE:
            package_json["omp"] = {"extensions": EXTENSION_ENTRIES}
        output[root / PACKAGE_JSON] = json_payload(package_json)
    return output


def is_mcp_package(package: Package) -> bool:
    runtime = omp_runtime(package)
    return runtime is not None and frozenset(runtime.components) == MCP_COMPONENTS


def mcp_source(repo_root: Path = REPO_ROOT) -> bytes:
    """The audited source bytes; parsed only to fail closed, never expanded."""
    content = (repo_root / SOURCE_MCP_PATH).read_bytes()
    audit_no_secret_literals(load_mcp_config(content, SOURCE_MCP_PATH.as_posix()), SOURCE_MCP_PATH.as_posix())
    return content


def mcp_transport(server: Mapping[str, Any]) -> str:
    """omp's transport fallback: the declared `type`, else stdio with a command, http with a url."""
    declared = server.get("type")
    if isinstance(declared, str) and declared:
        return declared
    return "stdio" if server.get("command") else "http" if server.get("url") else "stdio"


def mcp_connection_key(server: Mapping[str, Any]) -> str:
    """The fields omp's isSameMCPConnection compares (capability/mcp.ts) for a plugin server, as a stable key.

    auth and oauth always count; then url and headers for http/sse, or command, args, env and cwd
    for stdio. requestIdFormat is left out: omp's plugin loader (discovery/claude-plugins.ts) drops it,
    so every plugin server compares as the default. A plugin's stdio env is all-literal, so the
    literal-key sets match whenever env does.
    """
    transport = mcp_transport(server)
    fields = ("command", "args", "env", "cwd") if transport == "stdio" else ("url", "headers")
    shared = [server.get("auth"), server.get("oauth")]
    return json.dumps([transport, shared, [server.get(key) for key in fields]], sort_keys=True)


def with_server_query(url: str, name: str) -> str:
    parts = urlsplit(url)
    marker = urlencode({"ycc-server": name})
    return urlunsplit(parts._replace(query=f"{parts.query}&{marker}" if parts.query else marker))


def omp_mcp_bytes(source: bytes) -> bytes:
    """The OMP `.mcp.json`: every source server reachable under its own name (YAN-1291).

    A later http/sse server whose connection equals an earlier one's gets `ycc-server=<name>`
    appended to its url query; a stdio duplicate raises. Unchanged input returns `source`; a
    changed url is patched in place so every other byte stays the source's, falling back to
    `json.dumps(indent=2)` only when the patched text would not parse back to the same config.
    """
    where = SOURCE_MCP_PATH.as_posix()
    config = load_mcp_config(source, where)
    owners: dict[str, str] = {}
    renamed: list[tuple[str, str, str]] = []
    for name, server in config["mcpServers"].items():
        if not isinstance(server, dict):
            raise ValueError(f"{where}: {name}: server must be an object")
        first = owners.get(mcp_connection_key(server))
        if first is not None:
            if mcp_transport(server) == "stdio":
                raise ValueError(f"{name}: same stdio connection as {first}; OMP would shadow it")
            url = server.get("url")
            if not isinstance(url, str):
                raise ValueError(f"{where}: {name}: {mcp_transport(server)} server without a url")
            server["url"] = with_server_query(url, name)
            renamed.append((name, url, server["url"]))
            if mcp_connection_key(server) in owners:
                raise ValueError(f"{name}: same connection as {owners[mcp_connection_key(server)]} after ycc-server")
        owners[mcp_connection_key(server)] = name
    if not renamed:
        audit_no_secret_literals(config, where)
        return source
    content = patch_urls(source, renamed)
    if content is None or load_mcp_config(content, where) != config:
        content = (json.dumps(config, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    audit_no_secret_literals(load_mcp_config(content, where), where)
    return content


def patch_urls(source: bytes, renamed: Iterable[tuple[str, str, str]]) -> bytes | None:
    """Replace each renamed server's url literal in place; None when a literal cannot be found."""
    text = source.decode("utf-8")
    cursor = 0
    for name, old, new in renamed:
        server = re.compile(rf"{re.escape(json.dumps(name))}\s*:\s*\{{").search(text, cursor)
        if server is None:
            return None
        url = re.compile(rf'"url"\s*:\s*({re.escape(json.dumps(old))})').search(text, server.end())
        if url is None:
            return None
        literal = json.dumps(new, ensure_ascii=False)
        text = text[: url.start(1)] + literal + text[url.end(1) :]
        cursor = url.start(1) + len(literal)
    return text.encode("utf-8")


def mcp_payloads(packages: Iterable[Package], repo_root: Path = REPO_ROOT) -> dict[Path, Payload]:
    roots = [package_root(package) for package in packages if is_mcp_package(package)]
    if not roots:
        return {}
    content = omp_mcp_bytes(mcp_source(repo_root))
    return {root / MCP_CONFIG: Payload(content) for root in roots}


def is_rules_package(package: Package) -> bool:
    runtime = omp_runtime(package)
    return runtime is not None and frozenset(runtime.components) == RULES_COMPONENTS


def rules_payloads(packages: Iterable[Package], repo_root: Path = REPO_ROOT) -> dict[Path, Payload]:
    """The flat OMP rules for every rules-only row, rendered from ycc/rules."""
    roots = [package_root(package) for package in packages if is_rules_package(package)]
    if not roots:
        return {}
    import generate_omp_rules

    rules = generate_omp_rules.build_rules(repo_root / SOURCE_RULES_PATH)
    return {root / RULES_DIR / name: Payload(text.encode("utf-8")) for root in roots for name, text in rules.items()}


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


def scope_guard_payloads(root: Path, mcp_namespaces: list[str]) -> dict[Path, Payload]:
    """The scope guard extension and the agent scope data it enforces (YAN-1250)."""
    import generate_omp_agents as agents

    scopes = {
        "schemaVersion": SCOPE_SCHEMA_VERSION,
        "mcpNamespaces": mcp_namespaces,
        "agents": agents.agent_scopes(),
    }
    return {
        root / SCOPE_GUARD: Payload((REPO_ROOT / SCOPE_GUARD_TEMPLATE).read_bytes()),
        root / AGENT_SCOPES: json_payload(scopes),
    }


def build_output(
    model: PackageModel,
    version: str,
    author: dict[str, str],
    *,
    include_unlisted: bool = False,
    components: ComponentSource = component_payloads,
    guard: GuardSource = scope_guard_payloads,
    repo_root: Path = REPO_ROOT,
) -> tuple[dict[Path, Payload], tuple[Path, ...]]:
    """Resolve the complete expected output and owned roots before any write.

    The ycc component trees and their scope guard are always expected: the sibling generators
    write the trees unconditionally, so a deferred ycc row only loses its manifests and catalog
    entry. OMP names a plugin MCP server `<package>:<server>`, so every modeled MCP package key is
    a namespace the guard accepts in front of a declared server.
    """
    roots = tuple(dict.fromkeys((COMPONENT_ROOT, *native_package_roots(model.packages))))
    selected = native_packages(model.packages)
    output = manifest_payloads(selected, version, author)
    output.update(mcp_payloads(selected, repo_root))
    output.update(rules_payloads(selected, repo_root))
    output.update(components(COMPONENT_ROOT))
    output.update(guard(COMPONENT_ROOT, sorted(package.key for package in model.packages if is_mcp_package(package))))
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
