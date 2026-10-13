---
name: bundle-release
description: 'Prepares ycc bundle releases for ycc maintainers only. Use when bumping ycc version, regenerating release bundles, or drafting ycc release notes.'
argument-hint: '<new-version> [--dry-run] [--skip-notes] [--no-publish]'
allowed-tools:
  - Read
  - Grep
  - Glob
  - Write
  - Bash(git:*)
  - Bash(python3:*)
  - 'Bash(ycc/skills/bundle-release/scripts/*.sh:*)'
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/bundle-release/scripts/*.sh:*)'
  - Bash(./scripts/sync.sh:*)
  - Bash(./scripts/validate.sh:*)
---

# ycc Bundle Release

This skill prepares a `ycc` release by validating a clean tree, bumping the version
across the two hand-edited source-of-truth JSON files, regenerating the derived Cursor,
Codex, and opencode bundles, running the full validator sweep, and drafting release notes. It
never auto-commits or pushes — the user reviews all changes and runs the emitted
commands manually.

## Arguments

Parse `$ARGUMENTS` for:

- **new-version** (required, first positional) — target semver, e.g. `2.1.0`.
- **--dry-run** — run preflight and print the full release plan, write nothing.
- **--skip-notes** — skip drafting `docs/releases/<version>.md`.
- **--no-publish** — this is the default; the skill never invokes `gh release create`.
  The flag is accepted silently for clarity.

## Phase 0: Pre-flight

Run `ycc/skills/bundle-release/scripts/preflight.sh`. On non-zero
exit, STOP and surface the full stderr output to the user. Do not proceed.

Checks owned by `preflight.sh`:

- Working tree is clean (`git status --porcelain` returns empty output).
- Currently on `main` branch (or user has confirmed a release branch is intentional).
- Version parity: `ycc/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
  carry identical version strings before the bump.
- No stale version literals (`version: X.Y.Z` or `"version": "X.Y.Z"`) in hand-edited
  docs (`CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/README.md`) where the semver does
  not match the current bundle version. Author should use the `<managed by
bundle-release>` placeholder form in example snippets — see
  `references/version-policy.md` for the full rule.
- `./scripts/validate.sh` passes on the pre-release tree.

## Phase 1: Semver sanity check

Read `ycc/skills/bundle-release/references/version-policy.md`.
Compare the current version (reported by preflight output) against the requested
`<new-version>`.

Determine the bump kind (major / minor / patch) by inspecting recent commit history:

```
git log $(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~20)..HEAD --oneline
```

If the requested bump looks mismatched with the recent history — for example, new
skills were added but a patch bump was requested — surface the concern and ask the user
to confirm before continuing.

## Phase 2: Dry-run check

If `--dry-run` was passed, print the full release plan:

- Current version and new version.
- Files that will be modified (`ycc/.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`).
- Derived bundles that will be regenerated (`.cursor-plugin/`, `.codex-plugin/`, `.opencode-plugin/`).
- All commands that would be executed, in order.

Then STOP without writing or executing anything.

## Phase 3: Bump version

Run `ycc/skills/bundle-release/scripts/bump-version.sh <new-version>`.

This script updates both hand-edited JSON files atomically. After it exits, surface the
diff (`git diff ycc/.claude-plugin/plugin.json .claude-plugin/marketplace.json`) for
user review. If the script exits non-zero, surface stderr and STOP.

## Phase 4: Regenerate derived bundles

Run `./scripts/sync.sh`.

If it fails, surface the following rollback command and STOP:

```
git checkout -- ycc/.claude-plugin/plugin.json .claude-plugin/marketplace.json .opencode-plugin/ && ./scripts/sync.sh
```

Do not hand-edit `.cursor-plugin/`, `.codex-plugin/`, or `.opencode-plugin/` — these are regenerated only.

## Phase 5: Validate

Run `./scripts/validate.sh`.

If it fails, surface the same rollback command as Phase 4 and STOP. Fix the reported
error, re-run `./scripts/sync.sh` if needed, then re-run `./scripts/validate.sh` before
continuing.

## Phase 6: Draft release notes

Unless `--skip-notes` was passed, run:

```
ycc/skills/bundle-release/scripts/draft-notes.sh <new-version>
```

This fills the release notes template and writes `docs/releases/<new-version>.md`.
Prompt the user to review and edit the Summary and Upgrade Notes sections before
committing. If the script exits non-zero, surface stderr and STOP.

## Phase 7: Emit next-step commands

ALWAYS emit the following block, substituting the actual `<new-version>` value:

```
Release prepared. No commits have been made — review the diff, then run:

git add ycc/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json \
        .cursor-plugin .codex-plugin .opencode-plugin \
        docs/inventory.json \
        docs/releases/<new-version>.md
git commit -m "chore(release): v<new-version>"
git tag v<new-version>
git push origin main --tags

# Optional GitHub release:
gh release create v<new-version> --notes-file docs/releases/<new-version>.md --title "v<new-version>"
```

Omit `docs/releases/<new-version>.md` from the `git add` line if `--skip-notes` was
passed.

## Important Notes

- Never auto-commits or pushes. The user reviews all changes and runs the emitted
  commands manually.
- Never hand-edits `.cursor-plugin/`, `.codex-plugin/`, or `.opencode-plugin/` — these paths are fully
  regenerated by `./scripts/sync.sh`.
- Rollback command for any mid-run failure after Phase 3:
  `git checkout -- ycc/.claude-plugin/plugin.json .claude-plugin/marketplace.json .opencode-plugin/ && ./scripts/sync.sh`
- See `references/release-checklist.md` for the full manual checklist.
- See `references/version-policy.md` for semver bump rules and the never-edit list.
