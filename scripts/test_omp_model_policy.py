#!/usr/bin/env python3
"""Policy tests for scripts/omp_model_policy.py (targets.omp and the managed snippet)."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import omp_model_policy as policy  # noqa: E402
from generate_codex_common import SRC_AGENTS_DIR, parse_frontmatter  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def used_agent_models() -> set[str]:
    return {
        str(parse_frontmatter(path.read_text(encoding="utf-8"))[0].get("model", "inherit"))
        for path in SRC_AGENTS_DIR.glob("*.md")
    }


class OmpModelPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.omp = policy.load_omp()
        self.snippet: dict[str, Any] = yaml.safe_load((REPO_ROOT / self.omp["config"]).read_text(encoding="utf-8"))
        self.used = used_agent_models()

    def errors(self, omp: dict[str, Any] | None = None, snippet: object = None) -> list[str]:
        return policy.omp_model_errors(
            self.omp if omp is None else omp, self.snippet if snippet is None else snippet, self.used
        )

    def assert_error(self, errors: list[str], *needles: str) -> None:
        self.assertTrue(
            any(all(needle in error for needle in needles) for error in errors),
            f"expected an error containing {needles!r}; got {errors!r}",
        )

    def test_p1_repo_models_and_snippet_are_valid(self) -> None:
        self.assertEqual(self.errors(), [])
        self.assertEqual(policy.agent_model_map(), {"opus": "@slow", "sonnet": "@task", "inherit": None})

    def test_p2_unknown_role_rejected(self) -> None:
        omp = copy.deepcopy(self.omp)
        omp["roles"]["architect"] = "subagent"
        self.assert_error(self.errors(omp), "roles.architect", "unknown OMP role")

    def test_p3_bad_selector_or_effort_rejected(self) -> None:
        cases = {
            "bare id": ("subagent", "model", "claude-opus-5", "subagent.model"),
            "missing provider": ("main", "model", "/claude-fable-5-1", "main.model"),
            "unknown effort": ("fallback", "effort", "ultra", "fallback.effort"),
        }
        for label, (entry, field, value, needle) in cases.items():
            with self.subTest(label):
                omp = copy.deepcopy(self.omp)
                omp[entry][field] = value
                self.assert_error(self.errors(omp), needle, repr(value))

    def test_p4_agent_model_alias_rejected(self) -> None:
        omp = copy.deepcopy(self.omp)
        omp["agentModels"]["opus"] = "pi/slow"
        self.assert_error(self.errors(omp), "agentModels.opus", "legacy 'pi/'")

        omp = copy.deepcopy(self.omp)
        omp["agentModels"]["opus"] = "@plan"
        self.assert_error(self.errors(omp), "agentModels.opus", "'@plan'", "does not manage")

        omp = copy.deepcopy(self.omp)
        del omp["agentModels"]["sonnet"]
        self.assert_error(self.errors(omp), "agentModels", "sonnet")

    def test_p5_snippet_extra_key_or_drift_rejected(self) -> None:
        snippet = copy.deepcopy(self.snippet)
        snippet["tools"]["approval"] = {"bash": "allow"}
        self.assert_error(self.errors(snippet=snippet), "tools.approval", "not a ycc-managed OMP key")

        snippet = copy.deepcopy(self.snippet)
        snippet["modelRoles"]["slow"] = "anthropic/claude-opus-5:max"
        self.assert_error(self.errors(snippet=snippet), "modelRoles.slow", "claude-opus-5:max")


if __name__ == "__main__":
    unittest.main()
