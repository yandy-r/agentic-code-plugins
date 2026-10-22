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

import omp_model_policy
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
# Declared in ycc/settings/models.json targets.omp.agentModels.
MODEL_MAP: Mapping[str, str | None] = omp_model_policy.agent_model_map()

# OMP reserves these names for the top-level and fallback subagent sessions and drops
# custom agents that use them.
RESERVED_AGENT_NAMES = frozenset({"main", "sub"})
# OMP's bundled task agents (task/agents.ts EMBEDDED_AGENT_DEFS). Plugin agents load
# before bundled ones, so a ycc agent with one of these names would replace it.
BUNDLED_AGENT_NAMES = frozenset({"task", "sonic", "scout", "reviewer", "security-reviewer", "seance"})

_SCOPED_BASH = re.compile(r"^Bash\((?P<prefix>[^()]*\S):\*\)$")
_MCP_TOOL = re.compile(r"^mcp__(?P<server>[A-Za-z0-9_.-]+?)__(?P<tool>[A-Za-z0-9_.-]+)$")

SHELL_SCOPE_HEADING = "## Shell scope (OMP)"

# Body tool wording (D7). The shared skills rewrite already maps WebSearch, WebFetch,
# AskUserQuestion, the Todo/Task tools and Agent. Agent bodies also name file and shell
# tools, which are ordinary English words (Read, Write, Edit, Grep, Glob, Bash), so prose
# rewrites them only in tool contexts and never inside fenced code or other code spans:
#   - a code span whose whole content is a Claude tool name, or `Bash(<prefix>:*)`;
#   - a list of tool names that holds a backticked tool or a non-English name;
#   - "<Tool> tool(s)", "<Tool> exists";
#   - "use/uses/using/via <Tool>" followed by a function word, punctuation or line end.
# NotebookEdit is never English, so it is always rewritten.
_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")
_CODE_SPAN = re.compile(r"(`[^`\n]+`)")
_SPAN_SCOPED_BASH = re.compile(r"^`Bash\((?P<prefix>[^()`]*\S):\*\)`$")
_PLACEHOLDER = "\x00{}\x00"
_BARE_NAMES = r"(?:Read|Write|Edit|Glob|Grep|Bash|NotebookEdit)"
_BARE = r"(?<![\w.\-/\x00])" + _BARE_NAMES + r"(?![\w\-(])(?!\s+scripts?\b)"
# Tokens already mapped to OMP (by the span pass or the shared WebFetch/WebSearch rewrite).
_OMP_TOKEN = r"`(?:read|write|edit|glob|grep|bash|web_search)`(?: \(URL\))?"
_TOKEN = r"(?:" + _OMP_TOKEN + r"|" + _BARE + r")"
_LIST_SEP = r"(?:[ \t]*/[ \t]*|,\s+(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)"
_LIST = re.compile(_TOKEN + r"(?:" + _LIST_SEP + _TOKEN + r")+")
_LIST_TRIGGER = re.compile(_OMP_TOKEN + r"|(?<![\w.\-/\x00])(?:Glob|Grep|NotebookEdit)(?![\w\-(])")
_BARE_NAME = re.compile(_BARE)
_NOUN = re.compile(r"(?<![\w.\-/\x00])(the\s+)?(" + _BARE_NAMES + r")(\s+)(tools?)\b")
_SUBJECT = re.compile(r"(" + _BARE + r")(?=\s+exists\b)")
_FOLLOW = r"(?=[ \t]*(?:$|[.,;:)!?]|\s+(?:to|with|for|on|or|and|in|when|if|instead|first|calls?)\b))"
_VERB = re.compile(r"\b((?:[Uu]ses?|[Uu]sing|via)\s+)(" + _BARE + r")" + _FOLLOW, re.MULTILINE)
_NOTEBOOK = re.compile(r"(?<![\w.\-/\x00])NotebookEdit(?![\w\-(])")
_OMP_LIST = re.compile(_OMP_TOKEN + r"(?:" + _LIST_SEP + _OMP_TOKEN + r")+")
_OMP_ID = re.compile(r"`([a-z_]+)`")
# Claude tool identifiers that must not survive outside fenced code. None is English, and
# the shared rewrite plus the passes above map every use in prose and code spans, so a
# leftover would point an OMP agent at a tool it does not have:
#   - anywhere outside fences: the Claude-only names below;
#   - in prose (outside code spans): `Bash(` scope syntax;
#   - as a whole code span: a Claude file/shell tool name.
# Other code spans, e.g. `Write(p []byte)`, stay verbatim and are not checked.
_CLAUDE_ONLY_TOOLS = re.compile(
    r"\b(?:AskUserQuestion|TodoWrite|TaskCreate|TaskUpdate|TaskList|TaskGet|WebFetch|WebSearch|NotebookEdit)\b"
)
_PROSE_BASH_SCOPE = re.compile(r"\bBash\(")
_TOOL_SPAN = re.compile(r"`(?:" + _BARE_NAMES + r")`")

# Sentences that read wrongly once tool names are mapped, keyed by source file stem
# and rewritten before every other transform. Generation fails when a listed agent or
# sentence is gone, so rewording the source cannot silently skip the rewrite.
AGENT_SENTENCES: PathSentences = {
    "db-modifier": (("because permission mode permits Bash.", "because permission mode permits `bash`."),),
    "git-cleanup": (
        (
            "Where a runtime cannot enforce\n"
            "command scopes (Codex projects any `Bash` as a writable sandbox), the MUST NOT",
            "The OMP scope guard limits\n`bash` to these prefixes, but `git`, `gh` and `glab` can still"
            " mutate state, so the MUST NOT",
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
    """OMP tools for one agent plus the scope the ycc OMP scope guard enforces for it.

    `bash` lists the allowed shell prefixes (empty: no shell); None means unrestricted (plain
    `Bash`). `mcp` lists the declared (server, tool) pairs (empty: no MCP tool).
    """

    tools: list[str]
    bash: list[str] | None
    mcp: list[tuple[str, str]]


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
    """Claude `tools` list -> OMP tool IDs (D3) plus the scoped shell prefixes and MCP tools (D4)."""
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise OmpGenerationError(f"{rel}: 'tools' must be a YAML list of strings")
    tools: list[str] = []
    scopes: list[str] = []
    mcp_tools: list[tuple[str, str]] = []
    plain_bash = False
    for entry in raw:
        mcp = _MCP_TOOL.match(entry)
        if mcp:
            # OMP mounts every MCP tool in every agent; the scope guard allows only these.
            server = mcp.group("server")
            if server not in mcp_servers:
                raise OmpGenerationError(f"{rel}: tool '{entry}' names MCP server '{server}', not in ycc-mcp")
            if (server, mcp.group("tool")) not in mcp_tools:
                mcp_tools.append((server, mcp.group("tool")))
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
    return ToolPlan(tools, None if plain_bash else scopes, mcp_tools)


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
    """The prompt form of the shell scope the ycc OMP scope guard enforces (D4)."""
    wildcard = " (`*` stands for one argument)" if any("*" in prefix for prefix in prefixes) else ""
    lines = [
        SHELL_SCOPE_HEADING,
        "",
        "The ycc scope guard, an OMP extension in the ycc package, blocks every `bash` call outside",
        f"this scope. Run `bash` only for commands that start with one of these prefixes{wildcard}:",
        "",
        *(f"- `{prefix}`" for prefix in prefixes),
        "",
        "Every command in a pipeline, `&&`/`||`/`;` chain, subshell or `{ }` group must match a prefix",
        "too. The guard also blocks what it cannot verify: `$` expansions, command substitution,",
        "backticks, here-documents, leading `VAR=value` assignments and output redirection other than",
        "to `/dev/null`. If the task needs any other command, do not retry it in another form; say",
        "which command you need in your report.",
    ]
    return "\n".join(lines) + "\n"


def scope_entry(plan: ToolPlan | None) -> dict[str, Any]:
    """One agent's agent-scopes.json entry; None (no `tools` key) is unrestricted."""
    if plan is None:
        return {"bash": None, "mcp": None}
    return {"bash": plan.bash, "mcp": [{"server": server, "tool": tool} for server, tool in plan.mcp]}


def _omp_tool(name: str) -> str:
    return f"`{TOOL_MAP[name]}`"


def _rewrite_span(span: str) -> str:
    """A span holding exactly a Claude tool name or a scoped Bash form; others stay verbatim."""
    content = span[1:-1]
    if content in TOOL_MAP:
        return _omp_tool(content)
    scoped = _SPAN_SCOPED_BASH.match(span)
    if scoped:
        return f"`bash` (`{scoped.group('prefix')}` commands)"
    return span


def _noun(match: re.Match[str]) -> str:
    # "the Write tool" -> "the `write` tool"; "using Edit tools" -> "using the `edit` tool".
    article = match.group(1) or ("the " if match.group(4) == "tools" else "")
    return f"{article}{_omp_tool(match.group(2))}{match.group(3)}tool"


def _rewrite_prose(prose: str) -> str:
    """Paragraph-level pass over prose whose non-tool code spans are placeholders."""

    def tool_list(match: re.Match[str]) -> str:
        run = match.group(0)
        if not _LIST_TRIGGER.search(run):
            return run
        return _BARE_NAME.sub(lambda name: _omp_tool(name.group(0)), run)

    prose = _LIST.sub(tool_list, prose)
    prose = _NOUN.sub(_noun, prose)
    prose = _SUBJECT.sub(lambda match: _omp_tool(match.group(1)), prose)
    prose = _VERB.sub(lambda match: match.group(1) + _omp_tool(match.group(2)), prose)
    return _NOTEBOOK.sub(lambda match: _omp_tool(match.group(0)), prose)


def _check_tool_lists(prose: str, rel: Path) -> None:
    for run in _OMP_LIST.finditer(prose):
        tools = _OMP_ID.findall(run.group(0))
        if len(tools) != len(set(tools)):
            raise OmpGenerationError(
                f"{rel}: Claude tools in '{run.group(0)}' map to the same OMP tool; reword the source list"
            )


def _rewrite_prose_chunk(chunk: str, rel: Path) -> str:
    spans: list[str] = []

    def protect(match: re.Match[str]) -> str:
        span = _rewrite_span(match.group(0))
        if span != match.group(0) or span[1:-1] in OMP_TOOL_IDS:
            return span
        spans.append(span)
        return _PLACEHOLDER.format(len(spans) - 1)

    prose = _rewrite_prose(_CODE_SPAN.sub(protect, chunk))
    _check_tool_lists(prose, rel)
    for index, span in enumerate(spans):
        prose = prose.replace(_PLACEHOLDER.format(index), span, 1)
    return prose


def rewrite_agent_tool_names(text: str, rel: Path) -> str:
    """Claude file/shell tool names in agent prose -> backticked OMP tool IDs.

    Fenced code and code spans other than bare tool names stay verbatim. A list whose
    names collapse onto one OMP tool fails, because it has no single right wording.
    """
    chunks: list[str] = []
    prose: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            if not in_fence:
                chunks.append(_rewrite_prose_chunk("".join(prose), rel))
                prose = []
            in_fence = not in_fence
            chunks.append(line)
        elif in_fence:
            chunks.append(line)
        else:
            prose.append(line)
    chunks.append(_rewrite_prose_chunk("".join(prose), rel))
    return "".join(chunks)


def claude_tool_residue(text: str) -> list[str]:
    """Lines outside fenced code that still name a Claude tool (see _CLAUDE_ONLY_TOOLS)."""
    hits: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = _CODE_SPAN.sub("", line)
        if _CLAUDE_ONLY_TOOLS.search(line) or _PROSE_BASH_SCOPE.search(prose) or _TOOL_SPAN.search(line):
            hits.append(line.strip())
    return hits


def transform_agent(
    agent: SourceAgent,
    catalog: Catalog,
    plan: ToolPlan | None,
    sentences: tuple[tuple[str, str], ...] = (),
) -> str:
    """Render one OMP agent file."""
    rel = _rel(agent.stem)
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

    body = rewrite(apply_path_sentences(agent.body, rel, sentences, "AGENT_SENTENCES"))
    for line in claude_tool_residue(output["description"] + "\n" + body):
        raise OmpGenerationError(f"{rel}: Claude tool name left after OMP rewrites: {line}")
    if plan is not None and plan.bash:
        body = body.rstrip("\n") + "\n\n" + shell_scope_section(plan.bash)
    return dump_frontmatter(output) + body


def tool_plans(agents: list[SourceAgent], mcp_servers: frozenset[str]) -> dict[str, ToolPlan | None]:
    """Agent file stem -> its ToolPlan (None without a `tools` key): the one source of agent scope."""
    return {
        agent.stem: (
            map_tools(agent.frontmatter["tools"], _rel(agent.stem), mcp_servers)
            if "tools" in agent.frontmatter
            else None
        )
        for agent in agents
    }


def agent_scopes(*, src_root: Path | None = None, mcp_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """agent-scopes.json `agents`: lowercased agent name (OMP's ctx.agent.name) -> scope_entry."""
    agents = load_source_agents(SRC_AGENTS_DIR if src_root is None else src_root)
    plans = tool_plans(agents, load_mcp_servers() if mcp_path is None else load_mcp_servers(mcp_path))
    scopes: dict[str, dict[str, Any]] = {}
    for agent in agents:
        key = str(agent.frontmatter["name"]).strip().lower()
        if key in scopes:
            raise OmpGenerationError(f"{_rel(agent.stem)}: agent name '{key}' collides case-insensitively")
        scopes[key] = scope_entry(plans[agent.stem])
    return dict(sorted(scopes.items()))


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
    plans = tool_plans(agents, load_mcp_servers() if mcp_path is None else load_mcp_servers(mcp_path))

    outputs = {
        Path(f"{agent.stem}.md"): transform_agent(agent, catalog, plans[agent.stem], sentences.get(agent.stem, ()))
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
