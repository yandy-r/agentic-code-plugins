#!/usr/bin/env python3
"""Per-entry selection (``list`` / ``--entries``) for install_slices.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install_slices


class SelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.state_file = self.home / "state" / "installed-units.json"
        env = {"HOME": str(self.home), "YCC_MANAGED_CONFIG_STATE": str(self.state_file.parent / "managed.json")}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = install_slices.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    def units(self) -> dict[str, list[str]]:
        if not self.state_file.is_file():
            return {}
        units: dict[str, list[str]] = json.loads(self.state_file.read_text(encoding="utf-8"))["units"]
        return units

    def listed(self, target: str, slice_name: str) -> list[str]:
        rc, out, _ = self.run_cli("list", "--target", target, "--slice", slice_name)
        self.assertEqual(rc, 0)
        return out.splitlines()

    def test_list_hides_helpers_and_maps_stems(self) -> None:
        codex_agents = self.listed("codex", "agents")
        self.assertIn("implementor", codex_agents)
        self.assertFalse(any(name.endswith((".toml", ".md")) for name in codex_agents))
        self.assertEqual(codex_agents, sorted(codex_agents))
        self.assertIn("implementor", self.listed("claude", "agents"))
        for target in ("claude", "cursor", "codex", "opencode", "agents"):
            skills = self.listed(target, "skills")
            self.assertIn("code-review", skills, target)
            self.assertFalse({"_shared", "shared", "ycc-shared"} & set(skills), target)
        self.assertEqual(self.listed("claude", "commands"), self.listed("claude", "skills"))
        self.assertEqual(self.listed("agents", "agents"), [])
        self.assertFalse(self.home.joinpath(".codex").exists())

    def test_selective_install_keeps_owned_entries_and_state(self) -> None:
        skills = self.home / ".codex/skills"
        self.assertEqual(self.run_cli("install", "--target", "codex", "--slice", "skills")[0], 0)
        before = self.units()[str(skills)]
        listing = sorted(p.name for p in skills.iterdir())
        rc, _, _ = self.run_cli("install", "--target", "codex", "--slice", "skills", "--entries", "code-review")
        self.assertEqual(rc, 0)
        self.assertEqual(self.units()[str(skills)], before)
        self.assertEqual(sorted(p.name for p in skills.iterdir()), listing)
        rc, out, _ = self.run_cli("install", "--target", "codex", "--slice", "skills")
        self.assertEqual(rc, 0)
        self.assertNotIn("removed", out)
        self.assertEqual(self.units()[str(skills)], before)

    def test_selective_install_ships_helpers_and_merges_state(self) -> None:
        rc, _, _ = self.run_cli("install", "--target", "opencode", "--slice", "skills", "--entries", "code-review")
        self.assertEqual(rc, 0)
        skills = self.home / ".config/opencode/skills"
        self.assertEqual(sorted(p.name for p in skills.iterdir()), ["code-review"])
        self.assertTrue((self.home / ".config/opencode/shared").is_dir())
        rc, _, _ = self.run_cli("install", "--target", "opencode", "--slice", "skills", "--entries", "quick-review")
        self.assertEqual(rc, 0)
        self.assertEqual(self.units()[str(skills)], ["code-review", "quick-review"])

    def test_codex_agents_stem_mapping(self) -> None:
        args = ("--target", "codex", "--slice", "agents", "--entries", "implementor,code-reviewer")
        self.assertEqual(self.run_cli("install", *args)[0], 0)
        agents = self.home / ".codex/agents"
        self.assertEqual(sorted(p.name for p in agents.iterdir()), ["code-reviewer.toml", "implementor.toml"])
        rc, _, _ = self.run_cli("remove", "--target", "codex", "--slice", "agents", "--entries", "implementor")
        self.assertEqual(rc, 0)
        self.assertEqual(self.units()[str(agents)], ["code-reviewer.toml"])
        self.assertEqual([p.name for p in agents.iterdir()], ["code-reviewer.toml"])

    def test_remove_keeps_helpers_until_last_owned_entry(self) -> None:
        base = ("--target", "codex", "--slice", "skills", "--entries")
        self.assertEqual(self.run_cli("install", *base, "code-review,quick-review")[0], 0)
        skills = self.home / ".codex/skills"
        self.assertEqual(self.units()[str(skills)], ["_shared", "code-review", "quick-review"])
        self.assertEqual(self.run_cli("remove", *base, "code-review")[0], 0)
        self.assertEqual(sorted(p.name for p in skills.iterdir()), ["_shared", "quick-review"])
        self.assertEqual(self.units()[str(skills)], ["_shared", "quick-review"])
        self.assertEqual(self.run_cli("remove", *base, "quick-review")[0], 0)
        self.assertFalse(skills.exists())
        self.assertNotIn(str(skills), self.units())

    def test_remove_helper_unit_with_last_owned_entry(self) -> None:
        base = ("--target", "agents", "--slice", "skills", "--entries")
        self.assertEqual(self.run_cli("install", *base, "code-review,quick-review")[0], 0)
        shared = self.home / ".agents/ycc-shared"
        self.assertTrue(shared.is_dir())
        self.assertEqual(self.run_cli("remove", *base, "code-review")[0], 0)
        self.assertTrue(shared.is_dir())
        self.assertEqual(self.run_cli("remove", *base, "quick-review")[0], 0)
        self.assertFalse(shared.exists())
        self.assertFalse((self.home / ".agents/skills").exists())
        self.assertEqual(self.units(), {})

    def test_remove_keeps_helpers_beside_untracked_base_mirror(self) -> None:
        # 'base' rsyncs the whole bundle and records nothing in state.
        for src, dest in (
            ("packages/cursor/ycc/skills", ".cursor/skills"),
            (".opencode-plugin/skills", ".config/opencode/skills"),
            (".opencode-plugin/shared", ".config/opencode/shared"),
        ):
            shutil.copytree(install_slices.REPO_ROOT / src, self.home / dest, symlinks=True)
        for target, skills, helper in (
            ("cursor", ".cursor/skills", ".cursor/skills/_shared"),
            ("opencode", ".config/opencode/skills", ".config/opencode/shared"),
        ):
            args = ("remove", "--target", target, "--slice", "skills", "--entries", "go-patterns")
            self.assertEqual(self.run_cli(*args)[0], 0, target)
            self.assertFalse((self.home / skills / "go-patterns").exists(), target)
            self.assertTrue((self.home / helper).is_dir(), f"{target} keeps its shared helpers")
            self.assertTrue((self.home / skills / "code-review").is_dir(), target)

    def test_dependency_warning_counts_same_run_selection(self) -> None:
        args = ("install", "--target", "claude", "--slice", "skills", "--entries", "plan")
        rc, out, _ = self.run_cli(*args)
        self.assertEqual(rc, 0)
        self.assertIn("agent 'planner' is referenced by plan", out)
        with patch.dict(os.environ, {"YCC_PENDING_AGENTS": "planner"}):
            rc, out, _ = self.run_cli(*args)
        self.assertEqual(rc, 0)
        self.assertNotIn("'planner'", out)

    def test_unknown_name_writes_nothing(self) -> None:
        args = ("--target", "claude", "--slice", "skills", "--entries", "code-review,nope")
        rc, out, err = self.run_cli("install", *args)
        self.assertEqual(rc, 1)
        self.assertIn("[err] unknown skills entry for claude: nope (valid: ", err)
        self.assertIn("code-review", err)
        self.assertEqual(out, "")
        self.assertFalse((self.home / ".claude").exists())
        self.assertFalse(self.state_file.exists())

    def test_entries_rejected_for_strict_and_claude_commands_remove(self) -> None:
        for args in (
            ("install", "--target", "cursor", "--slice", "commands", "--entries", "plan"),
            ("remove", "--target", "claude", "--slice", "commands", "--entries", "plan"),
        ):
            with self.assertRaises(SystemExit) as caught:
                self.run_cli(*args)
            self.assertEqual(caught.exception.code, 2)

    def test_dependency_warning_fires_and_clears(self) -> None:
        args = ("install", "--target", "claude", "--slice", "skills", "--entries", "code-review")
        rc, out, _ = self.run_cli(*args)
        self.assertEqual(rc, 0)
        self.assertIn(
            "[!!]  claude: agent 'code-reviewer' is referenced by code-review but not installed"
            " — add it: ycc sync --target claude --intent agents --agents code-reviewer",
            out,
        )
        self.assertIn("skill 'review-fix' is referenced by code-review", out)
        rc, _, _ = self.run_cli("install", "--target", "claude", "--slice", "agents")
        self.assertEqual(rc, 0)
        rc, _, _ = self.run_cli("install", "--target", "claude", "--slice", "skills")
        self.assertEqual(rc, 0)
        rc, out, _ = self.run_cli(*args)
        self.assertEqual(rc, 0)
        self.assertNotIn("[!!]", out)

    def test_dependency_warning_silent_with_plugin(self) -> None:
        plugins = self.home / ".claude/plugins/installed_plugins.json"
        plugins.parent.mkdir(parents=True)
        plugins.write_text('{"plugins": {"ycc@ycc": []}}', encoding="utf-8")
        rc, out, _ = self.run_cli("install", "--target", "claude", "--slice", "skills", "--entries", "code-review")
        self.assertEqual(rc, 0)
        self.assertNotIn("[!!]", out)

    def test_dispatched_only_agent_warning(self) -> None:
        args = ("install", "--target", "opencode", "--slice", "agents", "--entries", "review-fixer")
        rc, out, _ = self.run_cli(*args)
        self.assertEqual(rc, 0)
        self.assertIn("[!!]  opencode: agent 'review-fixer' is dispatched only by ", out)
        self.assertIn("review-fix", out)
        skills = self.home / ".agents/skills/review-fix"
        skills.mkdir(parents=True)
        rc, out, _ = self.run_cli(*args)
        self.assertEqual(rc, 0)
        self.assertNotIn("dispatched only", out)


if __name__ == "__main__":
    unittest.main()
