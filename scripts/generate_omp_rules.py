#!/usr/bin/env python3
"""Flatten ycc/rules into OMP-native rules named ycc-<family>-<stem>.md.

OMP scans <plugin>/rules/*.{md,mdc} non-recursively and names a rule by its
file stem, so the nested source tree is flattened. Frontmatter keeps
`description`, maps `paths` to `globs`, and emits `alwaysApply` only when it is
true (globs are then dropped). Relative rule links become rule:// URLs.

Rulebook globs are advisory, so every non-common family with globs also gets a
ycc-<family>-trigger.md TTSR rule: `condition: .*` scoped to edit/write tool
streams on the family's globs with `interruptMode: never`, which attaches a
reminder listing the family's rules after the first matching edit or write.
Triggers carry no `description`, so with `ttsr.enabled: false` they stay out of
the rulebook instead of becoming listing entries.
Source of truth: ycc/rules/. Every policy violation fails closed.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from collections.abc import Mapping
from pathlib import Path

import yaml
from generate_cursor_rules import (
    ALWAYS_APPLY_MAX_BODY_LINES,
    ALWAYS_APPLY_MAX_RULES,
    SKIPPED_RULE_NAMES,
    parse_frontmatter,
    validate_description,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "ycc/rules"
DST_DIR = REPO_ROOT / "packages/omp/ycc-rules/rules"
RULE_PREFIX = "ycc-"
SOURCE_KEYS = frozenset({"description", "paths", "alwaysApply"})
OUTPUT_KEYS = ("description", "alwaysApply", "globs", "condition", "scope", "interruptMode")
FORBIDDEN = ("~/.claude", "CLAUDE_PLUGIN_ROOT", "/ycc:")
COMMON_FAMILY = "common"
TRIGGER_STEM = "trigger"
TRIGGER_SCOPE = ["tool:edit", "tool:write"]

# [text](target) where target has no whitespace; images excluded by the lookbehind.
_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def flat_name(rel: Path) -> str:
    """Return the flat OMP file name for a source path relative to ycc/rules."""
    if len(rel.parts) != 2 or rel.suffix != ".md":
        raise ValueError(f"{rel}: OMP rules are flat; nest at most one family directory")
    family, _ = rel.parts
    return f"{RULE_PREFIX}{family}-{rel.stem}.md"


def rule_frontmatter(rel: Path, data: Mapping[str, object], body: str) -> dict[str, object]:
    """Map Claude-style source frontmatter to OMP rule frontmatter."""
    unknown = sorted(str(key) for key in data if key not in SOURCE_KEYS)
    if unknown:
        raise ValueError(f"{rel}: unsupported frontmatter keys {unknown}; allowed: {sorted(SOURCE_KEYS)}")
    try:
        description = validate_description(rel, data.get("description"), body)
    except SystemExit as exc:
        raise ValueError(str(exc)) from None

    out: dict[str, object] = {"description": description}
    # OMP compares `alwaysApply === true`; a string "true" is not true.
    if data.get("alwaysApply") is True:
        out["alwaysApply"] = True
        return out

    paths = data.get("paths")
    if paths is None:
        if rel.parts[0] != COMMON_FAMILY:
            raise ValueError(f"{rel}: non-common rules need paths")
        return out
    globs = [paths] if isinstance(paths, str) else paths
    if not isinstance(globs, list) or not globs or not all(isinstance(g, str) and g for g in globs):
        raise ValueError(f"{rel}: paths must be a non-empty string or list of strings")
    out["globs"] = list(globs)
    return out


def rewrite_links(body: str, rel: Path, names: set[str]) -> str:
    """Rewrite relative rule links to rule://ycc-<family>-<stem> URLs."""

    def replace(match: re.Match[str]) -> str:
        text, target = match.group(1), match.group(2)
        if target.startswith("#") or _SCHEME_RE.match(target):
            return match.group(0)
        if "#" in target or not target.endswith(".md"):
            raise ValueError(f"{rel}: relative link {target!r} must point at a whole rule file (*.md)")
        resolved = posixpath.normpath(posixpath.join(rel.parent.as_posix(), target))
        try:
            name = flat_name(Path(resolved))
        except ValueError:
            raise ValueError(f"{rel}: link {target!r} resolves outside the rule families") from None
        if name not in names:
            raise ValueError(f"{rel}: link {target!r} points at a missing or skipped rule ({resolved})")
        stem = name.removesuffix(".md")
        if text == posixpath.basename(target):
            text = text.removesuffix(".md")
        return f"[{text}](rule://{stem})"

    return _LINK_RE.sub(replace, body)


def dump_frontmatter(data: Mapping[str, object]) -> str:
    ordered = {key: data[key] for key in OUTPUT_KEYS if key in data}
    text = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False).rstrip()
    return f"---\n{text}\n---\n"


def trigger_rule(family: str, members: list[tuple[str, Mapping[str, object]]]) -> str | None:
    """Render the TTSR trigger for one family from its (rule name, frontmatter) pairs, or None without globs."""
    globs: list[str] = []
    for _name, data in members:
        member_globs = data.get("globs")
        for glob in member_globs if isinstance(member_globs, list) else []:
            if isinstance(glob, str) and glob not in globs:
                globs.append(glob)
    if not globs:
        return None
    frontmatter: dict[str, object] = {
        "globs": globs,
        "condition": ".*",
        "scope": list(TRIGGER_SCOPE),
        "interruptMode": "never",
    }
    lines = [f"# ycc {family} rules", "", "You edited a matching file. Read and apply these ycc rules:", ""]
    for name, data in members:
        stem = name.removesuffix(".md")
        description = " ".join(str(data["description"]).split())
        lines.append(f"- [{stem}](rule://{stem}): {description}")
    return dump_frontmatter(frontmatter) + "\n" + "\n".join(lines) + "\n"


def build_rules(src: Path = SRC_DIR) -> dict[str, str]:
    """Return {flat file name: rendered rule text} for every shippable rule under src."""
    if not src.is_dir():
        raise ValueError(f"{src}: missing rules source directory")
    for path in sorted(src.rglob("*.md")):
        rel = path.relative_to(src)
        if len(rel.parts) > 2:
            flat_name(rel)  # raises: nesting deeper than one family directory

    sources: dict[str, Path] = {}
    for path in sorted(src.glob("*/*.md")):
        if path.name in SKIPPED_RULE_NAMES:
            continue
        rel = path.relative_to(src)
        name = flat_name(rel)
        if name in sources:
            raise ValueError(f"{name}: flat name collision between {sources[name]} and {rel}")
        sources[name] = rel

    names = set(sources)
    rendered: dict[str, str] = {}
    always: list[tuple[Path, int]] = []
    families: dict[str, list[tuple[str, Mapping[str, object]]]] = {}
    for name, rel in sources.items():
        _has_fm, data, body = parse_frontmatter((src / rel).read_text(encoding="utf-8"))
        frontmatter = rule_frontmatter(rel, data, body)
        body_out = rewrite_links(body, rel, names)
        text = dump_frontmatter(frontmatter) + body_out
        hits = [token for token in FORBIDDEN if token in text]
        if hits:
            raise ValueError(f"{rel}: Claude-only tokens {hits} are not allowed in OMP rules")
        if frontmatter.get("alwaysApply") is True:
            always.append((rel, len(body_out.splitlines())))
        rendered[name] = text
        families.setdefault(rel.parts[0], []).append((name, frontmatter))

    if len(always) > ALWAYS_APPLY_MAX_RULES:
        listed = ", ".join(str(rel) for rel, _ in always)
        raise ValueError(f"too many alwaysApply rules: {len(always)} > {ALWAYS_APPLY_MAX_RULES} ({listed})")
    total = sum(lines for _, lines in always)
    if total > ALWAYS_APPLY_MAX_BODY_LINES:
        raise ValueError(f"alwaysApply bodies too large: {total} > {ALWAYS_APPLY_MAX_BODY_LINES} lines")

    for family, members in families.items():
        if family == COMMON_FAMILY:
            continue
        trigger = trigger_rule(family, members)
        if trigger is None:
            continue
        name = f"{RULE_PREFIX}{family}-{TRIGGER_STEM}.md"
        if name in rendered:
            raise ValueError(f"{name}: trigger name collides with source rule {sources[name]}")
        rendered[name] = trigger
    return rendered


def write_tree(dest: Path, dry_run: bool = False) -> set[Path]:
    """Write the flat rules into dest and prune stale ycc-*.md files; return written paths."""
    rules = build_rules(SRC_DIR)
    written = {dest / name for name in rules}
    if dry_run:
        for path in sorted(written):
            print(f"Would write {path}")
        return written
    dest.mkdir(parents=True, exist_ok=True)
    for name, text in rules.items():
        (dest / name).write_text(text, encoding="utf-8")
    for stale in dest.glob(f"{RULE_PREFIX}*.md"):
        if stale not in written:
            stale.unlink()
    return written


def check_tree(dest: Path) -> list[str]:
    """Return drift between dest and the generator output."""
    rules = build_rules(SRC_DIR)
    actual = {p.name for p in dest.glob("*") if p.is_file()} if dest.is_dir() else set()
    diffs = [f"missing: {name}" for name in sorted(set(rules) - actual)]
    diffs += [f"extra: {name}" for name in sorted(actual - set(rules))]
    diffs += [
        f"drift: {name}"
        for name in sorted(set(rules) & actual)
        if (dest / name).read_text(encoding="utf-8") != rules[name]
    ]
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DST_DIR, help=f"output directory (default: {DST_DIR})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 if --out differs from generator output")
    mode.add_argument("--dry-run", action="store_true", help="print paths that would be written")
    mode.add_argument("--lint", action="store_true", help="validate the source rules without writing")
    args = parser.parse_args(argv)
    try:
        if args.lint:
            print(f"OK: {len(build_rules(SRC_DIR))} OMP rules")
            return 0
        if args.check:
            diffs = check_tree(args.out)
            for line in diffs:
                print(f"  {line}", file=sys.stderr)
            if diffs:
                print(f"OMP rules are out of date under {args.out}", file=sys.stderr)
                return 1
            return 0
        written = write_tree(args.out, dry_run=args.dry_run)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not args.dry_run:
        print(f"Wrote {len(written)} rules under {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
