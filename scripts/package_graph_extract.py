#!/usr/bin/env python3
"""Extract source component dependencies without third-party YAML dependencies."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field, replace
from pathlib import Path

# Builtins used by the standalone dispatch contract are runtime-owned, not shipped agents.
# See ycc/skills/_shared/references/standalone-dispatch.md and ycc/settings/models.json.
BUILTIN_AGENTS = frozenset({"explore", "general", "general-purpose", "generalPurpose", "shell"})
CATALOG_SKILLS = frozenset({"orchestrate", "init", "write-docs"})
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
# Pipe-separated dispatch values are code spans; bare cells are Markdown table headings.
DISPATCH = re.compile(r"\bsubagent_type`?\s*(?:[:=]\s*`?[\"']?|\|\s*`)([^\s\"'`,)|]+)")
BOLD_DISPATCH = re.compile(r"\*\*Subagent Type\*\*:\s*`([^`]+)`")
TABLE_DISPATCH = re.compile(r"\|\s*Subagent Type\s*\|\s*`([^`]+)`\s*\|")
# Prose dispatch: "using subagent type `x`", "All eight use `x`", and "- Agent: x" roster fields.
PROSE_DISPATCH = re.compile(r"\bsubagent type\s+`([^`\s]+)`|\bAll \w+ use\s+`([^`\s]+)`", re.IGNORECASE)
FIELD_DISPATCH = re.compile(r"^\s*[-*]\s+(?:\*\*)?Agent(?:\*\*)?:\s*`?([a-z][a-z0-9:-]*)`?\s*$")
# Markdown table columns whose backticked cells name the dispatched agent type.
DISPATCH_COLUMN = re.compile(
    r"`?(?:source )?subagent[_ ]type`?|plugin agent name|(?:recommended|primary|supporting) agents?",
    re.IGNORECASE,
)
TABLE_SEPARATOR = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
# A dispatch cell is one or more code spans joined by commas, "or" or "/"; each span is a value.
CODE_LIST_CELL = re.compile(r"\s*`[^`]+`(?:\s*(?:,|\bor\b|/)\s*`[^`]+`)*\s*$")
# Bare agent-name contexts (beyond dispatch syntax): headings, list leads, parentheses, arrows.
HEADING_LEAD = re.compile(r"^\s*#{1,6}\s+")
LIST_LEAD = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(?:\*\*)?`?")
ARROW = re.compile(r"(?:→|->)\s*`?")
NAME_CHAIN = re.compile(r"`?\s*(?:,|\+|\bor\b|/)\s*`?")
SHELL_STRING = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'")
# `ycc:` is the canonical namespace; `ycc-agents:` is the v7 split's agent namespace (always an agent).
MENTION = re.compile(r"(?<![\w/-])(/?)(ycc|ycc-agents):([a-z][a-z0-9-]*)(?![a-z0-9-]|:)")
NAMESPACE = re.compile(r"^/?(?:ycc|ycc-agents):")
# `ycc:<name>` followed by "agent(s)"/"sub-agent(s)" names the agent when a skill shares that name.
AGENT_CONTEXT = re.compile(r"`?\s+(?:standalone\s+)?(?:sub-?)?agents?\b")
PLUGIN_FILE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT(?:%/)?\}/skills/([^\s\"'`)]+)")
RELATIVE_SHARED = re.compile(r"\.\./\.\./_shared/(scripts/[^\s\"'`)]+)")


@dataclass(frozen=True)
class Reference:
    """One agent dispatch or `ycc:` mention; `start:end` spans `token` on 1-based `line`.

    `role` is `dispatch` (an agent-type value), or `skill`/`agent` for a resolved mention.
    """

    line: int
    start: int
    end: int
    token: str
    role: str

    @property
    def name(self) -> str:
        """The referenced name without a leading `/`, `ycc:` or `ycc-agents:` namespace."""
        return NAMESPACE.sub("", self.token)


def _table_dispatch_columns(lines: list[str]) -> dict[int, set[int]]:
    """Map data-row line indexes to the cell indexes of their table's dispatch columns."""
    columns: dict[int, set[int]] = {}
    index = 0
    while index + 1 < len(lines):
        if not lines[index].lstrip().startswith("|") or not TABLE_SEPARATOR.match(lines[index + 1]):
            index += 1
            continue
        header = [cell.strip().lower() for cell in lines[index].strip().strip("|").split("|")]
        teammate = any(cell.startswith("teammate") for cell in header)
        wanted = {
            i for i, cell in enumerate(header) if DISPATCH_COLUMN.fullmatch(cell) or (teammate and cell == "type")
        }
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            if wanted:
                columns[index] = wanted
            index += 1
    return columns


def _cell_spans(line: str, wanted: set[int]) -> list[tuple[int, int, str]]:
    """Return every code-span value of the wanted cells that hold only code spans."""
    pipes = [i for i, char in enumerate(line) if char == "|"]
    spans = []
    for column, (left, right) in enumerate(zip(pipes, pipes[1:], strict=False)):
        if column in wanted and CODE_LIST_CELL.match(line, left + 1, right):
            spans += [(m.start(1), m.end(1), m[1].strip()) for m in CODE_SPAN.finditer(line, left + 1, right)]
    return spans


def _line_dispatches(line: str, columns: set[int]) -> list[tuple[int, int, str]]:
    """All non-overlapping dispatch value spans on one line, leftmost first."""
    found = [
        (m.start(1), m.end(1), m[1])
        for regex in (DISPATCH, BOLD_DISPATCH, TABLE_DISPATCH)
        for m in regex.finditer(line)
    ]
    for match in PROSE_DISPATCH.finditer(line):
        group = 1 if match[1] is not None else 2
        found.append((match.start(group), match.end(group), match[group]))
    found.extend((m.start(1), m.end(1), m[1]) for m in FIELD_DISPATCH.finditer(line))
    found.extend(_cell_spans(line, columns))
    kept: list[tuple[int, int, str]] = []
    for span in sorted(set(found)):
        if not kept or span[0] >= kept[-1][1]:
            kept.append(span)
    return kept


def _bare_name_pattern(names: Collection[str]) -> re.Pattern[str] | None:
    """Whole-word bare names: not namespaced, not a path or file segment, not a longer word."""
    if not names:
        return None
    alternatives = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w:/.@$-])(?:{alternatives})(?![\w-]|\.\w)")


def _chain(line: str, start: int, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Names at `start` and those chained after it by `,`, `+`, `or` or `/`."""
    spans = []
    match = pattern.match(line, start)
    while match:
        spans.append((match.start(), match.end()))
        joint = NAME_CHAIN.match(line, match.end())
        match = pattern.match(line, joint.end()) if joint and joint.end() > match.end() else None
    return spans


def _bare_agent_spans(line: str, pattern: re.Pattern[str] | None, shell: bool) -> set[tuple[int, int]]:
    """Bare plugin-agent names in agent-naming contexts of one line.

    Markdown: any code span or table row, a heading that is only the name, a list item's
    leading names, a parenthesized name, and arrow targets. Shell: any quoted string literal.
    """
    if pattern is None:
        return set()
    spans: set[tuple[int, int]] = set()
    regions = (
        [(m.start(), m.end()) for m in SHELL_STRING.finditer(line)]
        if shell
        else [(m.start(1), m.end(1)) for m in CODE_SPAN.finditer(line)]
    )
    if not shell and line.lstrip().startswith("|"):
        regions.append((0, len(line)))
    for start, end in regions:
        spans |= {(m.start(), m.end()) for m in pattern.finditer(line, start, end)}
    if shell:
        return spans
    heading = HEADING_LEAD.match(line)
    if heading:
        match = pattern.fullmatch(line.rstrip(), heading.end())
        spans |= {(match.start(), match.end())} if match else set()
    lead = LIST_LEAD.match(line)
    if lead:
        spans |= set(_chain(line, lead.end(), pattern))
    for arrow in ARROW.finditer(line):
        spans |= set(_chain(line, arrow.end(), pattern))
    for match in pattern.finditer(line):
        before, after = line[: match.start()].rstrip("` "), line[match.end() :].lstrip("` ")
        if before.endswith("(") and after.startswith(")"):
            spans.add((match.start(), match.end()))
    return spans


def iter_references(
    text: str, skills: Collection[str], agents: Collection[str], *, shell: bool = False
) -> list[Reference]:
    """Find dispatch values, namespaced mentions and bare agent names; one detector for graph and split.

    A `ycc:` mention names a skill when slash-prefixed or a known skill, unless an agent of the
    same name is followed by "agent" context (`ycc:releaser` agent); other mentions name agents.
    Bare names (role `agent`, token without namespace) are reported only for agents that are not
    also skills or builtins, in the contexts of `_bare_agent_spans`; `shell` selects shell syntax.
    """
    lines = text.splitlines()
    columns = {} if shell else _table_dispatch_columns(lines)
    pattern = _bare_name_pattern(set(agents) - set(skills) - BUILTIN_AGENTS)
    references: list[Reference] = []
    for index, line in enumerate(lines):
        number = index + 1
        dispatches = _line_dispatches(line, columns.get(index, set()))
        references.extend(Reference(number, start, end, token, "dispatch") for start, end, token in dispatches)
        taken = [(start, end) for start, end, _ in dispatches]
        for match in MENTION.finditer(line):
            if any(start <= match.start() < end for start, end in taken):
                continue
            taken.append((match.start(), match.end()))
            name = match[3]
            role = "skill" if match[2] == "ycc" and (match[1] or name in skills) else "agent"
            if role == "skill" and not match[1] and name in agents and AGENT_CONTEXT.match(line, match.end()):
                role = "agent"
            references.append(Reference(number, match.start(), match.end(), match[0], role))
        for start, end in sorted(_bare_agent_spans(line, pattern, shell)):
            if not any(s <= start < e for s, e in taken):
                references.append(Reference(number, start, end, line[start:end], "agent"))
    return sorted(references, key=lambda ref: (ref.line, ref.start))


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


def agent_frontmatter(text: str) -> tuple[str, list[tuple[str, int]]]:
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
        self.skill_names: set[str] = set()
        self.agent_names: set[str] = set()

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
            name, skills = agent_frontmatter(path.read_text(encoding="utf-8"))
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
        lines = text.splitlines()
        for ref in iter_references(text, self.skill_names, self.agent_names, shell=path.suffix == ".sh"):
            evidence = f"{prefix}:{ref.line}"
            if ref.role == "dispatch":
                name = ref.name
                if name not in BUILTIN_AGENTS and not NAME.fullmatch(name) and "<" not in name and "{{" not in name:
                    self.errors.append(f"{evidence}: invalid agent reference {name!r}")
                    continue
                dst = self.resolve(name, "agent", evidence)
                if dst:
                    kind = "handoff" if src.startswith("agent:") else "dispatch"
                    self.graph.add_edge(src, dst, kind, evidence)
                continue
            dst = self.resolve(ref.name, ref.role, evidence)
            if dst:
                namespaced = ref.token != ref.name
                edge_kind = "handoff" if src.startswith("agent:") and ref.role == "agent" and namespaced else "mention"
                self.graph.add_edge(src, dst, edge_kind, evidence)
        for number, line in enumerate(lines, 1):
            evidence = f"{prefix}:{number}"
            for match in PLUGIN_FILE.finditer(line):
                self.file_edges(src, match[1], evidence)
            for match in RELATIVE_SHARED.finditer(line):
                self.file_edges(src, "_shared/" + match[1], evidence)

    def extract(self) -> tuple[Graph, list[str]]:
        self.discover()
        self.skill_names = {n.removeprefix("skill:") for n in self.graph.nodes if n.startswith("skill:")}
        self.agent_names = {n.removeprefix("agent:") for n in self.graph.nodes if n.startswith("agent:")}
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
