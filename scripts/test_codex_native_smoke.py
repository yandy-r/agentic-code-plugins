#!/usr/bin/env python3
"""Behavior tests for codex_native_smoke.check_checkout using real Git repos.

Run directly (``python3 scripts/test_codex_native_smoke.py``). No Codex CLI,
network, or model is used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import codex_native_smoke  # noqa: E402

SPARSE_DIRS = (".agents/plugins", ".codex-plugin/ycc", ".codex-plugin/ycc-mcp")


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@localhost",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return proc.stdout.strip()


class CheckCheckoutTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        # Hooks can export repository-specific GIT_* variables (GIT_DIR,
        # GIT_WORK_TREE, ...) that would point every git subprocess — this
        # module's helper and check_checkout's own git calls alike — at the
        # caller's repository. Strip them and pin git to no system/global
        # config before the first git call so all subprocesses share one
        # clean Git environment with no inherited hooks or templates.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.repo = self.root / "staging"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        for rel in (*SPARSE_DIRS, "outside"):
            (self.repo / rel).mkdir(parents=True)
            (self.repo / rel / "f").write_text(rel, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "first")
        self.pinned = git(self.repo, "rev-parse", "HEAD")
        self.add_path = self.root / "add.json"
        self.add_path.write_text(json.dumps({"installedRoot": str(self.repo)}), encoding="utf-8")

    def check(self, profile: str, ref: str | None = None) -> None:
        codex_native_smoke.check_checkout(self.add_path, ref or self.pinned, profile)

    def sparse(self, *dirs: str) -> None:
        git(self.repo, "sparse-checkout", "set", "--cone", *dirs)

    def test_full_profile_accepts_non_sparse_checkout_at_pinned_commit(self) -> None:
        self.check("full")

    def test_full_profile_rejects_sparse_checkout(self) -> None:
        self.sparse(*SPARSE_DIRS)
        with self.assertRaisesRegex(ValueError, "sparse"):
            self.check("full")

    def test_sparse_profile_accepts_exact_selection(self) -> None:
        self.sparse(*SPARSE_DIRS)
        self.check("sparse")

    def test_sparse_profile_rejects_extra_selection(self) -> None:
        self.sparse(*SPARSE_DIRS, "outside")
        with self.assertRaisesRegex(ValueError, "unexpected.*outside"):
            self.check("sparse")

    def test_sparse_profile_rejects_missing_selection(self) -> None:
        self.sparse(*SPARSE_DIRS[:2])
        with self.assertRaisesRegex(ValueError, "missing.*ycc-mcp"):
            self.check("sparse")

    def test_sparse_profile_rejects_non_sparse_checkout(self) -> None:
        with self.assertRaises(ValueError):
            self.check("sparse")

    def test_wrong_head_is_rejected_for_every_profile(self) -> None:
        (self.repo / "outside/f").write_text("moved", encoding="utf-8")
        git(self.repo, "commit", "-qam", "second")
        for profile in ("full", "sparse"):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, "!= pinned"):
                    self.check(profile)

    def test_non_sha_ref_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "full lowercase commit SHA"):
            self.check("full", "main")


if __name__ == "__main__":
    unittest.main()
