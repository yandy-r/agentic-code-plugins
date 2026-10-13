---
description: 'Create a GitHub pull request from the current branch — validates preconditions,
  discovers PR templates, analyzes commits and file diffs, references PRP artifacts
  (prds/plans/reports), pushes, and creates the PR via gh. Lightweight sibling of
  /git-workflow --pr; use this when you only need the PR, not the commit+docs orchestration.
  Adapted from PRPs-agentic-eng by Wirasm. Usage: [base-branch] [--draft] [--ci] [--ci-max-pushes=N]
  [--ci-max-same-failure=N] [--ci-timeout-min=N] [--ci-yes]'
---

Use the skill tool to load the `prp-pr` skill, then follow its instructions with these arguments:

$ARGUMENTS
