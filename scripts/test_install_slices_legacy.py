#!/usr/bin/env python3
"""Failed-unlink state retention for install_slices.retire_legacy_commands."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install_slices

_real_unlink = Path.unlink


class RetireLegacyUnlinkTest(unittest.TestCase):
    def test_failed_unlink_stays_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            commands = home / ".claude" / "commands"
            commands.mkdir(parents=True)
            for name in ("ok.md", "bad.md"):
                (commands / name).write_text("wrapper", encoding="utf-8")
            state_file = home / "state" / "installed-units.json"
            state_file.parent.mkdir()
            names = ["ok.md", "bad.md", "missing.md"]
            state_file.write_text(json.dumps({"version": 1, "units": {str(commands): names}}), encoding="utf-8")

            def fake_unlink(self: Path, *args: object, **kwargs: object) -> None:
                if self.name == "bad.md":
                    raise PermissionError("denied")
                _real_unlink(self, *args, **kwargs)

            env = {"HOME": str(home), "YCC_MANAGED_CONFIG_STATE": str(state_file.parent / "managed.json")}
            with patch.dict(os.environ, env), patch.object(Path, "unlink", fake_unlink):
                rc = install_slices.main(["remove", "--target", "claude", "--slice", "commands"])

            self.assertEqual(rc, 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))["units"]
            self.assertEqual(state, {str(commands): ["bad.md"]})
            self.assertFalse((commands / "ok.md").exists())
            self.assertTrue((commands / "bad.md").exists())


if __name__ == "__main__":
    unittest.main()
