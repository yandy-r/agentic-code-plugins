#!/usr/bin/env python3
"""Critical tests for the Cursor-native package generator."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_cursor_packages as generator  # noqa: E402
from package_model import REPO_ROOT, PackageModel, load_package_model  # noqa: E402

SCRIPT = REPO_ROOT / "scripts/generate_cursor_packages.py"

YCC_ROOT = Path("packages/cursor/ycc")
RULES_ROOT = Path("packages/cursor/ycc-rules")
MCP_ROOT = Path("packages/cursor/ycc-mcp")
HOOKS_ROOT = Path("packages/cursor/ycc-hooks")
FALLBACK_ROOT = Path("packages/cursor/installer-fallback")
MANIFEST = Path(".cursor-plugin/plugin.json")
LEGACY_ROOT = Path(".cursor-plugin")


def with_cursor_runtime(model: PackageModel, key: str, **changes: object) -> PackageModel:
    def runtimes_of(entry):
        return replace(entry, **changes) if entry.runtime == "cursor" else entry

    packages = tuple(
        (
            replace(package, runtimes=tuple(runtimes_of(entry) for entry in package.runtimes))
            if package.key == key
            else package
        )
        for package in model.packages
    )
    return PackageModel(model.schema_version, model.version_source, packages)


def unlisted(model: PackageModel) -> PackageModel:
    """Return a copy of the model with every runtime explicitly unlisted."""
    packages = tuple(
        replace(package, runtimes=tuple(replace(entry, listed=False) for entry in package.runtimes))
        for package in model.packages
    )
    return PackageModel(model.schema_version, model.version_source, packages)


class CursorNativePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.dest = self.tmp / "repo"
        # Explicit unlisted fixture: independent of which real packages are currently listed.
        self.model = unlisted(load_package_model())
        self.patch_generator("load_package_model", lambda: self.model)

    def snapshot(self, root: Path) -> dict[Path, bytes]:
        return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    @staticmethod
    def json_at(root: Path, rel: Path) -> dict:
        return json.loads((root / rel).read_text(encoding="utf-8"))

    def patch_generator(self, name: str, value: object) -> None:
        patcher = patch.object(generator, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_all_modes_raise(self, dest: Path) -> None:
        actions: tuple[Callable[[], object], ...] = (
            lambda: generator.write_all(dest),
            lambda: generator.write_all(dest, dry_run=True),
            lambda: generator.run_check(dest),
        )
        for action in actions:
            with self.assertRaises(ValueError):
                action()

    def test_selected_cursor_packages_generate_without_any_root_marketplace(self) -> None:
        inventory = generator.write_all(self.dest)
        roots = {Path(*rel.parts[:3]) for rel in inventory}
        self.assertEqual(roots, {YCC_ROOT, RULES_ROOT, MCP_ROOT, HOOKS_ROOT, FALLBACK_ROOT})
        self.assertFalse((self.dest / LEGACY_ROOT / "marketplace.json").exists())
        self.assertFalse((self.dest / LEGACY_ROOT).exists())
        for key, _runtime in (
            ("ycc", {"skills", "agents", "commands", "shared"}),
            ("ycc-rules", {"rules"}),
            ("ycc-mcp", {"mcp"}),
            ("ycc-hooks", {"hooks"}),
        ):
            manifest = self.json_at(self.dest, Path(f"packages/cursor/{key}") / MANIFEST)
            self.assertEqual(manifest["name"], key)
            self.assertEqual(manifest["minClientVersions"], {"cursor": generator.MIN_CURSOR_VERSION})
            self.assertEqual(manifest["version"], generator.native_version(self.model))
            for forbidden in ("listed", "status", "mechanism", "components", "runtimes", "shared"):
                self.assertNotIn(forbidden, manifest)

    def test_skills_agents_rules_and_commands_land_in_the_right_package_roots(self) -> None:
        generator.write_all(self.dest)
        self.assertTrue((self.dest / YCC_ROOT / "skills" / "init" / "SKILL.md").is_file())
        self.assertTrue((self.dest / YCC_ROOT / "skills" / "_shared" / "scripts" / "rules_pointer.py").is_file())
        self.assertTrue((self.dest / YCC_ROOT / "agents" / "api-docs-expert.md").is_file())
        self.assertTrue((self.dest / RULES_ROOT / "rules" / "README.md").is_file())
        self.assertTrue(any((self.dest / RULES_ROOT / "rules").rglob("*.mdc")))
        commands = sorted(path.name for path in (self.dest / YCC_ROOT / "commands").glob("*.md"))
        self.assertIn("init.md", commands)
        self.assertNotIn("_shared.md", commands)
        init = (self.dest / YCC_ROOT / "commands" / "init.md").read_text(encoding="utf-8")
        self.assertIn("name: init", init)
        self.assertIn("${CURSOR_PLUGIN_ROOT}/skills/init/SKILL.md", init)
        self.assertIn("$ARGUMENTS", init)

    def test_native_plugin_root_references_resolve_within_each_package(self) -> None:
        generator.write_all(self.dest)
        from validate_cursor_native import resource_errors

        for key in ("ycc", "ycc-rules", "ycc-mcp", "ycc-hooks"):
            self.assertEqual(resource_errors(self.dest / "packages/cursor" / key), [])
        broken = self.dest / YCC_ROOT / "skills/init/SKILL.md"
        broken.write_text(broken.read_text() + "\n${CURSOR_PLUGIN_ROOT}/skills/missing/SKILL.md\n", encoding="utf-8")
        self.assertTrue(any("missing/SKILL.md" in error for error in resource_errors(self.dest / YCC_ROOT)))

    def test_resource_audit_resolves_literal_prefix_before_globs(self) -> None:
        from validate_cursor_native import resource_errors

        root = self.tmp / "package"
        (root / "skills/x/scripts").mkdir(parents=True)
        (root / "skills/x/run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        broken = root / "skills/x/SKILL.md"
        good = (
            "${CURSOR_PLUGIN_ROOT}/skills/x/scripts/*.sh\n"
            "${CURSOR_PLUGIN_ROOT}/skills/x/scripts/{a,b}.sh\n"
            "${CURSOR_PLUGIN_ROOT}/skills/x/<kebab-name>\n"
            "${CURSOR_PLUGIN_ROOT}/skills/x/{{NAME}}\n"
            "${CURSOR_PLUGIN_ROOT}/skills/x/run.sh\n"
        )
        broken.write_text(good, encoding="utf-8")
        self.assertEqual(resource_errors(root), [])
        broken.write_text("${CURSOR_PLUGIN_ROOT}/skills/x/missingdir/*.sh\n", encoding="utf-8")
        self.assertTrue(resource_errors(root))
        broken.write_text("${CURSOR_PLUGIN_ROOT}/../../outside/agent.md\n", encoding="utf-8")
        self.assertTrue(resource_errors(root))
        broken.write_text(good, encoding="utf-8")
        quoted = root / "hooks.json"
        quoted.write_text(
            json.dumps({"command": 'bash "${CURSOR_PLUGIN_ROOT}/skills/x/run.sh" session'}), encoding="utf-8"
        )
        self.assertEqual(resource_errors(root), [])

    def test_fallback_config_is_byte_identical_to_the_canonical_source(self) -> None:
        generator.write_all(self.dest)
        generated = self.dest / FALLBACK_ROOT / "config/cli-config.json"
        source = REPO_ROOT / generator.SOURCE_CLI_CONFIG_PATH
        self.assertEqual(generated.read_bytes(), source.read_bytes())
        self.assertFalse(generated.stat().st_mode & 0o100)

    def test_mcp_env_placeholders_are_preserved_and_declared_never_materialized(self) -> None:
        with patch.dict(os.environ, {"XERO_CLIENT_ID": "SENTINEL", "XERO_CLIENT_SECRET": "SENTINEL"}):
            generator.write_all(self.dest)
        for content in self.snapshot(self.dest).values():
            self.assertNotIn(b"SENTINEL", content)
        config = self.json_at(self.dest, MCP_ROOT / "mcp.json")
        self.assertEqual(config["mcpServers"]["xero"]["env"]["XERO_CLIENT_ID"], "${XERO_CLIENT_ID}")
        manifest = self.json_at(self.dest, MCP_ROOT / MANIFEST)
        self.assertEqual(manifest["mcpServers"], "./mcp.json")
        self.assertEqual(
            set(manifest["variables"]["properties"]),
            {"XERO_CLIENT_ID", "XERO_CLIENT_SECRET"},
        )

    def test_credential_literals_fail_before_any_write_but_placeholders_pass(self) -> None:
        literal = {"env": {"API_TOKEN": "literal"}}
        cases = {
            "env literal": literal,
            "authorization literal": {"headers": {"Authorization": "Bearer literal-secret"}},
            "authorization mixed": {"headers": {"Authorization": "Bearer lit${TOKEN}"}},
            "authorization suffix": {"headers": {"Authorization": "Bearer ${TOKEN}-literal"}},
            "authorization unschemed literal": {"headers": {"Authorization": "literal-secret"}},
            "env mixed": {"env": {"API_TOKEN": "prefix-${TOKEN}"}},
            "two placeholders": {"env": {"API_TOKEN": "${A}${B}"}},
        }
        for label, server in cases.items():
            with self.subTest(label=label):
                source = self.tmp / f"{label.replace(' ', '-')}.json"
                source.write_text(json.dumps({"mcpServers": {"svc": {"type": "http", **server}}}), encoding="utf-8")
                self.patch_generator("SOURCE_MCP_PATH", source)
                self.assert_all_modes_raise(self.dest)
                self.assertFalse(self.dest.exists())
        for label, server in {
            "bearer placeholder": {"headers": {"Authorization": "Bearer ${TOKEN}"}},
            "bare placeholder": {"env": {"API_TOKEN": "${TOKEN}"}},
        }.items():
            with self.subTest(label=label):
                config = {"mcpServers": {"svc": {"type": "http", "url": "https://example.invalid", **server}}}
                generator.audit_no_secret_literals(config, label)

    def test_native_init_uses_package_local_agents_and_mcp_without_home_dependencies(self) -> None:
        generator.write_all(self.dest)
        from validate_cursor_native import resource_errors

        root = self.dest / YCC_ROOT
        self.assertEqual(resource_errors(root), [])
        skill = (root / "skills/init/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("${HOME}/.cursor/agents", skill)
        self.assertNotIn("mcp-library", skill)
        self.assertIn("${CURSOR_PLUGIN_ROOT}/agents/", skill)
        self.assertIn("${CURSOR_PLUGIN_ROOT}/resources/mcp/select-mcp.py", skill)
        catalog = (root / "skills/init/scripts/generate-agent-catalog.sh").read_text(encoding="utf-8")
        self.assertNotIn("${HOME}/.cursor/agents", catalog)
        self.assertTrue((root / "resources/mcp/select-mcp.py").stat().st_mode & 0o100)
        bundled = (root / "resources/mcp/mcp.json").read_bytes()
        self.assertEqual(bundled, (REPO_ROOT / generator.SOURCE_MCP_PATH).read_bytes())
        # A planted installer-only home dependency is caught; user state paths are not.
        planted = root / "skills/init/SKILL.md"
        planted.write_text(skill + "\n${HOME}/.cursor/agents/x.md\n", encoding="utf-8")
        self.assertTrue(any("installer-only" in error for error in resource_errors(root)))
        planted.write_text(skill + "\n~/.cursor/session-data/s.json\n.cursor/mcp.json\n", encoding="utf-8")
        self.assertEqual(resource_errors(root), [])

    def test_mcp_helper_merges_selected_servers_without_dropping_user_config(self) -> None:
        generator.write_all(self.dest)
        helper = self.dest / YCC_ROOT / "resources/mcp/select-mcp.py"
        project = self.tmp / "project/.cursor/mcp.json"
        project.parent.mkdir(parents=True)
        project.write_text(json.dumps({"x": 1, "mcpServers": {"mine": {"url": "u"}}}), encoding="utf-8")
        run = lambda *args: subprocess.run(  # noqa: E731
            [sys.executable, str(helper), "--destination", str(project), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(run("--dry-run", "context7").returncode, 0)
        self.assertEqual(json.loads(project.read_text())["mcpServers"], {"mine": {"url": "u"}})
        self.assertEqual(run("context7", "xero").returncode, 0)
        merged = json.loads(project.read_text())
        self.assertEqual(merged["x"], 1)
        self.assertEqual(merged["mcpServers"]["mine"], {"url": "u"})
        self.assertEqual(merged["mcpServers"]["xero"]["env"]["XERO_CLIENT_ID"], "${env:XERO_CLIENT_ID}")
        self.assertEqual(merged["mcpServers"]["xero"]["env"]["XERO_CLIENT_SECRET"], "${env:XERO_CLIENT_SECRET}")
        self.assertEqual(run("context7", "xero").returncode, 0)
        self.assertEqual(json.loads(project.read_text()), merged)
        project.write_text(json.dumps({"mcpServers": {"context7": {"url": "other"}}}), encoding="utf-8")
        self.assertNotEqual(run("context7").returncode, 0)
        self.assertEqual(json.loads(project.read_text())["mcpServers"]["context7"], {"url": "other"})
        self.assertEqual(run("--force", "context7").returncode, 0)
        self.assertNotEqual(run("nope").returncode, 0)

    def test_standalone_translation_rewrites_bare_placeholders_without_materializing(self) -> None:
        helper = self.tmp / "select-mcp.py"
        helper.write_bytes((REPO_ROOT / "ycc/settings/cursor/select-mcp.py").read_bytes())
        namespace = {"__file__": str(helper)}
        exec(compile(helper.read_bytes(), str(helper), "exec"), namespace)
        self.assertEqual(
            namespace["standalone"]({"env": {"A": "${A}", "B": ["x${B}", 1], "C": "${env:C}"}}),
            {"env": {"A": "${env:A}", "B": ["x${env:B}", 1], "C": "${env:C}"}},
        )

    def test_installer_projection_restores_the_file_copy_init_bytes(self) -> None:
        import generate_cursor_skills as skills
        from cursor_native_resources import INIT_FILES, restore_installer_init

        generator.write_all(self.dest)
        staged = self.tmp / "skills"
        staged.mkdir()
        init = staged / "init"
        init.mkdir()
        for rel in INIT_FILES:
            target = staged / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.dest / YCC_ROOT / "skills" / rel).read_bytes())
        restore_installer_init(staged)
        for rel in INIT_FILES:
            source = (REPO_ROOT / "ycc/skills" / rel).read_text(encoding="utf-8")
            self.assertEqual((staged / rel).read_text(encoding="utf-8"), skills.transform_text_content(source, rel))

    def test_hooks_registers_only_session_start_and_preserves_script_mode(self) -> None:
        generator.write_all(self.dest)
        hooks = self.json_at(self.dest, HOOKS_ROOT / "hooks/hooks.json")
        self.assertEqual(hooks["version"], 1)
        self.assertEqual(set(hooks["hooks"]), {"sessionStart"})
        self.assertNotIn("WorktreeCreate", hooks["hooks"])
        self.assertNotIn("SessionStart", hooks["hooks"])
        script = self.dest / HOOKS_ROOT / "hooks/herdr-session-start.sh"
        self.assertEqual(script.read_bytes(), (REPO_ROOT / generator.SOURCE_HOOK_PATH).read_bytes())
        self.assertTrue(script.stat().st_mode & 0o100)

    def test_unsupported_hook_event_fails_before_writes(self) -> None:
        hooks_path = self.tmp / "hooks.json"
        cases = {
            "claude event": {"version": 1, "hooks": {"SessionStart": [{"command": "x"}]}},
            "worktree event": {
                "version": 1,
                "hooks": {"sessionStart": [{"command": "x"}], "WorktreeCreate": [{"command": "x"}]},
            },
            "bad shape": {"version": 1, "hooks": {"sessionStart": {}}},
        }
        for label, hooks in cases.items():
            with self.subTest(label=label):
                hooks_path.write_text(json.dumps(hooks), encoding="utf-8")
                self.patch_generator("SOURCE_HOOKS_PATH", hooks_path)
                self.assert_all_modes_raise(self.dest)
                self.assertFalse(self.dest.exists())

    def test_unsupported_component_sets_fail_before_writes(self) -> None:
        cases = {
            "combined components": with_cursor_runtime(self.model, "ycc-mcp", components=("mcp", "hooks")),
            "unknown component": with_cursor_runtime(self.model, "ycc-hooks", components=("skills",)),
            "empty native": with_cursor_runtime(self.model, "ycc-rules", components=()),
        }
        for label, broken in cases.items():
            with self.subTest(label=label), patch.object(generator, "load_package_model", return_value=broken):
                self.assert_all_modes_raise(self.dest)
                self.assertFalse(self.dest.exists())

    def test_listing_controls_catalog_not_payloads_and_unlisting_prunes_catalog(self) -> None:
        generator.write_all(self.dest)
        unlisted_payloads = self.snapshot(self.dest)
        listed = with_cursor_runtime(with_cursor_runtime(self.model, "ycc-mcp", listed=True), "ycc-hooks", listed=True)
        with patch.object(generator, "load_package_model", return_value=listed):
            inventory = generator.write_all(self.dest)
            self.assertEqual(generator.run_check(self.dest), 0)
        self.assertIn(MCP_ROOT / MANIFEST, inventory)
        self.assertIn(HOOKS_ROOT / MANIFEST, inventory)
        self.assertIn(generator.MARKETPLACE_PATH, inventory)
        marketplace = self.json_at(self.dest, generator.MARKETPLACE_PATH)
        self.assertEqual(
            marketplace,
            {
                "name": "ycc",
                "plugins": [
                    {"name": "ycc-mcp", "source": "./packages/cursor/ycc-mcp"},
                    {"name": "ycc-hooks", "source": "./packages/cursor/ycc-hooks"},
                ],
            },
        )
        listed_payloads = self.snapshot(self.dest)
        del listed_payloads[generator.MARKETPLACE_PATH]
        self.assertEqual(listed_payloads, unlisted_payloads)
        neighbor = self.dest / LEGACY_ROOT / "keep.json"
        neighbor.write_bytes(b"keep\n")
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(generator.run_check(self.dest), 1)
        self.assertIn(f"extra in output: {generator.MARKETPLACE_PATH}", errors.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as actions:
            generator.write_all(self.dest, dry_run=True)
        self.assertIn(f"Would remove {generator.MARKETPLACE_PATH}", actions.getvalue())
        self.assertTrue((self.dest / generator.MARKETPLACE_PATH).is_file())
        deferred = with_cursor_runtime(self.model, "ycc-hooks", status="deferred")
        with patch.object(generator, "load_package_model", return_value=deferred):
            generator.write_all(self.dest)
        self.assertFalse((self.dest / HOOKS_ROOT).exists())
        self.assertFalse((self.dest / generator.MARKETPLACE_PATH).exists())
        self.assertEqual(neighbor.read_bytes(), b"keep\n")

    def test_full_marketplace_has_one_schema_valid_entry_per_native_directory(self) -> None:
        model = self.model
        for package in generator.native_packages(model.packages):
            model = with_cursor_runtime(model, package.key, listed=True)
        with patch.object(generator, "load_package_model", return_value=model):
            generator.write_all(self.dest)
        marketplace = self.json_at(self.dest, generator.MARKETPLACE_PATH)
        self.assertEqual(marketplace, generator.build_marketplace(model.packages))
        schema = generator.read_json(generator.SCHEMA_DIR / "marketplace.schema.json")
        self.assertEqual(list(generator.Draft7Validator(schema).iter_errors(marketplace)), [])
        entries = marketplace["plugins"]
        self.assertEqual({entry["name"] for entry in entries}, {"ycc", "ycc-rules", "ycc-mcp", "ycc-hooks"})
        self.assertEqual(len(entries), len({entry["source"] for entry in entries}))
        for entry in entries:
            self.assertEqual(entry["source"], f"./packages/cursor/{entry['name']}")
            self.assertTrue((self.dest / entry["source"] / MANIFEST).is_file())

    def test_marketplace_builder_ignores_ineligible_listed_rows(self) -> None:
        model = with_cursor_runtime(self.model, "ycc-hooks", listed=True, status="deferred")
        model = with_cursor_runtime(model, "installer-fallback", listed=True)
        self.assertIsNone(generator.build_marketplace(model.packages))
        self.assertIsNone(generator.build_marketplace(()))
        package = next(package for package in self.model.packages if package.key == "ycc-mcp")
        package = replace(
            package,
            key="Invalid_Name",
            runtimes=tuple(replace(row, listed=True) if row.runtime == "cursor" else row for row in package.runtimes),
        )
        with self.assertRaisesRegex(ValueError, "vendored Cursor schema"):
            generator.build_marketplace((package,))

    def test_listed_marketplace_check_reports_missing_and_stale_without_mutation(self) -> None:
        model = with_cursor_runtime(self.model, "ycc-mcp", listed=True)
        with patch.object(generator, "load_package_model", return_value=model):
            generator.write_all(self.dest)
            marketplace = self.dest / generator.MARKETPLACE_PATH
            marketplace.unlink()
            before = self.snapshot(self.dest)
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(generator.run_check(self.dest), 1)
            self.assertIn(f"missing file: {generator.MARKETPLACE_PATH}", errors.getvalue())
            self.assertEqual(self.snapshot(self.dest), before)
            marketplace.write_text(json.dumps({"name": "ycc", "plugins": []}), encoding="utf-8")
            before = self.snapshot(self.dest)
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(generator.run_check(self.dest), 1)
            self.assertIn(f"drift: {generator.MARKETPLACE_PATH}", errors.getvalue())
            self.assertEqual(self.snapshot(self.dest), before)
            generator.write_all(self.dest)
            self.assertEqual(
                self.json_at(self.dest, generator.MARKETPLACE_PATH), generator.build_marketplace(model.packages)
            )

    def test_missing_version_source_fails_before_any_write(self) -> None:
        version_source = self.tmp / "version.json"
        version_source.write_text(json.dumps({"version": ""}), encoding="utf-8")
        model = replace(self.model, version_source=str(version_source))
        with patch.object(generator, "load_package_model", return_value=model):
            self.assert_all_modes_raise(self.dest)
        self.assertFalse(self.dest.exists())

    def test_manifest_schema_violations_fail_before_any_write(self) -> None:
        author = {"name": "yandy-r", "email": "not-an-email"}
        with patch.object(generator, "manifest_author", return_value=author):
            self.assert_all_modes_raise(self.dest)
        self.assertFalse(self.dest.exists())

    def test_marketplace_schema_violations_fail_before_any_write(self) -> None:
        model = with_cursor_runtime(self.model, "ycc-mcp", listed=True)
        read_json = generator.read_json

        def schema_fixture(path: Path) -> object:
            if path.name == "marketplace.schema.json":
                return {"type": "object", "required": ["unsupported"]}
            return read_json(path)

        with (
            patch.object(generator, "load_package_model", return_value=model),
            patch.object(generator, "read_json", side_effect=schema_fixture),
        ):
            self.assert_all_modes_raise(self.dest)
        self.assertFalse(self.dest.exists())

    def test_managed_symlinks_are_rejected_without_mutation(self) -> None:
        target = self.tmp / "outside"
        target.mkdir()
        (target / "keep").write_bytes(b"untouched\n")
        managed = (Path("packages"), Path("packages/cursor"), MCP_ROOT, MCP_ROOT / "mcp.json", HOOKS_ROOT)
        for index, rel in enumerate(managed):
            with self.subTest(rel=rel):
                dest = self.tmp / f"symlink-case-{index}"
                link = dest / rel
                link.parent.mkdir(parents=True)
                link.symlink_to(target, target_is_directory=True)
                before = self.snapshot(dest)
                self.assert_all_modes_raise(dest)
                self.assertEqual(self.snapshot(dest), before)
                self.assertEqual(self.snapshot(target), {Path("keep"): b"untouched\n"})

    def test_marketplace_symlinks_are_rejected_in_listed_and_absent_states(self) -> None:
        target = self.tmp / "outside.json"
        target.write_bytes(b"untouched\n")
        listed = with_cursor_runtime(self.model, "ycc-mcp", listed=True)
        for index, model in enumerate((self.model, listed)):
            for dangling in (False, True):
                with self.subTest(listed=bool(index), dangling=dangling):
                    dest = self.tmp / f"marketplace-symlink-{index}-{dangling}"
                    link = dest / generator.MARKETPLACE_PATH
                    link.parent.mkdir(parents=True)
                    link.symlink_to(target if not dangling else self.tmp / "missing")
                    with patch.object(generator, "load_package_model", return_value=model):
                        self.assert_all_modes_raise(dest)
                    self.assertTrue(link.is_symlink())
                    self.assertFalse((dest / "packages").exists())
                    self.assertEqual(target.read_bytes(), b"untouched\n")

    def test_marketplace_parent_symlinks_and_directory_conflicts_are_rejected(self) -> None:
        target = self.tmp / "outside"
        target.mkdir()
        linked_dest = self.tmp / "linked-parent"
        linked_dest.mkdir()
        (linked_dest / LEGACY_ROOT).symlink_to(target, target_is_directory=True)
        self.assert_all_modes_raise(linked_dest)
        self.assertEqual(list(target.iterdir()), [])
        conflict_dest = self.tmp / "directory-conflict"
        (conflict_dest / generator.MARKETPLACE_PATH).mkdir(parents=True)
        self.assert_all_modes_raise(conflict_dest)
        self.assertFalse((conflict_dest / "packages").exists())

    def test_checked_in_tree_matches_the_real_manifest_listing_state(self) -> None:
        real = load_package_model()
        with patch.object(generator, "load_package_model", return_value=real):
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(generator.run_check(REPO_ROOT), 0, errors.getvalue())
            expected = generator.build_marketplace(real.packages)
            marketplace = REPO_ROOT / generator.MARKETPLACE_PATH
            if expected is None:
                self.assertFalse(marketplace.exists())
            else:
                self.assertEqual(json.loads(marketplace.read_text(encoding="utf-8")), expected)

    def test_legacy_payload_roots_are_retired_but_neighboring_files_survive(self) -> None:
        legacy_skills = self.dest / LEGACY_ROOT / "skills/stale"
        legacy_config = self.dest / LEGACY_ROOT / "config/cli-config.json"
        legacy_manifest_dir = self.dest / LEGACY_ROOT / "marketplace-stub"
        legacy_manifest_dir.parent.mkdir(parents=True)
        legacy_skills.mkdir(parents=True)
        (legacy_skills / "old.md").write_bytes(b"old\n")
        legacy_config.parent.mkdir(parents=True)
        legacy_config.write_bytes(b"old\n")
        legacy_manifest_dir.write_bytes(b"not a dir\n")
        generator.write_all(self.dest)
        self.assertFalse((self.dest / LEGACY_ROOT / "skills").exists())
        self.assertFalse((self.dest / LEGACY_ROOT / "config").exists())
        self.assertEqual((self.dest / LEGACY_ROOT / "marketplace-stub").read_bytes(), b"not a dir\n")

    def test_check_reports_missing_drift_extra_without_mutation(self) -> None:
        generator.write_all(self.dest)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(generator.run_check(self.dest), 0)
        (self.dest / MCP_ROOT / MANIFEST).write_text("drift\n", encoding="utf-8")
        (self.dest / HOOKS_ROOT / "hooks/hooks.json").unlink()
        (self.dest / RULES_ROOT / "rules/stale.mdc").write_bytes(b"stale\n")
        script = self.dest / HOOKS_ROOT / "hooks/herdr-session-start.sh"
        script.chmod(script.stat().st_mode & ~0o100)
        before = self.snapshot(self.dest)
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(generator.run_check(self.dest), 1)
        details = errors.getvalue()
        self.assertIn(f"missing file: {HOOKS_ROOT / 'hooks/hooks.json'}", details)
        self.assertIn(f"drift: {MCP_ROOT / MANIFEST}", details)
        self.assertIn(f"executable-bit drift: {HOOKS_ROOT / 'hooks/herdr-session-start.sh'}", details)
        self.assertIn(f"extra in output: {RULES_ROOT / 'rules/stale.mdc'}", details)
        self.assertEqual(self.snapshot(self.dest), before)

    def test_check_on_missing_destination_does_not_create_it(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(generator.run_check(self.dest), 1)
        self.assertIn("missing file", errors.getvalue())
        self.assertFalse(self.dest.exists())

    def test_dry_run_mutates_nothing_and_cli_modes_are_exclusive(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            inventory = generator.write_all(self.dest, dry_run=True)
        self.assertIn(f"Would write {MCP_ROOT / MANIFEST}", output.getvalue())
        self.assertFalse(self.dest.exists())
        self.assertIn(MCP_ROOT / MANIFEST, inventory)
        generator.write_all(self.dest)
        (self.dest / MCP_ROOT / "stale.json").write_bytes(b"stale\n")
        before = self.snapshot(self.dest)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            generator.write_all(self.dest, dry_run=True)
        self.assertIn(f"Would remove {MCP_ROOT / 'stale.json'}", output.getvalue())
        self.assertEqual(self.snapshot(self.dest), before)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run", "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
