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
- closure: the ycc root holds only manifests, skills/agents/commands and the scope guard; every
  source skill, agent and the shared stub ship; every command has its skill; every skill://
  reference resolves;
- MCP closure: an MCP-only root (ycc-mcp) holds only its manifests and `.mcp.json`, which is
  byte-identical to generate_omp_packages.omp_mcp_bytes(mcp-configs/mcp.json) (YAN-1291: a
  later http/sse duplicate connection carries `ycc-server=<name>`), parses with an `mcpServers`
  object, and carries no secret literal (credential keys hold only `${VAR}` placeholders);
- rules closure (YAN-1175): a rules-only root (ycc-rules) holds only its manifests and a flat
  `rules/` of regular `ycc-*.md` files (no subdirectories or symlinks) whose names and bytes
  equal generate_omp_rules' rendering of ycc/rules;
- code surfaces (YAN-1174, YAN-1250): the only OMP code is the ycc agent scope guard. The ycc
  package.json must declare exactly `omp.extensions: ["./extensions/scope-guard.ts"]` (agents never
  ship without their guard), and `extensions/` must hold exactly scope-guard.ts (the template
  bytes) and agent-scopes.json. ycc ships no OMP hooks: herdr session reporting is herdr's own
  integration (`herdr integration install omp`) and WorktreeCreate has no OMP event (ADR 0002).
  Any other package.json `extensions`/`hooks`/`tools` key (top level or under `omp`/`pi`), the
  same keys in a plugin manifest, a top-level hooks/, extensions/ or tools/ directory, any
  hooks.json, and any JS/TS module outside skills/ are rejected;
- hook verdicts (YAN-1174, checkout only): every ycc lifecycle-hook source and registration
  has an entry in HOOK_VERDICTS and no entry is stale; the spike dossier's §3 matrix row for
  each entry holds its verdict token; no OMP contract doc promises a ycc herdr shim.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import generate_omp_packages as generator
import generate_omp_rules
from mcp_secret_audit import audit_no_secret_literals, load_mcp_config
from package_model import Package, PackageModel, load_package_model

# omp marketplace/types.ts NAME_RE / MAX_NAME_LENGTH, manager.ts RUNTIME_PACKAGE_NAME_RE.
NAME_SEGMENT = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$")
MAX_NAME_LENGTH = 64
RUNTIME_PACKAGE_NAME = re.compile(r"^(?:@[a-zA-Z0-9][a-zA-Z0-9._~-]*/)?[a-zA-Z0-9][a-zA-Z0-9._~-]*$")
ROOT_ENTRIES = frozenset(
    {".omp-plugin", ".claude-plugin", "package.json", *generator.COMPONENT_DIRS, generator.EXTENSION_DIR.name}
)
MCP_ROOT_ENTRIES = frozenset({".omp-plugin", ".claude-plugin", "package.json", generator.MCP_CONFIG.name})
RULES_ROOT_ENTRIES = frozenset({".omp-plugin", ".claude-plugin", "package.json", generator.RULES_DIR.name})
SKILL_REF = re.compile(r"skill://([A-Za-z0-9][A-Za-z0-9-]*)(/[^\s`'\"()\[\]|,;<>]*)?")
PATTERN_CHARS = frozenset("*?[]{}$<>")
SKILL_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)

# Keys in package.json (top level, and under "omp"/"pi") and plugin manifests that load code in OMP.
CODE_SURFACE_KEYS = frozenset({"extensions", "hooks", "tools"})
CODE_SURFACE_DIRS = frozenset({"hooks", "extensions", "tools"})
CODE_SUFFIXES = (".ts", ".js", ".mjs", ".cjs")
CODE_SURFACE_MESSAGE = (
    "ycc OMP packages ship no hooks or extensions besides the ycc agent scope guard "
    "(herdr reporting is herdr's own integration; ADR 0002)"
)
GUARD_FILES = frozenset({generator.SCOPE_GUARD, generator.AGENT_SCOPES})
PLUGIN_MANIFESTS = (Path(".omp-plugin/plugin.json"), Path(".claude-plugin/plugin.json"))

# Every ycc lifecycle-hook registration -> (OMP verdict token, row anchor in the spike §3 matrix).
# Keys are "<source file>" or "<registration file>#<event>"; hook_verdict_errors derives the live
# set from HOOK_SOURCE_DIR, HOOK_SOURCE_FILES and the HOOK_REGISTRATIONS events, and requires equality.
HOOK_VERDICTS: dict[str, tuple[str, str]] = {
    "ycc/settings/hooks/worktree-create.sh": ("**unsupported**", "`worktree-create.sh` (`WorktreeCreate`)"),
    "ycc/settings/hooks/herdr-agent-state.sh": ("**n/a**", "`ycc/settings/hooks/herdr-agent-state.sh`"),
    "ycc/settings/cursor/herdr-session-start.sh": ("**native**", "herdr session reporting"),
    "ycc/settings/cursor/hooks.json#sessionStart": ("**native**", "`ycc/settings/cursor/hooks.json`"),
    "ycc/settings/settings.json#WorktreeCreate": ("**unsupported**", "`worktree-create.sh` (`WorktreeCreate`)"),
    "packages/claude/ycc-hooks/hooks/hooks.json#WorktreeCreate": ("**unsupported**", "Package `ycc-hooks`"),
}
HOOK_SOURCE_DIR = Path("ycc/settings/hooks")
HOOK_SOURCE_FILES = (Path("ycc/settings/cursor/herdr-session-start.sh"),)
HOOK_REGISTRATIONS = (
    Path("ycc/settings/cursor/hooks.json"),
    Path("ycc/settings/settings.json"),
    Path("packages/claude/ycc-hooks/hooks/hooks.json"),
)
SPIKE_DOSSIER = Path("docs/internal/spikes/omp-runtime-contract.md")
HOOK_DOCS = (
    Path("docs/internal/adr/0002-omp-runtime-contract.md"),
    Path("docs/install/omp.md"),
    Path("ycc/skills/_shared/references/target-capability-matrix.md"),
)
# Phrases that promise the ycc OMP herdr reporter YAN-1174 ruled out.
SHIM_PHRASES = (
    "session_start shim",
    "herdr extension shim",
    "session_start` extension shim",
    "herdr `session_start` shim",
)
TABLE_CELL_SPLIT = re.compile(r"(?<!\\)\|")


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


def code_key_errors(rel: Path, payload: dict[str, Any], *, nested: bool, guard: bool = False) -> list[str]:
    keys = [key for key in sorted(CODE_SURFACE_KEYS) if key in payload]
    errors: list[str] = []
    if nested:
        for scope in ("omp", "pi"):
            section = payload.get(scope)
            if not isinstance(section, dict):
                continue
            for key in sorted(CODE_SURFACE_KEYS):
                if key not in section:
                    continue
                if guard and scope == "omp" and key == "extensions":
                    if section[key] != generator.EXTENSION_ENTRIES:
                        errors.append(f"{rel}#omp.extensions: must be exactly {generator.EXTENSION_ENTRIES}")
                    continue
                keys.append(f"{scope}.{key}")
    if guard and not (isinstance(payload.get("omp"), dict) and "extensions" in payload["omp"]):
        errors.append(f"{rel}#omp.extensions: missing; ycc agents must not ship without the scope guard")
    return [*errors, *(f"{rel}#{key}: {CODE_SURFACE_MESSAGE}" for key in keys)]


def scope_guard_errors(root: Path) -> list[str]:
    """The ycc root ships exactly the generated scope guard, with the template's bytes."""
    base = root / generator.COMPONENT_ROOT
    errors: list[str] = []
    for rel in sorted(GUARD_FILES):
        path = base / rel
        if path.is_symlink() or not path.is_file():
            errors.append(f"{generator.COMPONENT_ROOT / rel}: missing scope guard file")
    template = generator.REPO_ROOT / generator.SCOPE_GUARD_TEMPLATE
    guard = base / generator.SCOPE_GUARD
    if guard.is_file() and guard.read_bytes() != template.read_bytes():
        errors.append(
            f"{generator.COMPONENT_ROOT / generator.SCOPE_GUARD}: must equal {generator.SCOPE_GUARD_TEMPLATE}"
        )
    scopes = base / generator.AGENT_SCOPES
    if scopes.is_file():
        try:
            payload = load_object(scopes)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if payload.get("schemaVersion") != generator.SCOPE_SCHEMA_VERSION or not isinstance(
                payload.get("agents"), dict
            ):
                errors.append(f"{generator.COMPONENT_ROOT / generator.AGENT_SCOPES}: malformed scope data")
    return errors


def hook_surface_errors(root: Path, model: PackageModel) -> list[str]:
    """No OMP package root may carry code OMP loads (extensions, hooks, tools) besides the scope guard."""
    errors: list[str] = []
    roots = dict.fromkeys((*generator.native_package_roots(model.packages), generator.COMPONENT_ROOT))
    for package_root in roots:
        base = root / package_root
        if not base.is_dir():
            continue
        guarded = package_root == generator.COMPONENT_ROOT
        manifests = ((generator.PACKAGE_JSON, True), *((manifest, False) for manifest in PLUGIN_MANIFESTS))
        for manifest, nested in manifests:
            if not (base / manifest).is_file():
                continue
            try:
                payload = load_object(base / manifest)
            except ValueError as exc:
                errors.append(f"{package_root / manifest}: {exc}")
                continue
            errors.extend(code_key_errors(package_root / manifest, payload, nested=nested, guard=guarded and nested))
        if guarded and (base / "agents").is_dir():
            errors.extend(scope_guard_errors(root))
        for entry in sorted(base.iterdir()):
            if (
                entry.is_dir()
                and entry.name in CODE_SURFACE_DIRS
                and not (guarded and entry.name == generator.EXTENSION_DIR.name)
            ):
                errors.append(f"{package_root / entry.name}: {CODE_SURFACE_MESSAGE}")
        for path in sorted(base.rglob("*")):
            if not path.is_file() and not path.is_symlink():
                continue
            rel = path.relative_to(base)
            if guarded and rel.parts[0] == generator.EXTENSION_DIR.name:
                if rel not in GUARD_FILES or path.is_symlink():
                    errors.append(f"{package_root / rel}: {CODE_SURFACE_MESSAGE}")
                continue
            if rel.parts[0] in CODE_SURFACE_DIRS:
                continue  # reported once as a directory above
            if path.name == "hooks.json" or (path.suffix in CODE_SUFFIXES and rel.parts[0] != "skills"):
                errors.append(f"{package_root / rel}: {CODE_SURFACE_MESSAGE}")
    return errors


def registered_events(source_root: Path, registration: Path) -> tuple[list[str], list[str]]:
    """``(events, errors)`` for the ``hooks`` object of one JSON hook registration file."""
    path = source_root / registration
    if not path.is_file():
        return [], []
    try:
        hooks = load_object(path).get("hooks", {})
    except ValueError as exc:
        return [], [str(exc)]
    if not isinstance(hooks, dict):
        return [], [f"{registration}: hooks must be an object"]
    return [f"{registration}#{event}" for event in hooks], []


def live_hook_keys(source_root: Path) -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    errors: list[str] = []
    hook_dir = source_root / HOOK_SOURCE_DIR
    if hook_dir.is_dir():
        keys.update(str(HOOK_SOURCE_DIR / path.name) for path in hook_dir.iterdir() if path.is_file())
    keys.update(str(path) for path in HOOK_SOURCE_FILES if (source_root / path).is_file())
    for registration in HOOK_REGISTRATIONS:
        events, problems = registered_events(source_root, registration)
        keys.update(events)
        errors.extend(problems)
    return keys, errors


def dossier_verdict_errors(source_root: Path) -> list[str]:
    try:
        lines = (source_root / SPIKE_DOSSIER).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{SPIKE_DOSSIER}: unreadable: {exc}"]
    # A §3 matrix row: | component | Claude form | OMP surface | verdict | ...
    rows = [cells for line in lines if line.startswith("|") and len(cells := TABLE_CELL_SPLIT.split(line)) > 4]
    errors: list[str] = []
    for key, (token, anchor) in sorted(HOOK_VERDICTS.items()):
        matches = [cells for cells in rows if anchor in cells[1]]
        if not matches:
            errors.append(f"{SPIKE_DOSSIER}: no §3 matrix row for {key} (anchor {anchor!r})")
        elif not any(token in cells[4] for cells in matches):
            errors.append(f"{SPIKE_DOSSIER}: §3 row {anchor!r} verdict must hold {token} for {key}")
    return errors


def shim_phrase_errors(source_root: Path) -> list[str]:
    errors: list[str] = []
    for doc in (*HOOK_DOCS, SPIKE_DOSSIER):
        try:
            text = (source_root / doc).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            errors.append(f"{doc}: unreadable: {exc}")
            continue
        lowered = text.lower()
        errors.extend(
            f"{doc}: promises a ycc OMP herdr reporter ({phrase!r}); ycc ships no OMP hooks (YAN-1174)"
            for phrase in SHIM_PHRASES
            if phrase.lower() in lowered
        )
    return errors


def hook_verdict_errors(source_root: Path) -> list[str]:
    """Every ycc hook has exactly one OMP verdict that the spike matrix states, and no doc promises a shim."""
    live, errors = live_hook_keys(source_root)
    errors.extend(
        f"{key}: ycc hook has no OMP verdict; add it to HOOK_VERDICTS and the spike §3 matrix"
        for key in sorted(live - HOOK_VERDICTS.keys())
    )
    errors.extend(
        f"{key}: stale HOOK_VERDICTS entry; the hook source or registration no longer exists"
        for key in sorted(HOOK_VERDICTS.keys() - live)
    )
    errors.extend(dossier_verdict_errors(source_root))
    errors.extend(shim_phrase_errors(source_root))
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
    allowed = ROOT_ENTRIES if has_manifests else frozenset((*generator.COMPONENT_DIRS, generator.EXTENSION_DIR.name))
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


def mcp_closure_errors(root: Path, source_root: Path, package: Package) -> list[str]:
    rel = generator.package_root(package)
    package_root = root / rel
    if not package_root.is_dir():
        return [f"{rel}: missing package root"]
    errors = [
        f"{rel / entry.name}: unexpected entry outside the manifests and {generator.MCP_CONFIG}"
        for entry in sorted(package_root.iterdir())
        if entry.name not in MCP_ROOT_ENTRIES
    ]
    config_rel = rel / generator.MCP_CONFIG
    config_path = root / config_rel
    if config_path.is_symlink() or not config_path.is_file():
        return [*errors, f"{config_rel}: missing MCP configuration"]
    content = config_path.read_bytes()
    try:
        expected: bytes | None = generator.omp_mcp_bytes((source_root / generator.SOURCE_MCP_PATH).read_bytes())
    except ValueError as exc:
        errors.append(f"{generator.SOURCE_MCP_PATH}: {exc}")
        expected = None
    if expected is not None and content != expected:
        errors.append(f"{config_rel}: must equal the OMP rendering of {generator.SOURCE_MCP_PATH}")
    try:
        config = load_mcp_config(content, config_rel.as_posix())
        audit_no_secret_literals(config, config_rel.as_posix())
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def rules_closure_errors(root: Path, source_root: Path, package: Package) -> list[str]:
    rel = generator.package_root(package)
    package_root = root / rel
    if not package_root.is_dir():
        return [f"{rel}: missing package root"]
    errors = [
        f"{rel / entry.name}: unexpected entry outside the manifests and {generator.RULES_DIR}/"
        for entry in sorted(package_root.iterdir())
        if entry.name not in RULES_ROOT_ENTRIES
    ]
    rules_rel = rel / generator.RULES_DIR
    rules_dir = root / rules_rel
    if rules_dir.is_symlink() or not rules_dir.is_dir():
        return [*errors, f"{rules_rel}: missing rules directory"]
    try:
        expected = generate_omp_rules.build_rules(source_root / generator.SOURCE_RULES_PATH)
    except ValueError as exc:
        return [*errors, f"{generator.SOURCE_RULES_PATH}: {exc}"]
    actual: set[str] = set()
    for entry in sorted(rules_dir.iterdir()):
        entry_rel = rules_rel / entry.name
        if entry.is_symlink() or not entry.is_file():
            errors.append(f"{entry_rel}: rules/ holds only regular files (no subdirectories or symlinks)")
        elif not (entry.name.startswith(generate_omp_rules.RULE_PREFIX) and entry.suffix == ".md"):
            errors.append(f"{entry_rel}: rule files must be named {generate_omp_rules.RULE_PREFIX}*.md")
        elif entry.name not in expected:
            errors.append(f"{entry_rel}: no source rule under {generator.SOURCE_RULES_PATH}")
        else:
            actual.add(entry.name)
            if entry.read_bytes() != expected[entry.name].encode("utf-8"):
                errors.append(f"{entry_rel}: drifted from {generator.SOURCE_RULES_PATH}")
    errors.extend(f"{rules_rel / name}: missing rule" for name in sorted(set(expected) - actual))
    return errors


def validate(root: Path, model: PackageModel, *, source_root: Path | None = None, export: bool = False) -> list[str]:
    """Every OMP package policy violation under ``root`` (a checkout, or an export with ``export``)."""
    source = root if source_root is None else source_root
    version = generator.native_version(model, source)
    packages = generator.native_packages(model.packages)
    errors = catalog_errors(root, model, version, export=export)
    errors.extend(manifest_errors(root, packages, version))
    errors.extend(inactive_root_errors(root, model, packages))
    errors.extend(hook_surface_errors(root, model))
    has_manifests = generator.WORKFLOW_PACKAGE in {package.key for package in packages}
    errors.extend(closure_errors(root, source, has_manifests=has_manifests))
    for package in packages:
        if generator.is_mcp_package(package):
            errors.extend(mcp_closure_errors(root, source, package))
        elif generator.is_rules_package(package):
            errors.extend(rules_closure_errors(root, source, package))
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
            errors.extend(hook_verdict_errors(root))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"validate_omp_native: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"validate_omp_native: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
