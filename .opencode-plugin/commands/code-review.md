---
description: 'Dual-mode code review — local uncommitted changes or a GitHub PR. Writes
  a machine-parseable artifact under docs/prps/reviews/ with finding IDs and Status
  fields (Open/Fixed/Failed) that /review-fix consumes in place. PR mode reads changed
  files, runs validation commands, assigns severity, and posts the review via gh.
  Use when the user asks to "review code", "review PR", "check uncommitted changes",
  "review pr N", "parallel review", "team review", or says "/code-review". Usage:
  [--quick] [--approve | --request-changes] [--parallel] [--no-worktree] [--keep-draft]
  [--keep-worktree] [--yes] [--save] [pr-number | pr-url | blank for local review]'
---

Use the skill tool to load the `code-review` skill, then follow its instructions with these arguments:

$ARGUMENTS
