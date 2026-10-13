#!/usr/bin/env python3
"""Tests for scripts/generate_codex_agents.py (sandbox_mode emission).

Run directly (``python3 scripts/test_generate_codex_agents.py``) or through
``./scripts/validate.sh --only codex``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_codex_agents import build_agent_toml, is_read_only  # noqa: E402
from generate_opencode_agents import convert_tools_to_permissions  # noqa: E402


class ReadOnlyDetectionTestCase(unittest.TestCase):
    def test_read_only_tools(self) -> None:
        self.assertTrue(is_read_only(["Read", "Grep", "Glob"]))
        self.assertTrue(is_read_only(["Read", "Glob", "WebFetch", "WebSearch"]))
        self.assertTrue(is_read_only("Read, Grep, Glob"))

    def test_write_tools_are_not_read_only(self) -> None:
        for tool in ("Write", "Edit", "NotebookEdit", "Bash"):
            self.assertFalse(is_read_only(["Read", "Grep", tool]), tool)

    def test_scoped_bash_counts_as_write(self) -> None:
        self.assertFalse(is_read_only(["Read", "Bash(git diff:*)"]))

    def test_mcp_tools_count_as_write(self) -> None:
        self.assertFalse(is_read_only(["Read", "mcp__sql__execute-sql"]))
        self.assertFalse(is_read_only(["Read", "mcp__context7__query-docs"]))

    def test_missing_tools_is_not_read_only(self) -> None:
        self.assertFalse(is_read_only(None))
        self.assertFalse(is_read_only([]))


class BuildAgentTomlTestCase(unittest.TestCase):
    def test_emits_read_only_sandbox(self) -> None:
        toml = build_agent_toml("advisory", "desc", "body", read_only=True)
        self.assertIn('sandbox_mode = "read-only"\n', toml)
        self.assertLess(toml.index("description"), toml.index("sandbox_mode"))

    def test_omits_sandbox_by_default(self) -> None:
        toml = build_agent_toml("implementor", "desc", "body")
        self.assertNotIn("sandbox_mode", toml)

    def test_escapes_toml_strings(self) -> None:
        toml = build_agent_toml('we"ird', "line\nbreak", 'body "quoted"')
        self.assertIn('"we\\"ird"', toml)
        self.assertIn('"line\\nbreak"', toml)


class OpenCodeParityTestCase(unittest.TestCase):
    """Codex read-only sandbox must match tools opencode would deny (no edit/shell allow)."""

    def test_read_only_tools_grant_no_edit_or_shell_in_opencode(self) -> None:
        tools = ["Read", "Grep", "Glob", "WebFetch", "WebSearch"]
        self.assertTrue(is_read_only(tools))
        allowed = {r["action"] for r in convert_tools_to_permissions(tools) if r["effect"] == "allow"}
        self.assertFalse(allowed & {"edit", "shell"})

    def test_write_tools_grant_edit_or_shell_in_opencode(self) -> None:
        for tool, action in (("Write", "edit"), ("Edit", "edit"), ("Bash(git diff:*)", "shell")):
            tools = ["Read", tool]
            self.assertFalse(is_read_only(tools))
            allowed = {r["action"] for r in convert_tools_to_permissions(tools) if r["effect"] == "allow"}
            self.assertIn(action, allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
