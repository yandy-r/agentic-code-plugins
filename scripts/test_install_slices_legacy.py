#!/usr/bin/env python3
"""Failed-unlink state retention for install_slices.retire_legacy_commands."""

from __future__ import annotations

import json
import os
import re
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


class NativeStandaloneProjectionTest(unittest.TestCase):
    """Native/listed tree projected to ~/.codex/skills keeps shared refs resolvable."""

    REF = re.compile(r"(?<![\w./~-])((?:\.\./)+_shared/[A-Za-z0-9_./-]*[A-Za-z0-9_-])")

    def test_relative_shared_refs_resolve_at_standalone_shared(self) -> None:
        import generate_codex_plugin as generator

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, home = root / "repo", root / "home"
            home.mkdir()
            generator.generate_native_tree(repo)
            env = {"HOME": str(home), "YCC_MANAGED_CONFIG_STATE": str(root / "managed.json")}
            with patch.dict(os.environ, env), patch.object(install_slices, "REPO_ROOT", repo):
                self.assertEqual(install_slices.main(["install", "--target", "codex", "--slice", "skills"]), 0)

            skills = home / ".codex" / "skills"
            self.assertTrue((skills / "_shared" / "scripts").is_dir())
            backport = (skills / "backport" / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("../../shared/", backport)
            shallow = set(self.REF.findall(backport))
            self.assertTrue(shallow, "backport must reference standalone _shared")
            self.assertTrue(any(ref.startswith("../_shared/scripts/") for ref in shallow), sorted(shallow))
            for ref in shallow:
                self.assertTrue((skills / "backport" / ref).resolve().exists(), ref)

            deeper = 0
            for path in skills.rglob("*"):
                if not path.is_file() or path.is_relative_to(skills / "_shared"):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                self.assertNotIn("../shared/", text.replace("../_shared/", ""), str(path))
                for ref in self.REF.findall(text):
                    if "{" in ref or "*" in ref:
                        continue
                    self.assertTrue((path.parent / ref).resolve().exists(), f"{path}: {ref}")
                    deeper += int(ref.startswith("../../_shared/"))
            self.assertGreater(deeper, 0)


if __name__ == "__main__":
    unittest.main()
