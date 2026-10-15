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
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from build_package_graph import check_closures, check_duplicates, main  # noqa: E402
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
