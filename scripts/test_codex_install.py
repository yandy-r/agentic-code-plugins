#!/usr/bin/env python3
"""Ownership and TOML preflight regressions for the native Codex installer."""

from __future__ import annotations

import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_install as installer


class NativeInstallSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.home = Path(temporary.name) / "home"
        self.home.mkdir()
        for name, value in (
            ("ROOT", self.root),
            ("repository_native_enabled", lambda packages: True),
            ("load_package_model", lambda: type("Model", (), {"packages": ()})()),
            ("validate", lambda *args, **kwargs: None),
            ("merge_config", lambda *args, **kwargs: None),
        ):
            patcher = patch.object(installer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.version("1.0.0")

    def version(self, version: str) -> None:
        for package in installer.MIGRATION_PACKAGES:
            root = self.root / ".codex-plugin" / package
            (root / ".codex-plugin").mkdir(parents=True, exist_ok=True)
            (root / ".codex-plugin/plugin.json").write_text(json.dumps({"name": package, "version": version}))
            (root / "payload").write_text(version)

    def cli(self, *args: str, **kwargs: object) -> None:
        if args[:2] != ("plugin", "add"):
            return
        package = args[2].split("@")[0]
        source = self.root / ".codex-plugin" / package
        version = json.loads((source / ".codex-plugin/plugin.json").read_text())["version"]
        cache = self.home / ".codex/plugins/cache/ycc" / package / version
        if cache.exists():
            shutil.rmtree(cache)
        shutil.copytree(source, cache)

    def snapshot(self) -> dict[str, bytes]:
        return {str(path.relative_to(self.home)): path.read_bytes() for path in self.home.rglob("*") if path.is_file()}

    def test_cli_upgrade_rejects_edited_old_version_before_any_mutation(self) -> None:
        with patch.object(installer, "cli", side_effect=self.cli):
            installer.install("local", True)
        old = self.home / ".codex/plugins/cache/ycc/ycc/1.0.0/payload"
        old.write_text("my edit")
        self.version("2.0.0")
        before = self.snapshot()
        with patch.object(installer, "cli") as cli:
            with self.assertRaisesRegex(ValueError, "edited or foreign"):
                installer.install("local", True)
            cli.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        installer.remove(False)
        self.assertEqual(old.read_text(), "my edit")

    def test_cli_upgrade_keeps_original_fingerprint_for_untouched_versions(self) -> None:
        with patch.object(installer, "cli", side_effect=self.cli):
            installer.install("local", True)
            original = installer.load_state()["caches"]
            self.version("2.0.0")
            installer.install("local", True)
        current = installer.load_state()["caches"]
        for key, fingerprint in original.items():
            self.assertEqual(current[key], fingerprint)
        self.assertEqual(len(current), 4)

    def test_fallback_refuses_closed_inline_marketplaces_without_mutation(self) -> None:
        config = self.home / ".codex/config.toml"
        config.parent.mkdir()
        text = 'marketplaces = { foreign = { source_type = "local", source = "/foreign" } }\n'
        config.write_text(text)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "closed inline table"):
            installer.install("local", False)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(tomllib.loads(config.read_text())["marketplaces"]["foreign"]["source"], "/foreign")

    def test_verified_toml_rejects_invalid_text_without_writing(self) -> None:
        config = self.home / "config.toml"
        config.write_text("model = 'mine'\n")
        with self.assertRaisesRegex(ValueError, "cannot update"):
            installer.write_verified_toml(config, "[broken")
        self.assertEqual(config.read_text(), "model = 'mine'\n")


if __name__ == "__main__":
    unittest.main()
