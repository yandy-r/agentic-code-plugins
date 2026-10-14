#!/usr/bin/env python3
"""Markdown structure and native call syntax projection for OpenCode V2."""

from __future__ import annotations

import re

_TEAM_ONLY_HEADING = re.compile(
    r"(?:"
    r"agent[- ]team|"
    r"team setup|"
    r"team lifecycle|"
    r"team summary|"
    r"team communication|"
    r"teammate configuration|"
    r"build the team name|"
    r"create the team|"
    r"clean up team|"
    r"shut down .*teammate|"
    r"spawn the teammate|"
    r"when to use `?--team`?|"
    r".*if `?--team`?.*|"
    r"path [bc].*team"
    r")",
    re.IGNORECASE,
)

_TEAM_OPERATION_LINE = re.compile(
    r"(?:"
    r"\bteam_name\b|"
    r"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS|"
    r"\b(?:TEAM_FLAG|AGENT_TEAM_MODE)\s*=\s*true(?!\|false)|"
    r"\bEXECUTION_MODE\s*=\s*agent_team\b|"
    r"\b(?:TeamCreate|TeamDelete|TaskCreate|TaskList|SendMessage)\b|"
    r"spawn coordinated subagents|"
    r"end the coordinated run"
    r")",
)

_TEAM_COMPATIBILITY_NOTE = (
    "> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, "
    "abort before setup or dispatch and ask the caller to rerun without it. This "
    "target uses native standalone `subagent` calls only."
)


def _heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
    if not match:
        return None
    return len(match.group(1)), match.group(2)


def _strip_team_sections(text: str) -> str:
    """Remove Markdown sections whose heading declares Claude-only team work."""
    output: list[str] = []
    skipped_level: int | None = None
    fence_marker: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        opening_fence = re.match(r"(```+|~~~+)", stripped)
        if opening_fence:
            token = opening_fence.group(1)
            marker = (token[0], len(token))
            if fence_marker is not None and marker[0] == fence_marker[0] and marker[1] >= fence_marker[1]:
                fence_marker = None
            elif fence_marker is None:
                fence_marker = marker
            if skipped_level is None:
                output.append(line)
            continue

        parsed = None if fence_marker else _heading(line.rstrip("\n"))
        if skipped_level is not None:
            if parsed and parsed[0] <= skipped_level:
                skipped_level = None
            else:
                continue
        if parsed and _TEAM_ONLY_HEADING.search(parsed[1]):
            skipped_level = parsed[0]
            continue
        if skipped_level is None:
            output.append(line)
    return "".join(output)


def _strip_embedded_team_communication_sections(text: str) -> str:
    """Strip Team Communication sections embedded inside prompt code fences."""
    output: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if re.match(r"^## Team Communication\b", line, re.IGNORECASE):
            skipping = True
            continue
        if skipping and re.match(r"^## (?!Team Communication\b)", line):
            skipping = False
        if not skipping:
            output.append(line)
    return "".join(output)


def _remove_team_operations(text: str, *, add_compatibility_note: bool) -> str:
    """Remove discrete team-only rows while preserving mixed standalone prose."""
    had_team_flag = "--team" in text
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        lowered = stripped.lower()
        if "claude_code_experimental_agent_teams" in lowered:
            continue
        if re.match(r"^(?:[-*]\s+|\|\s*)(?:\*\*)?`?--team`?", stripped):
            continue
        if re.match(r"^--team\b", stripped):
            continue
        if re.match(r"^\S*\/\S*\s+.*--team", stripped):
            continue
        if stripped.startswith("**Compatibility note**") and "--team" in stripped:
            continue
        if stripped.startswith("**Team opt-in note**"):
            continue
        if "--team" in line and re.search(r"(?:dispatch|spawn|run).*\bteam\b", line, re.IGNORECASE):
            continue
        if re.match(
            r"^\d+\. \*\*(?:Create team|Spawn in parallel|Clean up team)\*\*",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue
        if re.match(r"^- \*\*(?:Path B|Path C|Agent team)", stripped, re.IGNORECASE):
            continue
        if "path b additions" in lowered or "choose dispatch mode from" in lowered and "--team" in lowered:
            continue
        if "dry-run mode" in lowered and _TEAM_OPERATION_LINE.search(line):
            kept.append("Do not dispatch any `subagent` calls in dry-run mode.\n")
            continue

        line = line.replace(
            "spawn/return contract (never `Agent` without a `team_name`).",
            "native dispatch and result contract.",
        )
        line = re.sub(r"\s*\[--team\]", "", line)
        line = re.sub(r",\s*`?--team`?", "", line)
        line = re.sub(r"\s*/\s*`?--team`?", "", line)
        line = re.sub(r"\s+or\s+`?--team`?", "", line)
        line = re.sub(r"\s*\|\s*--team\b", "", line)
        line = re.sub(r"\s*With `?--team`?.*$", "\n", line, flags=re.IGNORECASE)
        line = re.sub(
            r"\s*[—-]\s*no team coordination,\s*no `team_name`\.?'?",
            ".",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(
            r"\s*no `name`, no `run_in_background`\.",
            " Each call uses native foreground arguments.",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(
            r"\s*No `team_name`[^.]*\.",
            " Every call uses only native OpenCode arguments.",
            line,
            flags=re.IGNORECASE,
        )
        if _TEAM_OPERATION_LINE.search(line):
            if "standalone" in line.lower() and " or " in line:
                line = line.split(" or ", 1)[0].rstrip() + "\n"
            else:
                continue
        kept.append(line)
    projected = "".join(kept)
    if not had_team_flag or not add_compatibility_note:
        return projected

    lines = projected.splitlines(keepends=True)
    insertion = 0
    for index, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            insertion = index + 1
            break
    note = f"\n{_TEAM_COMPATIBILITY_NOTE}\n"
    lines.insert(insertion, note)
    return "".join(lines)


def _project_standalone_only_terms(text: str) -> str:
    """Remove orphaned team choices and retain their standalone instructions."""
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        lowered = line.lower()
        if re.search(r"\b(?:TEAM_FLAG|AGENT_TEAM_MODE)\s*=\s*true(?!\|false)", line):
            continue
        if (
            "agent-team-dispatch.md" in lowered
            or "team lifecycle" in lowered
            or ("path b only" in lowered and "team" in lowered)
        ):
            continue
        if "agent team" in lowered or "team mode" in lowered:
            if "standalone" not in lowered and "parallel sub-agent" not in lowered:
                continue
            line = re.sub(r",?\s+or an? agent team.*$", ".\n", line, flags=re.IGNORECASE)
            line = re.sub(
                r",?\s*and\s+\*\*Path C \(Agent team\)\*\*",
                "",
                line,
                flags=re.IGNORECASE,
            )
            line = re.sub(r"\s*/\s*agent team", "", line, flags=re.IGNORECASE)
            line = re.sub(
                r"\s+or\s+agent team\s+`[^`]+`",
                "",
                line,
                flags=re.IGNORECASE,
            )
            line = re.sub(
                r"\s*\|\s*Agent team[^|\]]*",
                "",
                line,
                flags=re.IGNORECASE,
            )
        line = line.replace("AGENT_TEAM_MODE=false", "STANDALONE_MODE=true")
        line = line.replace("TEAM_FLAG=false", "STANDALONE_MODE=true")
        line = re.sub(
            r",?\s*\b(?:AGENT_TEAM_MODE|AGENT_TEAM_FLAG|TEAM_FLAG)\b(?:=true\|false)?",
            "",
            line,
        )
        line = line.replace("Teammate Name", "Sub-agent Role")
        line = line.replace("Teammate `name`", "Sub-agent role")
        line = line.replace("teammate `name`", "sub-agent role")
        line = line.replace("teammates", "sub-agents")
        line = line.replace("Teammates", "Sub-agents")
        line = line.replace("teammate", "sub-agent")
        line = line.replace("Teammate", "Sub-agent")
        line = line.replace(
            "send follow-up instructions",
            "re-dispatch the affected sub-agent with the needed guidance",
        )
        line = line.replace(
            "no re-dispatch the affected sub-agent with the needed guidance",
            "no inter-agent messaging",
        )
        line = line.replace(
            "Inter-sub-agent `re-dispatch the affected sub-agent with the needed guidance` coordination",
            "Inter-sub-agent messaging",
        )
        line = line.replace(
            "Inter-agent `re-dispatch the affected sub-agent with the needed guidance` coordination",
            "Inter-agent messaging",
        )
        output.append(line)
    return "".join(output)


def _translate_native_vocabulary(text: str) -> str:
    """Rewrite dispatch identifiers while preserving ordinary task prose."""
    output = text
    output = output.replace("opencode `task` tool", "native `subagent` tool")
    output = output.replace("built-in `task` tool", "native `subagent` tool")
    output = output.replace("`subagent_type`", "`agent`")
    output = re.sub(r"\bsubagent_type\b", "agent", output)
    output = output.replace("`run_in_background`", "`background`")
    output = re.sub(r"\brun_in_background\b", "background", output)
    output = re.sub(r"\bTask\(", "subagent(", output)
    output = re.sub(r"\bAgent\(", "subagent(", output)
    output = output.replace("`Task` tool calls", "native `subagent` calls")
    output = output.replace("`Task` tool call", "native `subagent` call")
    output = output.replace("`Task` calls", "native `subagent` calls")
    output = output.replace("`Task` call", "native `subagent` call")
    output = output.replace("Task calls", "native subagent calls")
    output = output.replace("Task call", "native subagent call")
    output = output.replace("blocking `Task` tool", "foreground native `subagent` call (`background=false`)")
    output = output.replace("blocking **`Task`** tool", "foreground native `subagent` call (`background=false`)")
    output = output.replace("blocking **Task** tool", "foreground native `subagent` call (`background=false`)")
    output = output.replace("blocking `Agent` tool", "foreground native `subagent` call (`background=false`)")
    output = output.replace("blocking **`Agent`** tool", "foreground native `subagent` call (`background=false`)")
    output = output.replace("blocking **Agent** tool", "foreground native `subagent` call (`background=false`)")
    output = output.replace("`Task`", "`subagent`")
    output = output.replace("`Agent` tool calls", "native `subagent` calls")
    output = output.replace("`Agent` tool call", "native `subagent` call")
    output = output.replace("`Agent` calls", "native `subagent` calls")
    output = output.replace("`Agent` call", "native `subagent` call")
    output = output.replace("`Agent`", "`subagent`")
    output = output.replace("Task/subagent call", "subagent call")
    output = output.replace(
        "`name=`",
        "`description` plus the role-specific `prompt`",
    )
    output = output.replace("Task spawn", "Subagent dispatch")
    output = _ensure_explicit_background(output)
    return output


def _ensure_explicit_background(text: str) -> str:
    """Add foreground intent to documented native calls that omit it."""
    insertions = [
        (close, arguments)
        for _, close, arguments in find_native_subagent_calls(text)
        if not re.search(r"\bbackground\s*=", arguments)
    ]

    for close, arguments in reversed(insertions):
        separator = "" if not arguments.strip() else ","
        if "\n" in arguments:
            trailing = len(arguments) - len(arguments.rstrip())
            insert_at = close - trailing
            addition = f"{separator}\n  background = false"
        else:
            insert_at = close
            addition = f"{separator} background=false"
        text = f"{text[:insert_at]}{addition}{text[insert_at:]}"
    return text


def find_native_subagent_calls(text: str) -> list[tuple[int, int, str]]:
    """Return balanced native call spans and argument text, respecting quotes."""
    calls: list[tuple[int, int, str]] = []
    cursor = 0
    while True:
        start = text.find("subagent(", cursor)
        if start < 0:
            break
        index = start + len("subagent(")
        depth = 1
        quote: str | None = None
        escaped = False
        while index < len(text) and depth:
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\" and quote:
                escaped = True
            elif quote:
                if char == quote:
                    quote = None
            elif char in {'"', "'"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth:
            cursor = start + len("subagent(")
            continue
        close = index - 1
        arguments = text[start + len("subagent(") : close]
        calls.append((start, close, arguments))
        cursor = index
    return calls


def _remove_empty_fenced_blocks(text: str) -> str:
    """Remove only structurally empty top-level Markdown fence blocks."""
    lines = text.splitlines(keepends=True)
    remove: set[int] = set()
    marker: tuple[str, int] | None = None
    start = 0
    has_content = False
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(```+|~~~+)", line)
        if match:
            token = match.group(1)
            current = (token[0], len(token))
            if marker is None:
                marker = current
                start = index
                has_content = False
            elif current[0] == marker[0] and current[1] >= marker[1]:
                if not has_content:
                    remove.update(range(start, index + 1))
                marker = None
            else:
                has_content = True
            continue
        if marker is not None and line.strip():
            has_content = True
    return "".join(
        line for index, line in enumerate(lines) if index not in remove and not re.fullmatch(r"\s*[-*]\s*\n?", line)
    )


def project_opencode_dispatch_description(text: str) -> str:
    """Remove unsupported team-mode advertising from generated frontmatter."""
    output = _translate_native_vocabulary(text)
    output = re.sub(
        r"\s*[;,.]?\s*(?:(?:pass|use)\s+`?--team`?|" r"combine\s+(?:it\s+)?with\s+`?--team`?)[^.]*\.?",
        "",
        output,
        flags=re.IGNORECASE,
    )
    output = output.replace("[--team]", "")
    output = output.replace(" or --team", "")
    output = output.replace(" and --team", "")
    output = re.sub(r"\s*\|\s*--team\b|--team\b\s*\|\s*", "", output)
    output = output.replace(
        "findings return inline as the call result",
        "each call returns candidate findings for independent validation",
    )
    output = re.sub(r"\s+", " ", output).strip(" ,;")
    output = output.replace("standalone sub-agents Worktree", "standalone sub-agents. Worktree")
    output = output.replace("tool Outputs", "tool. Outputs")
    output = output.replace("perspectives Use", "perspectives. Use")
    output = output.replace("tool Usage:", "tool. Usage:")
    output = output.replace("sub-agents Use when", "sub-agents. Use when")
    return output
