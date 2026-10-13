---
name: review-fix
description: 'Applies saved code-review findings and updates artifact status. Use when fixing a review file, applying severity-filtered findings, or tracking review fixes as Fixed or Failed.'
argument-hint: '[--parallel | --team] [--severity <level>] [--no-worktree] [--dry-run] <path/to/review.md | pr-number | blank>'
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
  - Bash(find:*)
  - Bash(mkdir:*)
  - Bash(git:*)
  - Bash(npm:*)
  - Bash(pnpm:*)
  - Bash(yarn:*)
  - Bash(bun:*)
  - Bash(npx:*)
  - Bash(cargo:*)
  - Bash(go:*)
  - Bash(pytest:*)
  - Bash(python:*)
  - Bash(python3:*)
  - Bash(make:*)
---

# Review Fix

Apply fixes for saved `/ycc:code-review` artifacts: filter findings, group
into dependency-safe batches, dispatch `ycc:review-fixer` agents, update the
artifact's Status fields in place, write a fix report. Adapted from
PRPs-agentic-eng by Wirasm. The artifact is the source of truth; never modify
a finding's `Suggested fix` — mark it `Failed` and let the human decide.

Input: `$ARGUMENTS`.

## Phase 0 — DETECT

Flag table (strip flags; remainder is the selector):

| Flag                 | Effect                                                                                                                             |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `--parallel`         | Standalone `ycc:review-fixer` sub-agents in parallel per batch; fail-stop between batches                                          |
| `--team`             | Claude Code only; same fan-out via agent team (TeamCreate once, flat task graph, per-batch spawn + shutdown)                       |
| `--severity <level>` | Minimum severity: CRITICAL/HIGH/MEDIUM/LOW; default HIGH                                                                           |
| `--dry-run`          | Print the fix plan and stop. No dispatch, no file changes. With `--team` also print team name and per-batch roster (no tool calls) |
| `--worktree`         | Legacy no-op; worktree mode is default (auto-detect from artifact)                                                                 |
| `--no-worktree`      | Apply fixes directly in current working tree                                                                                       |

Set `PARALLEL_MODE`, `MIN_SEVERITY`, `DRY_RUN`, and `AGENT_TEAM_MODE`;
`WORKTREE_MODE=true` unless `--no-worktree`. Gates:

- Both `--parallel` and `--team`:
  `--parallel and --team are mutually exclusive. Pick one.`
- `--team` without `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`:
  `--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Use --parallel instead, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Claude Code settings if you intentionally want agent-team dispatch.`
- `--team` in Cursor/Codex bundles: use `--parallel` instead.

Input resolution — artifact lives on the PR branch in the worktree's
`docs/prps/reviews/`; fall back to main repo's. Path ending `.md` → as-is;
digits → `docs/prps/reviews/pr-<N>-review.md`; blank → latest by mtime in
current worktree, then main repo; prompt user to confirm.

Error paths:

- Nothing found: `Error: No review artifact found.` + `Run /ycc:code-review first to produce a review artifact.`
- Missing explicit path: `Error: review file not found: <path>`
- Unparseable: `Error: Review file has no parseable findings or is not in the expected format.`
  Artifact schema lives in shared reference — see Phase 1.
- No Open findings: stop with Fixed/Failed counts, `Nothing to do.`

Package manager detection (`TYPECHECK_CMD`, `TEST_CMD`):

| File                | Type-check                      | Tests           |
| ------------------- | ------------------------------- | --------------- |
| `bun.lockb`         | `bun run typecheck`             | `bun test`      |
| `pnpm-lock.yaml`    | `pnpm typecheck` / `pnpm tsc`   | `pnpm test`     |
| `yarn.lock`         | `yarn typecheck`                | `yarn test`     |
| `package-lock.json` | `npx tsc --noEmit`              | `npm test`      |
| `Cargo.toml`        | `cargo check`                   | `cargo test`    |
| `go.mod`            | `go vet ./...`                  | `go test ./...` |
| `pyproject.toml`    | project-specific (mypy/pyright) | `pytest`        |

## Phase 1 — LOAD

Parse artifact per finding schema and status rules:

`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/review-artifact-format.md`

Finding missing Status → treat as Open, warn:
`Warning: Finding F### has no Status field. Treating as Open.`

Scan for `^## Worktree Setup`:

- Present → `WORKTREE_ACTIVE=true` (artifact declaration wins). Capture
  `PARENT_PATH` (parent worktree, `- **Parent**: <path> (branch: <branch>)`)
  and `PARENT_BRANCH`. Missing directory:
  `Error: parent worktree <path> is declared in the review artifact but does not exist.` +
  `Re-run /ycc:code-review --worktree <N> to recreate it, then retry.`
- Absent + `WORKTREE_MODE=false` → `WORKTREE_ACTIVE=false`; continue.
- Absent + forced `--worktree`: for `pr-<N>-review.md` resolve PR head and run
  `setup-worktree.sh parent <repo> pr-<N> --base-ref <head>`. For
  `local-*-review.md`: `Error: --worktree cannot be force-applied to a local review artifact that was produced without worktree isolation. Re-run /ycc:code-review --worktree to regenerate.`

## Phase 2 — FILTER

In order, tracking drops: (a) keep `Status: Open` only; (b) severity ≥
`MIN_SEVERITY` (CRITICAL > HIGH > MEDIUM > LOW); (c) drop empty
`Suggested fix`; (d) drop findings whose file is missing (`test -f`).

Print filter summary (Total/Already Fixed/Already Failed/Below threshold/No
suggested fix/Missing files/Eligible). `M == 0` → `No eligible findings to fix.`

## Phase 3 — PLAN

Grouping: same-file findings share one fixer, sorted by line descending;
different files are parallel candidates; batches ordered by severity
(CRITICAL first). With `WORKTREE_ACTIVE=true`, batch = one severity level,
same-file grouping preserved within each batch.

If `DRY_RUN=true`, stop here after printing the plan (defer exit to Phase 4
C.2 under `--team` so the roster prints too); reminder:
`Dry run complete. To apply fixes, re-run without --dry-run:` + command form.

## Phase 4 — EXECUTE

Read fixer prompt contract, Path B/C fan-out and failure handling:

`${CLAUDE_PLUGIN_ROOT}/skills/review-fix/references/fixer-dispatch.md`

Path selection: neither flag → Path A sequential; `--parallel` → Path B
standalone parallel batches; `--team` → Path C agent team.

Worktree lifecycle (`WORKTREE_ACTIVE=true`, per
`worktree-strategy.md` §1): all batches run inside `$PARENT_PATH`; no
per-severity child worktrees, no fan-in merge. Per batch: dispatch with
`Working directory: $PARENT_PATH` (no `isolation: "worktree"`), validate
(`$TYPECHECK_CMD` + `$TEST_CMD`) in `$PARENT_PATH`, advance. One-time parent
setup only when forced and not yet ensured.

Status updates in place via `Edit` after each agent returns: Fixed on
`STATUS: Fixed`, Failed on `STATUS: Failed`. Track per-batch todos. Between
batches, failed validation stops the pipeline and asks: resume sequentially /
switch to parallel / abort / skip to Phase 5.

## Phase 5 — VERIFY

Run `$TYPECHECK_CMD` and `$TEST_CMD`; record pass/fail. Diagnostic only — no
rollback; user decides.

## Phase 6 — REPORT

Read report template and worktree summary:

`${CLAUDE_PLUGIN_ROOT}/skills/review-fix/references/fix-report.md`

Write to `docs/prps/reviews/fixes/<source-name>-fixes.md` under the active
checkout root. In worktree mode, stage and commit the report alongside fix
commits and push. GitHub-only: detect forge first (see
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/forge-detection.md`); on
non-GitHub providers skip commit/push with notice
`PR posting is GitHub-only on provider <provider>; fixes applied locally — commit and push them yourself.` and `REPORT_COMMITTED: n/a`.

## Phase 7 — OUTPUT

Report source path, report path, mode, eligible/fixed/failed/skipped/open
counts, updated statuses, validation results, next steps
(`/ycc:code-review <target>` re-review, `/ycc:git-workflow --commit`).

Print under `### Goal Signals (machine-readable — printed verbatim for /goal)`,
as the last lines, one `KEY: PASS|FAIL` per line (always include the value):

```
PLAN_VALID: <PASS|FAIL>
REVIEW_UPDATED: <PASS|FAIL>
REPORT_CREATED: <PASS|FAIL>
VALIDATION_RUN: <PASS|FAIL>
REPORT_COMMITTED: <PASS|FAIL|n/a>
```

PASS only when the criterion holds: plan respects same-file sequentialization;
every attempted finding's Status updated in the source artifact; report
written under `docs/prps/reviews/fixes/`; Phase 5 completed (even if checks
failed); report committed and pushed (worktree mode; `n/a` in `--no-worktree`).
Also print an `Open remaining: <M - X - Y>` line.

## Edge cases

- Stale line numbers (file changed since review) → fixer returns Failed;
  note `stale line — file modified since review`.
- Interrupted runs resume cleanly: statuses update incrementally; re-runs skip
  Fixed/Failed.
- No recursive new-finding scan; re-run `/ycc:code-review` after fixes.

## /goal pairing

Done signal: `Open remaining: 0` plus all five Goal Signals printed. Failed
findings are terminal (never re-dispatched); when `Fixed + Failed == Eligible`
the pipeline is complete. Before relying on a `/goal` loop, read:

`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/goal-pairing.md`
