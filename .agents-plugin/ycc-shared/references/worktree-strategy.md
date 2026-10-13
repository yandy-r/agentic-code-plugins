# Worktree Strategy — Canonical Reference

## Contents

- 0. Default Behavior
- 1. Single feature worktree
- 2. Plan annotation format
- 3. Lifecycle (high level)
- 4. Per-Target Dispatch Matrix
- 5. End-of-Run Cleanup
- 7. Plan-artifact handoff
- 8. Harness `WorktreeCreate` Hook Integration

Used by `plan`, `prp-plan`, `parallel-plan`, `plan-workflow`,
`prp-implement`, `orchestrate`, and `implement-plan` for default
worktree isolation. Also used by `code-review` and `review-fix` — with
one twist: `code-review` in PR mode checks out an **existing** PR head branch
(see `--base-ref` below) instead of creating a new `feat/<feature>` branch from
`HEAD`.

This file documents the **single feature worktree** contract: naming scheme,
plan annotation format, per-target dispatch matrix, and cleanup. There is
**one** worktree per feature / issue / task-level run — not one child worktree
per parallel task, and not per-severity fan-out. Individual skills own flag
plumbing and per-phase behavior; the shared **invariant** lives here.

**Migration note (GitHub #79 / #80):** Older skills and plan artifacts may still
describe a parent/child model, `**Children**` lists, per-task `**Worktree**:`,
or `merge-children.sh` fan-in. That model is **deprecated** for the shared
contract. `setup-worktree.sh child` and `merge-children.sh` are **compatibility
shims** (see shared scripts) until all executors are updated. New planners and
executors should follow **only** the single-worktree contract below.

See `agent-team-dispatch.md` in this directory for the team lifecycle
and how a single worktree pairs with parallel teammate dispatch.

---

## 0. Default Behavior

Worktree isolation is **on by default** for all nine worktree-aware skills:

| Skill                       | Default                        | Opt out with    |
| --------------------------- | ------------------------------ | --------------- |
| `code-review` (PR mode) | worktree on                    | `--no-worktree` |
| `review-fix`            | worktree on                    | `--no-worktree` |
| `plan`                  | annotations emitted            | `--no-worktree` |
| `prp-plan`              | annotations emitted            | `--no-worktree` |
| `parallel-plan`         | annotations emitted            | `--no-worktree` |
| `plan-workflow`         | annotations emitted            | `--no-worktree` |
| `prp-implement`         | worktree on (auto-detect)      | `--no-worktree` |
| `implement-plan`        | worktree on (auto-detect)      | `--no-worktree` |
| `orchestrate`           | worktree on for parallel tasks | `--no-worktree` |

The legacy `--worktree` flag remains accepted on every skill as a silent no-op
(it now matches the default). Existing pipelines and documentation that pass
`--worktree` continue to work without modification.

**Auto-detect (executors)** — `prp-implement`, `implement-plan`, and
`orchestrate` first look for a `## Worktree Setup` section in the plan and
honor its annotations when present. When the plan has no annotations, the
fallback is now **on** (was off). `--no-worktree` overrides both the plan
annotations and the default.

**Artifact location for `code-review`** — In PR mode the review artifact is
written _into the active worktree_ at
`<worktree>/docs/prps/reviews/pr-<N>-review.md`, then committed and pushed to
the PR's head branch. See `ycc/skills/code-review/SKILL.md` for
the full lifecycle (draft→ready promotion, artifact commit+push, post-review
worktree removal, opt-outs `--keep-draft` and `--keep-worktree`).

`review-fix` follows: it discovers the artifact in the active worktree's
`docs/prps/reviews/` first, then falls back to the main repo for in-flight
artifacts written under the previous contract.

---

## 1. Single feature worktree

Every worktree-enabled run uses **exactly one** git worktree for isolated work
(unless the user opts out with `--no-worktree`).

### Feature worktree

| Property   | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| Path       | `<repo-root>/.claude/worktrees/<repo>-<feature>/`                     |
| Branch     | `feat/<feature>` (default) or `<base-ref>` (see below)                |
| Created    | Once, before the first batch or task (via `setup-worktree.sh parent`) |
| Lifetime   | Survives to end of run; used for the final PR                         |
| Removed by | User (never auto-removed by the skill)                                |

All tasks — parallel and sequential — share this **one** worktree. Parallel
sub-agents or teammates do **not** get separate worktree paths; they use the
same path with coordination rules in their prompt (`Working directory: <path>`)
so concurrent writers do not corrupt the tree (e.g. file-level batching, no
two agents on the same file, or serial execution for conflicting edits — see
per-skill rules).

The source contract uses the repo-local root
`<repo-root>/.claude/worktrees/` so each runtime stays inside the managed
worktree parent it is willing to enter. Generated target bundles rewrite this
root to the target equivalent (`<repo-root>/.codex/worktrees/`,
`<repo-root>/.cursor/worktrees/`, or
`<repo-root>/.config/opencode/worktrees/`). The shared `setup-worktree.sh`
helper also honors `YCC_WORKTREE_ROOT` for explicit overrides; relative
override values are resolved against the active repo root.

#### Checking out an existing branch (`--base-ref`)

By default the feature worktree is placed on a new `feat/<feature>` branch
created from `HEAD`. Skills that need to isolate an **existing** branch (e.g.,
`code-review` checking out a PR head) pass `--base-ref`:

```bash
# Default — new branch from HEAD
setup-worktree.sh parent <repo> <feature-slug>

# Check out an existing branch directly
setup-worktree.sh parent <repo> <feature-slug> --base-ref <branch>
```

When `--base-ref` is supplied:

- No new branch is created. The worktree is placed directly on `<branch>`.
- If `<branch>` does not resolve locally, the script runs
  `git fetch origin <branch>:<branch>` once and retries.
- The idempotency check expects the worktree to be on `<branch>`, not on
  `feat/<feature-slug>`.
- The worktree cannot coexist with the same branch already checked out in the
  main repo. Switch away from `<branch>` in the main repo first, or pick a
  different base ref.

---

## 2. Plan annotation format

Planners that support worktree output emit a top-level `## Worktree Setup`
section. Implementors use it to resolve the single path and feature slug. No
per-task or per-parallel child paths are **required** by the new contract.

### Top-level `## Worktree Setup` section

Placed at the top of the plan, after frontmatter and before the first batch or step.

**Current contract (single worktree only):**

```markdown
## Worktree Setup

- **Parent**: <repo-root>/.claude/worktrees/<repo>-<feature>/ (branch: feat/<feature>)
```

The `**Parent**:` line names the one feature worktree path. Do **not** add a
`**Children**:` list in new plans; parallel work happens **inside** this path.

### Legacy fields (back-compat, not part of the new contract)

Older plans may still include:

- A `**Children**:` bullet list (per parallel task)
- A per-task line: `- **Worktree**: <path> ...` inside a task block

Parsers that support legacy plans may read these for migration or display, but
the shared **default** is: **one** worktree, no fan-in merge, no
`setup-worktree.sh child` in the new workflow path.

### Review / PR review artifacts

For `code-review` + `review-fix`, the `## Worktree Setup` block should list
only the feature worktree (same `**Parent**:` form). The PR head branch is
expressed via `--base-ref` when creating that worktree — not by spawning extra
per-severity worktrees. Legacy artifacts that listed severity-keyed “children”
are deprecated; prefer a single `**Parent**:` only.

### Sequential vs parallel tasks

With the single worktree model, all tasks run against the same path. Planners
need not emit per-task `**Worktree**:` lines for new work.

---

## 3. Lifecycle (high level)

1. **Once:** `setup-worktree.sh parent <repo> <feature-slug>` (optional `--base-ref` for existing branches).
2. **Per batch / task:** run work in the feature worktree; dispatch parallel agents
   with `Working directory: <feature-worktree-path>` (or equivalent target-specific isolation) — **all share the same path**.
3. **No** `setup-worktree.sh child` and **no** `merge-children.sh` in the new contract.
   (Legacy calls may still exist in older skill text; shims are non-destructive — see script headers.)
4. **Validate** between batches as the skill requires.
5. On **merge conflicts** or validation failure, handle in the feature worktree
   per skill policy (pause, user resolve, etc.).

---

## 4. Per-Target Dispatch Matrix

| Capability profile          | Primary mechanism                                                                    | Fallback                |
| --------------------------- | ------------------------------------------------------------------------------------ | ----------------------- |
| Tool-side agent isolation   | Pre-create one feature worktree, then dispatch agents with `Working directory:` only | Bash `git worktree add` |
| Bash-only agent runtimes    | Bash `git worktree add` via prompt                                                   | same                    |
| Docs-only / manual runtimes | Docs-only (emit commands; no auto-create)                                            | User runs manually      |

Parallel teammates all target the **same** feature worktree path in prompts.
See `target-capability-matrix.md` in this directory for the full
per-target table.

---

## 5. End-of-Run Cleanup

The feature worktree remains at `<repo-root>/.claude/worktrees/<repo>-<feature>/` after the
run completes. Skills do not auto-remove it.

`list-worktrees.sh` can report the path, branch, and manual cleanup:

```bash
git worktree remove <repo-root>/.claude/worktrees/<repo>-<feature>/
# If you created feat/<feature> and it is fully merged:
git branch -d feat/<feature>
```

---

## 7. Plan-artifact handoff

Plan files (and their companion artifacts) are **pre-commit** at the moment the
implementor is invoked. They live in the main checkout because the planner ran
before the worktree existed. The implementor **moves** them into the feature
worktree exactly once, immediately after `setup-worktree.sh parent`.

**Never** `cp`, `rsync`, or "sync" plan files. Copying leaves an untracked file
behind in the main checkout, and from the user's perspective the canonical
location of the plan becomes ambiguous.

Artifacts covered by the always-move rule:

- `docs/prps/plans/<name>.plan.md` (from `prp-plan`)
- `docs/plans/<feature>/parallel-plan.md` (from `parallel-plan` / `plan-workflow`)
- `docs/plans/<feature>/shared.md` (from `plan-workflow`)
- Any companion research artifact emitted in the same `docs/plans/<feature>/`
  directory before commit

The canonical implementation is
[`_shared/scripts/move-plan-to-worktree.sh`](../scripts/move-plan-to-worktree.sh).
Skills that consume plan artifacts in worktree mode **must** call it. They
**must not** perform ad-hoc `cp` / `mv` / `rsync` logic of their own. The script
is idempotent (re-running is safe), echoes the new in-worktree plan path on
stdout, and never copies — only moves.

After the move, the implementor archives the plan inside the worktree at the
end of the run (`<plan-dir>/completed/<plan>`), keeping main untouched.

---

## 8. Harness `WorktreeCreate` Hook Integration

The `WorktreeCreate` hook registered in `ycc/settings/settings.json` still
matters for runtimes that intentionally use harness-managed worktree
creation. But for the single-worktree contract described here, executors should
pre-create the feature worktree once and dispatch agents against that existing
path via `Working directory:`. Do **not** rely on `Agent(isolation: "worktree")`
for per-task fan-out in these workflows, because the harness will create distinct
harness worktrees per agent. The hook body lives at
`ycc/settings/hooks/worktree-create.sh`. The full worktree placement policy is
documented in `ycc/settings/rules/AGENTS.md:207–224`.
