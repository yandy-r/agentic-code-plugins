#!/usr/bin/env python3
"""Build and validate the hidden v7 Claude split: skills-only `ycc` plus agents-only `ycc-agents`.

Nothing here is user-reachable. The split tree is built on demand into a caller-supplied
directory (never committed) and feeds only `--check` and the opt-in live harness
(scripts/test-claude-agents-split.sh). Reference detection is
package_graph_extract.iter_references, the same detector the package graph uses, so the
rewrite targets exactly the dispatch, handoff and mention edges the graph knows.

Split rules: agent references in dispatch contexts and `ycc:<agent>` mentions become
`ycc-agents:<frontmatter-name>`; built-in agents stay bare; `ycc:<skill>`, `/ycc:<skill>`
and bare skill names are untouched. `ycc` keeps its manifest name and depends on `ycc-agents`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_package_graph import agent_reach  # noqa: E402
from package_graph_extract import (  # noqa: E402
    BUILTIN_AGENTS,
    NAME,
    Reference,
    agent_frontmatter,
    extract_graph,
    iter_references,
)

SKILLS_PACKAGE = "ycc"
AGENTS_PACKAGE = "ycc-agents"
AGENTS_PREFIX = AGENTS_PACKAGE + ":"
LAB_MARKET = "ycc-split-lab"
MANIFEST = Path(".claude-plugin/plugin.json")
MARKETPLACE = Path(".claude-plugin/marketplace.json")
MODEL = Path("settings/packages.json")
# Shell reach-ins to the plugin's own agents/ directory; the split ycc has none. Absolute forms
# go through a *PLUGIN_ROOT variable; relative forms climb exactly the file's depth below the root.
AGENTS_DIR_REACH = re.compile(r"PLUGIN_ROOT(?::-[^}]*)?(?:%/)?\}?\"?/agents(?![\w.-])")
RELATIVE_AGENTS_REACH = re.compile(r"(?<![\w.])((?:\.\./)+)agents(?![\w.-])")
QUALIFIED_SKILL = re.compile(r"^ycc:([a-z][a-z0-9-]*)$")
# Bare agent names that are NOT agent references and must stay bare, keyed by path under
# skills/ (prefix match); None means every agent name. Everything else bare is rewritten.
ROLE_NAMES: dict[str, frozenset[str] | None] = {
    # Persona/teammate names: the `architect` persona dispatches ycc-agents:planner.
    "plan/": frozenset({"architect"}),
    # Teammate/description role names; their subagent_type is another agent.
    "feature-research/": frozenset({"practices-researcher"}),
    "prp-plan/SKILL.md": frozenset({"practices-researcher"}),
    "prp-plan/references/": frozenset({"practices-researcher"}),
    # Category keys are Cursor agent file stems scanned from ~/.cursor/agents, not dispatch values.
    "init/scripts/generate-agent-catalog.sh": None,
}


def role_names(skill_path: str) -> frozenset[str] | None:
    """Bare names allowed in one file (path relative to skills/); None allows every agent name."""
    allowed: set[str] = set()
    for prefix, names in ROLE_NAMES.items():
        if skill_path.startswith(prefix):
            if names is None:
                return None
            allowed |= names
    return frozenset(allowed)


def is_role_name(ref: Reference, allowed: frozenset[str] | None) -> bool:
    """A bare (unnamespaced) agent name the allowlist keeps as a role name or file stem."""
    return ref.role == "agent" and ref.token == ref.name and (allowed is None or ref.name in allowed)


class SplitError(Exception):
    """A source reference or layout the split cannot represent."""


@dataclass
class SplitReport:
    """Exact rewrite counts for one build, plus validator findings."""

    version: str
    skills: int = 0
    agents: int = 0
    rewritten_dispatches: int = 0
    rewritten_mentions: int = 0
    rewritten_handoffs: int = 0
    builtin_dispatches: int = 0
    dispatching_skills: dict[str, tuple[str, ...]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One stable line per count, then errors."""
        lines = [
            f"version: {self.version}",
            f"skills (split ycc): {self.skills}",
            f"agents (ycc-agents): {self.agents}",
            f"rewritten dispatch tokens (skills): {self.rewritten_dispatches}",
            f"rewritten ycc:<agent> mentions (skills): {self.rewritten_mentions}",
            f"rewritten agent handoffs (agents): {self.rewritten_handoffs}",
            f"builtin dispatches kept bare: {self.builtin_dispatches}",
            f"dispatching skills: {len(self.dispatching_skills)}",
        ]
        lines += [f"ERROR: {error}" for error in self.errors]
        return "\n".join(lines)


@dataclass(frozen=True)
class Catalog:
    """Source names: skills, and agent aliases (frontmatter name or file stem) to frontmatter name."""

    skills: frozenset[str]
    aliases: dict[str, str]

    @property
    def agents(self) -> frozenset[str]:
        return frozenset(self.aliases.values())


def load_catalog(source_root: Path) -> Catalog:
    """Index skill directories and agent frontmatter names; stems alias only when unambiguous."""
    skills = frozenset(p.parent.name for p in (source_root / "skills").glob("*/SKILL.md") if p.parent.name != "_shared")
    paths = sorted((source_root / "agents").glob("*.md"))
    names: dict[Path, str] = {}
    for path in paths:
        name, _ = agent_frontmatter(path.read_text(encoding="utf-8"))
        if not NAME.fullmatch(name):
            raise SplitError(f"{path}: invalid agent frontmatter name {name!r}")
        names[path] = name
    aliases = {name: name for name in names.values()}
    for path, name in names.items():
        aliases.setdefault(path.stem, name)
    return Catalog(skills, aliases)


def is_placeholder(name: str) -> bool:
    return "<" in name or "{{" in name


def split_token(ref: Reference, catalog: Catalog, where: str) -> str | None:
    """Return the split spelling of one reference, or None to keep it byte-for-byte."""
    if ref.role == "skill":
        return None
    name = ref.name
    if ref.role == "dispatch" and is_placeholder(name):
        return None
    if ref.role == "dispatch" and name in BUILTIN_AGENTS:
        return None if ref.token == name else name
    target = catalog.aliases.get(name)
    if target is None:
        raise SplitError(f"{where}: {ref.role} target {ref.token!r} is neither a known agent nor a builtin")
    token = AGENTS_PREFIX + target
    return None if token == ref.token else token


def rewrite_text(
    text: str, catalog: Catalog, where: str, *, shell: bool = False, allowed: frozenset[str] | None = frozenset()
) -> tuple[str, list[tuple[Reference, str]]]:
    """Apply split_token to every reference except allowed role names; returns new text and rewrites."""
    lines = text.splitlines(keepends=True)
    applied: list[tuple[Reference, str]] = []
    references = iter_references(text, catalog.skills, catalog.agents, shell=shell)
    for ref in sorted(references, key=lambda r: (r.line, -r.start)):
        if is_role_name(ref, allowed):
            continue
        token = split_token(ref, catalog, f"{where}:{ref.line}")
        if token is None:
            continue
        line = lines[ref.line - 1]
        lines[ref.line - 1] = line[: ref.start] + token + line[ref.end :]
        applied.append((ref, token))
    return "".join(lines), applied


def source_files(directory: Path) -> Iterator[Path]:
    """Files the package graph scans: hidden segments and bytecode caches excluded."""
    for path in sorted(directory.rglob("*")):
        parts = path.relative_to(directory).parts
        if path.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in parts):
            yield path


def write_file(path: Path, data: bytes, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, 0o755 if executable else 0o644)


def write_json(path: Path, value: Any) -> None:
    write_file(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), False)


def copy_tree(source: Path, dest: Path, catalog: Catalog, files: Iterator[Path]) -> list[Reference]:
    """Copy files, rewriting text references; returns the references that were rewritten."""
    rewritten: list[Reference] = []
    for path in files:
        raw = path.read_bytes()
        relative = path.relative_to(source).as_posix()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            data = raw  # Binary assets carry no textual references.
        else:
            allowed = role_names(relative) if source.name == "skills" else frozenset()
            where = path.relative_to(source.parent).as_posix()
            new, applied = rewrite_text(text, catalog, where, shell=path.suffix == ".sh", allowed=allowed)
            rewritten += [ref for ref, _ in applied]
            data = new.encode("utf-8")
        write_file(dest / relative, data, bool(path.stat().st_mode & 0o100))
    return rewritten


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SplitError(f"{path}: expected a JSON object")
    return value


def manifests(source_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Lockstep split manifests from the canonical manifest and the ycc-agents model row."""
    source = read_object(source_root / MANIFEST)
    version, author = source.get("version"), source.get("author")
    if not isinstance(version, str) or not version or not isinstance(author, dict):
        raise SplitError(f"{source_root / MANIFEST}: missing version or author")
    row = read_object(source_root / MODEL).get("packages", {}).get(AGENTS_PACKAGE)
    if not isinstance(row, dict) or not isinstance(row.get("description"), str):
        raise SplitError(f"{source_root / MODEL}: missing {AGENTS_PACKAGE} description")
    skills = {
        "name": SKILLS_PACKAGE,
        "version": version,
        "description": source.get("description", ""),
        "author": author,
        "dependencies": [AGENTS_PACKAGE],
    }
    agents = {"name": AGENTS_PACKAGE, "version": version, "description": row["description"], "author": author}
    return skills, agents


def build_split(source_root: Path, out_dir: Path) -> SplitReport:
    """Write out_dir/{ycc,ycc-agents} and a lab marketplace; fail on unknown dispatch targets."""
    graph, graph_errors = extract_graph(source_root)
    if graph_errors:
        raise SplitError("source package graph has errors:\n" + "\n".join(graph_errors))
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SplitError(f"{out_dir}: output directory must be empty")
    catalog = load_catalog(source_root)
    skills_manifest, agents_manifest = manifests(source_root)
    skills_root, agents_root = out_dir / SKILLS_PACKAGE, out_dir / AGENTS_PACKAGE
    skill_refs = copy_tree(
        source_root / "skills", skills_root / "skills", catalog, source_files(source_root / "skills")
    )
    agent_files = iter(sorted((source_root / "agents").glob("*.md")))
    agent_refs = copy_tree(source_root / "agents", agents_root / "agents", catalog, agent_files)
    write_json(skills_root / MANIFEST, skills_manifest)
    write_json(agents_root / MANIFEST, agents_manifest)
    write_json(
        out_dir / MARKETPLACE,
        {
            "name": LAB_MARKET,
            "description": "Hidden v7 lab catalog: skills-only ycc depending on agents-only ycc-agents.",
            "owner": skills_manifest["author"],
            "plugins": [{"name": key, "source": f"./{key}"} for key in (SKILLS_PACKAGE, AGENTS_PACKAGE)],
        },
    )
    builtins = 0
    for path in source_files(skills_root / "skills"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        builtins += sum(r.role == "dispatch" and r.name in BUILTIN_AGENTS for r in iter_references(text, set(), set()))
    return SplitReport(
        version=skills_manifest["version"],
        skills=len(catalog.skills),
        agents=len(catalog.agents),
        rewritten_dispatches=sum(r.role == "dispatch" for r in skill_refs),
        rewritten_mentions=sum(r.role != "dispatch" for r in skill_refs),
        rewritten_handoffs=len(agent_refs),
        builtin_dispatches=builtins,
        dispatching_skills={k.removeprefix("skill:"): v for k, v in agent_reach(graph).items()},
    )


# --- validator ---------------------------------------------------------------------------


def _layout_errors(out_dir: Path) -> list[str]:
    """Rule (d) plus manifest identity, lockstep version, dependency and catalog shape."""
    errors: list[str] = []
    skills_root, agents_root = out_dir / SKILLS_PACKAGE, out_dir / AGENTS_PACKAGE
    if (skills_root / "agents").exists():
        errors.append("split ycc must not contain an agents/ directory")
    if (agents_root / "skills").exists():
        errors.append("ycc-agents must not contain a skills/ directory")
    try:
        skills, agents = read_object(skills_root / MANIFEST), read_object(agents_root / MANIFEST)
        catalog = read_object(out_dir / MARKETPLACE)
    except (OSError, ValueError, SplitError) as exc:
        return [*errors, f"unreadable split manifest: {exc}"]
    if skills.get("name") != SKILLS_PACKAGE or agents.get("name") != AGENTS_PACKAGE:
        errors.append("manifest names must be 'ycc' and 'ycc-agents'")
    if skills.get("version") != agents.get("version"):
        errors.append("split manifests must share one lockstep version")
    if skills.get("dependencies") != [AGENTS_PACKAGE]:
        errors.append("split ycc must declare dependencies ['ycc-agents']")
    if "dependencies" in agents:
        errors.append("ycc-agents must not declare dependencies")
    sources = {p.get("name"): p.get("source") for p in catalog.get("plugins", []) if isinstance(p, dict)}
    if sources != {SKILLS_PACKAGE: "./ycc", AGENTS_PACKAGE: "./ycc-agents"}:
        errors.append(f"lab marketplace must list ./ycc and ./ycc-agents, got {sources}")
    return errors


def _reference_error(ref: Reference, skills: frozenset[str], agents: frozenset[str]) -> str | None:
    """Rules (a)-(c) for one reference in the split tree."""
    name = ref.name
    if ref.role == "skill":
        return None if name in skills else f"skill reference {ref.token!r} does not resolve in split ycc"
    if ref.role == "dispatch" and is_placeholder(name):
        return None
    if ref.role == "dispatch" and name in BUILTIN_AGENTS:
        return None if ref.token == name else f"builtin dispatch {ref.token!r} must stay bare"
    if not ref.token.startswith(AGENTS_PREFIX):
        if ref.token != name:
            kind = "unqualified agent reference"
        else:
            kind = "bare plugin-agent dispatch" if ref.role == "dispatch" else "bare plugin-agent name"
        return f"{kind} {ref.token!r}; use 'ycc-agents:{name}'"
    return None if name in agents else f"{ref.token!r} is not an agent frontmatter name in ycc-agents"


def _preload_errors(path: Path, text: str, skills: frozenset[str]) -> list[str]:
    """Rule (f): agent `skills:` preloads must be qualified `ycc:<skill>` that exist."""
    _, preloads = agent_frontmatter(text)
    errors = []
    for skill, line in preloads:
        match = QUALIFIED_SKILL.match(skill)
        if match is None or match[1] not in skills:
            errors.append(f"{path}:{line}: agent preload {skill!r} must be a qualified existing 'ycc:<skill>'")
    return errors


def _reads_own_agents_dir(text: str, depth: int) -> bool:
    """True when text reaches <plugin-root>/agents from a file `depth` directories below the root."""
    if AGENTS_DIR_REACH.search(text):
        return True
    return any(len(match[1]) // 3 == depth for match in RELATIVE_AGENTS_REACH.finditer(text))


def _reference_errors(out_dir: Path) -> list[str]:
    """Scan split skills and agents with the shared detector."""
    skills_dir, agents_dir = out_dir / SKILLS_PACKAGE / "skills", out_dir / AGENTS_PACKAGE / "agents"
    skills = frozenset(p.parent.name for p in skills_dir.glob("*/SKILL.md") if p.parent.name != "_shared")
    agents = frozenset(agent_frontmatter(p.read_text(encoding="utf-8"))[0] for p in agents_dir.glob("*.md"))
    errors: list[str] = []
    for path in [*source_files(skills_dir), *sorted(agents_dir.glob("*.md"))]:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        where = path.relative_to(out_dir).as_posix()
        in_skills = path.is_relative_to(skills_dir)
        allowed = role_names(path.relative_to(skills_dir).as_posix()) if in_skills else frozenset()
        for ref in iter_references(text, skills, agents, shell=path.suffix == ".sh"):
            error = None if is_role_name(ref, allowed) else _reference_error(ref, skills, agents)
            if error:
                errors.append(f"{where}:{ref.line}: {error}")
        if path.is_relative_to(agents_dir):
            errors += _preload_errors(Path(where), text, skills)
        elif _reads_own_agents_dir(text, len(path.relative_to(out_dir / SKILLS_PACKAGE).parts) - 1):
            errors.append(f"{where}: reads the plugin's own agents/ directory, which split ycc does not ship")
    return errors


def _reach_errors(out_dir: Path, expected: dict[str, tuple[str, ...]]) -> list[str]:
    """Rule (e) via the package graph of a combined view: each dispatching skill reaches the same agents."""
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp) / SKILLS_PACKAGE
        view.mkdir()
        os.symlink(out_dir.resolve() / SKILLS_PACKAGE / "skills", view / "skills")
        os.symlink(out_dir.resolve() / AGENTS_PACKAGE / "agents", view / "agents")
        graph, graph_errors = extract_graph(view)
    errors = [f"split graph: {error}" for error in graph_errors]
    reach = {k.removeprefix("skill:"): v for k, v in agent_reach(graph).items()}
    for skill in sorted(expected):
        actual = reach.get(skill)
        if actual is None:
            errors.append(f"dispatching skill {skill!r} reaches no ycc-agents agent")
        elif actual != expected[skill]:
            errors.append(f"dispatching skill {skill!r} reaches {actual!r}; expected {expected[skill]!r}")
    return errors


def validate_split(out_dir: Path, expected: dict[str, tuple[str, ...]]) -> list[str]:
    """Validate a built split tree; `expected` maps dispatching skills from the source graph."""
    errors = _layout_errors(out_dir)
    if errors:
        return errors
    return [*_reference_errors(out_dir), *_reach_errors(out_dir, expected)]


def build_and_validate(source_root: Path, out_dir: Path) -> SplitReport:
    report = build_split(source_root, out_dir)
    report.errors = validate_split(out_dir, report.dispatching_skills)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT / "ycc")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=Path, help="Build into this empty directory, then validate it.")
    group.add_argument("--check", action="store_true", help="Build into a temporary directory and validate.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args(argv)
    try:
        if args.check:
            with tempfile.TemporaryDirectory() as tmp:
                report = build_and_validate(args.source_root, Path(tmp))
        else:
            report = build_and_validate(args.source_root, args.out)
    except (OSError, ValueError, SplitError) as exc:
        print(f"claude_agents_split: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report.__dict__, indent=2, sort_keys=True) if args.json else report.summary())
    if report.errors:
        print(f"claude_agents_split: {len(report.errors)} validation error(s)", file=sys.stderr)
        return 1
    print(f"OK: split ycc + ycc-agents valid ({len(report.dispatching_skills)} dispatching skills)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
