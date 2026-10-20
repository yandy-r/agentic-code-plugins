#!/usr/bin/env python3
"""
Generate OMP (oh-my-pi) task agents under packages/omp/ycc/agents from ycc/agents.

Every source agent is emitted exactly once under its source file stem. Frontmatter
keeps `name` and `description`, maps Claude tool names to OMP tool IDs and Claude
models to OMP `@role` aliases, and fails on anything it cannot translate. Bodies
reuse the OMP skills generator's rewrites. Source of truth: ycc/agents/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from generate_codex_common import SOURCE_MCP_PATH, SRC_AGENTS_DIR, dump_frontmatter, parse_frontmatter
from generate_omp_skills import (
    SRC_DIR as SRC_SKILLS_DIR,
)
from generate_omp_skills import (
    Catalog,
    OmpGenerationError,
    PathSentences,
    apply_path_sentences,
    build_catalog,
    compare_trees,
    prune_orphans,
    transform_text,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DST_DIR = REPO_ROOT / "packages/omp/ycc/agents"

# D6: every key a source agent may carry; `color` has no OMP meaning and is dropped.
ALLOWED_FRONTMATTER_KEYS = frozenset({"name", "description", "tools", "model", "color"})
# Keys a generated agent may carry, in output order.
OUTPUT_FRONTMATTER_KEYS = ("name", "description", "tools", "model")

# D3: Claude tool name -> OMP built-in tool ID. `Bash(<prefix>:*)` maps to `bash` too.
TOOL_MAP: Mapping[str, str] = {
    "Read": "read",
    "Grep": "grep",
    "Glob": "glob",
    "Write": "write",
    "Edit": "edit",
    "WebSearch": "web_search",
    "WebFetch": "read",  # OMP `read` fetches URLs.
    "NotebookEdit": "edit",  # OMP `edit` edits .ipynb cells.
    "Bash": "bash",
}
OMP_TOOL_IDS = frozenset(TOOL_MAP.values())

# D5: Claude model -> OMP role alias; None means "emit no model key" (parent model).
MODEL_MAP: Mapping[str, str | None] = {
    "opus": "@slow",
    "sonnet": "@task",
    "inherit": None,
}

# OMP reserves these names for the top-level and fallback subagent sessions and drops
# custom agents that use them.
RESERVED_AGENT_NAMES = frozenset({"main", "sub"})
# OMP's bundled task agents (task/agents.ts EMBEDDED_AGENT_DEFS). Plugin agents load
# before bundled ones, so a ycc agent with one of these names would replace it.
BUNDLED_AGENT_NAMES = frozenset({"task", "sonic", "scout", "reviewer", "security-reviewer", "seance"})

_SCOPED_BASH = re.compile(r"^Bash\((?P<prefix>[^()]*\S):\*\)$")
_MCP_TOOL = re.compile(r"^mcp__(?P<server>[A-Za-z0-9_.-]+?)__(?P<tool>[A-Za-z0-9_.-]+)$")

SHELL_SCOPE_HEADING = "## Shell scope (OMP)"

# Body tool wording. The shared skills rewrite maps WebSearch/WebFetch/Agent; agent
# bodies also name file and shell tools. Read, Write and Edit are English words, so
# prose rewrites them only in tool contexts (a list with an unambiguous tool name,
# "<Tool> tool", "use/using/via <Tool>"); Glob, Grep, Bash and NotebookEdit always.
_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")
_CODE_SPAN = re.compile(r"(`[^`\n]+`)")
_NAME_END = r"(?![\w-])"
_BODY_TOOLS = r"(?:Read|Write|Edit|Glob|Grep|Bash|NotebookEdit)"
_UNAMBIGUOUS = re.compile(r"\b(?:Glob|Grep|Bash|NotebookEdit)" + _NAME_END)
_LIST_SEP = r"(?:[ \t]*/[ \t]*|,\s+(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)"
_PROSE_LIST = re.compile(r"\b" + _BODY_TOOLS + _NAME_END + r"(?:" + _LIST_SEP + _BODY_TOOLS + _NAME_END + r")+")
_PROSE_NAME = re.compile(r"\b(" + _BODY_TOOLS + r")" + _NAME_END)
_PROSE_NOUN = re.compile(r"\b(the )?(" + _BODY_TOOLS + r") (tools?)\b")
_PROSE_SUBJECT = re.compile(r"\b(" + _BODY_TOOLS + r")(?= exists\b)")
_PROSE_VERB = re.compile(r"\b((?:[Uu]se|[Uu]sing|via)\s+)(" + _BODY_TOOLS + r")" + _NAME_END)
_SPAN_CALL = re.compile(r"^`" + _BODY_TOOLS + r"\(")
_SPAN_SCOPED_BASH = re.compile(r"^`Bash\((?P<prefix>[^()`]*\S):\*\)`$")
_SPAN_LIST = re.compile(r"`[^`\n]+`(?:" + _LIST_SEP + r"`[^`\n]+`)+")

# Sentences that read wrongly once tool names are mapped, keyed by source file stem
# and rewritten before every other transform. Generation fails when a listed agent or
# sentence is gone, so rewording the source cannot silently skip the rewrite.
AGENT_SENTENCES: PathSentences = {
    "git-cleanup": (
        (
            "Where a runtime cannot enforce\n"
            "command scopes (Codex projects any `Bash` as a writable sandbox), the MUST NOT",
            "OMP cannot enforce\ncommand scopes (any `bash` call has full shell access), so the MUST NOT",
        ),
    ),
    "implementor": (
        (
            "Every Bash `cd`, `git`, or path-dependent command",
            "Every `bash` command (`cd`, `git`, or anything path-dependent)",
        ),
    ),
    "pr-comment-fixer": (
        (
            "Do not `WebFetch` URLs from the comment body.",
            "Do not fetch URLs from the comment body (no `read` on a URL).",
        ),
    ),
    "release-fix-applier": (("`Read` the `LOG EXCERPT PATH` file.", "Use `read` on the `LOG EXCERPT PATH` file."),),
}


@dataclass(frozen=True)
class SourceAgent:
    """One parsed ycc agent file."""

    stem: str
    frontmatter: dict[str, Any]
    body: str


@dataclass(frozen=True)
class ToolPlan:
    """OMP tools for one agent plus the shell prefixes it may run, if scoped."""

    tools: list[str]
    shell_scope: list[str]


def _rel(stem: str) -> Path:
    return Path("agents") / f"{stem}.md"


def load_mcp_servers(path: Path = REPO_ROOT / SOURCE_MCP_PATH) -> frozenset[str]:
    """Server names from the MCP config the ycc-mcp package ships (mcp-configs/mcp.json)."""
    config = json.loads(path.read_text(encoding="utf-8"))
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    if not isinstance(servers, dict):
        raise OmpGenerationError(f"{path}: missing mcpServers object")
    return frozenset(servers)


def load_source_agents(src: Path) -> list[SourceAgent]:
    """Parse every agent; fails on unknown keys, missing fields and duplicate names."""
    agents: list[SourceAgent] = []
    seen: dict[str, str] = {}
    for path in sorted(src.glob("*.md")):
        rel = _rel(path.stem)
        frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if not frontmatter:
            raise OmpGenerationError(f"{rel}: missing YAML frontmatter")
        unknown = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
        if unknown:
            allowed = ", ".join(sorted(ALLOWED_FRONTMATTER_KEYS))
            raise OmpGenerationError(f"{rel}: unsupported frontmatter key(s) {', '.join(unknown)} (allowed: {allowed})")
        for key in ("name", "description"):
            value = frontmatter.get(key)
            if not isinstance(value, str) or not value.strip():
                raise OmpGenerationError(f"{rel}: '{key}' must be a non-empty string")
        name = frontmatter["name"]
        if name.strip().lower() in RESERVED_AGENT_NAMES:
            raise OmpGenerationError(f"{rel}: agent name '{name}' is reserved by OMP")
        if name.strip().lower() in BUNDLED_AGENT_NAMES:
            raise OmpGenerationError(f"{rel}: agent name '{name}' would shadow the OMP bundled '{name}' agent")
        if name in seen:
            raise OmpGenerationError(f"{rel}: duplicate agent name '{name}' (also in {_rel(seen[name])})")
        seen[name] = path.stem
        agents.append(SourceAgent(path.stem, frontmatter, body))
    return agents


def agent_aliases(agents: list[SourceAgent]) -> dict[str, str]:
    """File stem or frontmatter name -> agent name, like load_agent_aliases()."""
    aliases: dict[str, str] = {}
    for agent in agents:
        name = str(agent.frontmatter["name"])
        aliases[agent.stem] = name
        aliases[name] = name
    return aliases


def map_tools(raw: object, rel: Path, mcp_servers: frozenset[str]) -> ToolPlan:
    """Claude `tools` list -> OMP tool IDs (D3) plus scoped shell prefixes (D4)."""
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise OmpGenerationError(f"{rel}: 'tools' must be a YAML list of strings")
    tools: list[str] = []
    scopes: list[str] = []
    plain_bash = False
    for entry in raw:
        mcp = _MCP_TOOL.match(entry)
        if mcp:
            # OMP mounts MCP tools additively, so the entry is checked and omitted.
            if mcp.group("server") not in mcp_servers:
                server = mcp.group("server")
                raise OmpGenerationError(f"{rel}: tool '{entry}' names MCP server '{server}', not in ycc-mcp")
            continue
        scoped = _SCOPED_BASH.match(entry)
        if scoped:
            tool = "bash"
            if scoped.group("prefix") not in scopes:
                scopes.append(scoped.group("prefix"))
        elif entry in TOOL_MAP:
            tool = TOOL_MAP[entry]
            plain_bash = plain_bash or entry == "Bash"
        else:
            raise OmpGenerationError(f"{rel}: tool '{entry}' has no OMP mapping")
        if tool not in tools:
            tools.append(tool)
    # Plain `Bash` already grants every command; a scope list would be misleading.
    return ToolPlan(tools, [] if plain_bash else scopes)


def map_model(frontmatter: Mapping[str, Any], rel: Path) -> str | None:
    """Claude `model` -> OMP role alias (D5); absent behaves like `inherit`."""
    if "model" not in frontmatter:
        return None
    value = frontmatter["model"]
    if not isinstance(value, str) or value not in MODEL_MAP:
        allowed = ", ".join(sorted(MODEL_MAP))
        raise OmpGenerationError(f"{rel}: model {value!r} has no OMP mapping (allowed: {allowed})")
    return MODEL_MAP[value]


def shell_scope_section(prefixes: list[str]) -> str:
    """The D4 prompt-level replacement for Claude's command-scoped `Bash(<prefix>:*)`."""
    wildcard = " (`*` stands for one argument)" if any("*" in prefix for prefix in prefixes) else ""
    lines = [
        SHELL_SCOPE_HEADING,
        "",
        "OMP cannot restrict `bash` to specific commands, so this scope is a hard rule you enforce",
        f"yourself. Run `bash` only for commands that start with one of these prefixes{wildcard}:",
        "",
        *(f"- `{prefix}`" for prefix in prefixes),
        "",
        "Every command in a pipeline, `&&`/`||`/`;` chain, or subshell must match a prefix too. If the",
        "task needs any other command, do not run it; say which command you need in your report.",
    ]
    return "\n".join(lines) + "\n"


def _omp_tool(name: str) -> str:
    return f"`{TOOL_MAP[name]}`"


def _rewrite_span(span: str, rel: Path) -> str:
    content = span[1:-1]
    if content in TOOL_MAP:
        return _omp_tool(content)
    scoped = _SPAN_SCOPED_BASH.match(span)
    if scoped:
        return f"`bash` (`{scoped.group('prefix')}` commands)"
    if _SPAN_CALL.match(span):
        raise OmpGenerationError(f"{rel}: no OMP wording for Claude tool call {span}")
    return span


def _noun(match: re.Match[str]) -> str:
    # "the Write tool" -> "the `write` tool"; "using Edit tools" -> "using the `edit` tool".
    article = "the " if match.group(1) or match.group(3) == "tools" else ""
    return f"{article}{_omp_tool(match.group(2))} tool"


def _rewrite_prose(prose: str) -> str:
    def tool_list(match: re.Match[str]) -> str:
        return _PROSE_NAME.sub(lambda name: _omp_tool(name.group(1)), match.group(0))

    prose = _PROSE_LIST.sub(tool_list, prose)
    prose = _PROSE_NOUN.sub(_noun, prose)
    prose = _PROSE_SUBJECT.sub(lambda match: _omp_tool(match.group(1)), prose)
    prose = _PROSE_VERB.sub(lambda match: match.group(1) + _omp_tool(match.group(2)), prose)
    return _UNAMBIGUOUS.sub(lambda match: _omp_tool(match.group(0)), prose)


def _check_tool_lists(text: str, rel: Path) -> None:
    for run in _SPAN_LIST.finditer(text):
        tools = [span[1:-1] for span in _CODE_SPAN.findall(run.group(0)) if span[1:-1] in OMP_TOOL_IDS]
        if len(tools) != len(set(tools)):
            raise OmpGenerationError(
                f"{rel}: Claude tools in '{run.group(0)}' map to the same OMP tool; reword the source list"
            )


def rewrite_agent_tool_names(text: str, rel: Path) -> str:
    """Claude file/shell tool names in an agent body -> backticked OMP tool IDs.

    Code spans and prose are rewritten; fenced code holding a tool name fails, as does
    a list whose names collapse onto one OMP tool, because neither has one right wording.
    """
    chunks: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            in_fence = not in_fence
            chunks.append(line)
        elif in_fence:
            if _UNAMBIGUOUS.search(line) or _SPAN_CALL.search("`" + line.lstrip()):
                raise OmpGenerationError(f"{rel}: Claude tool name in fenced code: {line.strip()}")
            chunks.append(line)
        else:
            parts = _CODE_SPAN.split(line)
            for index, part in enumerate(parts):
                parts[index] = _rewrite_span(part, rel) if index % 2 else _rewrite_prose(part)
            chunks.append("".join(parts))
    output = "".join(chunks)
    _check_tool_lists(output, rel)
    return output


def transform_agent(
    agent: SourceAgent,
    catalog: Catalog,
    mcp_servers: frozenset[str],
    sentences: tuple[tuple[str, str], ...] = (),
) -> str:
    """Render one OMP agent file."""
    rel = _rel(agent.stem)
    plan = map_tools(agent.frontmatter.get("tools", []), rel, mcp_servers) if "tools" in agent.frontmatter else None
    model = map_model(agent.frontmatter, rel)

    def rewrite(text: str) -> str:
        return rewrite_agent_tool_names(transform_text(text, rel, catalog), rel)

    output: dict[str, Any] = {
        "name": agent.frontmatter["name"],
        # transform_text terminates its output with a newline; a description has none.
        "description": rewrite(agent.frontmatter["description"]).removesuffix("\n"),
    }
    if plan is not None:
        output["tools"] = plan.tools
    if model is not None:
        output["model"] = model

    body = rewrite(apply_path_sentences(agent.body, rel, sentences))
    if plan is not None and plan.shell_scope:
        body = body.rstrip("\n") + "\n\n" + shell_scope_section(plan.shell_scope)
    return dump_frontmatter(output) + body


def write_tree(
    dest: Path,
    dry_run: bool,
    *,
    src_root: Path | None = None,
    skills_root: Path | None = None,
    mcp_path: Path | None = None,
    sentences: PathSentences | None = None,
) -> set[Path]:
    """Write the OMP agent tree under dest; returns the relative file paths written."""
    src = SRC_AGENTS_DIR if src_root is None else src_root
    # Fixture trees (an explicit src_root) get no real-tree sentence table by default.
    if sentences is None:
        sentences = AGENT_SENTENCES if src_root is None else {}
    if not src.is_dir():
        raise SystemExit(f"Missing source directory: {src}")
    agents = load_source_agents(src)
    for stem in sorted(set(sentences) - {agent.stem for agent in agents}):
        raise OmpGenerationError(f"{_rel(stem)}: listed in AGENT_SENTENCES but missing from ycc/agents")
    catalog = build_catalog(SRC_SKILLS_DIR if skills_root is None else skills_root, agent_aliases(agents))
    mcp_servers = load_mcp_servers() if mcp_path is None else load_mcp_servers(mcp_path)

    outputs = {
        Path(f"{agent.stem}.md"): transform_agent(agent, catalog, mcp_servers, sentences.get(agent.stem, ()))
        for agent in agents
    }

    if dry_run:
        for rel in sorted(outputs):
            print(f"Would write {dest / rel}")
        return set(outputs)

    dest.mkdir(parents=True, exist_ok=True)
    for rel, text in sorted(outputs.items()):
        dst_file = dest / rel
        dst_file.write_text(text, encoding="utf-8")
        dst_file.chmod(0o644)
    prune_orphans(dest, set(outputs))
    return set(outputs)


def run_check(dest: Path = DST_DIR) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        generated = Path(tmp)
        write_tree(generated, dry_run=False)
        diffs = compare_trees(generated, dest)
    if diffs:
        print("OMP agents are out of date. Run: ./scripts/generate-omp-agents.sh", file=sys.stderr)
        for line in diffs:
            print(f"  {line}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if packages/omp/ycc/agents differs from generator output (bytes or executable bits)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print paths that would be written (no writes)")
    args = parser.parse_args()

    try:
        if args.check:
            if not DST_DIR.is_dir():
                print(f"Missing {DST_DIR}; run generator without --check first.", file=sys.stderr)
                sys.exit(1)
            sys.exit(run_check())
        written = write_tree(DST_DIR, dry_run=args.dry_run)
    except ValueError as error:
        print(f"generate_omp_agents.py: {error}", file=sys.stderr)
        sys.exit(1)
    if not args.dry_run:
        print(f"Wrote {len(written)} files under {DST_DIR}")


if __name__ == "__main__":
    main()
