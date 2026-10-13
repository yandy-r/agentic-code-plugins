---
name: plan
description: 'Creates lightweight conversational implementation plans and waits for approval. Use when outlining an approach, breaking down a change before coding, or comparing implementation options.'
argument-hint: '[--parallel] [--team] [--enhanced] [--dry-run] [--no-worktree] [--visual] <what you want to plan>'
allowed-tools:
  - Read
  - Grep
  - Glob
  - Agent
  - Task
  - TodoWrite
  - AskUserQuestion
  - TeamCreate
  - TeamDelete
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - SendMessage
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(test:*)
  - Bash(git:*)
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/prepare-feature-branch.sh:*)'
---

# Plan Skill

Create a comprehensive implementation plan before writing any code. This is the lightweight conversational planner. For heavier planning tracks, see the comparison table at the bottom.

**Core rule**: You will **NOT** write any code until the user explicitly confirms the plan with "yes", "proceed", "approved", or similar affirmative.

---

## What This Skill Does

1. **Parse flags and the request** — Extract `--parallel`, `--team`, `--enhanced`, `--dry-run`, then read the user input and any referenced files
2. **Dispatch planner(s)** — Either dispatch a single `ycc:planner` (default), deploy a 3-persona team (`--team`), fan out 5 standalone parallel sub-agents (`--enhanced` alone), or deploy a 5-persona team (`--enhanced --team`). In parallel mode, augment the prompt(s) with output-shape directives
3. **Merge and relay the plan** — For the single-agent path, relay verbatim. For the team path, merge teammate outputs into one unified plan
4. **Wait for confirmation** — MUST receive explicit user approval before proceeding

## Flags

| Flag            | Effect                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--parallel`    | Instruct the planner(s) to emit a parallel-capable plan: a `Batches` summary section at the top, hierarchical step IDs (`1.1`, `1.2`, `2.1`), and explicit `Depends on [...]` annotations on every step. Enables in-conversation parallel implementation via `ycc:implementor` agents, or file-based handoff to `/ycc:prp-implement --parallel`.                                                                                                                                                                                                                                                   |
| `--team`        | Dispatch a 3-persona planning team (architect / risk-analyst / test-strategist) under a shared `TeamCreate`/`TaskList` with coordinated shutdown. Produces a richer plan by merging structural, risk, and testing perspectives. Heavier than the default single-agent path.                                                                                                                                                                                                                                                                                                                        |
| `--enhanced`    | Grow the persona roster from 3 to **5**, adding `security-reviewer` (threat model, input validation, authn/authz, secrets, dependency risk) and `ux-reviewer` (user-facing impact — UI, CLI, API responses, error messages). When passed alone, dispatches the 5 personas as **standalone parallel sub-agents** (Path C — works in every bundle). Combine with `--team` (Claude Code only) for team-coordinated dispatch (Path B enhanced). Composes with `--parallel` and `--no-worktree`. Lighter than `/ycc:prp-plan --enhanced` (which fans out to 7 researchers and writes an artifact file). |
| `--dry-run`     | Valid with `--team` (prints team-coordinated roster) or `--enhanced` (prints standalone or team roster depending on whether `--team` is also present). Prints the roster, then exits without spawning any agents.                                                                                                                                                                                                                                                                                                                                                                                  |
| `--worktree`    | (legacy — now default; safe to omit) Previously required to emit worktree annotations; the annotations are now emitted by default. Accepted as a silent no-op so existing pipelines continue to work.                                                                                                                                                                                                                                                                                                                                                                                              |
| `--no-worktree` | Opt out of worktree annotations. The plan will not contain a `## Worktree Setup` section or per-task `**Worktree**:` annotations.                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `--visual`      | Force-write the plan to a file, then render it as an Agent-Native visual artifact (MDX) via `ycc:visual-plan`; local-files by default, hosted link requires `--share`.                                                                                                                                                                                                                                                                                                                                                                                                                             |

**Flag interaction**:

- `--parallel` and `--team` are **independent and combinable**. `--parallel` shapes the plan's _output format_; `--team` switches the _dispatch mechanism_ to a coordinated team. Pass both for a multi-perspective plan formatted for parallel execution.
- `--enhanced` widens the persona _roster_ (3 → 5 personas). When passed alone it selects **Path C** (5 standalone parallel sub-agents); when combined with `--team` it selects **Path B enhanced** (5-persona team). Combine freely with `--parallel` and `--no-worktree`.
- `--dry-run` requires `--team` or `--enhanced` (or both). The single-agent path has nothing to dry-run.
- `--no-worktree` opts out of all worktree annotations. When omitted (the default), the plan emits a `## Worktree Setup` section naming the one feature worktree; all tasks (parallel and sequential) share that single path.

**Compatibility note**: `--team` depends on team tools (`TeamCreate`, `SendMessage`, etc.) which only Claude Code ships — in Cursor or Codex bundles `--team` aborts with a compatibility message. `--enhanced` alone runs in every bundle (Path C uses parallel `Task` calls without team tools). Only the combination `--enhanced --team` requires Claude Code; in Cursor or Codex, drop `--team` and `--enhanced` will dispatch via Path C.

**Note**: `--parallel` on `/ycc:plan` shapes the _output_, not the research phase. For research fan-out on larger features, use `/ycc:prp-plan --parallel` (sub-agent fan-out) or `/ycc:prp-plan --team` (Claude Code only; shared-task-list coordination).

## When to Use

Use this skill when:

- Starting a new feature
- Making significant architectural changes
- Working on complex refactoring
- Multiple files/components will be affected
- Requirements are unclear or ambiguous

---

## Process

### Step 1 — Parse flags and the user's request

**Flag parsing**: Extract `--parallel`, `--team`, `--enhanced`, `--dry-run`, `--no-worktree`, `--worktree`, and `--visual` from `$ARGUMENTS` before processing. Strip them out. Set `PARALLEL_MODE=true|false`, `AGENT_TEAM_MODE=true|false`, `ENHANCED_MODE=true|false`, `DRY_RUN=true|false`, `VISUAL_MODE=true|false`. Default `WORKTREE_MODE=true`; set `WORKTREE_MODE=false` if `--no-worktree` is present. `--worktree` is accepted as a legacy no-op (matches the default). The remaining text is the user's request.

```bash
# Default ON; pass --no-worktree to opt out. --worktree accepted as legacy no-op.
WORKTREE_MODE=true
case " $ARGUMENTS " in
  *" --no-worktree "*) WORKTREE_MODE=false ;;
esac
ARGUMENTS="${ARGUMENTS//--no-worktree/}"
ARGUMENTS="${ARGUMENTS//--worktree/}"  # legacy no-op

ENHANCED_MODE=false
case " $ARGUMENTS " in
  *" --enhanced "*) ENHANCED_MODE=true ;;
esac
ARGUMENTS="${ARGUMENTS//--enhanced/}"

VISUAL_MODE=false
case " $ARGUMENTS " in
  *" --visual "*) VISUAL_MODE=true ;;
esac
ARGUMENTS="${ARGUMENTS//--visual/}"
```

**Validation**:

- `--enhanced` does **not** auto-promote to team mode. When `ENHANCED_MODE=true` and `AGENT_TEAM_MODE=false`, dispatch via the new **Path C** below: a 5-persona roster spawned as standalone parallel sub-agents with no `TeamCreate`. Add `--team` explicitly to opt in to team-coordinated dispatch (Path B enhanced).
- If `DRY_RUN=true` and both `AGENT_TEAM_MODE=false` and `ENHANCED_MODE=false` → abort with: `--dry-run requires --team or --enhanced (no-op for the single-agent path).`
- If `--team` is invoked from a Cursor or Codex bundle, abort with the existing compatibility message: `--team requires team tools, which Cursor/Codex bundles do not ship. Use --parallel instead.`
- If `--team` is passed and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is not set to `1` in the environment, abort with: `--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Use --parallel instead, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Claude Code settings if you intentionally want agent-team dispatch.`
- `--enhanced` alone is supported in every bundle: Path C uses parallel `Task` calls without team tools. Only the `--enhanced --team` combination requires Claude Code; in Cursor or Codex, abort with: `--enhanced --team requires team tools, which Cursor/Codex bundles do not ship. Drop --team to use the standalone 5-persona path.`
- `--visual` is orthogonal and runs after the plan is produced. Because `/ycc:plan` writes no file by default, `--visual` forces a plan-file write first. `--dry-run` short-circuits it (prints intent only).

Read the stripped `$ARGUMENTS`. If it references a file path, read that file for context. If the request is ambiguous, ask a single focused clarifying question **before** dispatching.

### Step 2 — Dispatch

Choose dispatch path based on `AGENT_TEAM_MODE` and `ENHANCED_MODE`:

- **`AGENT_TEAM_MODE=false`, `ENHANCED_MODE=false`** (default) → **Path A**: single `ycc:planner` agent.
- **`AGENT_TEAM_MODE=false`, `ENHANCED_MODE=true`** → **Path C**: 5-persona roster (3 baseline + `security-reviewer` + `ux-reviewer`) spawned as standalone parallel sub-agents. No `TeamCreate`.
- **`AGENT_TEAM_MODE=true`, `ENHANCED_MODE=false`** → **Path B**: 3-persona planning team.
- **`AGENT_TEAM_MODE=true`, `ENHANCED_MODE=true`** → **Path B (enhanced)**: 5-persona planning team (3 baseline + `security-reviewer` + `ux-reviewer`). All Path B steps below apply with the wider roster.

---

### Path A — Single-agent dispatch (default)

Use the Agent tool with `subagent_type: "ycc:planner"`. In the prompt, include:

- The user's original request (verbatim)
- Any file paths or context they referenced
- A note that the agent should follow its Plan Format and end with `**WAITING FOR CONFIRMATION**: Proceed with this plan? (yes / no / modify)`
- **If `PARALLEL_MODE=true`**: append the parallel output directives (see below)

#### Sequential prompt (`PARALLEL_MODE=false` — default)

```
The user asked: "<user's request>"

Related context they pointed to: <files, URLs, or "none">

Produce a full implementation plan following your Plan Format. Use the
Read/Grep/Glob tools to analyze the codebase and include concrete file
paths. End with your standard confirmation prompt.
```

#### Parallel prompt (`PARALLEL_MODE=true`)

Append these directives to the sequential prompt:

```
PARALLEL OUTPUT MODE:

In addition to your standard Plan Format, shape the output for parallel
execution:

1. **Use hierarchical step IDs** — Number steps as `1.1`, `1.2`, `2.1`,
   `2.2`, etc. where the first digit is the batch and the second is the
   task within the batch.

2. **Populate the Dependencies field on every step** — Use the hierarchical
   IDs (e.g., `Depends on [1.1, 1.2]` or `Depends on [none]`). Never leave
   the field as "None / Requires step X" — always use the explicit format.

3. **Add a `## Batches` section immediately after `## Architecture Changes`
   and before `## Implementation Steps`**. Format:

   ## Batches

   Steps grouped by dependency for parallel execution. Steps within the
   same batch run concurrently; batches run in order.

   | Batch | Steps         | Depends On | Parallel Width |
   | ----- | ------------- | ---------- | -------------- |
   | B1    | 1.1, 1.2, 1.3 | —          | 3              |
   | B2    | 2.1           | B1         | 1              |
   | B3    | 3.1, 3.2      | B2         | 2              |

   - **Total steps**: N
   - **Total batches**: M
   - **Max parallel width**: X

4. **Batch construction rules**:
   - Steps with no dependencies go in Batch 1
   - A step joins the earliest batch where all its dependencies are in
     prior batches
   - Steps modifying the same file MUST be in different batches (no
     concurrent writes)
   - Cross-cutting changes (shared types, global config) get a dedicated
     early batch so downstream steps can depend on them
   - Prefer wide-shallow graphs (many independent steps per batch) over
     narrow-deep chains — maximize parallel width

5. **Still end with** `**WAITING FOR CONFIRMATION**: Proceed with this
   plan? (yes / no / modify)`
```

#### Worktree prompt (default — `WORKTREE_MODE=true`; skipped when `--no-worktree`)

By default, append these directives to the prompt. When `--no-worktree` is passed (`WORKTREE_MODE=false`), omit this block entirely and do not emit any worktree annotations.

```
WORKTREE MODE:

The plan consumer will run all tasks in a single shared git worktree.
In your emitted plan:

1. Add a top-level `## Worktree Setup` section BEFORE the Batches summary
   (or before Implementation Steps when there is no Batches section):

   ## Worktree Setup

   - **Parent**: <repo-root>/.claude/worktrees/<repo>-<feature>/ (branch: feat/<feature>)

   All tasks — parallel and sequential — share this one path. Do NOT add a
   `**Children**:` list and do NOT add per-task `**Worktree**:` annotations.

See `ycc/skills/_shared/references/worktree-strategy.md` §1–§2 for the
canonical single-worktree contract.
```

---

### Path C — Parallel sub-agent dispatch (`--enhanced` without `--team`)

See `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md` for the full standalone-dispatch contract (`Task` vs `Agent`+team, anti-patterns, backstop policy).

> **MANDATORY — STANDALONE SUB-AGENTS, NO TEAM**
>
> Path C dispatches the same 5-persona roster as Path B (enhanced) but **without** any
> team tooling. Do NOT call `TeamCreate`, `TaskCreate`, `SendMessage`, or `TeamDelete`.
> Every dispatch below uses the blocking `Task` tool with `subagent_type=` and a
> human-readable `description=` label for the merge step — never `Agent` (which spawns a
> background teammate whose output is not returned inline). This path mirrors the
> standalone fan-out pattern in `ycc:prp-plan`.
>
> 1. **No team lifecycle** — no `TeamCreate`, no shared `TaskList`, no shutdown messages
> 2. `Task` with `subagent_type=` and `description=` — **one message, FIVE `Task` calls**, fired in parallel
> 3. Wait for all 5 sub-agent responses to return (they return inline as `Task` tool results — `Task` blocks until each sub-agent completes)
> 4. Merge outputs per Path B §B.7 — same Markdown sections, same omission rules

#### C.1 Persona roster

Identical to Path B enhanced (5 personas):

| Sub-agent name      | `subagent_type`                 | Role focus                                                                         |
| ------------------- | ------------------------------- | ---------------------------------------------------------------------------------- |
| `architect`         | `ycc:planner`                   | Structural plan, phases, file layout, dependencies                                 |
| `risk-analyst`      | `ycc:codebase-research-analyst` | Risks, edge cases, rollback, migration concerns                                    |
| `test-strategist`   | `ycc:test-strategy-planner`     | Testing strategy, validation commands, acceptance criteria                         |
| `security-reviewer` | `ycc:research-specialist`       | Threat model, input validation, authn/authz, secrets handling, dependency risk     |
| `ux-reviewer`       | `ycc:research-specialist`       | User-facing impact (UI, CLI, API responses, error messages); skip if internal-only |

#### C.2 Dry-run gate (if `DRY_RUN=true`)

Print:

```
Dispatch:    standalone parallel sub-agents (no team)
Sub-agents:  5
  - architect         subagent_type=ycc:planner                    task=Structural plan, phases, file layout, dependencies
  - risk-analyst      subagent_type=ycc:codebase-research-analyst  task=Risks, edge cases, rollback, migration concerns
  - test-strategist   subagent_type=ycc:test-strategy-planner      task=Testing strategy, validation commands, acceptance criteria
  - security-reviewer subagent_type=ycc:research-specialist        task=Threat model, input validation, authn/authz, secrets, dependency risk
  - ux-reviewer       subagent_type=ycc:research-specialist        task=User-facing impact (UI, CLI, API responses, error messages); skip if internal-only
Batches:     1  (single message, 5 parallel Task calls)
```

Do **not** spawn any agents. Exit the skill.

#### C.3 Spawn the sub-agents (single message, 5 Task calls)

In ONE assistant message, issue 5 `Task` tool calls in parallel. Each call:

- Sets `subagent_type` and `description` per the C.1 roster
- Does **NOT** set `team_name=` or `name=` — those fields are exclusive to `Agent`+team dispatch
- Uses the same role-specific prompt content as Path B §B.5, with the following adjustment for the 3 baseline personas: **omit** the "coordinate via `SendMessage` if you discover work overlapping another teammate's scope" line — there is no team channel in Path C. Each prompt MUST still include:
  - The user's original request (verbatim)
  - Any file paths or context they referenced
  - The role focus (from C.1)
  - The standard confirmation prompt instruction
  - If `PARALLEL_MODE=true`: the parallel output directives from Path A (Parallel prompt section)
  - If `WORKTREE_MODE=true` (default): the worktree directives from Path A (Worktree prompt section)

For `security-reviewer` and `ux-reviewer`, copy the role-specific prompt verbatim from `${CLAUDE_PLUGIN_ROOT}/skills/plan/references/enhanced-personas.md`. Append the same `PARALLEL_MODE` and `WORKTREE_MODE` directives so all 5 sub-agents emit consistent output.

#### C.4 Collect results

Sub-agents return inline as `Task` tool results. There is no shared `TaskList` to poll —
gather the 5 outputs directly from the tool-result block.

Failure handling (no shutdown calls needed since no team was created):

- `architect` failure → critical; abort the skill with a clear error.
- `risk-analyst` or `test-strategist` failure → record "partial plan — {role} did not complete" and proceed with reduced merge, noting the gap in the relayed plan.
- `security-reviewer` or `ux-reviewer` failure → non-critical; record the gap ("partial plan — {role} did not complete; security/UX coverage may be incomplete") and proceed.

#### C.5 Merge outputs

Apply the Path B §B.7 merge rules verbatim — same `## Overview`, `## Architecture Changes`, `## Implementation Steps`, `## Risks & Mitigations`, `## Testing Strategy`, `## Security Considerations`, `## UX Impact`, `## Success Criteria` sections, same omission rules for `security-reviewer` / `ux-reviewer` no-finding responses, same `PARALLEL_MODE` Batches re-indexing rule. End with the standard confirmation prompt: `**WAITING FOR CONFIRMATION**: Proceed with this plan? (yes / no / modify)`.

---

### Path B — Agent-team dispatch (`AGENT_TEAM_MODE=true`)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path B you MUST use the agent-team lifecycle. Do NOT mix standalone sub-agents with
> team dispatch. Every `Agent` call below MUST include `team_name=` AND `name=`.
>
> 1. `TeamCreate` FIRST — before any agent spawn
> 2. `TaskCreate` — register all 3 subtasks in the shared task list
> 3. `Agent` with `team_name=` — one message, three calls
> 4. `TaskList` — wait for all teammates to mark complete
> 5. `SendMessage({type:"shutdown_request"})` — shut down all teammates
> 6. `TeamDelete` — clean up
>
> If `TeamCreate` fails, abort the skill with a clear error. Do NOT silently fall back
> to Path A. Refer to `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`
> for the full lifecycle contract.

#### B.1 Build the team name

Sanitize the user's request to produce `<sanitized-request>`:

- Lowercase; replace non-`[a-z0-9-]` with `-`; collapse runs of `-`; trim; truncate to
  **20 characters** max. Fall back to `untitled` if empty.

Team name: `plan-<sanitized-request>`.

#### B.2 Dry-run gate (if `DRY_RUN=true`)

Print (when `ENHANCED_MODE=false`):

```
Team name:   plan-<sanitized-request>
Teammates:   3
  - architect       subagent_type=ycc:planner                    task=Structural plan, phases, file layout, dependencies
  - risk-analyst    subagent_type=ycc:codebase-research-analyst  task=Risks, edge cases, rollback, migration concerns
  - test-strategist subagent_type=ycc:test-strategy-planner      task=Testing strategy, validation commands, acceptance criteria
Batches:     1  (batch 1: architect, risk-analyst, test-strategist)
Dependencies: none  (flat graph)
```

Print (when `ENHANCED_MODE=true`):

```
Team name:        plan-<sanitized-request>
Teammates:        5
  - architect         subagent_type=ycc:planner                    task=Structural plan, phases, file layout, dependencies
  - risk-analyst      subagent_type=ycc:codebase-research-analyst  task=Risks, edge cases, rollback, migration concerns
  - test-strategist   subagent_type=ycc:test-strategy-planner      task=Testing strategy, validation commands, acceptance criteria
  - security-reviewer subagent_type=ycc:research-specialist        task=Threat model, input validation, authn/authz, secrets, dependency risk
  - ux-reviewer       subagent_type=ycc:research-specialist        task=User-facing impact (UI, CLI, API responses, error messages); skip if internal-only
Batches:          1  (batch 1: all 5 teammates)
Dependencies:     none  (flat graph)
```

Do **not** call `TeamCreate` or any team/task/agent tools. Exit the skill.

#### B.3 Create the team

```
TeamCreate: team_name="plan-<sanitized-request>", description="Multi-perspective planning team for: <user request>"
```

On failure, abort.

#### B.4 Register subtasks

Create one task per teammate in the shared task list (flat graph — no dependencies). When `ENHANCED_MODE=false`, register **3** tasks; when `ENHANCED_MODE=true`, register **5** tasks (the 3 baseline plus `security-reviewer` and `ux-reviewer`):

```
TaskCreate: subject="architect: structural plan for <user request>", description="..."
TaskCreate: subject="risk-analyst: risks and edge cases for <user request>", description="..."
TaskCreate: subject="test-strategist: testing strategy for <user request>", description="..."
# When ENHANCED_MODE=true, also:
TaskCreate: subject="security-reviewer: threat model for <user request>", description="..."
TaskCreate: subject="ux-reviewer: user-facing impact for <user request>",  description="..."
```

#### B.5 Spawn the teammates (single message, N Agent calls)

When `ENHANCED_MODE=false` (default — 3 personas):

| Teammate name     | `subagent_type`                 | Role focus                                                 |
| ----------------- | ------------------------------- | ---------------------------------------------------------- |
| `architect`       | `ycc:planner`                   | Structural plan, phases, file layout, dependencies         |
| `risk-analyst`    | `ycc:codebase-research-analyst` | Risks, edge cases, rollback, migration concerns            |
| `test-strategist` | `ycc:test-strategy-planner`     | Testing strategy, validation commands, acceptance criteria |

When `ENHANCED_MODE=true` (5 personas):

| Teammate name       | `subagent_type`                 | Role focus                                                                         |
| ------------------- | ------------------------------- | ---------------------------------------------------------------------------------- |
| `architect`         | `ycc:planner`                   | Structural plan, phases, file layout, dependencies                                 |
| `risk-analyst`      | `ycc:codebase-research-analyst` | Risks, edge cases, rollback, migration concerns                                    |
| `test-strategist`   | `ycc:test-strategy-planner`     | Testing strategy, validation commands, acceptance criteria                         |
| `security-reviewer` | `ycc:research-specialist`       | Threat model, input validation, authn/authz, secrets handling, dependency risk     |
| `ux-reviewer`       | `ycc:research-specialist`       | User-facing impact (UI, CLI, API responses, error messages); skip if internal-only |

Spawn all teammates in **ONE message** with **N `Agent` tool calls** (N=3 or N=5), each with
`team_name="plan-<sanitized-request>"` and the role-specific `name` above.

For the 3 baseline personas, each teammate's prompt MUST include:

- The user's original request (verbatim)
- Any file paths or context they referenced
- The teammate's role focus (from the table) — make it clear what slice of the plan
  this teammate owns
- Instruction to coordinate via `SendMessage` if they discover work overlapping another
  teammate's scope (reference the teammate roster so they know who is working alongside
  them)
- If `PARALLEL_MODE=true`: append the same parallel output directives from Path A
  (section "Parallel prompt") — each teammate should structure its own slice with
  hierarchical step IDs and `Depends on` annotations
- If `WORKTREE_MODE=true` (default): append the same worktree directives from Path A
  (section "Worktree prompt") — teammates share the single feature worktree and must
  not emit per-task child paths. Omit when `--no-worktree` was passed.

For `security-reviewer` and `ux-reviewer` (when `ENHANCED_MODE=true`), copy the role-specific prompt verbatim from `${CLAUDE_PLUGIN_ROOT}/skills/plan/references/enhanced-personas.md`. Append the same `PARALLEL_MODE` and `WORKTREE_MODE` directives as above so all 5 teammates emit consistent output.

#### B.6 Monitor and collect results

Use `TaskList` to confirm all teammate tasks (3 or 5) are `completed` before merging. If any teammate
errors, record the failure in `TaskList` and decide per severity:

- `architect` failure → critical; abort with error, shut down remaining teammates, `TeamDelete`.
- `risk-analyst` or `test-strategist` failure → record "partial plan — {role} did not
  complete" and proceed with a reduced merge, noting the gap in the relayed plan.
- `security-reviewer` or `ux-reviewer` failure (enhanced only) → non-critical; record the gap
  ("partial plan — {role} did not complete; security/UX coverage may be incomplete") and proceed.

#### B.7 Merge outputs

Synthesize the teammate outputs (3 or 5) into a single unified plan following the standard
`ycc:planner` Plan Format. Merging rules:

- **Overview / Summary**: use `architect`'s framing.
- **Architecture Changes / Implementation Steps**: primarily `architect`; fold in
  `risk-analyst`'s findings as per-step risk callouts or a dedicated `## Risks &
Mitigations` section.
- **Testing Strategy / Success Criteria**: use `test-strategist`'s content verbatim.
- **Batches section** (if `PARALLEL_MODE=true`): use `architect`'s numbering; re-index
  if `risk-analyst` or `test-strategist` added follow-on steps.
- When `ENHANCED_MODE=true`, also fold in:
  - **`security-reviewer`** → add a top-level `## Security Considerations` section listing the threat-model findings and validation requirements. If specific steps need callouts (e.g., "input must be validated against …"), also annotate the matching `architect` step with `> **Security**: …`. If `security-reviewer` returned no significant findings, omit the section entirely (do not write "N/A").
  - **`ux-reviewer`** → add a top-level `## UX Impact` section with Before / After / Interaction Changes. If `ux-reviewer` returned "Internal change — no user-facing UX impact", omit the section entirely.
- End with the standard confirmation prompt: `**WAITING FOR CONFIRMATION**: Proceed
with this plan? (yes / no / modify)`

#### B.8 Shutdown and cleanup

After merging (success or partial), shut down every teammate that was spawned (3 or 5), then `TeamDelete`:

```
SendMessage(to="architect",         message={type:"shutdown_request"})
SendMessage(to="risk-analyst",      message={type:"shutdown_request"})
SendMessage(to="test-strategist",   message={type:"shutdown_request"})
# When ENHANCED_MODE=true, also:
SendMessage(to="security-reviewer", message={type:"shutdown_request"})
SendMessage(to="ux-reviewer",       message={type:"shutdown_request"})
TeamDelete
```

Always `TeamDelete` — even on abort or partial failure.

---

### Step 2.5 — Validate the plan before relaying

After the `ycc:planner` agent returns its plan, perform these quick checks BEFORE presenting it to the user. Use only the tools already available to this skill.

#### Check 1: Structure completeness

Scan the agent's response for these sections. If any **required** section is missing, re-dispatch the planner with a note to include the missing section(s).

**Required** (re-dispatch if missing):

- `## Overview` or `## Summary`
- `## Implementation Steps` or `## Step-by-Step Tasks`
- `## Testing Strategy`
- `**WAITING FOR CONFIRMATION**`

**Expected** (append a note to the plan if missing, but do NOT re-dispatch):

- `## Architecture Changes` or `## Requirements`
- `## Risks` or `## Risks & Mitigations`
- `## Success Criteria`

#### Check 2: File path spot-check

Extract up to 10 file paths from the plan (backtick-quoted paths or paths after `File:` annotations). For each, use Glob or `Bash: test -f "<path>"` to check existence.

- If **all paths exist**: clean pass, append nothing.
- If **>30% of checked paths are missing**: append a validation note before relaying:

  > **Validation Note**: {N} of {M} file paths in this plan could not be found in the current codebase. This may indicate renamed files, planned new files, or stale references. Review the paths in the Implementation Steps before confirming.

- If **a few paths are missing** (≤30%): append a lighter note listing only the missing paths.

#### Check 3: Parallel mode integrity (`PARALLEL_MODE=true` only)

If the plan was requested with `--parallel`, verify:

- A `## Batches` section exists in the response
- At least one `Depends on` annotation exists
- Step IDs use hierarchical format (N.N)

If any are missing, re-dispatch the planner (or `architect` teammate, if in Path B — but only _after_ `TeamDelete` has run; do not try to re-spawn inside a torn-down team) with a directive to add the missing parallel annotations.

#### Check 4: Multi-agent merge integrity (Path B and Path C)

After a Path B or Path C merge — that is, whenever multiple sub-agents contributed to the plan — verify the unified plan reflects every spawned perspective:

- `architect` slice: `## Implementation Steps` (or equivalent) is present and non-empty
- `risk-analyst` slice: a `## Risks` / `## Risks & Mitigations` section OR per-step risk callouts are present
- `test-strategist` slice: `## Testing Strategy` is present and non-empty
- When `ENHANCED_MODE=true`, also verify:
  - `security-reviewer` slice: `## Security Considerations` is present **OR** the merged plan documents that no significant security risks were found (e.g., a one-line note in `## Risks` such as "Security-reviewer: no significant risks identified"). Per-step `> **Security**:` callouts also satisfy this check.
  - `ux-reviewer` slice: `## UX Impact` is present **OR** the merged plan documents "Internal change — no user-facing UX impact". Both forms count as covered.

If the merge dropped a slice (e.g., because a teammate errored), append a visible note:

> **Validation Note**: The {role} perspective could not be included in this plan (teammate error). Review the plan for gaps in {area} before confirming.

---

### Step 3 — Relay the plan

Present the agent's plan to the user verbatim, including any validation notes appended in Step 2.5. Do not summarize, do not shorten, do not add your own commentary above it.

### Step 4 — WAIT

Do not touch any code until the user responds.

Valid user responses:

- **"yes" / "proceed" / "approved"** → proceed to implement
- **"modify: ..."** → re-dispatch the planner (Path A) or re-run Path B (new TeamCreate — the previous team was deleted in B.8) with the modification request and the previous plan as context
- **"different approach: ..."** → discard and re-dispatch Path A or re-run Path B with the new direction
- **"skip phase N and do phase M first"** → re-dispatch with the reorder request
- **"no"** → stop, do not implement

**Team-mode re-dispatch note**: Path B's team is `TeamDelete`d in Step B.8 _before_ the user sees the plan. Any re-dispatch from this step creates a **new** team (same name is fine — the old one no longer exists) with a fresh set of teammates. Do not attempt to send messages to teammates from the prior team.

**Path C re-dispatch note**: Path C never created a team, so there is no teardown to worry about. Any re-dispatch from this step simply fires a fresh batch of 5 parallel `Task` calls (no `team_name=`).

---

### Step 5 — Visual rendering (if `VISUAL_MODE=true`)

This step runs **only after** the user confirms the plan in Step 4 (it is the terminal decorator step). It never re-orders or substitutes for any earlier phase.

- **If `DRY_RUN=true`**: print `visual generation would run` and skip — do not force any write and do not invoke `ycc:visual-plan`. (`--dry-run` already exits earlier at the dispatch gate; this is the no-op contract for the combination.)
- **Otherwise**:
  1. **Force-write the plan to a file.** `/ycc:plan` keeps the plan in-chat and writes no artifact by default, so there is nothing on disk to visualize. Write the confirmed plan verbatim to a concrete path. Default location: `docs/prps/plans/<slug>.plan.md`, where `<slug>` is the user's request sanitized to kebab-case (same scheme as Path B §B.1: lowercase, non-`[a-z0-9-]` → `-`, collapse runs, trim, truncate to 20 chars, fallback `untitled`). Create the directory first (`mkdir -p docs/prps/plans`). Resolve the path to an **absolute** path.
  2. **Invoke** `ycc:visual-plan <absolute-plan-path>` with the absolute path written in the previous step.
  3. **Surface the link** that `ycc:visual-plan` prints (hosted URL, localhost preview, or `local files only`). Do not re-derive the output directory yourself.

See the canonical contract for the full force-write-first rule and `--dry-run` short-circuit:

```
${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/visual-mode.md
```

---

## Visual mode

`--visual` is the single, shared visual decorator described in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/visual-mode.md`. It is a
**terminal decorator step** — it does not change how the plan is researched,
dispatched, or relayed. It runs once, last, on the confirmed plan.

**FORCE-WRITE-FIRST (mandatory for `/ycc:plan`)**: unlike the other planning
skills, `/ycc:plan` writes **no** plan artifact by default — the plan stays
in-chat. There is therefore nothing on disk to visualize. When `VISUAL_MODE` is
set (and **not** `--dry-run`), the skill MUST:

1. **Write the otherwise-inline plan to a concrete file path first.** Default:
   `docs/prps/plans/<slug>.plan.md` (absolute path; directory created if
   missing). This forced write happens even though it would normally be skipped.
2. **Then invoke** `ycc:visual-plan <absolute-plan-path>` with that absolute
   path.

Without the forced write there is no input for `ycc:visual-plan`, so the
force-write is required, not optional. Under `--dry-run` this is moot: the
skill prints `visual generation would run` and forces no write (see §2.1 and §4
of the canonical reference). `ycc:visual-plan` derives its `visual/` output
directory relative to the plan path it is handed and never edits the plan file.

---

## Important Notes

**CRITICAL**: This skill will NOT write any code until the user explicitly confirms.

Do not summarize, do not touch files, do not run commands beyond read-only analysis. Wait.

If the user's instructions are unclear after the planner produces a draft, ask a focused clarifying question rather than guessing, then re-dispatch the planner with the clarification.

The `ycc:planner` agent owns the plan format, worked examples, sizing/phasing guidance, and red-flag checks. This skill is an orchestration layer — it decides _when_ to plan and _what_ to do with the plan, not _how_ a plan should be structured.

For Path B's team lifecycle contract (sanitization, shutdown sequence, failure policy), refer to:

```
${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md
```

---

## Integration with ycc

After planning, depending on what the user approves:

- Use `/ycc:prp-implement` if they want rigorous per-task validation loops (requires a PRP-format plan file — consider running `/ycc:prp-plan` first if you want that workflow)
- Use `/ycc:implement-plan` if the work was structured via `/ycc:parallel-plan`
- Use `/ycc:code-review` to review completed implementation
- Use `/ycc:git-workflow --commit` or `/ycc:prp-commit` to commit

### Executing a Parallel Plan

If the plan was produced with `--parallel` (has a `Batches` section and `Depends on` annotations), after the user confirms you have two options for parallel execution:

**Option 1 — In-conversation parallel execution (lightweight)**

Before dispatching any `ycc:implementor` agents, prepare the feature branch so agents do not commit on `main`:

- **`WORKTREE_MODE=true` (default)** — the plan already names the parent worktree at `<repo-root>/.claude/worktrees/<repo>-<feature>/` (branch `feat/<feature>`). Run `setup-worktree.sh parent <repo> <feature>` once, then dispatch agents with `Working directory: <parent path>`.
- **`WORKTREE_MODE=false` (`--no-worktree`)** — derive `FEATURE_SLUG` from the user's request using the same sanitization as Path B §B.1 (lowercase, non-`[a-z0-9-]` → `-`, collapse runs, truncate to 20 chars, fallback `untitled`), then run:

  ```bash
  FEATURE_BRANCH=$(bash ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/prepare-feature-branch.sh "${FEATURE_SLUG}")
  ```

  The script is idempotent on `feat/${FEATURE_SLUG}`, creates it from a trunk branch, exits 1 on unrelated dirty tree, and exits 2 on a different feature branch (re-run with `--allow-existing-feature-branch` after user confirmation) or, when `RELEASING.md` exists, on `release/*` (re-run with `--allow-release-branch` only for a release-only fix). See `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/branch-prep.md`. **Do not skip this step** — it is what prevents implementor agents from committing to `main`.

Then process batches sequentially. Within each batch, dispatch one `ycc:implementor` agent per step in a SINGLE message with MULTIPLE `Task` tool calls (standalone dispatch — see `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md`). Between batches, run the project's type-check and unit-test commands. On failure, stop and ask the user how to proceed.

This keeps everything in the current conversation — no file artifact needed.

For unattended loop-to-completion of a parallel plan, hand off to `/ycc:implement-plan` and pair it with the `/goal` session directive — see that skill's `## /goal pairing` section for the recommended done condition (`ALL_BATCHES_DONE`, `FILES_CHANGED_NONEMPTY`, `LINT_PASS`) and the transcript-output contract.

**Option 2 — Save to file and hand off (rigorous)**

Write the plan to `docs/prps/plans/{name}.plan.md` (adapting it to the PRP plan template if needed: add `Patterns to Mirror`, `Files to Change`, `Validation Commands`, etc.), then run `/ycc:prp-implement --parallel docs/prps/plans/{name}.plan.md` for the full 5-level validation pipeline.

Use Option 1 for small features and quick iterations. Use Option 2 when the user wants an implementation report, per-task validation logs, and the plan archived for audit.

---

## Comparison with other ycc planning tracks

| Track                  | When to use                                                                                                                                                                                                                                                               |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/ycc:plan` (this one) | Quick conversational plan via `ycc:planner` agent. No artifact file. Add `--parallel` to shape the output for parallel execution (no research fan-out). Add `--enhanced` to widen to 5 personas (security + UX), dispatched as standalone parallel sub-agents by default. |
| `/ycc:prp-plan`        | Artifact-producing plan with codebase pattern extraction. Single-pass. Add `--parallel` for 3-researcher fan-out + batched plan. Add `--enhanced` for the full 7-researcher fan-out.                                                                                      |
| `/ycc:prp-prd`         | Interactive PRD first, then prp-plan. Problem-first hypothesis workflow.                                                                                                                                                                                                  |
| `/ycc:plan-workflow`   | Heavyweight parallel-agent planning. Multi-task features. Artifact output.                                                                                                                                                                                                |
| `/ycc:parallel-plan`   | Lower-level component of `/ycc:plan-workflow` for dependency-aware plans.                                                                                                                                                                                                 |

### Which `--parallel` should I use?

- **`/ycc:plan --parallel`** — You want a quick parallel-capable plan without creating an artifact file. Planner does its own research. Best for small/medium features.
- **`/ycc:prp-plan --parallel`** — You want research fan-out (3 parallel researchers covering 8 categories) plus a full artifact file with patterns to mirror and validation commands. Best for medium/large features where you want a rigorous, auditable plan.
- **`/ycc:plan-workflow`** — You want heavyweight team orchestration with shared context and multi-phase validation. Best for very large features spanning many tasks.

### When to use `--team`

`--team` is a **Claude Code-only** execution mode. Cursor and Codex bundles ship
without the team tools (`TeamCreate`, `SendMessage`, etc.), so invoking `--team`
there has no effect — use `--parallel` instead.

- **`/ycc:plan --team`** — The task is complex enough that you want architect, risk, and testing perspectives but not heavy enough for an artifact file. Outputs a merged multi-perspective plan in the conversation.
- **`/ycc:plan --parallel --team`** — Same as above, but the merged plan is also formatted for parallel implementation (Batches section, `Depends on` annotations).
- **`/ycc:prp-plan --team`** — Team-coordinated research with shared TaskList for medium/large features that will produce an artifact file.
- **`/ycc:prp-implement --team`** — Team-coordinated execution with shared TaskList across all batches. Best for implementation runs where you want coordinated inter-batch shutdown and a single shared task graph.

### When to use `--enhanced`

`--enhanced` widens the roster from 3 to **5** personas, adding `security-reviewer` and `ux-reviewer`. By default (no `--team`) it dispatches via **Path C** — 5 standalone parallel sub-agents — which works in every bundle (Claude Code, Cursor, Codex). Combine with `--team` (Claude Code only) for team-coordinated dispatch via **Path B enhanced**. Reach for `--enhanced` when the change has plausible security exposure (new endpoint, new input source, authn/authz touch, secret handling) or user-facing surface (new UI / CLI flag / API response shape / error path). Skip it for purely internal refactors where no new threat surface or user touchpoint is introduced.

- **`/ycc:plan --enhanced <request>`** — Fans out 5 standalone parallel sub-agents (Path C). Works in every bundle. Best for medium-complexity features where a 3-persona plan would miss security or UX considerations and you don't need the team coordination overhead.
- **`/ycc:plan --enhanced --team <request>`** — Same 5-persona roster but dispatched as a Claude Code agent team with shared `TaskList` and coordinated shutdown. Use when you want team observability across the 5 perspectives.
- **`/ycc:plan --enhanced --parallel <request>`** — 5-persona plan formatted for parallel execution (Batches section, `Depends on` annotations).
- **`/ycc:plan --enhanced --dry-run <request>`** — Print the 5-persona roster without spawning anyone. Useful to confirm the team shape before paying the dispatch cost.
- **`/ycc:prp-plan --enhanced <request>`** — The heavier sibling: 7 researchers, artifact-producing. Use when you want the enhanced perspectives _and_ a saved plan file, not just an in-conversation plan.

### When to use `--no-worktree`

Worktree annotations are emitted by default. Pass `--no-worktree` to suppress the `## Worktree Setup` section and all per-task `**Worktree**:` annotations when you do not intend to use git worktree isolation:

- **`/ycc:plan --parallel <request>`** — Parallel-capable plan with full worktree annotations (default). Hand off to `/ycc:prp-implement` for isolated execution.
- **`/ycc:plan --no-worktree --parallel <request>`** — Parallel-capable plan without worktree annotations. Use when worktree isolation is not desired.
- **`/ycc:plan --parallel --team <request>`** — Multi-perspective plan formatted for both parallel execution and worktree isolation (default).
- **`/ycc:plan --no-worktree --parallel --team <request>`** — Multi-perspective plan with parallel execution but no worktree annotations.
