#!/usr/bin/env python3
"""Critical native-export boundary tests; run directly with Python's unittest."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import generate_codex_plugin as generator
from generate_codex_common import SOURCE_MCP_PATH
from generate_codex_mcp import CODEX_MCP_PATH, build_codex_mcp_config
from package_model import load_package_model

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts/generate_codex_plugin.py"
SKILLS_ROOT = Path(".codex-plugin/ycc")
MCP_ROOT = Path(".codex-plugin/ycc-mcp")
CATALOG = Path(".agents/plugins/marketplace.json")


class NativeExportTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.dest = self.tmp / "export"

    def cli(self, dest: Path, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--native-output", str(dest), *flags],
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def snapshot(root: Path) -> dict[Path, bytes]:
        return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    @staticmethod
    def json_at(root: Path, rel: Path) -> dict:
        return json.loads((root / rel).read_text(encoding="utf-8"))

    def test_native_tree_ownership_credentials_and_dormant_parity(self) -> None:
        with patch.dict(os.environ, {"XERO_CLIENT_ID": "SENTINEL"}):
            inventory = generator.generate_native_tree(self.dest)
        snapshot = self.snapshot(self.dest)
        self.assertEqual(set(snapshot), inventory)
        skills = self.json_at(self.dest, SKILLS_ROOT / ".codex-plugin/plugin.json")
        mcp = self.json_at(self.dest, MCP_ROOT / ".codex-plugin/plugin.json")
        version = json.loads((REPO_ROOT / load_package_model().version_source).read_text())["version"]
        self.assertEqual((skills["name"], skills["version"], skills["skills"]), ("ycc", version, "./skills/"))
        self.assertNotIn("mcpServers", skills)
        self.assertFalse((self.dest / SKILLS_ROOT / ".mcp.json").exists())
        self.assertTrue((self.dest / SKILLS_ROOT / "skills/plan/SKILL.md").is_file())
        self.assertTrue((self.dest / SKILLS_ROOT / "shared/scripts").is_dir())
        self.assertEqual((mcp["name"], mcp["version"], mcp["mcpServers"]), ("ycc-mcp", version, "./.mcp.json"))
        self.assertNotIn("skills", mcp)
        self.assertFalse((self.dest / MCP_ROOT / "skills").exists())
        self.assertFalse((self.dest / ".codex-plugin/ycc-hooks").exists())
        for manifest in (skills, mcp):
            self.assertNotIn("hooks", manifest)
            self.assertNotIn("listed", manifest)
        payload = self.json_at(self.dest, MCP_ROOT / ".mcp.json")
        self.assertEqual(payload, {"mcpServers": build_codex_mcp_config()["mcp_servers"]})
        self.assertNotIn("${", json.dumps(payload))
        self.assertIn("XERO_CLIENT_ID", payload["mcpServers"]["xero"]["env_vars"])
        for content in snapshot.values():
            self.assertNotIn(b"SENTINEL", content)
        catalog = self.json_at(self.dest, CATALOG)
        self.assertEqual(catalog["name"], "ycc")
        self.assertEqual([entry["name"] for entry in catalog["plugins"]], ["ycc", "ycc-mcp"])
        for entry in catalog["plugins"]:
            self.assertEqual(entry["source"], {"source": "local", "path": f'./.codex-plugin/{entry["name"]}'})
            self.assertEqual(entry["policy"], {"installation": "AVAILABLE", "authentication": "ON_INSTALL"})
            self.assertEqual(entry["category"], "Productivity")
            self.assertNotIn("listed", entry)
        legacy = self.tmp / "legacy"
        legacy_inventory = generator.write_all(legacy, dry_run=False)
        self.assertEqual(len(legacy_inventory), 6)
        for rel in (MCP_ROOT / ".codex-plugin/plugin.json", MCP_ROOT / ".mcp.json"):
            self.assertEqual((legacy / rel).read_bytes(), (self.dest / rel).read_bytes())
        self.assertEqual(self.json_at(legacy, CATALOG), generator.build_repo_marketplace())

    def test_catalog_filtering_and_unsupported_native_components(self) -> None:
        model = load_package_model()
        self.assertEqual(generator.build_native_marketplace(model.packages)["plugins"], [])
        self.assertEqual(len(generator.build_native_marketplace(model.packages, include_unlisted=True)["plugins"]), 2)
        hooks = next(package for package in model.packages if package.key == "ycc-hooks")
        runtimes = tuple(
            replace(entry, status="included") if entry.runtime == "codex" else entry for entry in hooks.runtimes
        )
        unsupported = replace(hooks, runtimes=runtimes)
        broken = replace(model, packages=model.packages + (unsupported,))
        with patch.object(generator, "load_package_model", return_value=broken):
            with self.assertRaisesRegex(ValueError, "unsupported.*ycc-hooks"):
                generator.generate_native_tree(self.dest)
        self.assertFalse(self.dest.exists())
        with self.assertRaisesRegex(ValueError, "unsupported.*ycc-hooks"):
            generator.build_native_marketplace((unsupported,))

    def test_missing_native_version_fails_before_writes(self) -> None:
        source = self.tmp / "version.json"
        source.write_text('{"name": "ycc"}\n', encoding="utf-8")
        model = replace(load_package_model(), version_source=str(source))
        with patch.object(generator, "load_package_model", return_value=model):
            with self.assertRaisesRegex(ValueError, "missing.*version"):
                generator.generate_native_tree(self.dest)
        self.assertFalse(self.dest.exists())

    def test_rerun_prunes_owned_extras_and_preserves_neighbors(self) -> None:
        generator.generate_native_tree(self.dest)
        extras = (
            SKILLS_ROOT / ".mcp.json",
            SKILLS_ROOT / "skills/orphan/SKILL.md",
            SKILLS_ROOT / "hooks/hooks.json",
            MCP_ROOT / "skills/orphan/SKILL.md",
        )
        neighbors = (Path("keep.txt"), Path(".codex-plugin/other/keep.txt"), Path(".agents/plugins/other.json"))
        for rel in extras + neighbors:
            path = self.dest / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep or prune\n")
        inventory = generator.generate_native_tree(self.dest)
        for rel in extras:
            self.assertFalse((self.dest / rel).exists())
        self.assertFalse((self.dest / SKILLS_ROOT / "skills/orphan").exists())
        self.assertFalse((self.dest / SKILLS_ROOT / "hooks").exists())
        for rel in neighbors:
            self.assertEqual((self.dest / rel).read_bytes(), b"keep or prune\n")
        self.assertEqual(set(self.snapshot(self.dest)), inventory | set(neighbors))

    def test_native_check_detects_drift_missing_and_stale_without_writes(self) -> None:
        generator.generate_native_tree(self.dest)
        result = self.cli(self.dest, "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = self.dest / SKILLS_ROOT / ".codex-plugin/plugin.json"
        changed.write_text("drift\n", encoding="utf-8")
        (self.dest / MCP_ROOT / ".mcp.json").unlink()
        stale = self.dest / SKILLS_ROOT / ".mcp.json"
        stale.write_text("stale\n", encoding="utf-8")
        before = self.snapshot(self.dest)
        result = self.cli(self.dest, "--check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("drift:", result.stderr)
        self.assertIn("missing", result.stderr)
        self.assertIn("extra in output:", result.stderr)
        self.assertEqual(self.snapshot(self.dest), before)
        missing = self.tmp / "missing"
        result = self.cli(missing, "--check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("missing", result.stderr)
        self.assertFalse(missing.exists())

    def test_dry_run_creates_nothing_and_modes_are_exclusive(self) -> None:
        result = self.cli(self.dest, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would write", result.stdout)
        self.assertFalse(self.dest.exists())
        with contextlib.redirect_stdout(io.StringIO()):
            inventory = generator.generate_native_tree(self.dest, dry_run=True)
        self.assertIn(CATALOG, inventory)
        self.assertFalse(self.dest.exists())
        result = self.cli(self.dest, "--dry-run", "--check")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.dest.exists())

    def test_rejects_unsafe_destinations_in_all_modes(self) -> None:
        alias = self.tmp / "repo-alias"
        alias.symlink_to(REPO_ROOT, target_is_directory=True)
        regular_file = self.tmp / "regular-file"
        regular_file.write_bytes(b"untouched\n")
        repo_subdir = REPO_ROOT / "native-export-should-not-exist"
        self.assertFalse(repo_subdir.exists())
        for dest in (Path("/"), REPO_ROOT, repo_subdir, REPO_ROOT.parent, alias, regular_file):
            for flags in ((), ("--check",), ("--dry-run",)):
                with self.subTest(dest=dest, flags=flags):
                    result = self.cli(dest, *flags)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(repo_subdir.exists())
        self.assertEqual(regular_file.read_bytes(), b"untouched\n")

    def test_rejects_all_managed_symlinks_without_mutation(self) -> None:
        target = self.tmp / "outside"
        target.mkdir()
        (target / "keep").write_bytes(b"untouched\n")
        managed = (
            Path(".agents"),
            Path(".agents/plugins"),
            CATALOG,
            Path(".codex-plugin"),
            SKILLS_ROOT,
            MCP_ROOT,
            SKILLS_ROOT / "skills/nested-link",
            MCP_ROOT / "nested-link",
        )
        for index, rel in enumerate(managed):
            dest = self.tmp / f"symlink-case-{index}"
            link = dest / rel
            link.parent.mkdir(parents=True)
            link.symlink_to(target, target_is_directory=True)
            before = self.snapshot(dest)
            for flags in ((), ("--check",), ("--dry-run",)):
                with self.subTest(rel=rel, flags=flags):
                    result = self.cli(dest, *flags)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("symlink", result.stderr)
                    self.assertEqual(self.snapshot(dest), before)
                    self.assertTrue(link.is_symlink())
            self.assertEqual(self.snapshot(target), {Path("keep"): b"untouched\n"})

    def test_excluded_native_roots_are_removed_including_empty_roots(self) -> None:
        generator.generate_native_tree(self.dest)
        hooks = self.dest / ".codex-plugin/ycc-hooks"
        neighbor = self.dest / ".codex-plugin/foreign/keep"
        neighbor.parent.mkdir(parents=True)
        neighbor.write_bytes(b"neighbor\n")
        for populated in (False, True):
            with self.subTest(populated=populated):
                hooks.mkdir()
                if populated:
                    (hooks / "hooks.json").write_bytes(b"stale hooks\n")
                before = self.snapshot(self.dest)
                result = self.cli(self.dest, "--check")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("extra in output: .codex-plugin/ycc-hooks", result.stderr)
                self.assertEqual(self.snapshot(self.dest), before)
                dry_run = self.cli(self.dest, "--dry-run")
                self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
                self.assertIn("Would remove .codex-plugin/ycc-hooks", dry_run.stdout)
                self.assertTrue(hooks.exists())
                generator.generate_native_tree(self.dest)
                self.assertFalse(hooks.exists())
                self.assertEqual(neighbor.read_bytes(), b"neighbor\n")

    def test_new_native_package_symlink_is_rejected_before_writes(self) -> None:
        model = load_package_model()
        mcp = next(package for package in model.packages if package.key == "ycc-mcp")
        added = replace(mcp, key="ycc-agents")
        model = replace(model, packages=model.packages + (added,))
        target = self.tmp / "outside"
        target.mkdir()
        (target / "keep").write_bytes(b"untouched\n")
        link = self.dest / ".codex-plugin/ycc-agents"
        link.parent.mkdir(parents=True)
        link.symlink_to(target, target_is_directory=True)
        before = self.snapshot(self.dest)
        with patch.object(generator, "load_package_model", return_value=model):
            for dry_run in (False, True):
                with self.assertRaisesRegex(ValueError, "symlink.*ycc-agents"):
                    generator.generate_native_tree(self.dest, dry_run=dry_run)
            with self.assertRaisesRegex(ValueError, "symlink.*ycc-agents"):
                generator.run_native_check(self.dest)
        self.assertEqual(self.snapshot(self.dest), before)
        self.assertEqual(self.snapshot(target), {Path("keep"): b"untouched\n"})

    def test_removed_mcp_selection_is_pruned_in_native_and_default_profiles(self) -> None:
        model = load_package_model()
        packages = tuple(
            (
                replace(
                    package,
                    runtimes=tuple(
                        replace(entry, status="excluded") if entry.runtime == "codex" else entry
                        for entry in package.runtimes
                    ),
                )
                if package.key == "ycc-mcp"
                else package
            )
            for package in model.packages
        )
        excluded_model = replace(model, packages=packages)
        generator.generate_native_tree(self.dest)
        legacy = self.tmp / "legacy"
        generator.write_all(legacy, dry_run=False)
        keep = legacy / SKILLS_ROOT / "skills/keep"
        keep.parent.mkdir(parents=True)
        keep.write_bytes(b"legacy skills\n")
        legacy_before = self.snapshot(legacy / SKILLS_ROOT)
        with patch.object(generator, "load_package_model", return_value=excluded_model):
            before = self.snapshot(self.dest)
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(generator.run_native_check(self.dest), 1)
            self.assertIn("extra in output: .codex-plugin/ycc-mcp", errors.getvalue())
            self.assertEqual(self.snapshot(self.dest), before)
            generator.generate_native_tree(self.dest)
            self.assertFalse((self.dest / MCP_ROOT).exists())
            for populated in (True, False):
                with self.subTest(populated=populated):
                    if not populated:
                        (legacy / MCP_ROOT).mkdir()
                    with contextlib.redirect_stderr(io.StringIO()) as errors:
                        self.assertEqual(generator.run_check(legacy), 1)
                    self.assertIn("extra in output: .codex-plugin/ycc-mcp", errors.getvalue())
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        generator.write_all(legacy, dry_run=True)
                    self.assertIn("Would remove .codex-plugin/ycc-mcp", output.getvalue())
                    self.assertTrue((legacy / MCP_ROOT).exists())
                    generator.write_all(legacy, dry_run=False)
                    self.assertFalse((legacy / MCP_ROOT).exists())
                    self.assertEqual(self.snapshot(legacy / SKILLS_ROOT), legacy_before)

    def test_default_rejects_managed_symlinks_without_mutation(self) -> None:
        target = self.tmp / "outside"
        target.mkdir()
        (target / "sentinel").write_bytes(b"outside sentinel\n")
        paths = (
            MCP_ROOT,
            MCP_ROOT / "nested",
            Path(".codex-plugin"),
            Path(".codex-plugin/config"),
            Path(".codex-plugin/config/mcp-servers.json"),
            SKILLS_ROOT / ".codex-plugin",
            SKILLS_ROOT / ".mcp.json",
            Path(".agents"),
            Path(".agents/plugins"),
            CATALOG,
        )
        for index, rel in enumerate(paths):
            dest = self.tmp / f"default-symlink-{index}"
            link = dest / rel
            link.parent.mkdir(parents=True)
            link.symlink_to(target, target_is_directory=True)
            before = self.snapshot(dest)
            for dry_run in (False, True):
                with self.subTest(rel=rel, dry_run=dry_run):
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        generator.write_all(dest, dry_run=dry_run)
            with self.assertRaisesRegex(ValueError, "symlink"):
                generator.run_check(dest)
            self.assertEqual(self.snapshot(dest), before)
            self.assertEqual(self.snapshot(target), {Path("sentinel"): b"outside sentinel\n"})

    def test_regular_file_package_roots_have_explicit_lifecycle(self) -> None:
        for native in (False, True):
            dest = self.tmp / f"regular-roots-{native}"
            root = dest / MCP_ROOT
            root.parent.mkdir(parents=True)
            root.write_bytes(b"selected root is a file\n")
            for dry_run in (False, True):
                with self.assertRaisesRegex(ValueError, "package root.*directory"):
                    if native:
                        generator.generate_native_tree(dest, dry_run=dry_run)
                    else:
                        generator.write_all(dest, dry_run=dry_run)
            self.assertEqual(self.snapshot(dest), {MCP_ROOT: b"selected root is a file\n"})
            root.unlink()
            excluded = dest / ".codex-plugin/ycc-hooks"
            excluded.write_bytes(b"stale excluded root\n")
            if native:
                generator.generate_native_tree(dest)
                excluded.write_bytes(b"stale excluded root\n")
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(generator.run_native_check(dest), 1)
                generator.generate_native_tree(dest)
            else:
                generator.write_all(dest, dry_run=False)
                excluded.write_bytes(b"stale excluded root\n")
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(generator.run_check(dest), 1)
                generator.write_all(dest, dry_run=False)
            self.assertIn("ycc-hooks", errors.getvalue())
            self.assertFalse(excluded.exists())

    def test_legacy_builders_and_bytes_unchanged(self) -> None:
        def serialized(payload: dict) -> bytes:
            return (json.dumps(payload, indent=2) + "\n").encode("utf-8")

        self.assertEqual(
            serialized(generator.build_plugin_manifest()),
            (REPO_ROOT / SKILLS_ROOT / ".codex-plugin/plugin.json").read_bytes(),
        )
        self.assertEqual(serialized(generator.build_repo_marketplace()), (REPO_ROOT / CATALOG).read_bytes())
        generator.write_all(self.dest, dry_run=False)
        legacy_files = (SKILLS_ROOT / ".codex-plugin/plugin.json", SKILLS_ROOT / ".mcp.json", CATALOG)
        for rel in legacy_files + (CODEX_MCP_PATH.relative_to(REPO_ROOT),):
            self.assertEqual((self.dest / rel).read_bytes(), (REPO_ROOT / rel).read_bytes())
        self.assertEqual((self.dest / SKILLS_ROOT / ".mcp.json").read_bytes(), SOURCE_MCP_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
