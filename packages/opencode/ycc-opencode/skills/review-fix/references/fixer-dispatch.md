# Fixer Dispatch

## Contents

- Fixer prompt (all paths)
- Path A — sequential
- Path B — parallel standalone batches
- Handling failures

## Fixer prompt (all paths)

Use `review-fixer` with its Finding spec: Shape A for one finding, Shape B
for a same-file group sorted by line descending. Include the full ID, severity,
file, line, category, description, and unchanged Suggested fix, plus:

```
SOURCE REVIEW FILE: <absolute artifact path>
PROJECT TYPE-CHECK COMMAND: <detected command or explicit SKIP (...)>
```

Agents edit only their assigned source files; orchestrator alone updates source
artifact statuses. When worktree active, append `Working directory: $PARENT_PATH`
and coordination note: other agents share this directory; do not run destructive
git commands (`reset`, `clean`, `checkout`). Do not pass `isolation: "worktree"`.

### Path A — Sequential Execution (default)

Process batches in order; within a batch, one finding or same-file group at a
time. For each: dispatch a single `review-fixer` (Shape A or B), wait for
its report, then `Edit` the finding's `**Status**: Open` line to `Fixed` on
`STATUS: Fixed` or `Failed` on `STATUS: Failed`. Track `[done] F042 — Fixed` /
`[failed] F043 — Failed: <blocker>` in todos. Continue after a failure so the
user gets the full picture. In worktree mode run the between-batch validation
inside `${PARENT_PATH}` before advancing to the next severity. Path A has no
stop-and-ask gate: between-batch validation is diagnostic here and never
pauses the pipeline; the fail-stop gate applies to Path B and Path C only.

### Path B — Parallel Sub-Agent Execution (`PARALLEL_MODE=true`)

- When `WORKTREE_ACTIVE=true`: batches are still severity-ordered. Dispatch every parallel review-fixer with `Working directory: ${PARENT_PATH}` only. Do **not** add `isolation: "worktree"`. Between-batch validation runs once in `${PARENT_PATH}` before advancing to the next severity. No fan-in merge.

Process batches sequentially; within each batch, dispatch all review-fixer agents as standalone sub-agents in parallel. Dispatch per the contract in `{{package-root}}/shared/references/standalone-dispatch.md`.

For each batch:

1. **Dispatch review-fixer agents in parallel** — Use a **single message** with **multiple native `subagent` calls**, one per finding or same-file group in the batch:
   - `agent`: `"review-fixer"`
   - `description`: e.g., `"Fix F042: missing null check in payments.ts"`
   - `prompt`: The Finding spec (Shape A or Shape B) plus `SOURCE REVIEW FILE` and `PROJECT TYPE-CHECK COMMAND`

2. **Wait for all agents in the batch to complete** before proceeding.

3. **Collect results and update the review file**:
   - For each `STATUS: Fixed` → `Edit` the review file to update that finding's `**Status**: Open` → `**Status**: Fixed`
   - For each `STATUS: Failed` → `Edit` the review file to update that finding's `**Status**: Open` → `**Status**: Failed`

4. **Between-batch validation (Levels 1 + 2)** — After each batch (except the last), run:

   ```bash
   $TYPECHECK_CMD
   $TEST_CMD
   ```

   - If both pass: log `[done] Batch N: K fixes — validation pass` and proceed.
   - If either fails: **stop** the parallel pipeline. Report which batch broke validation. Use `ask the user` to ask:
     - "Resume sequentially from next batch"
     - "Abort and leave current state as-is"
     - "Skip remaining findings and jump to Phase 5 (verify + report)"

5. **Track progress** in todos per batch, not per finding.

### Handling failures

If a `review-fixer` agent returns `STATUS: Failed`:

- **Do not retry** the same fix automatically. The agent already judged the Suggested fix to be incompatible.
- Mark the finding as `Failed` in the review file.
- Include the agent's `BLOCKER` and `RECOMMENDATION` in the fix report.
- Continue with remaining findings.
