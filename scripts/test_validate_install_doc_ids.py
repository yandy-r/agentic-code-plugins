#!/usr/bin/env python3
"""Deterministic consumer fixtures for install-document package identifiers."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import validate_install_doc_ids as validator
from package_model import Package, PackageModel, RuntimePackage


def runtime(name: str, *, status: str = "included", mechanism: str = "native") -> RuntimePackage:
    return RuntimePackage(
        runtime=name,
        status=status,
        listed=False,
        mechanism=mechanism,
        components=("skills",),
        requires=(),
        target_release="v7.0.0" if status == "deferred" else "v6.0.0",
        experimental=False,
        opt_in=False,
        evidence=(),
        gates=(),
        notes="",
    )


def fixture_model() -> PackageModel:
    def package(key: str, *rows: RuntimePackage) -> Package:
        return Package(key, "fixture", "lockstep", rows)

    return PackageModel(
        1,
        "ycc/.claude-plugin/plugin.json",
        (
            package("ycc", runtime("claude"), runtime("codex"), runtime("cursor")),
            package("ycc-mcp", runtime("claude"), runtime("codex"), runtime("cursor")),
            package("ycc-hooks", runtime("claude"), runtime("codex", status="excluded"), runtime("cursor")),
            package("ycc-all", runtime("claude")),
            package("ycc-agents", runtime("claude", status="deferred")),
            package("ycc-rules", runtime("cursor")),
            package("@yandy-r/ycc-opencode", runtime("opencode", mechanism="npm")),
            package("installer-fallback", runtime("agents", mechanism="file-copy")),
        ),
    )


class InstallDocIdsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model = fixture_model()
        self.write("README.md", "# Live installation\n")

    def write(self, relative: str, text: str) -> None:
        path = self.root / "docs/install" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def errors(self) -> list[str]:
        return validator.validate(self.root, self.model)

    def test_live_and_draft_examples_pass_without_listing_flip(self) -> None:
        self.write("claude.md", "Install `ycc@ycc`; mods use `status-bar@ycc-mods`.\n")
        self.write("codex.md", "`codex plugin add ycc@local-ycc-plugins`\n")
        self.write("v6/README.md", "`<package>@ycc`, `<pkg>@ycc`, `ycc-rules@ycc`, `@yandy-r/ycc-opencode`\n")
        self.write("v6/claude.md", '```json\n{"enabledPlugins": {"ycc-all@ycc": true}}\n```\n')
        self.write("v6/codex.md", '[plugins."ycc-mcp@ycc"]\nenabled = true\n')
        self.write("v6/cursor.md", "`ycc-rules@ycc` and `ycc-hooks@ycc`\n")
        self.write("v6/opencode.md", '```json\n{"plugins": ["@yandy-r/ycc-opencode@6.0.0"]}\n```\n')
        self.write("v6/agents.md", "`installer-fallback` is internal; file copy only.\n")
        self.assertEqual(self.errors(), [])

    def test_typo_and_internal_ids_are_rejected_in_live_and_draft_docs(self) -> None:
        for relative in ("claude.md", "v6/claude.md"):
            for identifier in ("ycc-mpc@ycc", "unmodeled@ycc", "installer-fallback@ycc", "status-bar@ycc"):
                with self.subTest(relative=relative, identifier=identifier):
                    self.write(relative, f"```sh\nclaude plugin install {identifier}\n```\n")
                    self.assertEqual(len(self.errors()), 1)
                    self.assertIn(f"docs/install/{relative}:2:", self.errors()[0])
                    self.assertIn(identifier, self.errors()[0])
            self.write(relative, "")

    def test_every_native_runtime_boundary_is_enforced_in_config_and_commands(self) -> None:
        for runtime_name, identifier in (
            ("claude", "ycc-rules@ycc"),
            ("codex", "ycc-all@ycc"),
            ("codex", "ycc-hooks@ycc"),
            ("cursor", "ycc-all@ycc"),
            ("opencode", "ycc@ycc"),
            ("agents", "ycc@ycc"),
        ):
            for text in (f"plugin install {identifier}", f'{{"enabledPlugins": {{"{identifier}": true}}}}'):
                with self.subTest(runtime=runtime_name, text=text):
                    relative = f"v6/{runtime_name}.md"
                    self.write(relative, text + "\n")
                    errors = self.errors()
                    self.assertEqual(len(errors), 1)
                    self.assertIn(runtime_name, errors[0])
                    self.assertIn(identifier, errors[0])
                    self.write(relative, "")

    def test_excluded_and_deferred_ids_fail_but_bare_negative_prose_passes(self) -> None:
        self.write("v6/codex.md", "`ycc-hooks` is excluded. `ycc-agents` is not a Codex package.\n")
        self.write("v6/claude.md", "`ycc-agents` is deferred to v7.\n")
        self.assertEqual(self.errors(), [])
        self.write("v6/claude.md", "`ycc-agents@ycc`\n")
        self.write("v6/codex.md", "`ycc-hooks@ycc`\n")
        errors = self.errors()
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("deferred" in error for error in errors))
        self.assertTrue(any("excluded" in error for error in errors))

    def test_summary_accepts_cross_runtime_ids_but_not_deferred_or_internal_ids(self) -> None:
        self.write("v6/README.md", "`ycc-rules@ycc`, `ycc-all@ycc`, and `@yandy-r/ycc-opencode`\n")
        self.assertEqual(self.errors(), [])
        self.write("v6/README.md", "`ycc-agents@ycc` and `installer-fallback@ycc`\n")
        self.assertEqual(len(self.errors()), 2)

    def test_scoped_npm_typos_and_wrong_runtime_fail_without_matching_third_party_packages(self) -> None:
        for identifier in (
            "@yandy-r/ycc-opencdoe",
            "@yand-r/ycc-opencode",
            "@ycc/ycc-opencode",
            "@yandy-r/other",
        ):
            with self.subTest(identifier=identifier):
                self.write("v6/opencode.md", f'{{"plugins": ["{identifier}"]}}\n')
                self.assertEqual(len(self.errors()), 1)
                self.assertIn(identifier, self.errors()[0])
        self.write("v6/opencode.md", "`@prevalentware/opencode-goal-plugin`, `@modelcontextprotocol/server-github`\n")
        self.assertEqual(self.errors(), [])
        self.write("v6/agents.md", "`@yandy-r/ycc-opencode`\n")
        self.assertEqual(len(self.errors()), 1)

    def test_marketplace_typos_do_not_escape_validation_and_legacy_is_exact(self) -> None:
        for identifier in ("ycc@yccc", "ycc-mcp@ycc-lab", "ycc@ycc.foo", "ycc-mcp@local-ycc-plugins"):
            with self.subTest(identifier=identifier):
                self.write("codex.md", f"`codex plugin add {identifier}`\n")
                self.assertEqual(len(self.errors()), 1)
                self.assertIn(identifier, self.errors()[0])
        self.write("codex.md", "`ycc@local-ycc-plugins`\n")
        self.write("v6/codex.md", '[plugins."ycc@local-ycc-plugins"]\nenabled = true\n')
        self.assertEqual(self.errors(), [])
        self.write("v6/claude.md", "`ycc@local-ycc-plugins`\n")
        self.assertEqual(len(self.errors()), 1)

    def test_model_status_changes_affect_consumer_without_a_hardcoded_allowlist(self) -> None:
        self.write("v6/claude.md", "`ycc-mcp@ycc`\n")
        self.assertEqual(self.errors(), [])
        packages = tuple(
            (
                replace(package, runtimes=tuple(replace(row, status="excluded") for row in package.runtimes))
                if package.key == "ycc-mcp"
                else package
            )
            for package in self.model.packages
        )
        self.model = replace(self.model, packages=packages)
        self.assertEqual(len(self.errors()), 1)

    def test_only_live_and_v6_install_docs_are_scanned_in_stable_order(self) -> None:
        self.write("z.md", "`typo@ycc`\n")
        self.write("a.md", "`oops@ycc`\n")
        self.write("archive/old.md", "`ignored@ycc`\n")
        unrelated = self.root / "docs/research/notes.md"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("`ignored@ycc`\n", encoding="utf-8")
        errors = self.errors()
        self.assertEqual(len(errors), 2)
        self.assertIn("docs/install/a.md:1:", errors[0])
        self.assertIn("docs/install/z.md:1:", errors[1])

    def test_missing_install_docs_and_unreadable_content_are_diagnostics(self) -> None:
        (self.root / "docs/install/README.md").unlink()
        self.assertTrue(any("no install documents" in error for error in self.errors()))
        path = self.root / "docs/install/README.md"
        path.write_bytes(b"\xff")
        self.assertTrue(any("cannot read" in error for error in self.errors()))

    def test_cli_root_scans_throwaway_fixture_and_returns_diagnostics(self) -> None:
        stderr = io.StringIO()
        stdout = io.StringIO()
        # The fixture root supplies docs, while --manifest supplies the real validated model.
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            self.assertEqual(validator.main(["--root", str(self.root)]), 0)
            self.write("v6/claude.md", "`ycc-mpc@ycc`\n")
            self.assertEqual(validator.main(["--root", str(self.root)]), 1)
        self.assertIn("validate_install_doc_ids:", stderr.getvalue())
        self.assertIn("ycc-mpc@ycc", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
