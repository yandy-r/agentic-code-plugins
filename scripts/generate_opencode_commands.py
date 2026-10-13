#!/usr/bin/env python3
"""Generate opencode commands from public ycc/skills/*/SKILL.md.

Keep native commands for commands-only installs. Each command loads its skill
via the skill tool and forwards $ARGUMENTS; workflow logic stays in SKILL.md.
Description, argument hints and model mappings come from skill frontmatter.
"""

from __future__ import annotations

import argparse
import filecmp
import sys
import tempfile
from pathlib import Path

from generate_opencode_common import (
    OPENCODE_COMMANDS_DIR,
    SRC_SKILLS_DIR,
    apply_opencode_text_transforms,
    dump_frontmatter,
    is_model_drop_sentinel,
    load_agent_aliases,
    load_model_aliases,
    map_model,
    parse_frontmatter,
)
from generate_opencode_dispatch import project_opencode_dispatch_description


def _stringify_argument_hint(value: object) -> str:
    """Argument hints may be strings, lists, or dicts in the Claude source.
    Return a plain string suitable for prepending to the description.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return " ".join(f"{key}={val}" for key, val in value.items())
    return str(value).strip()


def transform_command(
    stem: str,
    raw: str,
    aliases: dict[str, str],
    model_aliases: dict[str, str],
) -> str:
    frontmatter, _ = parse_frontmatter(raw)

    description = str(frontmatter.get("description") or "").strip()
    transformed_description = apply_opencode_text_transforms(description, aliases).strip()
    if not transformed_description:
        transformed_description = f"{stem} command"

    # Fold argument-hint into description so the usage hint still appears in
    # the TUI autocomplete, even though opencode doesn't have a dedicated
    # argument-hint field.
    argument_hint = _stringify_argument_hint(frontmatter.get("argument-hint"))
    if argument_hint and argument_hint not in transformed_description:
        transformed_description = f"{transformed_description} Usage: {argument_hint}".strip()
    transformed_description = project_opencode_dispatch_description(transformed_description)

    payload: dict[str, object] = {"description": transformed_description}

    agent_value = frontmatter.get("agent")
    if isinstance(agent_value, str) and agent_value.strip():
        payload["agent"] = agent_value.strip()

    raw_model = frontmatter.get("model")
    model_value = map_model(raw_model, model_aliases)
    if model_value:
        payload["model"] = model_value
    elif raw_model and not is_model_drop_sentinel(str(raw_model)):
        print(
            f"generate_opencode_commands: WARN unmapped model '{raw_model}' on {stem}.md — dropping model field",
            file=sys.stderr,
        )

    subtask = frontmatter.get("subtask")
    if isinstance(subtask, bool):
        payload["subtask"] = subtask

    body = (
        f"\nUse the skill tool to load the `{stem}` skill, then follow its instructions "
        "with these arguments:\n\n$ARGUMENTS\n"
    )
    return dump_frontmatter(payload) + body


def discover_skills(source: Path) -> list[Path]:
    """Return public skill entrypoints; private directories have no commands."""
    skills: list[Path] = []
    for path in sorted(source.glob("*/SKILL.md")):
        if path.parent.name.startswith("_"):
            continue
        frontmatter, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if frontmatter.get("user-invocable") is not False:
            skills.append(path)
    return skills


def write_all(dest: Path, dry_run: bool) -> set[Path]:
    aliases = load_agent_aliases()
    model_aliases = load_model_aliases()
    written: set[Path] = set()

    for src in discover_skills(SRC_SKILLS_DIR):
        stem = src.parent.name
        output = transform_command(
            stem,
            src.read_text(encoding="utf-8"),
            aliases,
            model_aliases,
        )
        target = dest / f"{stem}.md"
        written.add(target.relative_to(dest))
        if dry_run:
            print(f"Would write {target.relative_to(dest)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")

    if not dry_run:
        existing = sorted(dest.glob("*.md"))
        for path in existing:
            if path.relative_to(dest) not in written:
                path.unlink()
    return written


def compare_trees(generated: Path, repo_dest: Path) -> list[str]:
    gen_files = {path.relative_to(generated) for path in generated.glob("*.md")}
    repo_files = {path.relative_to(repo_dest) for path in repo_dest.glob("*.md")} if repo_dest.is_dir() else set()

    diffs: list[str] = []
    for rel in sorted(gen_files | repo_files):
        if rel not in repo_files:
            diffs.append(f"missing in repo: {rel}")
            continue
        if rel not in gen_files:
            diffs.append(f"extra in repo: {rel}")
            continue
        if not filecmp.cmp(generated / rel, repo_dest / rel, shallow=False):
            diffs.append(f"drift: {rel}")
    return diffs


def run_check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        write_all(temp_root, dry_run=False)
        diffs = compare_trees(temp_root, OPENCODE_COMMANDS_DIR)
        if diffs:
            print(
                "opencode commands are out of date. Run: ./scripts/generate-opencode-commands.sh",
                file=sys.stderr,
            )
            for diff in diffs:
                print(f"  {diff}", file=sys.stderr)
            return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if generated output drifts")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written")
    args = parser.parse_args()

    if args.check:
        if not OPENCODE_COMMANDS_DIR.is_dir():
            print(
                f"Missing {OPENCODE_COMMANDS_DIR}; run generator without --check first.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(run_check())

    if args.dry_run:
        write_all(OPENCODE_COMMANDS_DIR, dry_run=True)
        return

    OPENCODE_COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    write_all(OPENCODE_COMMANDS_DIR, dry_run=False)
    count = sum(1 for _ in OPENCODE_COMMANDS_DIR.glob("*.md"))
    print(f"Wrote {count} files under {OPENCODE_COMMANDS_DIR}")


if __name__ == "__main__":
    main()
