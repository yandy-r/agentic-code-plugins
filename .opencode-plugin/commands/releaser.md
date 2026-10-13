---
description: 'This skill should be used when the user asks to "prepare a release",
  "cut a release", "tag a release", "create a GitHub release", "draft release notes",
  "set up release CI", "add a release workflow", "audit release pipeline", "publish
  a GitHub release", or "publish release notes" for any project. Detects language/toolchain,
  drafts a changelog, plans platform/arch artifacts, optionally generates or audits
  GitHub Actions release CI, and emits the exact commands the user runs to tag and
  publish. Never auto-commits, pushes, or publishes without an explicit `--publish`
  and `--confirm` from the user. Generic external-project counterpart to `bundle-release`
  (which is scoped to this repo''s ycc bundle). Usage: [version] [--arch=list] [--os=list]
  [--ci-config[=generate|audit]] [--platform=name] [--skip-notes] [--dry-run] [--exclude-internal]
  [--publish[=create|edit|auto]] [--confirm] [--ci] [--ci-max-pushes=N] [--ci-max-same-failure=N]
  [--ci-timeout-min=N] [--ci-yes] [--ci-recut=destructive]'
---

Use the skill tool to load the `releaser` skill, then follow its instructions with these arguments:

$ARGUMENTS
