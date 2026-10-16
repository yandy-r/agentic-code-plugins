#!/usr/bin/env python3
"""Extract source component dependencies without third-party YAML dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

# Builtins used by the standalone dispatch contract are runtime-owned, not shipped agents.
# See ycc/skills/_shared/references/standalone-dispatch.md and ycc/settings/models.json.
BUILTIN_AGENTS = frozenset({"explore", "general", "general-purpose", "generalPurpose", "shell"})
CATALOG_SKILLS = frozenset({"orchestrate", "init", "write-docs"})
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
# Pipe-separated dispatch values are code spans; bare cells are Markdown table headings.
DISPATCH = re.compile(r"\bsubagent_type`?\s*(?:[:=]\s*`?[\"']?|\|\s*`)(?:ycc:)?([a-zA-Z][a-zA-Z0-9-]*)")
BOLD_DISPATCH = re.compile(r"\*\*Subagent Type\*\*:\s*`([^`]+)`")
TABLE_DISPATCH = re.compile(r"\|\s*Subagent Type\s*\|\s*`(?:ycc:)?([a-zA-Z][a-zA-Z0-9-]*)`\s*\|")
MENTION = re.compile(r"(?<![\w/-])(/?)ycc:([a-z][a-z0-9-]*)(?![a-z0-9-]|:)")
PLUGIN_FILE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT(?:%/)?\}/skills/([^\s\"'`)]+)")
RELATIVE_SHARED = re.compile(r"\.\./\.\./_shared/(scripts/[^\s\"'`)]+)")


@dataclass(frozen=True)
class Node:
    """A shipped skill, named agent, or individual shared file."""

    id: str
    kind: str
    path: str
    stem: str | None = None


@dataclass(frozen=True)
class Edge:
    """A dependency with its first source location and occurrence count."""

    src: str
    dst: str
    kind: str
    evidence: str
    count: int = 1


@dataclass
class Graph:
    """Source graph with canonical node IDs and deduplicated edges."""

    source_root: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], Edge] = field(default_factory=dict)

    def add_edge(self, src: str, dst: str, kind: str, evidence: str) -> None:
        """Keep the first evidence while counting repeated dependency occurrences."""
        key = (src, dst, kind)
        old = self.edges.get(key)
        self.edges[key] = replace(old, count=old.count + 1) if old else Edge(src, dst, kind, evidence)


def _frontmatter(text: str) -> tuple[str, list[tuple[str, int]]]:
    """Parse only scalar name and scalar/list skills from the leading YAML block."""
    name = ""
    skills: list[tuple[str, int]] = []
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return name, skills
    in_skills = False
    for number, line in enumerate(lines[1:], 2):
        if line == "---":
            break
        if line.startswith("name:"):
            name = line.partition(":")[2].strip().strip("\"'")
        if line.startswith("skills:"):
            value = line.partition(":")[2].split(" #", 1)[0].strip()
            in_skills = not value
            if value:
                skills.extend((s.strip().strip("\"'"), number) for s in value.strip("[]").split(",") if s.strip())
        elif in_skills:
            item = re.match(r"\s*-\s+([^#]+)", line)
            if item:
                skills.append((item[1].strip().strip("\"'"), number))
            elif line and not line[0].isspace():
                in_skills = False
    return name, skills


def _expand(path: str) -> list[str]:
    """Expand shell-style brace alternatives, preserving glob patterns."""
    match = re.search(r"\{([^{}]+)\}", path)
    if match is None:
        return [path]
    return [
        item for option in match[1].split(",") for item in _expand(path[: match.start()] + option + path[match.end() :])
    ]


class _Extractor:
    def __init__(self, source_root: Path) -> None:
        self.root = source_root.resolve()
        self.graph = Graph(self.root.name)
        self.errors: list[str] = []
        self.files: dict[Path, str] = {}
        self.preloads: list[tuple[str, str, str]] = []

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root.parent).as_posix()

    def walk(self, directory: Path) -> list[Path]:
        """List files under a directory, skipping hidden segments and bytecode caches."""
        return [
            child
            for child in sorted(directory.rglob("*"))
            if child.is_file()
            and not any(part.startswith(".") or part == "__pycache__" for part in child.relative_to(self.root).parts)
        ]

    def discover(self) -> None:
        for directory in (self.root / "skills", self.root / "agents"):
            if not directory.is_dir():
                self.errors.append(f"missing source directory: {self.relative(directory)}")
        for path in sorted((self.root / "skills").glob("*/SKILL.md")):
            if path.parent.name == "_shared":
                continue
            node = Node(f"skill:{path.parent.name}", "skill", self.relative(path))
            self.graph.nodes[node.id] = node
            for child in self.walk(path.parent):
                self.files[child] = node.id
        shared = self.root / "skills/_shared"
        for path in self.walk(shared):
            node = Node(f"shared:{path.relative_to(shared).as_posix()}", "shared", self.relative(path))
            self.graph.nodes[node.id] = node
            self.files[path] = node.id
        for path in sorted((self.root / "agents").glob("*.md")):
            name, skills = _frontmatter(path.read_text(encoding="utf-8"))
            if not NAME.fullmatch(name):
                self.errors.append(f"{self.relative(path)}:2: invalid agent name {name!r}")
                continue
            node = Node(f"agent:{name}", "agent", self.relative(path), path.stem)
            if node.id in self.graph.nodes:
                self.errors.append(f"{self.relative(path)}:2: duplicate agent name {name!r}")
                continue
            self.graph.nodes[node.id] = node
            self.files[path] = node.id
            self.preloads.extend((node.id, skill, f"{node.path}:{number}") for skill, number in skills)

    def resolve(self, name: str, kind: str, evidence: str) -> str | None:
        if kind == "agent" and name in BUILTIN_AGENTS:
            return None
        if not NAME.fullmatch(name):
            return None  # Template placeholders, not concrete references.
        target = f"{kind}:{name}"
        if target not in self.graph.nodes:
            hint = ""
            if kind == "agent":
                aliases = [n.id.removeprefix("agent:") for n in self.graph.nodes.values() if n.stem == name]
                if aliases:
                    hint = f"; did you mean frontmatter name {aliases[0]!r}?"
            self.errors.append(f"{evidence}: unresolved {kind} reference {name!r}{hint}")
            return None
        return target

    def file_edges(self, src: str, raw: str, evidence: str) -> None:
        if any(marker in raw for marker in ("<", "{{", "...")):
            return
        for expanded in _expand(raw.split("#", 1)[0].removesuffix(":*")):
            pattern = self.root / "skills" / expanded
            try:
                pattern.resolve().relative_to((self.root / "skills").resolve())
            except ValueError:
                self.errors.append(f"{evidence}: source path escapes skills: {raw!r}")
                continue
            matches = sorted((self.root / "skills").glob(expanded))
            matches = [path for path in matches if path.exists()]
            if not matches:
                self.errors.append(f"{evidence}: missing source file {expanded!r}")
                continue
            for path in matches:
                relative = path.relative_to(self.root / "skills")
                if relative.parts[0] == "_shared":
                    if path.is_dir():
                        continue  # Existence is enough for a shared directory reference.
                    dst = f"shared:{Path(*relative.parts[1:]).as_posix()}"
                    kind = "shared"
                else:
                    dst = f"skill:{relative.parts[0]}"
                    kind = "script" if path.suffix in {".sh", ".py"} else "file"
                if dst == src:
                    continue
                if dst not in self.graph.nodes:
                    self.errors.append(f"{evidence}: source file has no component: {expanded!r}")
                else:
                    self.graph.add_edge(src, dst, kind, evidence)

    def scan(self, path: Path, src: str) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            return  # Binary assets are nodes, but cannot contain textual dependency contracts.
        prefix = self.relative(path)
        for number, line in enumerate(text.splitlines(), 1):
            evidence = f"{prefix}:{number}"
            found = [*DISPATCH.finditer(line), *BOLD_DISPATCH.finditer(line), *TABLE_DISPATCH.finditer(line)]
            dispatches = sorted(found, key=lambda m: m.start())
            for match in dispatches:
                name = match[1].removeprefix("ycc:")
                if name not in BUILTIN_AGENTS and not NAME.fullmatch(name) and "<" not in name and "{{" not in name:
                    self.errors.append(f"{evidence}: invalid agent reference {name!r}")
                    continue
                dst = self.resolve(name, "agent", evidence)
                if dst:
                    kind = "handoff" if src.startswith("agent:") else "dispatch"
                    self.graph.add_edge(src, dst, kind, evidence)
            for match in MENTION.finditer(line):
                if any(d.start() <= match.start() < d.end() for d in dispatches):
                    continue
                name = match[2]
                kind = "skill" if match[1] or f"skill:{name}" in self.graph.nodes else "agent"
                dst = self.resolve(name, kind, evidence)
                if dst:
                    edge_kind = "handoff" if src.startswith("agent:") and kind == "agent" else "mention"
                    self.graph.add_edge(src, dst, edge_kind, evidence)
            for match in PLUGIN_FILE.finditer(line):
                self.file_edges(src, match[1], evidence)
            for match in RELATIVE_SHARED.finditer(line):
                self.file_edges(src, "_shared/" + match[1], evidence)

    def extract(self) -> tuple[Graph, list[str]]:
        self.discover()
        for src, skill, evidence in self.preloads:
            dst = self.resolve(skill.removeprefix("ycc:"), "skill", evidence)
            if dst:
                self.graph.add_edge(src, dst, "preload", evidence)
        for path, src in sorted(self.files.items()):
            self.scan(path, src)
        for skill in sorted(CATALOG_SKILLS):
            src = f"skill:{skill}"
            if src not in self.graph.nodes:
                self.errors.append(f"missing catalog skill: {skill!r}")
                continue
            for dst in sorted(self.graph.nodes):
                if dst.startswith("agent:"):
                    self.graph.add_edge(src, dst, "catalog", f"{self.graph.nodes[src].path}:1")
        return self.graph, sorted(set(self.errors))


def extract_graph(source_root: Path) -> tuple[Graph, list[str]]:
    """Extract deterministic source dependencies and return strict resolution errors."""
    return _Extractor(source_root).extract()
