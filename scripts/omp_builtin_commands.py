#!/usr/bin/env python3
"""Drift guard for OMP_BUILTIN_COMMANDS against a live omp.

generate_omp_commands.py pins omp's built-in slash command names and aliases so the
``ycc`` namespace and every ``ycc:<name>`` command stay dispatchable. This check asks a
real omp for its commands (RPC ``get_available_commands``, ``source: builtin``) and fails
when a live built-in name or alias is missing from the pin, or when a live built-in
shadows the namespace or a generated command. Pinned names that RPC does not report are
not drift: RPC lists only the commands available to a headless session.

The probe runs ``omp --mode rpc`` under ``env -i`` with a throwaway HOME/XDG tree and a
null model provider on 127.0.0.1:9; no prompt is sent, so no request is made. When omp
is not installed (or older than MIN_OMP_VERSION) the check prints a warning and exits 0,
so ./scripts/validate.sh stays runnable without omp. CI sets ``--require`` (or
``YCC_OMP_REQUIRED=1``) to turn that skip into a hard failure (YAN-1552).

Usage:
  omp_builtin_commands.py                     probe OMP_BIN or omp on PATH
  omp_builtin_commands.py --require           same, but missing/old omp is an error
  omp_builtin_commands.py --commands-json F   check a saved get_available_commands frame
Exit 0 when clean or skipped, 1 on drift, a failed probe, or (with --require) no usable omp;
2 for --require with --commands-json. YCC_OMP_REQUIRED is ignored for saved frames.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_omp_commands import COMMAND_NAMESPACE, OMP_BUILTIN_COMMANDS, load_commands  # noqa: E402
from generate_omp_packages import MIN_OMP_VERSION  # noqa: E402
from generate_omp_skills import SRC_DIR, build_catalog  # noqa: E402

PROBE_TIMEOUT = 60
NULL_MODELS = """providers:
  ycc-null:
    baseUrl: http://127.0.0.1:9/v1
    apiKey: none
    api: openai-completions
    auth: none
    models:
      - id: null-model
        name: Null Model
        api: openai-completions
        reasoning: false
        input: [text]
"""


class ProbeError(Exception):
    """The live omp probe could not produce a command list."""


def version_key(version: str) -> tuple[int, ...]:
    digits = version.split("/")[-1].strip().split("-")[0]
    try:
        return tuple(int(part) for part in digits.split("."))
    except ValueError as error:
        raise ProbeError(f"unparseable omp version: {version!r}") from error


def builtin_names(commands: Iterable[dict[str, Any]]) -> frozenset[str]:
    """Names and aliases of every ``source: builtin`` command."""
    names: set[str] = set()
    for command in commands:
        if command.get("source") != "builtin":
            continue
        name = command.get("name")
        if not isinstance(name, str) or not name:
            raise ProbeError(f"builtin command without a name: {command!r}")
        names.add(name)
        aliases = command.get("aliases") or []
        if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
            raise ProbeError(f"builtin command {name!r} has malformed aliases: {aliases!r}")
        names.update(aliases)
    return frozenset(names)


def drift_errors(
    live: frozenset[str],
    command_names: Iterable[str],
    *,
    pinned: frozenset[str] = OMP_BUILTIN_COMMANDS,
    namespace: str = COMMAND_NAMESPACE,
) -> list[str]:
    """Every way the live built-ins break the pin or shadow ycc commands."""
    errors = [
        f"live omp built-in '{name}' is missing from OMP_BUILTIN_COMMANDS "
        "(refresh the pin in scripts/generate_omp_commands.py)"
        for name in sorted(live - pinned)
    ]
    if namespace in live:
        errors.append(f"live omp built-in '{namespace}' shadows the command namespace")
    errors.extend(
        f"live omp built-in '{namespace}:{name}' shadows a generated command"
        for name in sorted(command_names)
        if f"{namespace}:{name}" in live
    )
    return errors


def commands_from_frames(lines: Iterable[str]) -> list[dict[str, Any]]:
    """The command list from the first ``get_available_commands`` response frame."""
    for line in lines:
        try:
            frame = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(frame, dict) or frame.get("command") != "get_available_commands":
            continue
        if frame.get("success") is not True:
            raise ProbeError(f"get_available_commands failed: {frame}")
        commands = frame.get("data", {}).get("commands")
        if not isinstance(commands, list):
            raise ProbeError("get_available_commands returned no command list")
        return [command for command in commands if isinstance(command, dict)]
    raise ProbeError("no get_available_commands response")


def probe(omp: str) -> list[dict[str, Any]]:
    """One isolated ``omp --mode rpc`` session; returns its command list."""
    with tempfile.TemporaryDirectory(prefix="ycc-omp-builtins.") as tmp:
        root = Path(tmp)
        agent = root / "home/.omp/agent"
        agent.mkdir(parents=True)
        (agent / "models.yml").write_text(NULL_MODELS, encoding="utf-8")
        (agent / "config.yml").write_text("mcp:\n  startupTimeoutMs: 0\n", encoding="utf-8")
        work = root / "work"
        work.mkdir()
        env = {
            # The omp directory first: an npm/bun install is a shim that needs its runtime alongside.
            "PATH": os.pathsep.join((str(Path(omp).resolve().parent), "/usr/local/bin", "/usr/bin", "/bin")),
            "LANG": "C.UTF-8",
            "TERM": "dumb",
            "NO_COLOR": "1",
            "HOME": str(root / "home"),
            "TMPDIR": str(root),
            **{f"XDG_{kind}_HOME": str(root / kind.lower()) for kind in ("CONFIG", "DATA", "STATE", "CACHE")},
        }
        request = json.dumps({"id": "cmds", "type": "get_available_commands"}) + "\n"
        argv = [omp, "--mode", "rpc", "--no-session", "--no-title", "--model", "ycc-null/null-model"]
        try:
            result = subprocess.run(
                argv, input=request, capture_output=True, text=True, cwd=work, env=env, timeout=PROBE_TIMEOUT
            )
        except subprocess.TimeoutExpired as error:
            raise ProbeError(f"omp --mode rpc timed out after {PROBE_TIMEOUT}s") from error
        if result.returncode != 0:
            raise ProbeError(f"omp --mode rpc exited {result.returncode}: {result.stderr.strip()[-500:]}")
        return commands_from_frames(result.stdout.splitlines())


def env_required() -> bool:
    """True when YCC_OMP_REQUIRED is set to a truthy value (1, true, yes, on)."""
    return os.environ.get("YCC_OMP_REQUIRED", "").strip().lower() in {"1", "true", "yes", "on"}


def live_omp(*, require: bool = False) -> str | None:
    """The omp binary to probe; None (with a warning) when the check may skip.

    With ``require`` a missing or too-old omp raises ProbeError instead of skipping.
    """
    omp = os.environ.get("OMP_BIN") or shutil.which("omp")
    if not omp or not os.access(omp, os.X_OK):
        if require:
            raise ProbeError("omp not found (set OMP_BIN or install omp) and a live omp is required")
        print("[warn] omp not found (set OMP_BIN or install omp): skipping the built-in command drift check")
        return None
    try:
        result = subprocess.run([omp, "--version"], capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise ProbeError(f"omp --version timed out after {PROBE_TIMEOUT}s") from error
    if result.returncode != 0:
        raise ProbeError(f"omp --version exited {result.returncode}: {result.stderr.strip()[-500:]}")
    version = result.stdout
    if version_key(version) < version_key(MIN_OMP_VERSION):
        if require:
            raise ProbeError(f"{version.strip()} is older than {MIN_OMP_VERSION} and a live omp is required")
        print(f"[warn] {version.strip()} is older than {MIN_OMP_VERSION}: skipping the built-in command drift check")
        return None
    # Absolute, not resolved (a shim keeps its name): the probe runs in a temp cwd.
    return os.path.abspath(omp)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--commands-json", type=Path, help="saved RPC frames (JSONL) instead of a live probe")
    parser.add_argument(
        "--require",
        action="store_true",
        help="fail instead of skipping when omp is missing or older than MIN_OMP_VERSION "
        "(also enabled by YCC_OMP_REQUIRED=1)",
    )
    args = parser.parse_args(argv)
    if args.require and args.commands_json is not None:
        # A saved frame needs no omp, so --require would silently assert nothing.
        parser.error("--require checks a live omp and cannot be combined with --commands-json")
    # YCC_OMP_REQUIRED only gates the live probe; it is ignored for saved frames.
    require = args.require or env_required()
    try:
        if args.commands_json is not None:
            commands = commands_from_frames(args.commands_json.read_text(encoding="utf-8").splitlines())
        else:
            omp = live_omp(require=require)
            if omp is None:
                return 0
            commands = probe(omp)
        live = builtin_names(commands)
    except (OSError, ProbeError) as error:
        print(f"omp_builtin_commands.py: {error}", file=sys.stderr)
        return 1
    names = [command.name for command in load_commands(SRC_DIR, build_catalog(SRC_DIR))]
    errors = drift_errors(live, names)
    for message in errors:
        print(f"omp_builtin_commands.py: {message}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK: {len(live)} live omp built-in names and aliases are pinned; none shadows a ycc command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
