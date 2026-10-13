---
description: 'Plan and apply fixes for findings in a /code-review artifact. Parses
  the review file, filters by severity, groups same-file findings into dependency-safe
  batches, dispatches review-fixer agents, updates Status in place (Open → Fixed/Failed),
  runs validation, and writes a fix report under docs/prps/reviews/fixes/. Use when
  the user asks to "fix review findings", "apply review fixes", "review-fix PR 42",
  "fix the code review", "team review-fix", or says "/review-fix". Usage: [--parallel]
  [--severity <level>] [--no-worktree] [--dry-run] <path/to/review.md | pr-number
  | blank>'
---

Use the skill tool to load the `review-fix` skill, then follow its instructions with these arguments:

$ARGUMENTS
