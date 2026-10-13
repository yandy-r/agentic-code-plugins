# Agent Team Dispatch — Canonical Lifecycle Reference

Used by `plan`, `plan-workflow`, `prp-plan`, `prp-implement`,
`implement-plan`, `orchestrate` and `deep-research`
when the `--team` flag is passed. This file documents the universal create an agent group → record the task → Agent →
the task tracker → send follow-up instructions → close the agent group lifecycle. Individual skills own their teammate
roster and prompt templates; only the mechanism lives here.

> **`--team` is opt-in.** It requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` to be set
> in the user's Codex environment. Skills that reference this document validate
> that at flag-parse time and abort with guidance to use `--parallel` instead when the
> flag isn't set.
>
> **Implicit-team model note.** Recent Codex versions removed the `create an agent group`/`close the agent group`
> tools in favor of an implicit team model: every session already has one team when the
> experimental flag is set, teammates are spawned directly via the `Agent` tool's `name`
> parameter, and `team_name` is accepted but ignored. A full rewrite of this document's
> lifecycle (Steps 1-6) to match the implicit-team model is a follow-up, not done in this
> pass — for now, `create an agent group`/`record the task`/`close the agent group` calls in this doc's lifecycle
> remain as documented, and skills should continue to call them where their target CLI
> still supports them, but this may need revisiting.

## Contents

1. Team Name Sanitization
2. Lifecycle (6 steps)
3. Spawn Rule
4. Failure Policy
5. Dry-Run Semantics
6. Multi-Batch Runs
7. Worktree-aware team dispatch
8. Skill Adapters: Planning and Batched Executors

---

## 1. Team Name Sanitization

Team names follow the pattern: `<skill-prefix>-<sanitized-context>`.

**Sanitization rules for the `<sanitized-context>` portion**:

1. Lowercase all characters.
2. Replace any character matching `[^a-z0-9-]` with `-`.
3. Collapse runs of `-` to a single `-`.
4. Trim leading and trailing `-`.
5. **Truncate to a maximum of 20 characters** for the `<sanitized-context>` portion
   (the prefix is excluded from this cap).

**Skill prefixes** (do not change):

| Skill                | Prefix  | Example                 |
| -------------------- | ------- | ----------------------- |
| `plan`           | `plan-` | `plan-add-rate-limit`   |
| `prp-plan`       | `prpp-` | `prpp-billing-webhooks` |
| `prp-implement`  | `prpi-` | `prpi-user-auth-flow`   |
| `implement-plan` | `impl-` | `impl-user-auth-flow`   |
| `deep-research`  | `drpr-` | `drpr-ai-deployment`    |
| `plan-workflow`  | `pw-`   | `pw-user-auth-flow`     |
| `orchestrate`    | `orch-` | `orch-user-auth-flow`   |

If the sanitized context would be empty (e.g., only symbols), fall back to
`untitled`.

---

## 2. Lifecycle (6 steps)

Every `--team` run MUST perform these steps in order. Deviation corrupts the
shared task list or leaves orphaned teammates.

### Step 1 — create an agent group

```
create an agent group: team_name="<prefix>-<sanitized-context>", description="<one-line purpose>"
```

The description should name the skill and the concrete goal (e.g., `"Multi-perspective
planning team for: add rate limiting"`). If `create an agent group` fails, **abort the skill** with
a clear error. Do NOT silently fall back to a non-team mode — any teammates spawned
with a stale `team_name` will error, and orphaned teams make debugging harder.

### Step 2 — record the task (all tasks up front)

Register every subtask before spawning any teammates. Wire dependencies via
`addBlockedBy` so the shared task list reflects the full graph:

```
record the task: subject="<task-id>: <short description>", description="<full spec>"
update the task tracker: taskId="<task-2-id>", addBlockedBy=["<task-1-id>"]
```

Up-front registration is important for multi-batch runs (e.g., `prp-implement`): it
preserves dependency state across batches and prevents the the task tracker from resetting
when teammates from a completed batch are shut down.

For single-batch runs (e.g., `plan`, `prp-plan`), the task graph is flat — still
register all tasks before spawning.

### Step 3 — Agent spawn (single message, multiple calls)

**CRITICAL**: All teammates for a given batch MUST be spawned in **ONE message** with
**MULTIPLE `Agent` tool calls**. Sequential `Agent` calls across messages break the
parallel semantics.

Every `Agent` call MUST include both `team_name=` and `name=`:

```
Agent(
  team_name   = "<prefix>-<sanitized-context>",
  name        = "<teammate-name>",
  subagent_type = "<subagent-type>",
  description = "<one-line task title>",
  prompt      = "<full task prompt>"
)
```

The `name` must match the `record the task` `subject` prefix so the the task tracker maps cleanly.

### Step 4 — the task tracker monitoring

Use `the task tracker` to confirm batch completion before advancing. Teammates mark their
tasks complete via `update the task tracker`; the orchestrator reads status via `the task tracker`. Do
NOT rely on agent return values alone — check the shared task state.

If a teammate messages the orchestrator with an issue, respond via `send follow-up instructions` with
guidance.

### Step 5 — send follow-up instructions (shutdown between batches)

Between batches — or at the end of a single-batch run before `close the agent group` — send a
shutdown request to every teammate of the completed batch:

```
send follow-up instructions(to="<teammate-name>", a shutdown request)
```

Wait for all shutdowns to complete before spawning the next batch (multi-batch runs)
or proceeding to Step 6 (single-batch runs).

### Step 6 — close the agent group

After the final batch completes (or if the skill aborts partway), clean up:

```
close the agent group
```

Always `close the agent group` — orphaned teams persist across skill invocations and pollute the
workspace.

---

## 3. Spawn Rule (non-negotiable)

- All teammates in a batch → ONE message → MULTIPLE `Agent` calls.
- Every `Agent` call includes `team_name=` + `name=`.
- No standalone sub-agent spawns mixed in.

If an implementation spawns an agent without `team_name`, it's a bug. Fix before
continuing.

`Agent`+`team_name` (this file) and `Task` (standalone fan-out) are mutually exclusive
primitives — never mix them within the same dispatch. See
[standalone-dispatch.md](./standalone-dispatch.md) for the `Task` contract.

---

## 4. Failure Policy

| Failure                        | Response                                                         |
| ------------------------------ | ---------------------------------------------------------------- |
| `create an agent group` fails             | Abort skill; report error. Do NOT fall back silently.            |
| `record the task` fails             | `close the agent group`, then abort.                                        |
| Teammate returns error         | Record failure in the task tracker; decide per skill (continue / abort). |
| Between-batch validation fails | Shutdown current batch, ask user (fix / sequential / abort).     |
| User aborts mid-run            | `send follow-up instructions(shutdown)` to active teammates, then `close the agent group`.  |

Never leave a team live after the skill exits.

---

## 5. Dry-Run Semantics

If the skill is invoked with both `--team` and `--dry-run` (where the skill
supports dry-run), print:

```
Team name:      <prefix>-<sanitized-context>
Teammates:      <count>
  - <name-1>   subagent_type=<type>   task=<short>
  - <name-2>   subagent_type=<type>   task=<short>
  ...
Batches:        <count>  (batch <n>: <comma-separated teammate names>)
Dependencies:   <edge-count>  (or "none" for flat graphs)
```

Do **not** call `create an agent group`, `record the task`, `Agent`, `send follow-up instructions`, or `close the agent group` in
dry-run mode. The output above is the entire dry-run artifact.

---

## 6. Multi-Batch Runs (relevant to `prp-implement`)

For skills that process multiple batches against a single team:

1. `create an agent group` once at the start.
2. `record the task` for **every task across all batches** up front, with `addBlockedBy`
   wiring dependencies.
3. For each batch in order:
   - Spawn teammates for the batch's tasks (single message, multiple `Agent` calls).
   - Wait for `the task tracker` to show all batch tasks complete.
   - Run any between-batch validation the skill requires.
   - `send follow-up instructions(shutdown)` to all teammates of the completed batch.
4. `close the agent group` once at the end.

This is cheaper than recreating a team per batch and preserves dependency state
across batches. If validation fails between batches, the user may abort or switch
to a non-team mode — in both cases, `send follow-up instructions(shutdown)` + `close the agent group` first.

---

## 7. Worktree-aware team dispatch

Worktree mode is **on by default** for the 9 worktree-aware skills; pass `--no-worktree`
to opt out. The legacy `--worktree` flag is accepted as a silent no-op (it matches the
new default). When worktree mode is active (default), all teammates — parallel and
sequential — share **one** feature worktree: `<repo-root>/.codex/worktrees/<repo>-<feature>/`
(see [worktree-strategy.md](./worktree-strategy.md)). Parallel safety comes from
per-skill batching and prompts (e.g. different files, or exclusive sections), not from
separate per-task worktrees. The `setup-worktree.sh child` + `merge-children.sh` fan-in
**sequence is deprecated**; do not add it in new team flows.

**One-time (before the first `Agent` spawn, when the feature worktree is used):** ensure
the feature worktree exists, typically via:

`setup-worktree.sh parent <repo> <feature-slug>` (optional `--base-ref` for an existing
branch — e.g. PR review).

### 7.1 Per-batch ordering

Exact ordering within ONE batch (supersedes the old “create child / merge-children” flow):

1. `record the task` for all tasks in the batch (as in §2.2) — _if_ the team graph registers batch tasks the same way as non-team mode; otherwise follow the skill’s own registration rules.
2. `Agent` spawn — one message, multiple `Agent` calls (per §2.3). Each call includes
   `team_name=`, `name=`, and the **same** `Working directory: <feature-worktree-path>` in the prompt (or equivalent) so all parallel teammates operate in the one tree. Do
   **not** add `isolation: "worktree"` for this contract; that creates
   separate harness worktrees per teammate.
3. `the task tracker` monitor → `send follow-up instructions(shutdown)` to every teammate of the batch (per
   §2.4–2.5).
4. **Between batches:** run whatever validation the skill requires **inside the same**
   feature worktree. **Do not** call `merge-children.sh` for fan-in; that entrypoint is a
   deprecated no-op in the new contract.
5. On validation or manual-merge failure in the worktree, follow the skill’s failure
   policy; do not expect `CONFLICT:` lines from a removed child merge script.

`merge-children.sh` and `setup-worktree.sh child` remain on disk for legacy skill text
and compatibility only.

### 7.2 Sequential vs parallel in one tree

“Sequential” here means the orchestrator does not run multiple `Agent` calls for a step
in one message; it does **not** mean a different worktree. Everyone uses
`<feature-worktree-path>` when worktree mode is on.

### 7.3 Dry-run interaction

`--dry-run` with `--team` (worktree mode is active by default; add `--no-worktree` to
suppress) may add a line to the existing dry-run output (§5), e.g.:

```
Worktree:   feature=<repo-root>/.codex/worktrees/<repo>-<feature>/  (all teammates)
```

No `setup-worktree.sh` or `merge-children.sh` calls are made in dry-run mode.

---

## 8. Skill Adapters: Planning and Batched Executors

Worktree/branch preparation, dependency-batch resolution and plan-execution mechanics are
mode-independent: use standalone-dispatch.md sections 8-10 even for `--team`. This section owns only
what differs when `--team` is passed.

Prerequisites: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, else abort with
`--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Use --parallel instead, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Codex settings if you intentionally want agent-team dispatch.`
Cursor/Codex abort: `--team requires team tools, which Cursor/Codex bundles do not ship. Use --parallel instead.`

### 8.1 Planning team adapter (`plan`, `prp-plan`)

Flat roster: register one `record the task` per teammate (no `addBlockedBy`), one `Agent` message with
`team_name=` and `name=`, `the task tracker` until complete, merge, `send follow-up instructions` shutdown to every spawned
teammate, `close the agent group` always (even on abort/partial failure). Prompt per teammate: role focus,
verbatim request/context, coordination via `send follow-up instructions` with the roster for overlapping scope,
output directives (`standalone-dispatch.md` sections 8.4 and 9.2). Teams are deleted before the
plan is relayed; any re-dispatch creates a new team (same name fine) and never messages the old one.
Critical teammate failure: abort, shut down the rest, `close the agent group`.

Plan adapter exact registration subjects (description: `Multi-perspective planning team for: <user request>`):

```
record the task: subject="architect: structural plan for <user request>", description="..."
record the task: subject="risk-analyst: risks and edge cases for <user request>", description="..."
record the task: subject="test-strategist: testing strategy for <user request>", description="..."
# When ENHANCED_MODE=true, also:
record the task: subject="security-reviewer: threat model for <user request>", description="..."
record the task: subject="ux-reviewer: user-facing impact for <user request>", description="..."
```

### 8.2 Batched executor adapter (`implement-plan`, `prp-implement`, `orchestrate`)

1. `create an agent group` once, with `description` naming the skill and feature.
2. `record the task` for every task across all batches with subject `<task-id>: <title>` and the full
   spec; then `update the task tracker ... addBlockedBy=[...]` for each dependency (section 6). Any failure:
   `close the agent group`, then abort.
3. Per batch: identify tasks whose dependencies are done; single-message `Agent` calls with
   `team_name`, `name` equal to task ID, `subagent_type`, description, task-template prompt that
   requires reading listed files first, self-validation and `update the task tracker` completion, plus the
   section 7 / standalone section 8.3 working-directory lines.
4. `the task tracker` until batch is complete; answer teammate issues via `send follow-up instructions`.
5. Skill's between-batch validation (e.g. `prp-implement` Levels 1+2) inside the execution tree.
6. `send follow-up instructions(to="<task-id>", message={type:"shutdown_request"})` to every teammate of the
   batch; wait before next batch. Print the skill's `[done] Batch BN: ...` marker.
7. `close the agent group` once after the last batch or on abort.

Failure: no auto-retry, no skipping. Ask the user via `ask the user`: fix manually and resume,
switch to sequential/standalone for remaining batches, or abort. Switch/abort: shutdown active
teammates then `close the agent group`. Resume: shut down current batch teammates and continue. The feature
worktree survives abort for manual inspection/cleanup.

### 8.3 Dry-run for executors

Print team name, `Total tasks: <N> (across <M> batches, max parallel width <X>)`,
`Dependencies: <K edges>`, per-batch task IDs (`(depends on Batch N-1)`), and the per-batch
teammate roster (`<task-id> subagent_type=implementor task=<short>`). Call no team, task,
agent, `send follow-up instructions` or `close the agent group` tools; stop.
