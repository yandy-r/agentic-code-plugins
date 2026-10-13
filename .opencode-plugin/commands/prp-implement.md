---
description: 'Execute a PRP plan file with per-task validation loops. Detects package
  manager, prepares git branch, runs 5 validation levels (static/unit/build/integration/edge),
  writes a report to docs/prps/reports/, and archives the plan. Auto-detects parallel-capable
  plans and prompts for sequential or parallel execution. Use when the user asks to
  "execute a PRP plan", "implement from a plan file", "run prp-implement", "parallel
  PRP implement", "team PRP implement", or provides a path to a .plan.md file. Usage:
  [--parallel] [--worktree] [--no-worktree] [--dry-run] <path/to/plan.md>'
---

Use the skill tool to load the `prp-implement` skill, then follow its instructions with these arguments:

$ARGUMENTS
