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
