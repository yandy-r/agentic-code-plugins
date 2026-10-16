#!/usr/bin/env python3
"""Unit tests for the opt-in scripts/cursor_live_smoke.py cleanup guarantees.

Run directly (``python3 scripts/test_cursor_live_smoke.py``) or through
``./scripts/validate.sh --only cursor-native``. No Cursor CLI or model is used.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import cursor_live_smoke  # noqa: E402

SMOKE = SCRIPTS / "cursor_live_smoke.py"


class SocketRecorderTestCase(unittest.TestCase):
    def test_bind_failure_closes_the_socket(self) -> None:
        with patch.object(cursor_live_smoke.socket, "socket", autospec=True) as socket_factory:
            server = socket_factory.return_value
            server.bind.side_effect = OSError("AF_UNIX path too long")
            with self.assertRaises(OSError):
                cursor_live_smoke.SocketRecorder(Path("/not-bound.sock"))
            server.close.assert_called_once_with()

    def test_thread_start_failure_closes_and_unlinks_the_socket(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cls.") as tmp:
            path = Path(tmp) / "h.sock"
            with patch.object(cursor_live_smoke.threading.Thread, "start", autospec=True, side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    cursor_live_smoke.SocketRecorder(path)
            self.assertFalse(path.exists())

    def test_close_removes_the_socket_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cls.") as tmp:
            recorder = cursor_live_smoke.SocketRecorder(Path(tmp) / "h.sock")
            self.assertTrue(recorder.path.exists())
            recorder.close()
            self.assertFalse(recorder.path.exists())


class CredentialCleanupTestCase(unittest.TestCase):
    def test_credential_is_removed_when_recorder_construction_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth_dir = root / "config/cursor"
            auth_dir.mkdir(parents=True)
            (auth_dir / "auth.json").write_text('{"token": "secret"}', encoding="utf-8")
            long_tmp = root / ("t" * 110)  # TMPDIR honored by mkdtemp -> AF_UNIX path too long
            long_tmp.mkdir()
            env = {
                **os.environ,
                "TMPDIR": str(long_tmp),
                "XDG_CONFIG_HOME": str(root / "config"),
                "CURSOR_AGENT_BIN": "/bin/true",
            }
            env.pop("CURSOR_API_KEY", None)

            result = subprocess.run(
                [sys.executable, str(SMOKE), "--keep"], capture_output=True, text=True, env=env, cwd=root
            )

            self.assertNotEqual(result.returncode, 0)
            retained = re.search(r"Retained lab: (.+)", result.stdout)
            self.assertIsNotNone(retained, result.stdout + result.stderr)
            lab = Path(retained.group(1))
            self.assertTrue(lab.is_dir())
            self.assertEqual(list(lab.rglob("auth.json")), [])
            self.assertNotIn("secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
