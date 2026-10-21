# Standalone Dispatch — OMP `task` Contract

## Contents

1. Call Shape
2. Spawn Rule
3. Result Delivery and Batch Completion
4. Hard Anti-Patterns
5. Disk-Artifact Backstop
6. Failure Policy
7. Team Mode
8. Worktree and Branch Preparation
9. Dependency Resolution and Batching
10. Executing a Confirmed Plan

This is the generated OMP (oh-my-pi) contract for standalone sub-agent fan-out. It uses
OMP's `task`, `wait`, `todo`, `proc://` and `agent://` surfaces directly. Sections 8-10
hold the dispatch-independent worktree, dependency-batching and plan-execution mechanics.

---

## 1. Call Shape

One `task` call dispatches a batch of standalone sub-agents:

```
task({
  context: "<shared background: goal, plan path, worktree line, artifact contract>",
  tasks: [
    { agent: "<ycc agent name, e.g. implementor>", name: "<CamelCase role>",
      task: "<full self-contained prompt incl. Working directory:>",
      solutionSpace: "<how open-ended>" },
    { agent: "<ycc agent name>", name: "<CamelCase role>",
      task: "<full self-contained prompt>", solutionSpace: "<how open-ended>" }
  ]
})
```

- `agent` selects the agent by its frontmatter name. `name` labels the job; it is not a
  teammate identity.
- `task` carries the complete prompt. A sub-agent starts blank, so inline any skill or
  shared reference content it needs; standalone agent installs do not ship those files.
- `context` holds background every item shares. Keep per-item facts in `task`.

---

## 2. Spawn Rule (non-negotiable)

- Put every independent agent of a batch in **one** `task` call, one `tasks[]` item each.
- Never set `isolated`. ycc pre-creates one feature worktree and passes it through the
  `Working directory:` line (section 8). Isolation is off by default
  (`task.isolation.enabled`) and, when on, makes one `~/.omp/wt` copy per agent and merges
  patches back, which breaks the single-worktree contract.
- If `task.batch` is off, issue one `task` call per agent in a single message and write
  the shared context to `local://ctx.md`.
- Keep every dispatched agent associated with its role and expected deliverable.

---

## 3. Result Delivery and Batch Completion

With async on (the default), `task` returns background job ids at once; results arrive
later as async-result messages.

- Call `wait` until **every** job you spawned has settled. Never end the turn while a job
  you own is running: `omp -p`, `--mode json` and RPC runs exit and drop pending results.
- If `task` ran inline (async off) or `wait` is absent, the results are already in the
  call output; do not wait.
- Do not busy-wait with `sleep`, `echo`, or status loops.
- Wait for the whole batch before merging or starting the next batch.

Validate each completed agent's report and required artifacts before marking its step
complete. A spawn acknowledgement or job status alone is not a findings report. An inline
summary longer than 5000 characters is truncated; read `agent://<id>` for the full report.

---

## 4. Hard Anti-Patterns

- Do not set `isolated` for ycc fan-out.
- Do not end the turn or finish the run with owned jobs pending.
- Do not proceed with a partial batch while other results are pending.
- Do not use `todo` for dispatch or result retrieval; it tracks only the orchestrator's
  own steps. Inspect a job with `read proc://<id>` and cancel one with
  `write proc://<id>/kill`.
- Do not fabricate findings for a completed agent with an empty or malformed report.
  Apply the backstop and failure policies below after completion.

---

## 5. Disk-Artifact Backstop

Content-producing sub-agents that can write files (for example, report-writing
researchers) should also write findings to a declared artifact path and return the same
content. Read-only reviewers, advisors, and planners never write artifacts: the
orchestrator persists each valid delivered report, and an empty or missing return is a
failed review, not evidence to reconstruct.

For agents allowed to write a backstop artifact:

1. After the job settles, validate its delivered report first (`agent://<id>` when the
   inline summary is truncated).
2. If the delivered report is empty or missing, re-read the backstop artifact from disk
   before treating the sub-agent as failed.
3. Only if **both** the delivered report and the backstop artifact are empty or missing is
   the sub-agent considered to have failed (see section 6).

Code-writing sub-agents (for example `implementor`, `review-fixer`) have no separate
findings file: the artifact is the code already on disk, plus a final `STATUS:` line in the
delivered report (`STATUS: Fixed` / `STATUS: Failed: <reason>`).

Keep deliverables in repo paths. `local://` is session-scoped and is lost with the session.

---

## 6. Failure Policy

| Failure                                                                                  | Response                                                                                                                                   |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Single sub-agent: empty/missing delivered report **and** empty/missing backstop artifact | Record a gap. If non-critical to the overall task, continue without it. Otherwise, re-dispatch once with the same prompt before giving up. |
| Majority of a batch fails (empty/missing delivered report **and** backstop artifact)     | Abort the skill run and report to the user, with guidance to retry. Do not attempt to synthesize a result from a majority-failed batch.    |
| Re-dispatch also fails                                                                   | Treat as a true failure per the non-critical/abort branches above — do not re-dispatch more than once with an identical prompt.            |

Never silently drop a failed sub-agent's slot from downstream synthesis without recording
the gap — a quietly missing finding is worse than a reported one.

---

## 7. Team Mode

`--team` is unsupported on OMP: abort before dispatch and rerun without `--team` (see
`agent-team-dispatch.md` in this directory). `write agent://<id>` messages a live agent,
but it is not a team lifecycle; never use it to emulate a team roster, shared task list,
or shutdown protocol.

---

## 8. Worktree and Branch Preparation

Single source for plan, plan-workflow, prp-plan (annotation directive) and the executors
`implement-plan`, `prp-implement`, `orchestrate`. Applies to standalone runs; `--team` is unsupported on OMP (section 7).

### 8.1 How worktree mode is decided

1. `--no-worktree` present: `WORKTREE_MODE=false`. Forced off regardless of plan annotations;
   no feature worktree; work on the prepared `feat/<slug>` branch in the current checkout.
2. Plan contains `## Worktree Setup`: `WORKTREE_MODE=true`. Annotations are the source of truth.
3. Neither: `WORKTREE_MODE=true` (default). Derive the single path below.

`--worktree` is a silent legacy no-op; combining it with `--no-worktree` is an error where the
skill says so. When the plan has `## Worktree Setup`, read `WT_PARENT_PATH` from its
`**Parent**:` line and `WT_FEATURE_SLUG` as the segment after `<repo>-`. Set
`WORKTREE_ACTIVE=true` if annotations exist or `WORKTREE_MODE=true`; false for `--no-worktree`.

Default-on deduction (no annotations):

- `WT_REPO_NAME` = basename of `git rev-parse --show-toplevel`
- `WT_FEATURE_SLUG` per skill: `implement-plan` uses the raw feature-name argument;
  `prp-implement` sanitizes the plan basename (cap 40); `orchestrate` sanitizes the task
  description (cap 20); `plan` confirmed execution uses the team sanitization (cap 20,
  fallback `untitled`). Shared sanitizer: lowercase, `[^a-z0-9-]` to `-`, collapse runs, trim
- `FEATURE_BRANCH` = `feat/${WT_FEATURE_SLUG}`
- `WT_PARENT_PATH` = `<repo-root>/.omp/worktrees/${WT_REPO_NAME}-${WT_FEATURE_SLUG}/`

### 8.2 Prepare (before any implementor dispatch)

Set `REPO_ROOT=$(git rev-parse --show-toplevel)`. Inspect `git status --porcelain`: expected pre-commit plan artifacts may be dirty;
unrelated dirty files: stop and ask user to stash, commit or clean. Then:

```bash
FEATURE_BRANCH=$(bash skill://ycc-shared/scripts/prepare-feature-branch.sh "${WT_FEATURE_SLUG}")
```

Do not skip it. Narrative-only branch instructions let agents commit to `main`. Contract:
`branch-prep.md`. When `WORKTREE_ACTIVE=true`, once before the first batch (idempotent; adopts
the prepared branch; echoes path, store as `WT_PARENT_PATH`):

```bash
WT_PARENT_PATH=$(bash skill://ycc-shared/scripts/setup-worktree.sh parent "${WT_REPO_NAME}" "${WT_FEATURE_SLUG}")
```

Then move plan artifacts once (never `cp`, `rsync` or sync; never move back); companions such as
`shared.md` ride as extra arguments. Use `$PLAN_PATH` for every later reference; run later
validation/reports/archive inside `$WT_PARENT_PATH`:

```bash
PLAN_PATH=$(bash skill://ycc-shared/scripts/move-plan-to-worktree.sh "<plan-path>" "$WT_PARENT_PATH" ["<companion>" ...])
```

`WORKTREE_ACTIVE=false`: skip worktree setup and the move; keep original plan path and run in
the prepared current checkout.

### 8.3 Agent prompt lines

Active worktree, every agent prompt (parallel and sequential):

```
Working directory: ${WT_PARENT_PATH}
All parallel agents in this batch share this path; batching guarantees no two agents touch the same file.
```

`--no-worktree`:

```
Working directory: ${REPO_ROOT}
All parallel agents in this batch share the current feature branch; batching guarantees no two agents touch the same file.
```

Treat that directory as repo root for Read/Write/Edit/Bash. Never set `isolated` on a `task` item: it makes a separate `~/.omp/wt` copy per agent and
breaks the single-worktree contract. The prompt line is sufficient.

### 8.4 Planner annotation directive (default WORKTREE_MODE=true; omit for --no-worktree)

Append to planner and persona prompts:

```
WORKTREE MODE:

The plan consumer will run all tasks in a single shared git worktree.
In your emitted plan:

1. Add a top-level `## Worktree Setup` section BEFORE the Batches summary
   (or before Implementation Steps when there is no Batches section):

   ## Worktree Setup

   - **Parent**: <repo-root>/.omp/worktrees/<repo>-<feature>/ (branch: feat/<feature>)

   Substitute the concrete `<repo>` and `<feature>` values; keep `<repo-root>/.omp/worktrees/`
   as this runtime's worktree root. All tasks - parallel and sequential - share this one path.
   Do NOT add a `**Children**:` list and do NOT add per-task `**Worktree**:` annotations.
```

---

## 9. Dependency Resolution and Batching

### 9.1 Graph and batches

Build the graph from `Depends on [...]` annotations. Tasks with `Depends on [none]` form batch 1.
A task joins the earliest batch whose dependencies are all in prior batches. Two tasks touching the
same file never share a batch. Cross-cutting shared types/config get a dedicated early batch.
Prefer wide-shallow graphs over narrow-deep chains. Dispatch each batch as one `task` call;
`wait` for the whole batch before the next.

### 9.2 Planner output directives (parallel plans)

When a planner is asked for parallel output, append:

```
PARALLEL OUTPUT MODE:

Shape the output for parallel execution:
1. Number steps hierarchically (1.1, 1.2, 2.1); first digit is batch.
2. Populate Dependencies on every step with explicit IDs (`Depends on [1.1, 1.2]` or `Depends on [none]`).
3. Add `## Batches` after `## Architecture Changes` and before `## Implementation Steps`:

   | Batch | Steps         | Depends On | Parallel Width |
   | ----- | ------------- | ---------- | -------------- |
   | B1    | 1.1, 1.2, 1.3 | -          | 3              |

   - **Total steps**: N
   - **Total batches**: M
   - **Max parallel width**: X
4. Apply the batch construction rules from section 9.1.
```

### 9.3 Between batches and failures

Run the skill's own validation inside the execution tree (worktree path or prepared checkout).
After each batch update todos and print the skill's verbatim `[done] Batch BN: K tasks — complete` marker (em dash; transcript loops match the marker).
Do not auto-retry a failed batch (usually file conflict or hidden dependency) and do not skip it;
later batches may depend on it. Preserve completed work; ask the user (fix/resume, switch to
sequential, abort) per the `failure-recovery` class in `question-policy.md` in this directory.
Standalone partial failure: continue only independent tasks.

---

## 10. Executing a Confirmed Plan

After a user confirms an in-conversation parallel plan: run section 8 (worktree: plan names parent
`<repo-root>/.omp/worktrees/<repo>-<feature>/`; run `setup-worktree.sh parent` once, dispatch with
`Working directory: <parent path>`; `--no-worktree`: derive the slug with the team-name sanitization
rules (lowercase, non `[a-z0-9-]` to `-`, collapse, cap 20, fallback `untitled`) and run
`prepare-feature-branch.sh`). The helper is idempotent, exits 1 on unrelated dirty tree, exits 2 on
a different feature branch (`--allow-existing-feature-branch` after confirmation) or on `release/*`
when `RELEASING.md` exists (`--allow-release-branch` for release-only fixes). Do not skip.
Then process section 9 batches with one `implementor` item per step in one `task` batch; run the
project type-check and unit-test commands between batches; on failure stop and ask the user
(`failure-recovery` class in `question-policy.md`).
