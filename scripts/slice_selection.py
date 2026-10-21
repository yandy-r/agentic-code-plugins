"""Per-entry selection for install_slices.py (``--entries`` and ``list``).

Selector names are what users type: the entry name for directories, the file
stem for files (``implementor.md`` / ``implementor.toml`` -> ``implementor``).
Helper entries (``_shared``, ``shared``, ``ycc-shared``, a unit's ``extra``
entries and every entry of a slice's later units) are never selectable; they
ship with any selection and leave only with the last owned entry.

After a selective install, the canonical sources of the selected entries are
scanned for ``ycc:<name>`` references so missing skills and agents can be
reported per target (warn only).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import NoReturn, Protocol, TypeVar

HELPER_NAMES = frozenset({"_shared", "shared", "ycc-shared"})
KINDS = ("skills", "agents")
NOUN = {"skills": "skill", "agents": "agent"}
# Agents that only make sense when a dispatching skill is available.
DISPATCHED_AGENTS = frozenset(
    {
        "backport-conflict-resolver",
        "pr-comment-fixer",
        "release-fix-applier",
        "releaser",
        "review-fixer",
        "git-cleanup",
    }
)
# Targets whose skills also resolve from the cross-tool ~/.agents/skills.
AGENTS_SKILLS_READERS = frozenset({"codex", "opencode", "cursor"})

Ref = tuple[str, bool]  # (referenced name, written as '/ycc:<name>')


class UnitLike(Protocol):
    """The install_slices.Unit fields selection reads."""

    @property
    def dest(self) -> str: ...

    @property
    def extra(self) -> Mapping[str, str]: ...

    @property
    def strict(self) -> bool: ...


U = TypeVar("U", bound=UnitLike)


class ContextLike(Protocol):
    """The install_slices.Context fields selection reads."""

    @property
    def home(self) -> Path: ...

    @property
    def state(self) -> dict[str, list[str]]: ...


def selector(name: str, src: Path) -> str:
    return Path(name).stem if src.is_file() else name


def selectable(entries: Mapping[str, Path], extra: Iterable[str]) -> dict[str, str]:
    """Selector name -> entry name for the user-pickable entries of a slice's first unit."""
    hidden = HELPER_NAMES | set(extra)
    return {selector(name, src): name for name, src in entries.items() if name not in hidden}


def parse_entries(raw: str) -> list[str]:
    names: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def plan_selection(
    units_entries: Sequence[Mapping[str, Path]],
    extra: Iterable[str],
    raw: str,
    owned_first: Iterable[str],
    present_first: Iterable[str],
    install: bool,
    where: tuple[str, str],
) -> list[frozenset[str] | None] | str:
    """Entry names each unit acts on for ``--entries`` (None = the whole unit), or an error line.

    Install ships the chosen entries plus every helper. Remove takes the chosen
    entries; helpers go only when no other non-helper entry remains in the first
    unit's destination, recorded in state or present on disk (a 'base' mirror
    records nothing). ``where`` is (slice, target) for the message.
    """
    hidden = HELPER_NAMES | set(extra)
    names = selectable(units_entries[0], extra)
    wanted = parse_entries(raw)
    unknown = [name for name in wanted if name not in names] or ([] if wanted else ["(none)"])
    if unknown:
        noun = "entry" if len(unknown) == 1 else "entries"
        valid = ", ".join(sorted(names))
        return f"[err] unknown {where[0]} {noun} for {where[1]}: {', '.join(unknown)} (valid: {valid})"
    chosen = frozenset(names[name] for name in wanted)
    helpers = frozenset(n for n in units_entries[0] if n in hidden)
    rest = len(units_entries) - 1
    if install:
        return [chosen | helpers, *(frozenset(entries) for entries in units_entries[1:])]
    if {n for n in (*owned_first, *present_first) if n not in hidden} - chosen:
        return [chosen, *([frozenset()] * rest)]
    owned_helpers = frozenset(n for n in owned_first if n in hidden)
    return [chosen | helpers | owned_helpers, *([None] * rest)]


def print_selectable(
    args: argparse.Namespace,
    specs: Mapping[tuple[str, str], Sequence[U]],
    entries_of: Callable[[U], Mapping[str, Path]],
) -> int:
    """``list``: print the user-selectable names of a slice's first unit, sorted, one per line.

    Claude has no commands slice of its own: ``commands`` lists its skills.
    """
    slice_name = "skills" if (args.target, args.slice) == ("claude", "commands") else args.slice
    units = specs.get((args.target, slice_name))
    if units:
        for name in sorted(selectable(entries_of(units[0]), units[0].extra)):
            print(name)
    return 0


def plan_run(
    args: argparse.Namespace,
    units: Sequence[U],
    entries_of: Callable[[U], Mapping[str, Path]],
    home: Path,
    state: Mapping[str, list[str]],
    fail: Callable[[str], NoReturn],
) -> list[tuple[U, frozenset[str] | None]] | None:
    """(unit, pick) pairs one install_slices run acts on (pick None = the whole unit); None after an error.

    Without ``--entries`` every unit runs whole. ``fail`` rejects ``--entries`` on
    slices that cannot narrow (strict carriers, claude commands remove).
    """
    if args.entries is None:
        return [(unit, None) for unit in units]
    if not units or any(unit.strict for unit in units):
        fail("--entries is not supported for this slice (strict carriers, claude commands remove)")
    entries = [entries_of(unit) for unit in units]
    first = home / units[0].dest
    present = [n for n in entries[0] if (first / n).exists() or (first / n).is_symlink()]
    owned = state.get(str(first), [])
    where = (args.slice, args.target)
    plan = plan_selection(entries, units[0].extra, args.entries, owned, present, args.action == "install", where)
    if isinstance(plan, str):
        print(plan, file=sys.stderr)
        return None
    return [(unit, pick) for unit, pick in zip(units, plan, strict=True) if pick is None or pick]


def print_dependency_warnings(
    args: argparse.Namespace,
    kind: str,
    conflicts: int,
    repo_root: Path,
    specs: Mapping[tuple[str, str], Sequence[U]],
    ctx: ContextLike,
) -> None:
    """After a clean selective install of ``kind`` on ``args.target``, print its dependency warnings."""
    if conflicts or args.action != "install" or args.entries is None:
        return
    dests = {k: specs[(args.target, k)][0].dest for k in KINDS if (args.target, k) in specs}
    selected = parse_entries(args.entries)
    for line in dependency_warnings(repo_root, ctx.home, args.target, kind, selected, ctx.state, dests):
        print(line)


class References:
    """``ycc:<name>`` references in the canonical ycc skill and agent sources."""

    def __init__(self, repo_root: Path) -> None:
        self.root = repo_root / "ycc"
        self.names: dict[str, frozenset[str]] = {}
        for kind in KINDS:
            base = self.root / kind
            found = (p.stem for p in base.iterdir() if not p.name.startswith((".", "_"))) if base.is_dir() else ()
            self.names[kind] = frozenset(found)
        everything = self.names["skills"] | self.names["agents"]
        alternation = "|".join(sorted(map(re.escape, everything), key=len, reverse=True)) or "(?!)"
        self.pattern = re.compile(rf"(?<![A-Za-z0-9_-])(/?)ycc:({alternation})(?![A-Za-z0-9_-])")
        self._cache: dict[tuple[str, str], frozenset[Ref]] = {}

    def of(self, kind: str, name: str) -> frozenset[Ref]:
        key = (kind, name)
        if key not in self._cache:
            src = self.root / kind / name if kind == "skills" else self.root / kind / f"{name}.md"
            files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file()) if src.is_dir() else []
            refs: set[Ref] = set()
            for path in files:
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                refs.update((m.group(2), bool(m.group(1))) for m in self.pattern.finditer(text))
            self._cache[key] = frozenset(refs)
        return self._cache[key]

    def kinds(self, ref: Ref, referrer_kind: str, referrer: str) -> list[str]:
        """Kinds a reference may mean; a name both skill and agent satisfies either."""
        name, slash = ref
        kinds = [kind for kind in KINDS if name in self.names[kind]]
        if name == referrer:
            # A unit naming itself means the other kind of the same name, if any.
            kinds = [kind for kind in kinds if kind != referrer_kind]
        elif slash and "skills" in kinds:
            kinds = ["skills"]  # '/ycc:<name>' is a slash command
        return kinds

    def dispatchers(self, agent: str) -> list[str]:
        """Skills that reference the agent as 'ycc:<agent>' (not as a slash command)."""
        return sorted(s for s in self.names["skills"] if (agent, False) in self.of("skills", s))


class Availability:
    """Whether a skill or agent is usable on one target after the install.

    ``YCC_PENDING_SKILLS`` / ``YCC_PENDING_AGENTS`` (comma-separated, ``*`` for
    every entry; set by the installer) name entries another slice of the same
    run installs on this target.
    """

    def __init__(self, home: Path, target: str, state: Mapping[str, list[str]], dests: Mapping[str, str]) -> None:
        self.home = home
        self.target = target
        self.state = state
        self.dests = dests
        self.pending = {kind: set(parse_entries(os.environ.get(f"YCC_PENDING_{kind.upper()}", ""))) for kind in KINDS}
        self.plugin = False
        if target == "claude":
            plugins = home / ".claude/plugins/installed_plugins.json"
            try:
                self.plugin = plugins.is_file() and '"ycc@ycc"' in plugins.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                self.plugin = False
        elif target == "codex":
            self.plugin = (home / ".codex/plugins/ycc").exists()

    def has(self, kind: str, name: str) -> bool:
        if self.plugin or name in self.pending[kind] or "*" in self.pending[kind]:
            return True
        dest = self.home / self.dests[kind]
        recorded = self.state.get(str(dest), [])
        if any(c in recorded or (dest / c).exists() for c in (name, f"{name}.md", f"{name}.toml")):
            return True
        shared_home = self.home / ".agents/skills" / name
        return kind == "skills" and self.target in AGENTS_SKILLS_READERS and shared_home.exists()


def dependency_warnings(
    repo_root: Path,
    home: Path,
    target: str,
    kind: str,
    selected: Iterable[str],
    state: Mapping[str, list[str]],
    dests: Mapping[str, str],
) -> list[str]:
    """Warn lines for references the selected entries make to units missing on the target."""
    if kind not in KINDS:
        return []
    refs = References(repo_root)
    avail = Availability(home, target, state, dests)
    missing: dict[tuple[str, str], set[str]] = {}
    lines: list[str] = []
    for name in sorted(set(selected)):
        dispatched = kind == "agents" and name in DISPATCHED_AGENTS and "skills" in dests
        skills = refs.dispatchers(name) if dispatched else []
        if skills and not any(avail.has("skills", s) for s in skills):
            lines.append(
                f"[!!]  {target}: agent '{name}' is dispatched only by {', '.join(skills)}, none installed"
                f" — add one: ycc sync --target {target} --intent skills --skills {skills[0]}"
            )
        for ref in sorted(refs.of(kind, name)):
            kinds = [k for k in refs.kinds(ref, kind, name) if k in dests]
            if ref[0] in skills and kinds == ["skills"]:
                continue  # covered by the dispatcher warning above
            if kinds and not any(avail.has(k, ref[0]) for k in kinds):
                missing.setdefault((kinds[0], ref[0]), set()).add(name)
    for (ref_kind, ref_name), referrers in sorted(missing.items()):
        lines.append(
            f"[!!]  {target}: {NOUN[ref_kind]} '{ref_name}' is referenced by {', '.join(sorted(referrers))}"
            f" but not installed — add it: ycc sync --target {target} --intent {ref_kind} --{ref_kind} {ref_name}"
        )
    return lines
