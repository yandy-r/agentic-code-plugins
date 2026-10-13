---
name: plan-workflow
description: 'Researches, analyzes, and validates feature plans with checkpoints. Use when running research-to-plan workflow, producing shared.md and parallel-plan.md, or reviewing research before planning.'
argument-hint: '[--team] [--research-only] [--plan-only] [--no-checkpoint] [--optimized] [--dry-run] [--no-worktree] [--visual] [feature-name]'
allowed-tools:
  - Read
  - Grep
  - Glob
  - Write
  - Task
  - Agent
  - TeamCreate
  - TeamDelete
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - SendMessage
  - AskUserQuestion
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(test:*)
  - Bash(mkdir:*)
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/*.sh:*)'
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/*.sh:*)'
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/**/*.sh:*)'
---

# Unified Planning Workflow

Single command to research, analyze, and plan feature implementation. Default dispatch is standalone parallel sub-agents via the `Task` tool; pass `--team` (Claude Code only) to run each stage as teammates under a shared `TeamCreate`/`TaskList` with coordinated shutdown and inter-teammate `SendMessage` coordination. This skill combines the functionality of `shared-context` and `parallel-plan` with optimizations and checkpoint support.

## Workflow Overview

```
+--------------------------------------------------------------+
|                    /plan-workflow feature                     |
+--------------------------------------------------------------+
|                                                               |
|  +-----------+   +----------+   +---------------------+      |
|  | Research  |-->|Checkpoint|-->| Planning + Validate |      |
|  | Team      |   | (Review) |   | Team                |      |
|  +-----------+   +----------+   +---------------------+      |
|       |                                     |                 |
|   shared.md                         parallel-plan.md         |
|                                                               |
+--------------------------------------------------------------+
```

## Arguments

**Target**: `$ARGUMENTS`

Parse arguments (flags first, then the feature name):

- **--team**: Optional. (Claude Code only) Deploy research, analysis, and validation stages as teammates under a shared `TeamCreate`/`TaskList` with coordinated shutdown. Default is standalone parallel sub-agents via the `Task` tool. Cursor and Codex bundles lack team tools — do not pass `--team` there.
- **--research-only**: Stop after research phase (creates shared.md only)
- **--plan-only**: Skip research, use existing shared.md
- **--no-checkpoint**: No pause between research and planning
- **--optimized**: Use 7-agent optimized deployment (default: 10-agent standard)
- **--dry-run**: Show execution plan without running. With `--team`, also prints the team name and teammate roster.
- **--worktree**: Optional. (legacy — now default; safe to omit) Worktree annotations are emitted in the generated `parallel-plan.md` by default. Accepted as a silent no-op so existing pipelines continue to work.
- **--no-worktree**: Optional. Opt out of worktree annotations in the generated `parallel-plan.md`. No effect when `--research-only` is passed (no plan file is generated). Honored with `--plan-only`.
- **--visual**: Render the finished plan as an Agent-Native visual artifact (MDX) via `ycc:visual-plan`; local-files by default, hosted link requires `--share`.
- **feature-name**: Required. Directory name in `${PLANS_DIR}/`

If no feature name provided, abort with usage instructions:

```
Usage: /plan-workflow [--team] [options] [--visual] [feature-name]

Options:
  --team            (Claude Code only) Dispatch stages as agent team (default: standalone sub-agents)
  --research-only   Stop after research phase (creates shared.md only)
  --plan-only       Skip research, use existing shared.md
  --no-checkpoint   No pause between research and planning (default: checkpoint enabled)
  --optimized       Use 7-agent optimized deployment (default: 10-agent standard)
  --dry-run         Show execution plan without running
  --worktree        (legacy — now default; safe to omit) Worktree annotations emitted by default
  --no-worktree     Opt out of worktree annotations in the generated parallel-plan.md
  --visual          Render the finished plan as a visual artifact via ycc:visual-plan (local-files by default; hosted link requires --share)

Examples:
  /plan-workflow user-authentication
  /plan-workflow payment-integration --no-checkpoint
  /plan-workflow api-refactor --research-only
  /plan-workflow user-auth --plan-only
  /plan-workflow --team new-feature --optimized
  /plan-workflow --team --dry-run new-feature
  /plan-workflow add-billing-dashboard                 # worktree annotations included by default
  /plan-workflow --no-worktree add-billing-dashboard   # skip worktree annotations
  /plan-workflow --visual add-billing-dashboard        # render the finished plan as a visual artifact
```

---

## Visual mode

See `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/visual-mode.md` for the canonical `--visual` contract shared by all planning skills.

`--visual` is a **terminal decorator step**, not a dispatch mode. It is orthogonal to and composes with `--team`, `--optimized`, and `--no-worktree`, and runs once at the very end.

When `VISUAL_MODE=true` and `--dry-run` is **not** set, after the final phase (the plan has been written and validated) the workflow invokes:

```
ycc:visual-plan <absolute-plan-path>
```

where `<absolute-plan-path>` is the **actual written plan path** — the feature-dir plan at `${feature_dir}/parallel-plan.md` resolved in Phase 0 — **not** a hardcoded `docs/prps/plans` path. `ycc:visual-plan` derives its `visual/` output directory relative to that plan path.

When `--dry-run` is set, `--visual` is **short-circuited**: print `visual generation would run` and do not invoke `ycc:visual-plan`. `--research-only` produces no plan file, so `--visual` has nothing to render and does not run.

---

## Phase 0: Initialize

### Step 1: Parse Arguments

Extract from `$ARGUMENTS`:

1. **--team**: Boolean flag. Set `AGENT_TEAM_MODE=true` if present, else `false`.
2. **--research-only / --plan-only / --no-checkpoint / --optimized / --dry-run**: Boolean flags. Set each corresponding variable if present.
3. **--no-worktree / --worktree**: Default `WORKTREE_MODE=true`. Set `WORKTREE_MODE=false` if `--no-worktree` is present. `--worktree` is accepted as a legacy no-op (matches the default). Has no effect when `--research-only` is set (no plan file is generated). Honored with `--plan-only`.

```bash
# Default ON; pass --no-worktree to opt out. --worktree accepted as legacy no-op.
WORKTREE_MODE=true
case " $ARGUMENTS " in
  *" --no-worktree "*) WORKTREE_MODE=false ;;
esac
ARGUMENTS="${ARGUMENTS//--no-worktree/}"
ARGUMENTS="${ARGUMENTS//--worktree/}"  # legacy no-op

VISUAL_MODE=false
case " $ARGUMENTS " in
  *" --visual "*) VISUAL_MODE=true ;;
esac
ARGUMENTS="${ARGUMENTS//--visual/}"
```

4. **--visual**: Boolean flag. Set `VISUAL_MODE=true` if present, else `false`. Terminal decorator — see [## Visual mode](#visual-mode).
5. **feature-name**: First non-flag argument (required).

**Mutual exclusion (abort before any write)**: If both `--research-only` and `--plan-only` are present, print a usage error and **STOP** — no directory creation, no file writes:

```
Error: --research-only and --plan-only are mutually exclusive
Usage: /plan-workflow [--team] [--research-only | --plan-only] [--no-checkpoint] [--optimized] [--dry-run] [--no-worktree] [--visual] [feature-name]
```

Validate the feature name:

- Must be provided
- Should use kebab-case (lowercase with hyphens)
- No special characters except hyphens

**Compatibility note**: When this skill is invoked from a Cursor or Codex bundle, `--team` must not be used (those bundles ship without team tools).

**Team opt-in note**: If `--team` is passed and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is not set to `1` in the environment, abort with: `--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Omit --team for standalone dispatch, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Claude Code settings if you intentionally want agent-team dispatch.`

### Step 2: Resolve Plans Directory

Use the shared resolver to determine the correct plans directory:

```bash
source ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/resolve-plans-dir.sh
feature_dir="$(get_feature_plan_dir "[feature-name]")"
```

This handles monorepo detection, `.plans-config` files, and git root resolution automatically.

### Step 3: Run State Detection

Run the state detection script:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/check-state.sh [feature-name]
```

This script reports:

- Whether `${feature_dir}/` exists
- Whether `shared.md` exists
- Whether `parallel-plan.md` exists
- Any existing research files

### Step 4: Determine Execution Mode

Based on flags and detected state:

| State                | --plan-only | --research-only | Action                                                                                              |
| -------------------- | ----------- | --------------- | --------------------------------------------------------------------------------------------------- |
| No shared.md         | No          | No              | Full workflow from Phase 1                                                                          |
| No shared.md         | No          | Yes             | Full workflow from Phase 1, stop at Step 15A (research-only stop)                                   |
| No shared.md         | Yes         | No              | Fail fast in Step 4B — never fall back to research                                                  |
| Has shared.md        | Yes         | No              | Skip to Phase 5 (Analysis)                                                                          |
| Has shared.md        | No          | Yes             | Regenerate only if overwrite chosen in Step 4C, then stop at Step 15A; else STOP and reuse existing |
| Has shared.md        | No          | No              | Full workflow from Phase 1 (shared.md regenerates only if overwrite chosen in Step 4C)              |
| Has parallel-plan.md | Any         | Any             | Warn about overwrite (Step 4C)                                                                      |

**Note**: "Planning" in this workflow = Phase 8 (Plan Generation). "Analysis" = Phase 5.
The `--plan-only` flag skips Research + Checkpoint (Phases 1-4) but NOT Analysis (Phase 5).

### Step 4A: Dry-Run Preview (when `--dry-run`, before anything else)

If `--dry-run` is present, handle it FIRST — before the prereq gate, before the
overwrite prompt, before any `mkdir`, write, agent dispatch, or rendering. Read and
display the dry-run template:

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/checkpoint-messages.md
```

Display the "Dry Run" section with values substituted, then **STOP**. Dry run writes
nothing, dispatches no agents (`Task`/`Agent`/`TeamCreate`), renders nothing, and never
prompts. If `--plan-only` is also set and `check-state.sh` shows no `shared.md`, state
in the preview that a real run would fail fast at Step 4B (missing prerequisite —
see the fail-fast message there) and STOP.

### Step 4B: Plan-Only Prerequisite Gate (when `--plan-only`, before any write)

If `PLAN_ONLY=true` (and `--dry-run` is **not** set — dry run never reaches here), run
the prerequisite check **before any `mkdir` or file write**:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/check-prerequisites.sh "[feature-name]"
```

- **Exit 0** → proceed (overwrite choice, then directory creation).
- **Non-zero** → print the script's output, then print:
  `run /ycc:shared-context <feature> or /ycc:plan-workflow <feature> --research-only first`, and **STOP**. Never fall back to running research inline under `--plan-only`.

**`--optimized --plan-only` restriction** (documented gate, smallest safe behavior):
`--optimized --plan-only` requires the five unified analysis files above to already
exist (from a prior `--optimized` full run); there is no standard-mode Phase 5 to
regenerate them. After `check-prerequisites.sh` passes, verify the five unified files
exist **before any write or dispatch**. If any is missing, STOP and tell the user:
`--optimized --plan-only needs a prior --optimized full run. Run /ycc:plan-workflow <feature> --optimized first.` See also Phase 7 PRE-CHECK.

### Step 4C: Overwrite Choice (when shared.md or parallel-plan.md exists)

If `check-state.sh` reported an existing `shared.md` (full mode or `--research-only`) or `parallel-plan.md`:

- **Interactive (checkpoint enabled)**: surface the matching warning from `templates/checkpoint-messages.md` ("Existing State Warnings") and let the user choose regenerate vs reuse/stop.
- **Non-interactive (`--no-checkpoint`, including both thin aliases which force it)**: default is **regenerate (overwrite)** so pipelines stay non-blocking. State the choice when proceeding (e.g. "shared.md exists — regenerating (non-interactive default)").
- **Research-only reuse**: report the existing `shared.md` path, state that no files were changed, print `/ycc:parallel-plan <feature>` as the next step, and **STOP** without dispatching agents.

### Step 5: Create Directory

Only reached when `--dry-run` is **not** set. If `${feature_dir}/` doesn't exist:

```bash
mkdir -p "${feature_dir}"
```

---

## Phase 1: Research Stage (unless --plan-only)

### Step 7: Team Setup (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step entirely — the default path dispatches standalone sub-agents in Step 10.

If `AGENT_TEAM_MODE=true`, follow the universal lifecycle contract at
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`.

Create an agent team for the entire workflow:

```
TeamCreate: team_name="pw-[feature-name]", description="Planning workflow team for [feature-name]"
```

On failure, abort the skill with the `TeamCreate` error message. Do NOT silently fall back to sub-agent mode.

### Step 8: Read Research Prompts

Read the research prompts template:

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/research-agents.md
```

### Step 9: Create Research Tasks (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step entirely — standalone `Task` dispatch does not use the shared task list.

If `AGENT_TEAM_MODE=true`, create 4 tasks in the shared task list:

1. **"Research architecture for [feature-name]"**
2. **"Research patterns for [feature-name]"**
3. **"Research integrations for [feature-name]"**
4. **"Research documentation for [feature-name]"**

If `TaskCreate` fails for any task, call `TeamDelete` and abort.

### Step 10: Spawn Research Agents

| Name / Teammate `name`    | Subagent Type               | Output File                | Model  | Focus                                    |
| ------------------------- | --------------------------- | -------------------------- | ------ | ---------------------------------------- |
| `architecture-researcher` | `codebase-research-analyst` | `research-architecture.md` | sonnet | System structure, components, data flow  |
| `patterns-researcher`     | `codebase-research-analyst` | `research-patterns.md`     | sonnet | Existing patterns, conventions, examples |
| `integration-researcher`  | `codebase-research-analyst` | `research-integration.md`  | sonnet | APIs, databases, external systems        |
| `docs-researcher`         | `codebase-research-analyst` | `research-docs.md`         | sonnet | Relevant documentation files             |

**Model Assignment**: Pass `model: "sonnet"` for all research agents.

Each agent writes findings to `${feature_dir}/[output-file]`.

Use the prompts from `research-agents.md` with variables substituted:

- `{{FEATURE_NAME}}` - The feature directory name
- `{{FEATURE_DIR}}` - Full output directory path (`${feature_dir}`, resolved in Step 2)

#### Path A — Standalone sub-agents (`AGENT_TEAM_MODE=false`, default)

**CRITICAL**: Deploy all 4 research agents in a **SINGLE message** with **MULTIPLE `Task` tool calls**. No `team_name` — standalone dispatch. Each `Task` call uses the `subagent_type` and `model` from the table above and the corresponding prompt from `research-agents.md`.

In this mode there is no shared task list; rely on each `Task`'s return value plus the artifact check in Step 11 to confirm completion. Inter-agent `SendMessage` coordination is not available — each sub-agent works independently from the prompt alone.

#### Path B — Agent team (`AGENT_TEAM_MODE=true`)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path B you MUST follow the agent-team lifecycle at
> `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`.
> Do NOT mix standalone `Task` calls with team dispatch.

All 4 `TaskCreate` entries were registered up front in Step 9 — do not re-create them here.

Spawn all 4 teammates in **ONE message** with **FOUR `Agent` tool calls**. Every call MUST include:

- `team_name = "pw-[feature-name]"`
- `name = "<teammate-name>"` (from the table above — must match the `TaskCreate` subject prefix)
- `subagent_type` and `model` from the table above
- The researcher-specific prompt from `research-agents.md`

After spawning, use `TaskList` to confirm all 4 tasks are `completed` before proceeding to Step 11.

---

## Phase 2: Validate Research Artifacts

### Step 11: Validate Research Artifacts

After all research agents complete, validate all research files:

- **Path A (standalone, default)**: rely on `Task` return values; each sub-agent writes its `research-*.md` (or, in `--optimized`, `analysis-*.md`) artifact before returning.
- **Path B (`--team`)**: check via `TaskList` that all 4 research tasks are `completed`.

Then run:

```bash
# Standard mode (4-file research-*.md set):
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-research-artifacts.sh "${feature_dir}"

# Optimized mode (5-file unified analysis-*.md set):
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-research-artifacts.sh "${feature_dir}" --optimized
```

If `--optimized` was passed, you MUST append `--optimized` to this validator. The validator's default file set (`research-*.md`) does not exist in optimized mode.

If validation fails: in Path B, message the relevant teammate to fix their output; in Path A, re-dispatch the failing sub-agent via `Task`. Wait for correction, rerun validation until pass. Do NOT have the orchestrator write the missing file itself from a captured agent summary — that bypasses the contract and produces fragile output.

**Do not proceed to shared.md synthesis until validation passes.**

### Step 12: Shut Down Research Teammates (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step — standalone sub-agents return on their own.

Otherwise, send shutdown requests to all research teammates:

```
SendMessage to each teammate: message={type: "shutdown_request"}
```

---

## Phase 3: Consolidate Research

### Step 13: Read Research Results

After verifying all files exist (Step 11 passed), read the input set for the active mode before synthesizing `shared.md`:

**Standard mode (4 research files)**:

1. `${feature_dir}/research-architecture.md`
2. `${feature_dir}/research-patterns.md`
3. `${feature_dir}/research-integration.md`
4. `${feature_dir}/research-docs.md`

**Optimized mode (5 unified analysis files — no `research-*.md` exist)**:

1. `${feature_dir}/analysis-architecture.md`
2. `${feature_dir}/analysis-patterns.md`
3. `${feature_dir}/analysis-integration.md`
4. `${feature_dir}/analysis-docs.md`
5. `${feature_dir}/analysis-tasks.md`

### Step 14: Generate shared.md

Read the shared structure template:

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/shared-structure.md
```

Create `${feature_dir}/shared.md` following the template exactly.

### Step 15: Validate shared.md

Run the validation script:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-shared.sh "${feature_dir}/shared.md"
```

Fix any errors before proceeding.

### Step 15A: Research-Only Stop (if `--research-only`)

If `RESEARCH_ONLY=true`, **STOP here** once `shared.md` exists and `validate-shared.sh` passed. Skip Phases 4–9.5 entirely (checkpoint, analysis, planning, validation, visual).

1. If `AGENT_TEAM_MODE=true`, shut down any remaining teammates and call `TeamDelete` (same cleanup as Step 33). Standalone mode has no team.
2. Print the research-only summary: use "Research Complete Summary" from `templates/checkpoint-messages.md` (standard or optimized variant), listing the artifacts this run actually created — standard: `research-*.md` (4) + `shared.md`; `--optimized`: the five unified `analysis-*.md` files (`analysis-architecture.md`, `analysis-patterns.md`, `analysis-integration.md`, `analysis-docs.md`, `analysis-tasks.md`) + `shared.md` — plus dispatch mode.
3. Next step line: `/ycc:parallel-plan <feature>` or `/ycc:plan-workflow <feature> --plan-only`.
4. **STOP** — do not write or dispatch anything further.

---

## Phase 4: Checkpoint (unless --no-checkpoint or --research-only)

### Step 16: Pause for User Review

If checkpoint is enabled, use **AskUserQuestion** with these options:

**Question**: "Research complete for [feature-name]. Review the shared context before planning?"

**Options**:

1. **Continue to planning** - Proceed to Phase 5
2. **Review shared.md first** - Display shared.md contents, then re-prompt
3. **Stop here** - End workflow, user will continue manually

Read checkpoint message format from:

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/checkpoint-messages.md
```

If user chooses "Review shared.md first":

- Read and display `${feature_dir}/shared.md`
- Re-prompt with same question

If user chooses "Stop here":

- If `AGENT_TEAM_MODE=true`, clean up team (`TeamDelete`). In standalone mode there is no team to tear down.
- Display completion summary for research phase only
- **STOP** - do not proceed to planning

---

## Phase 5: Analysis Stage (unless --research-only or --optimized)

> **MANDATORY**: This phase MUST run in standard mode, including when `--plan-only` is used.
> The `--plan-only` flag skips Research (Phases 1-4), NOT Analysis. Analysis agents produce
> the `analysis-*.md` files required by Phase 8 (Plan Generation).

### Step 17: Create Team (if `--team` and --plan-only)

If `AGENT_TEAM_MODE=false`, skip this step entirely — standalone mode has no team.

If `AGENT_TEAM_MODE=true` and `--plan-only` was used (team doesn't exist yet):

```
TeamCreate: team_name="pw-[feature-name]", description="Planning workflow team for [feature-name]"
```

### Step 18: Read Analysis Prompts

In standard mode (not --optimized), read analysis prompts:

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/planning-agents.md
```

### Step 19: Create Analysis Tasks (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step entirely — standalone `Task` dispatch does not use the shared task list.

If `AGENT_TEAM_MODE=true`, create 3 analysis tasks in the shared task list:

1. **"Synthesize planning context for [feature-name]"**
2. **"Analyze code patterns for [feature-name]"**
3. **"Suggest task structure for [feature-name]"**

### Step 20: Spawn Analysis Agents

| Name / Teammate `name` | Subagent Type               | Output File           | Model  | Focus                  |
| ---------------------- | --------------------------- | --------------------- | ------ | ---------------------- |
| `context-synthesizer`  | `codebase-research-analyst` | `analysis-context.md` | sonnet | Condense planning docs |
| `code-analyzer`        | `codebase-research-analyst` | `analysis-code.md`    | sonnet | Extract code patterns  |
| `task-structurer`      | `codebase-research-analyst` | `analysis-tasks.md`   | sonnet | Suggest task breakdown |

**Model Assignment**: Pass `model: "sonnet"` for all analysis agents.

Each agent writes to `${feature_dir}/[output-file]`.

Use the prompts from `planning-agents.md` with variables substituted:

- `{{FEATURE_NAME}}` - The feature directory name
- `{{FEATURE_DIR}}` - Full output directory path (`${feature_dir}`, resolved in Step 2)

#### Path A — Standalone sub-agents (`AGENT_TEAM_MODE=false`, default)

**CRITICAL**: Deploy all 3 analysis agents in a **SINGLE message** with **MULTIPLE `Task` tool calls**. No `team_name`. Each `Task` call uses the `subagent_type` and `model` from the table above and the corresponding prompt from `planning-agents.md`.

#### Path B — Agent team (`AGENT_TEAM_MODE=true`)

Spawn all 3 teammates in **ONE message** with **THREE `Agent` tool calls**, each with `team_name="pw-[feature-name]"` and the matching `name=` from the table above. The 3 analysis tasks registered in Step 19 are used here. After spawning, use `TaskList` to confirm all 3 tasks are `completed`.

---

## Phase 6: Validate and Persist Analysis Artifacts

### Step 21: First Validation Check

After analysis agents complete, validate all analysis files:

- **Path A (standalone, default)**: rely on `Task` return values; each sub-agent writes its `analysis-*.md` artifact before returning.
- **Path B (`--team`)**: check via `TaskList` that all 3 (standard) or 5 (optimized) analysis tasks are `completed`.

Then run:

```bash
# Standard mode (3-file set: analysis-context, analysis-code, analysis-tasks):
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-analysis-artifacts.sh "${feature_dir}"

# Optimized mode (5-file unified set):
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-analysis-artifacts.sh "${feature_dir}" --optimized
```

If `--optimized` was passed, you MUST append `--optimized` to this validator.

If validation passes → skip to Step 22 (Pre-Generation Gate).
If validation fails → in Path B, message the relevant teammate; in Path A, re-dispatch the failing sub-agent via `Task`. Wait, re-validate. Do NOT have the orchestrator write the missing file itself.

### Step 22: Pre-Generation Gate (MANDATORY — cannot be skipped)

Run the pre-generation gate script:

```bash
# Standard mode:
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/persist-or-fail.sh "${feature_dir}"

# Optimized mode:
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/persist-or-fail.sh "${feature_dir}" --optimized
```

If `--optimized` was passed, you MUST append `--optimized` to the gate script. Without the flag, the gate looks for the standard 3-file set and will incorrectly fail in optimized mode.

- **Exit 0** → proceed to Phase 7
- **Exit 1** → the script prints `MISSING_FILES` and `ACTION_REQUIRED`. Re-dispatch the failing teammate (Path B) or sub-agent (Path A) to write the missing file(s), then re-run this gate until it passes (exit 0).

**Do NOT proceed to plan generation until `persist-or-fail.sh` exits 0. Do NOT have the orchestrator ad-hoc write the missing files from captured agent summaries — that bypasses the contract and was the root cause of the May 2026 reproducer where 3 of 5 unified-analyst files were missing on disk.**

### Step 23: Shut Down Analysis Teammates (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step — standalone sub-agents return on their own.

Otherwise, send shutdown requests to all analysis teammates.

---

## Phase 7: Read Analysis Results

> **PRE-CHECK — branch on execution mode**:
>
> - **Standard**: if `analysis-context.md`, `analysis-code.md`, or `analysis-tasks.md` do not exist in `${feature_dir}/`, Phase 5 was skipped in error. Go back and run Phase 5 now.
> - **Optimized**: the five unified files below must exist (produced by Phase 1 unified agents, gated by Step 22). If any is missing, STOP and tell the user: `--optimized --plan-only needs a prior --optimized full run. Run /ycc:plan-workflow <feature> --optimized first.` Optimized mode has no Phase 5 to regenerate them.

### Step 24: Read Analysis Results

After verifying all files exist, read the file set for the active mode:

**Standard mode (3 files)**:

1. `${feature_dir}/analysis-context.md`
2. `${feature_dir}/analysis-code.md`
3. `${feature_dir}/analysis-tasks.md`

**Optimized mode (5 unified files)**:

1. `${feature_dir}/analysis-architecture.md`
2. `${feature_dir}/analysis-patterns.md`
3. `${feature_dir}/analysis-integration.md`
4. `${feature_dir}/analysis-docs.md`
5. `${feature_dir}/analysis-tasks.md`

---

## Phase 8: Plan Generation

### Step 25: Read Plan Template

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/plan-structure.md
```

### Step 26: Generate parallel-plan.md

Create `${feature_dir}/parallel-plan.md` following the template exactly.

Required sections:

- Title & Overview (3-4 information-dense sentences)
- Critically Relevant Files and Documentation
- Implementation Plan with Phases and Tasks
- Advice section

**Worktree annotations** (default — `WORKTREE_MODE=true`; skipped when `--no-worktree`): insert a `## Worktree Setup` section immediately after the title/overview and before the first batch. When `WORKTREE_MODE=false`, omit all worktree annotations. Use
`<feature-slug>` = the sanitized feature name (same as `${feature_dir}` basename).
Format exactly as defined in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/worktree-strategy.md` §2:

```markdown
## Worktree Setup

- **Parent**: <repo-root>/.claude/worktrees/<repo>-<feature-slug>/ (branch: feat/<feature-slug>)
```

All tasks — parallel and sequential — share this single feature worktree. Do **not**
add a `**Children**:` list. Do **not** add per-task `**Worktree**:` lines.

> **Plan-file handoff**: leave `parallel-plan.md` and `shared.md` in `docs/plans/<feature-slug>/` (main checkout). The implementor (`ycc:implement-plan` / `ycc:prp-implement`) will **move** them into the feature worktree once created — never copied or synced. See `worktree-strategy.md` §7.

**Plan-generation agent prompt** (both standalone Path A and `--team` Path B): by default (`WORKTREE_MODE=true`), append the following directive to the plan-generation prompt. Omit when `--no-worktree` was passed (`WORKTREE_MODE=false`):

> WORKTREE MODE: Annotate the generated `parallel-plan.md` with a single
> `## Worktree Setup` section (containing only the `**Parent**:` line) placed
> before the first batch, following
> `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/worktree-strategy.md` §2.
> All tasks — parallel and sequential — share this one feature worktree path.
> Do NOT add a `**Children**:` list. Do NOT add per-task `**Worktree**:` lines.

In the `--team` Path B additionally cross-reference
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md` §7 for
shared-worktree team dispatch: all parallel teammates operate against the same
feature worktree path, not separate per-task paths.

### Step 27: Plan Structure Check (deferred)

Structural validation (`validate-workflow-plan.sh`) runs **once**, on the final artifact, in Step 31A — after validation-agent fixes. Do not run it against the pre-validation draft.

---

## Phase 9: Validation Stage

### Step 28: Read Validation Prompts

```bash
cat ${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/templates/validation-agents.md
```

### Step 29: Create Validation Tasks (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step entirely — standalone `Task` dispatch does not use the shared task list.

If `AGENT_TEAM_MODE=true`:

**Standard Mode**: Create 3 validation tasks:

1. **"Validate file paths in [feature-name] plan"**
2. **"Validate dependency graph in [feature-name] plan"**
3. **"Validate task completeness in [feature-name] plan"**

**Optimized Mode**: Create 2 validation tasks:

1. **"Validate paths and dependencies in [feature-name] plan"**
2. **"Validate task completeness in [feature-name] plan"**

### Step 30: Spawn Validation Agents

**Standard Mode**: 3 agents:

| Name / Teammate `name`   | Subagent Type               | Model  | Focus                                   |
| ------------------------ | --------------------------- | ------ | --------------------------------------- |
| `path-validator`         | `explore`                   | haiku  | Verify all referenced files exist       |
| `dependency-validator`   | `explore`                   | haiku  | Check for circular/invalid dependencies |
| `completeness-validator` | `codebase-research-analyst` | sonnet | Ensure tasks are actionable             |

**Optimized Mode**: 2 agents:

| Name / Teammate `name`   | Subagent Type               | Model  | Focus                           |
| ------------------------ | --------------------------- | ------ | ------------------------------- |
| `path-dep-validator`     | `explore`                   | haiku  | Verify paths + dependency graph |
| `completeness-validator` | `codebase-research-analyst` | sonnet | Task quality + completeness     |

**Model Assignment**: Pass `model: "haiku"` for path/dependency validators, `model: "sonnet"` for completeness-validator.

#### Path A — Standalone sub-agents (`AGENT_TEAM_MODE=false`, default)

**CRITICAL**: Deploy all validation agents (3 in standard, 2 in optimized) in a **SINGLE message** with **MULTIPLE `Task` tool calls**. No `team_name`. Each `Task` call uses the `subagent_type` and `model` from the relevant table above and the corresponding prompt from `validation-agents.md`. Rely on each `Task`'s return value for validator findings.

#### Path B — Agent team (`AGENT_TEAM_MODE=true`)

Spawn all validation teammates in **ONE message** with matching `Agent` tool calls, each with `team_name="pw-[feature-name]"` and the matching `name=` from the table above. The validation tasks registered in Step 29 are used here. After spawning, use `TaskList` to confirm all tasks are `completed`.

### Step 31: Review and Fix Issues

After validators complete:

- **Path A (standalone, default)**: review each `Task` return value for validator findings.
- **Path B (`--team`)**: review findings via `TaskList` and teammate messages.
- Fix any issues identified:
  - Correct invalid file paths
  - Resolve circular dependencies
  - Add missing details to incomplete tasks

### Step 31A: Validate Final Plan Structure

After all fixes, run once on the final artifact (before visual/completion):

```bash
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-workflow-plan.sh "${feature_dir}/parallel-plan.md"
```

Fix any structural errors it reports (missing `### Phase` is an error); do not proceed until it exits 0.

### Step 32: Shut Down Validation Teammates (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step — standalone sub-agents return on their own.

Otherwise, send shutdown requests to all validation teammates.

---

## Phase 9.5: Visual Mode (if --visual)

If `VISUAL_MODE=false`, skip this phase entirely.

This step runs only after the plan has been written (Phase 8) and validated (Phases 8–9). It never re-orders, re-runs, or substitutes for any earlier phase. See `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/visual-mode.md`.

### Step 32.5: Render Visual Artifact

- If `--dry-run` is set, print `visual generation would run` and **STOP** this phase (the §2.1 short-circuit — no visual artifacts are produced).
- If `--research-only` was used, no plan file was generated; skip this phase.
- Otherwise, invoke `ycc:visual-plan` on the **actual written plan path** (the feature-dir plan resolved in Phase 0, not a hardcoded `docs/prps/plans` path):

```
ycc:visual-plan "${feature_dir}/parallel-plan.md"
```

`ycc:visual-plan` derives its `visual/` output directory relative to the supplied plan path and prints the resulting link (hosted URL, localhost preview, or `local files only`). Surface that link in the Phase 10 summary; do not re-derive the path yourself, and do not edit the plan file.

---

## Phase 10: Summary

### Step 33: Clean Up Team (if `--team`)

If `AGENT_TEAM_MODE=false`, skip this step — there is no team to tear down.

Otherwise, delete the team and its resources:

```
TeamDelete
```

### Step 34: Display Completion Summary

Skipped entirely when `RESEARCH_ONLY=true` (workflow ended at Step 15A with the research-only summary) or when the user stopped at the checkpoint. Otherwise provide a comprehensive summary — list only files this run actually created (`--plan-only`: omit Research Phase files; `--research-only` never reaches here):

```markdown
# Plan Workflow Complete

## Feature

[feature-name]

## Files Created

### Research Phase

Standard: the four `research-*.md` files below. Optimized: omit them and list the five unified `analysis-*.md` files under Analysis Phase instead.

- ${feature_dir}/research-architecture.md
- ${feature_dir}/research-patterns.md
- ${feature_dir}/research-integration.md
- ${feature_dir}/research-docs.md
- ${feature_dir}/shared.md

### Analysis Phase

Standard: three files. Optimized: five unified files.

- ${feature_dir}/analysis-context.md
- ${feature_dir}/analysis-code.md
- ${feature_dir}/analysis-tasks.md

Optimized set: `analysis-architecture.md`, `analysis-patterns.md`, `analysis-integration.md`, `analysis-docs.md`, `analysis-tasks.md`.

### Planning Phase

- ${feature_dir}/parallel-plan.md

## Dispatch Summary

- Dispatch Mode: [standalone sub-agents | agent team pw-[feature-name]]
- Execution Mode: [standard/optimized]
- Research agents: [4 standard / 0 optimized (unified agents counted under Analysis)]
- Analysis agents: [3 standard / 5 optimized (unified)]
- Validation agents: [3 standard / 2 optimized]
- Total agents: [10 standard / 7 optimized]
- Inter-agent sharing: [Disabled (Path A) | Enabled — teammates shared findings within each phase (Path B)]

## Plan Overview

- **Total Phases**: [count]
- **Total Tasks**: [count]
- **Independent Tasks**: [count that can run in parallel]
- **Max Dependency Depth**: [deepest chain]

## Validation Results

- File Path Validation: [passed/X issues]
- Dependency Graph: [valid/X issues]
- Task Completeness: [X high quality, Y needs work]

## Next Steps

The implementation plan is ready. Run:

/implement-plan [feature-name]

This will execute the plan with parallel agents where dependencies allow.
```

---

## Optimized Mode

When `--optimized` flag is used, the workflow changes:

### Optimized Agent Architecture

Instead of separate research (4) + analysis (3) agents, deploy 5 unified agents:

| Unified Agent         | Combines                            | Output                     | Model  |
| --------------------- | ----------------------------------- | -------------------------- | ------ |
| `arch-analyst`        | Arch Research + Context Synthesizer | `analysis-architecture.md` | sonnet |
| `pattern-analyst`     | Pattern Research + Code Analyzer    | `analysis-patterns.md`     | sonnet |
| `integration-analyst` | Integration Research                | `analysis-integration.md`  | sonnet |
| `docs-analyst`        | Doc Research                        | `analysis-docs.md`         | sonnet |
| `task-planner`        | Task Structure Agent                | `analysis-tasks.md`        | sonnet |

**Model Assignment**: Pass `model: "sonnet"` for all unified agents.

These agents produce combined research+analysis output, skipping Phase 5 entirely.

Validation uses 2 agents instead of 3 (Path + Dependency merged).

Dispatch follows the same Path A / Path B split as standard mode:

- **Path A (standalone, default)**: spawn all 5 unified agents in a single message with 5 `Task` calls.
- **Path B (`--team`)**: register 5 unified tasks up front, then spawn 5 teammates in a single message with `team_name="pw-[feature-name]"`.

**Total**: 7 agents instead of 10, 2 stages instead of 3.

**`--optimized --plan-only`**: reuses the five unified artifacts from a prior `--optimized` full run; there is no Phase 5 to regenerate them. Enforced at Step 4B (before any write) and re-checked by the Phase 7 PRE-CHECK.

### Optimized Mode Validation

Step 11 (research validator), Step 21 (analysis validator), and Step 22 (pre-generation gate) all accept an `--optimized` flag and MUST be invoked with it when `--optimized` was passed to the skill:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-research-artifacts.sh "${feature_dir}" --optimized
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/validate-analysis-artifacts.sh "${feature_dir}" --optimized
${CLAUDE_PLUGIN_ROOT}/skills/plan-workflow/scripts/persist-or-fail.sh "${feature_dir}" --optimized
```

In optimized mode, the gate's `MISSING_FILES` set is the 5 unified files: `analysis-architecture.md`, `analysis-patterns.md`, `analysis-integration.md`, `analysis-docs.md`, `analysis-tasks.md`. If any are missing, re-dispatch the failing agent — do NOT have the orchestrator write the file itself from a captured summary.

---

## Quality Standards

### shared.md Quality Checklist

- [ ] Clear, information-dense overview (3-4 sentences)
- [ ] All file paths verified to exist
- [ ] Brief but useful descriptions for each item
- [ ] Patterns linked to example files where possible
- [ ] Documentation marked with required reading topics

### parallel-plan.md Quality Checklist

- [ ] Information-dense overview (3-4 sentences)
- [ ] Complete list of critically relevant files
- [ ] Tasks organized into logical phases
- [ ] At least one independent task per phase
- [ ] Advice section with implementation insights
- [ ] No circular dependencies
- [ ] All file paths verified

### Task Quality Checklist

Each task must have:

- [ ] Clear, descriptive title
- [ ] Explicit dependencies listed
- [ ] "READ THESE BEFORE TASK" section
- [ ] Files to Create list (if any)
- [ ] Files to Modify list
- [ ] Concise, actionable instructions

---

## Output Contract

All files are written to `${feature_dir}/` (resolved via `resolve-plans-dir.sh`).

### Research Phase Artifacts

| File                       | Producer                         | Required Before     |
| -------------------------- | -------------------------------- | ------------------- |
| `research-architecture.md` | architecture-researcher teammate | shared.md synthesis |
| `research-patterns.md`     | patterns-researcher teammate     | shared.md synthesis |
| `research-integration.md`  | integration-researcher teammate  | shared.md synthesis |
| `research-docs.md`         | docs-researcher teammate         | shared.md synthesis |
| `shared.md`                | Team lead (this skill)           | Analysis phase      |

### Analysis Phase Artifacts (Standard Mode)

| File                  | Producer                     | Required Before             |
| --------------------- | ---------------------------- | --------------------------- |
| `analysis-context.md` | context-synthesizer teammate | parallel-plan.md generation |
| `analysis-code.md`    | code-analyzer teammate       | parallel-plan.md generation |
| `analysis-tasks.md`   | task-structurer teammate     | parallel-plan.md generation |

### Planning Phase Artifacts

| File               | Producer               | Required Before  |
| ------------------ | ---------------------- | ---------------- |
| `parallel-plan.md` | Team lead (this skill) | Skill completion |

**Contract Rules**:

1. Each agent MUST write its own output file using the Write tool
2. In Path B (`--team`), each teammate MUST share key findings with relevant teammates via SendMessage. In Path A (standalone), inter-agent sharing is unavailable — each sub-agent works independently.
3. The orchestrator MUST run `validate-research-artifacts.sh` before generating shared.md (Step 11)
4. The orchestrator MUST run `validate-analysis-artifacts.sh` after analysis agents complete (Step 21)
5. The orchestrator MUST run `persist-or-fail.sh` as a mandatory pre-generation gate (Step 22)
6. If validation fails, the orchestrator MUST message the failing teammate (Path B) or re-dispatch the sub-agent (Path A)
7. No file may be skipped or deferred — `persist-or-fail.sh` must exit 0 before plan generation
8. In Path B, the team MUST be cleaned up (TeamDelete) before skill completion

---

## Monorepo Support

The skill automatically detects and uses the correct plans directory in monorepo setups.

### Default Behavior

- Plans are created at the **git repository root** in `docs/plans/`
- Running the skill from any subdirectory still creates plans at the root

### Configuration

Create a `.plans-config` file to customize behavior:

**Repository Root** (centralized plans):

```yaml
# .plans-config at repo root
plans_dir: docs/plans
```

**Package-Level Plans** (optional):

```yaml
# .plans-config in packages/app1/
plans_dir: docs/plans
scope: local
```

---

## Important Notes

- **You are the planning orchestrator** - coordinate all phases of the workflow
- **Choose dispatch mode from `$ARGUMENTS`** - default is standalone sub-agents via `Task`; `--team` switches to teammates under `TeamCreate`/`TaskList`
- **One team for entire workflow (Path B only)** - create once, use across all phases
- **Spawn in parallel** - a single message per phase with multiple `Task` calls (Path A) or multiple `Agent` calls with `team_name=` + `name=` (Path B)
- **Pass model parameters** - use `model: "sonnet"` for research/analysis agents, `model: "haiku"` for path/dependency validators, `model: "sonnet"` for completeness-validator
- **Teammates share findings (Path B only)** - inter-teammate `SendMessage` coordination is unavailable to standalone sub-agents
- **Shut down between phases (Path B only)** - shut down teammates before spawning new ones for next phase
- **Validate with scripts** - run validation scripts after agents complete
- **Message on failure (Path B)** - if validation fails, message the relevant teammate; in Path A, re-dispatch a sub-agent
- **Preserve context** - read condensed analysis, not raw files
- **Validate thoroughly** - multiple validation passes ensure quality
- **Clean up team (Path B only)** - always `TeamDelete` before completing when a team was created
- **Monorepo aware** - automatically resolves correct plans directory via `resolve-plans-dir.sh`
