---
description: 'This skill should be used when the user asks to "create a RELEASING.md",
  "set up a branching model", "define a release process", "document how we branch
  and release", "add release branches", "switch to release branches", "upgrade the
  release model", "audit the release model", "check RELEASING.md", or when a repo
  has no written branching/release model and a skill (init, blueprint, releaser) offers
  to create one. Surveys the repo (tags, release/* branches, CI triggers, version
  files, sync merges), proposes trunk-only (every release tagged from the trunk) or
  release-branches (minors from the trunk, patches from release/X.Y with backports),
  and renders a project-specific RELEASING.md with a machine-readable state block
  plus pointer sections in AGENTS.md and AGENTS.md. --upgrade moves trunk-only to
  release-branches; --audit reports drift read-only. Never commits or pushes. Usage:
  [--upgrade | --audit] [--model trunk-only|release-branches] [--trunk NAME] [--yes]'
---

Use the skill tool to load the `release-model` skill, then follow its instructions with these arguments:

$ARGUMENTS
