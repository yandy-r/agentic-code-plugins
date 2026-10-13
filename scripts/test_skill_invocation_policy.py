#!/usr/bin/env python3
"""Focused tests for skill disable-model-invocation target propagation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_agents_common
import generate_agents_skills
import generate_codex_skills
import generate_cursor_skills
from generate_agents_common import transform_skill_markdown as agents_transform
from generate_codex_common import model_invocation_disabled, parse_frontmatter
from generate_opencode_skills import transform_skill_markdown as opencode_transform


def skill(raw: str, name: str = "example") -> str:
    return f"---\nname: {name}\ndescription: Example\n{raw}---\nBody\n"


def write_source(root: Path, marker: str = "disable-model-invocation: true\n") -> Path:
    source = root / "src/skills"
    path = source / "example/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(skill(marker), encoding="utf-8")
    return source


class StrictTypesTest(unittest.TestCase):
    def test_true_false_and_omitted(self) -> None:
        self.assertTrue(model_invocation_disabled({"disable-model-invocation": True}, "x"))
        self.assertFalse(model_invocation_disabled({"disable-model-invocation": False}, "x"))
        self.assertFalse(model_invocation_disabled({}, "x"))

    def test_rejects_non_booleans(self) -> None:
        for value in ("true", 1, 0, None, [], {}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "disable-model-invocation"):
                    model_invocation_disabled({"disable-model-invocation": value}, "x")


class CodexTest(unittest.TestCase):
    def generate(self, tmp: Path, marker: str = "disable-model-invocation: true\n") -> tuple[Path, Path, set[Path]]:
        source = write_source(tmp, marker)
        dest = tmp / "dest"
        with patch.object(generate_codex_skills, "SRC_SKILLS_DIR", source):
            written = generate_codex_skills.write_tree(dest, dry_run=False)
        return source, dest, written

    def test_writes_native_boolean_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, dest, written = self.generate(Path(raw))
            sidecar = Path("skills/example/agents/openai.yaml")
            self.assertIn(sidecar, written)
            expected = "policy:\n  allow_implicit_invocation: false\n"
            self.assertEqual((dest / sidecar).read_text(encoding="utf-8"), expected)

    def test_omitted_flag_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source, dest, written = self.generate(Path(raw), "")
            sidecar = dest / "skills/example/agents/openai.yaml"
            self.assertFalse(sidecar.exists())
            first = {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()}
            with patch.object(generate_codex_skills, "SRC_SKILLS_DIR", source):
                generate_codex_skills.write_tree(dest, dry_run=False)
            self.assertEqual(first, {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()})
            self.assertFalse(sidecar.exists())

    def test_flip_prunes_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source, dest, _ = self.generate(tmp)
            sidecar = dest / "skills/example/agents/openai.yaml"
            self.assertTrue(sidecar.exists())
            (source / "example/SKILL.md").write_text(skill(""), encoding="utf-8")
            with patch.object(generate_codex_skills, "SRC_SKILLS_DIR", source):
                generate_codex_skills.write_tree(dest, dry_run=False)
            self.assertFalse(sidecar.exists())
            self.assertFalse((dest / "skills/example/agents").exists())

    def test_extra_file_stale_check(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source, dest, written = self.generate(tmp, "")
            stale = dest / "skills/example/agents/openai.yaml"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale\n", encoding="utf-8")
            diffs = generate_codex_skills.compare_trees(dest, dest, written)
            self.assertIn("extra in repo: skills/example/agents/openai.yaml", diffs)

    def test_authored_sidecar_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = write_source(tmp)
            authored = source / "example/agents/openai.yaml"
            authored.parent.mkdir()
            authored.write_text("policy: {}\n", encoding="utf-8")
            with patch.object(generate_codex_skills, "SRC_SKILLS_DIR", source):
                with self.assertRaisesRegex(ValueError, r"authored agents/openai\.yaml"):
                    generate_codex_skills.write_tree(tmp / "dest", dry_run=False)


class OpenCodeTest(unittest.TestCase):
    def test_inserts_native_string_metadata(self) -> None:
        transformed = opencode_transform(skill("metadata:\n  custom: keep\ndisable-model-invocation: true\n"), {})
        self.assertIn("custom: keep", transformed)
        self.assertIn("opencode/autoinvoke: 'false'", transformed)
        self.assertEqual(transformed.count("opencode/autoinvoke"), 1)

    def test_omitted_flag_keeps_metadata_unrestricted(self) -> None:
        transformed = opencode_transform(skill("metadata:\n  custom: keep\n"), {})
        self.assertIn("custom: keep", transformed)
        self.assertNotIn("opencode/autoinvoke", transformed)

    def test_conflict_and_nonmapping_fail(self) -> None:
        for marker in ("metadata:\n  opencode/autoinvoke: always\n", "metadata: nope\n"):
            with self.subTest(marker=marker):
                with self.assertRaises(ValueError):
                    opencode_transform(skill(marker + "disable-model-invocation: true\n"), {})


class RealTypesTest(unittest.TestCase):
    def test_boolean_is_yaml_bool(self) -> None:
        path = Path(__file__).resolve().parent.parent / "ycc/skills/releaser/SKILL.md"
        frontmatter, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertIs(frontmatter["disable-model-invocation"], True)

    def test_quoted_boolean_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "disable-model-invocation"):
            model_invocation_disabled({"disable-model-invocation": "false"}, "x")


class CursorTest(unittest.TestCase):
    def test_retain_flag(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = write_source(tmp)
            dest = tmp / "dest"
            with patch.object(generate_cursor_skills, "SRC_DIR", source):
                generate_cursor_skills.write_tree(dest, dry_run=False)
            self.assertIn("disable-model-invocation: true", (dest / "example/SKILL.md").read_text(encoding="utf-8"))


INVALID_MARKERS = (
    'disable-model-invocation: "true"\n',
    'disable-model-invocation: "false"\n',
    "disable-model-invocation: 1\n",
    "disable-model-invocation: null\n",
    "disable-model-invocation: []\n",
)


class StrictPathsTest(unittest.TestCase):
    def test_cursor_rejects_invalid_and_passes_valid(self) -> None:
        for marker in INVALID_MARKERS:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                source = write_source(tmp, marker)
                with patch.object(generate_cursor_skills, "SRC_DIR", source):
                    with self.assertRaisesRegex(ValueError, "disable-model-invocation"):
                        generate_cursor_skills.write_tree(tmp / "dest", dry_run=False)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = write_source(tmp, "disable-model-invocation: false\n")
            with patch.object(generate_cursor_skills, "SRC_DIR", source):
                generate_cursor_skills.write_tree(tmp / "dest", dry_run=False)
            self.assertIn(
                "disable-model-invocation: false",
                (tmp / "dest/example/SKILL.md").read_text(encoding="utf-8"),
            )

    def test_agents_rejects_invalid_and_omits_valid(self) -> None:
        for marker in INVALID_MARKERS:
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(ValueError, "disable-model-invocation"):
                    agents_transform(skill(marker), {})
        for marker in ("disable-model-invocation: false\n", ""):
            with self.subTest(marker=marker):
                self.assertNotIn("disable-model-invocation", agents_transform(skill(marker), {}))


class AgentsTest(unittest.TestCase):
    def test_omit_flag_and_keep_description(self) -> None:
        transformed = agents_transform(skill("disable-model-invocation: true\n"), {})
        self.assertIn("description: Example", transformed)
        self.assertNotIn("disable-model-invocation", transformed)

    def test_full_tree_omits_flag(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = write_source(tmp)
            dest = tmp / "dest"
            with (
                patch.object(generate_agents_skills, "SRC_SKILLS_DIR", source),
                patch.object(generate_agents_common, "SRC_SKILLS_DIR", source),
            ):
                generate_agents_skills.write_tree(dest, dry_run=False)
            generated = (dest / "skills/example/SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("disable-model-invocation", generated)


if __name__ == "__main__":
    unittest.main()
