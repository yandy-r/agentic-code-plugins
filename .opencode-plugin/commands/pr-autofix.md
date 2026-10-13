---
description: 'Vendor-neutral PR comment auto-fix — discover every review thread, file-level
  review comment, and top-level PR comment from any author (bot or human), dispatch
  per-comment fix agents, resolve threads on success or reply-then-resolve on skip,
  and optionally enter the bounded CI auto-fix loop (--ci) to drive the PR to green.
  Sister skill to /review-fix (which consumes /code-review artifacts); this one consumes
  GitHub PR comments directly. Use when the user asks to "auto-fix PR comments", "apply
  reviewer feedback", "fix the PR review", "vendor-neutral autofix", or says "/pr-autofix".
  Usage: [<pr-number|pr-url>] [--include-resolved] [--include-outdated] [--author
  <pattern>] [--bot-only] [--human-only] [--severity <level>] [--yes|-y] [--dry-run]
  [--parallel] [--no-resolve] [--no-reply-on-skip] [--no-push] [--commit-style one|per-comment]
  [--ci] [--ci-confirm] [--ci-max-pushes=N] [--ci-max-same-failure=N] [--ci-timeout-min=N]
  [--ci-yes]'
---

Use the skill tool to load the `pr-autofix` skill, then follow its instructions with these arguments:

$ARGUMENTS
