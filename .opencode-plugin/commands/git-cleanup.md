---
description: 'This skill should be used when the user asks to "clean up git", "prune
  stale branches", "clean up worktrees", "close stale PRs/issues", "tidy up my repo",
  or mentions removing abandoned branches, worktrees, remote-tracking refs, tags,
  stashes, PRs, or issues on GitHub/GitLab. Analyzes active code before recommending
  deletions, presents a plan, and only acts after explicit approval. Dry-run and read-only
  audit by default. Usage: [--dry-run|--apply] [--branches] [--worktrees] [--remotes]
  [--stashes] [--tags] [--prs] [--issues] [--stale-days=N] [--host=github|gitlab|auto]
  [--protect=<pattern>] [--report-only]'
---

Use the skill tool to load the `git-cleanup` skill, then follow its instructions with these arguments:

$ARGUMENTS
