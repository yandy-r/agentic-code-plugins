# Standalone Dispatch — Agent Tool Reference

## Contents

1. What `Agent` Is
2. Spawn Rule
3. Blocking / Inline-Return Semantics
4. Hard Anti-Patterns
5. Disk-Artifact Backstop
6. Failure Policy
7. Cross-Target Portability
8. Worktree and Branch Preparation
9. Dependency Resolution and Batching
10. Executing a Confirmed Plan

Used by `prp-plan`, `deep-research`, `prp-implement`, `review-fix`,
`quick-fix`, `orchestrate`, `feature-research`, `parallel-plan`,
`shared-context`, `plan-workflow`, `clean`, and `git-workflow` for
**standalone** sub-agent fan-out (no shared team, no `--team` flag). This file documents
the `Agent`-tool spawn/return contract. See `agent-team-dispatch.md` in this directory
for the separate `Agent` with `name` lifecycle used by `--team`/Path C runs. Sections 8-10
hold the dispatch-mode-independent worktree, dependency-batching and plan-execution
mechanics that `--team` runs reuse; only dispatch arguments and coordination differ.

---

## 1. What `Agent` Is

`Agent` is Codex's primitive for spawning one or more standalone sub-agents that run
to completion and hand their result back to the caller in the **same turn**, as the tool's
return value. Omit `name` and `run_in_background` for standalone foreground dispatch — each `Agent`
call is an independent, self-contained dispatch. Compatibility generators must translate
this Claude-facing source contract into each target's native dispatch and result vocabulary;
generated bundles must not describe `Agent` as a universal host API.

The same tool serves both modes; arguments select the mode:

|                 | `Agent` (standalone)                       | `Agent` with `name` (Path C / `--team`)                               |
| --------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| Availability    | Codex                                | Codex runtime only; not available in bundle invocations                                                      |
| Execution model | Blocking — caller waits for the result     | Async — spawns a background teammate                                  |
| Result delivery | Returned inline as the tool's return value | A "finished" notification only; output is **not** returned inline     |
| Coordination    | None — no shared task list                 | `record the task`/`the task tracker`/`send follow-up instructions` against the shared team         |
| Lifecycle       | Fire, wait, read result, done              | Implicit team → spawn with `name` → monitor → `send follow-up instructions(shutdown)` |

The "finished notification, no inline output" behavior of `Agent` with `name` is the root
cause of the bug this document exists to prevent: skills that dispatch standalone work via
`Agent` with `name` (instead of an unnamed call) and then try to read the sub-agent's findings inline get
nothing — the orchestrator goes idle waiting on output that was never returned to it.

---

## 2. Spawn Rule (non-negotiable)

All standalone sub-agents in a batch are spawned via **ONE message** with **MULTIPLE
`Agent` tool calls**:

```
Agent(subagent_type="<type>", description="<short title>", prompt="<full task prompt>")
Agent(subagent_type="<type>", description="<short title>", prompt="<full task prompt>")
Agent(subagent_type="<type>", description="<short title>", prompt="<full task prompt>")
```

- The call must **not** pass `name` or `run_in_background`. The `name` parameter
  converts the call into a teammate dispatch and `run_in_background` makes it async.
  Omit `team_name` too: it is ignored by the runtime and has no effect. Passing `name` —
  especially when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is enabled, which makes every
  session an implicit team — converts what should be a blocking, inline foreground
  dispatch into an async background teammate. That conversion replaces the inline
  return with a "finished" notification, and orchestrators that expect the former end up
  idle waiting for output that never arrives (see §3-4).
- Standalone sub-agents share no team task list. Use the task tools (`record the task`, `the task details`,
  `the task tracker`, `update the task tracker`) only for the orchestrator's own progress tracking, and never
  `send follow-up instructions` a standalone sub-agent — it has no teammate inbox.
- Sequential `Agent` calls across separate messages forfeit the parallel fan-out the
  pattern exists for — batch them into one message whenever the work is independent.

---

## 3. Blocking / Inline-Return Semantics

In the normal case, `Agent` calls **block** the orchestrator until every sub-agent in the
batch returns, and each sub-agent's full report is delivered as that `Agent` call's return
value, in the **same turn** the batch was dispatched. Read that return value directly —
this is the expected, common-case contract, and the vast majority of `Agent` batches
resolve this way.

**Defensive fallback**: if the runtime ran the batch asynchronously (for example, a
runtime bug or a flag like `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` reshaping the dispatch —
see §2) and the results are not yet in hand at the point where you would normally read
them, do **not** sleep-loop or poll waiting for them. Instead, **yield — end your turn**
(stop generating; do not call `sleep`, `echo`, or any other busywork tool "to wait") so
that any queued completion notification can flush. Resume merging results into the
skill's workflow once you are notified that the batch has completed.

The orchestrator must never:

- Poll for completion.
- `sleep` in a loop waiting for an `Agent` call to "finish."
- Treat the absence of a notification, on its own, as proof that nothing returned — check
  the actual return value first; only fall back to yielding (above) if it is genuinely
  empty/missing at read time.

If a batch of `Agent` calls returns inline, the work is done and every report is already in
hand — proceed directly to merging, no waiting required.

---

## 4. Hard Anti-Patterns

These mirror the Failure Policy intent of `agent-team-dispatch.md` in this directory
§4, but for the standalone path. Each of the following is a bug, not a stylistic
preference:

- **Do NOT** dispatch standalone fan-out via `Agent` with `name` or
  `run_in_background` set (see §2). Either produces a background
  teammate whose output is never returned inline — exactly the failure mode this document
  exists to prevent.
- **Do NOT** background an `Agent` dispatch or otherwise detach from it.
- **Do NOT** `sleep`-loop or poll waiting for an `Agent` call to complete. In the normal
  case `Agent` blocks; the result is already available when the call returns.
- **Do NOT** keep the turn alive with `sleep`, `echo`, or any other busywork "waiting" for
  sub-agents to finish — including in the async-fallback case described in §3. In current
  Codex versions, a live turn blocks completion-notification delivery, so busywork
  "waiting" deadlocks the session until the user manually presses ESC. If there is nothing
  productive to do while waiting, end the turn.
- **Do NOT** rely on "finished" notifications as the primary way to retrieve standalone
  sub-agent output — the inline return value is. Only fall back to waiting on a
  notification (by yielding, per §3) if the inline return is genuinely empty/missing at
  read time.
- **Do NOT** call `send follow-up instructions` for standalone sub-agents. Standalone agents return
  findings inline; `send follow-up instructions` operates only against active teammates.
- **Do NOT** silently synthesize or fabricate findings when a sub-agent's inline return is
  empty or missing. Treat it as a failure and follow the Failure Policy in §6 — never
  paper over a missing result with invented content.

---

## 5. Disk-Artifact Backstop

Content-producing sub-agents with `Write` (for example, report-writing researchers)
should also write findings to a declared artifact path and return the same content
inline. Read-only reviewers, advisors, and planners never write artifacts: the
orchestrator persists each valid inline return, and an empty/missing return is a
failed review, not evidence to reconstruct.

For agents allowed to write a backstop artifact:

1. The orchestrator validates the inline return first.
2. If the inline return is empty or missing, re-read the backstop artifact from disk
   before treating the sub-agent as failed.
3. Only if **both** the inline return and the backstop artifact are empty/missing is the
   sub-agent considered to have failed (see §6).

For **code-writing** sub-agents (e.g. `implementor`, `review-fixer`), there is no
separate findings file — the "artifact" is the code changes already committed to disk,
plus a final `STATUS:` line in the inline return so the blocking `Agent` result stays
parseable (e.g. `STATUS: Fixed` / `STATUS: Failed: <reason>`).

---

## 6. Failure Policy

| Failure                                                                               | Response                                                                                                                                   |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Single sub-agent: empty/missing inline return **and** empty/missing backstop artifact | Record a gap. If non-critical to the overall task, continue without it. Otherwise, re-dispatch once with the same prompt before giving up. |
| Majority of a batch fails (empty/missing inline return **and** backstop artifact)     | Abort the skill run and report to the user, with guidance to retry. Do not attempt to synthesize a result from a majority-failed batch.    |
| Re-dispatch also fails                                                                | Treat as a true failure per the non-critical/abort branches above — do not re-dispatch more than once with an identical prompt.            |

Never silently drop a failed sub-agent's slot from downstream synthesis without recording
the gap — a quietly missing finding is worse than a reported one.

---

## 7. Cross-Target Portability

This file is the Claude-facing source contract. Cursor, Codex, and opencode generators
must project it onto the target's actual tools and lifecycle rather than copying Claude
identifiers or return assumptions. `Agent` with `name` remains Claude-Code-only. Per the
`AGENTS:cursor` note in `target-capability-matrix.md` in this directory, those
generated targets have no Claude teammate-messaging surface (`send follow-up instructions`); their standalone path must use the target-native dispatch
primitive, and their generated `--team` path must fail closed when no equivalent exists.

---

## 8. Worktree and Branch Preparation

Single source for plan, plan-workflow, prp-plan (annotation directive) and the executors
`implement-plan`, `prp-implement`, `orchestrate`. Applies to standalone and `--team` runs.

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
- `WT_PARENT_PATH` = `<repo-root>/.codex/worktrees/${WT_REPO_NAME}-${WT_FEATURE_SLUG}/`

### 8.2 Prepare (before any implementor dispatch)

Set `REPO_ROOT=$(git rev-parse --show-toplevel)`. Inspect `git status --porcelain`: expected pre-commit plan artifacts may be dirty;
unrelated dirty files: stop and ask user to stash, commit or clean. Then:

```bash
FEATURE_BRANCH=$(bash ~/.codex/plugins/ycc/shared/scripts/prepare-feature-branch.sh "${WT_FEATURE_SLUG}")
```

Do not skip it. Narrative-only branch instructions let agents commit to `main`. Contract:
`branch-prep.md`. When `WORKTREE_ACTIVE=true`, once before the first batch (idempotent; adopts
the prepared branch; echoes path, store as `WT_PARENT_PATH`):

```bash
WT_PARENT_PATH=$(bash ~/.codex/plugins/ycc/shared/scripts/setup-worktree.sh parent "${WT_REPO_NAME}" "${WT_FEATURE_SLUG}")
```

Then move plan artifacts once (never `cp`, `rsync` or sync; never move back); companions such as
`shared.md` ride as extra arguments. Use `$PLAN_PATH` for every later reference; run later
validation/reports/archive inside `$WT_PARENT_PATH`:

```bash
PLAN_PATH=$(bash ~/.codex/plugins/ycc/shared/scripts/move-plan-to-worktree.sh "<plan-path>" "$WT_PARENT_PATH" ["<companion>" ...])
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

Treat that directory as repo root for Read/Write/Edit/Bash. Never pass `isolation: "worktree"` or
`Agent(isolation: "worktree")`; it creates separate harness worktrees. Codex/opencode: prompt line is
sufficient. Cursor: warn and print the manual `git worktree add` command.

### 8.4 Planner annotation directive (default WORKTREE_MODE=true; omit for --no-worktree)

Append to planner and persona prompts:

```
WORKTREE MODE:

The plan consumer will run all tasks in a single shared git worktree.
In your emitted plan:

1. Add a top-level `## Worktree Setup` section BEFORE the Batches summary
   (or before Implementation Steps when there is no Batches section):

   ## Worktree Setup

   - **Parent**: <repo-root>/.codex/worktrees/<repo>-<feature>/ (branch: feat/<feature>)

   All tasks - parallel and sequential - share this one path. Do NOT add a
   `**Children**:` list and do NOT add per-task `**Worktree**:` annotations.

See worktree-strategy.md section 1-2 for the canonical single-worktree contract.
```

---

## 9. Dependency Resolution and Batching

### 9.1 Graph and batches

Build the graph from `Depends on [...]` annotations. Tasks with `Depends on [none]` form batch 1.
A task joins the earliest batch whose dependencies are all in prior batches. Two tasks touching the
same file never share a batch. Cross-cutting shared types/config get a dedicated early batch.
Prefer wide-shallow graphs over narrow-deep chains. Dispatch each batch as one message;
wait for the whole batch before the next.

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
sequential, abort). Standalone partial failure: continue only independent tasks.

---

## 10. Executing a Confirmed Plan

After a user confirms an in-conversation parallel plan: run section 8 (worktree: plan names parent
`<repo-root>/.codex/worktrees/<repo>-<feature>/`; run `setup-worktree.sh parent` once, dispatch with
`Working directory: <parent path>`; `--no-worktree`: derive the slug with the team-name sanitization
rules (lowercase, non `[a-z0-9-]` to `-`, collapse, cap 20, fallback `untitled`) and run
`prepare-feature-branch.sh`). The helper is idempotent, exits 1 on unrelated dirty tree, exits 2 on
a different feature branch (`--allow-existing-feature-branch` after confirmation) or on `release/*`
when `RELEASING.md` exists (`--allow-release-branch` for release-only fixes). Do not skip.
Then process section 9 batches with one `implementor` `Agent` per step in one message; run the
project type-check and unit-test commands between batches; on failure stop and ask the user.
