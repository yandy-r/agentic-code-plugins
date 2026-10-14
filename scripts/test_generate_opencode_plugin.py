#!/usr/bin/env python3
"""Tests for the opencode rules copy and its shared rules validator."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from generate_opencode_plugin import build_agents_md
from validate_global_rules import RULES_LINE_CAP, rules_errors

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SOURCE_RULES = REPO_ROOT / "ycc" / "settings" / "rules" / "CLAUDE.md"
GENERATED_RULES = REPO_ROOT / ".opencode-plugin" / "AGENTS.md"


class ShippedRulesTestCase(unittest.TestCase):
    def test_source_and_generated_rules_are_clean(self) -> None:
        for text in (SOURCE_RULES.read_text(encoding="utf-8"), build_agents_md()):
            self.assertEqual(rules_errors(text), [])
            self.assertLessEqual(len(text.splitlines()), RULES_LINE_CAP)

    def test_committed_generated_rules_match_generator(self) -> None:
        self.assertEqual(GENERATED_RULES.read_text(encoding="utf-8"), build_agents_md())

    def test_agents_source_is_a_symlink_to_claude_source(self) -> None:
        agents = SOURCE_RULES.with_name("AGENTS.md")
        self.assertTrue(agents.is_symlink())
        self.assertEqual(agents.readlink(), Path("CLAUDE.md"))


class ValidatorFailureTestCase(unittest.TestCase):
    def test_rejects_empty_rules(self) -> None:
        self.assertIn("rules file is empty", rules_errors("  \n"))

    def test_rejects_over_budget(self) -> None:
        errors = rules_errors("rule\n" * (RULES_LINE_CAP + 1))
        self.assertIn(f"rules file exceeds {RULES_LINE_CAP} lines", errors)

    def test_rejects_duplicated_filename_pair(self) -> None:
        errors = rules_errors("Project `AGENTS.md` / `AGENTS.md` overrides these.\n")
        self.assertIn("duplicated AGENTS.md filename pair", errors)

    def test_rejects_duplicated_filename_pair_across_spacing(self) -> None:
        self.assertIn("duplicated AGENTS.md filename pair", rules_errors("`AGENTS.md`/`AGENTS.md`\n"))

    def test_rejects_graphify(self) -> None:
        self.assertIn("personal graphify rules must not be shipped", rules_errors("# graphify\n"))

    def test_rejects_repeated_runtime_name_in_one_list(self) -> None:
        errors = rules_errors("Shared by runtimes (opencode, Cursor, Codex, opencode).\n")
        self.assertIn("repeated runtime name in one list", errors)

    def test_distinct_runtime_names_in_one_list_pass(self) -> None:
        self.assertEqual(rules_errors("Runtimes (Claude Code, Cursor, Codex, opencode).\n"), [])

    def test_rejects_repeated_runtime_name_without_parentheses(self) -> None:
        errors = rules_errors("Shared by opencode, Cursor,\nCodex, and opencode across runtimes.\n")
        self.assertIn("repeated runtime name in one list", errors)


class ValidatorCliTestCase(unittest.TestCase):
    def run_cli(self, *paths: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "validate_global_rules.py"), *map(str, paths)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_passes_for_shipped_rules(self) -> None:
        result = self.run_cli(SOURCE_RULES, GENERATED_RULES)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_fails_for_missing_file(self) -> None:
        result = self.run_cli(REPO_ROOT / "does-not-exist.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("required rules file missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
