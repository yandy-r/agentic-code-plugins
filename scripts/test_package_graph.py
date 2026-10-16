#!/usr/bin/env python3
"""Package component-graph tests: current tree, negative, synthetic, and CLI coverage."""

from __future__ import annotations

import functools
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_package_graph import check_closures, check_duplicates, main, package_sets  # noqa: E402
from package_graph_extract import Graph, extract_graph  # noqa: E402
from package_model import PackageModel, load_package_model  # noqa: E402

SOURCE_ROOT = REPO_ROOT / "ycc"
MISSING_AGENT = "codebase-research-analyst"
AGENT_FILE = "code-researcher.md"


@functools.lru_cache(maxsize=1)
def real_graph() -> tuple[Graph, list[str]]:
    """Extract the real tree once; tests only read the result."""
    return extract_graph(SOURCE_ROOT)


def with_replaced_entry(model: PackageModel, key: str, runtime: str, **fields: Any) -> PackageModel:
    """Return a model with one RuntimePackage replaced (dataclasses.replace, no validation)."""
    packages = []
    for package in model.packages:
        if package.key == key:
            runtimes = tuple(
                replace(entry, **fields) if entry.runtime == runtime else entry for entry in package.runtimes
            )
            packages.append(replace(package, runtimes=runtimes))
        else:
            packages.append(package)
    return replace(model, packages=tuple(packages))


CATALOG_SKILL_NAMES = ("init", "orchestrate", "write-docs")
S1_EVIDENCE = "ycc/skills/s1/SKILL.md"


def write_skill(root: Path, name: str, body: str = "") -> None:
    """Write a minimal SKILL.md (frontmatter plus optional body) for a synthetic skill."""
    (root / "skills" / name).mkdir(parents=True, exist_ok=True)
    (root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}", encoding="utf-8")


def build_tree(parent: Path, s1_body: str = "") -> Path:
    """Build a complete synthetic source tree: catalog skills, `s1`, shared scripts dir, one agent.

    The first body line of `s1` is line 4 of its SKILL.md.
    """
    root = parent / "ycc"
    for directory in ("skills/_shared/scripts", "agents"):
        (root / directory).mkdir(parents=True)
    for catalog in CATALOG_SKILL_NAMES:
        write_skill(root, catalog)
    write_skill(root, "s1", s1_body)
    (root / "agents/real.md").write_text("---\nname: real-agent\n---\n", encoding="utf-8")
    return root


def skill_agent_edges(graph: Graph, skill: str) -> list[tuple[str, str, str]]:
    return [key for key in graph.edges if key[0] == f"skill:{skill}" and key[1].startswith("agent:")]


class CurrentTreeTests(unittest.TestCase):
    def test_extraction_has_no_errors(self) -> None:
        self.assertEqual(real_graph()[1], [])

    def test_named_agent_node_path(self) -> None:
        node = real_graph()[0].nodes.get(f"agent:{MISSING_AGENT}")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.path, "ycc/agents/code-researcher.md")

    def test_init_dispatches_to_named_agent(self) -> None:
        self.assertIn(("skill:init", f"agent:{MISSING_AGENT}", "dispatch"), real_graph()[0].edges)

    def test_real_model_closures_clean_with_agents_only_gaps(self) -> None:
        errors, gaps = check_closures(real_graph()[0], load_package_model())
        self.assertEqual(errors, [])
        self.assertNotEqual(gaps, [])
        for gap in gaps:
            self.assertIn("@agents ", gap)

    def test_real_model_has_no_duplicates(self) -> None:
        self.assertEqual(check_duplicates(load_package_model()), [])


class MissingAgentTests(unittest.TestCase):
    """Runs against a temp tree with only agents/ copied; skills/ is a read-only symlink."""

    tmp: ClassVar[tempfile.TemporaryDirectory[str]]
    root: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()  # noqa: SIM115 - cleaned up in tearDownClass
        cls.root = Path(cls.tmp.name) / "ycc"
        cls.root.mkdir()
        os.symlink(SOURCE_ROOT / "skills", cls.root / "skills")
        shutil.copytree(SOURCE_ROOT / "agents", cls.root / "agents")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def tearDown(self) -> None:
        (self.root / "agents" / AGENT_FILE).write_bytes((SOURCE_ROOT / "agents" / AGENT_FILE).read_bytes())

    def test_deleted_agent_file_errors(self) -> None:
        (self.root / "agents" / AGENT_FILE).unlink()
        _, errors = extract_graph(self.root)
        self.assertTrue(any(MISSING_AGENT in error for error in errors), errors)

    def test_renamed_agent_frontmatter_errors(self) -> None:
        path = self.root / "agents" / AGENT_FILE
        text = path.read_text(encoding="utf-8").replace("name: codebase-research-analyst", "name: renamed-agent", 1)
        self.assertNotEqual(text, path.read_text(encoding="utf-8"))
        path.write_text(text, encoding="utf-8")
        _, errors = extract_graph(self.root)
        self.assertTrue(any(MISSING_AGENT in error for error in errors), errors)

    def test_missing_agent_cli_returns_1(self) -> None:
        (self.root / "agents" / AGENT_FILE).unlink()
        self.assertEqual(main(["--source-root", str(self.root)]), 1)


class ModelMutationTests(unittest.TestCase):
    def test_duplicate_agents_component_on_claude(self) -> None:
        model = with_replaced_entry(load_package_model(), "ycc-agents", "claude", status="included")
        self.assertEqual(check_duplicates(model), ["duplicate component 'agents' on claude: ycc, ycc-agents"])

    def test_closure_unsatisfied_without_codex_fallback_agents(self) -> None:
        model = load_package_model()
        entry = model.lookup("installer-fallback", "codex")
        assert entry is not None
        components = tuple(c for c in entry.components if c != "agents")
        self.assertNotEqual(components, entry.components)
        mutated = with_replaced_entry(model, "installer-fallback", "codex", components=components)
        errors, _ = check_closures(real_graph()[0], mutated)
        self.assertTrue(any("ycc@codex" in error and "closure unsatisfied" in error for error in errors), errors)


class SyntheticTreeTests(unittest.TestCase):
    def test_edge_kinds_and_traversal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "ycc"
            for directory in ("skills/s1", "skills/s2", "skills/_shared/scripts", "agents"):
                (root / directory).mkdir(parents=True)
            (root / "skills/s1/SKILL.md").write_text(
                "---\nname: s1\n---\n"
                "Shared: ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/h.sh#anchor\n"
                "Also: ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/{h.sh,i.sh}\n"
                "Script: ${CLAUDE_PLUGIN_ROOT}/skills/s2/helper.sh\n"
                "Escaping: ${CLAUDE_PLUGIN_ROOT}/skills/../../outside\n",
                encoding="utf-8",
            )
            (root / "skills/s2/SKILL.md").write_text("---\nname: s2\n---\n", encoding="utf-8")
            (root / "skills/s2/helper.sh").write_text("# shellcheck shell=sh\n", encoding="utf-8")
            (root / "skills/_shared/scripts/h.sh").write_text("# shellcheck shell=sh\n", encoding="utf-8")
            (root / "skills/_shared/scripts/i.sh").write_text("# shellcheck shell=sh\n", encoding="utf-8")
            for catalog in CATALOG_SKILL_NAMES:
                write_skill(root, catalog)
            (root / "agents/a1.md").write_text(
                "---\nname: named-one\nskills:\n- s1\n---\nHand off to ycc:named-two and stem ref ycc:stem-only.\n",
                encoding="utf-8",
            )
            (root / "agents/stem-only.md").write_text("---\nname: named-two\n---\n", encoding="utf-8")
            graph, errors = extract_graph(root)
            self.assertIn(("skill:s1", "shared:scripts/h.sh", "shared"), graph.edges)  # #anchor strip
            self.assertIn(("skill:s1", "shared:scripts/i.sh", "shared"), graph.edges)  # {a,b} expansion
            self.assertIn(("skill:s1", "skill:s2", "script"), graph.edges)
            self.assertIn(("agent:named-one", "skill:s1", "preload"), graph.edges)  # zero-indent list item
            self.assertIn(("agent:named-one", "agent:named-two", "handoff"), graph.edges)
            self.assertTrue(any("did you mean frontmatter name 'named-two'" in error for error in errors), errors)
            self.assertTrue(any("source path escapes skills" in error for error in errors), errors)


class StrictDispatchTests(unittest.TestCase):
    BAD_NAMES = (
        "Codebase-Research-Analyst",
        "codebaseResearchAnalyst",
        "real-agent_extra",
        "generalPurpose_extra",
    )

    @staticmethod
    def syntaxes(name: str) -> dict[str, str]:
        return {
            "generic equals": f'subagent_type="{name}"',
            "generic colon": f"subagent_type: {name}",
            "generic ycc namespace": f'subagent_type="ycc:{name}"',
            "bold": f"**Subagent Type**: `{name}`",
            "bold ycc namespace": f"**Subagent Type**: `ycc:{name}`",
            "table": f"| Subagent Type | `{name}` |",
            "pipe backtick": f"| subagent_type | `{name}` |",
            "table ycc namespace": f"| Subagent Type | `ycc:{name}` |",
        }

    def test_invalid_concrete_dispatch_errors_in_every_syntax(self) -> None:
        for bad in self.BAD_NAMES:
            for label, line in self.syntaxes(bad).items():
                with self.subTest(name=bad, syntax=label), tempfile.TemporaryDirectory() as tmpdir:
                    root = build_tree(Path(tmpdir), line + "\n")
                    graph, errors = extract_graph(root)
                    self.assertTrue(
                        any(
                            "invalid agent reference" in e and repr(bad) in e and f"{S1_EVIDENCE}:4" in e
                            for e in errors
                        ),
                        errors,
                    )
                    self.assertEqual(skill_agent_edges(graph, "s1"), [])

    def test_valid_dispatch_in_every_syntax_has_no_errors(self) -> None:
        for label, line in self.syntaxes("real-agent").items():
            with self.subTest(syntax=label), tempfile.TemporaryDirectory() as tmpdir:
                graph, errors = extract_graph(build_tree(Path(tmpdir), line + "\n"))
                self.assertEqual(errors, [])
                self.assertIn(("skill:s1", "agent:real-agent", "dispatch"), graph.edges)

    def test_builtin_and_placeholder_dispatches_are_preserved(self) -> None:
        lines = (
            'subagent_type="generalPurpose"',
            "subagent_type: generalPurpose",
            'subagent_type="ycc:generalPurpose"',
            "**Subagent Type**: `generalPurpose`",
            "| Subagent Type | `generalPurpose` |",
            'subagent_type="<type>"',
            "subagent_type = <subagent-type>",
            'subagent_type="{{agent}}"',
            "subagent_type: {{agent}}",
            "**Subagent Type**: `<agent-type>`",
            "**Subagent Type**: `{{agent}}`",
            "| Subagent Type | `<type>` |",
            "| Subagent Type | `{{agent}}` |",
            "| subagent_type | `<type>` |",
            "| subagent_type | `{{agent}}` |",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            graph, errors = extract_graph(build_tree(Path(tmpdir), "\n".join(lines) + "\n"))
            self.assertEqual(errors, [])
            self.assertEqual(skill_agent_edges(graph, "s1"), [])

    def test_table_header_cells_are_not_dispatch_references(self) -> None:
        body = "| name | subagent_type | Plan section |\n| subagent_type | `RoleFocus` |\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            graph, errors = extract_graph(build_tree(Path(tmpdir), body))
            self.assertFalse(any("'Plan'" in error for error in errors), errors)
            self.assertTrue(any("invalid agent reference" in e and "'RoleFocus'" in e for e in errors), errors)
            self.assertEqual(skill_agent_edges(graph, "s1"), [])


class CatalogSkillTests(unittest.TestCase):
    def test_complete_synthetic_tree_has_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph, errors = extract_graph(build_tree(Path(tmpdir)))
            self.assertEqual(errors, [])
            for catalog in CATALOG_SKILL_NAMES:
                self.assertIn((f"skill:{catalog}", "agent:real-agent", "catalog"), graph.edges)

    def test_each_missing_catalog_skill_errors(self) -> None:
        for catalog in CATALOG_SKILL_NAMES:
            with self.subTest(catalog=catalog), tempfile.TemporaryDirectory() as tmpdir:
                root = build_tree(Path(tmpdir))
                shutil.rmtree(root / "skills" / catalog)  # synthetic tree only; never the real skills symlink
                _, errors = extract_graph(root)
                self.assertTrue(
                    any(catalog in e and "catalog" in e.lower() and "missing" in e.lower() for e in errors), errors
                )

    def test_missing_catalog_skill_cli_returns_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = build_tree(Path(tmpdir))
            shutil.rmtree(root / "skills" / "orchestrate")
            self.assertEqual(main(["--source-root", str(root)]), 1)


class SharedFileTests(unittest.TestCase):
    def test_missing_shared_file_errors_with_source_evidence(self) -> None:
        body = "Run ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/missing.sh\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            graph, errors = extract_graph(build_tree(Path(tmpdir), body))
            self.assertTrue(
                any(
                    f"{S1_EVIDENCE}:4" in e and "missing source file" in e and "_shared/scripts/missing.sh" in e
                    for e in errors
                ),
                errors,
            )
            self.assertNotIn(("skill:s1", "shared:scripts/missing.sh", "shared"), graph.edges)


class RequiresCycleTests(unittest.TestCase):
    def cyclic_model(self) -> PackageModel:
        model = load_package_model()
        for key, required in (("ycc", "ycc-mcp"), ("ycc-mcp", "ycc-hooks"), ("ycc-hooks", "ycc")):
            model = with_replaced_entry(model, key, "claude", requires=(required,))
        return model

    def test_transitive_requires_cycle_is_reported(self) -> None:
        _, errors = package_sets(self.cyclic_model())
        self.assertIn("requires cycle on claude: ycc -> ycc-mcp -> ycc-hooks -> ycc", errors)

    def test_check_closures_retains_cycle_errors(self) -> None:
        errors, _ = check_closures(real_graph()[0], self.cyclic_model())
        self.assertIn("requires cycle on claude: ycc -> ycc-mcp -> ycc-hooks -> ycc", errors)


class RuntimeGapTests(unittest.TestCase):
    def test_missing_agents_on_non_agents_runtime_is_error_not_gap(self) -> None:
        for key, runtime in (("installer-fallback", "codex"), ("ycc", "claude")):
            with self.subTest(package=key, runtime=runtime):
                model = load_package_model()
                entry = model.lookup(key, runtime)
                assert entry is not None
                components = tuple(c for c in entry.components if c != "agents")
                self.assertNotEqual(components, entry.components)
                mutated = with_replaced_entry(model, key, runtime, components=components)
                errors, gaps = check_closures(real_graph()[0], mutated)
                self.assertTrue(
                    any(f"@{runtime}" in e and "closure unsatisfied" in e and "agent:" in e for e in errors), errors
                )
                self.assertFalse(any(f"@{runtime} " in gap for gap in gaps), gaps)


class OutputTests(unittest.TestCase):
    def test_output_writes_schema_version_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = str(Path(tmpdir) / "graph.json")
            self.assertEqual(main(["--output", outfile]), 0)
            payload = json.loads(Path(outfile).read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertIn("nodes", payload)
            self.assertIn("edges", payload)


if __name__ == "__main__":
    started = time.perf_counter()
    try:
        unittest.main()
    finally:
        print(f"runtime: {time.perf_counter() - started:.1f}s", file=sys.stderr)
