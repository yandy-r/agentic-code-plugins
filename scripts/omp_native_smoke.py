#!/usr/bin/env python3
"""Assertions for scripts/test-omp-native-packages.sh (opt-in live OMP install harness).

Each subcommand reads files the harness captured from real `omp` runs and exits non-zero
with a message on the first violation. Nothing here invokes omp or a model.

  installed      LIST_JSON SOURCE_ROOT VERSION  ycc@ycc in `plugin list --json` at VERSION; the
                                                cache copy matches the package root byte-for-byte
  mcp-installed  LIST_JSON SOURCE_ROOT VERSION  the same proof for ycc-mcp@ycc
  commands       RPC_OUT SOURCE_ROOT            every packaged command and skill registered
                                                (`ycc:<cmd>` file commands, `skill:<name>` skills)
  agents         RPC_OUT SOURCE_ROOT            probe output: every packaged agent loaded from the
                                                install with its generated `model:` kept
  absent         LIST_JSON OMP_HOME             no ycc plugin, registry entry or runtime link remains
  mcp-absent     LIST_JSON OMP_HOME             the same proof for ycc-mcp@ycc
  mcp-fixture    SOURCE_ROOT                    add the fixture-only stdio stub servers (`smoke`,
                                                `smokeoff` with enabled: false) to the ycc-mcp copy
  mcp-stub       PATH                           write the stdio MCP stub (user override fixture)
  mcp-listed     RPC_OUT SHIPPED_MCP LIST_JSON  MCP probe (omp's loadAllMCPConfigs): every server in
                                                SHIPPED_MCP is discovered as `ycc-mcp:<server>` from
                                                the install with no ycc-mcp server shadowed and a
                                                distinct OAuth credential id per distinct http url
                                                (YAN-1291); the browser filter drops exactly playwright
                                                when browser.enabled; env placeholders arrive literally
  mcp-state      RPC_OUT SERVER STATE TOOLS     SERVER (or `ycc-mcp:*`) is absent|plugin|native in
                                                the MCP probe; TOOLS (comma list or -) are minted
                                                tool names get_state's system prompt must carry
                                                (the server started), or must not with a `!` prefix
  bump           SOURCE_ROOT VERSION FILE...    rewrite `version` (and catalog versions) in FILEs
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from generate_omp_packages import mcp_connection_key

PACKAGE = "ycc"
PLUGIN_ID = "ycc@ycc"
PACKAGE_ROOT = Path("packages/omp/ycc")
MCP_PACKAGE = "ycc-mcp"
MCP_PLUGIN_ID = "ycc-mcp@ycc"
MCP_PACKAGE_ROOT = Path("packages/omp/ycc-mcp")
# Fixture-only stdio servers the harness adds to its ycc-mcp copy (never to the export).
STUB_SERVERS = {"smoke": True, "smokeoff": False}
# Servers omp's browser filter (mcp/config.ts filterBrowserMCPServers) drops while the built-in
# browser is enabled. Asserted exactly, so a new browser-like server fails loudly.
BROWSER_FILTERED = {"playwright"}
STUB_SOURCE = """import json, sys
name = sys.argv[1]
for line in sys.stdin:
    try:
        m = json.loads(line)
    except ValueError:
        continue
    if m.get("id") is None:
        continue
    if m.get("method") == "initialize":
        r = {"protocolVersion": m["params"].get("protocolVersion", "2024-11-05"),
             "capabilities": {"tools": {}}, "serverInfo": {"name": name, "version": "0"}}
    elif m.get("method") == "tools/list":
        r = {"tools": [{"name": name + "_ping", "description": "marker " + name,
                        "inputSchema": {"type": "object", "properties": {}}}]}
    else:
        r = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\\n")
    sys.stdout.flush()
"""
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


def installed_entry(list_json: Path, plugin_id: str = PLUGIN_ID) -> dict[str, Any]:
    payload = load_json(list_json)
    matches = [item for item in payload.get("marketplace", []) if item.get("id") == plugin_id]
    if len(matches) != 1 or not matches[0].get("entries"):
        raise SmokeError(f"{list_json}: expected exactly one {plugin_id} install, got {matches}")
    entry: dict[str, Any] = matches[0]["entries"][0]
    return entry


def tree(root: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path.relative_to(root): (path.read_bytes(), path.stat().st_mode & 0o111)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def check_installed(
    list_json: Path, source_root: Path, version: str, plugin_id: str = PLUGIN_ID, package_root: Path = PACKAGE_ROOT
) -> str:
    entry = installed_entry(list_json, plugin_id)
    if entry.get("version") != version or entry.get("scope") != "user":
        raise SmokeError(f"{plugin_id}: expected user scope at {version}, got {entry}")
    install = Path(str(entry.get("installPath", "")))
    if not install.is_dir():
        raise SmokeError(f"{plugin_id}: installPath {install} does not exist")
    expected, actual = tree(source_root / package_root), tree(install)
    # omp adds generated runtime files (for example .lsp.json) beside the copied payload.
    missing = sorted(str(rel) for rel in expected if rel not in actual)
    changed = sorted(str(rel) for rel in expected if rel in actual and actual[rel] != expected[rel])
    if missing or changed:
        raise SmokeError(f"{install}: cache differs from the package root; missing={missing[:5]} changed={changed[:5]}")
    count = len(expected)
    return f"{plugin_id} {version} at {install} ({count} payload files byte-identical, executable bits preserved)"


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


def check_absent(list_json: Path, omp_home: Path, package: str = PACKAGE, plugin_id: str = PLUGIN_ID) -> str:
    payload = load_json(list_json)
    if any(package == str(item.get("id", "")).split("@", 1)[0] for item in payload.get("marketplace", [])):
        raise SmokeError(f"{list_json}: {package} still installed")
    registry = omp_home / "plugins/installed_plugins.json"
    if registry.is_file() and plugin_id in load_json(registry).get("plugins", {}):
        raise SmokeError(f"{registry}: still lists {plugin_id}")
    link = omp_home / "plugins/node_modules" / package
    if link.exists() or link.is_symlink():
        raise SmokeError(f"{link}: runtime link remains")
    lock = omp_home / "plugins/omp-plugins.lock.json"
    if lock.is_file() and package in load_json(lock).get("plugins", {}):
        raise SmokeError(f"{lock}: still lists {package}")
    caches = sorted((omp_home / "plugins/cache/plugins").glob(f"ycc___{package}___*"))
    if caches:
        raise SmokeError(f"plugin cache remains: {[str(path) for path in caches]}")
    return f"no {plugin_id} install, registry entry, lock entry, runtime link or cache remains"


def write_stub(path: Path) -> str:
    path.write_text(STUB_SOURCE, encoding="utf-8")
    return f"wrote stdio MCP stub {path}"


def add_mcp_fixture(source_root: Path) -> str:
    """Append the stub servers to the fixture's ycc-mcp `.mcp.json`; the shipped text stays a prefix."""
    root = source_root / MCP_PACKAGE_ROOT
    config = root / ".mcp.json"
    text = config.read_text(encoding="utf-8")
    shipped: dict[str, Any] = json.loads(text)["mcpServers"]
    tail = "\n  }\n}\n"
    if not text.endswith(tail) or set(STUB_SERVERS) & set(shipped):
        raise SmokeError(f"{config}: unexpected layout; cannot append the fixture stubs")
    stubs = {
        name: {"command": "python3", "args": ["${OMP_PLUGIN_ROOT}/mcp_stub.py", name]}
        | ({} if enabled else {"enabled": False})
        for name, enabled in STUB_SERVERS.items()
    }
    entries = "".join(f",\n    {json.dumps(name)}: {json.dumps(value)}" for name, value in stubs.items())
    updated = text[: -len(tail)] + entries + tail
    if json.loads(updated)["mcpServers"] != shipped | stubs:
        raise SmokeError(f"{config}: appending the stubs changed a shipped server")
    config.write_text(updated, encoding="utf-8")
    write_stub(root / "mcp_stub.py")
    return f"fixture-only stubs {sorted(STUB_SERVERS)} appended to {config}; shipped servers unchanged"


def mcp_probe(rpc_out: Path) -> dict[str, Any]:
    probe = next((c.get("description", "") for c in rpc_commands(rpc_out) if c.get("name") == "mcp-probe"), None)
    if not isinstance(probe, str) or not probe.startswith(PROBE_PREFIX):
        raise SmokeError(f"{rpc_out}: MCP probe failed: {probe!r}")
    payload = json.loads(probe[len(PROBE_PREFIX) :])
    if not isinstance(payload, dict) or not isinstance(payload.get("servers"), dict):
        raise SmokeError(f"{rpc_out}: MCP probe returned no server map: {probe[:300]!r}")
    return payload


def system_prompt(rpc_out: Path) -> str:
    for frame in frames(rpc_out):
        if frame.get("type") == "response" and frame.get("command") == "get_state":
            if frame.get("success") is not True:
                raise SmokeError(f"{rpc_out}: get_state failed: {frame}")
            return json.dumps(frame.get("data", {}).get("systemPrompt"))
    raise SmokeError(f"{rpc_out}: no get_state response")


def check_mcp_listed(rpc_out: Path, shipped_mcp: Path, list_json: Path) -> str:
    shipped: dict[str, dict[str, Any]] = load_json(shipped_mcp)["mcpServers"]
    config = Path(str(installed_entry(list_json, MCP_PLUGIN_ID).get("installPath", ""))) / ".mcp.json"
    probe = mcp_probe(rpc_out)
    servers: dict[str, dict[str, Any]] = {
        name: value for name, value in probe["servers"].items() if name.startswith(f"{MCP_PACKAGE}:")
    }
    # Equivalent connections would collapse onto the first definition (capability/index.ts
    # dedupe); the generator disambiguates them (YAN-1291), so the shipped config has none.
    owners: dict[str, str] = {}
    for name, server in shipped.items():
        first = owners.setdefault(mcp_connection_key(server), name)
        if first != name:
            raise SmokeError(f"{shipped_mcp}: {name} has the same connection as {first}")
    expected = {f"{MCP_PACKAGE}:{name}" for name in shipped}
    stubs = {f"{MCP_PACKAGE}:{name}" for name, enabled in STUB_SERVERS.items() if enabled}
    missing = sorted(expected - set(servers))
    extra = sorted(set(servers) - expected - stubs)
    if missing or extra:
        raise SmokeError(f"{rpc_out}: discovered {sorted(servers)}; missing={missing} unexpected={extra}")
    shadowed = sorted(name for name in probe.get("shadowed", []) if name.startswith(f"{MCP_PACKAGE}:"))
    if shadowed:
        raise SmokeError(f"{rpc_out}: shadowed {shadowed}, expected none")
    # Each distinct http url logs in to its own auth-storage row (mcp/oauth-flow.ts mcpOAuthCredentialId).
    credential_ids: dict[str, str] = probe.get("credentialIds", {})
    urls = {name: server["url"] for name, server in servers.items() if isinstance(server.get("url"), str)}
    if set(credential_ids) & set(servers) != set(urls):
        raise SmokeError(
            f"{rpc_out}: credential ids for {sorted(set(credential_ids) & set(servers))}, urls {sorted(urls)}"
        )
    holders: dict[str, str] = {}
    for name in sorted(urls):
        holder = holders.setdefault(credential_ids[name], name)
        if holder != name and urls[holder] != urls[name]:
            raise SmokeError(f"{rpc_out}: {name} and {holder} share OAuth credential id {credential_ids[name]}")
    if len(set(holders)) != len(set(urls.values())):
        raise SmokeError(f"{rpc_out}: {len(set(holders))} credential ids for {len(set(urls.values()))} distinct urls")
    problems: list[str] = []
    for name in sorted(expected):
        found, source = servers[name], shipped[name.split(":", 1)[1]]
        if found.get("provider") != "claude-plugins" or found.get("path") != str(config):
            problems.append(f"{name}: from {found.get('provider')} {found.get('path')}, not {config}")
        for key in ("args", "url", "env"):
            if key in source and found.get(key) != source[key]:
                problems.append(f"{name}: {key} {found.get(key)!r} != shipped {source[key]!r}")
    if problems:
        raise SmokeError(f"{rpc_out}: {problems[:6]}")
    # The probe reports which servers survive the browser filter a session applies with the
    # live browser.enabled setting (sdk.ts shouldFilterBrowserMCPForPrelude).
    dropped = sorted(set(servers) - set(probe.get("browserKept", [])))
    filtered = BROWSER_FILTERED if probe.get("browserEnabled") else set()
    expected_dropped = sorted(f"{MCP_PACKAGE}:{name}" for name in filtered)
    if dropped != expected_dropped:
        raise SmokeError(f"{rpc_out}: browser filter drops {dropped}, expected {expected_dropped}")
    xero = servers.get(f"{MCP_PACKAGE}:xero", {}).get("env")
    linear = {name: credential_ids[name] for name in sorted(urls) if name.startswith(f"{MCP_PACKAGE}:linear")}
    return (
        f"{len(expected)} servers discovered from {config}: {sorted(expected)}; "
        f"shadowed: {shadowed}; {len(set(holders))} OAuth credential ids for {len(urls)} http servers "
        f"({json.dumps(linear)}); "
        f"browser filter drops {dropped} (browser.enabled={probe.get('browserEnabled')}); "
        f"{MCP_PACKAGE}:xero env {json.dumps(xero)}"
    )


def check_mcp_state(rpc_out: Path, server: str, state: str, tools: str) -> str:
    """SERVER's source in the probe, and which minted tool names get_state's prompt carries.

    TOOLS is a comma list (or `-`): a plain name must be in the prompt (the server started)
    unless STATE is `absent`; a `!`-prefixed name (a prefix works too) must never be there.
    """
    servers: dict[str, dict[str, Any]] = mcp_probe(rpc_out)["servers"]
    prompt = system_prompt(rpc_out)
    wildcard = server.endswith(":*")
    found = sorted(name for name in servers if name.startswith(server[:-1])) if wildcard else []
    provider = {"plugin": "claude-plugins", "native": "native", "absent": None}.get(state, "?")
    if provider == "?" or (wildcard and provider is not None):
        raise SmokeError(f"unknown state {state!r} for {server}")
    if provider is None and (found or server in servers):
        raise SmokeError(f"{rpc_out}: {server} still loaded: {found or servers[server]}")
    if provider is not None and servers.get(server, {}).get("provider") != provider:
        raise SmokeError(f"{rpc_out}: {server} expected from {provider}, got {servers.get(server)}")
    notes: list[str] = []
    for tool in [] if tools == "-" else tools.split(","):
        forbidden = tool.startswith("!") or provider is None
        name = tool.removeprefix("!")
        if forbidden == (name in prompt):
            raise SmokeError(
                f"{rpc_out}: {name} {'still' if forbidden else 'not'} in get_state's system prompt"
                + ("" if forbidden else f" ({server} loaded but did not start)")
            )
        notes.append(f"no {name}" if forbidden else f"started: {name} in get_state")
    where = "absent" if provider is None else f"from {provider}"
    return f"{server} {where}" + "".join(f"; {note}" for note in notes)


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
    "mcp-installed": (
        3,
        lambda a: check_installed(Path(a[0]), Path(a[1]), a[2], MCP_PLUGIN_ID, MCP_PACKAGE_ROOT),
    ),
    "mcp-absent": (2, lambda a: check_absent(Path(a[0]), Path(a[1]), MCP_PACKAGE, MCP_PLUGIN_ID)),
    "mcp-fixture": (1, lambda a: add_mcp_fixture(Path(a[0]))),
    "mcp-stub": (1, lambda a: write_stub(Path(a[0]))),
    "mcp-listed": (3, lambda a: check_mcp_listed(Path(a[0]), Path(a[1]), Path(a[2]))),
    "mcp-state": (4, lambda a: check_mcp_state(Path(a[0]), a[1], a[2], a[3])),
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
