#!/usr/bin/env python3
"""Hidden v7 Claude split: rewrite table, unknown targets, validator rules, determinism, real tree."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from claude_agents_split import (  # noqa: E402
    Catalog,
    SplitError,
    build_and_validate,
    build_split,
    rewrite_text,
    validate_split,
)

CATALOG = Catalog(
    skills=frozenset({"releaser", "plan", "init"}),
    aliases={
        "planner": "planner",
        "implementor": "implementor",
        "releaser": "releaser",
        "codebase-research-analyst": "codebase-research-analyst",
        "code-researcher": "codebase-research-analyst",
    },
)


def rewrite(line: str) -> str:
    return rewrite_text(line + "\n", CATALOG, "fixture.md")[0].rstrip("\n")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def source_tree(parent: Path) -> Path:
    """Minimal canonical source: catalog skills, two dispatching skills, three agents."""
    root = parent / "ycc"
    write(root / ".claude-plugin/plugin.json", json.dumps({"name": "ycc", "version": "9.9.9", "author": {"name": "t"}}))
    write(root / "settings/packages.json", json.dumps({"packages": {"ycc-agents": {"description": "Agents only."}}}))
    for skill in ("init", "orchestrate", "write-docs"):
        write(root / f"skills/{skill}/SKILL.md", f"---\nname: {skill}\n---\n")
    write(root / "skills/plan/SKILL.md", '---\nname: plan\n---\nUse `subagent_type: "ycc:planner"`.\n')
    write(
        root / "skills/releaser/SKILL.md",
        "---\nname: releaser\n---\nRun `/ycc:releaser`; delegate to the `ycc:releaser` agent.\n",
    )
    write(root / "skills/releaser/scripts/run.sh", "#!/usr/bin/env bash\n")
    (root / "skills/releaser/scripts/run.sh").chmod(0o755)
    write(root / "skills/_shared/references/d.md", "Dispatch `subagent_type=implementor`.\n")
    write(root / "agents/planner.md", "---\nname: planner\n---\nHand off to `ycc:implementor`.\n")
    write(root / "agents/implementor.md", "---\nname: implementor\n---\nSee `/ycc:plan`.\n")
    write(root / "agents/releaser.md", "---\nname: releaser\n---\nCalled by the `ycc:releaser` skill.\n")
    return root


class RewriteTableTests(unittest.TestCase):
    def test_rewrite_table(self) -> None:
        cases = {
            'subagent_type: "ycc:planner"': 'subagent_type: "ycc-agents:planner"',
            "subagent_type=implementor": "subagent_type=ycc-agents:implementor",
            "| Subagent Type | `implementor` |": "| Subagent Type | `ycc-agents:implementor` |",
            "**Subagent Type**: `code-researcher`": "**Subagent Type**: `ycc-agents:codebase-research-analyst`",
            'subagent_type: "explore"': 'subagent_type: "explore"',
            'subagent_type="ycc:general-purpose"': 'subagent_type="general-purpose"',
            'subagent_type="<type>"': 'subagent_type="<type>"',
            "single ycc:planner via Agent": "single ycc-agents:planner via Agent",
            "Run `/ycc:releaser` now": "Run `/ycc:releaser` now",
            "see the ycc:releaser skill": "see the ycc:releaser skill",
            "delegate to the `ycc:releaser` agent": "delegate to the `ycc-agents:releaser` agent",
            'subagent_type: "ycc:releaser"': 'subagent_type: "ycc-agents:releaser"',
            "- Agent: planner": "- Agent: ycc-agents:planner",
            "All three use `implementor`.": "All three use `ycc-agents:implementor`.",
            "already `ycc-agents:planner`": "already `ycc-agents:planner`",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(rewrite(source), expected)

    def test_table_columns_rewrite_only_agent_values(self) -> None:
        table = "| Teammate | Type | Output |\n| --- | --- | --- |\n| `arch` | `implementor` | `plan.md` |\n"
        expected = (
            "| Teammate | Type | Output |\n| --- | --- | --- |\n| `arch` | `ycc-agents:implementor` | `plan.md` |\n"
        )
        self.assertEqual(rewrite_text(table, CATALOG, "t.md")[0], expected)

    def test_multiple_tokens_on_one_line_keep_offsets(self) -> None:
        line = "ycc:planner then ycc:implementor then /ycc:plan"
        self.assertEqual(rewrite(line), "ycc-agents:planner then ycc-agents:implementor then /ycc:plan")

    def test_unknown_targets_fail_loudly(self) -> None:
        for line in ("subagent_type: ghost", 'subagent_type: "ycc:ghost"', "hand off to ycc:ghost"):
            with self.subTest(line=line), self.assertRaisesRegex(SplitError, "ghost.*neither a known agent"):
                rewrite_text(line + "\n", CATALOG, "f.md")

    def test_multi_span_dispatch_cell_and_arrow_list(self) -> None:
        table = "| Task | Recommended Agent |\n| --- | --- |\n| Find | `explore`, `planner` or `code-researcher` |\n"
        expected = (
            "| Task | Recommended Agent |\n| --- | --- |\n"
            "| Find | `explore`, `ycc-agents:planner` or `ycc-agents:codebase-research-analyst` |\n"
        )
        self.assertEqual(rewrite_text(table, CATALOG, "t.md")[0], expected)
        self.assertEqual(rewrite("- Backend → implementor"), "- Backend → ycc-agents:implementor")
        self.assertEqual(
            rewrite("1. planner + implementor (parallel)"), "1. ycc-agents:planner + ycc-agents:implementor (parallel)"
        )

    def test_shell_string_literals_and_role_allowlist(self) -> None:
        script = 'VALID=(\n  "explore"\n  "implementor"\n)\necho "- planner or implementor"\n# planner prose\n'
        expected = (
            'VALID=(\n  "explore"\n  "ycc-agents:implementor"\n)\n'
            'echo "- ycc-agents:planner or ycc-agents:implementor"\n# planner prose\n'
        )
        self.assertEqual(rewrite_text(script, CATALOG, "s.sh", shell=True)[0], expected)
        persona = "| `planner` | `implementor` |\n"
        kept = rewrite_text(persona, CATALOG, "p.md", allowed=frozenset({"planner"}))[0]
        self.assertEqual(kept, "| `planner` | `ycc-agents:implementor` |\n")


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = source_tree(Path(self.tmp.name) / "src")
        self.out = Path(self.tmp.name) / "out"

    def test_layout_manifests_and_counts(self) -> None:
        report = build_and_validate(self.source, self.out)
        self.assertEqual(report.errors, [])
        self.assertEqual((report.rewritten_dispatches, report.rewritten_mentions, report.rewritten_handoffs), (2, 1, 1))
        # Prose `ycc:releaser` agent mentions are rewritten but stay out of the dispatch closure.
        self.assertEqual(sorted(report.dispatching_skills), ["plan"])
        skills = json.loads((self.out / "ycc/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
        agents = json.loads((self.out / "ycc-agents/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual((skills["name"], skills["version"], skills["dependencies"]), ("ycc", "9.9.9", ["ycc-agents"]))
        self.assertEqual(
            (agents["name"], agents["version"], agents["description"]), ("ycc-agents", "9.9.9", "Agents only.")
        )
        self.assertFalse((self.out / "ycc/agents").exists())
        self.assertTrue((self.out / "ycc/skills/_shared/references/d.md").is_file())
        self.assertTrue((self.out / "ycc/skills/releaser/scripts/run.sh").stat().st_mode & 0o100)
        releaser = (self.out / "ycc/skills/releaser/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`/ycc:releaser`", releaser)
        self.assertIn("`ycc-agents:releaser` agent", releaser)
        self.assertIn("`ycc:releaser` skill", (self.out / "ycc-agents/agents/releaser.md").read_text(encoding="utf-8"))

    def test_unknown_source_dispatch_fails_build(self) -> None:
        write(self.source / "skills/plan/SKILL.md", "---\nname: plan\n---\nsubagent_type: ghost\n")
        with self.assertRaisesRegex(SplitError, "ghost"):
            build_split(self.source, self.out)

    def test_non_empty_output_is_refused(self) -> None:
        write(self.out / "stale.txt", "x")
        with self.assertRaisesRegex(SplitError, "must be empty"):
            build_split(self.source, self.out)

    def test_deterministic_bytes_and_modes(self) -> None:
        second = Path(self.tmp.name) / "again"
        build_split(self.source, self.out)
        build_split(self.source, second)

        def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
            return {
                p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mode)
                for p in sorted(root.rglob("*"))
                if p.is_file()
            }

        self.assertEqual(snapshot(self.out), snapshot(second))


class ValidatorRuleTests(unittest.TestCase):
    """One negative fixture per rule, each applied to an otherwise valid split tree."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"
        self.expected = build_split(source_tree(Path(self.tmp.name) / "src"), self.out).dispatching_skills
        self.assertEqual(validate_split(self.out, self.expected), [])

    def errors_after(self, relative: str, text: str) -> list[str]:
        write(self.out / relative, text)
        return validate_split(self.out, self.expected)

    def assert_rule(self, relative: str, text: str, needle: str) -> None:
        errors = self.errors_after(relative, text)
        self.assertTrue(any(needle in error for error in errors), errors)

    def test_a_unknown_qualified_target(self) -> None:
        self.assert_rule("ycc/skills/plan/extra.md", "subagent_type: ycc-agents:ghost\n", "not an agent frontmatter")

    def test_a_builtin_must_stay_bare(self) -> None:
        self.assert_rule("ycc/skills/plan/extra.md", "subagent_type: ycc-agents:explore\n", "must stay bare")

    def test_b_leftover_ycc_dispatch_and_bare_dispatch(self) -> None:
        self.assert_rule("ycc/skills/plan/extra.md", 'subagent_type: "ycc:planner"\n', "unqualified agent reference")
        self.assert_rule("ycc/skills/plan/more.md", "subagent_type: planner\n", "bare plugin-agent dispatch")

    def test_b_leftover_agent_handoff(self) -> None:
        self.assert_rule("ycc-agents/agents/extra.md", "---\nname: extra\n---\nAsk ycc:planner.\n", "'ycc:planner'")

    def test_b_bare_agent_names_in_code_tables_and_shell(self) -> None:
        self.assert_rule(
            "ycc/skills/plan/extra.md", "| T | `planner`, `explore` |\n", "bare plugin-agent name 'planner'"
        )
        self.assert_rule("ycc/skills/plan/arrow.md", "- Docs → implementor\n", "bare plugin-agent name 'implementor'")
        self.assert_rule("ycc/skills/plan/v.sh", 'VALID=("implementor")\n', "bare plugin-agent name 'implementor'")

    def test_c_skill_reference_must_resolve(self) -> None:
        self.assert_rule("ycc/skills/plan/extra.md", "Run `/ycc:missing-skill`.\n", "does not resolve in split ycc")

    def test_d_split_directories(self) -> None:
        self.assert_rule("ycc/agents/planner.md", "---\nname: planner\n---\n", "agents/ directory")
        shutil.rmtree(self.out / "ycc/agents")
        self.assert_rule("ycc-agents/skills/x/SKILL.md", "---\nname: x\n---\n", "skills/ directory")

    def test_e_dispatching_skill_must_keep_a_dispatch(self) -> None:
        self.assert_rule("ycc/skills/plan/SKILL.md", "---\nname: plan\n---\nNo dispatch.\n", "'plan' reaches no")

    def test_e_retargeted_dispatch_changes_reached_agents(self) -> None:
        text = '---\nname: plan\n---\nUse `subagent_type: "ycc-agents:implementor"`.\n'
        self.assert_rule("ycc/skills/plan/SKILL.md", text, "'plan' reaches ('agent:implementor',); expected")

    def test_f_agent_preloads_must_be_qualified(self) -> None:
        agent = "ycc-agents/agents/implementor.md"
        self.assert_rule(agent, "---\nname: implementor\nskills:\n  - plan\n---\n", "agent preload 'plan'")
        self.assertEqual(self.errors_after(agent, "---\nname: implementor\nskills:\n  - ycc:plan\n---\n"), [])

    def test_manifest_dependency_is_required(self) -> None:
        manifest = {"name": "ycc", "version": "9.9.9", "author": {"name": "t"}}
        self.assert_rule("ycc/.claude-plugin/plugin.json", json.dumps(manifest), "dependencies ['ycc-agents']")

    def test_agents_dir_reach_in_is_an_error(self) -> None:
        for line in (
            'ls "${PLUGIN_ROOT}/agents"',
            'ls "${CLAUDE_PLUGIN_ROOT}"/agents/x.md',
            'ls "${CLAUDE_PLUGIN_ROOT:-.}/agents"',
            'ls "$SCRIPT_DIR/../../../agents"',
        ):
            with self.subTest(line=line):
                self.assert_rule("ycc/skills/plan/check.sh", line + "\n", "reads the plugin's own agents/")

    def test_agents_prefixed_path_is_not_a_reach_in(self) -> None:
        self.assertEqual(self.errors_after("ycc/skills/plan/check.sh", 'ls "${PLUGIN_ROOT}/agents-team"\n'), [])


class RealTreeTests(unittest.TestCase):
    def test_real_source_builds_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_and_validate(REPO_ROOT / "ycc", Path(tmp))
        self.assertEqual(report.errors, [])
        self.assertEqual(report.agents, 55)
        for skill in ("feature-research", "plan-workflow", "git-workflow", "clean", "implement-plan", "releaser"):
            self.assertIn(skill, report.dispatching_skills)
        self.assertIn("agent:release-fix-applier", report.dispatching_skills["releaser"])


if __name__ == "__main__":
    unittest.main()
