#!/usr/bin/env python3
"""Focused checks for Cursor rule generation and policy linting."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_cursor_rules as rules

SOURCE_RULE = (
    "---\ndescription: When editing Go files, apply idiomatic error wrapping.\n"
    "paths:\n  - '**/*.go'\n---\n# Go Coding Style\nWrap errors with context.\n"
)


def mdc(description: str, body: str, always: bool = False, scoped: bool = True) -> str:
    globs = "globs:\n- '**/*.go'\n" if scoped and not always else ""
    return f"---\ndescription: {description}\nalwaysApply: {str(always).lower()}\n{globs}---\n{body}"


class SourceGenerationTest(unittest.TestCase):
    def test_source_description_is_emitted_not_h1(self) -> None:
        out = rules.build_mdc(Path("golang/coding-style.md"), SOURCE_RULE)
        _, fm, _ = rules.parse_frontmatter(out)
        self.assertEqual(fm["description"], "When editing Go files, apply idiomatic error wrapping.")
        self.assertEqual(fm["globs"], ["**/*.go"])
        self.assertFalse(fm["alwaysApply"])

    def test_missing_description_fails(self) -> None:
        raw = SOURCE_RULE.replace("description: When editing Go files, apply idiomatic error wrapping.\n", "")
        with self.assertRaisesRegex(SystemExit, "non-empty description"):
            rules.build_mdc(Path("golang/coding-style.md"), raw)

    def test_description_equal_to_h1_fails(self) -> None:
        raw = SOURCE_RULE.replace("When editing Go files, apply idiomatic error wrapping.", "Go Coding Style")
        with self.assertRaisesRegex(SystemExit, "not repeat the H1"):
            rules.build_mdc(Path("golang/coding-style.md"), raw)

    def test_description_over_limit_fails(self) -> None:
        raw = SOURCE_RULE.replace("When editing Go files, apply idiomatic error wrapping.", "x" * 201)
        with self.assertRaisesRegex(SystemExit, "exceeds 200"):
            rules.build_mdc(Path("golang/coding-style.md"), raw)

    def test_scoped_rule_without_globs_fails(self) -> None:
        raw = "---\ndescription: When editing Go files, apply it.\n---\n# Title\nBody\n"
        with self.assertRaisesRegex(SystemExit, "need paths/globs"):
            rules.build_mdc(Path("golang/coding-style.md"), raw)

    def test_hooks_sources_are_not_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            (src / "golang").mkdir(parents=True)
            (src / "golang" / "coding-style.md").write_text(SOURCE_RULE, encoding="utf-8")
            (src / "golang" / "hooks.md").write_text("Configure in `~/.claude/settings.json`\n", encoding="utf-8")
            with patch.object(rules, "SRC_DIR", src), patch.object(rules, "REPO_ROOT", Path(tmp)):
                written = rules.write_tree(dest, dry_run=False)
            self.assertEqual(written, {Path("golang/coding-style.mdc")})
            self.assertEqual([p.name for p in dest.rglob("*") if p.is_file()], ["coding-style.mdc"])


class GeneratedLintTest(unittest.TestCase):
    def lint(self, files: dict[str, str]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dst = root / "rules"
            for name, text in files.items():
                path = dst / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            err = io.StringIO()
            with patch.object(rules, "DST_DIR", dst), patch.object(rules, "REPO_ROOT", root):
                with contextlib.redirect_stderr(err):
                    return rules.lint_generated_rules(), err.getvalue()

    def test_valid_tree_passes(self) -> None:
        errors, _ = self.lint(
            {
                "common/security.mdc": mdc("Before committing, check secrets.", "# Security\nCheck.\n", always=True),
                "golang/coding-style.mdc": mdc("When editing Go files, wrap errors.", "# Go Style\nWrap.\n"),
            }
        )
        self.assertEqual(errors, 0)

    def test_always_apply_count_over_two_fails(self) -> None:
        files = {
            f"common/r{i}.mdc": mdc(f"When working, apply rule {i}.", f"# R{i}\nBody\n", always=True) for i in range(3)
        }
        errors, err = self.lint(files)
        self.assertGreater(errors, 0)
        self.assertIn("TOO MANY alwaysApply rules: 3 > 2", err)

    def test_always_apply_body_budget_fails(self) -> None:
        body = "# Big\n" + "line\n" * 60
        errors, err = self.lint({"common/big.mdc": mdc("Before commit, apply big rule.", body, always=True)})
        self.assertGreater(errors, 0)
        self.assertIn("alwaysApply body too large", err)

    def test_description_equal_to_h1_fails(self) -> None:
        errors, err = self.lint({"golang/style.mdc": mdc("Go Style", "# Go Style\nBody\n")})
        self.assertGreater(errors, 0)
        self.assertIn("BAD description", err)

    def test_claude_settings_path_fails(self) -> None:
        errors, err = self.lint(
            {"golang/style.mdc": mdc("When editing Go, apply style.", "# Style\nSee ~/.claude/settings.json\n")}
        )
        self.assertGreater(errors, 0)
        self.assertIn("CLAUDE-ONLY content", err)

    def test_task_execution_fails(self) -> None:
        errors, err = self.lint(
            {"golang/style.mdc": mdc("When editing Go, apply style.", "# Style\nUse parallel Task execution.\n")}
        )
        self.assertGreater(errors, 0)
        self.assertIn("CLAUDE-ONLY content", err)

    def test_emitted_hooks_rule_fails(self) -> None:
        errors, err = self.lint({"golang/hooks.mdc": mdc("When editing Go, configure hooks.", "# Hooks\nBody\n")})
        self.assertGreater(errors, 0)
        self.assertIn("hooks rule emitted", err)


if __name__ == "__main__":
    unittest.main()
