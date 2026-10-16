#!/usr/bin/env python3
"""Critical tests for relocatable native Codex skill resources."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_codex_skills as skills  # noqa: E402
from generate_codex_common import (  # noqa: E402
    PLUGIN_ROOT,
    SRC_SKILLS_DIR,
    VERBATIM_SKILL_FILES,
    parse_frontmatter,
)


class NativeResourceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.written = skills.write_tree(cls.root, False, native_paths=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_native_output_has_no_installer_dependency_and_preserves_verbatim_files(self) -> None:
        verbatim_outputs = {
            skills.plugin_output_path(Path(rel)).relative_to(PLUGIN_ROOT): rel for rel in VERBATIM_SKILL_FILES
        }
        for rel in sorted(self.written):
            with self.subTest(path=rel):
                output = (self.root / rel).read_bytes()
                if rel in verbatim_outputs:
                    self.assertEqual(output, (SRC_SKILLS_DIR / verbatim_outputs[rel]).read_bytes())
                else:
                    self.assertNotIn(b"~/.codex/plugins/ycc", output)
                    # A scaffold payload intentionally names the future authored skill.
                    logical = b"${CLAUDE_PLUGIN_ROOT}/skills/{{NAME}}/scripts/<name>.sh"
                    self.assertNotIn(b"CLAUDE_PLUGIN_ROOT", output.replace(logical, b""))
                if rel.name == "SKILL.md":
                    _, body = parse_frontmatter(output.decode())
                    instruction = body.lstrip().split("\n\n", 1)[0]
                    self.assertIn("this SKILL.md's directory", instruction)
                    self.assertIn("absolute path", instruction)
                    self.assertIn("project as cwd", instruction)

    def test_rewritten_bundled_resources_resolve_inside_emitted_tree(self) -> None:
        checked = 0
        seen_contexts: set[str] = set()
        for rel in sorted(self.written):
            legacy = PLUGIN_ROOT / rel
            if not legacy.is_file() or not skills.should_transform_text(legacy):
                continue
            if rel.as_posix() == "shared/references/target-capability-matrix.md":
                continue
            content = (self.root / rel).read_text(encoding="utf-8")
            refs = re.findall(r"~/\.codex/plugins/ycc/([a-zA-Z0-9_./{},#-]+)", legacy.read_text())
            for reference in refs:
                if "{{" in reference:
                    continue
                reference = reference.split("#", 1)[0].rstrip(".,")
                if not reference:
                    continue
                # Expand the authored compact list notation, not arbitrary template payloads.
                brace = re.search(r"\{([^{}]+)\}", reference)
                targets = [reference]
                if brace:
                    targets = [
                        reference[: brace.start()] + name + reference[brace.end() :]
                        for name in brace.group(1).split(",")
                    ]
                with self.subTest(document=rel, reference=reference):
                    if rel.as_posix() in skills.NATIVE_PROMPT_FILES:
                        emitted = skills.NATIVE_PLUGIN_PLACEHOLDER + "/" + reference
                    else:
                        emitted = Path(os.path.relpath(reference, rel.parent)).as_posix()
                    self.assertIn(emitted, content)
                    for target in targets:
                        relative = os.path.relpath(target, rel.parent)
                        resolved = (self.root / rel.parent / relative).resolve()
                        self.assertTrue(resolved.is_relative_to(self.root))
                        self.assertTrue(resolved.exists(), str(resolved))
                    checked += 1
                    seen_contexts.add("shared" if rel.parts[0] == "shared" else rel.parent.name)
        self.assertGreater(checked, 200)
        self.assertTrue({"shared", "references", "scripts", "git-workflow"} <= seen_contexts)

    def test_executable_script_directory_references_have_a_definition(self) -> None:
        checked = 0
        for rel in sorted(self.written):
            if rel.suffix not in {".sh", ".bash"}:
                continue
            defined = False
            for number, line in enumerate((self.root / rel).read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.match(r"^\s*(?:local\s+)?SCRIPT_DIR=", line):
                    defined = True
                if "${SCRIPT_DIR}/" in line:
                    with self.subTest(script=rel, line=number):
                        self.assertTrue(defined)
                        checked += 1
        self.assertGreater(checked, 20)

    def test_forwarded_prompts_require_absolute_substitution(self) -> None:
        for rel in skills.NATIVE_PROMPT_FILES:
            content = (self.root / rel).read_text()
            self.assertIn("Before forwarding any prompt", content)
            references = re.findall(r"<installed ycc plugin root>/([\w./-]+)", content)
            self.assertTrue(references)
            for reference in references:
                self.assertTrue((self.root / reference).is_file())
        for rel in ("skills/git-workflow/SKILL.md", "skills/git-workflow/references/commit-phases.md"):
            self.assertIn("Before Step 14 dispatch, expand every", (self.root / rel).read_text())
        payload = self.root / "skills/bundle-author/references/templates/skill-template.md"
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/{{NAME}}/scripts/<name>.sh", payload.read_text())

    def test_frontmatter_and_legacy_home_references_are_relative_but_user_home_is_not(self) -> None:
        raw = (
            "---\nname: sample\ndescription: 'Read ${CLAUDE_PLUGIN_ROOT}/skills/_shared/"
            "references/branching-model.md'\n---\n"
            "Read ~/.codex/plugins/ycc/shared/references/branching-model.md and "
            "~/.codex/skills/git-workflow/SKILL.md. Keep ~/.codex/settings.json, "
            "~/.codex/session-data/ and ~/.codex/skills/not-a-bundled-skill/SKILL.md.\n"
        )
        rendered = skills.transform_skill_markdown(
            raw, {}, native_paths=True, output_path=Path("skills/sample/SKILL.md")
        )
        frontmatter, body = parse_frontmatter(rendered)
        self.assertIn("../../shared/references/branching-model.md", frontmatter["description"])
        self.assertIn("../../shared/references/branching-model.md", body)
        self.assertIn("../git-workflow/SKILL.md", body)
        self.assertIn("~/.codex/settings.json", body)
        self.assertIn("~/.codex/session-data/", body)
        self.assertIn("~/.codex/skills/not-a-bundled-skill/SKILL.md", body)

    def test_bundle_release_still_names_authored_metadata(self) -> None:
        content = (self.root / "skills/bundle-release/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ycc/.claude-plugin/plugin.json", content)
        self.assertNotIn("ycc/.codex-plugin/plugin.json", content)


class LegacyCompatibilityTestCase(unittest.TestCase):
    def test_default_and_explicit_legacy_trees_match_checked_in_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            default = Path(tmp) / "default"
            explicit = Path(tmp) / "explicit"
            written = skills.write_tree(default, False)
            self.assertEqual(written, skills.write_tree(explicit, False, native_paths=False))
            self.assertEqual(skills.compare_trees(default, PLUGIN_ROOT, written), [])
            for rel in sorted(written):
                with self.subTest(path=rel):
                    self.assertEqual((default / rel).read_bytes(), (explicit / rel).read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
