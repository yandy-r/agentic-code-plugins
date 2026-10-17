#!/usr/bin/env python3
"""Regression test: standalone agents must not reach into skill/shared source files.

Standalone agent installs (Claude ~/.claude/agents, Cursor, Codex, opencode
file-copy, the opencode npm package) ship the agent bodies without the plugin's
``ycc/skills`` or ``_shared`` trees. An agent body that names those paths, or
defers to "the skill's ``references/...``", points at files the runtime cannot
resolve. Guidance must be prompt-owned or self-contained in the agent body.

Scans the checked-in agent source and every generated agent surface; it never
regenerates anything.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each surface is (label, glob relative to the repo root). Every surface must
# match at least one file so a moved directory cannot silently pass.
SURFACES: tuple[tuple[str, str], ...] = (
    ("source", "ycc/agents/*.md"),
    ("codex", ".codex-plugin/agents/*.toml"),
    ("opencode", ".opencode-plugin/agents/*.md"),
    ("cursor", "packages/cursor/ycc/agents/*.md"),
    ("opencode-npm", "packages/opencode/ycc-opencode/agents/*.md"),
)

REACH_IN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ycc/skills/"),
    re.compile(r"_shared/"),
    re.compile(r"\.opencode-plugin/(?:skills|shared)/"),
    re.compile(r"\{\{package-root\}\}/(?:skills|shared)/"),
    re.compile(r"CLAUDE_PLUGIN_ROOT"),
    re.compile(r"worktree-strategy\.md"),
    # Prose deferrals: "the skill's `references/...`", "the shared `x.md` reference"
    # (including when wrapped across lines or escaped inside a TOML string).
    re.compile(r"skill's(?:\s|\\n)+`references/"),
    re.compile(r"shared(?:\s|\\n)+`[\w.-]+\.md`(?:\s|\\n)+reference"),
)


def find_reach_ins(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, matched_text)`` for every reach-in in ``text``."""
    hits: list[tuple[int, str]] = []
    for pattern in REACH_IN_PATTERNS:
        for match in pattern.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            hits.append((lineno, " ".join(match.group(0).split())))
    return sorted(hits)


def scan_surface(glob: str) -> tuple[list[Path], list[str]]:
    """Return the files matched by ``glob`` and their ``path:line: match`` offenders."""
    files = sorted(REPO_ROOT.glob(glob))
    offenders: list[str] = []
    for path in files:
        rel = path.relative_to(REPO_ROOT)
        for lineno, matched in find_reach_ins(path.read_text(encoding="utf-8")):
            offenders.append(f"{rel}:{lineno}: {matched}")
    return files, offenders


class StandaloneAgentReferenceTests(unittest.TestCase):
    def test_agent_surfaces_have_no_source_reach_ins(self) -> None:
        for label, glob in SURFACES:
            with self.subTest(surface=label):
                files, offenders = scan_surface(glob)
                self.assertTrue(files, f"no agent files matched {glob}")
                self.assertEqual(
                    offenders,
                    [],
                    "standalone agents must not reference skill/shared source files:\n" + "\n".join(offenders),
                )

    def test_matcher_flags_synthetic_reach_ins(self) -> None:
        samples = (
            "see `ycc/skills/demo/references/x.md`",
            "from `_shared/scripts/lib/x.sh`",
            "see .opencode-plugin/skills/demo/SKILL.md",
            "see {{package-root}}/shared/references/x.md",
            "${CLAUDE_PLUGIN_ROOT}/skills/demo",
            "rules in the demo skill's `references/rules.md`",
            "per the bundle's shared `branching-model.md` reference",
            "per the bundle's shared\n`branching-model.md` reference",
            "open `worktree-strategy.md` first",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(len(find_reach_ins(f"intro\n{sample}\n")), 1)
                self.assertEqual(find_reach_ins(f"intro\n{sample}\n")[0][0], 2)

    def test_matcher_ignores_project_paths(self) -> None:
        self.assertEqual(find_reach_ins("write to `docs/plans/x.md` and `docs/prps/reviews/y.md`\n"), [])


if __name__ == "__main__":
    unittest.main()
