#!/usr/bin/env python3
"""Assertions for scripts/test-omp-native-packages.sh (opt-in live OMP install harness).

Each subcommand reads files the harness captured from real `omp` runs and exits non-zero
with a message on the first violation. Nothing here invokes omp or a model.

  installed  LIST_JSON SOURCE_ROOT VERSION   ycc@ycc in `plugin list --json` at VERSION; the
                                             cache copy matches the package root byte-for-byte
  commands   RPC_OUT SOURCE_ROOT             every packaged command and skill registered
                                             (`ycc:<cmd>` file commands, `skill:<name>` skills)
  agents     RPC_OUT SOURCE_ROOT             probe output: every packaged agent loaded from the
                                             install with its generated `model:` kept
  absent     LIST_JSON OMP_HOME              no ycc plugin, registry entry or runtime link remains
  bump       SOURCE_ROOT VERSION FILE...     rewrite `version` (and catalog versions) in FILEs
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

PACKAGE = "ycc"
PLUGIN_ID = "ycc@ycc"
PACKAGE_ROOT = Path("packages/omp/ycc")
PROBE_PREFIX = "PROBE "
NAME_LINE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
MODEL_LINE = re.compile(r"^model:\s*['\"]?([^'\"\n]+)['\"]?\s*$", re.MULTILINE)


class SmokeError(Exception):
    """A captured omp result that contradicts the generated package."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SmokeError(f"{path}: unreadable JSON: {exc}") from exc


def frames(path: Path) -> Iterator[dict[str, Any]]:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                frame = json.loads(line)
            except ValueError as exc:
                raise SmokeError(f"{path}:{number}: not an RPC JSON frame: {exc}") from exc
            if isinstance(frame, dict):
                yield frame


def rpc_commands(path: Path) -> list[dict[str, Any]]:
    for frame in frames(path):
        if frame.get("type") == "response" and frame.get("command") == "get_available_commands":
            if frame.get("success") is not True:
                raise SmokeError(f"{path}: get_available_commands failed: {frame}")
            commands = frame.get("data", {}).get("commands")
            if not isinstance(commands, list):
                raise SmokeError(f"{path}: get_available_commands returned no command list")
            return [command for command in commands if isinstance(command, dict)]
    raise SmokeError(f"{path}: no get_available_commands response")


def installed_entry(list_json: Path) -> dict[str, Any]:
    payload = load_json(list_json)
    matches = [item for item in payload.get("marketplace", []) if item.get("id") == PLUGIN_ID]
    if len(matches) != 1 or not matches[0].get("entries"):
        raise SmokeError(f"{list_json}: expected exactly one {PLUGIN_ID} install, got {matches}")
    entry: dict[str, Any] = matches[0]["entries"][0]
    return entry


def tree(root: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path.relative_to(root): (path.read_bytes(), path.stat().st_mode & 0o111)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def check_installed(list_json: Path, source_root: Path, version: str) -> str:
    entry = installed_entry(list_json)
    if entry.get("version") != version or entry.get("scope") != "user":
        raise SmokeError(f"{PLUGIN_ID}: expected user scope at {version}, got {entry}")
    install = Path(str(entry.get("installPath", "")))
    if not install.is_dir():
        raise SmokeError(f"{PLUGIN_ID}: installPath {install} does not exist")
    expected, actual = tree(source_root / PACKAGE_ROOT), tree(install)
    # omp adds generated runtime files (for example .lsp.json) beside the copied payload.
    missing = sorted(str(rel) for rel in expected if rel not in actual)
    changed = sorted(str(rel) for rel in expected if rel in actual and actual[rel] != expected[rel])
    if missing or changed:
        raise SmokeError(f"{install}: cache differs from the package root; missing={missing[:5]} changed={changed[:5]}")
    count = len(expected)
    return f"{PLUGIN_ID} {version} at {install} ({count} payload files byte-identical, executable bits preserved)"


def skill_names(skills: Path) -> set[str]:
    names: set[str] = set()
    for skill in skills.glob("*/SKILL.md"):
        match = NAME_LINE.search(skill.read_text(encoding="utf-8"))
        names.add(match.group(1) if match else skill.parent.name)
    return names


def check_commands(rpc_out: Path, source_root: Path) -> str:
    root = source_root / PACKAGE_ROOT
    commands = rpc_commands(rpc_out)
    registered = {(command.get("name"), command.get("source")) for command in commands}
    expected_commands = {f"{PACKAGE}:{path.stem}" for path in (root / "commands").glob("*.md")}
    expected_skills = {f"skill:{name}" for name in skill_names(root / "skills")}
    missing = sorted(name for name in expected_commands if (name, "file") not in registered)
    missing += sorted(name for name in expected_skills if (name, "skill") not in registered)
    if missing:
        raise SmokeError(f"{rpc_out}: not registered: {missing}")
    extra = sorted(
        str(name)
        for name, source in registered
        if isinstance(name, str) and name.startswith(f"{PACKAGE}:") and name not in expected_commands
    )
    if extra:
        raise SmokeError(f"{rpc_out}: unexpected {PACKAGE}: commands: {extra}")
    return f"{len(expected_commands)} {PACKAGE}:<skill> commands and {len(expected_skills)} skill: entries registered"


def check_agents(rpc_out: Path, source_root: Path) -> str:
    probe = next((c.get("description", "") for c in rpc_commands(rpc_out) if c.get("name") == "probe"), None)
    if not isinstance(probe, str) or not probe.startswith(PROBE_PREFIX):
        raise SmokeError(f"{rpc_out}: agent probe failed: {probe!r}")
    loaded = {name: (model, path) for name, model, path in json.loads(probe[len(PROBE_PREFIX) :])}
    agents_dir = source_root / PACKAGE_ROOT / "agents"
    problems: list[str] = []
    with_model = 0
    for agent in sorted(agents_dir.glob("*.md")):
        text = agent.read_text(encoding="utf-8")
        name_match, model_match = NAME_LINE.search(text), MODEL_LINE.search(text)
        name = name_match.group(1) if name_match else agent.stem
        expected = model_match.group(1) if model_match else None
        with_model += expected is not None
        if name not in loaded:
            problems.append(f"{name}: not discovered")
            continue
        model, path = loaded[name]
        if model != expected:
            problems.append(f"{name}: model {model!r}, expected {expected!r}")
        if not path or f"/plugins/cache/plugins/{PACKAGE}___{PACKAGE}___" not in path:
            problems.append(f"{name}: loaded from {path!r}, not the {PLUGIN_ID} install")
    if problems:
        raise SmokeError(f"{rpc_out}: agent problems: {problems[:8]}")
    return f"{len(list(agents_dir.glob('*.md')))} agents loaded from the install; {with_model} keep their @role model"


def check_absent(list_json: Path, omp_home: Path) -> str:
    payload = load_json(list_json)
    if any(PACKAGE == str(item.get("id", "")).split("@", 1)[0] for item in payload.get("marketplace", [])):
        raise SmokeError(f"{list_json}: {PACKAGE} still installed")
    registry = omp_home / "plugins/installed_plugins.json"
    if registry.is_file() and PLUGIN_ID in load_json(registry).get("plugins", {}):
        raise SmokeError(f"{registry}: still lists {PLUGIN_ID}")
    link = omp_home / "plugins/node_modules" / PACKAGE
    if link.exists() or link.is_symlink():
        raise SmokeError(f"{link}: runtime link remains")
    lock = omp_home / "plugins/omp-plugins.lock.json"
    if lock.is_file() and PACKAGE in load_json(lock).get("plugins", {}):
        raise SmokeError(f"{lock}: still lists {PACKAGE}")
    caches = sorted((omp_home / "plugins/cache/plugins").glob(f"ycc___{PACKAGE}___*"))
    if caches:
        raise SmokeError(f"plugin cache remains: {[str(path) for path in caches]}")
    return f"no {PLUGIN_ID} install, registry entry, lock entry, runtime link or cache remains"


def bump(source_root: Path, version: str, files: list[str]) -> str:
    for rel in files:
        path = source_root / rel
        payload = load_json(path)
        if "plugins" in payload:
            payload.setdefault("metadata", {})["version"] = version
            for entry in payload["plugins"]:
                entry["version"] = version
        else:
            payload["version"] = version
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"set {version} in {', '.join(files)}"


COMMANDS: dict[str, tuple[int, Callable[[list[str]], str]]] = {
    "installed": (3, lambda a: check_installed(Path(a[0]), Path(a[1]), a[2])),
    "commands": (2, lambda a: check_commands(Path(a[0]), Path(a[1]))),
    "agents": (2, lambda a: check_agents(Path(a[0]), Path(a[1]))),
    "absent": (2, lambda a: check_absent(Path(a[0]), Path(a[1]))),
}


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "bump":
        print(bump(Path(argv[2]), argv[3], argv[4:]))
        return 0
    if len(argv) < 2 or argv[1] not in COMMANDS or len(argv) - 2 != COMMANDS[argv[1]][0]:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(COMMANDS[argv[1]][1](argv[2:]))
    except (SmokeError, OSError, ValueError, KeyError) as exc:
        print(f"omp_native_smoke {argv[1]}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
