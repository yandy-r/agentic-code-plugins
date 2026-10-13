# Parallel Plan Inputs

## Contents

- Usage block
- Task parser output
- Dependency graph
- Todo format
- Monorepo Support

## Usage block

Print when no feature name remains after stripping flags:

```
Usage: /implement-plan [--team] [--dry-run] [--worktree] [--no-worktree] <feature-name>

Examples:
  /implement-plan user-authentication
    # default: create/reuse one feature worktree on feat/user-authentication

  /implement-plan --team user-authentication
    # agent-team dispatch (worktree still on by default)

  /implement-plan --dry-run payment-integration
  /implement-plan --team --dry-run payment-integration

  /implement-plan --no-worktree my-feature
    # opt out of worktree isolation; create/use feat/my-feature in the current checkout

  /implement-plan --team --no-worktree my-feature
    # agent-team dispatch on the current-checkout feature branch
```

## Task parser output

`parse-dependencies.sh` emits optional header lines followed by per-task rows.

Header lines (only when the plan has a `## Worktree Setup` section):

- `WT_PARENT_PATH=<path>` — parent worktree path
- `WT_FEATURE_SLUG=<slug>` — the `<repo>-<feature>` directory suffix; split on `-` to get the feature component

Per-task rows (`TASK_ID|TASK_TITLE|DEPENDENCIES`):

- **Task ID**: e.g., 1.1, 2.3, 3.1 (or T0, T1, T2)
- **Task Title**: descriptive name
- **Dependencies**: list from `Depends on [...]` or `- **Dependencies**: ...`
- **Files to Read**: from "READ THESE BEFORE TASK" (parsed from the plan markdown directly)
- **Files to Create**: from "Files to Create"
- **Files to Modify**: from "Files to Modify"
- **Instructions**: implementation details

## Dependency graph

```
Independent Tasks (Depends on [none]):
  - Task 1.1
  - Task 1.3
  - Task 2.2

Dependent Tasks:
  - Task 1.2 → depends on [1.1]
  - Task 2.1 → depends on [1.1, 1.2]
  - Task 2.3 → depends on [2.1, 2.2]
  - Task 3.1 → depends on [2.1]
```

Keep this graph available for both Path A (ordering) and Path B (`addBlockedBy` wiring).

## Todo format

Using the task tracker, one item per task:

- `id`: Task ID (e.g., "task-1-1")
- `content`: "[Task ID] [Task Title] - Depends on: [dependencies]"
- `status`: "pending"

```
- task-1-1: "1.1 Create user model - Depends on: none"
- task-1-2: "1.2 Add validation - Depends on: 1.1"
- task-1-3: "1.3 Setup routes - Depends on: none"
```

## Monorepo Support

The skill detects and uses the correct plans directory in monorepo setups.

Default behavior:

- Plans are read from the git repository root in `docs/plans/`.
- Running the skill from any subdirectory (e.g., `packages/app1/`) still reads plans from the root.

Configuration — create a `.plans-config` file:

Repository root (centralized plans):

```yaml
# .plans-config at repo root
plans_dir: docs/plans
```

Package-level plans (optional):

```yaml
# .plans-config in packages/app1/
plans_dir: docs/plans
scope: local
```

With `scope: local`, plans are read from the local `docs/plans/` instead of the root.

Example monorepo structure:

```
monorepo/
  .plans-config          # plans_dir: docs/plans
  docs/plans/            # Centralized plans (default)
    feature-a/
      shared.md
      parallel-plan.md   # Read by this skill
  packages/
    app1/
    app2/
```

Running `/implement-plan feature-a` from anywhere executes `monorepo/docs/plans/feature-a/parallel-plan.md`.
