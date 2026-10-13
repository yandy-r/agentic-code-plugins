---
name: implement-plan
description: Executes parallel-plan.md with dependency-aware implementor batches.
  Use when implementing a planned feature, running parallel-plan tasks, or resuming
  a batched implementation.
allowed-tools:
- Read
- Grep
- Glob
- Write
- Edit
- MultiEdit
- Agent
- Task
- AskUserQuestion
- TodoWrite
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
- Bash(grep:*)
- Bash(git:*)
- Bash(~/.agents/skills/implement-plan/scripts/*.sh:*)
- Bash(~/.agents/ycc-shared/scripts/*.sh:*)
---

# Parallel Plan Executor

Execute a parallel implementation plan by deploying implementor agents in dependency-resolved batches. This is **Step 3** of the planning workflow, transforming the plan into working code. **Operational context:** Require parallel-plan.md from parallel-plan. Worktree isolation is on by default: create or reuse one feature worktree on a feature branch; --no-worktree uses only the current-checkout feature branch, and --worktree is a legacy no-op. Standalone sub-agents are default.

Parallelism is the baseline of this skill — every batch's tasks dispatch concurrently. The only choice is **how** the implementor agents are dispatched:

- **Standalone sub-agents** (default) — plain `Task` calls per batch, no shared task list. Works in Claude Code, Cursor, and Codex.
- **Agent team** (`--team`, Claude Code only) — single `TeamCreate` with all tasks registered up front (`TaskCreate` + `addBlockedBy` for dependency wiring), per-batch teammate spawn, coordinated inter-batch shutdown via `SendMessage`, and `TeamDelete` at the end. Adds shared task-graph observability across all batches.

## Workflow Integration

This skill is the final step of the planning workflow. It requires `parallel-plan.md` from the parallel-plan skill.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ shared-context  │ ──▶ │  parallel-plan  │ ──▶ │  implement-plan │
│  (Step 1)       │     │  (Step 2)       │     │  (this skill)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     Creates:                Creates:               Executes:
     shared.md              parallel-plan.md      parallel-plan.md
```

**If parallel-plan.md doesn't exist**, run `/parallel-plan [feature-name]` first.

## Arguments

**Target**: `$ARGUMENTS`

Parse flags first, then treat the remainder as the feature name:

- `--team` — (Claude Code only) Dispatch each batch's implementor agents under a shared `TeamCreate` with up-front `TaskCreate` + `addBlockedBy` dependency wiring and per-batch shutdown via `SendMessage`. Aborts if invoked from a Cursor or Codex bundle (team tools are absent there).
- `--dry-run` — Show the execution plan without deploying agents. With `--team`, also prints the team name and per-batch teammate roster.
- `--worktree` — (legacy — now default; safe to omit) Accepted as a silent no-op. Worktree isolation is on by default; this flag matches the new default and has no additional effect.
- `--no-worktree` — Force worktree mode **OFF** regardless of plan annotations. Create/use `feat/<feature-name>` in the current checkout and run tasks there. No feature worktree is created.
- `<feature-name>` — The name of the feature to implement (matches directory name in `docs/plans/`).

Strip the flags from `$ARGUMENTS` and set `TEAM_FLAG=true|false`, `DRY_RUN=true|false`, `WORKTREE_MODE=true|false`, and `WORKTREE_FLAG_PRESENT=true|false`. The remaining non-flag token is the feature name.

**Validation**:

- `--worktree` and `--no-worktree` together → abort with: `--worktree and --no-worktree are mutually exclusive. Use --no-worktree to opt out of the default.`
- If `--team` is passed and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is not set to `1` in the environment, abort with: `--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Use --parallel instead, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Claude Code settings if you intentionally want agent-team dispatch.`

If no feature name is provided after stripping flags, abort with usage instructions:

```
Usage: /implement-plan [--team] [--dry-run] [--worktree] [--no-worktree] <feature-name>

Examples:
  /implement-plan user-authentication
    # default: create/reuse one feature worktree on feat/user-authentication

  /implement-plan --team user-authentication
    # agent-team dispatch (worktree still on by default)

  /implement-plan --dry-run payment-integration
  /implement-plan --team --dry-run payment-integration

  /implement-plan --no-worktree my-feature
    # opt out of worktree isolation; create/use feat/my-feature in the current checkout

  /implement-plan --team --no-worktree my-feature
    # agent-team dispatch on the current-checkout feature branch
```

**Compatibility note**: When this skill is invoked from a Cursor or Codex bundle, `--team` must abort with a clear message. Those bundles ship without team tools (`TeamCreate`, `TaskCreate`, `SendMessage`, etc.). The default standalone sub-agent path is the only execution mode available there. `--worktree` is compatible with all targets through a single pre-created feature worktree plus `Working directory:` prompts. Do **not** request tool-side per-agent worktree isolation for task dispatch in this flow, because that creates separate harness worktrees and breaks the single-worktree contract. Codex and opencode use Bash `git worktree add`; Cursor emits manual setup commands only.

---

## Phase 0: Prerequisites Check

### Step 1: Validate Prerequisites

After flag parsing, extract the feature name (first non-flag argument).

Run the prerequisites check script:

```bash
~/.agents/skills/implement-plan/scripts/check-prerequisites.sh [feature-name]
```

If the script exits with error:

- Display the error message
- Instruct user to run `/parallel-plan` first to create the implementation plan
- **STOP HERE** - do not proceed

### Step 2: Read Planning Documents

Read the essential planning documents:

1. `docs/plans/[feature-name]/parallel-plan.md` - The implementation plan
2. `docs/plans/[feature-name]/shared.md` - Architecture context

Also read files listed in the "Critically Relevant Files" section of parallel-plan.md.

---

## Phase 1: Parse Plan & Build Dependency Graph

### Step 3: Extract Tasks

Parse `parallel-plan.md` to extract all tasks and optional worktree annotations:

```bash
~/.agents/skills/implement-plan/scripts/parse-dependencies.sh docs/plans/[feature-name]/parallel-plan.md
```

The script emits optional header lines followed by per-task rows.

**Header lines** (present only when the plan has a `## Worktree Setup` section):

- `WT_PARENT_PATH=<path>` — parent worktree path
- `WT_FEATURE_SLUG=<slug>` — the `<repo>-<feature>` directory suffix; split on `-` to get the feature component

**Per-task rows** (`TASK_ID|TASK_TITLE|DEPENDENCIES`):

- **Task ID**: e.g., 1.1, 2.3, 3.1 (or T0, T1, T2)
- **Task Title**: Descriptive name
- **Dependencies**: List from `Depends on [...]` or `- **Dependencies**: ...`
- **Files to Read**: From "READ THESE BEFORE TASK" (parsed from the plan markdown directly)
- **Files to Create**: From "Files to Create"
- **Files to Modify**: From "Files to Modify"
- **Instructions**: Implementation details

### How Worktree Mode Is Decided

The decision follows a strict precedence order:

1. **`--no-worktree` present** → `WORKTREE_MODE=false`. Worktree isolation is forced off regardless of plan annotations. No feature worktree is created.
2. **Plan contains `## Worktree Setup`** → `WORKTREE_MODE=true`. The plan annotations are the source of truth; follow them exactly.
3. **Neither of the above** → `WORKTREE_MODE=true` **(new default — was false)**. Worktree isolation activates even when the plan has no annotations. The single feature-worktree path is derived from the feature name using the deduction rules below.

`--worktree` is accepted as a silent no-op and matches the new default; it has no additional effect.

**After parsing**, determine worktree activation:

- If any `WT_PARENT_PATH=` header line was emitted → the plan has worktree annotations → set `WORKTREE_ACTIVE=true`, store `WT_PARENT_PATH` and `WT_FEATURE_SLUG`.
- If `WORKTREE_MODE=true` (flag passed or default) → set `WORKTREE_ACTIVE=true` regardless of annotation presence.
- Always ensure branch variables exist:
  - `WT_REPO_NAME` = basename of git repo root (run `git -C . rev-parse --show-toplevel | xargs basename`)
  - `WT_FEATURE_SLUG` = parsed plan annotation slug if present; otherwise the `<feature-name>` argument (same as `${feature_dir}` basename)
  - `FEATURE_BRANCH` = `feat/${WT_FEATURE_SLUG}`
- If `WORKTREE_ACTIVE=true` and the plan had no annotations (the default-on fallback), also set `WT_PARENT_PATH` = `<repo-root>/.claude/worktrees/${WT_REPO_NAME}-${WT_FEATURE_SLUG}/`.
- If `WORKTREE_MODE=false` (`--no-worktree`) → no feature worktree; set `WORKTREE_ACTIVE=false`.

### Step 4: Build Dependency Graph

Create a dependency graph structure:

```
Independent Tasks (Depends on [none]):
  - Task 1.1
  - Task 1.3
  - Task 2.2

Dependent Tasks:
  - Task 1.2 → depends on [1.1]
  - Task 2.1 → depends on [1.1, 1.2]
  - Task 2.3 → depends on [2.1, 2.2]
  - Task 3.1 → depends on [2.1]
```

Keep this graph available for both Path A (ordering) and Path B (`addBlockedBy` wiring).

---

## Phase 2: Create Todo List

### Step 5: Generate Comprehensive Todos

Using **TodoWrite**, create a todo item for each task in the plan:

Format each todo as:

- `id`: Task ID (e.g., "task-1-1")
- `content`: "[Task ID] [Task Title] - Depends on: [dependencies]"
- `status`: "pending"

Example:

```
- task-1-1: "1.1 Create user model - Depends on: none"
- task-1-2: "1.2 Add validation - Depends on: 1.1"
- task-1-3: "1.3 Setup routes - Depends on: none"
```

### Step 6: Identify First Batch

Identify all tasks with `Depends on [none]` - these form the first batch.

Mark these as ready for execution.

---

## Phase 2.5: PREPARE — Branch / Worktree Setup

### Step 6.5: Check git state

Run from the current checkout:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
CURRENT_BRANCH=$(git branch --show-current)
GIT_STATUS=$(git status --porcelain)
FEATURE_BRANCH="feat/${WT_FEATURE_SLUG}"
```

Before creating a worktree or branch, inspect `GIT_STATUS`.

- If the only dirty files are expected pre-commit plan artifacts under `docs/plans/${WT_FEATURE_SLUG}/`, continue.
- If there are unrelated dirty files, **STOP** and ask the user to stash, commit, or re-run after cleaning the checkout.

### Step 6.6: Prepare the execution tree

Prepare the feature branch directly in the current checkout **before** any worktree setup or implementor-agent dispatch. The helper exits non-zero on failure and echoes the prepared branch name on success. **Do not skip it** — narrative-only branch instructions are how the original `--no-worktree` bug allowed agents to commit to `main`. See `~/.agents/ycc-shared/references/branch-prep.md` for the helper's behavior and exit-code contract.

```bash
FEATURE_BRANCH=$(bash ~/.agents/ycc-shared/scripts/prepare-feature-branch.sh "${WT_FEATURE_SLUG}")
```

When `WORKTREE_ACTIVE=true`, create the parent worktree **once** before Batch 1. The worktree adopts the prepared `FEATURE_BRANCH`:

```bash
WT_PARENT_PATH=$(bash ~/.agents/ycc-shared/scripts/setup-worktree.sh parent "${WT_REPO_NAME}" "${WT_FEATURE_SLUG}")
```

This is a one-time call before Batch 1. The script is idempotent — if the parent
worktree already exists with the correct branch it echoes the path and returns 0.

Store the echoed path as `WT_PARENT_PATH` (overrides any deduced value).

All agents in every batch — parallel and sequential — operate directly in this
single feature worktree. No child worktrees are created.

When `WORKTREE_ACTIVE=false` (`--no-worktree`), skip parent-worktree setup.

After this branch step, all agents in every batch operate in the current checkout. Include `Working directory: ${REPO_ROOT}` in each prompt when `--no-worktree` is active so dispatched agents target the prepared branch consistently.

### Step 6.7: Move plan artifacts into the worktree

> **Only when `WORKTREE_ACTIVE=true`** — skip this move entirely when `--no-worktree` is active.
>
> **Invariant**: plan artifacts move into the worktree once; they never travel back. Never `cp`, `rsync`, or "sync" plan files across trees.

`parallel-plan.md` and `shared.md` are pre-commit and live in the **main checkout** when this skill starts. Move them into the worktree right after creation — never copy, never sync. After this step the main checkout is clean.

```bash
PLAN_PATH=$(bash ~/.agents/ycc-shared/scripts/move-plan-to-worktree.sh \
  "docs/plans/${WT_FEATURE_SLUG}/parallel-plan.md" \
  "$WT_PARENT_PATH" \
  "docs/plans/${WT_FEATURE_SLUG}/shared.md")
```

`$PLAN_PATH` is the canonical plan location inside the worktree. Use it for every later reference in this run. Any companion research artifact emitted under the same `docs/plans/${WT_FEATURE_SLUG}/` directory before commit can ride along by appending it to the argument list above.

All subsequent file writes in Phase 3 (validation, between-batch checks, reports) run inside `$WT_PARENT_PATH`, not from the main repo root. When `--no-worktree` is active, keep using the original plan path and run Phase 3 in the current checkout on the prepared feature branch.

---

## Phase 3: Execute in Batches

### Step 7: Dry Run Gate

If `--dry-run` is present:

**Default dry-run (no `--team`)** — display the batch roster only:

```markdown
# Dry Run: Implementation Plan for [feature-name]

## Execution Batches

### Batch 1 (Independent Tasks)

- Task 1.1: [Title]
- Task 1.3: [Title]
- Task 2.2: [Title]

### Batch 2 (After Batch 1)

- Task 1.2: [Title] (depends on 1.1)
- Task 2.1: [Title] (depends on 1.1, 1.2)

### Batch 3 (After Batch 2)

- Task 2.3: [Title] (depends on 2.1, 2.2)
- Task 3.1: [Title] (depends on 2.1)

## Summary

- Total Tasks: [count]
- Total Batches: [count]
- Max Parallelism: [largest batch size]

## Next Steps

Remove --dry-run flag to execute the plan.
```

**`--team --dry-run`** — also print the team name and per-batch teammate roster:

```
Team name:    impl-<sanitized-feature-name>
Total tasks:  <N>  (across <M> batches, max parallel width <X>)
Dependencies: <K edges>  (from the parsed Depends on annotations)

Batch 1: <comma-separated task IDs>
Batch 2: <comma-separated task IDs>  (depends on Batch 1)
...
Batch M: <comma-separated task IDs>  (depends on Batch M-1)

Per-batch teammate roster:
  Batch 1:
    - <task-id-1>  subagent_type=implementor  task=<short>
    - <task-id-2>  subagent_type=implementor  task=<short>
  ...
```

Do **not** call `TeamCreate`, `TaskCreate`, `Agent`, `Task`, `SendMessage`, or `TeamDelete` in dry-run mode. **STOP HERE**.

### Step 8: Branch on `TEAM_FLAG`

- `TEAM_FLAG=false` → **Path A — Standalone sub-agent batches** (default).
- `TEAM_FLAG=true` → **Path B — Agent team batches**.

---

### Path A — Standalone Sub-Agent Batches (default)

See `~/.agents/ycc-shared/references/standalone-dispatch.md` for the full standalone-dispatch contract (`Task` vs `Agent`+team, anti-patterns, backstop policy). Standalone batches dispatch via the blocking `Task` tool — never background, poll, or sleep waiting on a result; the sub-agent's report is already in hand when the `Task` call returns.

Read the agent task prompt template once before the loop:

```bash
cat ~/.agents/skills/implement-plan/templates/agent-task-prompt.md
```

For each batch of ready tasks, in order:

**CRITICAL**: Deploy all agents in the batch in a **SINGLE message** with **MULTIPLE `Task` tool calls**.

#### Path A — Task spawn

For each task in the batch, deploy an implementor with:

| Field         | Value                                      |
| ------------- | ------------------------------------------ |
| subagent_type | `implementor`                          |
| description   | "Implement [Task ID]: [Title]"             |
| prompt        | Use template with task details substituted |

No `team_name`, no `name`, no `run_in_background`, no `TaskCreate` — standalone `Task` semantics. In the normal case the call blocks and returns the implementor's full report inline. If a batch doesn't return inline (async fallback), don't `sleep`-loop or poll waiting on it — yield/end the turn so the completion notification can flush, then resume.

**When `WORKTREE_ACTIVE=true`**, include in the `prompt` for every task in the batch (parallel and sequential):

```
Working directory: ${WT_PARENT_PATH}
All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.
```

**When `WORKTREE_ACTIVE=false` (`--no-worktree`)**, include the prepared current checkout instead:

```
Working directory: ${REPO_ROOT}
All parallel agents in this batch share the current feature branch; batching guarantees no two agents touch the same file.
```

Do **not** pass `isolation: "worktree"` here. Tool-side worktree isolation creates a distinct harness worktree per agent, which is exactly the behavior this migration is removing. Use the shared `Working directory:` line only. On **Codex / opencode**, that prompt line is likewise sufficient. On **Cursor**, emit a warning and print the `git worktree add` command for the user to run; do not auto-create.

#### Task Requirements (Path A)

Each implementor agent must:

1. **Read context first**:
   - `docs/plans/[feature-name]/parallel-plan.md`
   - `docs/plans/[feature-name]/shared.md`
   - Files listed in "READ THESE BEFORE TASK"

2. **Implement the specific task**:
   - Create files listed in "Files to Create"
   - Modify files listed in "Files to Modify"
   - Follow the instructions exactly

3. **Validate changes**:
   - Check for linting errors on modified files
   - Ensure code compiles/parses correctly

4. **Return summary**:
   - List of files created
   - List of files modified
   - Any issues encountered

#### Process Batch Results (Path A)

After each batch completes:

1. **Update todos**: Mark completed tasks as `completed`
2. **Review agent outputs**: Check for errors or issues
3. **Log batch completion** — Print to the transcript: `[done] Batch BN: K tasks — complete` (the same marker Path B emits at B.4 step 5, so a `/goal` loop can observe per-batch progress regardless of dispatch path — see `## /goal pairing`)
4. **Identify next batch**: Find tasks whose dependencies are now satisfied
5. **Handle failures**: If a task failed, note it and continue with independent tasks

#### Repeat Until Complete (Path A)

```
While tasks remain:
  1. Find tasks where all dependencies are completed
  2. Deploy agents for those tasks in parallel (single message, multiple Task calls)
  3. Wait for batch to complete
  4. Validate in the execution tree: `$WT_PARENT_PATH` when `WORKTREE_ACTIVE=true`, otherwise the prepared current-checkout feature branch
  5. Update task status
  6. Identify next batch
```

---

### Path B — Agent Team Batches (`--team`)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path B you MUST follow the agent-team lifecycle. Do NOT mix standalone sub-agents
> with team dispatch. Every `Agent` call below MUST include `team_name=` AND `name=`.
>
> 1. `TeamCreate` ONCE at the start (single team across all batches)
> 2. `TaskCreate` for **every task across all batches** up front, with `addBlockedBy`
>    wiring the dependency graph from the plan's `Depends on` annotations
> 3. Per batch: spawn teammates (single message, multiple `Agent` calls with
>    `team_name=` + `name=`)
> 4. `TaskList` to monitor batch completion
> 5. `SendMessage({type:"shutdown_request"})` to all teammates of completed batch
>    BEFORE spawning next batch
> 6. `TeamDelete` ONCE after final batch (or on abort)
>
> If `TeamCreate` or up-front `TaskCreate` fails, abort the skill. Refer to
> `~/.agents/ycc-shared/references/agent-team-dispatch.md`
> for the full lifecycle contract.

#### B.1 Build the team name

Sanitize the feature name (lowercase, replace non-alphanumeric with `-`, collapse runs, trim, cap at **20 chars**, fall back to `untitled` if empty). Team name: `impl-<sanitized-feature-name>`.

#### B.2 Create the team

```
TeamCreate: team_name="impl-<sanitized-feature-name>", description="implement-plan team for: <feature-name>"
```

On failure, abort.

#### B.3 Register ALL tasks up front with the dependency graph

For **every task across all batches** in the parsed task list:

```
TaskCreate: subject="<task-id>: <task title>", description="<full spec — files to read, files to create, files to modify, instructions>"
```

Then wire dependencies from the Phase 1 Step 4 graph — for each task `T` with `Depends on [X, Y, Z]`:

```
TaskUpdate: taskId="<T-id>", addBlockedBy=["<X-id>", "<Y-id>", "<Z-id>"]
```

This populates the shared task graph **once**, not per batch. Subsequent batches can read `TaskList` to confirm prerequisites are complete.

If any `TaskCreate` or `TaskUpdate` fails → `TeamDelete`, then abort.

#### B.4 Per-batch loop

Read the agent task prompt template once:

```bash
cat ~/.agents/skills/implement-plan/templates/agent-task-prompt.md
```

For each batch `B1, B2, ... BN` in dependency order, follow the ordering mandated by
`agent-team-dispatch.md §7.1` when `WORKTREE_ACTIVE=true`:

1. **Identify batch tasks** — All tasks whose dependencies are now satisfied and whose `TaskList` status is still pending.

2. **Spawn batch teammates** — Single message, multiple `Agent` tool calls, one per task in the batch. Every call MUST include:
   - `team_name`: `"impl-<sanitized-feature-name>"`
   - `name`: the task ID (e.g., `"1.1"`, `"2.3"`) — must match the `TaskCreate` subject prefix
   - `subagent_type`: `"implementor"`
   - `description`: `"Implement [Task ID]: [Title]"`
   - `prompt`: template-filled task spec. Include a directive that the agent must read the files listed in "READ THESE BEFORE TASK" before writing code, must validate its own modified files, and must call `TaskUpdate` to mark its task complete.

   **(WORKTREE_ACTIVE)** include in every teammate's `prompt` (parallel and sequential):

   ```
   Working directory: ${WT_PARENT_PATH}
   All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.
   ```

   **(`--no-worktree`)** include the prepared current checkout instead:

   ```
   Working directory: ${REPO_ROOT}
   All parallel agents in this batch share the current feature branch; batching guarantees no two agents touch the same file.
   ```

   Do **not** pass `isolation: "worktree"` here. Tool-side worktree isolation creates a distinct harness worktree per teammate, which breaks the single-worktree contract. On **Codex / opencode**, the `Working directory:` line in the prompt is sufficient. On **Cursor**, emit a warning + manual `git worktree add` command.

3. **Wait for batch completion via `TaskList`** — poll until all tasks in this batch are `completed`. If a teammate messages with an issue, respond via `SendMessage` with guidance.

4. **Shut down completed-batch teammates** — Send to every teammate of the just-completed batch:

   ```
   SendMessage(to="<task-id>", message={type:"shutdown_request"})
   ```

   Wait for shutdowns to complete before proceeding to the next batch.

5. **Track progress** — Log: `[done] Batch BN: K tasks — complete`

#### B.5 Failure handling

If a teammate fails:

- **Do NOT auto-retry** — parallel failures often indicate file conflicts or missing dependencies between supposedly-independent tasks.
- **Do NOT skip the failing batch** — tasks in later batches may depend on it.
- Use `AskUserQuestion` to ask the user: _"Batch {BN} had failures. Choose: (1) fix manually and resume, (2) switch to sequential standalone sub-agents for remaining batches, (3) abort."_
- If the user chooses (2) or (3), send `SendMessage(shutdown)` to all active teammates, then `TeamDelete` before proceeding.
- If `WORKTREE_ACTIVE=true` and the run aborts mid-batch, the feature worktree at `<repo-root>/.claude/worktrees/<repo>-<feature>/` survives and can be inspected or cleaned up manually.

#### B.6 After all batches complete

`TeamDelete` once. Proceed to Phase 4.

---

## Phase 4: Final Verification & Summary

### Step 9: Verify Implementation

After all tasks complete:

1. **Check for lint errors**: Run linting on all modified files and **print the outcome to the transcript** (zero errors, or the list of errors). Step 10's `LINT_PASS` signal is derived from this printed outcome — the `/goal` evaluator only reads transcript text, never the linter's exit state.
2. **Verify file creation**: Ensure all "Files to Create" exist
3. **Review changes**: Quick sanity check of modifications

### Step 10: Display Summary

**When `WORKTREE_ACTIVE=true`**, call `list-worktrees.sh` first and capture its output
for inclusion in the report:

```bash
bash ~/.agents/ycc-shared/scripts/list-worktrees.sh \
  "${WT_REPO_NAME}" "${WT_FEATURE_SLUG}"
```

Provide completion summary:

```markdown
# Implementation Complete

## Feature

[feature-name]

## Execution Mode

[Standalone sub-agents | Agent team (team: impl-<name>)]

## Execution Summary

- **Total Tasks**: [count]
- **Completed**: [count]
- **Failed**: [count]
- **Batches Executed**: [count]

## Files Changed

### Created

- /path/to/new/file.ext
- /path/to/another/file.ext

### Modified

- /path/to/existing/file.ext
- /path/to/another/existing/file.ext

## Task Results

### Batch 1

- [x] Task 1.1: [Title] - Success
- [x] Task 1.3: [Title] - Success

### Batch 2

- [x] Task 1.2: [Title] - Success
- [x] Task 2.1: [Title] - Success

## Issues Encountered

[List any problems or warnings]

## Worktree Status ← include this section only when WORKTREE_ACTIVE=true

[Output of list-worktrees.sh]

> The parent worktree at `<repo-root>/.claude/worktrees/[repo]-[feature]/` survives for inspection
> and PR creation. When you are done, run:
>
> git worktree remove <repo-root>/.claude/worktrees/[repo]-[feature]/
> git branch -d feat/[feature]

## Next Steps

1. Review the changes in your editor
2. Run tests to verify functionality
3. Commit the changes when satisfied
4. **Optional**: Generate implementation report:

/code-report [feature-name]

## Goal Signals (machine-readable — printed verbatim for /goal)

ALL_BATCHES_DONE: PASS
FILES_CHANGED_NONEMPTY: PASS
LINT_PASS: PASS
```

Print every signal verbatim as the last lines of the completion summary. Use `PASS` only
when the matching criterion in `## Success Criteria` is met; otherwise `FAIL` (for example
`FILES_CHANGED_NONEMPTY: FAIL` when the "Files Changed" section enumerated no files).

---

## Quality Standards

### Batch Execution Checklist

Each batch must:

- [ ] Deploy all ready tasks in parallel (single message, multiple `Task` calls in Path A; multiple `Agent` calls with `team_name=` in Path B)
- [ ] Wait for all agents to complete before next batch
- [ ] Update todo (and in Path B, TaskList) status after completion
- [ ] Handle failures gracefully
- [ ] In Path B: shut down completed-batch teammates before spawning the next batch

### Agent Quality Checklist

Each agent must:

- [ ] Read all required context files first
- [ ] Implement only the assigned task
- [ ] Validate changes before returning
- [ ] Return clear summary of changes
- [ ] In Path B: call `TaskUpdate` to mark its own task complete

### Overall Quality Checklist

The implementation must:

- [ ] Complete all tasks in the plan
- [ ] Respect dependency ordering
- [ ] Maximize parallel execution
- [ ] Report any failures clearly

---

## Monorepo Support

The skill automatically detects and uses the correct plans directory in monorepo setups.

### Default Behavior

- Plans are read from the **git repository root** in `docs/plans/`
- Running the skill from any subdirectory (e.g., `packages/app1/`) will still read plans from the root

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

With `scope: local`, plans are read from the local `docs/plans/` instead of the root.

### Example: Monorepo Structure

```
monorepo/
  .plans-config          # plans_dir: docs/plans
  docs/plans/            # Centralized plans (default)
    feature-a/
      shared.md
      parallel-plan.md   # Read by this skill
  packages/
    app1/
    app2/
```

Running `/implement-plan feature-a` from anywhere executes `monorepo/docs/plans/feature-a/parallel-plan.md`.

---

## Important Notes

- **You are the orchestrator** — coordinate agents, don't implement yourself
- **Parallelism is the baseline** — every batch dispatches concurrently regardless of path
- **Default dispatch is standalone sub-agents** — `--team` is an opt-in for shared task-graph observability in Claude Code
- **Deploy in batches** — single message with multiple `Task` calls per batch (Path A) or `Agent` calls with `team_name=` per batch (Path B)
- **Respect dependencies** — never start a task before its dependencies complete
- **Track progress** — update todos (and in Path B, `TaskList`) as tasks complete
- **Handle failures** — continue with independent tasks if one fails (Path A); escalate to the user via `AskUserQuestion` (Path B)
- **Monorepo aware** — automatically resolves correct plans directory

---

## Success Criteria

- **ALL_BATCHES_DONE**: Every batch printed its `[done] Batch BN: K tasks — complete` marker and no batch was left unprocessed.
- **FILES_CHANGED_NONEMPTY**: The Phase 4 Step 10 "Files Changed" section enumerates at least one created or modified file.
- **LINT_PASS**: Step 9 linting printed zero errors across all modified files.

These keys are emitted verbatim in the Phase 4 Step 10 "Goal Signals" block so a `/goal`
evaluator can observe completion from the transcript.

---

## /goal pairing

Pair this skill with the `/goal` session directive to loop the batch executor to completion
without re-prompting between batches or after the lint pass. Supply an explicit done
condition that references the Phase 4 Step 10 Goal Signals block rather than file paths.

Recommended condition template:

```
/goal Execute the parallel plan at docs/plans/<feature>/parallel-plan.md using the
implement-plan workflow, continuing through every batch and the Phase 4 lint pass
without returning control to me. Done when the transcript shows the Phase 4
"# Implementation Complete" output followed by all three Goal Signals printed verbatim —
ALL_BATCHES_DONE: PASS, FILES_CHANGED_NONEMPTY: PASS, LINT_PASS: PASS. If any signal prints
FAIL, keep fixing and re-running until all three are PASS. Stop after 25 turns if not
achieved.
```

The transcript-output contract and shared caveats (worktree cwd, interactive failure
prompts, platform availability) live in the shared reference — read it before relying on a
`/goal` loop:

```
~/.agents/ycc-shared/references/goal-pairing.md
```

---

## Agent Team Lifecycle Reference

For Path B's team lifecycle contract (sanitization, shutdown sequence, failure policy,
multi-batch reuse pattern), refer to:

```
~/.agents/ycc-shared/references/agent-team-dispatch.md
```
