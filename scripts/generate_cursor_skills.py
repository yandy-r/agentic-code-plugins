#!/usr/bin/env python3
"""
Generate Cursor-native skills under .cursor-plugin/skills from ycc/skills.

Transforms are deterministic and idempotent. Source of truth: ycc/skills/
"""

from __future__ import annotations

import argparse
import re
import stat
import sys
import tempfile
from pathlib import Path

from generate_codex_common import model_invocation_disabled, parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "ycc" / "skills"
DST_DIR = REPO_ROOT / ".cursor-plugin" / "skills"

# Extensions we treat as UTF-8 text and apply transforms to.
TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".mdc",
        ".sh",
        ".bash",
        ".json",
        ".yaml",
        ".yml",
        ".txt",
        ".toml",
        ".gitignore",
        ".tmpl",
    }
)

# Filenames without a listed suffix but still text (e.g. Makefile rarely; skills use SKILL.md)
TEXT_NAMES = frozenset({"SKILL.md", "LICENSE", "Makefile"})

# Skill-tree source files copied verbatim into the Cursor bundle. They describe or check
# all three deployment targets literally, so blind replacements (.claude-plugin/ →
# .cursor-plugin/, ~/.claude/ → ~/.cursor/, etc.) corrupt the content. Paths are
# source-relative to ycc/skills/.
VERBATIM_SKILL_FILES = frozenset(
    {
        "_shared/references/target-capability-matrix.md",
        "hooks-workflow/references/support-notes.md",
        "compatibility-audit/scripts/audit-install-assumptions.sh",
        "compatibility-audit/scripts/audit-target-features.sh",
        "compatibility-audit/references/reading-the-report.md",
    }
)


def should_transform_text(path: Path) -> bool:
    if path.name in TEXT_NAMES:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def fix_mcp_malformed_tokens(s: str) -> str:
    prev = None
    out = s
    while prev != out:
        prev = out
        out = re.sub(
            r"mcp\*\*([a-zA-Z0-9]+)\*\*([a-zA-Z0-9][a-zA-Z0-9.-]*)",
            r"mcp__\1__\2",
            out,
        )
    return out


def apply_skills_text_transforms(s: str) -> str:
    """Cursor-native rewrites for skills content."""
    s = s.replace("CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT")

    s = fix_mcp_malformed_tokens(s)

    s = s.replace("~/.claude/", "~/.cursor/")
    # ${HOME}/.claude/... and $HOME/.claude/... (bash), and any /.claude/ path segment
    s = re.sub(r"\$\{HOME\}/\.claude/", r"${HOME}/.cursor/", s)
    s = re.sub(r"\$HOME/\.claude/", r"$HOME/.cursor/", s)
    s = s.replace("/.claude/", "/.cursor/")
    s = s.replace(".claude-plugin/", ".cursor-plugin/")

    s = re.sub(r"/ycc:([a-zA-Z0-9-]+)", r"/\1", s)

    s = re.sub(r"\bycc:([a-zA-Z0-9-]+)\b", r"\1", s)

    # Phrase-specific Task / Agent tool wording (before generic replacements)
    s = s.replace(
        "Refer to Task tool description for latest updates.",
        "Refer to Cursor agent documentation for latest updates.",
    )
    s = s.replace(
        "Refer to Agent tool description for latest updates.",
        "Refer to Cursor agent documentation for latest updates.",
    )
    s = s.replace(
        "available agents in the Task tool",
        "available agents in Cursor",
    )
    s = s.replace(
        "available agents in the Agent tool",
        "available agents in Cursor",
    )
    s = s.replace(
        "available agents in a parallel agent run",
        "available agents in Cursor",
    )
    s = s.replace(
        "List of all valid agent types from Task tool",
        "List of all valid agent types for Cursor",
    )
    s = s.replace(
        "List of all valid agent types from Agent tool",
        "List of all valid agent types for Cursor",
    )
    s = s.replace("Use the Task tool with", "Use parallel agents with")
    s = s.replace("Use the Agent tool with", "Use parallel agents with")

    s = re.sub(
        r"(?i)use the (?:Task|Agent) tool to launch (?:the )?`?([a-zA-Z0-9-]+)`? agent",
        r"invoke the `\1` agent",
        s,
    )
    s = re.sub(
        r"(?i)use the (?:Task|Agent) tool to launch the ([a-zA-Z0-9-]+) agent",
        r"invoke the `\1` agent",
        s,
    )
    s = s.replace("Task tool to launch", "invoke")
    s = s.replace("Agent tool to launch", "invoke")
    s = s.replace("the Task tool", "Cursor")
    s = s.replace("the Agent tool", "Cursor")
    s = s.replace("Task tool calls", "parallel agent invocations")
    s = s.replace("Agent tool calls", "parallel agent invocations")
    s = s.replace("Task tool call", "agent invocation")
    s = s.replace("Agent tool call", "agent invocation")
    s = s.replace("Single Task tool call", "Single agent invocation")
    s = s.replace("Single Agent tool call", "Single agent invocation")
    s = s.replace("MULTIPLE Task tool calls", "Multiple parallel agent invocations")
    s = s.replace("MULTIPLE Agent tool calls", "Multiple parallel agent invocations")

    # Preserve tool identifiers in YAML; translate prose only. Path/namespace
    # rewrites above still apply to scoped Bash permissions in frontmatter.
    preamble = ""
    if s.startswith("---\n"):
        end = s.find("\n---\n", 4)
        if end >= 0:
            preamble, s = s[: end + 5], s[end + 5 :]
    for tool, wording in (
        ("TodoWrite", "task tracker"),
        ("TaskCreate", "task registration"),
        ("TaskUpdate", "task status update"),
        ("TaskList", "task list"),
        ("TaskGet", "task details"),
        ("TeamCreate", "agent group setup"),
        ("TeamDelete", "agent group cleanup"),
    ):
        s = re.sub(rf"\b{tool}\b", wording, s)

    s = s.replace("main Claude session", "main Cursor session")
    s = s.replace("Claude is running ", "When running ")
    s = re.sub(r"\bClaude API with structured output\b", "LLM API with structured output", s)
    s = s.replace("closing Claude Code", "closing the session")
    s = s.replace("Claude home directory", "Cursor home directory")
    s = s.replace("Claude CLI", "Cursor CLI")
    s = s.replace("set up Claude CLI environment", "set up the Cursor environment")
    s = s.replace("Claude tools", "Cursor tools")
    s = s.replace("Restart Claude CLI", "Restart Cursor")
    s = s.replace("Claude CLI logs", "Cursor logs")
    s = s.replace("read by Claude", "read by the assistant")
    s = s.replace("want Claude to fully absorb", "want the assistant to fully absorb")

    s = s.replace("- /.claude", "- /.cursor")

    s = s.replace("parallel Task execution", "parallel agent runs")
    s = s.replace("Parallel Task execution", "Parallel agent runs")

    return preamble + s


def restore_bundle_release_source_paths(content: str) -> str:
    """Release docs intentionally point at Claude plugin metadata source files."""
    return (
        content.replace("ycc/.cursor-plugin/plugin.json", "ycc/.claude-plugin/plugin.json")
        .replace(".cursor-plugin/marketplace.json", ".claude-plugin/marketplace.json")
        .replace(".cursor-plugin/ && ./scripts/sync.sh", ".opencode-plugin/ && ./scripts/sync.sh")
    )


def transform_text_content(content: str, rel: Path) -> str:
    if rel.as_posix() == "_shared/references/agent-team-dispatch.md":
        return (
            "# Agent Team Dispatch\n\n"
            "Agent teams (`--team`) are unsupported in the Cursor bundle. Abort if requested; "
            "rerun without `--team` using standalone dispatch.\n"
        )
    out = apply_skills_text_transforms(content)
    if rel.parts and rel.parts[0] == "bundle-release":
        out = restore_bundle_release_source_paths(out)
    if out and not out.endswith("\n"):
        out += "\n"
    return out


def copy_mode(src: Path, dst: Path) -> None:
    try:
        st = src.stat()
        mode = stat.S_IMODE(st.st_mode)
        dst.chmod(mode)
    except OSError:
        pass


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append(p)
    return files


def write_tree(dest: Path, dry_run: bool) -> set[Path]:
    """Write transformed tree under dest. Returns set of relative paths (files)."""
    if not SRC_DIR.is_dir():
        raise SystemExit(f"Missing source directory: {SRC_DIR}")

    written: set[Path] = set()

    for src_file in iter_source_files(SRC_DIR):
        rel = src_file.relative_to(SRC_DIR)
        dst_file = dest / rel
        written.add(rel)

        if src_file.name == "SKILL.md":
            # Flag is copied verbatim; validate strictly so bad YAML types fail fast.
            frontmatter, _ = parse_frontmatter(src_file.read_text(encoding="utf-8"))
            model_invocation_disabled(frontmatter, src_file.parent.name)

        if dry_run:
            print(f"Would write {dst_file.relative_to(REPO_ROOT)}")
            continue

        if rel.as_posix() in VERBATIM_SKILL_FILES:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            dst_file.write_bytes(src_file.read_bytes())
            copy_mode(src_file, dst_file)
            continue

        dst_file.parent.mkdir(parents=True, exist_ok=True)

        if should_transform_text(src_file):
            try:
                text = src_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                data = src_file.read_bytes()
                dst_file.write_bytes(data)
                copy_mode(src_file, dst_file)
                continue
            dst_file.write_text(transform_text_content(text, rel), encoding="utf-8")
        else:
            dst_file.write_bytes(src_file.read_bytes())

        copy_mode(src_file, dst_file)

    if not dry_run:
        prune_orphans(dest, written)

    return written


def prune_orphans(dest: Path, source_rels: set[Path]) -> None:
    """Remove files/dirs under dest that are not present in source."""
    all_dest_files: list[Path] = []
    for p in dest.rglob("*"):
        if p.is_file():
            all_dest_files.append(p)

    for p in sorted(all_dest_files, key=lambda x: len(x.parts), reverse=True):
        try:
            rel = p.relative_to(dest)
        except ValueError:
            continue
        if rel not in source_rels:
            p.unlink()

    # Remove empty directories bottom-up
    dirs = sorted(
        {d for d in dest.rglob("*") if d.is_dir()},
        key=lambda x: len(x.parts),
        reverse=True,
    )
    for d in dirs:
        if d == dest:
            continue
        try:
            next(d.iterdir())
        except StopIteration:
            d.rmdir()


def compare_trees(generated: Path, repo_dst: Path) -> list[str]:
    """Compare file-by-file; returns human-readable diff lines."""
    diffs: list[str] = []
    gen_files: set[Path] = set()
    for p in generated.rglob("*"):
        if p.is_file():
            gen_files.add(p.relative_to(generated))

    dst_files: set[Path] = set()
    if repo_dst.is_dir():
        for p in repo_dst.rglob("*"):
            if p.is_file():
                dst_files.add(p.relative_to(repo_dst))

    for rel in sorted(gen_files | dst_files):
        g = generated / rel
        r = repo_dst / rel
        if rel not in dst_files:
            diffs.append(f"missing in repo: {rel}")
            continue
        if rel not in gen_files:
            diffs.append(f"extra in repo: {rel}")
            continue
        if g.read_bytes() != r.read_bytes():
            diffs.append(f"drift: {rel}")
    return diffs


def run_check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tpath = Path(tmp)
        write_tree(tpath, dry_run=False)
        diffs = compare_trees(tpath, DST_DIR)
        if diffs:
            print(
                "Cursor skills are out of date. Run: ./scripts/generate-cursor-skills.sh",
                file=sys.stderr,
            )
            for line in diffs:
                print(f"  {line}", file=sys.stderr)
            return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if .cursor-plugin/skills differs from generator output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths that would be written (no writes)",
    )
    args = parser.parse_args()

    if args.check:
        if not DST_DIR.is_dir():
            print(
                f"Missing {DST_DIR}; run generator without --check first.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(run_check())

    if args.dry_run:
        write_tree(DST_DIR, dry_run=True)
        return

    write_tree(DST_DIR, dry_run=False)
    n = sum(1 for _ in DST_DIR.rglob("*") if _.is_file())
    print(f"Wrote {n} files under {DST_DIR}")


if __name__ == "__main__":
    main()
