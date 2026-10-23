#!/usr/bin/env python3
"""Broken-fixture tests for the OMP built-in command drift guard (omp_builtin_commands.py)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import omp_builtin_commands as guard  # noqa: E402
from generate_omp_commands import OMP_BUILTIN_COMMANDS  # noqa: E402
from generate_omp_packages import MIN_OMP_VERSION  # noqa: E402


def frame(commands: list[dict[str, Any]], success: bool = True) -> str:
    payload = {"type": "response", "command": "get_available_commands", "success": success}
    return json.dumps({**payload, "data": {"commands": commands}})


def builtin(name: str, *aliases: str) -> dict[str, Any]:
    return {"name": name, "aliases": list(aliases), "source": "builtin"}


class DriftTests(unittest.TestCase):
    def run_saved(self, *lines: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = guard.main(["--commands-json", str(path)])
        return code, err.getvalue()

    def test_pinned_builtins_and_non_builtin_sources_pass(self) -> None:
        code, err = self.run_saved(
            '{"type":"ready"}',
            frame([builtin("compact"), builtin("force", "force:"), {"name": "ycc:plan", "source": "file"}]),
        )
        self.assertEqual((code, err), (0, ""))

    def test_an_unpinned_live_alias_fails(self) -> None:
        code, err = self.run_saved(frame([builtin("compact", "squash")]))
        self.assertEqual(code, 1)
        self.assertIn("'squash' is missing from OMP_BUILTIN_COMMANDS", err)

    def test_a_builtin_that_shadows_the_namespace_or_a_command_fails(self) -> None:
        errors = guard.drift_errors(frozenset({"ycc", "ycc:plan"}), ["plan", "clean"], pinned=frozenset())
        self.assertIn("live omp built-in 'ycc' shadows the command namespace", errors)
        self.assertIn("live omp built-in 'ycc:plan' shadows a generated command", errors)
        self.assertFalse(any("ycc:clean" in error for error in errors))

    def test_pinned_names_absent_from_rpc_are_not_drift(self) -> None:
        self.assertEqual(guard.drift_errors(frozenset({"compact"}), []), [])
        self.assertIn("quit", OMP_BUILTIN_COMMANDS)

    def test_malformed_or_missing_responses_fail(self) -> None:
        for lines, message in (
            (("not json",), "no get_available_commands response"),
            ((frame([], success=False),), "get_available_commands failed"),
            ((json.dumps({"command": "get_available_commands", "success": True, "data": {}}),), "no command list"),
            ((frame([{"source": "builtin"}]),), "builtin command without a name"),
            ((frame([{"name": "x", "aliases": "y", "source": "builtin"}]),), "malformed aliases"),
        ):
            with self.subTest(message=message):
                code, err = self.run_saved(*lines)
                self.assertEqual(code, 1)
                self.assertIn(message, err)

    def test_missing_omp_skips_with_a_warning(self) -> None:
        out = io.StringIO()
        with patch.dict(os.environ, {"OMP_BIN": "", "PATH": ""}), redirect_stdout(out):
            self.assertEqual(guard.main([]), 0)
        self.assertIn("[warn] omp not found", out.getvalue())

    def test_an_old_omp_skips_with_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "omp"
            fake.write_text("#!/bin/sh\necho omp/18.0.0\n", encoding="utf-8")
            fake.chmod(0o755)
            out = io.StringIO()
            with patch.dict(os.environ, {"OMP_BIN": str(fake)}), redirect_stdout(out):
                self.assertEqual(guard.main([]), 0)
        self.assertIn(f"older than {MIN_OMP_VERSION}", out.getvalue())

    def run_live(self, argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env), redirect_stdout(out), redirect_stderr(err):
            code = guard.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_require_makes_a_missing_omp_an_error(self) -> None:
        for argv, env in (
            (["--require"], {"OMP_BIN": "", "PATH": ""}),
            ([], {"OMP_BIN": "", "PATH": "", "YCC_OMP_REQUIRED": "1"}),
        ):
            with self.subTest(argv=argv, env=env):
                code, out, err = self.run_live(argv, env)
                self.assertEqual(code, 1)
                self.assertNotIn("[warn]", out)
                self.assertIn("a live omp is required", err)

    def test_require_makes_an_old_omp_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "omp"
            fake.write_text("#!/bin/sh\necho omp/18.0.0\n", encoding="utf-8")
            fake.chmod(0o755)
            code, out, err = self.run_live(["--require"], {"OMP_BIN": str(fake)})
        self.assertEqual(code, 1)
        self.assertNotIn("[warn]", out)
        self.assertIn(f"older than {MIN_OMP_VERSION} and a live omp is required", err)

    def test_a_falsy_required_env_still_skips(self) -> None:
        code, out, _ = self.run_live([], {"OMP_BIN": "", "PATH": "", "YCC_OMP_REQUIRED": "0"})
        self.assertEqual(code, 0)
        self.assertIn("[warn] omp not found", out)

    def test_require_does_not_affect_saved_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.jsonl"
            path.write_text(frame([builtin("compact")]) + "\n", encoding="utf-8")
            code, _, err = self.run_live(["--require", "--commands-json", str(path)], {})
        self.assertEqual((code, err), (0, ""))

    def test_a_failing_probe_is_an_error_not_a_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "omp"
            fake.write_text(
                '#!/bin/sh\n[ "$1" = --version ] && { echo omp/99.0.0; exit 0; }\necho boom >&2\nexit 3\n',
                encoding="utf-8",
            )
            fake.chmod(0o755)
            err = io.StringIO()
            with patch.dict(os.environ, {"OMP_BIN": str(fake)}), redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(guard.main([]), 1)
        self.assertIn("omp --mode rpc exited 3: boom", err.getvalue())


if __name__ == "__main__":
    unittest.main()
