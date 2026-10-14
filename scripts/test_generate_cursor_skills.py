#!/usr/bin/env python3
"""Unit tests for scripts/generate_cursor_skills.py rewrite transforms."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_codex_common import apply_codex_text_transforms, parse_frontmatter  # noqa: E402
from generate_cursor_skills import apply_skills_text_transforms, transform_text_content  # noqa: E402
from generate_opencode_dispatch_markdown import _remove_team_operations  # noqa: E402


class CursorSkillsTransformsTestCase(unittest.TestCase):
    def test_rewrites_agent_and_task_tool_phrasing(self) -> None:
        cases = (
            (
                "Refer to Agent tool description for latest updates.",
                "Refer to Cursor agent documentation for latest updates.",
            ),
            ("available agents in the Agent tool", "available agents in Cursor"),
            ("List of all valid agent types from Agent tool", "List of all valid agent types for Cursor"),
            ("Use the Agent tool with", "Use parallel agents with"),
            ("the Agent tool", "Cursor"),
            ("Agent tool calls", "parallel agent invocations"),
            ("Agent tool call", "agent invocation"),
            ("Single Agent tool call", "Single agent invocation"),
            ("MULTIPLE Agent tool calls", "MULTIPLE parallel agent invocations"),
            ("the Task tool", "Cursor"),
            ("Task tool calls", "parallel agent invocations"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertIn(expected, apply_skills_text_transforms(source))

    def test_rewrites_task_tracking_tools(self) -> None:
        source = (
            "Track progress via TodoWrite.\n"
            "Use TaskCreate to register tasks, then TaskUpdate to update progress.\n"
            "Query TaskList for batch completion and TaskGet for details.\n"
            "Do not invoke TeamCreate or TeamDelete in bundles.\n"
        )
        transformed = apply_skills_text_transforms(source)
        self.assertNotIn("TodoWrite", transformed)
        self.assertNotIn("TaskCreate", transformed)
        self.assertNotIn("TaskUpdate", transformed)
        self.assertNotIn("TaskList", transformed)
        self.assertNotIn("TaskGet", transformed)
        self.assertNotIn("TeamCreate", transformed)
        self.assertNotIn("TeamDelete", transformed)
        self.assertIn("task tracker", transformed)
        self.assertIn("task registration", transformed)
        self.assertIn("task status update", transformed)
        self.assertIn("task details", transformed)
        self.assertIn("agent group setup", transformed)
        self.assertIn("agent group cleanup", transformed)
        self.assertNotIn("the the", transformed)

    def test_rewrites_agent_launch_regex(self) -> None:
        self.assertIn(
            "invoke the `implementor` agent",
            apply_skills_text_transforms("Use the Agent tool to launch the `implementor` agent"),
        )
        self.assertIn(
            "invoke the `reviewer` agent",
            apply_skills_text_transforms("Use the Agent tool to launch the reviewer agent"),
        )

    def test_frontmatter_tool_identifiers_are_preserved(self) -> None:
        source = (
            "---\nname: demo\nallowed-tools:\n  - Agent\n  - TaskCreate\n  - TaskGet\n"
            "  - TaskList\n  - TaskUpdate\n---\nUse TaskCreate then TaskList.\n"
        )
        out = transform_text_content(source, Path("demo/SKILL.md"))
        frontmatter, body = out.split("\n---\n", 1)
        listed = [line.strip()[2:] for line in frontmatter.splitlines() if line.startswith("  - ")]
        self.assertEqual(listed, ["Agent", "TaskCreate", "TaskGet", "TaskList", "TaskUpdate"])
        self.assertNotIn("TaskCreate", body)

    def test_generated_allowed_tools_are_real_tool_names(self) -> None:
        root = Path(__file__).resolve().parent.parent
        invalid_phrases = ("record the task", "the task", "task registration", "task list", "task details")
        for skill in sorted((root / "ycc" / "skills").glob("*/SKILL.md")):
            rel = skill.relative_to(root / "ycc" / "skills")
            generated = transform_text_content(skill.read_text(encoding="utf-8"), rel)
            tools = parse_frontmatter(generated)[0].get("allowed-tools", [])
            if isinstance(tools, str):
                tools = [tools]
            for tool in tools:
                with self.subTest(skill=skill.parent.name, tool=tool):
                    self.assertFalse(any(phrase in tool for phrase in invalid_phrases))

    def test_word_boundaries_and_article_artifacts(self) -> None:
        self.assertEqual(apply_skills_text_transforms("TaskListX"), "TaskListX")
        self.assertNotIn("the the", apply_codex_text_transforms("the TaskList and the TodoWrite", {}))

    def test_team_lifecycle_reference_is_unsupported_note(self) -> None:
        out = transform_text_content("### Step 2 — TaskCreate\n", Path("_shared/references/agent-team-dispatch.md"))
        self.assertIn("unsupported in the Cursor bundle", out)
        self.assertNotIn("TaskCreate", out)

    def test_opencode_standalone_sentence_join(self) -> None:
        out = _remove_team_operations(
            "One message, multiple calls, no `name`, no `run_in_background`. Next.\n", add_compatibility_note=False
        )
        self.assertNotIn("calls, Each", out)
        self.assertIn("calls. Each call uses native foreground arguments.", out)


if __name__ == "__main__":
    unittest.main()
