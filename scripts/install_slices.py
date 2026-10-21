#!/usr/bin/env python3
"""Install or remove one slice (skills, agents, commands) of a ycc bundle.

A slice lands entry by entry in the tool's own user directory
(``~/.claude/skills/<name>``, ``~/.codex/skills/<name>``, ...) instead of
registering the whole plugin. Entries are copied, with plugin-root paths and
``ycc:`` namespace prefixes rewritten so each one works without the plugin.

Ownership: the names this helper installed are recorded per destination in
``installed-units.json`` next to the managed-config state file. An existing
entry is replaced only when it is recorded there or already byte-identical to
what would be written (for example a copy left by the 'base' step); anything
else is someone else's and needs ``--force``. Entries other than the ones the
slice ships are never touched.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from slice_selection import plan_run, print_dependency_warnings, print_selectable

REPO_ROOT = Path(__file__).resolve().parent.parent
SLICES = ("skills", "agents", "commands", "hooks")
NATIVE_ROOT_PLACEHOLDER = "<installed ycc plugin root>"


@dataclass(frozen=True)
class Unit:
    """One source directory mirrored entry by entry into one destination."""

    src: str  # repo-relative directory whose entries are installed
    dest: str  # destination directory, relative to $HOME
    # Extra entries installed under a fixed name: {dest_name: repo-relative path}.
    extra: dict[str, str] = field(default_factory=dict)
    # Install only these entry names from src (empty = every entry).
    only: tuple[str, ...] = ()
    # Strict filesystem carriers track bytes, reject local edits, and preflight
    # the entire slice before changing any entry (including symlink ancestors).
    strict: bool = False


# Claude has no commands slice of its own: skills are the slash commands, so
# 'commands' aliases 'skills' there. Wrappers an older ycc installed under this
# directory are retired by ownership (see retire_legacy_commands).
LEGACY_COMMANDS_DEST = ".claude/commands"

SPECS: dict[tuple[str, str], tuple[Unit, ...]] = {
    ("claude", "skills"): (Unit("ycc/skills", ".claude/skills"),),
    ("claude", "agents"): (Unit("ycc/agents", ".claude/agents"),),
    ("cursor", "skills"): (Unit("packages/cursor/ycc/skills", ".cursor/skills"),),
    ("cursor", "agents"): (Unit("packages/cursor/ycc/agents", ".cursor/agents"),),
    ("cursor", "commands"): (Unit("packages/cursor/ycc/commands", ".cursor/commands", strict=True),),
    ("cursor", "hooks"): (
        Unit("packages/cursor/ycc-hooks/hooks", ".cursor/hooks", only=("herdr-session-start.sh",), strict=True),
    ),
    # Codex keeps shared helpers beside skills/ in the plugin; standalone
    # skills find them at ~/.codex/skills/_shared instead.
    ("codex", "skills"): (
        Unit(".codex-plugin/ycc/skills", ".codex/skills", extra={"_shared": ".codex-plugin/ycc/shared"}),
    ),
    ("codex", "agents"): (Unit(".codex-plugin/agents", ".codex/agents"),),
    ("opencode", "skills"): (
        Unit(".opencode-plugin/skills", ".config/opencode/skills"),
        Unit(".opencode-plugin", ".config/opencode", only=("shared",)),
    ),
    # Cross-tool ~/.agents/skills (skills only). The shared helpers sit beside
    # skills/ as ~/.agents/ycc-shared; ~/.agents/plugins (Codex) is never listed.
    ("agents", "skills"): (
        Unit(".agents-plugin/skills", ".agents/skills"),
        Unit(".agents-plugin", ".agents", only=("ycc-shared",)),
    ),
    ("opencode", "agents"): (Unit(".opencode-plugin/agents", ".config/opencode/agents"),),
    ("opencode", "commands"): (Unit(".opencode-plugin/commands", ".config/opencode/commands"),),
}


@dataclass
class Context:
    home: Path
    force: bool
    rewrites: list[tuple[str, str]]
    pattern: re.Pattern[str] | None
    state: dict[str, list[str]]
    hashes: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    skills_dir: Path | None = None
    skills_pending: bool = False


def rewrites_for(target: str, home: Path) -> list[tuple[str, str]]:
    """Literal (old, new) path rewrites that detach a slice from its plugin root."""
    if target == "claude":
        # Absolute, not '~': these paths sit inside quoted shell strings.
        return [("${CLAUDE_PLUGIN_ROOT}/skills/", f"{home}/.claude/skills/")]
    if target == "codex":
        return [
            ("~/.codex/plugins/ycc/skills/", "~/.codex/skills/"),
            ("~/.codex/plugins/ycc/shared/", "~/.codex/skills/_shared/"),
            ("../../../shared/", "../../_shared/"),
            ("../../shared/", "../_shared/"),
            # Native prompt templates: expand the placeholder to the installed standalone location.
            (f"{NATIVE_ROOT_PLACEHOLDER}/shared/references/", f"{home}/.codex/skills/_shared/references/"),
        ]
    if target == "cursor":
        # Only reference documents need rebasing; script tokens have shell quoting semantics.
        return [("${CURSOR_PLUGIN_ROOT}/skills/_shared/references/", f"{home}/.cursor/skills/_shared/references/")]
    return []


def namespace_pattern(target: str) -> re.Pattern[str] | None:
    """Match 'ycc:<name>' / '/ycc:<name>' for every ycc skill, agent and command."""
    if target not in ("claude", "codex"):
        return None
    names: set[str] = set()
    for kind in SLICES:
        root = REPO_ROOT / "ycc" / kind
        if root.is_dir():
            names.update(p.stem for p in root.iterdir() if not p.name.startswith((".", "_")))
    if not names:
        return None
    alternation = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9_-])(/?)ycc:({alternation})(?![A-Za-z0-9_-])")


def state_path() -> Path:
    """installed-units.json beside the managed-config state file."""
    managed = os.environ.get("YCC_MANAGED_CONFIG_STATE")
    if managed:
        return Path(managed).expanduser().parent / "installed-units.json"
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "ycc" / "installed-units.json"


def load_state(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    units = data.get("units", {}) if isinstance(data, dict) else {}
    return {k: list(v) for k, v in units.items() if isinstance(v, list)}


def save_state(path: Path, units: dict[str, list[str]], hashes: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "units": {k: sorted(v) for k, v in sorted(units.items()) if v}}
    if hashes:
        payload["sha256"] = hashes
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".installed-units.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def shipped_entries(unit: Unit) -> dict[str, Path]:
    """Map destination entry name -> source path for everything the unit ships."""
    src = REPO_ROOT / unit.src
    if not src.is_dir():
        raise SystemExit(f"[err] slice source not found: {src}")
    entries = {
        p.name: p
        for p in sorted(src.iterdir())
        if not p.name.startswith(".") and (not unit.only or p.name in unit.only)
    }
    for name, rel in unit.extra.items():
        extra_src = REPO_ROOT / rel
        if extra_src.exists():
            entries[name] = extra_src
    return entries


_NATIVE_HEADER = re.compile(
    r"## Native prompt substitution\n\nBefore forwarding any prompt, replace every `"
    + re.escape(NATIVE_ROOT_PLACEHOLDER)
    + r"` with the absolute installed ycc plugin root \(resolve `[^`]*` from this document's directory\)\. "
    r"Forward only absolute resource paths; keep the user's project as cwd\.\n\n"
)


def transform_tree(root: Path, rewrites: list[tuple[str, str]], pattern: re.Pattern[str] | None) -> None:
    """Apply path and namespace rewrites to every UTF-8 text file under root."""
    files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for old, replacement in rewrites:
            new = new.replace(old, replacement)
        # The root-substitution header is moot once every placeholder is expanded.
        if new != text and new.count(NATIVE_ROOT_PLACEHOLDER) == 1:
            new = _NATIVE_HEADER.sub("", new)
        if pattern is not None:
            new = pattern.sub(r"\1\2", new)
        if new != text:
            path.write_text(new, encoding="utf-8")


def project_cursor_init(name: str, staged: Path) -> None:
    """Restore the file-copy init bytes the package replaces with package-local resources."""
    if name != "init" or not staged.is_dir() or not (staged / "scripts/generate-agent-catalog.sh").is_file():
        return
    if "${CURSOR_PLUGIN_ROOT}/resources/mcp/select-mcp.py" not in (staged / "SKILL.md").read_text(encoding="utf-8"):
        return
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cursor_native_resources import restore_installer_init

    restore_installer_init(staged.parent)


def stage(
    name: str, src: Path, staging: Path, rewrites: list[tuple[str, str]], pattern: re.Pattern[str] | None
) -> Path:
    staged = staging / name
    staging.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, staged, symlinks=True)
    else:
        shutil.copy2(src, staged)
    project_cursor_init(name, staged)
    transform_tree(staged, rewrites, pattern)
    return staged


def same_entry(a: Path, b: Path) -> bool:
    """True when two files or trees have identical names and contents."""
    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and os.readlink(a) == os.readlink(b)
    if a.is_file() and b.is_file():
        return filecmp.cmp(a, b, shallow=False)
    if not (a.is_dir() and b.is_dir()):
        return False
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(same_entry(a / d, b / d) for d in cmp.common_dirs)


def delete_entry(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def entry_hash(path: Path) -> str:
    """Fingerprint the bytes and executable bit of strict carrier files."""
    return hashlib.sha256(path.read_bytes() + str(path.stat().st_mode & 0o111).encode()).hexdigest()


def strict_unit(unit: Unit, ctx: Context, install: bool) -> int:
    """Plan all ownership decisions before mutating a Cursor carrier directory."""
    dest = ctx.home / unit.dest
    key = str(dest)
    for parent in (dest, *dest.parents):
        if parent.is_symlink():
            print(f"[err] refusing symlinked Cursor carrier destination: {parent}", file=sys.stderr)
            return 1
        if parent == ctx.home:
            break
    entries = shipped_entries(unit)
    owned = set(ctx.state.get(key, []))
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        skills_dir = ctx.skills_dir or ctx.home / ".cursor/skills"
        rewrites = [("${CURSOR_PLUGIN_ROOT}/skills/", f"{skills_dir}/")] if unit.dest == ".cursor/commands" else []
        if install and unit.dest == ".cursor/commands" and not ctx.skills_pending:
            missing = [name for name in entries if not (skills_dir / Path(name).stem / "SKILL.md").is_file()]
            if missing:
                print(
                    f"[err] Cursor commands require installed skills at {skills_dir}: {', '.join(missing)}; "
                    "run install.sh install --target cursor --only skills,commands first",
                    file=sys.stderr,
                )
                return 1
        staged = {name: stage(name, src, staging, rewrites, None) for name, src in entries.items()}
        actions: list[str] = []
        for name in sorted((set(entries) | owned) if install else owned):
            if not name or Path(name).name != name or name in {".", ".."}:
                print("[err] invalid Cursor carrier ownership state", file=sys.stderr)
                return 1
            target = dest / name
            if exists(target):
                wanted = staged.get(name)
                plain = target.is_file() and not target.is_symlink()
                matches = wanted is not None and plain and same_entry(wanted, target)
                recorded = ctx.hashes.get(str(target))
                unchanged = target.is_file() and not target.is_symlink() and recorded == entry_hash(target)
                if not (matches and install or unchanged or ctx.force):
                    print(
                        f"[err] Cursor carrier ownership collision: {target}; "
                        "not owned or locally edited (use --force)",
                        file=sys.stderr,
                    )
                    return 1
                actions.append(name)
            elif install and name in entries:
                actions.append(name)
        if ctx.dry_run:
            return 0
        if install:
            dest.mkdir(parents=True, exist_ok=True)
        for name in actions:
            target = dest / name
            if exists(target):
                delete_entry(target)
            ctx.hashes.pop(str(target), None)
            if install and name in staged:
                shutil.move(str(staged[name]), str(target))
                ctx.hashes[str(target)] = entry_hash(target)
        if install:
            ctx.state[key] = sorted(entries)
        else:
            ctx.state.pop(key, None)
            if dest.is_dir() and not any(dest.iterdir()):
                dest.rmdir()
    print(f"[ok] Cursor {unit.dest} {'installed' if install else 'removed'}")
    return 0


def install_unit(unit: Unit, ctx: Context, pick: frozenset[str] | None = None) -> int:
    """Install the unit's entries; with pick, only those names, merging state and pruning nothing."""
    if unit.strict:
        return strict_unit(unit, ctx, True)
    dest = ctx.home / unit.dest
    key = str(dest)
    owned = set(ctx.state.get(key, []))
    entries = {name: src for name, src in shipped_entries(unit).items() if pick is None or name in pick}
    conflicts = 0
    installed: set[str] = set()
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        for name, src in entries.items():
            staged = stage(name, src, staging, ctx.rewrites, ctx.pattern)
            target = dest / name
            if exists(target):
                if same_entry(staged, target):
                    installed.add(name)
                    continue
                base = stage(name, src, staging / "base", [], None)
                if name not in owned and not ctx.force and not same_entry(base, target):
                    print(
                        f"[err] refusing to replace {target}: not installed by ycc (re-run with --force)",
                        file=sys.stderr,
                    )
                    conflicts += 1
                    continue
                delete_entry(target)
            shutil.move(str(staged), str(target))
            installed.add(name)
    for name in sorted(owned - set(entries)) if pick is None else ():
        stale = dest / name
        if exists(stale):
            delete_entry(stale)
            print(f"[ok]  removed {stale} (no longer shipped)")
    ctx.state[key] = sorted(installed if pick is None else owned | installed)
    print(f"[ok]  {len(installed)} entr{'y' if len(installed) == 1 else 'ies'} up to date in {dest}")
    return conflicts


def remove_unit(unit: Unit, ctx: Context, pick: frozenset[str] | None = None) -> int:
    """Remove the unit's entries; with pick, only those names (state drops only them)."""
    if unit.strict:
        return strict_unit(unit, ctx, False)
    dest = ctx.home / unit.dest
    key = str(dest)
    owned = set(ctx.state.get(key, []))
    left = sorted(owned - pick) if pick is not None else []
    if not dest.is_dir():
        print(f"[ok]  nothing to remove: {dest}")
        ctx.state[key] = left  # save_state drops empty lists
        return 0
    entries = shipped_entries(unit)
    removed = 0
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        for name in sorted(owned | set(entries) if pick is None else pick):
            target = dest / name
            if not exists(target):
                continue
            ours = name in owned or ctx.force
            if not ours and name in entries:
                # A copy the 'base' step left behind is identical to the bundle.
                plain = same_entry(entries[name], target)
                base = stage(name, entries[name], staging / "base", [], None)
                ours = (
                    plain
                    or same_entry(base, target)
                    or same_entry(stage(name, entries[name], staging, ctx.rewrites, ctx.pattern), target)
                )
            if ours:
                delete_entry(target)
                removed += 1
            else:
                print(f"[!!]  kept {target}: not installed by ycc (re-run with --force to remove it)")
    ctx.state[key] = left
    print(f"[ok]  removed {removed} entr{'y' if removed == 1 else 'ies'} from {dest}")
    if dest != ctx.home and not any(dest.iterdir()):
        dest.rmdir()
        print(f"[ok]  removed empty directory {dest}")
    return 0


def retire_legacy_commands(ctx: Context) -> None:
    """Delete the command wrappers ycc recorded under ~/.claude/commands.

    Only names recorded in installed-units.json go; foreign or unrecorded
    entries (even with --force) stay, and the directory goes only when this
    leaves it empty.
    """
    dest = ctx.home / LEGACY_COMMANDS_DEST
    key = str(dest)
    removed = 0
    left: list[str] = []
    for name in ctx.state.get(key, []):
        if name in ("", ".", "..") or Path(name).name != name:
            continue  # state is user-editable; a recorded name is a plain entry
        target = dest / name
        if not exists(target):
            continue
        # ycc only ever wrote wrapper files; a directory here is user data.
        if not (target.is_symlink() or target.is_file()):
            print(f"[!!]  kept {target}: not a ycc wrapper file")
            continue
        try:
            target.unlink()
            removed += 1
        except OSError as err:
            print(f"[!!]  could not retire {target}: {err}", file=sys.stderr)
            left.append(name)
    if left:
        ctx.state[key] = left
    else:
        ctx.state.pop(key, None)
    if not removed:
        return
    print(f"[ok]  retired {removed} legacy command wrapper{'' if removed == 1 else 's'} from {dest}")
    if not dest.is_symlink() and dest.is_dir() and not any(dest.iterdir()):
        dest.rmdir()
        print(f"[ok]  removed empty directory {dest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("install", "remove", "list"))
    parser.add_argument("--target", required=True, choices=sorted({t for t, _ in SPECS}))
    parser.add_argument("--slice", required=True, choices=SLICES)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--entries", help="Comma-separated names to install or remove (see 'list'); helpers follow")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preflight strict Cursor carrier ownership without writing"
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=os.environ.get("YCC_CURSOR_SKILLS_HOME"),
        help="Installed skills directory referenced by Cursor commands",
    )
    parser.add_argument(
        "--skills-pending",
        action="store_true",
        help="Preflight only: skills are scheduled in the same installer run",
    )
    args = parser.parse_args(argv)

    if args.action == "list":
        return print_selectable(args, SPECS, shipped_entries)
    install = args.action == "install"
    claude_commands = args.target == "claude" and args.slice == "commands"
    if args.skills_pending and not args.dry_run:
        parser.error("--skills-pending requires --dry-run")
    slice_name = "skills" if claude_commands and install else args.slice
    # Removing claude 'commands' only retires recorded legacy wrappers.
    units = () if claude_commands and not install else SPECS.get((args.target, slice_name))
    if units is None:
        print(f"[err] target '{args.target}' has no '{args.slice}' slice", file=sys.stderr)
        return 1
    if args.dry_run and any(not unit.strict for unit in units):
        parser.error("--dry-run is supported for strict Cursor commands/hooks carriers only")
    home = Path.home()
    path = state_path()
    hashes = json.loads(path.read_text(encoding="utf-8")).get("sha256", {}) if path.is_file() else {}
    ctx = Context(
        home,
        args.force,
        rewrites_for(args.target, home),
        namespace_pattern(args.target),
        load_state(path),
        hashes,
        args.dry_run,
        args.skills_dir,
        args.skills_pending,
    )
    if (plan := plan_run(args, units, shipped_entries, home, ctx.state, parser.error)) is None:
        return 1
    run = install_unit if install else remove_unit
    conflicts = 0
    try:
        for unit, pick in plan:
            conflicts += run(unit, ctx, pick)
        # Wrappers are redundant only once the skills are in place (all of them: a selection keeps them).
        retire = claude_commands or (install and slice_name == "skills" and args.entries is None)
        if args.target == "claude" and not conflicts and retire:
            retire_legacy_commands(ctx)
    finally:
        if not args.dry_run and (not conflicts or not any(unit.strict for unit in units)):
            save_state(path, ctx.state, ctx.hashes)
    print_dependency_warnings(args, slice_name, conflicts, REPO_ROOT, SPECS, ctx)
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
