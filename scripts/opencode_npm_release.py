#!/usr/bin/env python3
"""Check a maintainer product tag before CI packs/publishes the opt-in opencode npm package."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PACKAGE = Path("packages/opencode/ycc-opencode/package.json")
CANONICAL = Path("ycc/.claude-plugin/plugin.json")
CHECKER = Path("ycc/skills/bundle-release/scripts/release_versions.py")
PRODUCT_TAG = re.compile(r"refs/tags/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


class ReleaseGuardError(Exception):
    """The tag, source, or generated package is not safe to publish."""


def run(root: Path, *command: str) -> str:
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ReleaseGuardError(f"cannot run {command[0]}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ReleaseGuardError(f"{' '.join(command)} failed: {detail or result.returncode}")
    return result.stdout.strip()


def manifest(root: Path, rel: Path) -> dict[str, object]:
    try:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseGuardError(f"{rel}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReleaseGuardError(f"{rel}: expected JSON object")
    return data


def check_release(root: Path, event: str, ref: str, sha: str) -> str:
    """Require exact vX.Y.Z/canonical/generated parity and a tag reachable from fetched origin/main."""
    if event != "push":
        raise ReleaseGuardError("publication requires a tag push event")
    match = PRODUCT_TAG.fullmatch(ref)
    if match is None:
        raise ReleaseGuardError("publication requires a refs/tags/vX.Y.Z product tag")
    version = ".".join(match.groups())
    if re.fullmatch(r"[0-9a-fA-F]{40}", sha) is None:
        raise ReleaseGuardError("event SHA must be a full commit SHA")
    head = run(root, "git", "rev-parse", "--verify", "HEAD^{commit}")
    tagged = run(root, "git", "rev-parse", "--verify", f"{ref}^{{commit}}")
    if head != tagged or head.lower() != sha.lower():
        raise ReleaseGuardError("checked-out HEAD, product tag, and event SHA must identify the same commit")
    run(root, "git", "merge-base", "--is-ancestor", head, "refs/remotes/origin/main")
    canonical = manifest(root, CANONICAL).get("version")
    package = manifest(root, PACKAGE)
    if package.get("name") != "@yandy-r/ycc-opencode":
        raise ReleaseGuardError(f"{PACKAGE}: unexpected package name")
    if version != canonical or package.get("version") != canonical:
        raise ReleaseGuardError(
            f"version mismatch: tag={version!r}, canonical={canonical!r}, npm={package.get('version')!r}"
        )
    # The shared checker also requires every other included native/npm manifest,
    # and catches drift in marketplaces and generated lockstep version surfaces.
    checked = run(root, sys.executable, str(root / CHECKER), "check", str(root))
    if checked != version:
        raise ReleaseGuardError(f"lockstep checker reported {checked!r}, expected {version!r}")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    args = parser.parse_args(argv)
    try:
        version = check_release(args.root.resolve(), args.event, args.ref, args.sha)
    except ReleaseGuardError as exc:
        print(f"opencode_npm_release: {exc}", file=sys.stderr)
        return 1
    print(f"OK: v{version}, canonical and generated versions agree; tagged commit is reachable from origin/main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
