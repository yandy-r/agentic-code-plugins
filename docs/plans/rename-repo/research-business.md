# Rename Repo: Business Research

## Executive Summary

YAN-1134 / [#304](https://github.com/yandy-r/claude-plugins/issues/304) is safety preparation for v6.0.0, not authorization to rename this repository. A maintainer needs a deterministic, reviewable preview and a fixture-proven apply operation for the later YAN-1138 reference flip. Current installation behavior, repository identity, package visibility, local configuration, and stable plugin identities must not change in this preparation PR.

## Evidence and authority

- `docs/internal/adr/0001-package-model-and-versioning.md:41-57` separates repository transport identity from marketplace/plugin identities.
- `RELEASING.md:55-85`, especially the rename switch at line 83, requires behind-the-scenes preparation followed by an owner-led reference-flip PR.
- `docs/research/ystack/roadmap.json`, `rename-prep` and `flip-rename`, supplies acceptance and activation context; older package proposals do not override the ADR.
- `AGENTS.md:18-22` distinguishes source from generated targets.

## User Stories

| Actor               | Need                                                      | Observable result                                                                               |
| ------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Maintainer          | Review every proposed source edit                         | `--dry-run` prints a full unified diff and writes nothing.                                      |
| Later flip operator | Apply exactly the bounded transformation                  | Running without `--dry-run` changes only approved references in the 12 source files.            |
| Existing user       | Keep installed plugin identities                          | `ycc:`, `ycc@ycc`, `ycc-mods`, and official-marketplace identifiers remain byte-identical.      |
| Reviewer            | Distinguish intentional old-name survivors from omissions | Docs explain exclusions for generated, historical, bare-prose, and local filesystem references. |

## Business Rules

1. Ship tooling and tests, not the rename. Never run apply on the checkout under preparation.
2. Apply is the CLI default when `--dry-run` is absent; documentation must make this explicit. Preview remains the instructed maintainer first step.
3. Preserve marketplace and namespace identities: repository renaming is not an `acc` conversion or `ycc` rename.
4. Do not hand-edit generated targets, host names, remotes, trust paths, worktree paths, or unrelated settings.
5. No early version bump, release tag, package listing, npm publication, or migration activation is part of this issue.
6. A repeated apply on an already-transformed fixture succeeds as a no-op.

## Source scope rationale

The roadmap's approximate count of old-name references is not a write set. The settled 12-file allowlist includes current distribution/install sources and generator constants; historical issue/release links and generated copies deliberately remain outside it. Bare names such as the README heading are also outside the anchored-reference contract. `ycc/mods/.claude-plugin/marketplace.json` is included because its URL can change while its `ycc-mods` identity must not.

## Later activation, not preparation

The owner renames GitHub/Forgejo repositories and preserves redirects; the later flip updates remotes, applies reviewed source replacements, regenerates targets, and proves installation and old-URL behavior. Package listing remains a separate gate. These are future workflow responsibilities, not performed or verified here.

## Evidence status

The original research was read-only. Parent integration now reports 20 fixture tests and 50 scope tests passed, lint passed, and validation for inventory, scope, and practices passed. The real dry-run shows 24 anchored replacements in 12 files with no protected strings in the diff. The README bare-name rewrite was removed; only anchored owner/repo references are rewritten. No apply, host rename, release, or external activation is claimed. These are parent-reported results, not checks rerun by this documentation worker.
