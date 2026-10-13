---
name: orchestrate
description: Coordinates specialized agents in dependency-resolved batches. Use when
  delegating a complex task, splitting independent implementation work, or coordinating
  multiple specialists.
---

# Multi-Agent Orchestration Skill

You are an orchestration expert coordinating multiple specialized agents to accomplish complex tasks. **Your role is to coordinate agents, not do the work yourself.** **Operational context:** Worktree isolation is on by default; all parallel and sequential agents share one feature worktree. --no-worktree runs in the current checkout. Standalone sub-agents are default.

Parallelism is the baseline of this skill — every batch's tasks dispatch concurrently. The only choice is **how** the implementor agents are dispatched:

- **Standalone sub-agents** (default) — plain `Task` calls per batch, no shared task list. Works in Claude Code, Cursor, and Codex.
- **Agent team** (`--team`, Codex runtime only; not available in bundle invocations) — single `create an agent group` with all subtasks registered up front (`record the task` + `addBlockedBy` for dependency wiring), per-batch teammate spawn, coordinated inter-batch shutdown via `send follow-up instructions`, and `close the agent group` at the end. Adds shared task-graph observability across all batches.

## Current Task

**Orchestrating**: `$ARGUMENTS`

Parse flags first, then treat the remainder as the task description:

- `--team` — (Codex runtime only; not available in bundle invocations) Dispatch each batch's agents under a shared `create an agent group` with up-front `record the task` + `addBlockedBy` dependency wiring and per-batch shutdown via `send follow-up instructions`. Aborts if invoked from a Cursor or Codex bundle (team tools are absent there).
- `--dry-run` — Show the orchestration plan without deploying agents. With `--team`, also prints the team name and per-batch teammate roster. Prints a `Worktrees:` line when worktree mode is active (no scripts called).
- `--plan-only` — Create orchestration plan file at `docs/orchestration/[sanitized-task].md` without execution. When worktree mode is active, the plan gains a `## Worktree Setup` section.
- `--sequential` — Force sequential execution (single-task batches, for tightly dependent tasks). When worktree mode is active, all sequential tasks run in the single feature worktree.
- `--worktree` — (legacy — now default; safe to omit) Accepted as a silent no-op. Worktree isolation is on by default; this flag matches the new default and has no additional effect.
- `--no-worktree` — Force worktree mode **OFF** regardless of task structure. All tasks run directly in the current checkout; no feature worktree is created.
- `<task-description>`: The complex task to orchestrate (required, can be multi-word).

Strip flags from `$ARGUMENTS` and set `TEAM_FLAG=true|false`, `DRY_RUN=true|false`, `PLAN_ONLY=true|false`, `SEQUENTIAL=true|false`, `WORKTREE_MODE=true|false`. Join the remaining non-flag tokens into `TASK_DESCRIPTION`.

**Feature slug derivation**: after `TASK_DESCRIPTION` is set, always sanitize it to produce `FEATURE_SLUG` before any `WORKTREE_MODE` branching — lowercase, replace `[^a-z0-9-]` with `-`, collapse runs of `-`, trim leading/trailing `-`, truncate to 20 characters. Fall back to `untitled` if empty. This is the same sanitization used for team-name context in `agent-team-dispatch.md` §1.

If no task description is provided after stripping flags, abort with usage instructions:

```
Usage: $orchestrate [--team] [--dry-run] [--plan-only] [--sequential] [--worktree] [--no-worktree] <task-description>

Examples:
  $orchestrate "Implement user authentication with tests and docs"
    # default: all parallel and sequential tasks share one feature worktree

  $orchestrate --team "Implement user authentication with tests and docs"
    # agent-team dispatch (worktree still on by default for parallel tasks)

  $orchestrate --dry-run "Debug payment processing failure"
  $orchestrate --plan-only "Refactor database layer"
  $orchestrate --sequential "Migrate legacy config"
  $orchestrate --team --dry-run "Update API documentation across all services"

  $orchestrate --no-worktree "Refactor the auth middleware"
    # opt out of worktree isolation; all tasks run in the current checkout

  $orchestrate --team --no-worktree "Implement user authentication with tests and docs"
    # agent-team dispatch without worktrees
```

**Compatibility note**: When this skill is invoked from a Cursor or Codex bundle, `--team` must abort with a clear message. Those bundles ship without team tools (`create an agent group`, `record the task`, `send follow-up instructions`, etc.). The default standalone sub-agent path is the only execution mode available there. `--worktree` is supported on all targets via the Bash-fallback path (`git worktree add`); on Cursor, emit the `git worktree add` commands as instructions rather than auto-creating.

**Team opt-in note**: If `--team` is passed and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is not set to `1` in the environment, abort with: `--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Use --parallel instead, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Codex settings if you intentionally want agent-team dispatch.`

---

## Phase 0: Task Analysis

### Step 1: Parse Task Description

Extract the task description from `$ARGUMENTS` (everything before any flags).

Run the task analysis script:

```bash
~/.codex/plugins/ycc/skills/orchestrate/scripts/analyze-task.sh "$TASK_DESCRIPTION"
```

The script provides:

- Task complexity estimate
- Suggested decomposition approach
- Potential agent types needed
- Recommended execution mode (parallel vs sequential)

### Step 2: Load Agent Catalog

Read the complete agent catalog:

```bash
cat ~/.codex/plugins/ycc/skills/orchestrate/references/agent-catalog.md
```

This provides the complete reference of available agents organized by category, capabilities, and use cases.

### Step 3: Initial Assessment

Analyze the task to determine:

- **Scope**: Is this a feature, bug, refactor, documentation, or infrastructure task?
- **Components**: Which parts of the system are involved?
- **Complexity**: Simple (1-2 agents), Medium (3-5 agents), Complex (6+ agents)
- **Dependencies**: Are subtasks independent or sequential?

---

## Phase 1: Task Decomposition & Team Creation

### Step 4: Read Decomposition Template

```bash
cat ~/.codex/plugins/ycc/skills/orchestrate/references/task-breakdown.md
```

This template provides patterns for breaking down tasks by feature area, technical layer, cross-cutting concerns, and dependencies.

### Step 5: Register Subtasks

Branch on `TEAM_FLAG`:

- `TEAM_FLAG=false` → **Path A (default)**: register subtasks locally via `the task tracker`. No team is created. Skip to Step 6.
- `TEAM_FLAG=true` → **Path B**: create the team and register all subtasks up front with dependency wiring (5a–5c below).

#### Path A — Local todos (default)

Using **the task tracker**, register each subtask as a todo item:

```
- id: "subtask-1", content: "[Subtask 1 title] — agent: [agent-type] — depends: [none/list]", status: "pending"
- id: "subtask-2", content: "[Subtask 2 title] — agent: [agent-type] — depends: [subtask-1]", status: "pending"
```

Track batch completion in-context after each batch's `Agent` calls return.

#### Path B — Agent team (`--team` only)

> If `DRY_RUN=true` or `PLAN_ONLY=true`, **skip 5a–5c and proceed directly to Step 10**. Team creation is not needed for dry-run or plan-only output; compute the sanitized team name in-memory only.

**5a: Create the orchestration team:**

Sanitize the task description to create a team name (lowercase, replace non-alphanumeric with `-`, collapse runs, trim, cap at **20 chars**, fall back to `untitled` if empty). Team name: `orch-<sanitized-task>`.

```
create an agent group: team_name="orch-<sanitized-task>", description="Orchestration team for: <task description>"
```

On failure, abort.

**5b: Create subtasks in the shared task list:**

For **every subtask across all batches**, use **record the task**:

```
record the task: subject="[subtask-N]: [Description]", description="Agent: [agent-type]. Scope: [details]. Expected output: [deliverables]."
```

**5c: Wire up dependencies up front:**

For each subtask `T` with dependencies `[X, Y, Z]`, use **update the task tracker** with `addBlockedBy`:

```
update the task tracker: taskId="<T-id>", addBlockedBy=["<X-id>", "<Y-id>", "<Z-id>"]
```

This populates the shared task graph **once**, not per batch. If any `record the task` or `update the task tracker` fails → `close the agent group`, then abort.

### Step 6: Validate Task Decomposition

Ensure each subtask meets quality standards:

- [ ] Clear, specific scope (not too broad)
- [ ] Single responsibility (doesn't overlap with others)
- [ ] Appropriate size (completable in one focused session)
- [ ] Dependencies explicitly stated
- [ ] Success criteria clear
- [ ] Agent type assignment justified

Optionally run validation script:

```bash
if [[ -f "~/.codex/plugins/ycc/skills/orchestrate/scripts/validate-agents.sh" ]]; then
  ~/.codex/plugins/ycc/skills/orchestrate/scripts/validate-agents.sh
fi
```

---

## Phase 2: Agent Assignment

### Step 7: Map Subtasks to Agents

For each subtask, determine the optimal agent type based on:

| Task Type                | Recommended Agent                                         |
| ------------------------ | --------------------------------------------------------- |
| Code exploration/finding | `explore`, `code-finder`                                  |
| Architecture research    | `codebase-research-analyst`                               |
| Frontend UI work         | `frontend-ui-developer`, `nextjs-ux-ui-expert`            |
| Backend API work         | `nodejs-backend-architect`, `go-api-architect`            |
| Database changes         | `db-modifier`, `sql-database-architect`                   |
| Documentation            | `documentation-writer`, `api-docs-expert`                 |
| Testing strategy         | `test-strategy-planner`                                   |
| Bug diagnosis            | `root-cause-analyzer`                                     |
| Infrastructure           | `terraform-architect`, `cloudflare-architect`             |
| DevOps/automation        | `ansible-automation-expert`, `systems-engineering-expert` |

### Step 8: Read Agent Prompt Templates

```bash
cat ~/.codex/plugins/ycc/skills/orchestrate/references/agent-prompts.md
```

Use standard prompts for common orchestration patterns to ensure consistency.

### Step 9: Prepare Agent Instructions

For each subtask, prepare:

1. **Context**: What the agent needs to know
2. **Scope**: Specific files/areas to focus on
3. **Deliverables**: Expected outputs
4. **Constraints**: What NOT to do (avoid overlap)

---

## Phase 2.5: Worktree Setup

### How Worktree Mode Is Decided

The decision follows a strict precedence order:

1. **`--no-worktree` present** → `WORKTREE_MODE=false`. Worktree isolation is forced off. All tasks run directly in the current checkout. No feature worktree is created.
2. **Neither `--no-worktree` nor any explicit flag** → `WORKTREE_MODE=true` **(new default — was false)**. All parallel and sequential agents share one feature worktree.

`--worktree` is accepted as a silent no-op and matches the new default; it has no additional effect. Note: this skill does not auto-detect `## Worktree Setup` annotations from a plan (it creates its own decomposition), so the only opt-out is `--no-worktree`.

### Branch Preparation

When `DRY_RUN=false` and `PLAN_ONLY=false`, **always prepare the feature branch** before any worktree setup or agent dispatches. Without this, agents inherit whatever branch the orchestrator started on (typically `main`) and commit there:

```bash
FEATURE_BRANCH=$(bash ~/.codex/plugins/ycc/shared/scripts/prepare-feature-branch.sh "${FEATURE_SLUG}")
```

See `~/.codex/plugins/ycc/shared/references/branch-prep.md` for the helper's behavior and exit-code contract. Skip both this call and the worktree setup below when `DRY_RUN=true` or `PLAN_ONLY=true`.

When `WORKTREE_MODE=false` (`--no-worktree`), skip parent worktree setup after branch preparation.

### When `WORKTREE_MODE=true` and `DRY_RUN=false` and `PLAN_ONLY=false`

Determine the repository name from the current directory (`basename $(git rev-parse --show-toplevel)`). Use the `FEATURE_SLUG` derived during flag parsing.

Create the parent worktree **once**, before any batch dispatches:

```bash
bash ~/.codex/plugins/ycc/shared/scripts/setup-worktree.sh parent <repo-name> <FEATURE_SLUG>
```

Store the echoed path as `PARENT_WORKTREE_PATH`. All parallel and sequential agents in every batch share this path.

When `WORKTREE_MODE=true` and `SEQUENTIAL=true`: sequential tasks run in `PARENT_WORKTREE_PATH` — the same single worktree used for parallel tasks.

When `WORKTREE_MODE=true` and `DRY_RUN=true`: skip all script calls. Instead, compute the expected parent path as `<repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/` and proceed to Phase 3 to include it in the dry-run output.

When `WORKTREE_MODE=true` and `PLAN_ONLY=true`: skip all script calls. Include the worktree annotation in the written plan (see Phase 3).

---

## Phase 3: Dry Run Check

### Step 10: Check for Dry Run or Plan-Only Mode

If `--dry-run` is present:

**Default dry-run (no `--team`)** — display the batch roster only:

```markdown
# Dry Run: Orchestration Plan for [Task]

## Task Analysis

- Complexity: [Simple/Medium/Complex]
- Execution Mode: [Parallel/Sequential]
- Total Subtasks: [count]

## Subtask Breakdown

### Batch 1 (Independent Tasks)

1. **[Subtask 1]**
   - Agent: [agent-type]
   - Focus: [brief description]
   - Output: [expected deliverable]

2. **[Subtask 2]**
   - Agent: [agent-type]
   - Focus: [brief description]
   - Output: [expected deliverable]

### Batch 2 (After Batch 1)

1. **[Subtask 3]**
   - Agent: [agent-type]
   - Dependencies: [subtask-1]
   - Focus: [brief description]
   - Output: [expected deliverable]

## Agent Deployment Summary

- Total Agents: [count]
- Parallel Batches: [count]
- Max Parallelism: [largest batch size]

## Next Steps

Remove --dry-run flag to execute the orchestration.
```

**`--team --dry-run`** — also print the team name and per-batch teammate roster:

```
Team name:    orch-<sanitized-task>
Total subtasks: <N>  (across <M> batches, max parallel width <X>)
Dependencies: <K edges>

Batch 1: <comma-separated subtask IDs>
Batch 2: <comma-separated subtask IDs>  (depends on Batch 1)
...
Batch M: <comma-separated subtask IDs>  (depends on Batch M-1)

Per-batch teammate roster:
  Batch 1:
    - subtask-1  subagent_type=<agent-type>  focus=<short>
    - subtask-2  subagent_type=<agent-type>  focus=<short>
  ...
```

**`--worktree --dry-run`** — append a `Worktree:` line to the dry-run output (both the default and `--team` variants). No `setup-worktree.sh` or `list-worktrees.sh` calls are made in dry-run mode:

```
Worktree:   feature=<repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/  (all subtasks)
```

Do **not** call `create an agent group`, `record the task`, `Agent`, `send follow-up instructions`, or `close the agent group` in dry-run mode. **STOP HERE**.

If `--plan-only` is present:

- Create the plan as `docs/orchestration/[sanitized-task-name].md`
- Save the complete orchestration plan for later execution
- Display the plan location and summary
- No team cleanup required — team creation is skipped entirely in plan-only mode
- When `WORKTREE_MODE=true`: include a `## Worktree Setup` section in the written plan (immediately after frontmatter, before Batch 1). Follow the annotation format in `ycc/skills/_shared/references/worktree-strategy.md` §2: list only the parent path. Do NOT add child paths or a `**Children**:` list.
- **STOP HERE** — do not deploy agents

---

## Phase 4: Parallel Agent Deployment

### Step 11: Organize into Execution Batches

Group subtasks by dependencies:

**Batch 1**: All subtasks with no dependencies (fully independent)
**Batch 2**: Subtasks depending only on Batch 1
**Batch 3**: Subtasks depending on Batch 1 and/or 2
...and so on

If `--sequential` flag is present, create single-task batches.

### Step 12: Deploy Batch

Branch on `TEAM_FLAG`:

- `TEAM_FLAG=false` → **Path A — Standalone sub-agent batches** (default).
- `TEAM_FLAG=true` → **Path B — Agent team batches**.

---

#### Path A — Standalone Sub-Agent Batches (default)

See `~/.codex/plugins/ycc/shared/references/standalone-dispatch.md` for the full `Task`-vs-`Agent` dispatch contract and anti-patterns this path follows.

For each batch, do the following **in order**:

**1. Build the per-batch agent list** — determine each subtask's name, agent type, focus, and deliverables.

**2. Spawn ALL batch agents in a SINGLE message** using MULTIPLE `Task` tool calls. **No `team_name`, no `name`, no `record the task`** — standalone sub-agent semantics. Each prompt must use the **Path A coordination block** from `agent-prompts.md` (standalone implementor — no inter-agent coordination).

When `WORKTREE_MODE=true`, each Task call includes `Working directory: <PARENT_WORKTREE_PATH>` in the prompt. Do **not** pass `isolation: "worktree"` here: that creates a distinct harness worktree per agent and breaks the single-worktree contract. Add a coordination note: `All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.`:

```
Task(
  subagent_type = "nodejs-backend-architect",
  description = "Implement auth system",
  prompt = "Working directory: <repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path A coordination block]"
)
Task(
  subagent_type = "test-strategy-planner",
  description = "Create auth test plan",
  prompt = "Working directory: <repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path A coordination block]"
)
Task(
  subagent_type = "documentation-writer",
  description = "Document auth API",
  prompt = "Working directory: <repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path A coordination block]"
)
```

When `WORKTREE_MODE=false` (--no-worktree), omit the `Working directory:` line — standard Path A semantics.

**4. Wait for batch completion** — `Task` calls block until each sub-agent returns. Completion is implicit when all parallel calls in the single message return.

**5. Process results** — review each returned summary. Update the corresponding `the task tracker` items to `completed`.

**6. Handle failures** — if a subtask fails, note the failure, determine if dependent subtasks can proceed, and continue with independent subtasks.

**7. Identify next batch** — scan the `the task tracker` list for pending subtasks whose dependencies are now all `completed`. If subtasks remain but none are unblocked, report deadlock and stop.

No `send follow-up instructions` shutdown needed in Path A — there are no teammates to shut down.

---

#### Path B — Agent Team Batches (`--team`)

For each batch, do the following **in order** (follows `agent-team-dispatch.md` §7 lifecycle):

**1. Build the teammate list** for this batch — list each subtask's name and description so teammates know who else is working in parallel. Substitute into `{{BATCH_TEAMMATES}}`.

**2. Spawn ALL batch teammates in a SINGLE message** using MULTIPLE `Agent` tool calls. Every call MUST include `team_name` AND `name`. When `WORKTREE_MODE=true`, each call also includes a `Working directory: <PARENT_WORKTREE_PATH>` line in the prompt. Do **not** pass `isolation: "worktree"` here: that creates a distinct harness worktree per teammate and breaks the single-worktree contract. Add the coordination note: `All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.`:

```
Agent(
  team_name = "orch-<sanitized-task>",
  name = "subtask-1",
  subagent_type = "nodejs-backend-architect",
  description = "Implement auth system",
  isolation = "worktree",
  prompt = "Working directory: <repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path B Team Communication section]"
)
Agent(
  team_name = "orch-<sanitized-task>",
  name = "subtask-2",
  subagent_type = "test-strategy-planner",
  description = "Create auth test plan",
  isolation = "worktree",
  prompt = "Working directory: <repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path B Team Communication section]"
)
Agent(
  team_name = "orch-<sanitized-task>",
  name = "subtask-3",
  subagent_type = "documentation-writer",
  description = "Document auth API",
  isolation = "worktree",
  prompt = "Working directory: <repo-root>/.codex/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path B Team Communication section]"
)
```

When `WORKTREE_MODE=false` (--no-worktree), omit `isolation` and `Working directory:` — standard Path B semantics. Each prompt MUST include the Path B Team Communication section from `agent-prompts.md`, with `{{BATCH_NUMBER}}` and `{{BATCH_TEAMMATES}}` substituted.

**4. Monitor progress** — use `the task tracker` to check when all batch tasks are complete. If a teammate messages you with an issue, respond via `send follow-up instructions` with guidance.

**5. Handle failures** — if a subtask fails, note the failure, determine if dependent subtasks can proceed, and continue with independent subtasks.

**6. Shut down batch teammates** — send `send follow-up instructions(to="subtask-<N>", a shutdown request)` to each teammate of the just-completed batch. Wait for all shutdowns to complete before proceeding.

**7. Identify next batch** — check `the task tracker` for pending tasks with all blockers completed. If tasks remain but none are unblocked, report deadlock and stop.

### Step 13: Repeat Until Complete

Repeat Step 12 for each subsequent batch until all subtasks are completed or no more can be unblocked.

---

## Phase 5: Result Synthesis & Summary

### Step 14: Consolidate Agent Outputs

Run the summarization script:

```bash
~/.codex/plugins/ycc/skills/orchestrate/scripts/summarize-results.sh
```

Collect outputs from all agents and organize by:

- Files created
- Files modified
- Documentation added
- Tests created
- Issues encountered

### Step 15: Integration Check

Verify that agent outputs work together:

- [ ] No conflicting changes between agents
- [ ] All dependencies properly integrated
- [ ] Cross-references between components valid
- [ ] Consistent patterns and conventions used

### Step 16: Clean Up Team

Gated on `TEAM_FLAG`:

- `TEAM_FLAG=false` → No team was created. Skip this step.
- `TEAM_FLAG=true` → Delete the team and its resources:

  ```
  close the agent group
  ```

### Step 17: Final Summary

When `WORKTREE_MODE=true`, call `list-worktrees.sh` and append its output to the summary:

```bash
bash ~/.codex/plugins/ycc/shared/scripts/list-worktrees.sh <repo-name> <FEATURE_SLUG>
```

This prints the feature worktree path, its branch, and the `git worktree remove` command for manual cleanup. The worktree survives until manually removed — there are no child worktrees to clean up.

Provide comprehensive completion summary:

```markdown
# Orchestration Complete: [Task]

## Execution Mode

[Standalone sub-agents | Agent team (team: orch-<sanitized-task>)]

## Team Summary (Path B only)

- Team: orch-<sanitized-task>
- Total teammates spawned: [count across all batches]
- Batches executed: [count]
- Inter-agent sharing: Enabled (teammates shared findings within batches via send follow-up instructions)

## Execution Summary

- **Total Subtasks**: [count]
- **Completed**: [count]
- **Failed**: [count]
- **Execution Batches**: [count]

## Results by Agent

### [Agent Type 1] - [Subtask 1]

**Status**: Success
**Outputs**:

- Created: [files]
- Modified: [files]
- Notes: [key points]

### [Agent Type 2] - [Subtask 2]

**Status**: Success
**Outputs**:

- Created: [files]
- Modified: [files]
- Notes: [key points]

## Files Changed

### Created

- /path/to/new/file1.ext
- /path/to/new/file2.ext

### Modified

- /path/to/modified/file1.ext
- /path/to/modified/file2.ext

## Integration Status

- [x] All agent outputs integrated successfully
- [x] No conflicting changes detected
- [x] Cross-references validated
- [ ] Manual review needed for: [items]

## Issues Encountered

[List any problems, warnings, or areas needing attention]

## Next Steps

1. Review the changes in your editor
2. Test the integrated functionality
3. Address any failed subtasks if needed
4. Commit the changes when satisfied
```

---

## Quality Standards

### Task Decomposition Checklist

Each subtask must have:

- [ ] Clear, specific scope (not too broad or vague)
- [ ] Single responsibility (no overlapping work)
- [ ] Appropriate size (completable in one session)
- [ ] Explicit dependencies stated
- [ ] Clear success criteria
- [ ] Agent type assignment justified

### Agent Assignment Checklist

Each agent assignment must have:

- [ ] Agent type matches subtask requirements
- [ ] No duplicate work between agents
- [ ] Context files identified for agent
- [ ] Expected output format specified
- [ ] Non-overlapping scope with other agents
- [ ] Clear boundaries defined

### Execution Checklist

The orchestration must:

- [ ] Parse flags and set `TEAM_FLAG`, `DRY_RUN`, `PLAN_ONLY`, `SEQUENTIAL`, `WORKTREE_MODE` before any side effects (default: `WORKTREE_MODE=true` unless `--no-worktree` is passed)
- [ ] Deploy independent tasks in parallel (single message, multiple `Agent` calls)
- [ ] Respect dependency ordering between batches
- [ ] Track progress via `the task tracker` (Path A) or `the task tracker` (Path B)
- [ ] Handle failures gracefully
- [ ] Synthesize results on completion
- [ ] Verify integration between agent outputs
- [ ] In Path B: create team before spawning agents, include `team_name` + `name` on every `Agent` call, shut down teammates between batches via `send follow-up instructions`, and clean up with `close the agent group`

### Result Quality Checklist

The final result must have:

- [ ] All subtasks attempted
- [ ] Clear status for each subtask (success/fail)
- [ ] Complete list of files changed
- [ ] Integration issues identified
- [ ] Failed subtasks documented
- [ ] Next steps provided

---

## Best Practices

### Coordination Principles

1. **Delegate Everything**: Only coordinate; don't implement yourself
2. **Maximize Parallelism**: Run independent tasks simultaneously
3. **Clear Boundaries**: Ensure no overlap between agents
4. **Single Goal**: Keep all agents aligned to the main objective
5. **Track Progress**: `the task tracker` in Path A, `the task tracker` in Path B
6. **Synthesize Results**: Integrate outputs into coherent whole
7. **Path B additions**: `create an agent group` before spawning; every `Agent` call with `team_name=` and `name=`; `send follow-up instructions` shutdown between batches; `close the agent group` on completion

### When to Use Sequential Mode

Use `--sequential` flag when:

- Subtasks have tight coupling
- Each step informs the next
- Risk of conflicts is high
- Debugging or exploratory work

### When to Use Plan-Only Mode

Use `--plan-only` flag when:

- Need approval before execution
- Task is very large or risky
- Want to review approach first
- Building reusable orchestration pattern

### Common Orchestration Patterns

**Feature Implementation**:

- Research agent -> multiple implementation agents -> test agent -> docs agent

**Bug Investigation**:

- Root cause analyzer -> fix implementor -> test verifier -> docs updater

**Refactoring**:

- Architecture analyst -> multiple refactor agents -> test updater -> docs updater

**Documentation Update**:

- Code analyzer -> multiple doc writers -> cross-link validator

---

## Important Notes

- **You are the orchestrator** — coordinate agents, don't implement
- **Parallelism is the baseline** — every batch dispatches concurrently regardless of path
- **Default dispatch is standalone sub-agents** — `--team` is an opt-in for shared task-graph observability in Codex
- **Deploy in batches** — single message with multiple `Agent` calls per batch
- **Respect dependencies** — never start a subtask before its dependencies complete
- **Handle failures** — continue with independent subtasks if one fails
- **Track progress** — `the task tracker` updates (Path A) or `the task tracker` (Path B)
- **Path B only** — create team first, include `team_name` + `name` on every spawn, shut down teammates between batches via `send follow-up instructions`, and call `close the agent group` on completion
- **Quality over speed** — ensure proper coordination and integration

---

## Troubleshooting

### Issue: Agents producing conflicting changes

**Solution**: Review subtask boundaries, ensure non-overlapping scopes, redeploy with clearer instructions

### Issue: Dependencies not properly sequenced

**Solution**: Review dependency graph, adjust batch organization, ensure proper ordering

### Issue: Agent outputs don't integrate

**Solution**: Add integration subtask, deploy agent to resolve conflicts, update instructions for clarity

### Issue: Too many agents for single batch

**Solution**: Break into smaller batches, stagger deployment, or use sequential mode

### Issue: Unclear what to orchestrate

**Solution**: Ask clarifying questions before decomposition, use dry-run to preview, iterate on plan

---

## Agent Team Lifecycle Reference

For Path B's team lifecycle contract (sanitization, shutdown sequence, failure policy,
multi-batch reuse pattern), refer to:

```
~/.codex/plugins/ycc/shared/references/agent-team-dispatch.md
```
