#!/usr/bin/env python3
"""Opt-in live Cursor user-scope smoke: installed commands + sessionStart hook.

Runs the real installer (``install.sh install --target cursor --package ycc`` and
``--package ycc-hooks``) into a disposable HOME, then drives the installed
``cursor-agent`` CLI headlessly (one model session per probe) to prove:

* an installed ``~/.cursor/commands/<name>.md`` wrapper expands on ``/<name>`` and
  reads the installed ``~/.cursor/skills/<name>/SKILL.md`` by absolute path;
* ``$ARGUMENTS`` substitution reaches the model for a user command;
* the installed ``~/.cursor/hooks.json`` ``sessionStart`` entry runs the installed
  ``herdr-session-start.sh`` (a disposable unix-socket recorder receives its
  ``pane.report_agent_session`` payload) while a foreign ``sessionStart`` hook and a
  foreign command file, seeded before the install, survive and still fire.

Not part of CI and never run by the unit/validate suites: it needs an authenticated
Cursor CLI and performs real model inference. The real ``~/.cursor`` is never read or
written. Auth is copied (never printed) into the lab as
``$XDG_CONFIG_HOME/cursor/auth.json`` -- the only isolation form the CLI honors in
2026.10.14 (``CURSOR_CONFIG_DIR`` is not).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = "go-patterns"  # shipped user-invocable skill with a stable H1
SKILL_H1 = "Go Development Patterns"
PANE_ID = "ycc-cursor-live-pane"
PROBE_TIMEOUT = 240


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def real_auth_file() -> Path | None:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = config / "cursor" / "auth.json"
    return path if path.is_file() else None


class SocketRecorder:
    """Unix socket standing in for the herdr server; records JSON-line requests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.requests: list[dict] = []
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        bound = False
        try:
            self._server.bind(str(path))
            bound = True
            self._server.listen(8)
            self._server.settimeout(0.2)
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
        except BaseException:
            self._server.close()
            if bound:
                path.unlink(missing_ok=True)
            raise

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except (TimeoutError, OSError):
                continue
            with conn:
                conn.settimeout(1)
                data = b""
                try:
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    self.requests.append(json.loads(data))
                    conn.sendall(b'{"result":{}}\n')
                except (OSError, ValueError):
                    pass

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._server.close()
        self.path.unlink(missing_ok=True)


def run_installer(env: dict[str, str], *args: str) -> None:
    command = ["bash", str(REPO / "install.sh"), "install", "--target", "cursor", *args]
    print("+", " ".join(command[2:]), flush=True)
    result = subprocess.run(command, env=env, cwd=REPO, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-2000:] + result.stderr[-2000:])
        die(f"installer failed ({result.returncode}): {' '.join(args)}")


def agent_probe(agent: str, env: dict[str, str], workspace: Path, prompt: str) -> tuple[str, str]:
    """Run one headless session; return (result text, session id)."""
    command = [
        agent,
        "-p",
        "--trust",
        "--sandbox",
        "disabled",
        "--mode",
        "ask",
        "--output-format",
        "stream-json",
        "--workspace",
        str(workspace),
        prompt,
    ]
    result = subprocess.run(command, env=env, cwd=workspace, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    final, session = "", ""
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("session_id"):
            session = event["session_id"]
        if event.get("type") == "result":
            final = str(event.get("result", ""))
    if result.returncode != 0 or not final:
        die(f"cursor-agent probe failed (rc={result.returncode}, result empty={not final})")
    return final, session


def check(condition: bool, label: str) -> None:
    if not condition:
        die(f"FAIL {label}")
    print(f"PASS {label}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="retain the lab (no credentials are left in the output)")
    parser.add_argument("--agent", default=os.environ.get("CURSOR_AGENT_BIN") or shutil.which("cursor-agent") or "")
    args = parser.parse_args()
    if not args.agent or not os.access(args.agent, os.X_OK):
        die("install cursor-agent or set CURSOR_AGENT_BIN")
    auth = real_auth_file()
    if auth is None and not os.environ.get("CURSOR_API_KEY"):
        die("no Cursor auth: log in with the CLI (or set CURSOR_API_KEY) before running this opt-in smoke")

    lab = Path(tempfile.mkdtemp(prefix="cursor-live."))  # short path: unix socket limit
    home, xdg, workspace = lab / "home", lab / "xdg", lab / "workspace"
    recorder: SocketRecorder | None = None
    try:
        for directory in (home / ".cursor/commands", xdg / "cursor", workspace):
            directory.mkdir(parents=True)
        if auth is not None:
            shutil.copyfile(auth, xdg / "cursor/auth.json")
            (xdg / "cursor/auth.json").chmod(0o600)
        recorder = SocketRecorder(lab / "herdr.sock")
        version = subprocess.run([args.agent, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
        print(f"cursor-agent {version}; lab={lab}", flush=True)

        # Foreign state seeded before install: must survive and keep firing.
        foreign_out = lab / "foreign-hook.json"
        foreign_script = lab / "foreign_record.py"
        foreign_script.write_text(
            "import pathlib, sys\n" f"pathlib.Path({str(foreign_out)!r}).write_text(sys.stdin.read())\n",
            encoding="utf-8",
        )
        foreign_command = f"{sys.executable} {foreign_script}"
        (home / ".cursor/hooks.json").write_text(
            json.dumps({"version": 1, "hooks": {"sessionStart": [{"command": foreign_command}]}}),
            encoding="utf-8",
        )
        (home / ".cursor/commands/foreign-probe.md").write_text("foreign command\n", encoding="utf-8")

        base = {
            key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TERM", "CURSOR_API_KEY") if key in os.environ
        }
        env = {
            **base,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(xdg),
            "YCC_MANAGED_CONFIG_STATE": str(home / ".config/ycc/managed-config-state.json"),
            "YCC_INSTALL_SKIP_BUILD": "1",
        }
        run_installer(env, "--package", "ycc", "--skills-home", "native")
        run_installer(env, "--package", "ycc-hooks")

        # --- filesystem carrier assertions -------------------------------------
        wrapper = (home / ".cursor/commands" / f"{SKILL}.md").read_text(encoding="utf-8")
        skill_path = home / ".cursor/skills" / SKILL / "SKILL.md"
        check(
            str(skill_path) in wrapper and "${CURSOR_PLUGIN_ROOT}" not in wrapper,
            "command wrapper points at installed absolute skill path",
        )
        check(
            (home / ".cursor/commands/foreign-probe.md").read_text(encoding="utf-8") == "foreign command\n",
            "foreign command file untouched",
        )
        hook_script = home / ".cursor/hooks/herdr-session-start.sh"
        canonical = REPO / "ycc/settings/cursor/herdr-session-start.sh"
        check(
            hook_script.read_bytes() == canonical.read_bytes() and os.access(hook_script, os.X_OK),
            "installed hook script is canonical and executable",
        )
        hooks = json.loads((home / ".cursor/hooks.json").read_text(encoding="utf-8"))
        commands = [entry["command"] for entry in hooks["hooks"]["sessionStart"]]
        own_command = f"bash {shlex.quote(str(hook_script))} session"
        check(
            commands == [foreign_command, own_command] or set(commands) == {foreign_command, own_command},
            "hooks.json carries foreign + own sessionStart entries",
        )

        # --- live runtime: installed wrapper + own/foreign hooks -----------------
        live_env = {**env, "HERDR_ENV": "1", "HERDR_SOCKET_PATH": str(recorder.path), "HERDR_PANE_ID": PANE_ID}
        prompt = (
            f"/{SKILL} Smoke inspection only. Do not apply changes or give coding advice. "
            "Read the skill referenced by this command. Report its first Markdown H1 heading and the "
            "absolute path of the skill you read. Do not run shell commands."
        )
        result, session = agent_probe(args.agent, live_env, workspace, prompt)
        check(
            SKILL_H1 in result and str(skill_path) in result,
            f"/{SKILL} expanded: model read {skill_path} (H1 {SKILL_H1!r})",
        )
        reports = [r for r in recorder.requests if r.get("method") == "pane.report_agent_session"]
        check(
            any(
                r["params"].get("source") == "herdr:cursor"
                and r["params"].get("agent") == "cursor"
                and r["params"].get("pane_id") == PANE_ID
                and r["params"].get("agent_session_id") == session
                for r in reports
            ),
            "installed herdr hook sent pane.report_agent_session for this session",
        )
        foreign = json.loads(foreign_out.read_text(encoding="utf-8"))
        check(
            foreign.get("hook_event_name") == "sessionStart" and foreign.get("session_id") == session,
            "foreign sessionStart hook still fired for the same session",
        )

        # --- $ARGUMENTS substitution on a user command (synthetic) ---------------
        (home / ".cursor/commands/ycc-args-probe.md").write_text(
            "---\nname: ycc-args-probe\ndescription: live smoke\n---\n\n"
            "Reply with exactly this single line and nothing else: ARGS_MARKER $ARGUMENTS\n",
            encoding="utf-8",
        )
        result, _ = agent_probe(args.agent, live_env, workspace, "/ycc-args-probe alpha beta")
        check("ARGS_MARKER alpha beta" in result, "$ARGUMENTS substituted into user command")
        print(f"PASS Cursor live carriers (cursor-agent {version})")
        return 0
    finally:
        try:
            if recorder is not None:
                recorder.close()
        finally:
            # Even --keep retains evidence/payloads only, never the copied credential.
            (xdg / "cursor/auth.json").unlink(missing_ok=True)
            if args.keep:
                print(f"Retained lab: {lab}")
            else:
                shutil.rmtree(lab, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
