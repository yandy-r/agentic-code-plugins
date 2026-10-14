#!/usr/bin/env python3
"""Tests for merge_managed_config.py entry selection (--entries / --list-entries).

Run directly (``python3 scripts/test_managed_config_entries.py``) or through
``./scripts/validate.sh --only config``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "scripts" / "merge_managed_config.py"

SERVERS = {
    "github": {"url": "https://github"},
    "linear": {"url": "https://linear"},
    "stripe": {"url": "https://stripe"},
}


class EntrySelectionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state.json"
        self.addCleanup(self._tmp.cleanup)
        self.source = self.tmp / "mcp.json"
        self.source.write_text(json.dumps({"mcpServers": SERVERS}), encoding="utf-8")
        self.dest = self.tmp / "dest.json"

    def run_helper(
        self, *extra: str, profile: str = "claude-mcp", source: Path | None = None, dest: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "YCC_MANAGED_CONFIG_STATE": str(self.state)}
        argv = [
            sys.executable, str(HELPER), "--profile", profile,
            "--source", str(source or self.source),
            "--destination", str(dest or self.dest),
            "--groups", "mcp", *extra,
        ]  # fmt: skip
        return subprocess.run(argv, capture_output=True, text=True, env=env)

    def servers(self) -> dict:
        return json.loads(self.dest.read_text(encoding="utf-8")).get("mcpServers", {})

    def test_list_entries_prints_managed_names(self) -> None:
        result = self.run_helper("--list-entries")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["github", "linear", "stripe"])
        self.assertFalse(self.dest.exists())

    def test_merge_only_selected_entries(self) -> None:
        result = self.run_helper("--entries", "github,linear")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.servers()), ["github", "linear"])

    def test_partial_sync_does_not_prune_other_managed_entries(self) -> None:
        self.assertEqual(self.run_helper().returncode, 0)
        result = self.run_helper("--entries", "github")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.servers()), ["github", "linear", "stripe"])
        # Ownership of the unselected entries survives: a full remove still takes them.
        self.assertEqual(self.run_helper("--remove").returncode, 0)
        self.assertFalse(self.dest.exists())

    def test_unknown_entry_fails_without_writing(self) -> None:
        result = self.run_helper("--entries", "github,bogus")
        self.assertEqual(result.returncode, 1)
        self.assertIn("bogus", result.stderr)
        self.assertIn("managed: github, linear, stripe", result.stderr)
        self.assertFalse(self.dest.exists())

    def test_remove_only_selected_entries(self) -> None:
        self.assertEqual(self.run_helper().returncode, 0)
        result = self.run_helper("--remove", "--entries", "stripe")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(self.servers()), ["github", "linear"])

    def test_toml_selection(self) -> None:
        source = self.tmp / "config.toml"
        source.write_text(
            '[mcp_servers.github]\nurl = "https://github"\n\n[mcp_servers.playwright]\ncommand = "npx"\n',
            encoding="utf-8",
        )
        dest = self.tmp / "dest.toml"
        result = self.run_helper("--entries", "playwright", profile="codex-config", source=source, dest=dest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(tomllib.loads(dest.read_text(encoding="utf-8"))["mcp_servers"]), ["playwright"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
