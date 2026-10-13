#!/usr/bin/env python3
"""Focused checks for skill-derived OpenCode commands."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_opencode_commands as commands
from generate_opencode_common import parse_frontmatter


class SkillCommandsTest(unittest.TestCase):
    def test_discovery_and_pruning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, dest = root / "skills", root / "commands"
            for name, metadata in (
                ("public", ""),
                ("model-hidden", "disable-model-invocation: true\n"),
                ("hidden", "user-invocable: false\n"),
                ("_private", ""),
            ):
                path = source / name / "SKILL.md"
                path.parent.mkdir(parents=True)
                path.write_text(f"---\nname: {name}\n{metadata}description: Example\n---\nStale body", encoding="utf-8")
            (source / "incomplete").mkdir()
            self.assertEqual([p.parent.name for p in commands.discover_skills(source)], ["model-hidden", "public"])
            dest.mkdir()
            (dest / "orphan.md").write_text("old", encoding="utf-8")
            with patch.object(commands, "SRC_SKILLS_DIR", source):
                commands.write_all(dest, dry_run=False)
            self.assertEqual(sorted(p.name for p in dest.iterdir()), ["model-hidden.md", "public.md"])

    def test_thin_dispatch_and_frontmatter(self) -> None:
        raw = "---\ndescription: Example\nargument-hint: '[path] [--dry-run]'\nmodel: fast\n---\nDo not copy me\n"
        rendered = commands.transform_command("example", raw, {}, {"fast": "provider/model"})
        frontmatter, body = parse_frontmatter(rendered)
        self.assertEqual(frontmatter["description"], "Example Usage: [path] [--dry-run]")
        self.assertEqual(frontmatter["model"], "provider/model")
        self.assertIn("skill tool to load the `example` skill", body)
        self.assertIn("$ARGUMENTS", body)
        self.assertNotIn("/example", body)
        self.assertNotIn("Do not copy me", body)

    def test_absent_hint_has_no_usage(self) -> None:
        for hint in ("", "argument-hint: null\n"):
            raw = f"---\ndescription: Example\n{hint}---\n"
            rendered = commands.transform_command("example", raw, {}, {})
            self.assertNotIn("Usage:", rendered)


if __name__ == "__main__":
    unittest.main()
