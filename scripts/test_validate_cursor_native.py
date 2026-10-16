#!/usr/bin/env python3
"""Fixture tests for the native Cursor package validator (no CLI, no network)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_cursor_packages import MIN_CURSOR_VERSION  # noqa: E402
from package_model import Package, PackageModel, RuntimePackage, load_package_model  # noqa: E402
from validate_cursor_native import cursor_native_errors, main, resource_errors  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.2.3"
MARKETPLACE_ABSENCE_ERROR = ".cursor-plugin/marketplace.json must not exist before the listing flip"


def cursor_package(key: str, *components: str) -> Package:
    runtime = RuntimePackage(
        runtime="cursor",
        status="included",
        listed=False,
        mechanism="native",
        components=tuple(components),
        requires=(),
        target_release="v6.0.0",
        experimental=False,
        opt_in=False,
        evidence=(),
        gates=(),
        notes="",
    )
    return Package(key, "fixture package", "lockstep", (runtime,))


def fixture_model(*packages: Package) -> PackageModel:
    return PackageModel(1, "version.json", tuple(packages))


class CursorNativeValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.write_json(Path("version.json"), {"version": VERSION})

    def write_json(self, relative: Path, payload: Any) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def write_text(self, relative: Path, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def manifest(self, key: str, **changes: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": key,
            "version": VERSION,
            "description": "fixture plugin",
            "author": {"name": "fixture"},
            "minClientVersions": {"cursor": MIN_CURSOR_VERSION},
        }
        payload.update(changes)
        return payload

    def add_skills_package(self, **manifest_changes: Any) -> Package:
        self.write_json(
            Path("packages/cursor/ycc/.cursor-plugin/plugin.json"),
            self.manifest("ycc", **manifest_changes),
        )
        self.write_text(
            Path("packages/cursor/ycc/skills/demo/SKILL.md"),
            "Run ${CURSOR_PLUGIN_ROOT}/skills/demo/SKILL.md when requested.\n",
        )
        return cursor_package("ycc", "skills", "agents", "commands", "shared")

    def add_hooks_package(self, *, hooks: Any = None, executable: bool = True) -> Package:
        self.write_json(
            Path("packages/cursor/ycc-hooks/.cursor-plugin/plugin.json"),
            self.manifest("ycc-hooks"),
        )
        events = {"sessionStart": [{"command": 'bash "${CURSOR_PLUGIN_ROOT}/hooks/herdr-session-start.sh" session'}]}
        payload = events if hooks is None else hooks
        self.write_json(Path("packages/cursor/ycc-hooks/hooks/hooks.json"), {"version": 1, "hooks": payload})
        script = self.write_text(Path("packages/cursor/ycc-hooks/hooks/herdr-session-start.sh"), "#!/bin/sh\nexit 0\n")
        if executable:
            script.chmod(0o755)
        return cursor_package("ycc-hooks", "hooks")

    def add_mcp_package(self, *, mcp_text: str | None = None, **manifest_changes: Any) -> Package:
        changes: dict[str, Any] = {
            "variables": {"type": "object", "properties": {"TOKEN": {"type": "string"}}},
            "mcpServers": "./mcp.json",
        }
        changes.update(manifest_changes)
        self.write_json(Path("packages/cursor/ycc-mcp/.cursor-plugin/plugin.json"), self.manifest("ycc-mcp", **changes))
        text = mcp_text or json.dumps({"mcpServers": {"fixture": {"env": {"TOKEN": "${TOKEN}"}}}})
        self.write_text(Path("packages/cursor/ycc-mcp/mcp.json"), text)
        return cursor_package("ycc-mcp", "mcp")

    def assert_has_error(self, errors: list[str], expected: str) -> None:
        self.assertTrue(any(expected in error for error in errors), f"expected {expected!r} in {errors!r}")

    def test_valid_small_fixture_without_marketplace_is_clean(self) -> None:
        model = fixture_model(self.add_skills_package(), self.add_hooks_package(), self.add_mcp_package())

        errors = cursor_native_errors(self.root, model)

        self.assertEqual(errors, [])
        self.assertFalse((self.root / ".cursor-plugin/marketplace.json").exists())

    def test_existing_generated_checkout_is_consistent(self) -> None:
        # Native policy standalone: the checked-in generated tree must pass.
        self.assertEqual(cursor_native_errors(REPO_ROOT, load_package_model()), [])

    def test_plugin_schema_rejects_missing_name_and_extra_property(self) -> None:
        manifest = self.manifest("ycc")
        del manifest["name"]
        manifest["surprise"] = True
        self.write_json(Path("packages/cursor/ycc/.cursor-plugin/plugin.json"), manifest)
        self.write_text(Path("packages/cursor/ycc/skills/demo/SKILL.md"), "fixture\n")

        package = cursor_package("ycc", "skills", "agents", "commands", "shared")
        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assert_has_error(errors, "'name' is a required property")
        self.assert_has_error(errors, "Additional properties are not allowed")

    def test_plugin_schema_and_policy_reject_bad_identity_version_and_floor(self) -> None:
        package = self.add_skills_package(name="Bad Name", version="9.9.9", minClientVersions={"cursor": "0.0.1"})

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assert_has_error(errors, "does not match")
        self.assert_has_error(errors, "name/version must follow the package model")
        self.assert_has_error(errors, f"minClientVersions.cursor must be {MIN_CURSOR_VERSION}")

    def test_missing_manifest_and_malformed_manifest_are_diagnostics(self) -> None:
        model = fixture_model(cursor_package("ycc", "skills", "agents", "commands", "shared"))

        errors = cursor_native_errors(self.root, model)
        self.assert_has_error(errors, "packages/cursor/ycc/.cursor-plugin/plugin.json: missing")

        self.write_text(Path("packages/cursor/ycc/.cursor-plugin/plugin.json"), '{"name": ')
        errors = cursor_native_errors(self.root, model)
        self.assert_has_error(errors, "unreadable or malformed JSON")

    def test_hooks_require_exact_events_and_an_executable_script(self) -> None:
        package = self.add_hooks_package(executable=False)

        errors = cursor_native_errors(self.root, fixture_model(package))
        self.assert_has_error(errors, "must exist and be executable")

        self.write_json(
            Path("packages/cursor/ycc-hooks/hooks/hooks.json"),
            {"version": 1, "hooks": {"sessionStart": [], "sessionEnd": []}},
        )
        errors = cursor_native_errors(self.root, fixture_model(package))
        self.assert_has_error(errors, "hooks must register ['sessionStart'] only")

    def test_mcp_placeholders_must_match_declared_variables(self) -> None:
        package = self.add_mcp_package(mcp_text='{"mcpServers": {"fixture": {"env": {"TOKEN": "${OTHER}"}}}}')

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assert_has_error(errors, "MCP placeholders must all be declared variables")

    def test_mcp_server_pointer_is_required(self) -> None:
        package = self.add_mcp_package(mcpServers="./elsewhere.json")

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assert_has_error(errors, "mcpServers must point at ./mcp.json")

    def test_malformed_hooks_and_mcp_files_are_diagnostics(self) -> None:
        hooks = self.add_hooks_package()
        self.write_text(Path("packages/cursor/ycc-hooks/hooks/hooks.json"), "{")
        errors = cursor_native_errors(self.root, fixture_model(hooks))
        self.assert_has_error(errors, "unreadable or malformed JSON")

        mcp = self.add_mcp_package(mcp_text="{")
        errors = cursor_native_errors(self.root, fixture_model(mcp))
        self.assert_has_error(errors, "mcp.json: unreadable or malformed JSON")

    def test_schema_valid_marketplace_still_trips_the_absence_gate_only(self) -> None:
        package = self.add_skills_package()
        self.write_json(
            Path(".cursor-plugin/marketplace.json"),
            {"name": "fixture", "plugins": [{"name": "ycc", "source": "packages/cursor/ycc"}]},
        )

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assertEqual(errors, [MARKETPLACE_ABSENCE_ERROR])

    def test_marketplace_schema_violations_add_diagnostics_beside_the_gate(self) -> None:
        package = self.add_skills_package()
        self.write_json(Path(".cursor-plugin/marketplace.json"), {"name": "fixture"})

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assertIn(MARKETPLACE_ABSENCE_ERROR, errors)
        self.assert_has_error(errors, "'plugins' is a required property")

        self.write_json(
            Path(".cursor-plugin/marketplace.json"),
            {"name": "fixture", "plugins": [{"name": "ycc"}]},
        )
        errors = cursor_native_errors(self.root, fixture_model(package))
        self.assertIn(MARKETPLACE_ABSENCE_ERROR, errors)
        self.assert_has_error(errors, "'source' is a required property")

    def test_malformed_and_non_file_marketplace_are_clean_diagnostics(self) -> None:
        package = self.add_skills_package()
        self.write_text(Path(".cursor-plugin/marketplace.json"), "{")

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assertIn(MARKETPLACE_ABSENCE_ERROR, errors)
        self.assert_has_error(errors, "unreadable or malformed JSON")

        (self.root / ".cursor-plugin/marketplace.json").unlink()
        (self.root / ".cursor-plugin/marketplace.json").mkdir()
        errors = cursor_native_errors(self.root, fixture_model(package))
        self.assertIn(MARKETPLACE_ABSENCE_ERROR, errors)
        self.assert_has_error(errors, "unreadable or malformed JSON")

    def test_malformed_version_source_is_a_diagnostic(self) -> None:
        package = self.add_skills_package()
        (self.root / "version.json").write_text("{", encoding="utf-8")

        errors = cursor_native_errors(self.root, fixture_model(package))

        self.assert_has_error(errors, "unreadable or malformed JSON")

    def test_resource_regressions_are_reported(self) -> None:
        package_root = self.root / "packages/cursor/ycc"
        self.write_text(
            Path("packages/cursor/ycc/skills/demo/SKILL.md"),
            "Missing: ${CURSOR_PLUGIN_ROOT}/skills/nope/SKILL.md\n",
        )
        errors = resource_errors(package_root)
        self.assert_has_error(errors, "unresolved ${CURSOR_PLUGIN_ROOT}/skills/nope/SKILL.md")

        self.write_text(Path("packages/cursor/ycc/scripts/run.sh"), "cat ~/.cursor/skills/demo/SKILL.md\n")
        errors = resource_errors(package_root)
        self.assert_has_error(errors, "installer-only $HOME/.cursor/skills/demo/SKILL.md")

    def test_main_returns_exit_codes_without_a_cli(self) -> None:
        model = fixture_model(self.add_skills_package())
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(self.root, model), 0)
        self.assertEqual(stderr.getvalue(), "")

        self.write_text(Path(".cursor-plugin/marketplace.json"), "{")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(self.root, model), 1)
        self.assertIn("validate_cursor_native:", stderr.getvalue())
        self.assertIn(MARKETPLACE_ABSENCE_ERROR, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
