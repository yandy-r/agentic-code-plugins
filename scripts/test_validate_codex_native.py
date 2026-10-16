#!/usr/bin/env python3
"""Fixture-based structural checks for Codex catalogs, without running Codex."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import codex_marketplace as marketplace
import generate_codex_plugin as generator
import validate_codex_native as validator
from package_model import load_package_model


class CodexMarketplaceSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / generator.NATIVE_MARKETPLACE

    @staticmethod
    def catalog(source: object | None = None) -> dict:
        return {
            "name": "fixture",
            "plugins": [{"name": "fixture-plugin", "source": source or {"source": "local", "path": "./plugin"}}],
        }

    def write_catalog(self, catalog: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(catalog), encoding="utf-8")

    def assert_invalid_catalog(self, catalog: object, message: str) -> None:
        with self.assertRaisesRegex(ValueError, message):
            validator.check_catalog_structure(catalog, self.path)

    def test_supported_source_shapes_are_read_only(self) -> None:
        sources = (
            {"source": "local", "path": "./.codex-plugin/native"},
            {"source": "url", "url": "https://example.invalid/plugin.git"},
            {"source": "url", "url": "owner/repo", "path": "plugin", "sha": "immutable"},
            {"source": "git-subdir", "url": "https://example.invalid/fixture.git", "path": "./plugin", "ref": "main"},
            {
                "source": "npm",
                "package": "@fixture/plugin",
                "version": "^1.0.0",
                "registry": "https://registry.npmjs.org",
            },
        )
        for source in sources:
            with self.subTest(source=source):
                before = copy.deepcopy(source)
                self.assertIs(marketplace.validate_marketplace_source(source), source)
                validator.check_catalog_structure(self.catalog(source), self.path)
                self.assertEqual(source, before)

    def test_source_tag_and_shape_failures(self) -> None:
        cases = (
            ("./plugin", "source must be an object"),
            ({}, "source tag must be a string"),
            ({"source": []}, "source tag must be a string"),
            ({"source": "github", "repo": "owner/repo"}, "unsupported source tag 'github'"),
            ({"source": "local"}, "missing required source fields"),
            ({"source": "local", "path": None}, "missing required source fields"),
            ({"source": "local", "path": 7}, "path.*non-empty string"),
            ({"source": "local", "path": " "}, "path.*non-empty string"),
            ({"source": "local", "path": "/absolute"}, "path must start with"),
            ({"source": "local", "path": "./../escape"}, "marketplace root"),
            ({"source": "local", "path": "./plugin", "url": "https://example.invalid"}, "unsupported source fields"),
            ({"source": "url"}, "missing required source fields"),
            ({"source": "url", "url": False}, "url.*non-empty string"),
            ({"source": "url", "url": "not-a-git-source"}, "supported git source"),
            ({"source": "url", "url": "./../escape.git"}, "relative url.*marketplace root"),
            ({"source": "url", "url": "../escape.git"}, "relative url.*marketplace root"),
            ({"source": "url", "url": "..\\escape.git"}, "relative url.*marketplace root"),
            ({"source": "git-subdir", "url": "../escape.git", "path": "plugin"}, "relative url.*marketplace root"),
            ({"source": "url", "url": "https://example.invalid/plugin.git", "ref": []}, "ref.*must be a string"),
            ({"source": "git-subdir", "url": "https://example.invalid/fixture.git"}, "missing required source fields"),
            (
                {"source": "git-subdir", "url": "https://example.invalid/fixture.git", "path": []},
                "path.*non-empty",
            ),
            (
                {"source": "git-subdir", "url": "https://example.invalid/fixture.git", "path": "../escape"},
                "repository root",
            ),
            ({"source": "npm"}, "missing required source fields"),
            ({"source": "npm", "package": "@scope"}, "invalid package name"),
            ({"source": "npm", "package": "plugin", "version": "file:./local"}, "version must use the registry"),
            (
                {"source": "npm", "package": "plugin", "registry": "http://registry.example.invalid"},
                "registry must be an HTTPS URL",
            ),
        )
        for source, message in cases:
            with self.subTest(source=source):
                # Do not use the fixture's default source for the deliberately empty object.
                catalog = {"name": "fixture", "plugins": [{"name": "fixture-plugin", "source": source}]}
                self.assert_invalid_catalog(catalog, message)

    def test_catalog_structural_failures(self) -> None:
        entry = self.catalog()["plugins"][0]
        cases = (
            ([], "catalog must be a JSON object"),
            ({"plugins": []}, "name must be a non-empty string"),
            ({"name": [], "plugins": []}, "name must be a non-empty string"),
            ({"name": "fixture"}, "plugins must be a list"),
            ({"name": "fixture", "plugins": {}}, "plugins must be a list"),
            ({"name": "fixture", "plugins": [None]}, "expected an object"),
            ({"name": "fixture", "plugins": [{"name": []}]}, "name must be a non-empty string"),
            ({"name": "fixture", "plugins": [entry, entry]}, "duplicate plugin name"),
            ({"name": "fixture", "plugins": [], "interface": []}, "interface must be an object"),
            ({"name": "fixture", "plugins": [], "interface": {"displayName": 2}}, "displayName.*non-empty string"),
            ({"name": "fixture", "plugins": [{**entry, "policy": []}]}, "policy must be an object"),
            (
                {"name": "fixture", "plugins": [{**entry, "policy": {"installation": []}}]},
                "invalid policy installation",
            ),
            (
                {"name": "fixture", "plugins": [{**entry, "policy": {"authentication": "INVALID"}}]},
                "invalid policy authentication",
            ),
            ({"name": "fixture", "plugins": [{**entry, "category": []}]}, "category.*non-empty string"),
        )
        for catalog, message in cases:
            with self.subTest(catalog=catalog):
                self.assert_invalid_catalog(catalog, message)

    def test_catalog_diagnostic_includes_path(self) -> None:
        with self.assertRaises(ValueError) as caught:
            validator.check_catalog_structure({"name": "fixture", "plugins": [{"name": "bad"}]}, self.path)
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn("bad", str(caught.exception))

    def test_emitted_builders_remain_valid_and_unchanged(self) -> None:
        model = load_package_model()
        legacy = generator.build_repo_marketplace()
        self.assertEqual(legacy["plugins"][0]["source"], {"source": "local", "path": "./plugins/ycc"})
        native = generator.build_native_marketplace(model.packages, include_unlisted=True)
        self.assertEqual(generator.build_native_marketplace(model.packages)["plugins"], [])
        for catalog in (legacy, native):
            before = copy.deepcopy(catalog)
            validator.check_catalog_structure(catalog, self.path)
            self.assertEqual(catalog, before)
        for mode, path in (("local", "./.agents/plugins/ycc"), ("repo", "")):
            with self.subTest(mode=mode):
                entry = marketplace.build_entry(mode, path)
                self.assertEqual(entry["source"]["source"], "local" if mode == "local" else "git-subdir")
                validator.check_catalog_structure({"name": "fixture", "plugins": [entry]}, self.path)

    def test_installer_builder_rejects_traversing_source_before_writes(self) -> None:
        with self.assertRaisesRegex(ValueError, "marketplace root"):
            marketplace.merge(self.path, "local", "./../escape")
        self.assertFalse(self.path.exists())

    def test_native_gate_checks_structure_before_model_equality(self) -> None:
        self.write_catalog({"name": "ycc", "plugins": [{"name": [], "source": {"source": "github"}}]})
        with self.assertRaisesRegex(ValueError, "name must be a non-empty string"):
            validator.check_catalog(self.root, ())

    def test_native_gate_still_requires_exact_model_catalog(self) -> None:
        self.write_catalog({"name": "ycc", "plugins": [], "unexpected": "drift"})
        with self.assertRaisesRegex(ValueError, "model-driven native catalog"):
            validator.check_catalog(self.root, ())

    def test_legacy_gate_checks_structure_and_preserves_exact_equality(self) -> None:
        manifest_path = self.root / ".codex-plugin/ycc/.codex-plugin/plugin.json"
        manifest_path.parent.mkdir(parents=True)
        manifest = {"name": "ycc", "version": "1.0.0"}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        mcp_path = self.root / ".codex-plugin/ycc/.mcp.json"
        mcp_path.write_text('{"mcpServers": {}}', encoding="utf-8")
        with (
            patch.object(validator, "load_package_model", return_value=SimpleNamespace(packages=())),
            patch.object(generator, "native_version", return_value="1.0.0"),
            patch.object(generator, "build_plugin_manifest", return_value=manifest),
        ):
            catalog = generator.build_repo_marketplace()
            self.write_catalog(catalog)
            validator.validate(self.root, native=False)
            broken = copy.deepcopy(catalog)
            broken["plugins"][0]["source"] = {"source": "github", "repo": "owner/repo"}
            self.write_catalog(broken)
            with self.assertRaisesRegex(ValueError, "unsupported source tag 'github'"):
                validator.validate(self.root, native=False)
            catalog["interface"]["displayName"] = "Changed but structurally valid"
            self.write_catalog(catalog)
            with self.assertRaisesRegex(ValueError, "legacy discovered catalog changed"):
                validator.validate(self.root, native=False)


if __name__ == "__main__":
    unittest.main()
