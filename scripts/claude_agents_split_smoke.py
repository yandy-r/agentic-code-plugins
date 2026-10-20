#!/usr/bin/env python3
"""Opt-in live dispatch proof for the hidden v7 Claude split (ycc skills + ycc-agents agents).

Invoked by scripts/test-claude-agents-split.sh inside a scrubbed env -i lab. Reuses the
YAN-1121 loopback fake Messages API (claude_namespace_fake_api.Lab): no real inference,
credentials, or user config. The scripted parent calls Skill(ycc:<skill>) and then
Agent(ycc-agents:<agent>) for every dispatching skill in the package graph; each child
request must carry that agent's own system prompt. A missing qualified agent must fail
closed, and one bare plugin-agent dispatch is recorded as an observation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_package_graph import agent_reach  # noqa: E402
from claude_agents_split import AGENTS_PACKAGE, AGENTS_PREFIX, LAB_MARKET, SKILLS_PACKAGE  # noqa: E402
from claude_namespace_checks import check, negative_self_test, select_result  # noqa: E402
from claude_namespace_fake_api import Lab, save  # noqa: E402
from package_graph_extract import agent_frontmatter, extract_graph  # noqa: E402

FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
# Skill-load shell injection: !`${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/<read-only profiler>`.
INJECTION = re.compile(r"!`\$\{CLAUDE_PLUGIN_ROOT\}(/skills/[^`\s]+)`")
NEGATIVE_AGENT = AGENTS_PREFIX + "absent"
BARE_PROBE = ("plan", "planner")
# Probe agents pinned to a specific dispatch site; others take the skill's first direct dispatch.
# orchestrate: the SKILL.md "Recommended Agent" table (Step 7), not only its reference files.
PINNED_AGENTS = {"orchestrate": "frontend-ui-developer"}


def body_marker(path: Path) -> str:
    """A JSON-escaped body excerpt: present only where the file's body was really loaded."""
    body = FRONTMATTER.sub("", path.read_text(encoding="utf-8"), count=1)
    for line in body.splitlines():
        text = line.strip().lstrip("#>*- ").strip()
        if len(text) >= 40 and not any(char in text for char in "$`!\\"):
            return json.dumps(text[:80])[1:-1]
    raise SystemExit(f"CHECK FAILED [marker]: no usable body line in {path}")


class SplitLab(Lab):
    """Lab that can open a probe with a user-only skill's slash command instead of the Skill tool.

    `allowed` lists the exact skill-load injection commands of the probed skill; the CLI needs
    Bash permission for them. The fake model never requests Bash itself.
    """

    slash = ""
    allowed: tuple[str, ...] = ()

    def run(self, label: str, args: list[str]) -> tuple[int, str]:
        if self.slash:
            args = [f"/{self.slash} {arg}" if arg == "HARNESS:" + label else arg for arg in args]
        if self.allowed:
            tools = args.index("--tools") + 1
            args = [*args[:tools], args[tools] + ",Bash", *args[tools + 1 :]]
            args += ["--allowedTools", *(f"Bash({command})" for command in self.allowed)]
        return super().run(label, args)

    def response(self, body: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(body.get("messages", []))
        if self.slash and '"id": "toolu_ns_skill"' not in encoded and '"id": "toolu_ns_agent"' not in encoded:
            # The slash command already loaded the skill: start the scripted turn at the Agent stage.
            marker = {"role": "assistant", "content": [{"type": "text", "id": "toolu_ns_skill"}]}
            body = {**body, "messages": [*body.get("messages", []), marker]}
        return super().response(body)


def dispatch_plan(source_root: Path) -> dict[str, str]:
    """Map every dispatching skill in the source graph to one agent: its own dispatch first."""
    graph, errors = extract_graph(source_root)
    if errors:
        raise SystemExit("CHECK FAILED [source graph]: " + "; ".join(errors))
    direct: dict[str, list[str]] = {}
    for edge in graph.edges.values():
        if edge.kind == "dispatch" and edge.src.startswith("skill:"):
            direct.setdefault(edge.src, []).append(edge.dst)
    plan = {
        skill.removeprefix("skill:"): sorted(direct.get(skill, agents))[0].removeprefix("agent:")
        for skill, agents in agent_reach(graph).items()
    }
    for skill, agent in PINNED_AGENTS.items():
        if ("skill:" + skill, "agent:" + agent, "dispatch") not in graph.edges:
            raise SystemExit(f"CHECK FAILED [pinned probe]: {skill} no longer dispatches {agent}")
        plan[skill] = agent
    return plan


def user_only_skills(skills_dir: Path) -> set[str]:
    """Skills with disable-model-invocation: reachable only through their slash command."""
    return {
        path.parent.name
        for path in skills_dir.glob("*/SKILL.md")
        if re.search(r"^disable-model-invocation:\s*true\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    }


def install(lab: SplitLab, market: Path) -> list[dict[str, Any]]:
    """Add the lab catalog, install only ycc, and prove ycc-agents arrives via dependencies."""
    add = ["plugin", "marketplace", "add", str(market)]
    _, add_help = lab.run("help-add", ["plugin", "marketplace", "add", "--help"])
    code, _ = lab.run("marketplace-add", add + (["--scope", "user"] if "--scope" in add_help else []))
    check("marketplace add", 0, code)
    code, _ = lab.run("install-ycc", ["plugin", "install", f"{SKILLS_PACKAGE}@{LAB_MARKET}", "--scope", "user"])
    check("plugin install ycc", 0, code)
    code, out = lab.run("plugin-list", ["plugin", "list", "--json"])
    check("plugin list", 0, code)
    listing: list[dict[str, Any]] = json.loads(out)
    ids = sorted(str(item.get("id")) for item in listing)
    check(
        "installed ids (ycc pulls ycc-agents)",
        sorted(f"{k}@{LAB_MARKET}" for k in (SKILLS_PACKAGE, AGENTS_PACKAGE)),
        ids,
    )
    check("all enabled", [True] * len(listing), [item.get("enabled") for item in listing])
    lab.installed = {f"{k}@{LAB_MARKET}": k for k in (SKILLS_PACKAGE, AGENTS_PACKAGE)}
    lab.listing = listing
    print(f"PASS dependency install: {', '.join(ids)}", flush=True)
    return listing


def assert_inventory(row: dict[str, Any], skills: list[str], agents: list[str]) -> None:
    """The session sees split skills under ycc: and every agent only under ycc-agents:."""
    init = row["init"]
    seen_skills = {str(s) for s in init.get("skills", [])}
    seen_agents = {str(a) for a in init.get("agents", [])}
    check("init lists every ycc agent as ycc-agents:<name>", [], sorted(set(agents) - seen_agents))
    check("init lists no ycc:<agent>", [], sorted(a for a in seen_agents if a.startswith(SKILLS_PACKAGE + ":")))
    check("init lists every dispatching skill", [], sorted(set(skills) - seen_skills))


def assert_dispatch(row: dict[str, Any], skill_key: str, agent_key: str, slash: bool) -> None:
    label = row["label"]
    check(label + " status", "observed", row["status"])
    if not slash:
        skill_result = select_result(row["tool_results"], "toolu_ns_skill")
        check(label + " Skill result ok", False, skill_result.get("is_error", False))
    check(label + " skill body reached parent", True, row["markers_in_parent_messages"][skill_key])
    agent_result = select_result(row["tool_results"], "toolu_ns_agent")
    check(label + " Agent result ok", False, agent_result.get("is_error", False))
    check(label + " child request exists", True, row["subagent_requests"] > 0)
    check(label + " child SYSTEM is the agent prompt", True, row["child_system_markers"][agent_key])
    check(label + " agent prompt absent from first parent request", False, row["first_parent_markers"][agent_key])


def execute(lab: SplitLab, market: Path, plan: dict[str, str]) -> dict[str, Any]:
    install(lab, market)
    skills_dir, agents_dir = market / SKILLS_PACKAGE / "skills", market / AGENTS_PACKAGE / "agents"
    agent_paths = {agent_frontmatter(p.read_text(encoding="utf-8"))[0]: p for p in agents_dir.glob("*.md")}
    user_only = user_only_skills(skills_dir)
    summary: dict[str, Any] = {"version": lab.version, "dispatch": {}, "negative": None, "bare": None}
    for index, (skill, agent) in enumerate(sorted(plan.items())):
        markers = {"skill": body_marker(skills_dir / skill / "SKILL.md"), "agent": body_marker(agent_paths[agent])}
        slash = skill in user_only
        label = f"dispatch-{skill}"
        prompt_skill = f"{SKILLS_PACKAGE}:{skill}"
        lab.allowed = injections(market, skill)
        split_probe(lab, label, prompt_skill, AGENTS_PREFIX + agent, markers, slash)
        row = lab.results[-1]
        if index == 0:
            assert_inventory(row, [prompt_skill], [AGENTS_PREFIX + name for name in agent_paths])
        assert_dispatch(row, "skill", "agent", slash)
        summary["dispatch"][skill] = AGENTS_PREFIX + agent
        print(f"PASS {skill} -> {AGENTS_PREFIX}{agent}{' (slash)' if slash else ''}", flush=True)
    split_probe(lab, "negative-absent", f"{SKILLS_PACKAGE}:plan", NEGATIVE_AGENT, {}, False)
    negative = select_result(lab.results[-1]["tool_results"], "toolu_ns_agent")
    check("negative control is_error", True, negative.get("is_error", False))
    check("negative control names target", True, NEGATIVE_AGENT in json.dumps(negative.get("content", "")))
    check("negative control spawns no child", 0, lab.results[-1]["subagent_requests"])
    summary["negative"] = "error"
    print(f"PASS negative control: {NEGATIVE_AGENT} errors without a child request", flush=True)
    skill, agent = BARE_PROBE
    markers = {"agent": body_marker(agent_paths[agent])}
    split_probe(lab, "observe-bare", f"{SKILLS_PACKAGE}:{skill}", agent, markers, False)
    bare = select_result(lab.results[-1]["tool_results"], "toolu_ns_agent")
    resolved = not bare.get("is_error", False) and lab.results[-1]["child_system_markers"].get("agent", False)
    summary["bare"] = {"subagent_type": agent, "resolved": bool(resolved)}
    print(f"OBSERVED bare dispatch subagent_type={agent!r}: resolved={bool(resolved)} (recorded, not asserted)")
    return summary


def split_probe(lab: SplitLab, label: str, skill: str, agent: str, markers: dict[str, str], slash: bool) -> None:
    """Run one Lab probe; user-only skills start from their slash command instead of the Skill tool."""
    lab.slash = skill if slash else ""
    try:
        lab.probe(label, skill, agent, markers)
    finally:
        lab.slash, lab.allowed = "", ()


def injections(market: Path, skill: str) -> tuple[str, ...]:
    """Exact, plugin-rooted skill-load commands (as the CLI expands them) for one skill."""
    text = (market / SKILLS_PACKAGE / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    return tuple(str(market.resolve() / SKILLS_PACKAGE) + match[1] for match in INJECTION.finditer(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Lab evidence root (must not exist).")
    parser.add_argument("binary")
    parser.add_argument("version")
    parser.add_argument("market", type=Path, help="Built split marketplace (claude_agents_split.py --out).")
    parser.add_argument("--source-root", type=Path, default=SCRIPTS_DIR.parent / "ycc")
    args = parser.parse_args(argv)
    negative_self_test()
    plan = dispatch_plan(args.source_root)
    lab = SplitLab(args.root, args.binary, args.version)
    lab.home = args.root / "home"
    try:
        summary = execute(lab, args.market, plan)
    finally:
        lab.kill_child()
        lab.server.shutdown()
        lab.server.server_close()
    summary["dispatch_pass"] = f"{len(summary['dispatch'])}/{len(plan)}"
    save(args.root / "summary.json", summary)
    print(f"{args.version} split dispatch: {summary['dispatch_pass']} skills verified", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
