#!/usr/bin/env python3
"""Offline tag/base/version publication guards; never contact npm or create a product tag in the checkout."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import opencode_npm_release as guard

ROOT = Path(__file__).resolve().parent.parent


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Hooks can export repository-specific git variables; never mutate the caller's repo.
        env = dict(os.environ)
        for key in subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).splitlines():
            env.pop(key, None)
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Release guard test")
        self.git("config", "user.email", "release@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "tag.gpgsign", "false")
        self.write(guard.CANONICAL, {"name": "ycc", "version": "6.0.0"})
        self.write(guard.PACKAGE, {"name": "@yandy-r/ycc-opencode", "version": "6.0.0"})
        self.write(
            Path(".claude-plugin/marketplace.json"),
            {"plugins": [{"name": "ycc", "version": "6.0.0"}]},
        )
        self.write(
            Path("ycc/settings/packages.json"),
            {
                "version_source": str(guard.CANONICAL),
                "packages": {
                    "ycc": {"runtimes": {"claude": {"status": "included", "mechanism": "native"}}},
                    "@yandy-r/ycc-opencode": {"runtimes": {"opencode": {"status": "included", "mechanism": "npm"}}},
                },
            },
        )
        checker = self.root / guard.CHECKER
        checker.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / guard.CHECKER, checker)
        self.git("add", ".")
        self.git("commit", "-qm", "release fixture")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.sha)
        self.git("tag", "-a", "v6.0.0", "-m", "fixture tag")

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE, text=True).strip()

    def write(self, rel: Path, data: object) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    def check(self, event: str = "push", ref: str = "refs/tags/v6.0.0", sha: str | None = None) -> str:
        return guard.check_release(self.root, event, ref, self.sha if sha is None else sha)

    def test_valid_tag_and_lockstep_package_pass(self) -> None:
        self.assertEqual(self.check(), "6.0.0")

    def test_tag_can_be_ancestor_of_current_main(self) -> None:
        (self.root / "later").touch()
        self.git("add", ".")
        self.git("commit", "-qm", "later main commit")
        self.git("update-ref", "refs/remotes/origin/main", self.git("rev-parse", "HEAD"))
        self.git("checkout", "--detach", self.sha)
        self.assertEqual(self.check(), "6.0.0")

    def test_ordinary_branches_prs_and_manual_runs_fail(self) -> None:
        for event, ref in (
            ("push", "refs/heads/main"),
            ("push", "refs/heads/v6.0.0"),
            ("pull_request", "refs/tags/v6.0.0"),
            ("workflow_dispatch", "refs/tags/v6.0.0"),
        ):
            with self.subTest(event=event, ref=ref), self.assertRaises(guard.ReleaseGuardError):
                self.check(event, ref)

    def test_wrong_tag_format_fails(self) -> None:
        for tag in ("v6", "v6.0", "v06.0.0", "v6.0.0-beta.1", "v6.0.0+build", "ycc-opencode-v6.0.0"):
            with self.subTest(tag=tag), self.assertRaisesRegex(guard.ReleaseGuardError, "vX.Y.Z"):
                self.check(ref=f"refs/tags/{tag}")

    def test_wrong_tag_version_fails(self) -> None:
        self.git("tag", "v6.0.1")
        with self.assertRaisesRegex(guard.ReleaseGuardError, "version mismatch"):
            self.check(ref="refs/tags/v6.0.1")

    def test_canonical_generated_mismatch_fails(self) -> None:
        self.write(guard.PACKAGE, {"name": "@yandy-r/ycc-opencode", "version": "5.3.0"})
        with self.assertRaisesRegex(guard.ReleaseGuardError, "version mismatch"):
            self.check()

    def test_missing_npm_manifest_fails_without_source_mutation(self) -> None:
        before = (self.root / guard.CANONICAL).read_bytes()
        (self.root / guard.PACKAGE).unlink()
        with self.assertRaisesRegex(guard.ReleaseGuardError, "package.json"):
            self.check()
        self.assertEqual((self.root / guard.CANONICAL).read_bytes(), before)

    def test_wrong_package_name_fails(self) -> None:
        self.write(guard.PACKAGE, {"name": "not-the-owned-package", "version": "6.0.0"})
        with self.assertRaisesRegex(guard.ReleaseGuardError, "package name"):
            self.check()

    def test_other_lockstep_surfaces_are_required(self) -> None:
        self.write(Path(".claude-plugin/marketplace.json"), {"plugins": [{"name": "ycc", "version": "5.3.0"}]})
        with self.assertRaisesRegex(guard.ReleaseGuardError, "expected 6.0.0"):
            self.check()

    def test_wrong_event_sha_or_checkout_fails(self) -> None:
        with self.assertRaisesRegex(guard.ReleaseGuardError, "same commit"):
            self.check(sha="0" * 40)
        with self.assertRaisesRegex(guard.ReleaseGuardError, "full commit SHA"):
            self.check(sha=self.sha[:8])
        (self.root / "later").touch()
        self.git("add", ".")
        self.git("commit", "-qm", "different checkout")
        with self.assertRaisesRegex(guard.ReleaseGuardError, "same commit"):
            self.check()

    def test_topic_only_tag_fails_main_ancestry(self) -> None:
        self.git("checkout", "-qb", "topic")
        (self.root / "topic").touch()
        self.git("add", ".")
        self.git("commit", "-qm", "topic only")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("tag", "-f", "v6.0.0")
        with self.assertRaisesRegex(guard.ReleaseGuardError, "merge-base"):
            self.check()

    def test_missing_main_ref_fails_closed(self) -> None:
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaises(guard.ReleaseGuardError):
            self.check()

    def test_cli_without_ci_event_fails_closed(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(guard.main(["--root", str(self.root), "--event", "", "--ref", "", "--sha", ""]), 1)


if __name__ == "__main__":
    unittest.main()
