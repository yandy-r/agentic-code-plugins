#!/usr/bin/env python3
"""Critical checks for the OMP rules flattener (R1-R6)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import generate_omp_rules as rules
import yaml

EXPECTED_NAMES = sorted(
    [
        "ycc-common-agents.md",
        "ycc-common-code-review.md",
        "ycc-common-coding-style.md",
        "ycc-common-development-workflow.md",
        "ycc-common-git-workflow.md",
        "ycc-common-patterns.md",
        "ycc-common-performance.md",
        "ycc-common-security.md",
        "ycc-common-testing.md",
        *(
            f"ycc-{lang}-{stem}.md"
            for lang in ("golang", "python", "rust", "typescript")
            for stem in ("coding-style", "patterns", "security", "testing", "trigger")
        ),
        "ycc-web-coding-style.md",
        "ycc-web-design-quality.md",
        "ycc-web-patterns.md",
        "ycc-web-performance.md",
        "ycc-web-security.md",
        "ycc-web-testing.md",
        "ycc-web-trigger.md",
    ]
)


def rule(
    description: str = "Use when editing these files; apply the guidance.",
    body: str = "# Title\nBody.\n",
    **keys: object,
) -> str:
    data: dict[str, object] = {"description": description, **keys}
    return f"---\n{yaml.safe_dump(data, sort_keys=False)}---\n{body}"


def frontmatter(text: str) -> tuple[list[str], dict[str, object]]:
    end = text.index("\n---\n", 4)
    raw = text[4:end]
    keys = [line.split(":", 1)[0] for line in raw.splitlines() if line and not line.startswith(("-", " "))]
    return keys, yaml.safe_load(raw)


class FixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.src = Path(self._tmp.name) / "ycc/rules"

    def put(self, rel: str, text: str) -> None:
        path = self.src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class RealTreeTest(unittest.TestCase):
    def test_r1_real_tree_yields_31_flat_rules_and_5_triggers(self) -> None:
        built = rules.build_rules()
        self.assertEqual(sorted(built), EXPECTED_NAMES)
        self.assertEqual(len(built), 36)

    def test_r1_write_tree_emits_only_flat_rules_and_prunes_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "ycc-common-hooks.md").write_text("stale", encoding="utf-8")
            rules.write_tree(dest)
            self.assertEqual(sorted(p.name for p in dest.iterdir()), EXPECTED_NAMES)
            self.assertEqual(rules.check_tree(dest), [])


class TransformTest(FixtureTest):
    def test_r2_frontmatter_mapping_and_key_order(self) -> None:
        self.put("golang/coding-style.md", rule(paths=["**/*.go", "**/go.mod"]))
        self.put("common/coding-style.md", rule(alwaysApply=False))
        self.put("common/security.md", rule(alwaysApply=True, paths=["**/*"]))
        self.put("common/testing.md", rule(alwaysApply="true"))
        built = rules.build_rules(self.src)

        keys, data = frontmatter(built["ycc-golang-coding-style.md"])
        self.assertEqual(keys, ["description", "globs"])
        self.assertEqual(data["globs"], ["**/*.go", "**/go.mod"])

        keys, _ = frontmatter(built["ycc-common-coding-style.md"])
        self.assertEqual(keys, ["description"])

        keys, data = frontmatter(built["ycc-common-security.md"])
        self.assertEqual(keys, ["description", "alwaysApply"])
        self.assertIs(data["alwaysApply"], True)

        keys, _ = frontmatter(built["ycc-common-testing.md"])
        self.assertEqual(keys, ["description"], "a string 'true' is not alwaysApply on OMP")

    def test_r3_flat_name_collision_names_both_files(self) -> None:
        self.put("common/foo-bar.md", rule())
        self.put("common-foo/bar.md", rule(paths=["**/*"]))
        with self.assertRaises(ValueError) as ctx:
            rules.build_rules(self.src)
        self.assertIn("common/foo-bar.md", str(ctx.exception))
        self.assertIn("common-foo/bar.md", str(ctx.exception))

    def test_r4_deeper_nesting_fails(self) -> None:
        self.put("common/security.md", rule())
        self.put("golang/extra/deep.md", rule(paths=["**/*.go"]))
        with self.assertRaisesRegex(ValueError, "nest at most one family directory"):
            rules.build_rules(self.src)

    def test_r5_relative_link_becomes_rule_url(self) -> None:
        body = (
            "# Testing\nKeep CWV targets from [performance.md](performance.md) and [docs](https://example.com/x.md).\n"
        )
        self.put("web/testing.md", rule(body=body, paths=["**/*.tsx"]))
        self.put("web/performance.md", rule(paths=["**/*.tsx"]))
        out = rules.build_rules(self.src)["ycc-web-testing.md"]
        self.assertIn("[performance](rule://ycc-web-performance)", out)
        self.assertIn("[docs](https://example.com/x.md)", out)

    def test_r5_link_to_missing_rule_fails(self) -> None:
        self.put("web/testing.md", rule(body="# Testing\nSee [perf](performance.md).\n", paths=["**/*.tsx"]))
        with self.assertRaisesRegex(ValueError, "web/testing.md: link 'performance.md'"):
            rules.build_rules(self.src)

    def test_r6_forbidden_token_fails(self) -> None:
        self.put("common/agents.md", rule(body="# Agents\nRun /ycc:plan first.\n"))
        with self.assertRaisesRegex(ValueError, "common/agents.md: Claude-only tokens"):
            rules.build_rules(self.src)

    def test_r6_third_always_apply_rule_fails(self) -> None:
        for stem in ("a", "b", "c"):
            self.put(f"common/{stem}.md", rule(alwaysApply=True))
        with self.assertRaisesRegex(ValueError, "too many alwaysApply rules: 3 > 2"):
            rules.build_rules(self.src)

    def test_r7_trigger_per_glob_family_with_union_globs(self) -> None:
        self.put("rust/coding-style.md", rule(description="Use when editing Rust; apply style.", paths=["**/*.rs"]))
        self.put("rust/hooks.md", rule(paths=["**/build.rs"]))
        self.put("rust/security.md", rule(paths=["**/*.rs", "**/Cargo.toml"]))
        self.put("common/security.md", rule(alwaysApply=True))
        self.put("common/testing.md", rule())
        built = rules.build_rules(self.src)

        self.assertNotIn("ycc-common-trigger.md", built)
        text = built["ycc-rust-trigger.md"]
        keys, data = frontmatter(text)
        self.assertEqual(keys, ["globs", "condition", "scope", "interruptMode"], "no description: no rulebook entry")
        self.assertEqual(data["globs"], ["**/*.rs", "**/Cargo.toml"], "skipped hooks.md globs must not leak")
        self.assertEqual(
            (data["condition"], data["scope"], data["interruptMode"]), (".*", ["tool:edit", "tool:write"], "never")
        )
        self.assertIn(
            "[ycc-rust-coding-style](rule://ycc-rust-coding-style): Use when editing Rust; apply style.", text
        )
        self.assertIn("rule://ycc-rust-security", text)
        self.assertNotIn("hooks", text)

    def test_r7_trigger_name_collision_fails(self) -> None:
        self.put("python/trigger.md", rule(paths=["**/*.py"]))
        with self.assertRaisesRegex(ValueError, "ycc-python-trigger.md: trigger name collides with source rule"):
            rules.build_rules(self.src)


if __name__ == "__main__":
    unittest.main()
