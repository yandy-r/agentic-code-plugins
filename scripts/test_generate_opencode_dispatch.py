#!/usr/bin/env python3
"""Focused regressions for the OpenCode V2 dispatch projection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from generate_opencode_commands import discover_skills, transform_command
from generate_opencode_common import SRC_SKILLS_DIR, load_agent_aliases, load_model_aliases
from generate_opencode_dispatch import (
    project_opencode_dispatch,
    project_opencode_dispatch_description,
    render_standalone_dispatch_reference,
)
from generate_opencode_skills import transform_skill_markdown
from validate_opencode_dispatch import find_dispatch_residue

REPO_ROOT = Path(__file__).resolve().parent.parent


class OpenCodeDispatchProjectionTestCase(unittest.TestCase):
    def test_core_commands_preserve_description_boundaries(self) -> None:
        aliases = load_agent_aliases()
        model_aliases = load_model_aliases()
        commands = (
            "plan-workflow",
            "parallel-plan",
            "shared-context",
            "feature-research",
        )

        for command in commands:
            with self.subTest(command=command):
                source_path = REPO_ROOT / "ycc" / "skills" / command / "SKILL.md"
                rendered = transform_command(
                    command,
                    source_path.read_text(encoding="utf-8"),
                    aliases,
                    model_aliases,
                )
                self.assertEqual(
                    find_dispatch_residue(rendered, f"commands/{command}.md"),
                    [],
                )

    def test_core_workflows_render_with_all_required_contracts(self) -> None:
        aliases = load_agent_aliases()
        core_skills = (
            "shared-context",
            "parallel-plan",
            "plan",
            "plan-workflow",
            "feature-research",
            "deep-research",
            "code-review",
            "quick-review",
            "review-fix",
            "implement-plan",
            "orchestrate",
            "prp-plan",
        )

        for skill in core_skills:
            with self.subTest(skill=skill):
                source_path = REPO_ROOT / "ycc" / "skills" / skill / "SKILL.md"
                generated_path = f"skills/{skill}/SKILL.md"
                rendered = transform_skill_markdown(
                    source_path.read_text(encoding="utf-8"),
                    aliases,
                    Path(skill) / "SKILL.md",
                )

                self.assertEqual(
                    find_dispatch_residue(rendered, generated_path),
                    [],
                )

    def test_reference_uses_native_new_resume_and_result_contracts(self) -> None:
        rendered = render_standalone_dispatch_reference()

        self.assertIn('subagent(agent="<agent>", description="<short title>",', rendered)
        self.assertIn("background=false", rendered)
        self.assertIn("background=true", rendered)
        self.assertIn('sessionID="<existing child session ID>"', rendered)
        self.assertIn('task_status(sessionID="<child session ID>")', rendered)
        self.assertIn('task_result(sessionID="<child session ID>")', rendered)
        self.assertIn("does not verify the deliverables", rendered)
        self.assertIn("contentless completion is incomplete", rendered)
        self.assertIn("Inspect the working tree", rendered)
        self.assertIn("one retry", rendered)
        self.assertEqual(find_dispatch_residue(rendered, "standalone-dispatch.md"), [])

    def test_implement_plan_uses_foreground_native_dispatch_and_verifies_work(self) -> None:
        source = """# Parallel Plan Executor

Defaults to standalone sub-agents. Worktree isolation is enabled.

- `--dry-run` — Show the plan without dispatching.

Strip flags and set `DRY_RUN=true|false`.

Usage: /implement-plan [--dry-run] [--worktree] [--no-worktree] <feature-name>

### Path A — Standalone Sub-Agent Batches (default)

Standalone batches dispatch via the blocking `Task` tool.

#### Path A — Task spawn

| Field | Value |
| subagent_type | `implementor` |

No `team_name`, no `run_in_background`.

**When `WORKTREE_ACTIVE=true`**, include the working directory.

#### Process Batch Results (Path A)

After each batch completes:

1. Mark it complete.

#### Repeat Until Complete (Path A)

Use multiple Task calls.

### Path B — Agent Team Batches (`--team`)

TeamCreate then Agent(team_name="impl").
"""

        projected = project_opencode_dispatch(source, "skills/implement-plan/SKILL.md")

        self.assertIn('subagent(agent="implementor"', projected)
        self.assertIn("background=false", projected)
        self.assertIn("Validate every nonempty report", projected)
        self.assertIn("Inspect the working tree", projected)
        self.assertIn("`sessionID`", projected)
        self.assertNotIn("Path B", projected)
        self.assertEqual(find_dispatch_residue(projected, "skills/implement-plan/SKILL.md"), [])

    def test_implementor_does_not_promise_inline_task_return(self) -> None:
        source = """### 5. Required Final `STATUS:` Line

You are dispatched via the blocking `Task` tool — your entire response is returned
inline to the orchestrator in the same turn, so it must be mechanically parseable.
Always end with `STATUS: Complete`.
"""

        projected = project_opencode_dispatch(source, "agents/implementor.md")

        self.assertIn("native `subagent` tool", projected)
        self.assertIn("lifecycle state alone", projected)
        self.assertNotIn("same turn", projected)
        self.assertEqual(find_dispatch_residue(projected, "agents/implementor.md"), [])

    def test_team_only_sections_are_removed_and_team_flag_aborts(self) -> None:
        source = """# Workflow

Use `--team` to dispatch a shared team.

### Team Setup (if `--team`)

TeamCreate then Agent(team_name="demo").

### Standalone Work

Use Task(subagent_type="planner", run_in_background=false).
"""

        projected = project_opencode_dispatch(source, "skills/example/SKILL.md")

        self.assertIn("`--team` is unsupported", projected)
        self.assertIn('subagent(agent="planner", background=false)', projected)
        self.assertNotIn("Team Setup", projected)
        self.assertEqual(find_dispatch_residue(projected, "example.md"), [])

    def test_multiline_native_call_gets_explicit_foreground_intent(self) -> None:
        source = """subagent(
  agent = "planner",
  description = "Plan",
  prompt = "Return the plan"
)
"""

        projected = project_opencode_dispatch(source, "skills/example/SKILL.md")

        self.assertIn("background = false", projected)

    def test_quoted_parentheses_do_not_corrupt_native_call(self) -> None:
        source = 'Task(subagent_type="planner", prompt="Review foo(bar)")\n'

        projected = project_opencode_dispatch(source, "skills/example/SKILL.md")

        self.assertIn('prompt="Review foo(bar)"', projected)
        self.assertIn("background=false)", projected)
        self.assertEqual(find_dispatch_residue(projected, "quoted-call.md"), [])

    def test_nested_parentheses_do_not_corrupt_native_call(self) -> None:
        source = 'Task(subagent_type="planner", prompt=build(foo(bar)))\n'

        projected = project_opencode_dispatch(source, "skills/example/SKILL.md")

        self.assertIn("prompt=build(foo(bar))", projected)
        self.assertIn("background=false)", projected)
        self.assertEqual(find_dispatch_residue(projected, "nested-call.md"), [])

    def test_native_roles_use_description_and_prompt_not_name(self) -> None:
        source = "The `name=` field on the Task/subagent call differentiates roles.\n"

        projected = project_opencode_dispatch(source, "skills/example/reference.md")

        self.assertNotIn("`name=`", projected)
        self.assertIn("`description`", projected)
        self.assertIn("role-specific `prompt`", projected)

    def test_prp_implement_drops_stale_team_path_choice(self) -> None:
        source = """# Execute

### Path C — Agent Team Batch Execution

Unsupported team work.

Accept the choice → **Path A**, **Path B**, or **Path C**.
"""

        projected = project_opencode_dispatch(source, "skills/prp-implement/SKILL.md")

        self.assertNotIn("Agent Team", projected)
        self.assertNotIn("**Path C**", projected)

    def test_description_drops_unsupported_team_advertising(self) -> None:
        description = (
            "Execute a plan with standalone agents; pass --team (Claude Code only) "
            "to use an agent team. Defaults to the opencode `task` tool. "
            "Usage: [--team] [--no-worktree]."
        )

        projected = project_opencode_dispatch_description(description)

        self.assertNotIn("--team", projected)
        self.assertNotIn("agent team", projected)
        self.assertNotIn("`task` tool", projected)
        self.assertIn("native `subagent` tool", projected)
        self.assertIn("Execute a plan with standalone agents", projected)
        self.assertIn("[--no-worktree]", projected)

    def test_description_preserves_non_team_clause_before_team_opt_in(self) -> None:
        description = "Use this workflow for database changes and pass --team for coordination. Keep backups."

        projected = project_opencode_dispatch_description(description)

        self.assertIn("Use this workflow for database changes", projected)
        self.assertIn("Keep backups", projected)
        self.assertNotIn("--team", projected)

    def test_natural_language_task_is_not_rewritten(self) -> None:
        source = "Implement the task, then update the task status.\n"

        self.assertEqual(project_opencode_dispatch(source, "skills/example/SKILL.md"), source)

    def test_validator_reports_legacy_dispatch_syntax(self) -> None:
        legacy = 'Task(subagent_type="planner", run_in_background=true)\n'

        errors = find_dispatch_residue(legacy, "legacy.md")

        self.assertTrue(any("Task(" in error for error in errors))
        self.assertTrue(any("subagent_type" in error for error in errors))
        self.assertTrue(any("run_in_background" in error for error in errors))

    def test_validator_rejects_inline_guarantees_and_blanket_polling_bans(self) -> None:
        legacy = "The subagent blocks and returns inline in the same turn. Do not poll.\n"

        errors = find_dispatch_residue(legacy, "legacy-semantics.md")

        self.assertTrue(any("inline-return" in error for error in errors))
        self.assertTrue(any("polling ban" in error for error in errors))

    def test_validator_cli_inputs_can_be_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native.md"
            path.write_text(
                'subagent(agent="planner", description="Plan", prompt="Return a plan", background=false)\n',
                encoding="utf-8",
            )

            self.assertEqual(
                find_dispatch_residue(path.read_text(encoding="utf-8"), str(path)),
                [],
            )

    def test_generated_commands_are_skill_dispatches(self) -> None:
        aliases = load_agent_aliases()
        model_aliases = load_model_aliases()
        rendered = transform_command(
            "clean",
            (REPO_ROOT / "ycc" / "skills" / "clean" / "SKILL.md").read_text(encoding="utf-8"),
            aliases,
            model_aliases,
        )
        self.assertIn("$ARGUMENTS", rendered)
        self.assertIn("clean", rendered)
        self.assertNotIn("Task(", rendered)
        self.assertNotIn("subagent_type", rendered)

    def test_command_discovery_skips_private_skills(self) -> None:
        stems = [path.parent.name for path in discover_skills(SRC_SKILLS_DIR)]
        self.assertNotIn("_shared", stems)

    def test_command_description_keeps_argument_hint(self) -> None:
        aliases = load_agent_aliases()
        model_aliases = load_model_aliases()
        rendered = transform_command(
            "clean",
            (REPO_ROOT / "ycc" / "skills" / "clean" / "SKILL.md").read_text(encoding="utf-8"),
            aliases,
            model_aliases,
        )
        self.assertNotIn("usage: none", rendered.lower())


if __name__ == "__main__":
    unittest.main()
