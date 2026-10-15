# Branching and releases

These rules decide where every change to claude-plugins (the `ycc` bundle) goes and how
versions ship. They apply to humans and agents alike, on every task, without being
restated in prompts.

The core idea: **a change's target release is decided before work starts, and the target
decides the base branch.** A release is a tag on a branch — never a set of commits picked
from somewhere else after the fact.

## Current state

The block below is read by tools; the table is generated from it. Change both with
`release-state-update.sh` (or `/ycc:release-model`), never by hand.

<!-- ycc-release-state
model: trunk-only
trunk: main
support: latest-minor
backport_label: backport:{X.Y}
tracker: none
-->

<!-- ycc-release-state:table:begin -->

Model: **trunk-only**. Support window: latest-minor.

| Role  | Branch | Notes                        |
| ----- | ------ | ---------------------------- |
| Trunk | `main` | Every release is tagged here |

<!-- ycc-release-state:table:end -->

## Rules

1. **Know the target before you branch.** Every issue carries a target release (see
   [Planning](#planning)). No target: a bug in a shipped version is a patch; everything else
   goes to the next release.
2. **Branch off `main` and PR back into it.** Topic branches are short-lived (days, not
   weeks) and named `<type>/<issue-id>-<slug>`. If one falls behind, rebase it.
3. **Never "sync" one long-lived branch into another.** No `sync main into …` PRs.
4. **Every release comes from `main`.** Fixes ship in the next release; there are no
   maintenance branches and no backports. When an older version needs patches, upgrade the
   model with `/ycc:release-model --upgrade` instead of branching ad hoc.
5. **No new long-lived branches.** Large work lands on `main` in small PRs. See
   [Unfinished work](#unfinished-work).
6. **`main` is always releasable.** CI green, and nothing half-built reachable by users.
7. **Only maintainers cut releases**, following [Releasing](#releasing). Agents never tag.

## Where does my change go?

Every change targets the next release and goes into `main`. Bugs and security fixes
may prompt an earlier release; they never create a branch of their own.

## Unfinished work

Big features merge incrementally instead of living on a side branch. Anything a user could
reach before it is finished stays hidden: behind a setting or environment variable that
defaults to off, or simply not wired into navigation or routes until the last PR. When a
change cannot be hidden (a rename, a data-directory move), prepare everything behind the
scenes first and make the switch in one final PR shortly before the release.

List the project's feature switches here as they are added, with their default and the
release that flips them.

### v6.0.0 package-model gates (manifest implemented; generators pending)

The v6.0.0 package model is recorded in
[ADR 0001](docs/internal/adr/0001-package-model-and-versioning.md). The gates below
are **policy**. The package manifest now records the new flags, but no generator consumes them
yet and the publishing workflow is not implemented; each gate states the evidence that must pass
before the flip. They change nothing about the release
procedure below. This documentation change does not implement or trigger publication; the planned
npm policy below takes effect only after its release workflow is implemented and validated.

| Gate (planned)                                                   | State today                                                                                                                                                                                                                | Flips when                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Native package catalogs (Codex, Cursor, unlisted Claude add-ons) | Packages stay unlisted; no catalog lists them. The shipping `ycc` entry stays visible in every catalog throughout.                                                                                                         | The v6.0.0 listing PR after rename flips only after package validators, lockstep preflight, per-target migration/dedupe tests, and clean-machine fork installs pass for every listed package. `ycc-all` additionally requires proof of automatic dependency installation. Cursor additionally requires interactive installation and installed-plugin runtime verification. |
| `listed` flag in `ycc/settings/packages.json`                    | Manifest, schema, and loader are implemented; no generator consumes it. New packages stay unlisted; Claude `ycc` stays listed; the legacy Codex `ycc` entry remains. `listed` is **generator input, not a runtime field**. | `packages.json` and the package generators land on `main`.                                                                                                                                                                                                                                                                                                                 |
| Claude `ycc-hooks`                                               | Unlisted; existing installer hooks remain active until migration.                                                                                                                                                          | v6.0.0 rollout requires documented Claude Code 2.1.300 minimum and tested command-level dedupe that preserves user-owned hooks. Older clients retain installer-managed hooks.                                                                                                                                                                                              |
| Codex `ycc-hooks`                                                | Excluded. Hooks stay out of the Codex bundle.                                                                                                                                                                              | YAN-1149 verifies hook trust and dispatch, or a later spike supersedes the YAN-1123 no-go.                                                                                                                                                                                                                                                                                 |
| opencode `@yandy-r/ycc-opencode` npm package                     | Experimental; activation is always opt-in. No publishing workflow exists today; this documentation PR neither publishes the package nor implements its workflow.                                                           | Per owner decision for v6.0.0, CI publishes the package with provenance on a maintainer-pushed product tag.                                                                                                                                                                                                                                                                |
| Repo rename to `agentic-code-plugins`                            | Dry-run prep only.                                                                                                                                                                                                         | The owner renames the repo on GitHub and Forgejo, then one reference-flip PR applies it.                                                                                                                                                                                                                                                                                   |
| Install guides (`docs/install/*`)                                | Existing guides stay public and linked. New v6 package-install and migration content remains unwired until the v6 docs flip.                                                                                               | The v6 docs flip PR links the new package-install and migration content.                                                                                                                                                                                                                                                                                                   |
| Claude `ycc-agents` split                                        | Deferred to **v7.0.0** as a breaking change. The breaking v7.0.0 migration uses distinct manifest names and qualified `ycc-agents:` references.                                                                            | Production reference validation and live dispatch tests pass, then v7.0.0 ships.                                                                                                                                                                                                                                                                                           |

Versioning stays as in [Releasing](#releasing): one maintainer-pushed `v<semver>` tag,
lockstep versions across workflow packages, and no per-plugin tags. Per owner decision for
v6.0.0, CI publishes the experimental, opt-in `@yandy-r/ycc-opencode` npm package with
provenance on that maintainer-pushed product tag. No publishing workflow exists today, and this
documentation PR neither publishes the package nor implements that workflow.

Spike evidence for each gate: YAN-1121 namespace, YAN-1122 hooks, YAN-1123 Codex
marketplace, YAN-1124 Cursor, and YAN-1125 opencode. The dossiers live under
`docs/internal/spikes/`; each is linked from the ADR.

## Releasing

Tags follow `vX.Y.Z` and are cut on `main`. Version files:
`ycc/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (always the same
version). Changelog: none; each release has notes in `docs/releases/<version>.md`.
`/ycc:bundle-release` prepares a release; nothing publishes automatically.

### Every release — from `main`

1. On an up-to-date `main`, run `/ycc:bundle-release <version>`. It bumps both version
   files, regenerates the Cursor, Codex and opencode bundles, runs `./scripts/validate.sh`,
   and drafts `docs/releases/<version>.md`. It never commits.
2. Review the notes, then commit `chore(release): vX.Y.Z` with the version bump, the
   regenerated bundles, `docs/inventory.json` and the release notes.
3. Tag `vX.Y.Z` on that commit and push `main` with the tag.
4. Publish the GitHub release from `docs/releases/<version>.md`.

`/ycc:bundle-release` prints the exact commands for steps 2–4. Use `/ycc:releaser` only
for other projects.

## Planning

Targets are decided in the PR description: say which release a change is for.
