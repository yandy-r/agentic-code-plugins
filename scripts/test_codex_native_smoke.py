#!/usr/bin/env python3
"""Behavior tests for codex_native_smoke checks (checkout, fixture, version).

check_checkout uses real Git repos; check_fixture uses temporary trees.

Run directly (``python3 scripts/test_codex_native_smoke.py``). No Codex CLI,
network, or model is used.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
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


def catalog(*paths: str) -> str:
    plugins = [
        {"name": Path(p).name, "source": {"source": "local", "path": p}, "policy": {"installation": "AVAILABLE"}}
        for p in paths
    ]
    return json.dumps({"name": "ycc", "plugins": plugins}, indent=2)


class CheckFixtureTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.fresh = root / "fresh"
        self.remote = root / "remote"
        self.write(
            self.fresh, ".agents/plugins/marketplace.json", catalog("./.codex-plugin/ycc", "./.codex-plugin/ycc-mcp")
        )
        self.write(self.fresh, ".codex-plugin/ycc/.codex-plugin/plugin.json", '{"name": "ycc"}\n')
        self.write(self.fresh, ".codex-plugin/ycc/skills/s/SKILL.md", "skill\n")
        self.write(self.fresh, ".codex-plugin/ycc/skills/s/scripts/run.sh", "#!/bin/sh\n", executable=True)
        self.write(self.fresh, ".codex-plugin/ycc-mcp/.mcp.json", "{}\n")
        shutil.copytree(self.fresh, self.remote)
        # Installer-owned entries the native export never emits.
        self.write(self.remote, ".codex-plugin/agents/x.toml", "name = 'x'\n")
        self.write(self.remote, ".codex-plugin/config/y", "y\n")

    @staticmethod
    def write(root: Path, rel: str, text: str, *, executable: bool = False) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755 if executable else 0o644)

    def check(self) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codex_native_smoke.check_fixture(self.fresh, self.remote)
        return out.getvalue()

    def test_passes_and_ignores_installer_owned_entries(self) -> None:
        output = self.check()
        self.assertIn("PASS", output)
        self.assertIn(".codex-plugin/ycc, .codex-plugin/ycc-mcp", output)

    def test_changed_payload_byte_fails(self) -> None:
        self.write(self.remote, ".codex-plugin/ycc/skills/s/SKILL.md", "skilL\n")
        with self.assertRaisesRegex(ValueError, r"changed=\['skills/s/SKILL.md'\]"):
            self.check()

    def test_lost_exec_bit_fails(self) -> None:
        (self.remote / ".codex-plugin/ycc/skills/s/scripts/run.sh").chmod(0o644)
        with self.assertRaisesRegex(ValueError, r"changed=\['skills/s/scripts/run.sh'\]"):
            self.check()

    def test_extra_file_in_payload_dir_fails(self) -> None:
        self.write(self.remote, ".codex-plugin/ycc-mcp/stray.txt", "stray\n")
        with self.assertRaisesRegex(ValueError, r"ycc-mcp: missing=\[\] extra=\['stray.txt'\]"):
            self.check()

    def test_missing_payload_dir_fails(self) -> None:
        shutil.rmtree(self.remote / ".codex-plugin/ycc-mcp")
        with self.assertRaisesRegex(ValueError, r"ycc-mcp: missing=\['.mcp.json'\]"):
            self.check()

    def test_catalog_drift_fails(self) -> None:
        self.write(self.remote, ".agents/plugins/marketplace.json", catalog("./.codex-plugin/ycc"))
        with self.assertRaisesRegex(ValueError, r"\.agents/plugins: .*changed=\['marketplace.json'\]"):
            self.check()

    def test_catalog_without_plugins_fails(self) -> None:
        self.write(self.fresh, ".agents/plugins/marketplace.json", catalog())
        with self.assertRaisesRegex(ValueError, "names no plugins"):
            self.check()

    def test_unsafe_catalog_source_is_rejected(self) -> None:
        bad_sources = (
            {"source": "local", "path": "./.codex-plugin/../x"},
            {"source": "local", "path": "./.codex-plugin/.."},
            {"source": "local", "path": "./other/ycc"},
            {"source": "local", "path": "./.codex-plugin/ycc/nested"},
            {"source": "local", "path": "/abs/.codex-plugin/ycc"},
            {"source": "git", "path": "./.codex-plugin/ycc"},
            {"source": "local", "path": "./.codex-plugin/ycc", "url": "https://example.invalid"},
        )
        for source in bad_sources:
            with self.subTest(source=source):
                doc = {"name": "ycc", "plugins": [{"name": "ycc", "source": source}]}
                self.write(self.fresh, ".agents/plugins/marketplace.json", json.dumps(doc))
                with self.assertRaisesRegex(ValueError, "unsupported plugin source"):
                    self.check()

    def test_non_regular_file_is_rejected(self) -> None:
        (self.remote / ".codex-plugin/ycc/link").symlink_to("skills")
        with self.assertRaisesRegex(ValueError, "non-regular"):
            self.check()

    def test_symlinked_payload_root_is_rejected(self) -> None:
        payload = self.remote / ".codex-plugin/ycc-mcp"
        payload.rename(self.remote / "elsewhere")
        payload.symlink_to("../elsewhere")
        with self.assertRaisesRegex(ValueError, "non-directory payload root"):
            self.check()


class CheckVersionTestCase(unittest.TestCase):
    def test_minimum_accepts_supported_versions(self) -> None:
        for version in ("codex-cli 0.160.0\n", "codex-cli 0.163.0\n", "codex-cli 1.0.0"):
            with self.subTest(version=version):
                codex_native_smoke.check_version(version)

    def test_minimum_rejects_older_or_garbage(self) -> None:
        for version in ("codex-cli 0.159.9\n", "codex 0.160.0", "codex-cli 0.160", "garbage", ""):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, ">=0.160.0"):
                codex_native_smoke.check_version(version)

    def test_exact_accepts_only_that_version(self) -> None:
        codex_native_smoke.check_version("codex-cli 0.160.0\n", "0.160.0")
        for version in ("codex-cli 0.163.0\n", "codex-cli 0.159.9\n", "garbage"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "Codex 0.160.0 required"):
                codex_native_smoke.check_version(version, "0.160.0")


if __name__ == "__main__":
    unittest.main()
