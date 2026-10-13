---
description: 'Cherry-pick merged trunk PRs onto active maintenance branches (release/X.Y)
  and open one backport PR per target — driven by the project''s RELEASING.md release-branches
  model and its backport:X.Y labels. Handles a single PR (`<PR#> [--to release/X.Y]`)
  or every pending labelled PR (`--pending`); stops on conflicts or dispatches a minimal
  conflict resolver (`--resolve`) and asks before pushing; optionally watches CI (`--ci`).
  `--audit` is the read-only pre-tag check that every labelled PR has a merged backport
  and that no fix merged since the line''s last tag is unaccounted for. Never merges,
  tags, or pushes to release/* directly. Use when the user asks to "backport PR Usage:
  <PR#> [--to release/X.Y] | --pending [--resolve] [--ci] [--dry-run] | --audit [release/X.Y]
  [--since REF]'
---

Use the skill tool to load the `backport` skill, then follow its instructions with these arguments:

$ARGUMENTS
