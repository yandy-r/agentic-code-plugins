#!/usr/bin/env python3
"""
Generate Codex-native plugin skills under plugins/ycc/skills from ycc/skills.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from generate_codex_common import (
    HOME_INSTALL_PLUGIN_ROOT,
    PLUGIN_ROOT,
    PLUGIN_SHARED_DIR,
    PLUGIN_SKILLS_DIR,
    SRC_SKILLS_DIR,
    VERBATIM_SKILL_FILES,
    apply_codex_text_transforms,
    compress_skill_description,
    dump_frontmatter,
    load_agent_aliases,
    model_invocation_disabled,
    parse_frontmatter,
)

TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".mdc",
        ".sh",
        ".bash",
        ".py",
        ".json",
        ".yaml",
        ".yml",
        ".txt",
        ".toml",
        ".gitignore",
        ".tmpl",
    }
)

TEXT_NAMES = frozenset({"SKILL.md", "LICENSE", "Makefile"})


def should_transform_text(path: Path) -> bool:
    if path.name in TEXT_NAMES:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def plugin_output_path(rel: Path) -> Path:
    if rel.parts and rel.parts[0] == "_shared":
        return PLUGIN_SHARED_DIR / rel.relative_to("_shared")
    return PLUGIN_SKILLS_DIR / rel


def rewrite_plugin_paths(text: str) -> str:
    pattern = r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/([^\"`\s]+)"

    def replace(match: object) -> str:
        path_text = match.group(1)
        if path_text.startswith("_shared/"):
            return f"{HOME_INSTALL_PLUGIN_ROOT}/shared/{path_text[len('_shared/'):]}"
        return f"{HOME_INSTALL_PLUGIN_ROOT}/skills/{path_text}"

    return __import__("re").sub(pattern, replace, text)


def transform_skill_markdown(raw: str, aliases: dict[str, str]) -> str:
    frontmatter, body = parse_frontmatter(raw)
    name = str(frontmatter.get("name") or "skill")
    model_invocation_disabled(frontmatter, name)
    description = str(frontmatter.get("description") or "").strip()
    transformed_description = apply_codex_text_transforms(
        rewrite_plugin_paths(description),
        aliases,
    ).strip()
    transformed_description = compress_skill_description(transformed_description)
    transformed_body = apply_codex_text_transforms(
        rewrite_plugin_paths(body),
        aliases,
    )
    payload = {
        "name": name,
        "description": transformed_description,
    }
    return dump_frontmatter(payload) + transformed_body


def copy_mode(src: Path, dst: Path) -> None:
    try:
        mode = stat.S_IMODE(src.stat().st_mode)
        dst.chmod(mode)
    except OSError:
        pass


def iter_source_files() -> list[Path]:
    return sorted(path for path in SRC_SKILLS_DIR.rglob("*") if path.is_file())


OWNED_SUBDIRS = (
    PLUGIN_SKILLS_DIR.relative_to(PLUGIN_ROOT),
    PLUGIN_SHARED_DIR.relative_to(PLUGIN_ROOT),
)


def prune_orphans(dest_root: Path, expected_files: set[Path]) -> None:
    # Only prune files under subdirectories this generator owns. Other files
    # (e.g. .codex-plugin/plugin.json, .mcp.json) belong to generate_codex_plugin.py
    # and must be left alone.
    owned_roots = [dest_root / sub for sub in OWNED_SUBDIRS if (dest_root / sub).is_dir()]

    existing_files = sorted(
        (path for root in owned_roots for path in root.rglob("*") if path.is_file()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in existing_files:
        rel = path.relative_to(dest_root)
        if rel not in expected_files:
            path.unlink()

    existing_dirs = sorted(
        (path for root in owned_roots for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in existing_dirs:
        if path in owned_roots:
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()


def write_tree(dest_root: Path, dry_run: bool) -> set[Path]:
    aliases = load_agent_aliases()
    written: set[Path] = set()
    manual_skills: list[Path] = []
    for src in sorted(SRC_SKILLS_DIR.glob("*/SKILL.md")):
        frontmatter, _ = parse_frontmatter(src.read_text(encoding="utf-8"))
        if model_invocation_disabled(frontmatter, src.parent.name):
            # ponytail: no authored sidecars yet; add a field-preserving merge when needed.
            if (src.parent / "agents/openai.yaml").exists():
                raise ValueError(
                    f"skill '{src.parent.name}': authored agents/openai.yaml conflicts with generated policy"
                )
            manual_skills.append(src.parent.relative_to(SRC_SKILLS_DIR))

    for rel in manual_skills:
        out = dest_root / "skills" / rel / "agents/openai.yaml"
        written.add(out.relative_to(dest_root))
        if dry_run:
            print(f"Would write {out.relative_to(dest_root)}")
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("policy:\n  allow_implicit_invocation: false\n", encoding="utf-8")

    for src in iter_source_files():
        rel = src.relative_to(SRC_SKILLS_DIR)
        dst = plugin_output_path(rel)
        out = dest_root / dst.relative_to(PLUGIN_ROOT)
        written.add(out.relative_to(dest_root))

        if dry_run:
            print(f"Would write {out.relative_to(dest_root)}")
            continue

        out.parent.mkdir(parents=True, exist_ok=True)

        if str(rel.as_posix()) in VERBATIM_SKILL_FILES:
            # Multi-target meta file — copy bytes verbatim; no rewrites.
            out.write_bytes(src.read_bytes())
            copy_mode(src, out)
            continue

        if should_transform_text(src):
            text = src.read_text(encoding="utf-8")
            if rel.as_posix() == "_shared/references/agent-team-dispatch.md":
                transformed = (
                    "# Agent Team Dispatch\n\n"
                    "Agent teams (`--team`) are unsupported in the Codex bundle. Abort if "
                    "requested; rerun without `--team` using standalone dispatch.\n"
                )
            else:
                if rel.parts[0] in {"release-model", "init"}:
                    # These names describe the target repo's layout, not runtime rules.
                    text = text.replace("CLAUDE.md", "\x00RELEASE_MODEL_CLAUDE_FILE\x00")
                    if rel.parts[0] == "init":
                        # Version claims name the real product, not the target runtime.
                        text = text.replace("Claude Code", "\x00INIT_CLAUDE_CODE\x00")
                if src.name == "SKILL.md":
                    transformed = transform_skill_markdown(text, aliases)
                else:
                    transformed = apply_codex_text_transforms(
                        rewrite_plugin_paths(text),
                        aliases,
                    )
                if rel.parts and rel.parts[0] == "bundle-release":
                    transformed = restore_bundle_release_source_paths(transformed)
                transformed = transformed.replace("\x00RELEASE_MODEL_CLAUDE_FILE\x00", "CLAUDE.md")
                transformed = transformed.replace("\x00INIT_CLAUDE_CODE\x00", "Claude Code")
            out.write_text(transformed, encoding="utf-8")
        else:
            shutil.copyfile(src, out)
        copy_mode(src, out)

    if not dry_run:
        prune_orphans(dest_root, written)
    return written


def restore_bundle_release_source_paths(content: str) -> str:
    """Release docs intentionally point at Claude plugin metadata source files."""
    return (
        content.replace("ycc/.codex-plugin/plugin.json", "ycc/.claude-plugin/plugin.json")
        .replace(".codex-plugin/marketplace.json", ".claude-plugin/marketplace.json")
        .replace(".codex-plugin/ && ./scripts/sync.sh", ".opencode-plugin/ && ./scripts/sync.sh")
    )


def compare_trees(generated: Path, repo_dest: Path, expected_files: set[Path]) -> list[str]:
    diffs: list[str] = []
    for rel in sorted(expected_files):
        left = generated / rel
        right = repo_dest / rel
        if not right.exists():
            diffs.append(f"missing in repo: {rel}")
            continue
        if left.read_bytes() != right.read_bytes():
            diffs.append(f"drift: {rel}")
    for sub in OWNED_SUBDIRS:
        for path in sorted((repo_dest / sub).rglob("*")):
            if path.is_file() and path.relative_to(repo_dest) not in expected_files:
                diffs.append(f"extra in repo: {path.relative_to(repo_dest)}")
    return diffs


def run_check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        written = write_tree(temp_root, dry_run=False)
        diffs = compare_trees(temp_root, PLUGIN_ROOT, written)
        if diffs:
            print(
                "Codex plugin skills are out of date. Run: ./scripts/generate-codex-skills.sh",
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
        if not PLUGIN_ROOT.exists():
            print(
                f"Missing {PLUGIN_ROOT}; run generator without --check first.",
                file=sys.stderr,
            )
            sys.exit(1)
        sys.exit(run_check())

    if args.dry_run:
        write_tree(PLUGIN_ROOT, dry_run=True)
        return

    write_tree(PLUGIN_ROOT, dry_run=False)
    count = sum(1 for path in PLUGIN_ROOT.rglob("*") if path.is_file())
    print(f"Wrote {count} files under {PLUGIN_ROOT}")


if __name__ == "__main__":
    main()
