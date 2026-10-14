#!/usr/bin/env python3
"""Unit tests for scripts/generate_cursor_skills.py rewrite transforms."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_cursor_skills import apply_skills_text_transforms  # noqa: E402


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
        self.assertIn("the task tracker", transformed)
        self.assertIn("record the task", transformed)
        self.assertIn("update the task tracker", transformed)
        self.assertIn("the task details", transformed)
        self.assertIn("create an agent group", transformed)
        self.assertIn("close the agent group", transformed)

    def test_rewrites_agent_launch_regex(self) -> None:
        self.assertIn(
            "invoke the `implementor` agent",
            apply_skills_text_transforms("Use the Agent tool to launch the `implementor` agent"),
        )
        self.assertIn(
            "invoke the `reviewer` agent",
            apply_skills_text_transforms("Use the Agent tool to launch the reviewer agent"),
        )


if __name__ == "__main__":
    unittest.main()
