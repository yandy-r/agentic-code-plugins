#!/usr/bin/env python3
"""Reject legacy or unsupported dispatch contracts in generated OpenCode prose."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from generate_opencode_dispatch_markdown import find_native_subagent_calls

_EXCLUDED_SUFFIXES = frozenset(
    {
        "shared/references/target-capability-matrix.md",
        "skills/hooks-workflow/references/support-notes.md",
        "skills/compatibility-audit/references/reading-the-report.md",
    }
)

_FORBIDDEN: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Task(", re.compile(r"\bTask\(")),
    ("backticked Task tool", re.compile(r"`Task`")),
    ("backticked Agent tool", re.compile(r"`Agent`")),
    ("subagent_type", re.compile(r"\bsubagent_type\b")),
    ("team_name", re.compile(r"\bteam_name\b")),
    ("run_in_background", re.compile(r"\brun_in_background\b")),
    ("unsupported subagent name argument", re.compile(r"`name=`")),
    (
        "unsolicited Claude model alias",
        re.compile(r"\bmodel:\s*[\"'`](?:sonnet|haiku|opus)[\"'`]", re.IGNORECASE),
    ),
    (
        "Claude agent-team environment flag",
        re.compile(r"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"),
    ),
    (
        "operational team-mode branch",
        re.compile(r"\b(?:TEAM_FLAG|AGENT_TEAM_MODE)\s*=\s*true\b|" r"\bEXECUTION_MODE\s*=\s*agent_team\b"),
    ),
    ("unsupported agent-team mode", re.compile(r"\bagent team\b", re.IGNORECASE)),
    ("legacy opencode task tool", re.compile(r"(?:opencode|built-in) `task` tool")),
    (
        "cosmetic team-tool translation",
        re.compile(r"spawn coordinated subagents|end the coordinated run"),
    ),
    (
        "unsupported team Agent call",
        re.compile(r"\bAgent\([^\n)]*\bteam(?:_name)?\s*="),
    ),
    (
        "universal blocking inline-return claim",
        re.compile(
            r"(?i:\bsame turn\b)|"
            r"(?i:\breturns? inline\b)|"
            r"(?i:\breturned inline\b)|"
            r"(?i:\balready in hand\b)|"
            r"blocking[^\n]{0,80}\b(?:Task|subagent)\b|"
            r"(?i:\bsubagent[^\n]{0,80}\bblocks?\b)|"
            r"(?i:\bcompletion is implicit\b)"
        ),
    ),
    (
        "blanket polling ban",
        re.compile(
            r"never[^\n]{0,80}\bpoll\b|"
            r"\bdo not poll\b|"
            r"\bno polling\b|"
            r"\bpolling (?:is|are) forbidden\b|"
            r"\bmust not poll\b",
            flags=re.IGNORECASE,
        ),
    ),
    (
        "blank dispatch selector",
        re.compile(
            r"(?:depends on|Branch on|based on)[^\n]{0,80}``|^\|\s*``\s*\|",
            re.MULTILINE,
        ),
    ),
    ("orphan team dry-run roster", re.compile(r"^Team name:", re.MULTILINE)),
    ("orphan empty list item", re.compile(r"^[-*]\s*$", re.MULTILINE)),
)

_REQUIRED_FRAGMENTS: dict[str, tuple[str, ...]] = {
    "skills/shared-context/SKILL.md": (
        "Supported: the feature name, `--dry-run`",
        "Usage: /shared-context [feature-name] [--dry-run]",
        "<feature-name> --research-only --no-checkpoint [--dry-run]",
    ),
    "skills/parallel-plan/SKILL.md": (
        "Usage: /parallel-plan [--no-worktree] [--visual] [feature-name] [--dry-run]",
        "<feature-name> --plan-only --no-checkpoint [--dry-run] [--no-worktree] [--visual]",
    ),
    "skills/code-review/SKILL.md": (
        "`--quick`",
        "`QUICK_MODE=true|false`",
        "`PARALLEL_MODE=true|false`",
        "`KEEP_DRAFT=true|false`",
        "`KEEP_WORKTREE=true|false`",
        "depends on `PARALLEL_MODE`:",
    ),
    "skills/review-fix/SKILL.md": (
        "| `--dry-run` | Print the fix plan and stop.",
        "`PARALLEL_MODE`, `MIN_SEVERITY`, `DRY_RUN`",
        "If `DRY_RUN=true`, stop here",
    ),
    "skills/implement-plan/SKILL.md": (
        "`--dry-run`",
        "`DRY_RUN=true|false`",
        "Usage: /implement-plan [--dry-run] [--worktree] [--no-worktree] <feature-name>",
        'subagent(agent="implementor"',
        "standalone sub-agents. Worktree isolation",
    ),
    "skills/feature-research/SKILL.md": (
        "Deploy all 7 researchers",
        "`background=false`",
        "record its `sessionID`",
        "at most one retry",
        "tool. Outputs",
    ),
    "skills/deep-research/SKILL.md": (
        "Deploy all 8 persona agents",
        "Deploy both analysis agents",
        "Deploy all 4 strategic analysis agents",
        "`background=false`",
        "record its `sessionID`",
        "perspectives. Use",
    ),
    "skills/plan-workflow/SKILL.md": (
        "Deploy all 4 research agents",
        "Deploy all 3 analysis agents",
        "Deploy all validation agents",
        "spawn all 5 unified agents",
        "`background=false`",
        "record its `sessionID`",
    ),
    "skills/plan/SKILL.md": (
        "PERSPECTIVE_COUNT=1",
        "PERSPECTIVE_COUNT=3",
        "PERSPECTIVE_COUNT=5",
        'subagent(agent="<configured-agent>"',
        "background=false",
        "record `sessionID`",
    ),
    "skills/prp-plan/SKILL.md": (
        "validate-prp-plan.sh",
        "Three standalone researchers",
        'agent="prp-researcher"',
        "SEVEN native `subagent` calls",
        "`background=false`",
        "record its `sessionID`",
    ),
    "commands/plan-workflow.md": ("Use the skill tool to load the `plan-workflow` skill", "$ARGUMENTS"),
    "commands/parallel-plan.md": ("Use the skill tool to load the `parallel-plan` skill", "$ARGUMENTS"),
    "commands/shared-context.md": ("Use the skill tool to load the `shared-context` skill", "$ARGUMENTS"),
    "commands/feature-research.md": ("Use the skill tool to load the `feature-research` skill", "$ARGUMENTS"),
}


def find_dispatch_residue(text: str, display_path: str) -> list[str]:
    """Return human-readable errors for one generated Markdown document."""
    errors: list[str] = []
    for label, pattern in _FORBIDDEN:
        for match in pattern.finditer(text):
            line_index = text.count("\n", 0, match.start()) + 1
            excerpt = text.splitlines()[line_index - 1].strip()
            errors.append(f"{display_path}:{line_index}: {label}: {excerpt}")
    for start, _, arguments in find_native_subagent_calls(text):
        if not re.search(r"\bbackground\s*=", arguments):
            line_index = text.count("\n", 0, start) + 1
            errors.append(f"{display_path}:{line_index}: native subagent call omits explicit background")
    if _has_empty_fenced_block(text):
        errors.append(f"{display_path}: empty fenced block after dispatch projection")
    if re.search(r"\*\*Mode\*\*:[^\n]*\*\*Severity[^*]*\*\*:", text):
        errors.append(f"{display_path}: report fields were concatenated onto one line")
    normalized_path = Path(display_path).as_posix()
    allowed_reference = normalized_path.endswith("standalone-dispatch.md")
    for line_number, line in enumerate(text.splitlines(), 1):
        if "--team" in line and not ("OpenCode V2 compatibility" in line or allowed_reference):
            errors.append(f"{display_path}:{line_number}: operational --team residue: {line.strip()}")
    for suffix, fragments in _REQUIRED_FRAGMENTS.items():
        if normalized_path.endswith(suffix):
            for fragment in fragments:
                if fragment not in text:
                    errors.append(f"{display_path}: missing required dispatch fragment: {fragment}")
    return errors


def _has_empty_fenced_block(text: str) -> bool:
    """Return true when one Markdown fence opens and closes without content."""
    marker: tuple[str, int] | None = None
    has_content = False
    for line in text.splitlines():
        match = re.match(r"^\s*(```+|~~~+)", line)
        if match:
            token = match.group(1)
            current = (token[0], len(token))
            if marker is None:
                marker = current
                has_content = False
            elif current[0] == marker[0] and current[1] >= marker[1]:
                if not has_content:
                    return True
                marker = None
            else:
                has_content = True
            continue
        if marker is not None and line.strip():
            has_content = True
    return False


def _is_excluded(path: Path) -> bool:
    normalized = path.as_posix()
    return any(normalized.endswith(suffix) for suffix in _EXCLUDED_SUFFIXES)


def validate_paths(paths: list[Path]) -> list[str]:
    """Validate Markdown files below every file or directory in ``paths``."""
    errors: list[str] = []
    for root in paths:
        candidates = [root] if root.is_file() else sorted(root.rglob("*.md"))
        for path in candidates:
            if _is_excluded(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"{path}: unable to read generated dispatch prose: {exc}")
                continue
            errors.extend(find_dispatch_residue(text, str(path)))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    missing = [path for path in args.paths if not path.exists()]
    if missing:
        for path in missing:
            print(f"missing generated dispatch path: {path}", file=sys.stderr)
        return 1

    errors = validate_paths(args.paths)
    if errors:
        print("OpenCode V2 dispatch content policy failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
