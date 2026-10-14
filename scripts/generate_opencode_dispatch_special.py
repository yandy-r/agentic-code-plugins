#!/usr/bin/env python3
"""Focused OpenCode V2 projections for review and PRP workflows."""

from __future__ import annotations

import re

_PLAN_OVERVIEW = """## What This Skill Does

1. Parse `--parallel`, `--enhanced`, `--dry-run`, `--no-worktree`, `--worktree`,
   and `--visual`, then read the request and referenced files.
2. Dispatch one planner by default, three standalone planning perspectives when
   the user explicitly asks for a multi-perspective plan, or five perspectives
   when `--enhanced` is present.
3. Validate and merge every returned perspective into one plan.
4. Wait for explicit user confirmation before any implementation.

## Flags

| Flag | Effect |
| --- | --- |
| `--parallel` | Shape the plan for dependency-batched parallel implementation. |
| `--enhanced` | Use five standalone perspectives: architecture, risk, testing, security, and UX. |
| `--dry-run` | Print the selected multi-perspective roster and stop without dispatching. |
| `--worktree` | Legacy no-op; shared worktree annotations are enabled by default. |
| `--no-worktree` | Omit shared worktree annotations. |
| `--visual` | Force-write the confirmed plan and render it with `visual-plan`. |

`--parallel` changes the output shape, independently of whether one, three, or
five planning perspectives are dispatched. `--enhanced` selects five
perspectives. An explicit natural-language request for a multi-perspective plan
selects three perspectives when `--enhanced` is absent.

"""

_PLAN_PARSE = """### Step 1 — Parse flags and the user's request

Strip the supported flags from `$ARGUMENTS`. Set `PARALLEL_MODE`,
`ENHANCED_MODE`, `DRY_RUN`, `VISUAL_MODE`, and `WORKTREE_MODE` explicitly.
Default `WORKTREE_MODE=true`; `--no-worktree` sets it false and `--worktree` is
a legacy no-op. Set `PERSPECTIVE_COUNT=5` when `ENHANCED_MODE=true`, otherwise
set it to `3` only when the remaining request explicitly asks for a
multi-perspective plan; default it to `1`.

Read the stripped request and any referenced files. Ask one focused question
before dispatch if the request is ambiguous. `--dry-run` with
`PERSPECTIVE_COUNT=1` aborts because the single-agent path has no roster to
preview.

"""

_PLAN_DISPATCH = """### Step 2 — Dispatch

- `PERSPECTIVE_COUNT=1`: one foreground `planner` call.
- `PERSPECTIVE_COUNT=3`: `architect` (`planner`), `risk-analyst`
  (`codebase-research-analyst`), and `test-strategist`
  (`test-strategy-planner`) in one parallel foreground batch.
- `PERSPECTIVE_COUNT=5`: the same three plus `security-reviewer` and
  `ux-reviewer` (both `research-specialist`) in one parallel foreground batch.

Every call uses the native shape below, with a complete role-specific prompt and
no `sessionID` for a new child:

```text
subagent(agent="<configured-agent>", description="<perspective>",
         prompt="<complete planning prompt>", background=false)
```

Do not set `model`; each configured agent supplies or inherits its model. Include
the original request, referenced context, role focus, confirmation instruction,
and the parallel/worktree directives selected by the flags.

When `DRY_RUN=true`, print the selected three- or five-persona roster and stop
without calling `subagent`.

For a single planner, relay the validated report. For three or five perspectives,
merge architecture, risks, testing, and optional security/UX slices without
dropping a role. A terminal lifecycle state alone is insufficient: require each
candidate report and validate any declared artifact. For contentless completion,
record `sessionID`, inspect edits/artifacts, preserve work, retry at most once,
then report the missing perspective. Follow
`~/.config/opencode/shared/references/standalone-dispatch.md`.

"""


def _project_implementor(text: str) -> str:
    old_contract = re.compile(
        r"You are dispatched via (?:"
        r"[^\n]*— your entire response is returned\n"
        r"inline to the orchestrator in the same turn, so it must be mechanically parseable\."
        r"|[^\n]*\. Your report may be delivered directly or\n"
        r"asynchronously; always return a nonempty, mechanically parseable report\.)"
    )
    replacement = (
        "You are dispatched through OpenCode V2's native `subagent` tool. Return a "
        "nonempty, mechanically parseable report; the parent validates your report "
        "and on-disk work separately, and a host lifecycle state alone does not prove "
        "completion."
    )
    return old_contract.sub(replacement, text, count=1)


def _project_review_checklist(text: str) -> str:
    pattern = re.compile(
        r"Three standalone `code-reviewer` sub-agents,.*?(?=\n\n### Local / Quick Mode Roster)",
        flags=re.DOTALL,
    )
    replacement = (
        "Three standalone `code-reviewer` sub-agents use foreground native "
        "`subagent` calls with `background=false`. Read "
        "[standalone-dispatch.md](~/.config/opencode/shared/references/"
        "standalone-dispatch.md) for the complete dispatch, result, artifact, and "
        "failure contract."
    )
    output = pattern.sub(replacement, text, count=1)
    output = re.sub(
        r"6\. \(Path B only\).*?(?=7\. \(Path B only\))",
        (
            "6. (Path B only) Require `background=false`, nonempty findings in "
            "the Standard Findings Format, and independent scratch-artifact "
            "validation before accepting the reviewer result.\n"
        ),
        output,
        count=1,
        flags=re.DOTALL,
    )
    output = re.sub(
        r"After all 3 reviewers return \(Path B only — see.*?\):",
        (
            "After all 3 foreground reviewer calls return candidate reports and "
            "their scratch artifacts have been checked:"
        ),
        output,
        count=1,
        flags=re.DOTALL,
    )
    return output


def _project_prp_implement(text: str) -> str:
    """Remove Path C choices after the unsupported team branch is stripped."""
    output = text.replace(", or **Path C**", "")
    output = output.replace(" | **Path C**", "")
    return output


def _project_prp_plan(text: str) -> str:
    """Project enhanced standalone researcher calls onto native arguments."""
    output = re.sub(
        r"- Dispatch in a \*\*SINGLE message\*\* with \*\*SEVEN .*?\n",
        (
            "- Dispatch in a **SINGLE message** with **SEVEN native `subagent` "
            "calls**, each with `background=false`; validate every candidate report "
            "against its backstop artifact.\n"
        ),
        text,
        count=1,
    )
    output = re.sub(
        r"- Each call uses `@prp-researcher` with the `name` field set to the role " r"name .*?\n",
        (
            '- Each call uses `agent="prp-researcher"`; put the role name in '
            "`description` and the complete role instructions in `prompt`.\n"
        ),
        output,
        count=1,
    )
    output = output.replace(
        "dispatch mode (`--parallel` vs `--team`) is invisible to it",
        "standalone dispatch details are invisible to it",
    )
    output = re.sub(
        r"### Path B — Parallel sub-agents.*?(?=#### Path B \(enhanced\))",
        (
            "### Path B — Three standalone researchers (`PARALLEL_MODE=true`)\n\n"
            "Dispatch `patterns-research`, `quality-research`, and "
            "`infra-research` in one parallel foreground batch. Each call uses "
            '`agent="prp-researcher"`, the role name in `description`, a complete '
            "role prompt, and `background=false`. Validate every candidate report "
            "against its declared backstop artifact and apply the canonical "
            "contentless-result policy before synthesis.\n\n"
        ),
        output,
        count=1,
        flags=re.DOTALL,
    )
    output = re.sub(
        r"If `ENHANCED_MODE=true` or `PARALLEL_MODE=true` was used for research "
        r"dispatch.*?(?=\n\nIf `ENHANCED_MODE=true`)",
        (
            "For parallel or enhanced research, verify every expected backstop file. "
            "If a report is empty, record its `sessionID`, inspect the artifact, "
            "preserve valid work, retry at most once, and still report the child "
            "response incomplete; an artifact preserves work but does not prove a "
            "response.\n"
        ),
        output,
        count=1,
        flags=re.DOTALL,
    )
    return output


def _project_plan(text: str) -> str:
    """Restore single, three-, and five-perspective native planning modes."""
    output = re.sub(
        r"## What This Skill Does.*?(?=## When to Use)",
        _PLAN_OVERVIEW,
        text,
        count=1,
        flags=re.DOTALL,
    )
    output = re.sub(
        r"### Step 1 — Parse flags and the user's request.*?(?=### Step 2 — Dispatch)",
        _PLAN_PARSE,
        output,
        count=1,
        flags=re.DOTALL,
    )
    output = re.sub(
        r"### Step 2 — Dispatch.*?(?=### Step 2\.5 — Validate the plan before relaying)",
        _PLAN_DISPATCH,
        output,
        count=1,
        flags=re.DOTALL,
    )
    output = output.replace(
        "After a Path B or Path C merge — that is, whenever multiple sub-agents contributed to the plan —",
        "Whenever three or five sub-agents contributed to the plan,",
    )
    output = output.replace(
        "discard and re-dispatch Path A or re-run Path B with the new direction",
        "discard and re-dispatch the selected native planning mode with the new direction",
    )
    return output
