#!/usr/bin/env python3
"""Assertions for the opt-in Codex native package smoke harness."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from generate_codex_common import HOME_INSTALL_PLUGIN_ROOT, SOURCE_PLUGIN_PATH
from generate_codex_mcp import build_codex_mcp_config


def canonical_version() -> str:
    version = json.loads(SOURCE_PLUGIN_PATH.read_text(encoding="utf-8")).get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{SOURCE_PLUGIN_PATH}: missing nonempty version")
    return version


def check_version(version_text: str, exact: str | None = None) -> None:
    match = re.fullmatch(r"codex-cli (\d+)\.(\d+)\.(\d+)\s*", version_text)
    actual = tuple(map(int, match.groups())) if match else None
    if exact is not None:
        if actual != tuple(map(int, exact.split("."))):
            raise ValueError(f"Codex {exact} required, got {version_text!r}")
    elif actual is None or actual < (0, 160, 0):
        raise ValueError(f"Codex >=0.160.0 required, got {version_text!r}")


def check_catalog(add_path: Path, available_path: Path, *, payloads_present: bool = True) -> None:
    # Without payload manifests Codex can list catalog entries but not their version.
    version = canonical_version() if payloads_present else None
    add = json.loads(add_path.read_text(encoding="utf-8"))
    if add.get("marketplaceName") != "ycc":
        raise ValueError(f"expected marketplaceName ycc, got {add}")
    listing = json.loads(available_path.read_text(encoding="utf-8"))
    available = {item["pluginId"]: item for item in listing["available"]}
    if listing.get("installed") != [] or set(available) != {"ycc@ycc", "ycc-mcp@ycc"}:
        raise ValueError(f"unexpected initial catalog listing: {listing}")
    for plugin_id, item in available.items():
        if (
            item.get("version") != version
            or item.get("installed")
            or item.get("enabled")
            or item.get("installPolicy") != "AVAILABLE"
        ):
            raise ValueError(f"unexpected available entry for {plugin_id}: {item}")


def file_inventory(root: Path) -> dict[Path, tuple[bytes, bool]]:
    items: dict[Path, tuple[bytes, bool]] = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"unexpected non-regular file in {root}: {path}")
        # Git preserves only the executable bit of a regular file's mode,
        # so comparing raw S_IMODE false-fails across umasks (664 vs 644).
        items[path.relative_to(root)] = (
            path.read_bytes(),
            bool(mode & stat.S_IXUSR),
        )
    return items


def catalog_payload_dirs(catalog_path: Path) -> list[str]:
    """Return the `.codex-plugin/<name>` payload dirs a native catalog names."""
    plugins = json.loads(catalog_path.read_text(encoding="utf-8")).get("plugins")
    if not isinstance(plugins, list) or not plugins:
        raise ValueError(f"{catalog_path}: catalog names no plugins")
    dirs: list[str] = []
    for plugin in plugins:
        source = plugin.get("source") if isinstance(plugin, dict) else None
        path = source.get("path") if isinstance(source, dict) else None
        # One safe segment: no traversal, nesting, absolute, or non-local source.
        match = re.fullmatch(r"\./\.codex-plugin/([A-Za-z0-9][A-Za-z0-9._-]*)", path) if isinstance(path, str) else None
        if match is None or source != {"source": "local", "path": path}:
            raise ValueError(f"{catalog_path}: unsupported plugin source {source!r}")
        name = match.group(1)
        if name in dirs:
            raise ValueError(f"{catalog_path}: duplicate plugin source {path!r}")
        dirs.append(name)
    return dirs


def check_fixture(fresh_export: Path, remote_root: Path) -> None:
    # Compare the full catalog and every payload it names, not only files common
    # to both trees. Other `.codex-plugin/` entries (installer-owned agents/ and
    # config/) and fixture documentation are not installable payloads.
    payloads = [
        Path(".codex-plugin") / name for name in catalog_payload_dirs(fresh_export / ".agents/plugins/marketplace.json")
    ]
    problems: list[str] = []
    for rel in (Path(".agents/plugins"), *payloads):
        for root in (fresh_export / rel, remote_root / rel):
            # rglob follows a symlinked start directory, so reject it up front.
            if root.is_symlink() or (root.exists() and not root.is_dir()):
                raise ValueError(f"unexpected non-directory payload root: {root}")
        expected = file_inventory(fresh_export / rel)
        actual = file_inventory(remote_root / rel)
        missing = sorted(map(str, set(expected) - set(actual)))
        extra = sorted(map(str, set(actual) - set(expected)))
        changed = sorted(str(p) for p in set(expected) & set(actual) if expected[p] != actual[p])
        if missing or extra or changed:
            problems.append(f"{rel}: missing={missing} extra={extra} changed={changed}")
    if problems:
        raise ValueError(f"public fixture drift (bytes/exec bits): {problems}")
    compared = ", ".join(map(str, payloads))
    print(f"PASS public fixture catalog and payloads ({compared}) match fresh native export (bytes + exec bits)")


def check_mcp_list(mcp_path: Path, expected_packages: set[str]) -> None:
    servers = {entry["name"]: entry for entry in json.loads(mcp_path.read_text(encoding="utf-8"))}
    if "ycc-mcp" not in expected_packages:
        if servers:
            raise ValueError(f"skills-only install unexpectedly exposed MCP servers: {sorted(servers)}")
        return
    expected = build_codex_mcp_config()["mcp_servers"]
    if set(servers) != set(expected):
        raise ValueError(f"MCP server set {sorted(servers)} != expected {sorted(expected)}")
    for name, source_cfg in expected.items():
        entry = servers[name]
        if not entry.get("enabled"):
            raise ValueError(f"MCP server {name} is not enabled: {entry}")
        transport = entry["transport"]
        if "url" in source_cfg and transport.get("url") != source_cfg["url"]:
            raise ValueError(f"MCP URL mismatch for {name}: {transport}")
        if "command" in source_cfg:
            if transport.get("command") != source_cfg["command"] or transport.get("args") != source_cfg.get("args", []):
                raise ValueError(f"MCP stdio command mismatch for {name}: {transport}")
    xero = servers["xero"]["transport"]
    if xero.get("env") is not None or set(xero.get("env_vars") or ()) != {"XERO_CLIENT_ID", "XERO_CLIENT_SECRET"}:
        raise ValueError(f"unexpected Xero credential representation in runtime MCP config: {xero}")
    if "${" in json.dumps(servers):
        raise ValueError("untranslated Claude ${...} literal found in runtime MCP config")


def check_installed(
    source_root: Path,
    codex_home: Path,
    plugin_list_path: Path,
    mcp_list_path: Path,
    expected_packages: set[str],
) -> None:
    version = canonical_version()
    if (codex_home.parent / "home/.codex/plugins/ycc").exists() or (codex_home / "plugins/ycc").exists():
        raise ValueError("legacy ~/.codex/plugins/ycc path exists inside isolated sandbox")
    listing = json.loads(plugin_list_path.read_text(encoding="utf-8"))
    installed = {item["pluginId"]: item for item in listing["installed"]}
    expected_ids = {f"{pkg}@ycc" for pkg in expected_packages}
    if set(installed) != expected_ids:
        raise ValueError(f"installed plugin IDs {sorted(installed)} != expected {sorted(expected_ids)}")
    for plugin_id, item in installed.items():
        if not item.get("installed") or not item.get("enabled") or item.get("version") != version:
            raise ValueError(f"plugin {plugin_id} not installed/enabled at {version}: {item}")

    cache_parent = codex_home / "plugins/cache/ycc"
    cached_packages = {path.name for path in cache_parent.iterdir()} if cache_parent.is_dir() else set()
    if cached_packages != expected_packages:
        raise ValueError(f"cached package directories {sorted(cached_packages)} != {sorted(expected_packages)}")

    for pkg in sorted(expected_packages):
        src_pkg = source_root / ".codex-plugin" / pkg
        dst_pkg = cache_parent / pkg / version
        src_inv = file_inventory(src_pkg)
        dst_inv = file_inventory(dst_pkg)
        if set(src_inv) != set(dst_inv):
            missing = sorted(map(str, set(src_inv) - set(dst_inv)))
            extra = sorted(map(str, set(dst_inv) - set(src_inv)))
            raise ValueError(f"{pkg} cache inventory mismatch: missing={missing} extra={extra}")
        for rel, (src_bytes, src_mode) in src_inv.items():
            dst_bytes, dst_mode = dst_inv[rel]
            if src_bytes != dst_bytes or src_mode != dst_mode:
                raise ValueError(
                    f"{pkg}/{rel} cache drift: bytes={src_bytes == dst_bytes} executable={src_mode}->{dst_mode}"
                )
        manifest = json.loads((dst_pkg / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        if any("hooks" in rel.parts or rel.name == "hooks.json" for rel in dst_inv) or "hooks" in manifest:
            raise ValueError(f"{pkg} contains forbidden hook declaration or file")
        if pkg == "ycc":
            if "mcpServers" in manifest or (dst_pkg / ".mcp.json").exists() or not (dst_pkg / "skills").is_dir():
                raise ValueError("ycc cache violates skills-only boundary")
        else:
            if (
                manifest.get("mcpServers") != "./.mcp.json"
                or "skills" in manifest
                or (dst_pkg / "skills").exists()
                or (dst_pkg / "shared").exists()
            ):
                raise ValueError("ycc-mcp cache violates MCP-only boundary")
            raw_mcp = (dst_pkg / ".mcp.json").read_text(encoding="utf-8")
            mcp = json.loads(raw_mcp)
            xero_env = mcp["mcpServers"]["xero"].get("env_vars")
            if (
                "${" in raw_mcp
                or "mcp_servers" in mcp
                or set(xero_env or ()) != {"XERO_CLIENT_ID", "XERO_CLIENT_SECRET"}
            ):
                raise ValueError(f"invalid installed .mcp.json: {mcp['mcpServers']['xero']}")

    check_mcp_list(mcp_list_path, expected_packages)


def check_checkout(add_path: Path, expected_ref: str, profile: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_ref):
        raise ValueError(f"expected full lowercase commit SHA, got {expected_ref!r}")
    staging = Path(json.loads(add_path.read_text(encoding="utf-8"))["installedRoot"])

    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", "-C", str(staging), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if check and proc.returncode:
            raise ValueError(f"git {' '.join(args)} failed in staged checkout: {proc.stderr.strip()}")
        return proc

    head = git("rev-parse", "HEAD").stdout.strip()
    if head != expected_ref:
        raise ValueError(f"{profile} staged HEAD {head} != pinned {expected_ref}")
    sparse = git("sparse-checkout", "list", check=False)
    selected = [line.strip() for line in sparse.stdout.splitlines() if line.strip()]
    if profile == "full":
        enabled = git("config", "--bool", "--get", "core.sparseCheckout", check=False)
        if enabled.returncode not in (0, 1) or enabled.stdout.strip() not in ("", "false"):
            raise ValueError(f"full staged checkout unexpectedly sparse: {enabled.stdout.strip()!r}")
        if selected or sparse.returncode not in (0, 128):
            raise ValueError(f"full staged checkout has sparse selection or invalid state: {selected}")
    elif profile == "sparse":
        expected = {".agents/plugins", ".codex-plugin/ycc", ".codex-plugin/ycc-mcp"}
        missing = sorted(expected - set(selected))
        unexpected = sorted(set(selected) - expected)
        if sparse.returncode or missing or unexpected or len(selected) != len(set(selected)):
            raise ValueError(f"sparse selection {selected} missing {missing} unexpected {unexpected}")
        for key in ("core.sparseCheckout", "core.sparseCheckoutCone"):
            if git("config", "--get", key).stdout.strip() != "true":
                raise ValueError(f"sparse staged checkout lacks {key}=true")
    print(f"PASS {profile} checkout: HEAD={head}; sparse selection={selected or 'none'}")


def check_staging(add_path: Path, profile: str, source_root: Path | None = None) -> None:
    staging = Path(json.loads(add_path.read_text(encoding="utf-8"))["installedRoot"])
    catalog = staging / ".agents/plugins/marketplace.json"
    if not catalog.is_file():
        raise ValueError(f"{profile} staging is missing requested catalog: {catalog}")
    if source_root is None:
        sentinel = staging / "outside-sparse/sentinel"
        if profile == "full":
            if sentinel.read_text(encoding="utf-8") != "outside sparse selection\n":
                raise ValueError("full checkout lost fixture sentinel")
        elif sentinel.exists():
            raise ValueError("sparse checkout retained outside-selection sentinel")
    else:
        check_fixture(source_root, staging)
        # Full clones must retain every top-level fixture entry. Sparse clones must
        # omit unselected directories (cone-mode Git may still keep root files).
        for path in source_root.iterdir():
            if path.name in {".git", ".agents", ".codex-plugin"}:
                continue
            present = (staging / path.name).exists()
            if profile == "full" and not present or profile != "full" and path.is_dir() and present:
                raise ValueError(f"unexpected {path.name} presence in {profile} staging")
    for pkg in ("ycc", "ycc-mcp"):
        payload = staging / ".codex-plugin" / pkg / ".codex-plugin/plugin.json"
        if payload.is_file() != (profile != "catalog-only"):
            raise ValueError(f"unexpected payload presence for {pkg} in {profile}")
    print(f"PASS {profile} staging: full/sparse selection and both payload roots checked")


def check_failed_install(codex_home: Path, stderr_path: Path) -> None:
    error = stderr_path.read_text(encoding="utf-8")
    if not any(message in error for message in ("plugin source path is not a directory", "missing plugin.json")):
        raise ValueError(f"unexpected catalog-only install failure: {error}")
    cache = codex_home / "plugins/cache/ycc"
    if any((cache / pkg).exists() for pkg in ("ycc", "ycc-mcp")):
        raise ValueError("catalog-only failed installation left a package cache")
    print("PASS catalog-only sparse install rejected absent payload; neither package cached")


def resolve_installed_helper(codex_home: Path) -> Path:
    skill = codex_home / "plugins/cache/ycc/ycc" / canonical_version() / "skills/git-cleanup/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    if HOME_INSTALL_PLUGIN_ROOT in text or "Bundled paths are relative to this SKILL.md's directory" not in text:
        raise ValueError(f"{skill} is missing native relative-path guidance or retains installer symlink paths")
    match = re.search(r"`((?:\.\./)+shared/scripts/release-state\.sh) get`", text)
    if not match:
        raise ValueError(f"could not extract relative release-state.sh command from {skill}")
    helper = (skill.parent / match.group(1)).resolve(strict=True)
    cache_root = (codex_home / "plugins/cache/ycc/ycc" / canonical_version()).resolve(strict=True)
    if cache_root not in helper.parents or not os.access(helper, os.X_OK):
        raise ValueError(f"resolved helper {helper} is outside {cache_root} or not executable")
    return helper


def run_helper(helper: Path, project_dir: Path, codex_home: Path) -> None:
    expected_cwd = project_dir.resolve(strict=True)
    if Path.cwd().resolve(strict=True) != expected_cwd:
        raise ValueError(f"helper check must start in {expected_cwd}, got {Path.cwd()}")
    if (codex_home.parent / "home/.codex/plugins/ycc").exists() or (codex_home / "plugins/ycc").exists():
        raise ValueError("legacy ~/.codex/plugins/ycc symlink exists before helper execution")
    proc = subprocess.run(
        [str(helper), "get"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if Path.cwd().resolve(strict=True) != expected_cwd:
        raise ValueError("helper changed process working directory")
    if proc.stdout != "present=0\n" or proc.stderr:
        raise ValueError(f"unexpected release-state output: stdout={proc.stdout!r} stderr={proc.stderr!r}")
    print(f"helper argv: {[str(helper), 'get']!r}")
    print(f"helper exit={proc.returncode} cwd_before={expected_cwd} cwd_after={Path.cwd()}")
    print(f"helper stdout={proc.stdout!r} stderr={proc.stderr!r}")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--ignored"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if status.stdout or status.stderr:
        raise ValueError(f"helper dirtied user repository: {status.stdout!r} {status.stderr!r}")
    print("PASS helper output present=0; user repository remains clean; no legacy symlink")


def main() -> None:
    cmd, *args = sys.argv[1:]
    if cmd == "version":
        check_version(args[0], args[1] if args[1:] else None)
    elif cmd == "catalog":
        check_catalog(Path(args[0]), Path(args[1]), payloads_present=args[2:] != ["--catalog-only"])
    elif cmd == "staging":
        check_staging(Path(args[0]), args[1], Path(args[2]) if args[2:] else None)
    elif cmd == "checkout":
        check_checkout(Path(args[0]), args[1], args[2])
    elif cmd == "fixture":
        check_fixture(Path(args[0]), Path(args[1]))
    elif cmd == "failed-install":
        check_failed_install(Path(args[0]), Path(args[1]))
    elif cmd == "installed":
        check_installed(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]), set(args[4:]))
    elif cmd == "helper-path":
        print(resolve_installed_helper(Path(args[0])))
    elif cmd == "helper-run":
        run_helper(Path(args[0]), Path(args[1]), Path(args[2]))
    else:
        raise SystemExit(f"unknown subcommand: {cmd}")


if __name__ == "__main__":
    main()
