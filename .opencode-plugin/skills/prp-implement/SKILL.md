---
name: prp-implement
description: Executes PRP plan files with validation loops, reports, and archiving.
  Use when implementing a .plan.md file, executing a PRP plan, or running parallel
  PRP tasks.
---

# PRP Implement

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.

Execute a plan file step-by-step with continuous validation. Every change is verified immediately — never accumulate broken state. **Operational context:** Detect the package manager and prepare the Git branch; validate static, unit, build, integration, and edge cases, write docs/prps/reports/, and archive the plan. Detect parallel-capable plans and prompt for sequential or parallel execution unless an execution flag selects the mode.

> Adapted from PRPs-agentic-eng by Wirasm. Part of the PRP workflow series.

**Core Philosophy**: Validation loops catch mistakes early. Run checks after every change. Fix issues immediately.

**Golden Rule**: If a validation fails, fix it before moving on. Never accumulate broken state.

---

## Phase 0 — DETECT

### Flag Parsing

Extract flags from `$ARGUMENTS` before treating the remainder as a plan path:

| Flag            | Effect                                                                                                                                                                                                                                                                                                                                             |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--parallel`    | Force parallel execution via **standalone sub-agents** when the plan is parallel-capable. Skips the interactive prompt. Falls back to sequential with a warning if the plan has no `Batches` section. Works in opencode, Cursor, and Codex.                                                                                                     |
| `--worktree`    | (legacy — now default; safe to omit) Accepted as a silent no-op. Worktree isolation is on by default; this flag matches the new default and has no additional effect.                                                                                                                                                                              |
| `--no-worktree` | Force worktree mode **OFF** regardless of plan annotations. Tasks run directly in the current checkout. No feature worktree is created.                                                                                                                                                                                                            |

Strip the flags from `$ARGUMENTS` and set `PARALLEL_FLAG=true|false`, ``, `WORKTREE_MODE=true|false`, `DRY_RUN=true|false`. The remaining text is the plan file path.

**Validation**:

- `--no-worktree` combines freely with `--parallel`. No exclusivity rules.
- `--worktree` and `--no-worktree` together → abort with: `--worktree and --no-worktree are mutually exclusive. Use --no-worktree to opt out of the default.`


### Package Manager Detection

| File Exists                            | Package Manager | Runner                  |
| -------------------------------------- | --------------- | ----------------------- |
| `bun.lockb`                            | bun             | `bun run`               |
| `pnpm-lock.yaml`                       | pnpm            | `pnpm run`              |
| `yarn.lock`                            | yarn            | `yarn`                  |
| `package-lock.json`                    | npm             | `npm run`               |
| `pyproject.toml` or `requirements.txt` | uv / pip        | `uv run` or `python -m` |
| `Cargo.toml`                           | cargo           | `cargo`                 |
| `go.mod`                               | go              | `go`                    |

### Validation Scripts

Check `package.json` (or equivalent) for available scripts:

```bash
cat package.json | grep -A 20 '"scripts"'
```

Note available commands for: type-check, lint, test, build.

---

## Phase 1 — LOAD

Read the plan file:

```bash
cat "$ARGUMENTS"
```

Extract these sections from the plan:

- **Summary** — What is being built
- **Patterns to Mirror** — Code conventions to follow
- **Files to Change** — What to create or modify
- **Step-by-Step Tasks** — Implementation sequence
- **Validation Commands** — How to verify correctness
- **Acceptance Criteria** — Definition of done

If the file doesn't exist or isn't a valid plan:

```
Error: Plan file not found or invalid.
Run /prp-plan <feature-description> to create a plan first.
```

### Parallel-Capable Detection

After reading the plan, check whether it was written in parallel mode by looking for a `## Batches` section:

```bash
grep -c "^## Batches" "$PLAN_PATH" || echo 0
```

- **Count > 0** → Plan is **parallel-capable**. Parse the `Batches` table to extract batch ordering and `BATCH:` fields from tasks.
- **Count = 0** → Plan is **sequential only**.

### How Worktree Mode Is Decided

The decision follows a strict precedence order:

1. **`--no-worktree` present** → `WORKTREE_MODE=false`. Worktree isolation is forced off regardless of plan annotations. No feature worktree is created.
2. **Plan contains `## Worktree Setup`** → `WORKTREE_MODE=true`. The plan annotations are the source of truth; follow them exactly.
3. **Neither of the above** → `WORKTREE_MODE=true` **(new default — was false)**. Worktree isolation activates even when the plan has no annotations. The skill derives the single feature-worktree path from the plan name (see deduction rules below) and creates it using `setup-worktree.sh parent`.

`--worktree` is accepted as a silent no-op and matches the new default; it has no additional effect beyond what the default already provides.

### Worktree Detection

After reading the plan, scan for worktree annotations:

```bash
grep -c "^## Worktree Setup" "$PLAN_PATH" || echo 0
grep -c "^\- \*\*Worktree\*\*:" "$PLAN_PATH" || echo 0
```

**If `## Worktree Setup` is present**, extract:

- `WT_PARENT_PATH` — from the `**Parent**:` line inside that section (the path before any whitespace/comment)
- `WT_FEATURE_SLUG` — the segment after `<repo>-` in the parent path (e.g. `add-widget` from `<repo-root>/.config/opencode/worktrees/my-repo-add-widget/`)

Set `WORKTREE_ACTIVE=true` if the plan contains the `## Worktree Setup` section **OR** `WORKTREE_MODE=true` (default or explicitly passed).

**If `WORKTREE_MODE=true` but no `## Worktree Setup` section exists** (the default-on fallback), deduce paths:

- `WT_REPO_NAME` = `basename` of the git repository root (`git rev-parse --show-toplevel | xargs basename`)
- `WT_FEATURE_SLUG` = sanitized plan basename (strip `.plan.md`, lowercase, replace `[^a-z0-9-]` with `-`, collapse runs, truncate to 40 chars — same rules as the team-name sanitization but without the prefix and with a longer cap)
- `WT_PARENT_PATH` = `<repo-root>/.config/opencode/worktrees/${WT_REPO_NAME}-${WT_FEATURE_SLUG}/`

> Note: `WORKTREE_ACTIVE` only applies to parallel tasks. Sequential tasks always run in the parent worktree and are not affected by this flag.

### Execution Mode Decision

Decide between **Path A (Sequential)**, **Path B (Parallel sub-agents)** based on the flags and plan capability:

| Flags        | Parallel-capable plan | Action                                                                                                                                                                                                                                                     |
| ------------ | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--parallel` | Yes                   | Proceed with **Path B** (parallel sub-agent batch execution) — no prompt                                                                                                                                                                                   |
| `--parallel` | No                    | Warn: _"Plan has no `Batches` section — cannot run in parallel. Falling back to sequential execution."_ → **Path A**                                                                                                                                       |
| (none)       | Yes                   | Use `ask the user` to prompt: _"This plan is parallel-capable ({N} tasks in {M} batches, max width {X}). Run sequential / parallel sub-agents?"_. Accept user's choice → **Path A**, **Path B**.                            |
| (none)       | No                    | Proceed with **Path A** (sequential) — default, no prompt                                                                                                                                                                                                  |

Record the chosen mode as `EXECUTION_MODE=sequential|parallel|agent_team` for use in Phase 3.

**CHECKPOINT**: Plan loaded. All sections identified. Tasks extracted. Parallel capability detected. Execution mode chosen.

---

## Phase 2 — PREPARE

### Git State

```bash
git branch --show-current
git status --porcelain
```

### Branch Decision

Run the shared branch-prep helper **before any agent dispatch** so implementor agents inherit the right branch instead of `main`:

```bash
FEATURE_BRANCH=$(bash ~/.config/opencode/shared/scripts/prepare-feature-branch.sh \
  "${WT_FEATURE_SLUG}")
```

The script exits non-zero on failure and echoes the prepared branch name on success. **Do not skip it** — narrative-only branch instructions are how the original `--no-worktree` bug allowed agents to commit to `main`. See `~/.config/opencode/shared/references/branch-prep.md` for the helper's behavior and exit-code contract.

When `WORKTREE_ACTIVE=true`, run the helper first against the **main repo** (so `feat/<slug>` exists locally), then run the worktree setup step below — `setup-worktree.sh parent` will adopt the existing branch.

### Parent Worktree Setup (when `WORKTREE_ACTIVE=true`)

> **Invariant**: plan artifacts move into the worktree once; they never travel back. Never `cp`, `rsync`, or "sync" the plan file across trees — that's exactly the ambiguity this step exists to remove.

After the branch decision, create the parent worktree **once** before the first batch:

```bash
WT_PARENT_PATH=$(bash ~/.config/opencode/shared/scripts/setup-worktree.sh \
  parent "${WT_REPO_NAME}" "${WT_FEATURE_SLUG}")
```

This creates `<repo-root>/.config/opencode/worktrees/${WT_REPO_NAME}-${WT_FEATURE_SLUG}/` on branch `feat/${WT_FEATURE_SLUG}`, branching from the current HEAD. The call is idempotent — if the parent already exists on the expected branch it echoes the path and exits 0.

### Move Plan Into Worktree (when `WORKTREE_ACTIVE=true`)

Plan artifacts written by `prp-plan` are pre-commit and live in the **main checkout** when this skill starts. The first thing to do after the worktree exists is **move** them in — never copy, never sync:

```bash
PLAN_PATH=$(bash ~/.config/opencode/shared/scripts/move-plan-to-worktree.sh \
  "$ARGUMENTS" "$WT_PARENT_PATH")
```

After this step:

- `$PLAN_PATH` is the canonical plan location (inside the worktree). Use it for every later reference (validation, agent prompts, archive).
- The main checkout is clean — there is no plan file left behind in `docs/prps/plans/`.
- Companion artifacts (e.g. `docs/plans/<feature>/shared.md` from `plan-workflow`) can ride along by passing them as extra arguments to `move-plan-to-worktree.sh`.

All subsequent git operations and file writes in Phase 3 (validation, between-batch checks, the implementation report) run inside `$WT_PARENT_PATH`, not from the main repo root.

### Sync Remote

```bash
git pull --rebase origin $(git branch --show-current) 2>/dev/null || true
```

**CHECKPOINT**: On correct branch. Working tree ready. Remote synced. Parent worktree created (if `WORKTREE_ACTIVE=true`).

---

## Phase 3 — EXECUTE

Branch based on `EXECUTION_MODE` from Phase 1.

### Path A — Sequential Execution (`EXECUTION_MODE=sequential`)

Process each task from the plan sequentially.

#### Per-Task Loop

For each task in **Step-by-Step Tasks**:

1. **Read MIRROR reference** — Open the pattern file referenced in the task's MIRROR field. Understand the convention before writing code.
2. **Implement** — Write the code following the pattern exactly. Apply GOTCHA warnings. Use specified IMPORTS.
3. **Validate immediately** — After EVERY file change:

   ```bash
   # Run type-check (adjust command per project)
   [type-check command from Phase 0]
   ```

   If type-check fails → fix the error before moving to the next file.

4. **Track progress** — Log: `[done] Task N: [task name] — complete`

### Path B — Parallel Batch Execution (`EXECUTION_MODE=parallel`)

Process batches sequentially. Within each batch, dispatch one `implementor` agent per task in parallel.

#### Per-Batch Loop

For each batch `B1, B2, ... BN` in order (from the plan's `Batches` table):

1. **Identify batch tasks** — Extract all tasks with `BATCH: BN` from the Step-by-Step Tasks section.

2. **Dispatch implementor agents in parallel** — Use a **SINGLE message** with **MULTIPLE native `subagent` calls**, one per task in the batch. Each call:
   - `agent`: `"implementor"`
   - `description`: The task title (e.g., `"Task 1.1: add rate limiter middleware"`)
   - `prompt`: The complete task spec (ACTION, IMPLEMENT, MIRROR, IMPORTS, GOTCHA, VALIDATE) plus the relevant excerpt from the plan's **Patterns to Mirror** section. Include a directive that the agent must read the MIRROR source file before writing code and must run its own type-check on modified files before reporting complete.
   - **When `WORKTREE_ACTIVE=true`**: append `Working directory: ${WT_PARENT_PATH}` and `All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.` to every agent prompt (parallel and sequential). Do **not** request per-agent worktree isolation here: `Agent(isolation: "worktree")` creates distinct harness worktrees and breaks the single-worktree contract. The agent must treat `${WT_PARENT_PATH}` as its repo root for all Read / Write / Edit / Bash calls.

3. **Wait for all agents in the batch to complete** before proceeding.

4. **Between-batch validation (Levels 1 + 2)** — After each batch (including between-batches, not just at the end), run:

   ```bash
   # Level 1: Type-check — zero errors required
   [type-check command from Phase 0]

   # Level 2: Unit tests — affected area must be green
   [test command from Phase 0]
   ```

   - **If either fails**: **STOP** the parallel pipeline. Do NOT dispatch the next batch.
   - Report which batch failed and which type errors / test failures occurred.
   - Use `ask the user` to ask the user: _"Batch {BN} validation failed. Choose: (1) fix manually and resume from batch {BN+1}, (2) switch to sequential mode for remaining batches, (3) abort."_
   - Apply the user's choice.
   - When fixing and resuming, work within the same feature worktree at `${WT_PARENT_PATH}` — no child branches to merge or clean up.

5. **Track progress** — Log: `[done] Batch BN: K tasks — complete (type-check + tests pass)`

#### Handling Parallel Failures

If a batch fails validation:

- **Do NOT auto-retry** — parallel failures are often file conflicts or missing dependencies between supposedly-independent tasks, which won't resolve by retrying
- **Do NOT skip the failing batch** — tasks in later batches may depend on it
- Preserve all completed work; git state reflects whatever was successfully committed
- The user decides whether to resume, switch modes, or abort

#### After All Batches Complete

Proceed to **Phase 4 — VALIDATE** and run the full 5-level validation as normal. Between-batch validation only covered Levels 1 + 2; Phase 4 still runs Levels 3 (build), 4 (integration), and 5 (edge cases).

### Handling Deviations

If implementation must deviate from the plan:

- Note **WHAT** changed
- Note **WHY** it changed
- Continue with the corrected approach
- These deviations will be captured in the report

**CHECKPOINT**: All tasks executed. Deviations logged.

---

## Phase 4 — VALIDATE

Run all validation levels from the plan. Fix issues at each level before proceeding.

### Level 1: Static Analysis

```bash
# Type checking — zero errors required
[project type-check command]

# Linting — fix automatically where possible
[project lint command]
[project lint-fix command]
```

If lint errors remain after auto-fix, fix manually.

### Level 2: Unit Tests

Write tests for every new function (as specified in the plan's Testing Strategy).

```bash
[project test command for affected area]
```

- Every function needs at least one test
- Cover edge cases listed in the plan
- If a test fails → fix the implementation (not the test, unless the test is wrong)

### Level 3: Build Check

```bash
[project build command]
```

Build must succeed with zero errors.

### Level 4: Integration Testing (if applicable)

```bash
# Start server, run tests, stop server
[project dev server command] &
SERVER_PID=$!

# Wait for server to be ready (adjust port as needed)
SERVER_READY=0
for i in $(seq 1 30); do
  if curl -sf http://localhost:PORT/health >/dev/null 2>&1; then
    SERVER_READY=1
    break
  fi
  sleep 1
done

if [ "$SERVER_READY" -ne 1 ]; then
  kill "$SERVER_PID" 2>/dev/null || true
  echo "ERROR: Server failed to start within 30s" >&2
  exit 1
fi

[integration test command]
TEST_EXIT=$?

kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true

exit "$TEST_EXIT"
```

### Level 5: Edge Case Testing

Run through edge cases from the plan's Testing Strategy checklist.

**CHECKPOINT**: All 5 validation levels pass. Zero errors.

---

## Phase 5 — REPORT

### Create Implementation Report

```bash
mkdir -p docs/prps/reports
```

Write report to `docs/prps/reports/{plan-name}-report.md`:

```markdown
# Implementation Report: [Feature Name]

## Summary

[What was implemented]

## Assessment vs Reality

| Metric        | Predicted (Plan) | Actual         |
| ------------- | ---------------- | -------------- |
| Complexity    | [from plan]      | [actual]       |
| Confidence    | [from plan]      | [actual]       |
| Files Changed | [from plan]      | [actual count] |

## Tasks Completed

| #   | Task        | Status          | Notes               |
| --- | ----------- | --------------- | ------------------- |
| 1   | [task name] | [done] Complete |                     |
| 2   | [task name] | [done] Complete | Deviated — [reason] |

## Validation Results

| Level           | Status      | Notes           |
| --------------- | ----------- | --------------- |
| Static Analysis | [done] Pass |                 |
| Unit Tests      | [done] Pass | N tests written |
| Build           | [done] Pass |                 |
| Integration     | [done] Pass | or N/A          |
| Edge Cases      | [done] Pass |                 |

## Files Changed

| File           | Action  | Lines   |
| -------------- | ------- | ------- |
| `path/to/file` | CREATED | +N      |
| `path/to/file` | UPDATED | +N / -M |

## Deviations from Plan

[List any deviations with WHAT and WHY, or "None"]

## Issues Encountered

[List any problems and how they were resolved, or "None"]

## Tests Written

| Test File      | Tests   | Coverage       |
| -------------- | ------- | -------------- |
| `path/to/test` | N tests | [area covered] |

## Next Steps

- [ ] Code review via `/code-review`
- [ ] Create PR via `/prp-pr`
```

### Update PRD (if applicable)

If this implementation was for a PRD phase:

1. Update the phase status from `in-progress` to `complete`
2. Add report path as reference

### Archive Plan

Run inside `$WT_PARENT_PATH` (when `WORKTREE_ACTIVE=true`) so the archive lives next to the implementation report, not back in main. `$PLAN_PATH` is the relocated plan path set in Phase 2; if the run was `--no-worktree` it falls back to `$ARGUMENTS`.

```bash
PLAN_PATH="${PLAN_PATH:-$ARGUMENTS}"
mkdir -p "$(dirname -- "$PLAN_PATH")/completed"
mv "$PLAN_PATH" "$(dirname -- "$PLAN_PATH")/completed/"
```

### Worktree Summary (when `WORKTREE_ACTIVE=true`)

After archiving the plan, run:

```bash
bash ~/.config/opencode/shared/scripts/list-worktrees.sh \
  "${WT_REPO_NAME}" "${WT_FEATURE_SLUG}"
```

Include the full output (markdown table + cleanup commands) in the implementation report under a `## Worktree Summary` section. This shows the surviving parent worktree path, its branch, and the `git worktree remove` command for manual cleanup.

**CHECKPOINT**: Report created. PRD updated. Plan archived. Worktree summary captured (if applicable).

---

## Phase 6 — OUTPUT

Report to user:

```
## Implementation Complete

- **Plan**: [plan file path] → archived to completed/
- **Branch**: [current branch name]
- **Mode**: [Sequential | Parallel sub-agents (N batches, max width X)]
- **Status**: [done] All tasks complete

### Validation Summary

| Check       | Status               |
| ----------- | -------------------- |
| Type Check  | [done]               |
| Lint        | [done]               |
| Tests       | [done] (N written)   |
| Build       | [done]               |
| Integration | [done] or N/A        |

### Files Changed

- [N] files created, [M] files updated

### Deviations

[Summary or "None — implemented exactly as planned"]

### Artifacts

- Report: `docs/prps/reports/{name}-report.md`
- Archived Plan: `docs/prps/plans/completed/{name}.plan.md`

### PRD Progress (if applicable)

| Phase   | Status         |
| ------- | -------------- |
| Phase 1 | [done] Complete |
| Phase 2 | [next]         |
| ...     | ...            |

### Worktree Summary (if worktree mode was active)

[Output of `list-worktrees.sh <repo> <feature>` — surviving parent worktree path, branch, and cleanup commands]

> Run `git worktree remove <repo-root>/.config/opencode/worktrees/<repo>-<feature>/` after merging and pushing to clean up the parent worktree.

> Next step: Run `/prp-pr` to create a pull request, or `/code-review` to review changes first.

Print every signal verbatim. Use `PASS` only when the criterion in `## Success Criteria` is met; otherwise `FAIL`.

### Goal Signals (machine-readable — printed verbatim for /goal)

TASKS_COMPLETE: PASS
TYPES_PASS: PASS
LINT_PASS: PASS
TESTS_PASS: PASS
BUILD_PASS: PASS
REPORT_CREATED: PASS
PLAN_ARCHIVED: PASS
```

---

## Handling Failures

### Type Check Fails

1. Read the error message carefully
2. Fix the type error in the source file
3. Re-run type-check
4. Continue only when clean

### Tests Fail

1. Identify whether the bug is in the implementation or the test
2. Fix the root cause (usually the implementation)
3. Re-run tests
4. Continue only when green

### Lint Fails

1. Run auto-fix first
2. If errors remain, fix manually
3. Re-run lint
4. Continue only when clean

### Build Fails

1. Usually a type or import issue — check error message
2. Fix the offending file
3. Re-run build
4. Continue only when successful

### Integration Test Fails

1. Check server started correctly
2. Verify endpoint/route exists
3. Check request format matches expected
4. Fix and re-run

---

## Success Criteria

- **TASKS_COMPLETE**: All tasks from the plan executed
- **TYPES_PASS**: Zero type errors
- **LINT_PASS**: Zero lint errors
- **TESTS_PASS**: All tests green, new tests written
- **BUILD_PASS**: Build succeeds
- **REPORT_CREATED**: Implementation report saved
- **PLAN_ARCHIVED**: Plan moved to `docs/prps/plans/completed/`

These keys are emitted verbatim in the Phase 6 OUTPUT 'Goal Signals' block so a `/goal` evaluator can observe completion from the transcript.

---

## /goal pairing

Pair this skill with the `/goal` session directive for autonomous plan execution across phase CHECKPOINTs. Supply an explicit done condition that references the Phase 6 Goal Signals block rather than file paths.

Recommended condition template:

```
/goal Implement the plan at docs/prps/plans/<name>.plan.md using the prp-implement
workflow, continuing through every phase CHECKPOINT without returning control to me.
Done when the transcript shows the Phase 6 "## Implementation Complete" output followed
by all seven Goal Signals printed verbatim — TASKS_COMPLETE: PASS, TYPES_PASS: PASS,
LINT_PASS: PASS, TESTS_PASS: PASS, BUILD_PASS: PASS, REPORT_CREATED: PASS,
PLAN_ARCHIVED: PASS. If any signal prints FAIL, keep fixing and re-running validation
until all seven are PASS. Stop after 25 turns if not achieved.
```

The transcript-output contract and shared caveats (worktree cwd, interactive failure
prompts, platform availability) live in the shared reference — read it before relying on a
`/goal` loop:

```
~/.config/opencode/shared/references/goal-pairing.md
```

---

## Next Steps

- Run `/code-review` to review changes before committing
- Run `/prp-commit` to commit with a descriptive message
- Run `/prp-pr` to create a pull request
- Run `/prp-plan <next-phase>` if the PRD has more phases

---
