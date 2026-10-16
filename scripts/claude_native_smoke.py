#!/usr/bin/env python3
"""Helpers for the opt-in Claude native package install harness.

Subcommands are invoked by scripts/test-claude-native-packages.sh inside a
scrubbed lab environment. Nothing here starts a Claude session, an MCP server,
or any checked-in hook; the only hook executed is the lab-copied WorktreeCreate
script against a disposable Git repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKET_NAME = "ycc-native-lab"
CANONICAL = "ycc"
FORBIDDEN_ENV = re.compile(
    r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|PROXY|HERDR|ANTHROPIC|OPENAI|GITHUB|GH_|AWS|SSH|NODE_OPTIONS"
)
LAB_PATH_ENV = (
    "HOME",
    "CLAUDE_CONFIG_DIR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "TMPDIR",
)


class CheckFailed(Exception):
    pass


def check(label: str, expected: Any, actual: Any) -> None:
    if expected != actual:
        raise CheckFailed(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"ok: {label}")


def generated_keys() -> list[str]:
    root = REPO_ROOT / "packages" / "claude"
    keys = sorted(path.name for path in root.iterdir() if (path / ".claude-plugin" / "plugin.json").is_file())
    check("generated add-ons", ["ycc-all", "ycc-hooks", "ycc-mcp"], keys)
    return keys


def env_check(root: Path) -> None:
    """The lab must hold no credentials/proxies/HERDR state and only lab-contained paths."""
    leaked = sorted(name for name in os.environ if FORBIDDEN_ENV.search(name.upper()))
    check("no credential/proxy/HERDR environment", [], leaked)
    base = root.resolve()
    for name in LAB_PATH_ENV:
        value = os.environ.get(name, "")
        check(f"{name} inside lab", True, bool(value) and Path(value).resolve().is_relative_to(base))


def build_market(dest: Path) -> None:
    """Local marketplace: canonical ycc copied from source plus every generated add-on."""
    keys = generated_keys()
    if CANONICAL in keys:
        raise CheckFailed("canonical ycc must not be duplicated under packages/claude")
    skip = shutil.ignore_patterns("__pycache__", ".git")
    names = [CANONICAL, *keys]
    for name in names:
        source = REPO_ROOT / name if name == CANONICAL else REPO_ROOT / "packages" / "claude" / name
        shutil.copytree(source, dest / name, ignore=skip)
    catalog = {
        "name": MARKET_NAME,
        "owner": {"name": "native-smoke"},
        "plugins": [{"name": name, "source": f"./{name}"} for name in names],
    }
    (dest / ".claude-plugin").mkdir(exist_ok=True)
    (dest / ".claude-plugin" / "marketplace.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print("marketplace plugins: " + ", ".join(names))


def assert_list(listing: Path, mode: str, market: Path) -> None:
    items = json.loads(listing.read_text(encoding="utf-8"))
    if mode == "empty":
        check("no plugins before installing ycc-all", [], items)
        return
    catalog = json.loads((market / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    version = json.loads((market / CANONICAL / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    expected = sorted(f"{plugin['name']}@{catalog['name']}" for plugin in catalog["plugins"])
    check("installed plugin ids (ycc-all dependencies)", expected, sorted(item.get("id") for item in items))
    check("all plugins enabled", [True] * len(items), [item.get("enabled") for item in items])
    check("all plugins user scope", ["user"] * len(items), [item.get("scope") for item in items])
    check(
        "reported versions are lockstep",
        {i: version for i in expected},
        {item["id"]: item.get("version") for item in items},
    )


def lab_git(*args: str, cwd: Path, env: dict[str, str]) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=30, check=False)
    if done.returncode != 0:
        raise CheckFailed(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def worktrees(repo: Path, env: dict[str, str]) -> set[Path]:
    out = lab_git("worktree", "list", "--porcelain", cwd=repo, env=env)
    return {Path(line.removeprefix("worktree ")).resolve() for line in out.splitlines() if line.startswith("worktree ")}


def hook_smoke(market: Path, root: Path) -> None:
    """Run the lab-copied WorktreeCreate hook against a disposable fixture repository."""
    script = market / "ycc-hooks" / "hooks" / "worktree-create.sh"
    source = REPO_ROOT / CANONICAL / "settings" / "hooks" / "worktree-create.sh"
    check("copied hook is executable", True, os.access(script, os.X_OK))
    check("copied hook matches canonical source", source.read_bytes(), script.read_bytes())

    base = root.resolve()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "TMPDIR": os.environ["TMPDIR"],
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    }
    fixture = base / "hook-fixture" / "fixture-repo"
    wt_root = base / "hook-worktrees"
    fixture.mkdir(parents=True)
    lab_git("init", "-q", "-b", "main", cwd=fixture, env=env)
    (fixture / "fixture.txt").write_text("disposable fixture only\n", encoding="utf-8")
    lab_git("add", "fixture.txt", cwd=fixture, env=env)
    lab_git(
        "-c", "user.name=native-smoke", "-c", "user.email=native-smoke@localhost",
        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture",
        cwd=fixture, env=env,
    )  # fmt: skip

    payload = json.dumps(
        {"name": "smoke", "cwd": str(fixture), "session_id": "native-smoke", "hook_event_name": "WorktreeCreate"}
    )
    done = subprocess.run(
        ["bash", str(script)],
        input=payload,
        cwd=fixture,
        env={**env, "YCC_WORKTREE_ROOT": str(wt_root)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    check("hook exit status", 0, done.returncode)
    lines = done.stdout.splitlines()
    check("hook emitted exactly one path line", 1, len(lines))
    returned = Path(lines[0])
    check("returned path is the contained worktree", wt_root / "fixture-repo-smoke", returned)
    check("returned path is a directory", True, returned.is_dir())
    common = lab_git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=returned, env=env).strip()
    check("worktree belongs to fixture repo", (fixture / ".git").resolve(), Path(common).resolve())
    check("fixture git worktree list includes returned path", True, returned.resolve() in worktrees(fixture, env))
    check("worktree branch", "smoke", lab_git("rev-parse", "--abbrev-ref", "HEAD", cwd=returned, env=env).strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env-check").add_argument("root", type=Path)
    sub.add_parser("market").add_argument("dest", type=Path)
    listing = sub.add_parser("assert-list")
    listing.add_argument("listing", type=Path)
    listing.add_argument("mode", choices=("empty", "installed"))
    listing.add_argument("market", type=Path)
    hook = sub.add_parser("hook")
    hook.add_argument("market", type=Path)
    hook.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "env-check":
            env_check(args.root)
        elif args.command == "market":
            build_market(args.dest)
        elif args.command == "assert-list":
            assert_list(args.listing, args.mode, args.market)
        else:
            hook_smoke(args.market, args.root)
    except (CheckFailed, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"claude_native_smoke: CHECK FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
