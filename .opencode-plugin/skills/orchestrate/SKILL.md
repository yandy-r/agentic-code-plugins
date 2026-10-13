---
name: orchestrate
description: Coordinates specialized agents in dependency-resolved batches. Use when
  delegating a complex task, splitting independent implementation work, or coordinating
  multiple specialists.
---

# Multi-Agent Orchestration Skill

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.

You are an orchestration expert coordinating multiple specialized agents to accomplish complex tasks. **Your role is to coordinate agents, not do the work yourself.** **Operational context:** Worktree isolation is on by default; all parallel and sequential agents share one feature worktree. --no-worktree runs in the current checkout. Standalone sub-agents are default.

Parallelism is the baseline of this skill — every batch's tasks dispatch concurrently. The only choice is **how** the implementor agents are dispatched:

- **Standalone sub-agents** (default) — plain native `subagent` calls per batch, no shared task list. Works in opencode, Cursor, and Codex.

## Current Task

**Orchestrating**: `$ARGUMENTS`

Parse flags first, then treat the remainder as the task description:

- `--plan-only` — Create orchestration plan file at `docs/orchestration/[sanitized-task].md` without execution. When worktree mode is active, the plan gains a `## Worktree Setup` section.
- `--sequential` — Force sequential execution (single-task batches, for tightly dependent tasks). When worktree mode is active, all sequential tasks run in the single feature worktree.
- `--worktree` — (legacy — now default; safe to omit) Accepted as a silent no-op. Worktree isolation is on by default; this flag matches the new default and has no additional effect.
- `--no-worktree` — Force worktree mode **OFF** regardless of task structure. All tasks run directly in the current checkout; no feature worktree is created.
- `<task-description>`: The complex task to orchestrate (required, can be multi-word).

Strip flags from `$ARGUMENTS` and set ``, `DRY_RUN=true|false`, `PLAN_ONLY=true|false`, `SEQUENTIAL=true|false`, `WORKTREE_MODE=true|false`. Join the remaining non-flag tokens into `TASK_DESCRIPTION`.


If no task description is provided after stripping flags, abort with usage instructions:

```
Usage: /orchestrate [--dry-run] [--plan-only] [--sequential] [--worktree] [--no-worktree] <task-description>

Examples:
  /orchestrate "Implement user authentication with tests and docs"
    # default: all parallel and sequential tasks share one feature worktree

    # agent-team dispatch (worktree still on by default for parallel tasks)

  /orchestrate --dry-run "Debug payment processing failure"
  /orchestrate --plan-only "Refactor database layer"
  /orchestrate --sequential "Migrate legacy config"

  /orchestrate --no-worktree "Refactor the auth middleware"
    # opt out of worktree isolation; all tasks run in the current checkout

    # agent-team dispatch without worktrees
```



---

## Phase 0: Task Analysis

### Step 1: Parse Task Description

Extract the task description from `$ARGUMENTS` (everything before any flags).

Run the task analysis script:

```bash
~/.config/opencode/skills/orchestrate/scripts/analyze-task.sh "$TASK_DESCRIPTION"
```

The script provides:

- Task complexity estimate
- Suggested decomposition approach
- Potential agent types needed
- Recommended execution mode (parallel vs sequential)

### Step 2: Load Agent Catalog

Read the complete agent catalog:

```bash
cat ~/.config/opencode/skills/orchestrate/references/agent-catalog.md
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
cat ~/.config/opencode/skills/orchestrate/references/task-breakdown.md
```

This template provides patterns for breaking down tasks by feature area, technical layer, cross-cutting concerns, and dependencies.

### Step 5: Register Subtasks

Use standalone execution:

- `STANDALONE_MODE=true` → **Path A (default)**: register subtasks locally via `the todo tracker`. No team is created. Skip to Step 6.

#### Path A — Local todos (default)

Using **the todo tracker**, register each subtask as a todo item:

```
- id: "subtask-1", content: "[Subtask 1 title] — agent: [agent-type] — depends: [none/list]", status: "pending"
- id: "subtask-2", content: "[Subtask 2 title] — agent: [agent-type] — depends: [subtask-1]", status: "pending"
```

Track batch completion in-context after each batch's native `subagent` calls return.

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
if [[ -f "~/.config/opencode/skills/orchestrate/scripts/validate-agents.sh" ]]; then
  ~/.config/opencode/skills/orchestrate/scripts/validate-agents.sh
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
cat ~/.config/opencode/skills/orchestrate/references/agent-prompts.md
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
FEATURE_BRANCH=$(bash ~/.config/opencode/shared/scripts/prepare-feature-branch.sh "${FEATURE_SLUG}")
```

See `~/.config/opencode/shared/references/branch-prep.md` for the helper's behavior and exit-code contract. Skip both this call and the worktree setup below when `DRY_RUN=true` or `PLAN_ONLY=true`.

When `WORKTREE_MODE=false` (`--no-worktree`), skip parent worktree setup after branch preparation.

### When `WORKTREE_MODE=true` and `DRY_RUN=false` and `PLAN_ONLY=false`

Determine the repository name from the current directory (`basename $(git rev-parse --show-toplevel)`). Use the `FEATURE_SLUG` derived during flag parsing.

Create the parent worktree **once**, before any batch dispatches:

```bash
bash ~/.config/opencode/shared/scripts/setup-worktree.sh parent <repo-name> <FEATURE_SLUG>
```

Store the echoed path as `PARENT_WORKTREE_PATH`. All parallel and sequential agents in every batch share this path.

When `WORKTREE_MODE=true` and `SEQUENTIAL=true`: sequential tasks run in `PARENT_WORKTREE_PATH` — the same single worktree used for parallel tasks.

When `WORKTREE_MODE=true` and `DRY_RUN=true`: skip all script calls. Instead, compute the expected parent path as `<repo-root>/.config/opencode/worktrees/<repo>-<FEATURE_SLUG>/` and proceed to Phase 3 to include it in the dry-run output.

When `WORKTREE_MODE=true` and `PLAN_ONLY=true`: skip all script calls. Include the worktree annotation in the written plan (see Phase 3).

---

## Phase 3: Dry Run Check

### Step 10: Check for Dry Run or Plan-Only Mode

If `--dry-run` is present:


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




```
Worktree:   feature=<repo-root>/.config/opencode/worktrees/<repo>-<FEATURE_SLUG>/  (all subtasks)
```

Do not dispatch any `subagent` calls in dry-run mode.

If `--plan-only` is present:

- Create the plan as `docs/orchestration/[sanitized-task-name].md`
- Save the complete orchestration plan for later execution
- Display the plan location and summary
- No team cleanup required — team creation is skipped entirely in plan-only mode
- When `WORKTREE_MODE=true`: include a `## Worktree Setup` section in the written plan (immediately after frontmatter, before Batch 1). Follow the annotation format in `.opencode-plugin/skills/_shared/references/worktree-strategy.md` §2: list only the parent path. Do NOT add child paths or a `**Children**:` list.
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

Use standalone execution:

- `STANDALONE_MODE=true` → **Path A — Standalone sub-agent batches** (default).

---

#### Path A — Standalone Sub-Agent Batches (default)

See `~/.config/opencode/shared/references/standalone-dispatch.md` for the full native standalone dispatch, result, and failure contract this path follows.

For each batch, do the following **in order**:

**1. Build the per-batch agent list** — determine each subtask's name, agent type, focus, and deliverables.

**2. Spawn ALL batch agents in a SINGLE message** using multiple native `subagent` calls with `background=false`. Use only `agent`, `description`, and the complete `prompt`; validate every candidate report and owned artifact before accepting it.

When `WORKTREE_MODE=true`, each native subagent call includes `Working directory: <PARENT_WORKTREE_PATH>` in the prompt. Do **not** pass `isolation: "worktree"` here: that creates a distinct harness worktree per agent and breaks the single-worktree contract. Add a coordination note: `All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.`:

```
subagent(
  agent = "nodejs-backend-architect",
  description = "Implement auth system",
  prompt = "Working directory: <repo-root>/.config/opencode/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path A coordination block]",
  background = false
)
subagent(
  agent = "test-strategy-planner",
  description = "Create auth test plan",
  prompt = "Working directory: <repo-root>/.config/opencode/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path A coordination block]",
  background = false
)
subagent(
  agent = "documentation-writer",
  description = "Document auth API",
  prompt = "Working directory: <repo-root>/.config/opencode/worktrees/<repo>-<FEATURE_SLUG>/\nAll parallel agents in this batch share this path; batching guarantees no two agents touch the same file.\n\n[substituted template with Path A coordination block]",
  background = false
)
```

When `WORKTREE_MODE=false` (--no-worktree), omit the `Working directory:` line — standard Path A semantics.

**4. Wait for batch completion** — every native `subagent` call sets `background=false`. Process the batch after all calls return candidate reports, then validate each report and owned artifact before marking completion.

**5. Process results** — review each returned summary. Update the corresponding `the todo tracker` items to `completed`.

**6. Handle failures** — if a subtask fails, note the failure, determine if dependent subtasks can proceed, and continue with independent subtasks.

**7. Identify next batch** — scan the `the todo tracker` list for pending subtasks whose dependencies are now all `completed`. If subtasks remain but none are unblocked, report deadlock and stop.

Foreground child calls require no separate shutdown; every child has already returned its candidate report.

---

### Step 13: Repeat Until Complete

Repeat Step 12 for each subsequent batch until all subtasks are completed or no more can be unblocked.

---

## Phase 5: Result Synthesis & Summary

### Step 14: Consolidate Agent Outputs

Run the summarization script:

```bash
~/.config/opencode/skills/orchestrate/scripts/summarize-results.sh
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

### Step 17: Final Summary

When `WORKTREE_MODE=true`, call `list-worktrees.sh` and append its output to the summary:

```bash
bash ~/.config/opencode/shared/scripts/list-worktrees.sh <repo-name> <FEATURE_SLUG>
```

This prints the feature worktree path, its branch, and the `git worktree remove` command for manual cleanup. The worktree survives until manually removed — there are no child worktrees to clean up.

Provide comprehensive completion summary:

```markdown
# Orchestration Complete: [Task]

## Execution Mode

[Standalone sub-agents]


- Team: orch-<sanitized-task>
- Total sub-agents spawned: [count across all batches]
- Batches executed: [count]
- Inter-agent sharing: Enabled (sub-agents shared findings within batches via re-dispatch the affected sub-agent with the needed guidance)

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

- [ ] Parse flags and set ``, `DRY_RUN`, `PLAN_ONLY`, `SEQUENTIAL`, `WORKTREE_MODE` before any side effects (default: `WORKTREE_MODE=true` unless `--no-worktree` is passed)
- [ ] Deploy independent tasks in parallel (single message, multiple native `subagent` calls)
- [ ] Respect dependency ordering between batches
- [ ] Track progress via `the todo tracker` (Path A) or `the todo tracker` (Path B)
- [ ] Handle failures gracefully
- [ ] Synthesize results on completion
- [ ] Verify integration between agent outputs

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
5. **Track Progress**: `the todo tracker` in Path A, `the todo tracker` in Path B
6. **Synthesize Results**: Integrate outputs into coherent whole

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
- **Deploy in batches** — single message with multiple native `subagent` calls per batch
- **Respect dependencies** — never start a subtask before its dependencies complete
- **Handle failures** — continue with independent subtasks if one fails
- **Track progress** — `the todo tracker` updates (Path A) or `the todo tracker` (Path B)
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
