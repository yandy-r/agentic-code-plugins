# Review Dispatch

## Contents

- Standalone dispatch
- Scratch backstop and cleanup

## Standalone dispatch (Path B)

Follow the spawn/return contract in
`~/.config/opencode/shared/references/standalone-dispatch.md` for
how reviewers are dispatched and how their results are collected.

Dispatch 3 standalone `code-reviewer` sub-agents in parallel in a single
message with multiple native `subagent` calls. Use the mode-appropriate roster
(Local / Quick Mode Roster or PR Mode Roster) and the Standard Findings Format
from `~/.config/opencode/shared/references/review-checklist.md`.
That reference defines the roster, severity rubric, findings-format directive
and merge procedure. Prompt contract follows below.

Run-id and scratch paths per mode:

| Mode  | run-id                                                                                                    | scratch dir                                            |
| ----- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Local | `local-<TIMESTAMP>` (one canonical timestamp per invocation; reused for the Phase 3 review filename)      | `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/` |
| PR    | `pr-<NUMBER>` (PR numbers are unique; no timestamp)                                                       | `docs/prps/reviews/.review-scratch/pr-<NUMBER>/`       |
| Quick | `quick-<TIMESTAMP>` (reused for the artifact filename if the user later selects an artifact-writing path) | `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/` |

Each reviewer prompt includes the instruction "flag only gaps that affect correctness or the stated requirements", plus:

1. The list of changed files (mode-specific: `git diff --name-only HEAD` for
   local/quick; PR number + head revision + changed-file list for PR).
2. Relevant context (AGENTS.md rules, PRP artifacts, PR description) — PR mode only.
3. Its assigned focus / categories and what to check (from the roster tables
   in `review-checklist.md` — `~/.config/opencode/shared/references/review-checklist.md`).
4. The severity rubric.
5. A directive to return findings in the **Standard Findings Format** below.
6. (Path B only) The spawn/return contract loaded by the caller from
   `~/.config/opencode/shared/references/standalone-dispatch.md`.
   The reviewer is dispatched read-only (Read/Grep/Glob): it returns its
   findings inline as the `subagent` result and never writes files or runs
   commands. The prompt must supply the diff and any command output the
   reviewer needs.

After all 3 native `subagent` calls return, the calling skill (not the reviewer) persists
each valid inline return to its scratch copy at
`docs/prps/reviews/.review-scratch/<run-id>/<reviewer-name>.md`, where
`<run-id>` is `local-<YYYYMMDD-HHMMSS>` for local mode, `pr-<NUMBER>` for PR
mode, `quick-<YYYYMMDD-HHMMSS>` for quick mode. An empty, missing, or malformed
return marks that reviewer failed (merge procedure in review-checklist.md); the
scratch copy is not a second recovery source. Pass the merged findings to
the REPORT phase (Phase 3 local / Phase 6 PR) as if they came from a
single-pass review. Scratch cleanup happens after the artifact write; see
below.

Validation commands still run sequentially in the main skill —
parallelization applies only to the review pass.

## Scratch backstop and cleanup

- code-review local mode: remove `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/`
  once the review artifact has been written successfully (Phase 3).
- code-review PR mode: remove `docs/prps/reviews/.review-scratch/pr-<NUMBER>/`
  once the artifact has been written and (when `WORKTREE_ACTIVE=true`)
  committed successfully (Phase 6).
- quick-review: remove `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/`
  at the end of Phase 5 (HAND-OFF) unconditionally — including on "Discard"
  and "Apply fixes", which never write a permanent artifact. The scratch file
  is the one ephemeral exception to quick-review's artifact-free guarantee.
