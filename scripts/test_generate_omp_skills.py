#!/usr/bin/env python3
"""Golden tests for scripts/generate_omp_skills.py."""

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_omp_skills as omp  # noqa: E402
from generate_codex_common import VERBATIM_SKILL_FILES, parse_frontmatter  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixture agents: file stem -> frontmatter name, as load_agent_aliases returns them.
ALIASES = {
    "implementor": "implementor",
    "code-researcher": "codebase-research-analyst",
    "codebase-research-analyst": "codebase-research-analyst",
    "releaser": "releaser",
}

DEMO_SKILL = """\
---
name: demo
description: Demo skill.
argument-hint: '[--flag]'
allowed-tools:
  - Read
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/demo/scripts/*.sh:*)'
disable-model-invocation: true
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/guide.md` first.
Then read `${CLAUDE_PLUGIN_ROOT}/skills/releaser/references/notes.md#cut`.
Run `${CLAUDE_PLUGIN_ROOT}/skills/demo/scripts/run.sh --x`.
Pattern `${CLAUDE_PLUGIN_ROOT}/skills/demo/scripts/<name>.sh` stays a pattern.
See [guide](../_shared/references/guide.md) and [deep](../../_shared/references/guide.md#top).
Run /ycc:releaser to cut, or ycc:demo for the demo.
Delegate to the `ycc:releaser` agent; dispatch `subagent_type: "ycc:code-researcher"`.
Use `subagent_type=ycc:implementor` and ycc:implementor directly.
Ask with `AskUserQuestion`, track with `TaskCreate`, `TaskUpdate`, and `TaskList`.
Use the Agent tool for one agent, or a single message with multiple `Agent` calls.
Search with WebSearch, then WebFetch.

<!-- ycc:verbatim-block:begin -->
Keep /ycc:releaser and ${CLAUDE_PLUGIN_ROOT}/skills/nowhere here.
<!-- ycc:verbatim-block:end -->
"""

RUN_SH = """\
#!/usr/bin/env bash
# Rules: ${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/guide.md#rules
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
LIB="${SCRIPT_DIR}/../../_shared/scripts/lib.sh"
[[ -f "$LIB" ]] || LIB="${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/lib.sh"
echo 'run /ycc:releaser next'
"""

VERBATIM_TEXT = "Matrix: `${CLAUDE_PLUGIN_ROOT}` and `/ycc:<name>` stay literal.\n"


def write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def build_fixture(root: Path) -> Path:
    src = root / "skills"
    write(src / "demo/SKILL.md", DEMO_SKILL)
    write(src / "demo/scripts/run.sh", RUN_SH, 0o755)
    write(src / "releaser/SKILL.md", "---\nname: releaser\ndescription: Releaser.\n---\n\nBody.\n")
    write(src / "releaser/references/notes.md", "Notes.\n")
    write(src / "_shared/references/guide.md", "Guide.\n")
    write(src / "_shared/references/agent-team-dispatch.md", "Long team contract with TeamCreate.\n")
    write(src / "_shared/references/target-capability-matrix.md", VERBATIM_TEXT)
    write(src / "_shared/scripts/lib.sh", "#!/usr/bin/env bash\n", 0o755)
    write(
        src / "bundle-author/references/surface-map.md",
        "Author helpers as `${CLAUDE_PLUGIN_ROOT}/skills/<kebab-name>/scripts/<name>.sh`.\n",
    )
    write(src / "bundle-author/SKILL.md", "---\nname: bundle-author\ndescription: Author.\n---\n\nBody.\n")
    return src


class FixtureTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.src = build_fixture(self.root)
        self.dest = self.root / "out"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def generate(self) -> set[Path]:
        return omp.write_tree(self.dest, dry_run=False, src_root=self.src, aliases=ALIASES)

    def read(self, rel: str) -> str:
        return (self.dest / rel).read_text(encoding="utf-8")

    def assert_fails(self, rel: str, text: str, *needles: str) -> None:
        write(self.src / rel, text)
        with self.assertRaises(omp.OmpGenerationError) as caught:
            self.generate()
        for needle in (rel, *needles):
            self.assertIn(needle, str(caught.exception))


class PathRewriteTest(FixtureTestCase):
    def test_shared_sibling_and_relative_links(self) -> None:
        self.generate()
        body = self.read("demo/SKILL.md")
        self.assertIn("Read `skill://ycc-shared/references/guide.md` first.", body)
        self.assertIn("`skill://releaser/references/notes.md#cut`", body)
        self.assertIn("`skill://demo/scripts/run.sh --x`", body)
        self.assertIn("`skill://demo/scripts/<name>.sh` stays a pattern", body)
        self.assertIn(
            "[guide](skill://ycc-shared/references/guide.md) and [deep](skill://ycc-shared/references/guide.md#top)",
            body,
        )

    def test_script_fallback_uses_relative_primary_and_comments_use_urls(self) -> None:
        self.generate()
        script = self.read("demo/scripts/run.sh")
        self.assertIn('[[ -f "$LIB" ]] || LIB="${SCRIPT_DIR}/../../_shared/scripts/lib.sh"', script)
        self.assertIn("# Rules: skill://ycc-shared/references/guide.md#rules", script)
        self.assertIn("echo 'run /skill:releaser next'", script)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", script)


class RepositoryLayoutTest(FixtureTestCase):
    def test_source_authoring_guidance_keeps_plugin_root(self) -> None:
        self.generate()
        self.assertIn("bundle-author/references/surface-map.md", omp.REPOSITORY_LAYOUT_FILES)
        self.assertEqual(
            self.read("bundle-author/references/surface-map.md"),
            "Author helpers as `${CLAUDE_PLUGIN_ROOT}/skills/<kebab-name>/scripts/<name>.sh`.\n",
        )

    def test_real_source_authoring_files_keep_plugin_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            omp.write_tree(dest, dry_run=False)
            for rel in sorted(omp.REPOSITORY_LAYOUT_FILES):
                with self.subTest(rel=rel):
                    text = (dest / rel).read_text(encoding="utf-8")
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/", text)
                    self.assertNotIn("skill://", text)


class PathSentenceTest(FixtureTestCase):
    def test_sentence_rewritten_in_listed_file(self) -> None:
        write(self.src / "demo/references/p.md", "Track via `TaskList` (Path B).\n")
        sentences = {"demo/references/p.md": (("via `TaskList` (Path B)", "via `todo` (Path B lists tasks)"),)}
        omp.write_tree(self.dest, dry_run=False, src_root=self.src, aliases=ALIASES, path_sentences=sentences)
        self.assertEqual(self.read("demo/references/p.md"), "Track via `todo` (Path B lists tasks).\n")

    def test_stale_sentence_fails(self) -> None:
        write(self.src / "demo/references/p.md", "Reworded source.\n")
        sentences = {"demo/references/p.md": (("via `TaskList` (Path B)", "x"),)}
        with self.assertRaisesRegex(omp.OmpGenerationError, r"demo/references/p\.md: PATH_TOOL_SENTENCES"):
            omp.write_tree(self.dest, dry_run=False, src_root=self.src, aliases=ALIASES, path_sentences=sentences)

    def test_missing_listed_file_fails(self) -> None:
        sentences = {"demo/references/gone.md": (("a", "b"),)}
        with self.assertRaisesRegex(omp.OmpGenerationError, r"demo/references/gone\.md: listed"):
            omp.write_tree(self.dest, dry_run=False, src_root=self.src, aliases=ALIASES, path_sentences=sentences)

    def test_real_sentences_all_match(self) -> None:
        for rel, entries in omp.PATH_TOOL_SENTENCES.items():
            text = (omp.SRC_DIR / rel).read_text(encoding="utf-8")
            for source, _ in entries:
                with self.subTest(rel=rel, source=source):
                    self.assertIn(source, text)


class NamespaceTest(FixtureTestCase):
    def test_managed_block_marker_takes_bare_name(self) -> None:
        write(self.src / "demo/scripts/m.sh", "# --- ycc:demo managed block (do not edit) ---\n")
        self.generate()
        self.assertEqual(self.read("demo/scripts/m.sh"), "# --- demo managed block (do not edit) ---\n")

    def test_unknown_managed_block_marker_fails(self) -> None:
        self.assert_fails("demo/scripts/m.sh", "# --- ycc:nope managed block ---\n", "ycc:nope")

    def test_skill_and_agent_mapping_including_overlap(self) -> None:
        self.generate()
        body = self.read("demo/SKILL.md")
        self.assertIn("Run /skill:releaser to cut, or /skill:demo for the demo.", body)
        # `releaser` is both a skill and an agent: agent context wins.
        self.assertIn("Delegate to the `releaser` agent", body)
        # Agent references resolve through frontmatter names, not file stems.
        self.assertIn('`subagent_type: "codebase-research-analyst"`', body)
        self.assertIn("`subagent_type=implementor` and implementor directly.", body)

    def test_protected_block_untouched_and_marker_stripped(self) -> None:
        self.generate()
        body = self.read("demo/SKILL.md")
        self.assertIn("Keep /ycc:releaser and ${CLAUDE_PLUGIN_ROOT}/skills/nowhere here.\n", body)
        self.assertNotIn("ycc:verbatim-block", body)

    def test_tool_wording(self) -> None:
        self.generate()
        body = self.read("demo/SKILL.md")
        self.assertIn("Ask with `ask`, track with `todo`.", body)
        self.assertIn("Use the `task` tool for one agent, or a single message with multiple `task` calls.", body)
        self.assertIn("Search with `web_search`, then `read` (URL).", body)

    def test_tool_wording_in_code_never_nests_backticks(self) -> None:
        source = (
            'Wire with `TaskUpdate(taskId="<id>", addBlockedBy=["<dep>"])`.\n'
            "Dispatch via `Agent` or `Agent(name=...)`.\n"
            "```text\n"
            'TaskCreate: subject="1.1", description="Agent: <type>"\n'
            'Agent(subagent_type="planner")\n'
            "```\n"
        )
        expected = (
            'Wire with `todo(taskId="<id>", addBlockedBy=["<dep>"])`.\n'
            "Dispatch via `task` or `task(name=...)`.\n"
            "```text\n"
            'todo: subject="1.1", description="Agent: <type>"\n'
            'task(subagent_type="planner")\n'
            "```\n"
        )
        self.assertEqual(omp.rewrite_tool_wording(source), expected)

    def test_task_tool_wording_in_fenced_code(self) -> None:
        source = "```\n[Single message with 3 Agent tool calls]\n```\n"
        self.assertEqual(omp.rewrite_tool_wording(source), "```\n[Single message with 3 task tool calls]\n```\n")

    def test_todo_lists_keep_their_conjunctions(self) -> None:
        cases = (
            (
                "If you lack `SendMessage`, `TaskUpdate`, or `TaskList`, ignore this.",
                "If you lack `SendMessage` or `todo`, ignore this.",
            ),
            ("Inspect with `TaskList` or `TaskGet`.", "Inspect with `todo`."),
            ("Strip the `SendMessage`/`TaskList`/`TaskUpdate` lines.", "Strip the `SendMessage`/`todo` lines."),
            ("Track with `TaskCreate`, `TaskGet`,\n`TaskList`, and `TaskUpdate`.", "Track with `todo`."),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(omp.rewrite_tool_wording(source), expected)

    def test_team_dispatch_becomes_unsupported_note(self) -> None:
        self.generate()
        note = self.read("_shared/references/agent-team-dispatch.md")
        self.assertIn("`--team`", note)
        self.assertIn("unsupported", note)
        self.assertNotIn("TeamCreate", note)


class TreeTest(FixtureTestCase):
    def test_executable_bit_preserved(self) -> None:
        self.generate()
        for rel in ("demo/scripts/run.sh", "_shared/scripts/lib.sh"):
            self.assertTrue((self.dest / rel).stat().st_mode & stat.S_IXUSR, rel)
        self.assertFalse((self.dest / "demo/SKILL.md").stat().st_mode & stat.S_IXUSR)

    def test_manual_only_kept_and_allowed_tools_dropped(self) -> None:
        self.generate()
        frontmatter, _ = parse_frontmatter(self.read("demo/SKILL.md"))
        self.assertEqual(list(frontmatter), ["name", "description", "argument-hint", "disable-model-invocation"])
        self.assertIs(frontmatter["disable-model-invocation"], True)
        self.assertNotIn("disable-model-invocation", parse_frontmatter(self.read("releaser/SKILL.md"))[0])

    def test_shared_stub_shape(self) -> None:
        written = self.generate()
        self.assertIn(Path("_shared/SKILL.md"), written)
        frontmatter, body = parse_frontmatter(self.read("_shared/SKILL.md"))
        self.assertEqual(frontmatter["name"], "ycc-shared")
        self.assertIs(frontmatter["hide"], True)
        self.assertIs(frontmatter["disable-model-invocation"], True)
        self.assertTrue(frontmatter["description"])
        self.assertIn("skill://ycc-shared/", body)

    def test_source_shared_stub_rejected(self) -> None:
        self.assert_fails("_shared/SKILL.md", "---\nname: x\ndescription: x\n---\n", "ycc-shared")

    def test_verbatim_files_copied_byte_for_byte(self) -> None:
        self.generate()
        self.assertEqual(self.read("_shared/references/target-capability-matrix.md"), VERBATIM_TEXT)

    def test_idempotent_check_and_prune(self) -> None:
        self.generate()
        before = {p: p.read_bytes() for p in self.dest.rglob("*") if p.is_file()}
        write(self.dest / "stale/old.md", "stale\n")
        self.generate()
        self.assertFalse((self.dest / "stale").exists())
        self.assertEqual({p: p.read_bytes() for p in self.dest.rglob("*") if p.is_file()}, before)

    def test_compare_trees_detects_content_and_mode_drift(self) -> None:
        self.generate()
        fresh = self.root / "fresh"
        omp.write_tree(fresh, dry_run=False, src_root=self.src, aliases=ALIASES)
        self.assertEqual(omp.compare_trees(fresh, self.dest), [])
        (self.dest / "demo/scripts/run.sh").chmod(0o644)
        self.assertEqual(omp.compare_trees(fresh, self.dest), ["mode drift: demo/scripts/run.sh"])
        (self.dest / "demo/scripts/run.sh").chmod(0o755)
        (self.dest / "releaser/SKILL.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(omp.compare_trees(fresh, self.dest), ["drift: releaser/SKILL.md"])


class MissingReferenceTest(FixtureTestCase):
    def test_unknown_slash_reference(self) -> None:
        self.assert_fails("demo/references/a.md", "Run /ycc:nope now.\n", "/ycc:nope")

    def test_unknown_bare_reference(self) -> None:
        self.assert_fails("demo/references/a.md", "Run ycc:nope now.\n", "ycc:nope")

    def test_unknown_subagent_reference(self) -> None:
        self.assert_fails("demo/references/a.md", '`subagent_type: "ycc:demo"`\n', "ycc:demo")

    def test_missing_plugin_path(self) -> None:
        ref = "${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/missing.md"
        self.assert_fails("demo/references/a.md", f"Read `{ref}`.\n", ref)

    def test_plugin_path_outside_skills(self) -> None:
        ref = "${CLAUDE_PLUGIN_ROOT}/skills/nowhere/x.md"
        self.assert_fails("demo/references/a.md", f"Read `{ref}`.\n", ref)

    def test_missing_relative_shared_link(self) -> None:
        self.assert_fails("demo/references/a.md", "[x](../../_shared/missing.md)\n", "_shared/missing.md")

    def test_unknown_agent_suffix_falls_back_to_skill_lookup(self) -> None:
        self.assert_fails("demo/references/a.md", "Ask the `ycc:nope` agent.\n", "ycc:nope")

    def test_script_fallback_without_script_dir_fails(self) -> None:
        ref = '"${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/lib.sh"'
        self.assert_fails("demo/scripts/b.sh", f"LIB={ref}\n", "SCRIPT_DIR")

    def test_missing_script_fallback_target(self) -> None:
        ref = "${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/missing.sh"
        script = f'SCRIPT_DIR="$(pwd)"\nLIB="{ref}"\n'
        self.assert_fails("demo/scripts/b.sh", script, ref)

    def test_residual_plugin_root_in_markdown(self) -> None:
        self.assert_fails("demo/references/a.md", "Root is `${CLAUDE_PLUGIN_ROOT}`.\n", "CLAUDE_PLUGIN_ROOT")

    def test_residual_plugin_root_in_script_code(self) -> None:
        self.assert_fails("demo/scripts/b.sh", 'cd "${CLAUDE_PLUGIN_ROOT}"\n', "CLAUDE_PLUGIN_ROOT")

    def test_non_boolean_model_invocation_flag(self) -> None:
        for value in ('"true"', "1", "null"):
            with self.subTest(value=value):
                skill = f"---\nname: demo\ndescription: d\ndisable-model-invocation: {value}\n---\n"
                write(self.src / "demo/SKILL.md", skill)
                with self.assertRaisesRegex(ValueError, "disable-model-invocation"):
                    self.generate()


class RealTreeTest(unittest.TestCase):
    def test_inventory_parity_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            written = omp.write_tree(dest, dry_run=False)
            source_files = {p.relative_to(omp.SRC_DIR) for p in omp.SRC_DIR.rglob("*") if p.is_file()}
            self.assertEqual(written, source_files | {omp.SHARED_STUB_REL})
            source_skills = {p.parent.name for p in omp.SRC_DIR.glob("*/SKILL.md")}
            generated = {p.parent.name for p in dest.glob("*/SKILL.md")}
            self.assertEqual(generated, source_skills | {"_shared"})
            for skill in sorted(source_skills):
                with self.subTest(skill=skill):
                    frontmatter, _ = parse_frontmatter((dest / skill / "SKILL.md").read_text(encoding="utf-8"))
                    self.assertEqual(frontmatter["name"], skill)
            names = [parse_frontmatter(p.read_text(encoding="utf-8"))[0]["name"] for p in dest.glob("*/SKILL.md")]
            self.assertEqual(len(names), len(set(names)))
            self.assertIn("ycc-shared", names)

    def test_manual_only_policy_matches_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            omp.write_tree(dest, dry_run=False)
            for source in sorted(omp.SRC_DIR.glob("*/SKILL.md")):
                with self.subTest(skill=source.parent.name):
                    src_fm, _ = parse_frontmatter(source.read_text(encoding="utf-8"))
                    out = dest / source.relative_to(omp.SRC_DIR)
                    out_fm, _ = parse_frontmatter(out.read_text(encoding="utf-8"))
                    self.assertEqual(
                        out_fm.get("disable-model-invocation", False), src_fm.get("disable-model-invocation", False)
                    )
                    self.assertNotIn("allowed-tools", out_fm)

    def test_verbatim_files_exist(self) -> None:
        for rel in VERBATIM_SKILL_FILES:
            self.assertTrue((omp.SRC_DIR / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()
